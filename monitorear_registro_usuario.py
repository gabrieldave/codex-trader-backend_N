"""
Script de Monitoreo: Registro de Usuario
Verifica en tiempo real el estado del registro y envío de emails
"""

import os
import sys
import time
from datetime import datetime

# Configurar encoding para Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("\n" + "="*70)
print("MONITOREO: REGISTRO DE USUARIO")
print("="*70)
print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
print("⚠️ Este script monitoreará la base de datos cada 5 segundos")
print("   Presiona Ctrl+C para detener\n")

# Configurar Supabase
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
    print(f"✅ Conectado a Supabase: {SUPABASE_URL}\n")
    
except Exception as e:
    print(f"❌ Error al conectar con Supabase: {e}")
    sys.exit(1)

# Obtener email a monitorear
test_email = None
if len(sys.argv) > 1:
    test_email = sys.argv[1].strip()
else:
    try:
        test_email = input("Ingresa el email del usuario a monitorear (o Enter para monitorear todos los nuevos): ").strip()
    except (EOFError, KeyboardInterrupt):
        test_email = None

print("\n" + "="*70)
print("MONITOREANDO...")
print("="*70)
print("Presiona Ctrl+C para detener\n")

# Obtener timestamp de inicio para detectar usuarios nuevos
start_time = datetime.utcnow().isoformat()

try:
    iteration = 0
    while True:
        iteration += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        
        try:
            if test_email:
                # Monitorear usuario específico
                user_response = supabase_client.table("profiles").select(
                    "id, email, welcome_email_sent, tokens_reload_email_sent, tokens_restantes, current_plan, created_at"
                ).eq("email", test_email).execute()
                
                if user_response.data:
                    user = user_response.data[0]
                    print(f"[{current_time}] Usuario: {user['email']}")
                    print(f"  ID: {user['id']}")
                    print(f"  welcome_email_sent: {user.get('welcome_email_sent', False)}")
                    print(f"  tokens_reload_email_sent: {user.get('tokens_reload_email_sent', False)}")
                    print(f"  tokens_restantes: {user.get('tokens_restantes', 0):,}")
                    print(f"  current_plan: {user.get('current_plan', 'N/A')}")
                    print(f"  created_at: {user.get('created_at', 'N/A')}")
                    
                    if user.get('welcome_email_sent'):
                        print("  ✅ Email de bienvenida enviado")
                    else:
                        print("  ⏳ Esperando envío de email de bienvenida...")
                    print()
                else:
                    print(f"[{current_time}] ⏳ Usuario no encontrado aún...")
                    print()
            else:
                # Monitorear usuarios nuevos (creados después del inicio)
                users_response = supabase_client.table("profiles").select(
                    "id, email, welcome_email_sent, tokens_reload_email_sent, tokens_restantes, current_plan, created_at"
                ).gte("created_at", start_time).order("created_at", desc=True).limit(10).execute()
                
                if users_response.data:
                    print(f"[{current_time}] Usuarios nuevos encontrados: {len(users_response.data)}\n")
                    for user in users_response.data:
                        print(f"  👤 {user['email']}")
                        print(f"     ID: {user['id']}")
                        print(f"     welcome_email_sent: {user.get('welcome_email_sent', False)}")
                        print(f"     tokens_restantes: {user.get('tokens_restantes', 0):,}")
                        print(f"     current_plan: {user.get('current_plan', 'N/A')}")
                        
                        if user.get('welcome_email_sent'):
                            print("     ✅ Email de bienvenida enviado")
                        else:
                            print("     ⏳ Esperando envío de email de bienvenida...")
                        print()
                else:
                    if iteration == 1:
                        print(f"[{current_time}] ⏳ Esperando registro de nuevo usuario...")
                        print("   (Monitoreando usuarios creados después de ahora)")
                    print()
        
        except Exception as e:
            print(f"[{current_time}] ❌ Error: {e}\n")
        
        # Esperar 5 segundos antes de la siguiente verificación
        time.sleep(5)
        
except KeyboardInterrupt:
    print("\n\n" + "="*70)
    print("Monitoreo detenido por el usuario")
    print("="*70)
    print(f"Fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

