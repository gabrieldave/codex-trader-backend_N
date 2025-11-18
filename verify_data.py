import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
from supabase import create_client

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
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Error: Faltan variables de entorno")
    exit(1)

# Inicializar el cliente de Supabase
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

print("=" * 60)
print("VERIFICANDO DATOS EN SUPABASE")
print("=" * 60)

# Verificar la tabla knowledge usando el cliente de Supabase
print("\n1. Verificando tabla 'knowledge'...")
try:
    result = client.table("knowledge").select("*").limit(10).execute()
    print(f"   ✓ Tabla 'knowledge' encontrada")
    print(f"   Registros encontrados: {len(result.data)}")
    
    if result.data:
        print("\n   Primeros registros:")
        for i, record in enumerate(result.data[:3], 1):
            print(f"\n   Registro {i}:")
            print(f"   - ID: {record.get('id', 'N/A')}")
            print(f"   - Contenido (primeros 100 chars): {str(record.get('content', 'N/A'))[:100]}...")
            print(f"   - Metadata: {record.get('metadata', 'N/A')}")
    else:
        print("   ⚠️  No se encontraron registros en la tabla 'knowledge'")
except Exception as e:
    print(f"   ✗ Error al acceder a la tabla 'knowledge': {e}")

# Verificar si existe una colección de vecs
print("\n2. Verificando colección 'knowledge' en vecs...")
try:
    # Intentar usar vecs para verificar la colección
    import vecs
    project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
    encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
    postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"
    
    vx = vecs.create_client(postgres_connection_string)
    collections = vx.list_collections()
    print(f"   Colecciones encontradas: {collections}")
    
    if "knowledge" in collections:
        collection = vx.get_collection("knowledge")
        print(f"   ✓ Colección 'knowledge' existe")
        # Contar documentos
        count = collection.count()
        print(f"   Documentos en la colección: {count}")
        
        # Obtener algunos documentos de ejemplo
        if count > 0:
            print("\n   Primeros documentos:")
            # Usar list para obtener algunos IDs
            # Nota: vecs no tiene un método directo para listar, pero podemos intentar
            print("   (Los documentos están almacenados como vectores)")
    else:
        print("   ⚠️  No se encontró la colección 'knowledge'")
        print(f"   Colecciones disponibles: {collections}")
        
except Exception as e:
    print(f"   ✗ Error al verificar vecs: {e}")

# Verificar esquema de la base de datos
print("\n3. Verificando esquema de la base de datos...")
try:
    # Intentar consultar información del esquema
    result = client.rpc('exec_sql', {
        'query': "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE '%knowledge%' OR table_name LIKE '%vecs%'"
    }).execute()
    print("   Tablas relacionadas encontradas")
except Exception as e:
    # Si no funciona el RPC, intentar consultar directamente
    try:
        # Verificar si existe la tabla knowledge
        result = client.table("knowledge").select("id").limit(1).execute()
        print("   ✓ Esquema verificado")
    except Exception as e2:
        print(f"   ⚠️  No se pudo verificar el esquema: {e2}")

print("\n" + "=" * 60)
print("VERIFICACIÓN COMPLETA")
print("=" * 60)
print("\n💡 Nota: Los datos pueden estar almacenados en:")
print("   1. Tabla 'knowledge' (si usaste el formato tradicional)")
print("   2. Esquema 'vecs' con colección 'knowledge' (formato vecs)")
print("\n   Para ver los datos en Supabase Dashboard:")
print("   - Ve a Table Editor y busca 'knowledge' o 'vecs_knowledge'")
print("   - O ve a SQL Editor y ejecuta: SELECT * FROM knowledge LIMIT 10;")

