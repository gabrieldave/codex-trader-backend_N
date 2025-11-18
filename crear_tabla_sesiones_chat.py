"""
Script para crear la tabla de sesiones de chat en Supabase
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv
from urllib.parse import quote_plus

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def get_env(key):
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("❌ Error: Faltan variables de entorno SUPABASE_URL o SUPABASE_DB_PASSWORD")
    sys.exit(1)

# Extraer el project_ref de la URL de Supabase
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")

# Construir la cadena de conexión
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("="*80)
print("🔧 CREANDO TABLA DE SESIONES DE CHAT")
print("="*80)
print()

try:
    # Leer el archivo SQL
    with open("crear_tablas_completas.sql", "r", encoding="utf-8") as f:
        sql_script = f.read()
    
    # Conectar a la base de datos
    conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
    conn.autocommit = True
    cur = conn.cursor()
    
    # Ejecutar el script SQL
    print("📝 Ejecutando script SQL...")
    cur.execute(sql_script)
    
    print("✅ Tabla de sesiones de chat creada exitosamente")
    print()
    print("📋 Tablas creadas/modificadas:")
    print("  - chat_sessions: Tabla principal de sesiones de chat")
    print("  - conversations: Modificada para agregar conversation_id")
    print()
    print("🔒 Políticas RLS configuradas:")
    print("  - SELECT: Usuarios pueden ver solo sus propias sesiones")
    print("  - INSERT: Usuarios pueden crear solo sus propias sesiones")
    print("  - UPDATE: Usuarios pueden actualizar solo sus propias sesiones")
    print("  - DELETE: Usuarios pueden eliminar solo sus propias sesiones")
    print()
    print("⚙️  Funciones y triggers creados:")
    print("  - update_chat_sessions_updated_at: Actualiza updated_at automáticamente")
    print("  - generate_chat_session_title: Genera título automático")
    print()
    
    cur.close()
    conn.close()
    
    print("="*80)
    print("✅ ¡Tabla de sesiones de chat creada exitosamente!")
    print("="*80)
    
except FileNotFoundError:
    print("❌ Error: No se encontró el archivo create_chat_sessions_table.sql")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error al crear la tabla: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

