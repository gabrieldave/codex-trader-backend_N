"""
Script para consultar el consumo de tokens de las últimas consultas
"""
import os
import sys
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timedelta

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Error: Faltan variables de entorno SUPABASE_URL o SUPABASE_SERVICE_KEY")
    sys.exit(1)

# Crear cliente de Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

print("=" * 60)
print("CONSULTA DE TOKENS USADOS")
print("=" * 60)
print()

# Obtener el ID del usuario desde la línea de comandos o pedirlo
if len(sys.argv) > 1:
    user_id = sys.argv[1]
else:
    user_id = input("Ingresa el ID del usuario (o presiona Enter para ver todos): ").strip()

try:
    # Obtener tokens restantes actuales
    if user_id:
        profile_response = supabase.table("profiles").select("tokens_restantes, email").eq("id", user_id).execute()
        if profile_response.data:
            profile = profile_response.data[0]
            print(f"Usuario: {profile.get('email', 'N/A')}")
            print(f"ID: {user_id}")
            print(f"Tokens restantes actuales: {profile.get('tokens_restantes', 0)}")
            print()
        else:
            print(f"Usuario con ID {user_id} no encontrado")
            sys.exit(1)
    else:
        # Mostrar todos los usuarios
        profiles_response = supabase.table("profiles").select("id, email, tokens_restantes").execute()
        print("Usuarios disponibles:")
        for profile in profiles_response.data:
            print(f"  - {profile.get('email', 'N/A')} (ID: {profile.get('id')}) - Tokens: {profile.get('tokens_restantes', 0)}")
        print()
        user_id = input("Ingresa el ID del usuario para ver detalles: ").strip()
        if not user_id:
            sys.exit(0)
    
    # Nota: Los tokens se descuentan en la tabla profiles, pero no hay un historial
    # de consumo por consulta. Los logs del backend mostrarían el consumo.
    print("=" * 60)
    print("NOTA: El sistema actual no guarda un historial detallado de tokens")
    print("por consulta. Los tokens se descuentan directamente en la tabla profiles.")
    print()
    print("Para ver el consumo de tokens de consultas recientes, revisa los")
    print("logs del backend donde se imprime:")
    print("  - Tokens de entrada (input_tokens)")
    print("  - Tokens de salida (output_tokens)")
    print("  - Total de tokens usados")
    print("=" * 60)
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()















