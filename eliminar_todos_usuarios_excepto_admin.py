"""
Script para eliminar todos los usuarios excepto el administrador.

ADVERTENCIA: Este script eliminara TODOS los usuarios excepto el admin.
Esta accion es IRREVERSIBLE.

Uso:
    python eliminar_todos_usuarios_excepto_admin.py
"""
import os
import sys
from dotenv import load_dotenv

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Intentar importar requests, si no está disponible usar método alternativo
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("[!] requests no esta instalado. Usando metodo alternativo con Supabase client.")

load_dotenv()

# Configuración
ADMIN_EMAIL = "david.del.rio.colin@gmail.com"

# Obtener variables de entorno con limpieza
def get_env(key, default=""):
    """Obtiene variable de entorno y limpia comillas y formato."""
    value = os.getenv(key, default)
    if not value:
        return ""
    value = value.strip('"').strip("'").strip()
    # Si tiene formato "KEY=VALUE", extraer solo el valor
    if "=" in value:
        # Si empieza con http=, corregir a https://
        if value.startswith("http="):
            value = value.replace("http=", "https://", 1)
        elif not value.startswith("http"):
            value = value.split("=", 1)[1].strip()
    return value

SUPABASE_REST_URL = get_env("SUPABASE_REST_URL") or get_env("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY", "")
BACKEND_URL = get_env("BACKEND_URL", "http://localhost:8000")

# Debug: mostrar configuración (sin mostrar keys completas)
if SUPABASE_REST_URL:
    print(f"[DEBUG] SUPABASE_REST_URL: {SUPABASE_REST_URL[:30]}...")
else:
    print("[DEBUG] SUPABASE_REST_URL: NO CONFIGURADO")

def get_all_users():
    """Obtiene todos los usuarios de la base de datos."""
    try:
        from supabase import create_client
        
        if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
            print("[ERROR] SUPABASE_REST_URL y SUPABASE_SERVICE_KEY deben estar configurados")
            print(f"   SUPABASE_REST_URL: {'Configurado' if SUPABASE_REST_URL else 'NO CONFIGURADO'}")
            print(f"   SUPABASE_SERVICE_KEY: {'Configurado' if SUPABASE_SERVICE_KEY else 'NO CONFIGURADO'}")
            sys.exit(1)
        
        print(f"[i] Conectando a Supabase: {SUPABASE_REST_URL[:50]}...")
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        # Obtener todos los perfiles
        profiles_response = supabase.table("profiles").select("id, email").execute()
        
        if not profiles_response.data:
            print("ℹ️  No se encontraron usuarios en la base de datos")
            return []
        
        return profiles_response.data
    except Exception as e:
        print(f"❌ Error al obtener usuarios: {e}")
        sys.exit(1)

def delete_user_via_api(user_id: str, user_email: str):
    """Elimina un usuario usando el endpoint de admin."""
    if not REQUESTS_AVAILABLE:
        return delete_user_direct(user_id, user_email)
    
    admin_token = os.getenv("ADMIN_TOKEN", "")
    
    if not admin_token:
        print("⚠️  ADMIN_TOKEN no configurado. Intentando usar método directo...")
        return delete_user_direct(user_id, user_email)
    
    try:
        url = f"{BACKEND_URL}/admin/users/{user_id}"
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }
        
        response = requests.delete(url, headers=headers, timeout=30)
        
        if response.status_code in [200, 204]:
            return True
        else:
            print(f"   ⚠️  Error {response.status_code}: {response.text[:100]}")
            return delete_user_direct(user_id, user_email)
    except Exception as e:
        print(f"   ⚠️  Error al usar API: {e}")
        return delete_user_direct(user_id, user_email)

def delete_user_direct(user_id: str, user_email: str):
    """Elimina un usuario directamente usando Supabase."""
    try:
        from supabase import create_client
        
        if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
            print("   [ERROR] SUPABASE_REST_URL y SUPABASE_SERVICE_KEY deben estar configurados")
            return False
        
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        # Método 1: Intentar usar función RPC si existe
        try:
            result = supabase.rpc('delete_user_by_id', {'user_id_to_delete': user_id}).execute()
            return True
        except Exception as rpc_error:
            # Método 2: Si RPC no existe, usar Admin API REST
            if REQUESTS_AVAILABLE:
                try:
                    admin_api_url = f"{SUPABASE_REST_URL}/auth/v1/admin/users/{user_id}"
                    headers = {
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Content-Type": "application/json"
                    }
                    
                    response = requests.delete(admin_api_url, headers=headers, timeout=10)
                    
                    if response.status_code in [200, 204]:
                        return True
                    else:
                        print(f"   ⚠️  Error {response.status_code}: {response.text[:100]}")
                        return False
                except Exception as api_error:
                    print(f"   ⚠️  Error con Admin API: {api_error}")
            
            # Método 3: Eliminar directamente desde SQL (último recurso)
            # Nota: Esto requiere que la función delete_user_by_id exista
            print(f"   [!] No se pudo eliminar usando metodos automaticos")
            print(f"   [i] Ejecuta delete_user_function.sql en Supabase y vuelve a intentar")
            return False
            
    except Exception as e:
        print(f"   [ERROR] Error al eliminar usuario: {e}")
        return False

def main(skip_confirmations=False):
    print("=" * 60)
    print("ELIMINACION MASIVA DE USUARIOS")
    print("=" * 60)
    print(f"Admin protegido: {ADMIN_EMAIL}")
    print()
    
    # Confirmación
    if not skip_confirmations:
        print("[!] ADVERTENCIA: Este script eliminara TODOS los usuarios excepto el admin.")
        print("   Esta accion es IRREVERSIBLE.")
        print()
        try:
            confirm = input("Estas seguro? Escribe 'ELIMINAR TODOS' para confirmar: ")
            if confirm != "ELIMINAR TODOS":
                print("[X] Operacion cancelada.")
                sys.exit(0)
        except EOFError:
            print("[!] No se puede leer input. Usando modo automatico...")
            skip_confirmations = True
    
    print()
    print("Obteniendo lista de usuarios...")
    users = get_all_users()
    
    if not users:
        print("[i] No hay usuarios para eliminar.")
        sys.exit(0)
    
    print(f"[OK] Se encontraron {len(users)} usuarios")
    print()
    
    # Identificar admin
    admin_user = None
    users_to_delete = []
    
    for user in users:
        user_email = user.get("email", "").lower()
        if user_email == ADMIN_EMAIL.lower():
            admin_user = user
            print(f"[OK] Admin encontrado: {user_email} (ID: {user.get('id')})")
        else:
            users_to_delete.append(user)
    
    if not admin_user:
        print(f"[!] ADVERTENCIA: No se encontro el usuario admin ({ADMIN_EMAIL})")
        print("   Deseas continuar de todas formas?")
        continue_anyway = input("   Escribe 'SI' para continuar: ")
        if continue_anyway != "SI":
            print("[X] Operacion cancelada.")
            sys.exit(0)
    
    print()
    print(f"Resumen:")
    print(f"   - Total de usuarios: {len(users)}")
    print(f"   - Admin (protegido): 1")
    print(f"   - Usuarios a eliminar: {len(users_to_delete)}")
    print()
    
    if not users_to_delete:
        print("[i] No hay usuarios para eliminar (solo esta el admin).")
        sys.exit(0)
    
    # Mostrar lista de usuarios a eliminar
    print("Usuarios que se eliminaran:")
    for i, user in enumerate(users_to_delete, 1):
        print(f"   {i}. {user.get('email', 'Sin email')} (ID: {user.get('id')})")
    print()
    
    # Confirmación final
    if not skip_confirmations:
        try:
            final_confirm = input("Proceder con la eliminacion? (s/n): ")
            if final_confirm.lower() != 's':
                print("[X] Operacion cancelada.")
                sys.exit(0)
        except EOFError:
            print("[!] No se puede leer input. Continuando automaticamente...")
    
    print()
    print("Eliminando usuarios...")
    print()
    
    deleted_count = 0
    failed_count = 0
    
    for i, user in enumerate(users_to_delete, 1):
        user_id = user.get("id")
        user_email = user.get("email", "Sin email")
        
        print(f"[{i}/{len(users_to_delete)}] Eliminando {user_email}...", end=" ")
        
        if delete_user_via_api(user_id, user_email) or delete_user_direct(user_id, user_email):
            print("[OK]")
            deleted_count += 1
        else:
            print("[ERROR]")
            failed_count += 1
    
    print()
    print("=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print(f"[OK] Usuarios eliminados: {deleted_count}")
    if failed_count > 0:
        print(f"[ERROR] Usuarios con error: {failed_count}")
    print(f"Admin protegido: {ADMIN_EMAIL}")
    print()
    
    # Verificar usuarios restantes
    print("Verificando usuarios restantes...")
    remaining_users = get_all_users()
    print(f"[OK] Usuarios restantes: {len(remaining_users)}")
    
    if remaining_users:
        print("Usuarios que quedan:")
        for user in remaining_users:
            print(f"   - {user.get('email', 'Sin email')} (ID: {user.get('id')})")
    
    print()
    print("[OK] Proceso completado!")

if __name__ == "__main__":
    # Verificar si se pasa --auto para saltar confirmaciones
    skip_confirmations = "--auto" in sys.argv or "--yes" in sys.argv
    
    try:
        main(skip_confirmations=skip_confirmations)
    except KeyboardInterrupt:
        print("\n\n[X] Operacion cancelada por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

