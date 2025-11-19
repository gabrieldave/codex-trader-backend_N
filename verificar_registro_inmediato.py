"""
Script de Verificación Inmediata: Registro de Usuario
Ejecutar inmediatamente después de un registro para verificar el estado
"""

import os
import sys
from datetime import datetime, timezone, timedelta

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
print("VERIFICACION INMEDIATA: REGISTRO DE USUARIO")
print("="*70)
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

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
        print("[ERROR] SUPABASE_SERVICE_KEY no configurado")
        sys.exit(1)
    
    supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print(f"[OK] Conectado a Supabase\n")
    
except Exception as e:
    print(f"[ERROR] Error al conectar con Supabase: {e}")
    sys.exit(1)

# Buscar el usuario más reciente (últimos 2 minutos)
print("Buscando usuario mas reciente (ultimos 2 minutos)...\n")
umbral_tiempo = datetime.now(timezone.utc).replace(tzinfo=None)
umbral_str = (umbral_tiempo - timedelta(minutes=2)).isoformat()

try:
    users = supabase_client.table("profiles").select(
        "id, email, welcome_email_sent, created_at"
    ).gte("created_at", umbral_str).order("created_at", desc=True).limit(1).execute()
    
    if users.data:
        user = users.data[0]
        email = user.get("email", "N/A")
        welcome_sent = user.get("welcome_email_sent", False)
        created = user.get("created_at", "N/A")
        user_id = user.get("id")
        
        print("="*70)
        print("USUARIO ENCONTRADO")
        print("="*70)
        print(f"Email: {email}")
        print(f"ID: {user_id}")
        print(f"Creado: {created}")
        print(f"welcome_email_sent: {welcome_sent}")
        print()
        
        if welcome_sent:
            print("[OK] Email de bienvenida ENVIADO correctamente")
            print("      El sistema esta funcionando correctamente")
        else:
            print("[PROBLEMA] Email de bienvenida NO enviado")
            print()
            print("DIAGNOSTICO:")
            print("  1. Verificando si el usuario confirmo su email...")
            
            # Verificar confirmación de email
            try:
                from mcp_supabase_execute_sql import mcp_supabase_execute_sql
                # Usar SQL directo para verificar
                auth_check = supabase_client.table("auth.users").select("email_confirmed_at").eq("id", user_id).execute()
                if auth_check.data:
                    email_confirmed = bool(auth_check.data[0].get("email_confirmed_at"))
                    if email_confirmed:
                        print("     [INFO] Usuario YA confirmo su email")
                        print("     [PROBLEMA] El frontend NO llamo al endpoint")
                        print("     [SOLUCION] Verificar logs del backend en Railway")
                        print(f"     [ACCION] Enviar email manualmente:")
                        print(f"              python test_registro_usuario_emails.py {email}")
                    else:
                        print("     [INFO] Usuario NO ha confirmado su email aun")
                        print("     [SOLUCION] El email se enviara cuando confirme")
                else:
                    print("     [WARNING] No se pudo verificar confirmacion de email")
            except Exception as e:
                print(f"     [WARNING] Error al verificar confirmacion: {e}")
                print("     [ACCION] Verificar manualmente en Supabase Dashboard")
    else:
        print("[INFO] No se encontro usuario creado en los ultimos 2 minutos")
        print("       Espera unos segundos y ejecuta de nuevo, o")
        print("       Verifica que el usuario se haya registrado correctamente")
        
except Exception as e:
    print(f"[ERROR] Error al buscar usuario: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("Verificacion completada")
print("="*70)

