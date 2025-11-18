import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import vecs
import psycopg2

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

# Función para obtener variables de entorno manejando BOM y comillas
def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    value = os.getenv(key, "")
    if not value:
        # Intentar con posibles variaciones (BOM, espacios, etc.)
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener las variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("Error: Faltan variables de entorno")
    exit(1)

# Construir la cadena de conexión
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("=" * 60)
print("VERIFICANDO DATOS EN VECS (Supabase Vector Store)")
print("=" * 60)

try:
    # Conectar a vecs
    vx = vecs.create_client(postgres_connection_string)
    
    # Listar todas las colecciones
    print("\n1. Colecciones disponibles:")
    collections = vx.list_collections()
    for col in collections:
        print(f"   - {col.name} (dimensión: {col.dimension})")
    
    # Obtener la colección knowledge
    if "knowledge" in [c.name for c in collections]:
        print("\n2. Accediendo a la colección 'knowledge'...")
        collection = vx.get_collection("knowledge")
        print(f"   ✓ Colección 'knowledge' encontrada (dimensión: {collection.dimension})")
        
        # Consultar directamente la base de datos para contar
        print("\n3. Consultando la base de datos directamente...")
        conn = psycopg2.connect(postgres_connection_string)
        cur = conn.cursor()
        
        # Contar documentos
        cur.execute("SELECT COUNT(*) FROM vecs.knowledge")
        count = cur.fetchone()[0]
        print(f"   ✓ Total de documentos: {count}")
        
        if count > 0:
            print("\n4. Verificando estructura de la tabla...")
            # Primero verificar las columnas de la tabla
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'vecs' AND table_name = 'knowledge'
            """)
            columns = cur.fetchall()
            print("   Columnas en vecs.knowledge:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]}")
            
            print("\n5. Obteniendo algunos documentos de ejemplo...")
            
            # Consultar la tabla de vecs para ver los datos (sin la columna embedding que no existe)
            cur.execute("""
                SELECT id, metadata
                FROM vecs.knowledge 
                LIMIT 5
            """)
            
            rows = cur.fetchall()
            print(f"\n   Primeros {len(rows)} registros:")
            for i, row in enumerate(rows, 1):
                print(f"\n   Registro {i}:")
                print(f"   - ID: {row[0]}")
                if row[1]:
                    metadata = row[1]
                    print(f"   - Metadata: {metadata}")
            
            # Ver algunos metadatos específicos
            print("\n6. Archivos indexados:")
            cur.execute("""
                SELECT DISTINCT 
                    metadata->>'file_name' as file_name, 
                    metadata->>'file_type' as file_type,
                    COUNT(*) as chunks
                FROM vecs.knowledge 
                GROUP BY metadata->>'file_name', metadata->>'file_type'
                ORDER BY chunks DESC
                LIMIT 10
            """)
            rows2 = cur.fetchall()
            if rows2:
                for row in rows2:
                    print(f"   - Archivo: {row[0] or 'N/A'}, Tipo: {row[1] or 'N/A'}, Chunks: {row[2]}")
            else:
                # Si no hay metadatos estructurados, mostrar IDs únicos
                cur.execute("SELECT COUNT(DISTINCT id) FROM vecs.knowledge")
                unique_ids = cur.fetchone()[0]
                print(f"   Total de documentos únicos: {unique_ids}")
            
            cur.close()
            conn.close()
        else:
            print("\n   ⚠️  La colección existe pero está vacía")
            print("   Esto puede significar que la ingesta no se completó correctamente")
            cur.close()
            conn.close()
    else:
        print("\n   ✗ No se encontró la colección 'knowledge'")
        
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("VERIFICACIÓN COMPLETA")
print("=" * 60)

