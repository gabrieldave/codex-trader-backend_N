"""
Script de ejemplo para eliminar o desactivar un usuario del sistema.

Uso:
    python eliminar_usuario_ejemplo.py <user_id> [--deactivate]

Ejemplos:
    # Eliminar usuario completamente
    python eliminar_usuario_ejemplo.py 123e4567-e89b-12d3-a456-426614174000
    
    # Solo desactivar usuario (establecer tokens a 0)
    python eliminar_usuario_ejemplo.py 123e4567-e89b-12d3-a456-426614174000 --deactivate
"""
import sys
import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Obtener variables de entorno
SUPABASE_REST_URL = os.getenv("SUPABASE_REST_URL") or os.getenv("SUPABASE_URL", "").strip('"').strip("'").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip('"').strip("'").strip()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip('"').strip("'").strip()

# URL del backend (ajustar según tu configuración)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").strip('"').strip("'").strip()

def get_admin_token():
    """
    Obtiene un token de admin autenticándose con el email de admin.
    En producción, deberías usar un token permanente o un método más seguro.
    """
    # Nota: Esto requiere que tengas un endpoint de login o uses un token permanente
    # Por ahora, asumimos que tienes un token de admin
    admin_token = os.getenv("ADMIN_TOKEN", "")
    if not admin_token:
        print("⚠️ ADMIN_TOKEN no configurado. Necesitas un token de admin para usar este script.")
        print("   Obtén un token autenticándote como admin en tu aplicación.")
        sys.exit(1)
    return admin_token

def delete_user(user_id: str):
    """Elimina un usuario completamente del sistema."""
    admin_token = get_admin_token()
    
    url = f"{BACKEND_URL}/admin/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    print(f"🗑️  Eliminando usuario {user_id}...")
    response = requests.delete(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ {result.get('message', 'Usuario eliminado exitosamente')}")
        return True
    else:
        print(f"❌ Error al eliminar usuario: {response.status_code}")
        print(f"   {response.text}")
        return False

def deactivate_user(user_id: str):
    """Desactiva un usuario (establece tokens a 0)."""
    admin_token = get_admin_token()
    
    url = f"{BACKEND_URL}/admin/users/{user_id}/deactivate"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    print(f"🚫 Desactivando usuario {user_id}...")
    response = requests.post(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ {result.get('message', 'Usuario desactivado exitosamente')}")
        return True
    else:
        print(f"❌ Error al desactivar usuario: {response.status_code}")
        print(f"   {response.text}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python eliminar_usuario_ejemplo.py <user_id> [--deactivate]")
        print("\nEjemplos:")
        print("  # Eliminar usuario completamente")
        print("  python eliminar_usuario_ejemplo.py 123e4567-e89b-12d3-a456-426614174000")
        print("\n  # Solo desactivar usuario")
        print("  python eliminar_usuario_ejemplo.py 123e4567-e89b-12d3-a456-426614174000 --deactivate")
        sys.exit(1)
    
    user_id = sys.argv[1]
    deactivate_only = "--deactivate" in sys.argv
    
    if deactivate_only:
        success = deactivate_user(user_id)
    else:
        print("⚠️  ADVERTENCIA: Esta acción eliminará el usuario completamente del sistema.")
        print("   Esta acción es IRREVERSIBLE.")
        confirm = input("¿Estás seguro? Escribe 'ELIMINAR' para confirmar: ")
        
        if confirm == "ELIMINAR":
            success = delete_user(user_id)
        else:
            print("❌ Operación cancelada.")
            sys.exit(1)
    
    sys.exit(0 if success else 1)

