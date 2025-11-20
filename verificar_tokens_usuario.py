"""Script para verificar tokens de un usuario específico"""
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
    print("VERIFICACIÓN DE TOKENS PARA dakyo31@gmail.com")
    print("=" * 70)
    print()
    
    supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
    
    # Buscar usuario por email
    email = "dakyo31@gmail.com"
    print(f"[1/3] Buscando usuario: {email}")
    
    try:
        # Buscar en profiles
        profiles_response = supabase.table("profiles").select(
            "id, email, tokens_restantes, current_plan, referral_code, created_at"
        ).eq("email", email).execute()
        
        if not profiles_response.data:
            print(f"   ❌ Usuario NO encontrado en profiles")
            print()
            print("Posibles causas:")
            print("  1. El email está escrito diferente")
            print("  2. El usuario no tiene perfil")
            print()
            
            # Buscar emails similares
            similar_response = supabase.table("profiles").select("email").ilike("email", "%dakyo31%").execute()
            if similar_response.data:
                print("Emails similares encontrados:")
                for user in similar_response.data:
                    print(f"   - {user.get('email')}")
            sys.exit(1)
        
        print(f"   ✅ Encontrado(s) {len(profiles_response.data)} usuario(s):")
        print()
        
        for i, profile in enumerate(profiles_response.data, 1):
            print(f"Usuario {i}:")
            print(f"   Email: {profile.get('email')}")
            print(f"   ID: {profile.get('id')}")
            print(f"   Tokens restantes: {profile.get('tokens_restantes', 0):,}")
            print(f"   Plan actual: {profile.get('current_plan', 'N/A')}")
            print(f"   Código referido: {profile.get('referral_code', 'N/A')}")
            print(f"   Creado: {profile.get('created_at', 'N/A')}")
            print()
        
        # Verificar si hay múltiples usuarios con el mismo email
        if len(profiles_response.data) > 1:
            print("⚠️ PROBLEMA: Hay múltiples usuarios con el mismo email")
            print("   Esto puede causar problemas. Se recomienda eliminar duplicados.")
            print()
        
        # Verificar el usuario específico que aparece en los logs
        user_id_log = "6adaf460-eebc-41cc-a061-861fc5daf4ec"
        print(f"[2/3] Verificando usuario de los logs (ID: {user_id_log})...")
        
        log_user_response = supabase.table("profiles").select(
            "id, email, tokens_restantes, current_plan"
        ).eq("id", user_id_log).execute()
        
        if log_user_response.data:
            log_user = log_user_response.data[0]
            print(f"   ✅ Usuario encontrado:")
            print(f"      Email: {log_user.get('email')}")
            print(f"      ID: {log_user.get('id')}")
            print(f"      Tokens restantes: {log_user.get('tokens_restantes', 0):,}")
            print(f"      Plan: {log_user.get('current_plan', 'N/A')}")
            print()
            
            if log_user.get('email') != email:
                print(f"   ⚠️ El usuario de los logs tiene email diferente:")
                print(f"      Buscado: {email}")
                print(f"      Encontrado: {log_user.get('email')}")
                print()
        else:
            print(f"   ❌ Usuario de los logs NO encontrado en profiles")
            print()
        
        # Verificar usuarios en auth.users
        print("[3/3] Verificando usuarios en auth.users...")
        try:
            auth_users_response = supabase.auth.admin.list_users()
            if auth_users_response and hasattr(auth_users_response, 'users'):
                # Buscar por email
                matching_auth_users = []
                for auth_user in auth_users_response.users:
                    if 'dakyo31' in (auth_user.email or '').lower():
                        matching_auth_users.append({
                            'id': auth_user.id,
                            'email': auth_user.email,
                            'created_at': auth_user.created_at
                        })
                
                if matching_auth_users:
                    print(f"   ✅ Encontrados {len(matching_auth_users)} usuario(s) en auth.users:")
                    for auth_user in matching_auth_users:
                        print(f"      - {auth_user['email']} (ID: {auth_user['id']})")
                        
                        # Verificar si tiene perfil
                        profile_check = supabase.table("profiles").select("id").eq("id", auth_user['id']).execute()
                        if profile_check.data:
                            print(f"        ✅ Tiene perfil")
                        else:
                            print(f"        ❌ NO tiene perfil (huérfano)")
                    print()
                else:
                    print("   ℹ️ No hay usuarios con 'dakyo31' en auth.users")
            else:
                print("   ⚠️ No se pudieron obtener usuarios de auth.users")
        except Exception as e:
            print(f"   ⚠️ Error al verificar auth.users: {e}")
        
        print("=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print()
        print("Si el endpoint /tokens devuelve 20000 pero no se ve en el frontend:")
        print("  1. Verifica la consola del navegador para errores")
        print("  2. Verifica que el usuario esté correctamente autenticado")
        print("  3. Verifica que el frontend esté mostrando la respuesta correctamente")
        print()
        
    except Exception as e:
        print(f"❌ Error al buscar usuario: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

