"""Script para eliminar usuarios huérfanos (existen en auth.users pero no en profiles)"""
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

# Obtener admin email para proteger
ADMIN_EMAILS_ENV = get_env("ADMIN_EMAILS", "")
ADMIN_EMAILS = []
if ADMIN_EMAILS_ENV:
    ADMIN_EMAILS = [email.strip().lower() for email in ADMIN_EMAILS_ENV.split(",") if email.strip()]

if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
    print("❌ ERROR: Faltan variables de entorno SUPABASE_REST_URL y SUPABASE_SERVICE_KEY")
    sys.exit(1)

def main():
    print("=" * 70)
    print("ELIMINAR USUARIOS HUÉRFANOS")
    print("=" * 70)
    print("(Usuarios que existen en auth.users pero NO en profiles)")
    print()
    
    # Verificar modo automático
    skip_confirmations = "--auto" in sys.argv or "--yes" in sys.argv
    
    if not skip_confirmations:
        print("⚠️ ADVERTENCIA: Este script eliminará usuarios de auth.users")
        print("   que no tienen perfil en profiles.")
        print()
        print("Esto permitirá que estos usuarios se registren nuevamente.")
        print()
        try:
            confirm = input("¿Continuar? (s/n): ")
            if confirm.lower() != 's':
                print("\n❌ Operación cancelada.")
                sys.exit(0)
        except EOFError:
            print("\n⚠️ No se puede leer input. Usa --auto para modo automático.")
            sys.exit(1)
    
    try:
        from supabase import create_client
        import requests
        
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        # 1. Obtener usuarios de auth.users
        print("\n[1/3] Obteniendo usuarios de auth.users...")
        try:
            auth_users_response = supabase.auth.admin.list_users()
            if not auth_users_response or not hasattr(auth_users_response, 'users'):
                print("   ❌ No se pudieron obtener usuarios de auth.users")
                sys.exit(1)
            auth_users = auth_users_response.users
            print(f"   ✅ Encontrados {len(auth_users)} usuario(s)")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            sys.exit(1)
        
        # 2. Obtener perfiles
        print("[2/3] Obteniendo perfiles de profiles...")
        try:
            profiles_response = supabase.table("profiles").select("id").execute()
            profiles = profiles_response.data if profiles_response.data else []
            profile_ids = {profile['id'] for profile in profiles}
            print(f"   ✅ Encontrados {len(profiles)} perfil(es)")
        except Exception as e:
            print(f"   ❌ Error: {e}")
            sys.exit(1)
        
        # 3. Identificar usuarios huérfanos (excluyendo admin)
        print("[3/3] Identificando usuarios huérfanos (excluyendo admin)...")
        orphaned_users = []
        
        for auth_user in auth_users:
            user_id = auth_user.id
            user_email = (auth_user.email or "").lower()
            
            # Verificar si es admin
            is_admin = user_email in ADMIN_EMAILS
            if is_admin:
                print(f"   ⏭️  Saltando admin: {auth_user.email}")
                continue
            
            # Verificar si tiene perfil
            if user_id not in profile_ids:
                orphaned_users.append({
                    'id': user_id,
                    'email': auth_user.email or "Sin email"
                })
        
        if not orphaned_users:
            print("   ✅ No hay usuarios huérfanos para eliminar")
            print()
            print("Todos los usuarios tienen perfil (excepto el admin que está protegido).")
            return
        
        print(f"   ⚠️  Encontrados {len(orphaned_users)} usuario(s) huérfano(s) para eliminar")
        print()
        print("Usuarios que se eliminarán:")
        for i, user in enumerate(orphaned_users, 1):
            print(f"   {i}. {user['email']} (ID: {user['id']})")
        print()
        
        if not skip_confirmations:
            try:
                final_confirm = input("¿Eliminar estos usuarios? (s/n): ")
                if final_confirm.lower() != 's':
                    print("\n❌ Operación cancelada.")
                    sys.exit(0)
            except EOFError:
                print("\n⚠️ No se puede leer input. Cancelando...")
                sys.exit(1)
        
        # 4. Eliminar usuarios huérfanos
        print("\n" + "=" * 70)
        print("ELIMINANDO USUARIOS HUÉRFANOS")
        print("=" * 70)
        print()
        
        deleted_count = 0
        failed_count = 0
        
        for i, user in enumerate(orphaned_users, 1):
            user_id = user['id']
            user_email = user['email']
            
            print(f"[{i}/{len(orphaned_users)}] Eliminando {user_email}...", end=" ")
            
            try:
                # Intentar eliminar usando Admin API
                admin_api_url = f"{SUPABASE_REST_URL}/auth/v1/admin/users/{user_id}"
                headers = {
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Content-Type": "application/json"
                }
                response = requests.delete(admin_api_url, headers=headers, timeout=10)
                
                if response.status_code in [200, 204]:
                    print("✅")
                    deleted_count += 1
                else:
                    print(f"❌ Error {response.status_code}")
                    if response.text:
                        print(f"      {response.text[:100]}")
                    failed_count += 1
            except Exception as e:
                print(f"❌ Error: {str(e)[:50]}")
                failed_count += 1
        
        # Resumen
        print()
        print("=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print(f"✅ Usuarios eliminados: {deleted_count}")
        if failed_count > 0:
            print(f"❌ Usuarios con error: {failed_count}")
        print()
        print("Ahora estos usuarios pueden registrarse nuevamente con el mismo email.")
        print()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

