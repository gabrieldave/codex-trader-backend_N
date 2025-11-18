import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

# Obtener las variables de entorno, manejando posibles BOMs y comillas
def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    # Intentar con el nombre normal
    value = os.getenv(key, "")
    if not value:
        # Intentar con posibles variaciones (BOM, espacios, etc.)
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")

# Debug: mostrar las variables cargadas
print(f"SUPABASE_URL: {SUPABASE_URL[:50]}..." if SUPABASE_URL else "SUPABASE_URL: NO ENCONTRADA")
print(f"SUPABASE_SERVICE_KEY: {'ENCONTRADA' if SUPABASE_SERVICE_KEY else 'NO ENCONTRADA'}")

# Verificar todas las variables de entorno disponibles
print("\nVariables de entorno disponibles:")
for key in os.environ.keys():
    if 'SUPABASE' in key or 'OPENAI' in key:
        print(f"  {key}")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("\nError: No se pudieron cargar las variables de entorno.")
    print("   Verifica que el archivo .env este en el directorio actual.")
    exit(1)

# Inicializar el cliente de Supabase
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Verificar si la tabla existe consultando la tabla knowledge
try:
    # Intentar hacer una consulta simple a la tabla
    result = client.table("knowledge").select("id").limit(1).execute()
    print("✅ La tabla 'knowledge' existe y es accesible.")
    print(f"   Respuesta: {result}")
except Exception as e:
    print(f"❌ Error al acceder a la tabla 'knowledge': {e}")
    print("\n💡 La tabla podría no existir o tener un nombre diferente.")
    print("   Necesitas crear la tabla con la siguiente estructura:")
    print("""
   CREATE EXTENSION IF NOT EXISTS vector;
   
   CREATE TABLE IF NOT EXISTS knowledge (
       id BIGSERIAL PRIMARY KEY,
       content TEXT,
       metadata JSONB,
       embedding vector(1536)
   );
   
   CREATE INDEX IF NOT EXISTS knowledge_embedding_idx ON knowledge 
   USING ivfflat (embedding vector_cosine_ops);
   """)

