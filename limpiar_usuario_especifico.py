#!/usr/bin/env python3
"""
Script para eliminar un usuario específico de auth.users y profiles.
Útil para reusar correos en pruebas.
"""
import os
import sys
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Obtener variables de entorno con limpieza
def get_env(key, default=""):
    """Obtiene variable de entorno y limpia comillas y formato."""
    value = os.getenv(key, default)
    if not value:
        return ""
    value = value.strip('"').strip("'").strip()
    if "=" in value and not value.startswith(("http://", "https://", "postgresql://", "postgres://")):
        if value.startswith("http="):
            value = value.replace("http=", "https://", 1)
        elif not value.startswith(("http://", "https://", "postgresql://", "postgres://")):
            parts = value.split("=", 1)
            if len(parts) > 1:
                value = parts[1].strip()
    if value.startswith("//"):
        value = "postgresql://" + value[2:]
    return value

def _derive_rest_url_from_db(db_url: str) -> str:
    """Deriva la URL REST de Supabase desde una URL de conexión a la base de datos."""
    from urllib.parse import urlparse
    
    if not db_url:
        raise ValueError("SUPABASE_DB_URL is empty, cannot derive REST URL")
    
    if not db_url.startswith(("postgresql://", "postgres://")):
        raise ValueError(f"SUPABASE_DB_URL debe empezar con 'postgresql://' o 'postgres://'. Recibido: {db_url[:50]}...")
    
    parsed = urlparse(db_url)
    host_parts = parsed.hostname.split('.')
    
    # Formato: postgresql://postgres.xxxxx:[password]@aws-0-us-east-1.pooler.supabase.com:5432/postgres
    # o postgresql://postgres:[password]@db.xxxxx.supabase.co:5432/postgres
    # Necesitamos extraer el project_ref de diferentes formatos
    
    if 'supabase' in parsed.hostname:
        # Intentar extraer project_ref del hostname
        if 'pooler' in parsed.hostname:
            # Formato pooler: aws-0-us-east-1.pooler.supabase.com
            # Necesitamos usar otra forma de obtener el project_ref
            # Por ahora, intentar desde la URL completa
            for part in host_parts:
                if len(part) > 10 and part not in ['pooler', 'supabase', 'com', 'aws', 'us', 'east', 'db']:
                    project_ref = part
                    break
            else:
                raise ValueError(f"No se pudo extraer project_ref del hostname: {parsed.hostname}")
        else:
            # Formato normal: db.xxxxx.supabase.co
            project_ref = host_parts[1] if len(host_parts) > 1 else None
            if not project_ref:
                raise ValueError(f"No se pudo extraer project_ref del hostname: {parsed.hostname}")
        
        rest_url = f"https://{project_ref}.supabase.co"
        return rest_url
    else:
        raise ValueError(f"Hostname no reconocido como Supabase: {parsed.hostname}")

# Obtener configuración desde variables de entorno
SUPABASE_URL = get_env('SUPABASE_URL') or get_env('SUPABASE_REST_URL')
SUPABASE_SERVICE_KEY = get_env('SUPABASE_SERVICE_KEY') or get_env('SUPABASE_SERVICE_ROLE_KEY')
SUPABASE_DB_URL = get_env('SUPABASE_DB_URL')

# Si SUPABASE_URL es una URL de DB, derivar la REST URL
if SUPABASE_URL:
    if SUPABASE_URL.startswith("postgresql://") or SUPABASE_URL.startswith("postgres://"):
        try:
            SUPABASE_URL = _derive_rest_url_from_db(SUPABASE_URL)
        except Exception as e:
            print(f"[WARNING] No se pudo derivar URL REST desde SUPABASE_URL: {e}")
            SUPABASE_URL = None

# Si no hay SUPABASE_URL pero hay SUPABASE_DB_URL, derivar desde ahí
if not SUPABASE_URL and SUPABASE_DB_URL:
    try:
        SUPABASE_URL = _derive_rest_url_from_db(SUPABASE_DB_URL)
    except Exception as e:
        print(f"[WARNING] No se pudo derivar URL REST desde SUPABASE_DB_URL: {e}")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("[ERROR] Faltan variables de entorno SUPABASE_URL (o SUPABASE_REST_URL) y SUPABASE_SERVICE_KEY (o SUPABASE_SERVICE_ROLE_KEY)")
    print(f"   SUPABASE_URL: {'Configurada' if SUPABASE_URL else 'No configurada'}")
    print(f"   SUPABASE_SERVICE_KEY: {'Configurada' if SUPABASE_SERVICE_KEY else 'No configurada'}")
    sys.exit(1)

# Crear cliente de Supabase con service role key (permisos de admin)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def eliminar_usuario(email: str, auto: bool = False):
    """
    Elimina un usuario específico de auth.users y profiles.
    
    Args:
        email: Email del usuario a eliminar
        auto: Si es True, no pide confirmación
    """
    print(f"\n{'='*60}")
    print(f"[LIMPIAR] LIMPIEZA DE USUARIO: {email}")
    print(f"{'='*60}\n")
    
    # 1. Buscar usuario en profiles
    print("1. Buscando usuario en profiles...")
    try:
        profile_response = supabase.table("profiles").select("id, email, is_admin").eq("email", email).execute()
        
        if not profile_response.data:
            print(f"   [WARNING] No se encontro usuario en profiles con email: {email}")
            profile_id = None
        else:
            profile = profile_response.data[0]
            profile_id = profile["id"]
            is_admin = profile.get("is_admin", False)
            
            if is_admin:
                print(f"   [ERROR] El usuario {email} es admin. No se puede eliminar por seguridad.")
                return False
            
            print(f"   [OK] Usuario encontrado en profiles: {profile_id}")
    except Exception as e:
        print(f"   [ERROR] Error al buscar en profiles: {e}")
        return False
    
    # 2. Buscar usuario en auth.users
    print("\n2. Buscando usuario en auth.users...")
    try:
        # Usar admin API para buscar en auth.users
        auth_response = supabase.auth.admin.list_users()
        auth_user = None
        
        for user in auth_response.users:
            if user.email == email:
                auth_user = user
                break
        
        if not auth_user:
            print(f"   [WARNING] No se encontro usuario en auth.users con email: {email}")
        else:
            print(f"   [OK] Usuario encontrado en auth.users: {auth_user.id}")
    except Exception as e:
        print(f"   [WARNING] No se pudo verificar auth.users (puede requerir permisos adicionales): {e}")
        auth_user = None
    
    # 3. Confirmar eliminación
    if not auto:
        print(f"\n[ADVERTENCIA] ¿Estas seguro de que quieres eliminar al usuario {email}?")
        print(f"   Esto eliminara TODOS sus datos de ambas tablas.")
        respuesta = input("   Escribe 'SI' para confirmar: ")
        
        if respuesta.upper() != 'SI':
            print("   [CANCELADO] Eliminacion cancelada.")
            return False
    
    # 4. Eliminar datos relacionados del usuario
    if profile_id:
        print(f"\n3. Eliminando datos relacionados del usuario {profile_id}...")
        
        try:
            # Eliminar chat_sessions
            chat_sessions_response = supabase.table("chat_sessions").delete().eq("user_id", profile_id).execute()
            print(f"   [OK] Chat sessions eliminadas: {len(chat_sessions_response.data) if chat_sessions_response.data else 0}")
        except Exception as e:
            print(f"   [WARNING] Error al eliminar chat_sessions: {e}")
        
        try:
            # Eliminar conversations
            conversations_response = supabase.table("conversations").delete().eq("user_id", profile_id).execute()
            print(f"   [OK] Conversations eliminadas: {len(conversations_response.data) if conversations_response.data else 0}")
        except Exception as e:
            print(f"   [WARNING] Error al eliminar conversations: {e}")
        
        try:
            # Eliminar model_usage_events
            model_usage_response = supabase.table("model_usage_events").delete().eq("user_id", profile_id).execute()
            print(f"   [OK] Model usage events eliminados: {len(model_usage_response.data) if model_usage_response.data else 0}")
        except Exception as e:
            print(f"   [WARNING] Error al eliminar model_usage_events: {e}")
        
        try:
            # Eliminar stripe_payments
            payments_response = supabase.table("stripe_payments").delete().eq("user_id", profile_id).execute()
            print(f"   [OK] Stripe payments eliminados: {len(payments_response.data) if payments_response.data else 0}")
        except Exception as e:
            print(f"   [WARNING] Error al eliminar stripe_payments: {e}")
        
        try:
            # Eliminar referral_reward_events
            referral_response = supabase.table("referral_reward_events").delete().eq("user_id", profile_id).execute()
            print(f"   [OK] Referral reward events eliminados: {len(referral_response.data) if referral_response.data else 0}")
        except Exception as e:
            print(f"   [WARNING] Error al eliminar referral_reward_events: {e}")
        
        # 5. Eliminar de profiles
        print(f"\n4. Eliminando de profiles...")
        try:
            supabase.table("profiles").delete().eq("id", profile_id).execute()
            print(f"   [OK] Usuario eliminado de profiles")
        except Exception as e:
            print(f"   [ERROR] Error al eliminar de profiles: {e}")
            return False
    
    # 6. Eliminar de auth.users (requiere service role key)
    if auth_user:
        print(f"\n5. Eliminando de auth.users...")
        try:
            supabase.auth.admin.delete_user(auth_user.id)
            print(f"   [OK] Usuario eliminado de auth.users")
        except Exception as e:
            print(f"   [ERROR] Error al eliminar de auth.users: {e}")
            print(f"   [WARNING] El usuario puede seguir existiendo en auth.users, pero el perfil fue eliminado.")
            print(f"   [WARNING] Puedes eliminarlo manualmente desde el dashboard de Supabase.")
            return False
    
    print(f"\n{'='*60}")
    print(f"[OK] USUARIO {email} ELIMINADO EXITOSAMENTE")
    print(f"{'='*60}\n")
    return True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Elimina un usuario específico de auth.users y profiles")
    parser.add_argument("email", help="Email del usuario a eliminar")
    parser.add_argument("--auto", action="store_true", help="Eliminar sin pedir confirmación")
    
    args = parser.parse_args()
    
    success = eliminar_usuario(args.email, auto=args.auto)
    
    if success:
        print(f"[OK] Proceso completado exitosamente.")
        print(f"[EMAIL] Ahora puedes registrar nuevamente el email {args.email}")
        sys.exit(0)
    else:
        print(f"[ERROR] Proceso fallo. Revisa los errores arriba.")
        sys.exit(1)

