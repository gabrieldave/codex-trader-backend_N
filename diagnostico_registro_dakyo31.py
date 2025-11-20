"""Script completo para diagnosticar el problema de registro de dakyo31@gmail.com"""
import os
import sys
from dotenv import load_dotenv
from datetime import datetime

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
    print("DIAGNÓSTICO COMPLETO: REGISTRO DE dakyo31@gmail.com")
    print("=" * 70)
    print()
    
    supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
    
    # 1. Buscar en profiles
    print("[1/5] Buscando en tabla 'profiles'...")
    profiles_response = supabase.table("profiles").select(
        "id, email, created_at, welcome_email_sent, tokens_restantes, current_plan, referral_code"
    ).ilike("email", "%dakyo31%").execute()
    
    if profiles_response.data:
        print(f"   ✅ Encontrados {len(profiles_response.data)} usuario(s) en profiles:")
        for user in profiles_response.data:
            print(f"      - Email: {user.get('email')}")
            print(f"        ID: {user.get('id')}")
            print(f"        Creado: {user.get('created_at')}")
            print(f"        welcome_email_sent: {user.get('welcome_email_sent', False)}")
            print(f"        tokens_restantes: {user.get('tokens_restantes', 0):,}")
            print(f"        current_plan: {user.get('current_plan', 'N/A')}")
            print()
    else:
        print("   ❌ NO encontrado en profiles")
        print()
    
    # 2. Buscar en auth.users (requiere admin)
    print("[2/5] Buscando en auth.users (requiere permisos admin)...")
    try:
        auth_users_response = supabase.auth.admin.list_users()
        
        if auth_users_response and hasattr(auth_users_response, 'users'):
            dakyo31_found = False
            for auth_user in auth_users_response.users:
                if 'dakyo31' in (auth_user.email or '').lower():
                    dakyo31_found = True
                    print(f"   ✅ Encontrado en auth.users:")
                    print(f"      - Email: {auth_user.email}")
                    print(f"        ID: {auth_user.id}")
                    print(f"        Email confirmado: {auth_user.email_confirmed_at is not None}")
                    print(f"        Último login: {auth_user.last_sign_in_at}")
                    print(f"        Creado: {auth_user.created_at}")
                    print()
                    
                    # Verificar si existe en profiles
                    profile_check = supabase.table("profiles").select("id").eq("id", auth_user.id).execute()
                    if not profile_check.data:
                        print("      ⚠️ PROBLEMA: Usuario existe en auth.users pero NO en profiles")
                        print("      Esto significa que el trigger de creación de perfil no funcionó")
                        print()
            
            if not dakyo31_found:
                print("   ❌ NO encontrado en auth.users")
                print("   Esto significa que el usuario NO se registró correctamente")
                print()
        else:
            print("   ⚠️ No se pudieron obtener usuarios de auth.users")
            print()
    except Exception as e:
        print(f"   ⚠️ Error al acceder a auth.users: {e}")
        print("   (Esto puede ser normal si no tienes permisos de admin)")
        print()
    
    # 3. Verificar usuarios recientes (últimas 24 horas)
    print("[3/5] Verificando usuarios creados en las últimas 24 horas...")
    try:
        from datetime import datetime, timedelta, timezone
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        
        recent_profiles = supabase.table("profiles").select(
            "id, email, created_at"
        ).gte("created_at", yesterday.isoformat()).order("created_at", desc=True).limit(10).execute()
        
        if recent_profiles.data:
            print(f"   ✅ Encontrados {len(recent_profiles.data)} usuario(s) reciente(s):")
            for user in recent_profiles.data:
                print(f"      - {user.get('email')} (creado: {user.get('created_at')})")
        else:
            print("   ℹ️ No hay usuarios creados en las últimas 24 horas")
        print()
    except Exception as e:
        print(f"   ⚠️ Error al verificar usuarios recientes: {e}")
        print()
    
    # 4. Verificar configuración del trigger de creación de perfiles
    print("[4/5] Verificando si existe el trigger de creación de perfiles...")
    try:
        # Intentar verificar si el trigger existe (esto requiere permisos especiales)
        # Por ahora solo mostramos un mensaje
        print("   ℹ️ Para verificar el trigger, ejecuta en Supabase SQL Editor:")
        print("      SELECT * FROM pg_trigger WHERE tgname = 'on_auth_user_created';")
        print()
    except Exception as e:
        print(f"   ⚠️ No se pudo verificar el trigger: {e}")
        print()
    
    # 5. Verificar si hay problemas con el script de limpieza
    print("[5/5] Verificando si el script de limpieza podría haber afectado...")
    try:
        # Verificar cuántos usuarios hay en total
        all_users = supabase.table("profiles").select("id, email").execute()
        total_users = len(all_users.data) if all_users.data else 0
        
        print(f"   ℹ️ Total de usuarios en profiles: {total_users}")
        
        # Verificar si hay usuarios con emails similares que fueron eliminados
        print("   ℹ️ Verificando usuarios con emails similares...")
        similar_emails = supabase.table("profiles").select("email").ilike("email", "%dakyo%").execute()
        if similar_emails.data:
            print(f"      Encontrados {len(similar_emails.data)} usuario(s) con 'dakyo' en el email:")
            for user in similar_emails.data:
                print(f"         - {user.get('email')}")
        else:
            print("      No hay usuarios con 'dakyo' en el email")
        print()
    except Exception as e:
        print(f"   ⚠️ Error al verificar: {e}")
        print()
    
    # Resumen y recomendaciones
    print("=" * 70)
    print("RESUMEN Y RECOMENDACIONES")
    print("=" * 70)
    print()
    
    if not profiles_response.data:
        print("❌ PROBLEMA PRINCIPAL: Usuario NO encontrado en profiles")
        print()
        print("Posibles causas:")
        print("  1. El usuario NO se registró correctamente en Supabase")
        print("  2. El trigger de creación de perfil no funcionó")
        print("  3. El usuario fue eliminado después del registro")
        print("  4. Hay un error en el proceso de registro del frontend")
        print()
        print("Acciones recomendadas:")
        print("  1. Verifica los logs del backend al momento del registro")
        print("  2. Revisa la consola del navegador para ver errores")
        print("  3. Verifica que el trigger 'on_auth_user_created' existe en Supabase")
        print("  4. Intenta registrar el usuario nuevamente y observa los logs")
        print()
    else:
        user = profiles_response.data[0]
        if not user.get('welcome_email_sent', False):
            print("⚠️ Usuario existe pero NO recibió email de bienvenida")
            print()
            print("Posibles causas:")
            print("  1. El frontend NO llamó al endpoint /users/notify-registration")
            print("  2. El endpoint fue llamado pero falló el envío del email")
            print("  3. El router de usuarios no se registró correctamente")
            print()
            print("Acciones recomendadas:")
            print("  1. Verifica los logs del backend para ver si se llamó /users/notify-registration")
            print("  2. Revisa que el router de usuarios se registró al iniciar el servidor")
            print("  3. Puedes reenviar el email manualmente usando reenviar_email_bienvenida.py")
            print()
        else:
            print("✅ Usuario existe y recibió email de bienvenida")
            print("   El problema puede ser que el email llegó a spam o se perdió")
            print()
    
    print("=" * 70)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

