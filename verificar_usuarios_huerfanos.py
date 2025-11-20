"""Script para verificar usuarios que existen en auth.users pero no en profiles"""
import os
import sys
from dotenv import load_dotenv

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

def get_env(key, default=""):
    """Obtiene variable de entorno y limpia comillas."""
    value = os.getenv(key, default)
    if not value:
        return default
    value = value.strip('"').strip("'").strip()
    if value.startswith("https="):
        value = value.replace("https=", "https://", 1)
    if value.startswith("https:////"):
        value = value.replace("https:////", "https://", 1)
    return value

SUPABASE_REST_URL = get_env("SUPABASE_REST_URL") or get_env("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY", "")

if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
    print("❌ ERROR: Faltan variables de entorno SUPABASE_REST_URL y SUPABASE_SERVICE_KEY")
    sys.exit(1)

try:
    from supabase import create_client
    
    print("=" * 70)
    print("VERIFICACIÓN: USUARIOS HUÉRFANOS")
    print("=" * 70)
    print("(Usuarios que existen en auth.users pero NO en profiles)")
    print()
    
    supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
    
    # 1. Obtener todos los usuarios de auth.users
    print("[1/3] Obteniendo usuarios de auth.users...")
    try:
        auth_users_response = supabase.auth.admin.list_users()
        
        if not auth_users_response or not hasattr(auth_users_response, 'users'):
            print("   ⚠️ No se pudieron obtener usuarios de auth.users")
            print("   (Necesitas permisos de admin)")
            sys.exit(1)
        
        auth_users = auth_users_response.users
        print(f"   ✅ Encontrados {len(auth_users)} usuario(s) en auth.users")
        print()
    except Exception as e:
        print(f"   ❌ Error al obtener usuarios de auth.users: {e}")
        sys.exit(1)
    
    # 2. Obtener todos los perfiles
    print("[2/3] Obteniendo perfiles de profiles...")
    try:
        profiles_response = supabase.table("profiles").select("id, email").execute()
        profiles = profiles_response.data if profiles_response.data else []
        profile_ids = {profile['id'] for profile in profiles}
        print(f"   ✅ Encontrados {len(profiles)} perfil(es) en profiles")
        print()
    except Exception as e:
        print(f"   ❌ Error al obtener perfiles: {e}")
        sys.exit(1)
    
    # 3. Encontrar usuarios huérfanos
    print("[3/3] Buscando usuarios huérfanos...")
    orphaned_users = []
    
    for auth_user in auth_users:
        user_id = auth_user.id
        user_email = auth_user.email or "Sin email"
        
        if user_id not in profile_ids:
            orphaned_users.append({
                'id': user_id,
                'email': user_email,
                'created_at': auth_user.created_at,
                'email_confirmed_at': auth_user.email_confirmed_at,
                'last_sign_in_at': auth_user.last_sign_in_at
            })
    
    print("=" * 70)
    print("RESULTADO")
    print("=" * 70)
    print()
    
    if orphaned_users:
        print(f"⚠️ PROBLEMA: Encontrados {len(orphaned_users)} usuario(s) huérfano(s):")
        print()
        
        for i, user in enumerate(orphaned_users, 1):
            print(f"{i}. Email: {user['email']}")
            print(f"   ID: {user['id']}")
            print(f"   Creado: {user['created_at']}")
            print(f"   Email confirmado: {'Sí' if user['email_confirmed_at'] else 'No'}")
            print(f"   Último login: {user['last_sign_in_at'] or 'Nunca'}")
            print()
        
        print("=" * 70)
        print("EXPLICACIÓN DEL PROBLEMA")
        print("=" * 70)
        print()
        print("Estos usuarios existen en auth.users pero NO tienen perfil en profiles.")
        print("Esto causa que:")
        print("  1. No puedan usar la aplicación (error: 'Perfil de usuario no encontrado')")
        print("  2. No puedan registrarse nuevamente (Supabase dice que el email ya existe)")
        print("  3. Queden en un estado inconsistente")
        print()
        print("El script de limpieza eliminó los perfiles pero NO eliminó los usuarios")
        print("de auth.users, causando este problema.")
        print()
        print("=" * 70)
        print("SOLUCIÓN")
        print("=" * 70)
        print()
        print("Opciones:")
        print("  1. Eliminar estos usuarios de auth.users (recomendado)")
        print("  2. Crear perfiles para estos usuarios (si quieres mantenerlos)")
        print()
        print("Para eliminar, ejecuta:")
        print("  python eliminar_usuarios_huerfanos.py")
        print()
    else:
        print("✅ No hay usuarios huérfanos. Todos los usuarios tienen perfil.")
        print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

