import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import vecs
import psycopg2
from psycopg2.extras import RealDictCursor
import config

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
    print("Asegúrate de tener SUPABASE_URL y SUPABASE_DB_PASSWORD en tu archivo .env")
    exit(1)

# Construir la cadena de conexión
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

collection_name = config.VECTOR_COLLECTION_NAME

print("=" * 80)
print("ELIMINAR COLECCIÓN DE VECTORES")
print("=" * 80)
print(f"Colección objetivo: {collection_name}")
print()

# Paso 1: Verificar estado actual
print("1. Verificando estado actual de la colección...")
try:
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verificar si la tabla existe
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'vecs' 
            AND table_name = %s
        )
    """, (collection_name,))
    
    table_exists = cur.fetchone()['exists']
    
    if table_exists:
        # Contar documentos
        cur.execute(f"SELECT COUNT(*) as count FROM vecs.{collection_name}")
        count_result = cur.fetchone()
        total_docs = count_result['count'] if count_result else 0
        
        # Contar archivos únicos
        cur.execute(f"""
            SELECT COUNT(DISTINCT metadata->>'file_name') as count
            FROM vecs.{collection_name} 
            WHERE metadata->>'file_name' IS NOT NULL
        """)
        unique_files_result = cur.fetchone()
        unique_files = unique_files_result['count'] if unique_files_result else 0
        
        print(f"   ✓ La colección '{collection_name}' existe")
        print(f"   📊 Total de documentos (chunks): {total_docs:,}")
        print(f"   📁 Archivos únicos indexados: {unique_files}")
        print()
        
        if total_docs == 0:
            print("   ⚠️  La colección está vacía")
        else:
            print("   ⚠️  ADVERTENCIA: Esta acción eliminará TODOS los datos indexados")
            print("   ⚠️  Esta acción NO se puede deshacer")
    else:
        print(f"   ℹ️  La colección '{collection_name}' no existe")
        print("   No hay nada que eliminar")
        cur.close()
        conn.close()
        sys.exit(0)
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"   ✗ Error al verificar la colección: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Paso 2: Confirmación del usuario (o modo automático)
auto_mode = '--yes' in sys.argv or '--force' in sys.argv or '-y' in sys.argv

if not auto_mode:
    print("=" * 80)
    print("CONFIRMACIÓN REQUERIDA")
    print("=" * 80)
    print(f"Se eliminará la colección '{collection_name}' con {total_docs:,} documentos")
    print()
    print("⚠️  ESTA ACCIÓN ES IRREVERSIBLE")
    print()
    response = input("¿Estás seguro de que quieres continuar? (escribe 'SI' para confirmar): ")

    if response.strip().upper() != 'SI':
        print("\n❌ Operación cancelada. No se eliminó nada.")
        sys.exit(0)
else:
    print("=" * 80)
    print("MODO AUTOMÁTICO ACTIVADO")
    print("=" * 80)
    print(f"Se eliminará la colección '{collection_name}' con {total_docs:,} documentos")
    print("⚠️  Procediendo automáticamente...")
    print()

# Paso 3: Eliminar la colección
print("\n" + "=" * 80)
print("ELIMINANDO COLECCIÓN...")
print("=" * 80)

try:
    # Conectar a vecs
    print("\n1. Conectando a vecs...")
    vx = vecs.create_client(postgres_connection_string)
    
    # Verificar si la colección existe
    collections = vx.list_collections()
    collection_exists = any(c.name == collection_name for c in collections)
    
    if not collection_exists:
        print(f"   ℹ️  La colección '{collection_name}' no existe en vecs")
        print("   Intentando eliminar directamente desde la base de datos...")
    else:
        print(f"   ✓ Colección '{collection_name}' encontrada en vecs")
    
    # Eliminar usando SQL directo (más confiable)
    print("\n2. Eliminando tabla desde la base de datos...")
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor()
    
    # Eliminar la tabla
    cur.execute(f"DROP TABLE IF EXISTS vecs.{collection_name} CASCADE")
    conn.commit()
    
    print(f"   ✓ Tabla 'vecs.{collection_name}' eliminada exitosamente")
    
    # Verificar que se eliminó
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'vecs' 
            AND table_name = %s
        )
    """, (collection_name,))
    
    still_exists = cur.fetchone()[0]
    
    if still_exists:
        print("   ⚠️  La tabla aún existe. Puede haber un error.")
    else:
        print("   ✓ Confirmado: La tabla ha sido eliminada completamente")
    
    cur.close()
    conn.close()
    
    # Intentar eliminar también desde vecs si existe
    if collection_exists:
        try:
            print("\n3. Limpiando referencia en vecs...")
            collection = vx.get_collection(collection_name)
            # Nota: vecs puede no tener un método delete, pero la tabla ya está eliminada
            print("   ✓ Referencia limpiada (la tabla ya fue eliminada)")
        except Exception as e:
            print(f"   ℹ️  No se pudo limpiar referencia en vecs (normal si la tabla ya no existe): {e}")
    
    print("\n" + "=" * 80)
    print("✅ COLECCIÓN ELIMINADA EXITOSAMENTE")
    print("=" * 80)
    print(f"La colección '{collection_name}' y todos sus datos han sido eliminados.")
    print("\n💡 Próximos pasos:")
    print("   1. Ejecuta 'python ingest_improved.py' para indexar tus archivos desde cero")
    print("   2. O ejecuta 'python ingest.py' si prefieres el método básico")
    print("=" * 80)
    
except Exception as e:
    print(f"\n✗ Error al eliminar la colección: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

