"""Script para verificar usuario daky31@gmail.com y su estado de emails"""
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
    
    print("=" * 60)
    print("VERIFICACIÓN DE USUARIO daky31@gmail.com")
    print("=" * 60)
    print()
    
    supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
    
    # Buscar usuario en profiles
    users_response = supabase.table("profiles").select(
        "id, email, created_at, welcome_email_sent, tokens_restantes, current_plan"
    ).ilike("email", "%daky31%").execute()
    
    if not users_response.data:
        print("❌ Usuario daky31@gmail.com NO encontrado en profiles")
        print()
        print("Posibles causas:")
        print("  1. El usuario no se ha registrado todavía")
        print("  2. El email fue escrito diferente")
        print("  3. El usuario fue eliminado")
    else:
        print(f"✅ Encontrados {len(users_response.data)} usuario(s):")
        print()
        
        for user in users_response.data:
            print(f"Email: {user.get('email')}")
            print(f"ID: {user.get('id')}")
            print(f"Creado: {user.get('created_at')}")
            print(f"welcome_email_sent: {user.get('welcome_email_sent', False)}")
            print(f"tokens_restantes: {user.get('tokens_restantes', 0):,}")
            print(f"current_plan: {user.get('current_plan', 'N/A')}")
            print()
            
            if not user.get('welcome_email_sent', False):
                print("⚠️ PROBLEMA: welcome_email_sent = False")
                print("   El email de bienvenida NO fue enviado")
                print()
                print("Posibles causas:")
                print("  1. El frontend NO llamó al endpoint /users/notify-registration")
                print("  2. El endpoint fue llamado pero falló el envío del email")
                print("  3. El endpoint no se registró correctamente (error de indentación)")
    
    print()
    print("=" * 60)
    print("VERIFICANDO EN AUTH.USERS")
    print("=" * 60)
    
    # Intentar buscar en auth.users (requiere admin)
    try:
        # Buscar todos los usuarios y filtrar por email
        auth_users = supabase.auth.admin.list_users()
        
        if auth_users and hasattr(auth_users, 'users'):
            daky31_found = False
            for auth_user in auth_users.users:
                if 'daky31' in (auth_user.email or '').lower():
                    daky31_found = True
                    print(f"✅ Usuario encontrado en auth.users:")
                    print(f"   Email: {auth_user.email}")
                    print(f"   ID: {auth_user.id}")
                    print(f"   Email confirmado: {auth_user.email_confirmed_at is not None}")
                    print(f"   Último login: {auth_user.last_sign_in_at}")
                    print()
            
            if not daky31_found:
                print("⚠️ Usuario NO encontrado en auth.users")
        else:
            print("⚠️ No se pudieron obtener usuarios de auth.users")
    except Exception as e:
        print(f"⚠️ Error al acceder a auth.users: {e}")
        print("   (Esto es normal si no tienes permisos de admin)")
    
    print()
    print("=" * 60)
    print("RECOMENDACIONES")
    print("=" * 60)
    print("1. Verifica los logs del backend para ver si se llamó /users/notify-registration")
    print("2. Verifica que el router de usuarios se registró correctamente al iniciar el servidor")
    print("3. Revisa la consola del navegador para ver si hay errores al llamar al endpoint")
    print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

