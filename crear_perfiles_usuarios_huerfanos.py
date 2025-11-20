"""Script para crear perfiles para usuarios que existen en auth.users pero no en profiles"""
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

def main():
    SUPABASE_REST_URL = get_env("SUPABASE_REST_URL") or get_env("SUPABASE_URL", "")
    SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY", "")
    
    if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
        print("❌ ERROR: Faltan variables de entorno SUPABASE_REST_URL y SUPABASE_SERVICE_KEY")
        sys.exit(1)
    
    # Obtener ADMIN_EMAILS para proteger
    ADMIN_EMAILS_ENV = get_env("ADMIN_EMAILS", "")
    ADMIN_EMAILS = []
    if ADMIN_EMAILS_ENV:
        ADMIN_EMAILS = [email.strip().lower() for email in ADMIN_EMAILS_ENV.split(",") if email.strip()]
    
    try:
        from supabase import create_client
        import requests
        from lib.business import INITIAL_FREE_TOKENS
        
        print("=" * 70)
        print("CREAR PERFILES PARA USUARIOS HUÉRFANOS")
        print("=" * 70)
        print("(Usuarios que existen en auth.users pero NO en profiles)")
        print()
        
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        # 1. Obtener todos los usuarios de auth.users
        print("[1/4] Obteniendo usuarios de auth.users...")
        try:
            auth_users_response = supabase.auth.admin.list_users()
            if not auth_users_response or not hasattr(auth_users_response, 'users'):
                print("   ❌ No se pudieron obtener usuarios de auth.users")
                print("   ℹ️  Necesitas permisos de admin en Supabase")
                print()
                print("SOLUCIÓN ALTERNATIVA:")
                print("   Ejecuta este SQL en Supabase SQL Editor:")
                print()
                print("   INSERT INTO public.profiles (id, email, tokens_restantes, current_plan, referral_code)")
                print("   SELECT id, email, 20000, 'free', 'REF-' || UPPER(SUBSTRING(id::text FROM 1 FOR 8))")
                print("   FROM auth.users")
                print("   WHERE id NOT IN (SELECT id FROM public.profiles)")
                print("     AND email NOT IN (SELECT email FROM public.profiles WHERE email IS NOT NULL);")
                print()
                sys.exit(1)
            
            auth_users = auth_users_response.users
            print(f"   ✅ Encontrados {len(auth_users)} usuario(s) en auth.users")
            print()
        except Exception as e:
            print(f"   ❌ Error al obtener usuarios de auth.users: {e}")
            print()
            print("SOLUCIÓN ALTERNATIVA:")
            print("   Ejecuta este SQL en Supabase SQL Editor:")
            print()
            print("   INSERT INTO public.profiles (id, email, tokens_restantes, current_plan, referral_code)")
            print("   SELECT id, email, 20000, 'free', 'REF-' || UPPER(SUBSTRING(id::text FROM 1 FOR 8))")
            print("   FROM auth.users")
            print("   WHERE id NOT IN (SELECT id FROM public.profiles)")
            print("     AND email NOT IN (SELECT email FROM public.profiles WHERE email IS NOT NULL);")
            print()
            sys.exit(1)
        
        # 2. Obtener todos los perfiles
        print("[2/4] Obteniendo perfiles de profiles...")
        try:
            profiles_response = supabase.table("profiles").select("id").execute()
            profiles = profiles_response.data if profiles_response.data else []
            profile_ids = {profile['id'] for profile in profiles}
            print(f"   ✅ Encontrados {len(profiles)} perfil(es) en profiles")
            print()
        except Exception as e:
            print(f"   ❌ Error al obtener perfiles: {e}")
            sys.exit(1)
        
        # 3. Identificar usuarios huérfanos
        print("[3/4] Identificando usuarios huérfanos...")
        orphaned_users = []
        
        for auth_user in auth_users:
            user_id = auth_user.id
            user_email = (auth_user.email or "").lower()
            
            # Verificar si es admin
            is_admin = False
            if ADMIN_EMAILS:
                is_admin = user_email in ADMIN_EMAILS
            
            # Verificar si tiene perfil
            if user_id not in profile_ids and not is_admin:
                orphaned_users.append({
                    'id': user_id,
                    'email': auth_user.email or "Sin email"
                })
        
        if not orphaned_users:
            print("   ✅ No hay usuarios huérfanos")
            print()
            print("Todos los usuarios tienen perfil (excepto el admin que está protegido).")
            return
        
        print(f"   ⚠️  Encontrados {len(orphaned_users)} usuario(s) huérfano(s)")
        print()
        print("Usuarios que necesitan perfil:")
        for i, user in enumerate(orphaned_users, 1):
            print(f"   {i}. {user['email']} (ID: {user['id']})")
        print()
        
        # 4. Crear perfiles para usuarios huérfanos
        print("[4/4] Creando perfiles para usuarios huérfanos...")
        
        skip_confirmations = "--auto" in sys.argv or "--yes" in sys.argv
        
        if not skip_confirmations:
            try:
                confirm = input("¿Crear perfiles para estos usuarios? (s/n): ")
                if confirm.lower() != 's':
                    print("\n❌ Operación cancelada.")
                    sys.exit(0)
            except EOFError:
                print("\n⚠️ No se puede leer input. Usa --auto para modo automático.")
                sys.exit(1)
        
        created_count = 0
        failed_count = 0
        
        for i, orphan in enumerate(orphaned_users, 1):
            user_id = orphan['id']
            user_email = orphan['email']
            
            print(f"   [{i}/{len(orphaned_users)}] Creando perfil para {user_email}...", end=" ")
            
            try:
                # Generar código de referido único (formato: REF-XXXXXXXX)
                # Usar los primeros 8 caracteres del ID del usuario (sin guiones)
                code_suffix = str(user_id).replace("-", "")[:8].upper()
                referral_code = f"REF-{code_suffix}"
                
                # Crear perfil
                profile_response = supabase.table("profiles").insert({
                    "id": user_id,
                    "email": user_email,
                    "tokens_restantes": INITIAL_FREE_TOKENS,
                    "current_plan": "free",
                    "referral_code": referral_code
                }).execute()
                
                if profile_response.data:
                    print("✅")
                    created_count += 1
                else:
                    print("❌ No se recibieron datos")
                    failed_count += 1
            except Exception as e:
                error_msg = str(e)
                # Si el error es que ya existe, está bien
                if "duplicate" in error_msg.lower() or "already exists" in error_msg.lower() or "unique" in error_msg.lower():
                    print("ℹ️ Ya existe")
                    created_count += 1  # Considerarlo como exitoso
                else:
                    print(f"❌ Error: {error_msg[:50]}")
                    failed_count += 1
        
        # Resumen
        print()
        print("=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print(f"✅ Perfiles creados: {created_count}")
        if failed_count > 0:
            print(f"❌ Perfiles con error: {failed_count}")
        print()
        print("Ahora estos usuarios pueden usar la aplicación normalmente.")
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
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
