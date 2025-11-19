"""
Script para verificar qué usuarios hay en la base de datos.

Uso:
    python verificar_usuarios.py
"""
import os
import sys
from dotenv import load_dotenv

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

# Obtener variables de entorno con limpieza
def get_env(key, default=""):
    """Obtiene variable de entorno y limpia comillas."""
    value = os.getenv(key, default)
    if not value:
        return default
    value = value.strip('"').strip("'").strip()
    # Corregir formato incorrecto https= a https://
    if value.startswith("https="):
        value = value.replace("https=", "https://", 1)
    # Corregir doble barra
    if value.startswith("https:////"):
        value = value.replace("https:////", "https://", 1)
    return value

# Obtener variables de Supabase directamente
SUPABASE_REST_URL = get_env("SUPABASE_REST_URL") or get_env("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY", "")

ADMIN_EMAIL = "david.del.rio.colin@gmail.com"

def get_all_users():
    """Obtiene todos los usuarios de la base de datos."""
    try:
        from supabase import create_client
        
        print(f"[DEBUG] Variables de entorno:")
        print(f"   SUPABASE_REST_URL: {'Configurado' if SUPABASE_REST_URL else 'NO CONFIGURADO'}")
        if SUPABASE_REST_URL:
            print(f"   URL: {SUPABASE_REST_URL[:50]}...")
        print(f"   SUPABASE_SERVICE_KEY: {'Configurado' if SUPABASE_SERVICE_KEY else 'NO CONFIGURADO'}")
        print()
        
        if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
            print("[ERROR] SUPABASE_REST_URL y SUPABASE_SERVICE_KEY deben estar configurados")
            return None
        
        print(f"[i] Conectando a Supabase...")
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        # Obtener todos los perfiles
        profiles_response = supabase.table("profiles").select("id, email, created_at, tokens_restantes").execute()
        
        if not profiles_response.data:
            return []
        
        return profiles_response.data
    except Exception as e:
        print(f"[ERROR] Error al obtener usuarios: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("=" * 60)
    print("VERIFICACION DE USUARIOS")
    print("=" * 60)
    print()
    
    users = get_all_users()
    
    if users is None:
        print("[ERROR] No se pudo conectar a la base de datos")
        sys.exit(1)
    
    if not users:
        print("[i] No hay usuarios en la base de datos")
        sys.exit(0)
    
    print(f"[OK] Se encontraron {len(users)} usuarios")
    print()
    print("=" * 60)
    print("LISTA DE USUARIOS")
    print("=" * 60)
    print()
    
    admin_count = 0
    regular_count = 0
    
    for i, user in enumerate(users, 1):
        user_email = user.get("email", "Sin email")
        user_id = user.get("id", "N/A")
        tokens = user.get("tokens_restantes", 0)
        created = user.get("created_at", "N/A")
        
        is_admin = user_email.lower() == ADMIN_EMAIL.lower()
        
        if is_admin:
            admin_count += 1
            print(f"[ADMIN] {i}. {user_email}")
        else:
            regular_count += 1
            print(f"        {i}. {user_email}")
        
        print(f"           ID: {user_id}")
        print(f"           Tokens: {tokens:,}")
        print(f"           Creado: {created}")
        print()
    
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Total de usuarios: {len(users)}")
    print(f"  - Admin: {admin_count}")
    print(f"  - Regulares: {regular_count}")
    print()
    
    if regular_count > 0:
        print(f"[i] Hay {regular_count} usuario(s) que se pueden eliminar")
        print(f"    (excluyendo al admin: {ADMIN_EMAIL})")
    else:
        print("[i] Solo esta el admin, no hay usuarios para eliminar")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[X] Operacion cancelada por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
