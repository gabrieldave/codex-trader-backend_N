"""
Script para verificar y corregir el estado de administrador de un usuario.
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Cargar variables de entorno
load_dotenv()

def get_env(key: str, default: str = None) -> str:
    """Obtener variable de entorno limpiando comillas y espacios"""
    value = os.getenv(key, default)
    if value:
        # Limpiar comillas y espacios, y también corregir posibles errores de formato
        value = value.strip('"').strip("'").strip()
        # Corregir "https=" a "https:" si existe
        if "https=" in value:
            value = value.replace("https=", "https:")
        return value
    return value

# Configurar Supabase
SUPABASE_URL = get_env("SUPABASE_URL") or get_env("SUPABASE_REST_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY") or get_env("SUPABASE_SERVICE_ROLE_KEY")

# Si SUPABASE_URL es una URL de DB, derivar la REST URL
if SUPABASE_URL and SUPABASE_URL.startswith("postgresql://"):
    # Derivar URL REST desde URL de DB (usar la misma lógica que main.py)
    from urllib.parse import urlparse
    try:
        parsed = urlparse(SUPABASE_URL)
        host = parsed.hostname or ""
        username = parsed.username or ""
        
        # Caso 1: URL de pooler (ej: aws-0-us-west-1.pooler.supabase.com)
        if "pooler.supabase.com" in host or "pooler.supabase.co" in host:
            if username and username.startswith("postgres."):
                project_ref = username.replace("postgres.", "")
                if project_ref:
                    SUPABASE_URL = f"https://{project_ref}.supabase.co"
        
        # Caso 2: Conexión directa (ej: db.xxx.supabase.co)
        elif "db." in host and ".supabase.co" in host:
            project_ref = host.replace("db.", "").replace(".supabase.co", "")
            if project_ref:
                SUPABASE_URL = f"https://{project_ref}.supabase.co"
    except Exception as e:
        print(f"WARNING: Error al derivar URL REST: {e}")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("❌ ERROR: Faltan variables de entorno SUPABASE_URL y SUPABASE_SERVICE_KEY")
    print(f"   SUPABASE_URL: {SUPABASE_URL or 'No configurada'}")
    print(f"   SUPABASE_SERVICE_KEY: {'Configurada' if SUPABASE_SERVICE_KEY else 'No configurada'}")
    exit(1)

print(f"Conectando a Supabase: {SUPABASE_URL}")

# Crear cliente de Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    print("OK: Cliente de Supabase creado correctamente\n")
except Exception as e:
    print(f"ERROR: Error al crear cliente de Supabase: {e}")
    exit(1)

def verificar_admin(email: str):
    """Verifica el estado de admin de un usuario por email"""
    print(f"\n{'='*60}")
    print(f"Verificando estado de admin para: {email}")
    print(f"{'='*60}\n")
    
    # 1. Buscar usuario por email en auth.users
    try:
        users_response = supabase.auth.admin.list_users()
        # list_users() devuelve un objeto con .users o directamente una lista
        users_list = users_response.users if hasattr(users_response, 'users') else users_response
        user = None
        for u in users_list:
            if u.email and u.email.lower() == email.lower():
                user = u
                break
        
        if not user:
            print(f"ERROR: Usuario no encontrado con email: {email}")
            return
        
        print(f"OK: Usuario encontrado:")
        print(f"   ID: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Creado: {user.created_at}")
        
        # 2. Verificar perfil en profiles
        try:
            profile_response = supabase.table("profiles").select("*").eq("id", user.id).execute()
            
            if not profile_response.data:
                print(f"\nWARNING: Perfil no encontrado en la tabla profiles")
                print(f"   Creando perfil...")
                # Crear perfil si no existe
                supabase.table("profiles").insert({
                    "id": user.id,
                    "email": user.email,
                    "is_admin": True
                }).execute()
                print(f"   OK: Perfil creado con is_admin=True")
            else:
                profile = profile_response.data[0]
                print(f"\nPerfil encontrado:")
                print(f"   Email: {profile.get('email', 'N/A')}")
                print(f"   is_admin: {profile.get('is_admin', 'N/A')}")
                print(f"   tokens_restantes: {profile.get('tokens_restantes', 'N/A')}")
                
                # Verificar si is_admin existe como columna
                if 'is_admin' not in profile:
                    print(f"\nWARNING: La columna 'is_admin' no existe en la tabla profiles")
                    print(f"   Necesitas ejecutar el SQL para agregar la columna:")
                    print(f"\n   ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;")
                    print(f"   CREATE INDEX IF NOT EXISTS profiles_is_admin_idx ON profiles(is_admin);")
                else:
                    is_admin = profile.get('is_admin', False)
                    if not is_admin:
                        print(f"\nWARNING: El usuario NO esta marcado como admin (is_admin=False)")
                        respuesta = input(f"   ¿Deseas marcar este usuario como admin? (s/n): ")
                        if respuesta.lower() == 's':
                            supabase.table("profiles").update({
                                "is_admin": True
                            }).eq("id", user.id).execute()
                            print(f"   OK: Usuario marcado como admin")
                        else:
                            print(f"   ERROR: No se actualizó el estado de admin")
                    else:
                        print(f"\nOK: El usuario ESTA marcado como admin (is_admin=True)")
        
        except Exception as e:
            print(f"\nERROR: Error al consultar perfil: {e}")
            import traceback
            traceback.print_exc()
    
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

def verificar_columna_is_admin():
    """Verifica si la columna is_admin existe en la tabla profiles"""
    print(f"\n{'='*60}")
    print(f"Verificando si existe la columna is_admin en profiles")
    print(f"{'='*60}\n")
    
    try:
        # Intentar hacer un SELECT con is_admin
        response = supabase.table("profiles").select("is_admin").limit(1).execute()
        print(f"OK: La columna 'is_admin' existe en la tabla profiles")
        return True
    except Exception as e:
        error_msg = str(e)
        if "column" in error_msg.lower() and "does not exist" in error_msg.lower():
            print(f"ERROR: La columna 'is_admin' NO existe en la tabla profiles")
            print(f"\nEjecuta este SQL en Supabase:")
            print(f"\n   ALTER TABLE profiles ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;")
            print(f"   CREATE INDEX IF NOT EXISTS profiles_is_admin_idx ON profiles(is_admin);")
            return False
        else:
            print(f"WARNING: Error al verificar columna: {e}")
            return None

if __name__ == "__main__":
    import sys
    
    # Verificar primero si existe la columna
    columna_existe = verificar_columna_is_admin()
    
    # Si el usuario proporciona un email como argumento
    if len(sys.argv) > 1:
        email = sys.argv[1]
        verificar_admin(email)
    else:
        # Pedir email interactivamente
        email = input("\nIngresa el email del usuario a verificar: ").strip()
        if email:
            verificar_admin(email)
        else:
            print("ERROR: No se proporciono email")

