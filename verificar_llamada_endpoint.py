"""
Script para verificar si el endpoint /users/notify-registration fue llamado
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

def clean_env_vars():
    for key in list(os.environ.keys()):
        try:
            value = os.environ[key]
            if isinstance(value, str) and '\x00' in value:
                os.environ[key] = value.replace('\x00', '')
        except:
            pass

clean_env_vars()
try:
    load_dotenv()
    clean_env_vars()
except:
    pass

print("\n" + "="*70)
print("VERIFICACIÓN: LLAMADA AL ENDPOINT /users/notify-registration")
print("="*70)
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Verificar usuario más reciente
try:
    from supabase import create_client, Client
    
    SUPABASE_URL = "https://hozhyzdurdopkjoehqrh.supabase.co"
    
    def get_env(key):
        value = os.getenv(key, "")
        if not value:
            for env_key in os.environ.keys():
                if env_key.strip().lstrip('\ufeff') == key:
                    value = os.environ[env_key]
                    break
        return value.strip('"').strip("'").strip()
    
    SUPABASE_KEY = get_env("SUPABASE_SERVICE_KEY") or get_env("SUPABASE_SERVICE_ROLE_KEY")
    
    if not SUPABASE_KEY:
        print("❌ SUPABASE_SERVICE_KEY no configurado")
        sys.exit(1)
    
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Buscar usuario más reciente
    users = supabase_client.table("profiles").select(
        "id, email, welcome_email_sent, created_at"
    ).order("created_at", desc=True).limit(5).execute()
    
    if users.data:
        print("Usuarios más recientes:\n")
        for user in users.data:
            email = user.get("email", "N/A")
            welcome_sent = user.get("welcome_email_sent", False)
            created = user.get("created_at", "N/A")
            
            status = "✅ Email enviado" if welcome_sent else "❌ Email NO enviado"
            print(f"  👤 {email}")
            print(f"     Creado: {created}")
            print(f"     Estado: {status}")
            print()
            
            if not welcome_sent:
                print(f"  ⚠️ PROBLEMA: El email NO se envió para {email}")
                print(f"     Posibles causas:")
                print(f"     1. El frontend NO llamó al endpoint /users/notify-registration")
                print(f"     2. El endpoint fue llamado pero falló (revisar logs de Railway)")
                print(f"     3. El flag se reseteó o nunca se marcó")
                print()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("DIAGNÓSTICO")
print("="*70)
print("""
El problema más probable es que el FRONTEND no está llamando al endpoint.

Para verificar:
1. Revisa los logs de Railway del backend
2. Busca llamadas a "/users/notify-registration"
3. Si no hay llamadas, el frontend no está configurado correctamente

Para solucionar:
1. Verifica el código del frontend que maneja el registro
2. Asegúrate de que después de signUp() se llame al endpoint
3. O después de confirmar el email se llame al endpoint
""")

