"""
Sistema de Detección de Problemas con Emails de Bienvenida
Monitorea usuarios recientes y detecta si los emails no se están enviando
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
print("SISTEMA DE DETECCION DE PROBLEMAS: EMAILS DE BIENVENIDA")
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
    print(f"[OK] Conectado a Supabase: {SUPABASE_URL}\n")
    
except Exception as e:
    print(f"[ERROR] Error al conectar con Supabase: {e}")
    sys.exit(1)

# Configurar umbral de tiempo (usuarios creados en las últimas 2 horas)
umbral_tiempo = datetime.now(datetime.UTC).replace(tzinfo=None) - timedelta(hours=2)
umbral_str = umbral_tiempo.isoformat()

print("1. ANALISIS DE USUARIOS RECIENTES")
print("-" * 70)
print(f"Buscando usuarios creados en las ultimas 2 horas (desde {umbral_str})\n")

try:
    # Buscar usuarios recientes
    users = supabase_client.table("profiles").select(
        "id, email, welcome_email_sent, created_at"
    ).gte("created_at", umbral_str).order("created_at", desc=True).execute()
    
    # Obtener información de confirmación de email desde auth.users
    # Nota: Esto requiere permisos de service role
    user_ids = [u.get("id") for u in users.data] if users.data else []
    email_confirmed_map = {}
    if user_ids:
        try:
            # Consultar auth.users para verificar confirmación de email
            for user_id in user_ids:
                try:
                    auth_user = supabase_client.auth.admin.get_user_by_id(user_id)
                    if auth_user and auth_user.user:
                        email_confirmed_map[user_id] = bool(auth_user.user.email_confirmed_at)
                except:
                    # Si no se puede obtener, asumir que no está confirmado
                    email_confirmed_map[user_id] = False
        except:
            # Si falla, continuar sin esta información
            pass
    
    if not users.data:
        print("[INFO] No se encontraron usuarios creados en las ultimas 2 horas")
        print("       Esto es normal si no ha habido registros recientes\n")
    else:
        print(f"Usuarios encontrados: {len(users.data)}\n")
        
        problemas_encontrados = []
        usuarios_ok = []
        
        for user in users.data:
            email = user.get("email", "N/A")
            welcome_sent = user.get("welcome_email_sent", False)
            created = user.get("created_at", "N/A")
            user_id = user.get("id")
            email_confirmed = email_confirmed_map.get(user_id, None)  # None = desconocido
            
            # Calcular tiempo desde creación
            try:
                    created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    tiempo_desde_creacion = datetime.now(datetime.UTC).replace(tzinfo=None) - created_dt.replace(tzinfo=None)
                minutos = int(tiempo_desde_creacion.total_seconds() / 60)
            except:
                minutos = "N/A"
            
            if welcome_sent:
                usuarios_ok.append({
                    "email": email,
                    "created": created,
                    "minutos": minutos,
                    "email_confirmed": email_confirmed if email_confirmed is not None else "desconocido"
                })
            else:
                problemas_encontrados.append({
                    "email": email,
                    "created": created,
                    "minutos": minutos,
                    "email_confirmed": email_confirmed,
                    "id": user_id
                })
        
        # Mostrar resultados
        if usuarios_ok:
            print("[OK] Usuarios con email enviado correctamente:")
            for u in usuarios_ok:
                print(f"  - {u['email']} (creado hace {u['minutos']} min, confirmado: {u['email_confirmed']})")
            print()
        
        if problemas_encontrados:
            print("[PROBLEMA] Usuarios SIN email de bienvenida:")
            for p in problemas_encontrados:
                print(f"  - {p['email']} (creado hace {p['minutos']} min)")
                print(f"    ID: {p['id']}")
                print(f"    Email confirmado: {p['email_confirmed']}")
                print(f"    welcome_email_sent: False")
                print()
            
            print("="*70)
            print("DIAGNOSTICO AUTOMATICO")
            print("="*70)
            
            for p in problemas_encontrados:
                print(f"\nUsuario: {p['email']}")
                
                # Diagnóstico 1: ¿Confirmó el email?
                if p['email_confirmed'] is None:
                    print("  [INFO] No se pudo verificar si el usuario confirmo su email")
                    print("  [ACCION] Verificar manualmente en Supabase Dashboard")
                elif not p['email_confirmed']:
                    print("  [CAUSA PROBABLE] El usuario NO ha confirmado su email")
                    print("  [SOLUCION] El email se enviara cuando confirme el email")
                    print("  [ACCION] Esperar a que el usuario confirme su email")
                else:
                    print("  [INFO] El usuario YA confirmo su email")
                    
                    # Diagnóstico 2: ¿Tiempo suficiente?
                    if isinstance(p['minutos'], int) and p['minutos'] < 5:
                        print("  [INFO] Usuario muy reciente (menos de 5 min)")
                        print("  [ACCION] Esperar unos minutos mas, puede estar procesandose")
                    else:
                        print("  [PROBLEMA] Usuario confirmado hace mas de 5 minutos y email no enviado")
                        print("  [CAUSA PROBABLE] El frontend NO llamo al endpoint /users/notify-registration")
                        print("  [SOLUCION] Verificar:")
                        print("    1. Logs del backend en Railway para ver si llego la llamada")
                        print("    2. Logs del frontend en Vercel para ver errores")
                        print("    3. Consola del navegador del usuario para ver errores")
                        print("  [ACCION INMEDIATA] Enviar email manualmente:")
                        print(f"    python test_registro_usuario_emails.py {p['email']}")
        else:
            print("[OK] Todos los usuarios recientes tienen welcome_email_sent = True")
            print("      El sistema esta funcionando correctamente\n")
    
except Exception as e:
    print(f"[ERROR] Error al analizar usuarios: {e}")
    import traceback
    traceback.print_exc()

# Verificar configuración del backend
print("\n2. VERIFICACION DE CONFIGURACION")
print("-" * 70)

BACKEND_URL = "https://api.codextrader.tech"
print(f"Backend URL: {BACKEND_URL}")

try:
    import requests
    response = requests.get(f"{BACKEND_URL}/health", timeout=5)
    if response.status_code == 200:
        print("[OK] Backend esta respondiendo")
    else:
        print(f"[WARNING] Backend respondio con codigo {response.status_code}")
except Exception as e:
    print(f"[WARNING] No se pudo verificar el backend: {e}")
    print("   (Esto es normal si el endpoint /health no existe)")

print("\n" + "="*70)
print("RESUMEN")
print("="*70)
print("""
Este script detecta automaticamente usuarios que no recibieron el email de bienvenida.

EJECUTAR PERIODICAMENTE:
  - Cada hora para monitoreo continuo
  - Despues de cada registro para verificacion inmediata
  - Cuando se reporte un problema

ACCIONES AUTOMATICAS:
  - Identifica usuarios sin welcome_email_sent
  - Diagnostica la causa probable
  - Sugiere soluciones especificas
  - Proporciona comandos para enviar emails manualmente si es necesario
""")

print("="*70)
print("Deteccion completada")
print("="*70)

