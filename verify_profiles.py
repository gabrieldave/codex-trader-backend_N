import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
from supabase import create_client
import psycopg2

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener las variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not SUPABASE_DB_PASSWORD:
    print("Error: Faltan variables de entorno")
    exit(1)

print("=" * 70)
print("VERIFICANDO SISTEMA DE PERFILES")
print("=" * 70)

# Inicializar cliente de Supabase
client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# Construir conexión PostgreSQL para consultas directas
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

try:
    # 1. Verificar que la tabla existe usando el cliente de Supabase
    print("\n1. Verificando tabla 'profiles'...")
    try:
        result = client.table("profiles").select("id").limit(1).execute()
        print("   ✓ Tabla 'profiles' existe y es accesible")
    except Exception as e:
        print(f"   ✗ Error al acceder a la tabla: {e}")
        exit(1)
    
    # 2. Verificar estructura de la tabla usando PostgreSQL directo
    print("\n2. Verificando estructura de la tabla...")
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            column_name, 
            data_type, 
            column_default,
            is_nullable
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = 'profiles'
        ORDER BY ordinal_position
    """)
    
    columns = cur.fetchall()
    print("   Columnas en la tabla 'profiles':")
    for col in columns:
        default = col[2] if col[2] else "NULL"
        nullable = "NULL" if col[3] == "YES" else "NOT NULL"
        print(f"   - {col[0]}: {col[1]} (default: {default}, {nullable})")
    
    # Verificar que tokens_restantes tiene el default correcto
    tokens_col = next((c for c in columns if c[0] == 'tokens_restantes'), None)
    if tokens_col and '20000' in str(tokens_col[2]):
        print("   ✓ tokens_restantes tiene el valor por defecto correcto (20000)")
    else:
        print("   ⚠️  tokens_restantes podría no tener el default correcto")
    
    # 3. Verificar que RLS está habilitado
    print("\n3. Verificando Row Level Security (RLS)...")
    cur.execute("""
        SELECT tablename, rowsecurity 
        FROM pg_tables 
        WHERE schemaname = 'public' AND tablename = 'profiles'
    """)
    
    rls_info = cur.fetchone()
    if rls_info and rls_info[1]:
        print("   ✓ RLS está habilitado en la tabla 'profiles'")
    else:
        print("   ✗ RLS NO está habilitado")
    
    # 4. Verificar políticas RLS
    print("\n4. Verificando políticas RLS...")
    cur.execute("""
        SELECT 
            policyname,
            cmd,
            qual
        FROM pg_policies 
        WHERE schemaname = 'public' AND tablename = 'profiles'
        ORDER BY policyname
    """)
    
    policies = cur.fetchall()
    if policies:
        print(f"   ✓ Se encontraron {len(policies)} políticas:")
        for policy in policies:
            print(f"   - {policy[0]} ({policy[1]})")
            print(f"     Condición: {policy[2]}")
    else:
        print("   ✗ No se encontraron políticas RLS")
    
    # 5. Verificar función y trigger
    print("\n5. Verificando función handle_new_user()...")
    cur.execute("""
        SELECT routine_name, routine_type
        FROM information_schema.routines
        WHERE routine_schema = 'public' AND routine_name = 'handle_new_user'
    """)
    
    function = cur.fetchone()
    if function:
        print(f"   ✓ Función '{function[0]}' existe (tipo: {function[1]})")
    else:
        print("   ✗ Función 'handle_new_user' NO existe")
    
    print("\n6. Verificando trigger on_auth_user_created...")
    cur.execute("""
        SELECT 
            trigger_name,
            event_manipulation,
            event_object_table,
            action_statement
        FROM information_schema.triggers
        WHERE trigger_schema = 'auth' 
        AND trigger_name = 'on_auth_user_created'
    """)
    
    trigger = cur.fetchone()
    if trigger:
        print(f"   ✓ Trigger '{trigger[0]}' existe")
        print(f"     Evento: {trigger[1]} en tabla {trigger[2]}")
    else:
        print("   ✗ Trigger 'on_auth_user_created' NO existe")
    
    # 6. Contar perfiles existentes (si hay)
    print("\n7. Verificando perfiles existentes...")
    cur.execute("SELECT COUNT(*) FROM public.profiles")
    count = cur.fetchone()[0]
    print(f"   Total de perfiles en la tabla: {count}")
    
    if count > 0:
        cur.execute("SELECT id, email, tokens_restantes FROM public.profiles LIMIT 5")
        profiles = cur.fetchall()
        print("\n   Primeros perfiles:")
        for profile in profiles:
            print(f"   - ID: {profile[0][:8]}..., Email: {profile[1]}, Tokens: {profile[2]}")
    
    cur.close()
    conn.close()
    
    print("\n" + "=" * 70)
    print("VERIFICACIÓN COMPLETA")
    print("=" * 70)
    print("\n✅ Si todos los checks muestran ✓, el sistema está configurado correctamente!")
    print("   Los nuevos usuarios recibirán automáticamente 20,000 tokens al registrarse.")
    
except Exception as e:
    print(f"\n✗ Error durante la verificación: {e}")
    import traceback
    traceback.print_exc()

