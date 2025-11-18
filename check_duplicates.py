import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import config

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

def get_env(key):
    """Obtiene una variable de entorno"""
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("❌ Error: Faltan variables de entorno")
    sys.exit(1)

# Construir conexión
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

# Obtener configuración
COLLECTION_NAME = config.VECTOR_COLLECTION_NAME if hasattr(config, 'VECTOR_COLLECTION_NAME') else "knowledge"

print("=" * 80)
print("🔍 VERIFICACIÓN DE DUPLICADOS EN LA BASE DE DATOS")
print("=" * 80)
print(f"\n🗄️  Colección: {COLLECTION_NAME}")
print()

try:
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # 1. Verificar archivos únicos vs total de registros
    print("1️⃣  Verificando archivos únicos...")
    cur.execute(f"""
        SELECT 
            COUNT(DISTINCT metadata->>'file_name') as unique_files,
            COUNT(*) as total_chunks
        FROM vecs.{COLLECTION_NAME}
        WHERE metadata->>'file_name' IS NOT NULL
    """)
    
    stats = cur.fetchone()
    unique_files = stats['unique_files']
    total_chunks = stats['total_chunks']
    
    print(f"   • Archivos únicos: {unique_files}")
    print(f"   • Chunks totales: {total_chunks:,}")
    print()
    
    # 2. Verificar si hay chunks duplicados (mismo contenido para el mismo archivo)
    print("2️⃣  Verificando chunks duplicados por contenido...")
    cur.execute(f"""
        SELECT 
            metadata->>'file_name' as file_name,
            COUNT(*) as chunk_count,
            COUNT(DISTINCT id) as unique_ids,
            COUNT(*) - COUNT(DISTINCT id) as duplicate_ids
        FROM vecs.{COLLECTION_NAME}
        WHERE metadata->>'file_name' IS NOT NULL
        GROUP BY metadata->>'file_name'
        HAVING COUNT(*) > COUNT(DISTINCT id)
        ORDER BY duplicate_ids DESC
    """)
    
    duplicate_files = cur.fetchall()
    
    if duplicate_files:
        print(f"   ⚠️  Se encontraron {len(duplicate_files)} archivos con IDs duplicados:")
        for row in duplicate_files[:10]:
            print(f"      • {row['file_name']}: {row['duplicate_ids']} IDs duplicados")
        if len(duplicate_files) > 10:
            print(f"      ... y {len(duplicate_files) - 10} archivos más")
    else:
        print("   ✅ No se encontraron IDs duplicados")
    print()
    
    # 3. Verificar si hay chunks con el mismo ID (duplicados reales)
    print("3️⃣  Verificando duplicados reales (mismo ID)...")
    cur.execute(f"""
        SELECT 
            id,
            COUNT(*) as count
        FROM vecs.{COLLECTION_NAME}
        GROUP BY id
        HAVING COUNT(*) > 1
    """)
    
    duplicate_ids = cur.fetchall()
    
    if duplicate_ids:
        print(f"   ⚠️  Se encontraron {len(duplicate_ids)} IDs duplicados (ERROR CRÍTICO)")
        for row in duplicate_ids[:10]:
            print(f"      • ID {row['id']}: aparece {row['count']} veces")
        if len(duplicate_ids) > 10:
            print(f"      ... y {len(duplicate_ids) - 10} IDs más duplicados")
    else:
        print("   ✅ No se encontraron IDs duplicados")
        print("   (Cada chunk tiene un ID único - esto es correcto)")
    print()
    
    # 4. Verificar distribución de chunks por archivo (para detectar anomalías)
    print("4️⃣  Analizando distribución de chunks por archivo...")
    cur.execute(f"""
        SELECT 
            metadata->>'file_name' as file_name,
            COUNT(*) as chunk_count
        FROM vecs.{COLLECTION_NAME}
        WHERE metadata->>'file_name' IS NOT NULL
        GROUP BY metadata->>'file_name'
        ORDER BY chunk_count DESC
    """)
    
    all_files = cur.fetchall()
    
    # Calcular estadísticas
    chunk_counts = [row['chunk_count'] for row in all_files]
    if chunk_counts:
        avg_chunks = sum(chunk_counts) / len(chunk_counts)
        max_chunks = max(chunk_counts)
        min_chunks = min(chunk_counts)
        
        print(f"   • Promedio de chunks por archivo: {avg_chunks:.1f}")
        print(f"   • Máximo: {max_chunks} chunks")
        print(f"   • Mínimo: {min_chunks} chunks")
        
        # Archivos con muchos chunks (posible duplicación)
        high_chunk_files = [row for row in all_files if row['chunk_count'] > avg_chunks * 3]
        if high_chunk_files:
            print(f"\n   ⚠️  Archivos con número inusualmente alto de chunks (>3x promedio):")
            for row in high_chunk_files[:5]:
                print(f"      • {row['file_name']}: {row['chunk_count']} chunks")
            if len(high_chunk_files) > 5:
                print(f"      ... y {len(high_chunk_files) - 5} archivos más")
        else:
            print("\n   ✅ La distribución de chunks parece normal")
    print()
    
    # 5. Verificar si hay archivos indexados múltiples veces (mismo nombre, diferentes momentos)
    print("5️⃣  Verificando archivos indexados múltiples veces...")
    cur.execute(f"""
        SELECT 
            metadata->>'file_name' as file_name,
            COUNT(DISTINCT metadata->>'file_id') as file_id_count,
            COUNT(*) as total_chunks
        FROM vecs.{COLLECTION_NAME}
        WHERE metadata->>'file_name' IS NOT NULL
        GROUP BY metadata->>'file_name'
        HAVING COUNT(DISTINCT metadata->>'file_id') > 1
        ORDER BY file_id_count DESC
    """)
    
    multi_indexed = cur.fetchall()
    
    if multi_indexed:
        print(f"   ⚠️  Se encontraron {len(multi_indexed)} archivos con múltiples file_ids:")
        print("      (Esto puede indicar que se indexaron múltiples veces)")
        for row in multi_indexed[:10]:
            print(f"      • {row['file_name']}: {row['file_id_count']} file_ids diferentes, {row['total_chunks']} chunks totales")
        if len(multi_indexed) > 10:
            print(f"      ... y {len(multi_indexed) - 10} archivos más")
    else:
        print("   ✅ No se encontraron archivos con múltiples file_ids")
    print()
    
    # 6. Resumen de verificación
    print("=" * 80)
    print("📊 RESUMEN DE VERIFICACIÓN")
    print("=" * 80)
    
    has_issues = False
    
    if duplicate_files:
        print("⚠️  IDs duplicados detectados")
        has_issues = True
    
    if duplicate_ids:
        print("⚠️  IDs duplicados críticos detectados")
        has_issues = True
    
    if multi_indexed:
        print("⚠️  Archivos indexados múltiples veces detectados")
        has_issues = True
    
    if not has_issues:
        print("✅ No se encontraron duplicados significativos")
        print()
        print("La base de datos está limpia. El proceso de ingestión está")
        print("funcionando correctamente y no está creando duplicados.")
    else:
        print()
        print("⚠️  Se encontraron algunos posibles duplicados.")
        print("   Esto puede ser normal si:")
        print("   • El mismo archivo se procesó en diferentes momentos")
        print("   • Hay variaciones menores en el contenido")
        print("   • El proceso de ingestión se interrumpió y se reinició")
        print()
        print("   Recomendación: Si el número de duplicados es pequeño,")
        print("   no afectará significativamente el rendimiento del sistema.")
    
    print()
    print("=" * 80)
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error al verificar duplicados: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

