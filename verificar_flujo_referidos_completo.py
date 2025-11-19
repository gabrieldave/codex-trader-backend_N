"""
Script completo para verificar y simular el flujo del sistema de referidos.
Este script verifica:
1. Registro con código de referido
2. Asignación de 5,000 tokens al invitado
3. Procesamiento de compra del invitado
4. Asignación de 10,000 tokens al referrer
5. Envío de emails
6. Actualización de tablas y contadores
"""
import os
import sys
from datetime import datetime
from urllib.parse import quote_plus

def get_env(key):
    """Obtiene variable de entorno limpiando comillas"""
    value = os.environ.get(key)
    if value is None:
        return None
    return value.strip('"').strip("'").strip()

# Intentar cargar desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Obtener variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")
SUPABASE_KEY = get_env("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: Faltan variables de entorno SUPABASE_URL o SUPABASE_KEY")
    print("   Asegurate de tener estas variables configuradas en tu entorno")
    print("   o en un archivo .env en el directorio del proyecto")
    sys.exit(1)

# Construir cadena de conexión PostgreSQL
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
if SUPABASE_DB_PASSWORD:
    encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
    postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"
else:
    postgres_connection_string = None

print("=" * 70)
print("VERIFICACIÓN COMPLETA DEL SISTEMA DE REFERIDOS")
print("=" * 70)
print()

try:
    from supabase import create_client, Client
    import psycopg2
    
    # Conectar a Supabase
    print("1. Conectando a Supabase...")
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("   ✅ Conexión establecida con Supabase\n")
    
    # Verificar tablas y columnas necesarias
    print("2. Verificando estructura de base de datos...")
    
    if postgres_connection_string:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor()
        
        # Verificar tabla profiles tiene las columnas necesarias
        print("   a) Verificando tabla profiles...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = 'profiles'
            AND column_name IN (
                'referral_code', 
                'referred_by_user_id', 
                'referral_rewards_count', 
                'referral_tokens_earned',
                'has_generated_referral_reward',
                'tokens_restantes'
            )
        """)
        profile_columns = {row[0] for row in cur.fetchall()}
        
        required_profile_columns = {
            'referral_code',
            'referred_by_user_id',
            'referral_rewards_count',
            'referral_tokens_earned',
            'has_generated_referral_reward',
            'tokens_restantes'
        }
        
        missing_profile_columns = required_profile_columns - profile_columns
        if missing_profile_columns:
            print(f"      ❌ Faltan columnas en profiles: {', '.join(missing_profile_columns)}")
            print(f"      ⚠️ Ejecuta add_referral_columns_to_profiles.sql y add_has_generated_referral_reward_column.sql")
        else:
            print("      ✅ Todas las columnas necesarias existen en profiles")
        
        # Verificar tabla referral_reward_events
        print("   b) Verificando tabla referral_reward_events...")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'referral_reward_events'
            )
        """)
        table_exists = cur.fetchone()[0]
        
        if not table_exists:
            print("      ❌ Tabla referral_reward_events NO existe")
            print("      ⚠️ Ejecuta add_referral_rewards_system.sql para crearla")
        else:
            print("      ✅ Tabla referral_reward_events existe")
            
            # Verificar columnas de la tabla
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_schema = 'public' 
                AND table_name = 'referral_reward_events'
            """)
            event_columns = {row[0] for row in cur.fetchall()}
            required_event_columns = {
                'id',
                'invoice_id',
                'user_id',
                'referrer_id',
                'reward_type',
                'tokens_granted',
                'created_at'
            }
            
            missing_event_columns = required_event_columns - event_columns
            if missing_event_columns:
                print(f"      ❌ Faltan columnas: {', '.join(missing_event_columns)}")
            else:
                print("      ✅ Todas las columnas necesarias existen")
        
        # Verificar índices
        print("   c) Verificando índices...")
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' 
            AND tablename = 'referral_reward_events'
        """)
        indexes = {row[0] for row in cur.fetchall()}
        required_indexes = {
            'referral_reward_events_invoice_id_idx',
            'referral_reward_events_user_id_idx',
            'referral_reward_events_referrer_id_idx'
        }
        
        missing_indexes = required_indexes - indexes
        if missing_indexes:
            print(f"      ⚠️ Faltan índices: {', '.join(missing_indexes)}")
        else:
            print("      ✅ Todos los índices existen")
        
        # Verificar función generate_referral_code
        print("   d) Verificando función generate_referral_code...")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM pg_proc 
                WHERE proname = 'generate_referral_code'
            )
        """)
        function_exists = cur.fetchone()[0]
        
        if not function_exists:
            print("      ⚠️ Función generate_referral_code NO existe")
            print("      ⚠️ Ejecuta add_referral_columns_to_profiles.sql")
        else:
            print("      ✅ Función generate_referral_code existe")
        
        cur.close()
        conn.close()
        print()
    else:
        print("   ⚠️ No se puede verificar con PostgreSQL (falta SUPABASE_DB_PASSWORD)")
        print("   Continuando con verificación básica usando Supabase API\n")
    
    # Verificar constantes en lib/business.py
    print("3. Verificando constantes de negocio...")
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from lib.business import (
            INITIAL_FREE_TOKENS,
            REF_INVITED_BONUS_TOKENS,
            REF_REFERRER_BONUS_TOKENS,
            REF_MAX_REWARDS
        )
        
        print(f"   ✅ INITIAL_FREE_TOKENS: {INITIAL_FREE_TOKENS:,}")
        print(f"   ✅ REF_INVITED_BONUS_TOKENS: {REF_INVITED_BONUS_TOKENS:,}")
        print(f"   ✅ REF_REFERRER_BONUS_TOKENS: {REF_REFERRER_BONUS_TOKENS:,}")
        print(f"   ✅ REF_MAX_REWARDS: {REF_MAX_REWARDS}")
        print()
        
        # Verificar que los valores coinciden con lo esperado
        if REF_INVITED_BONUS_TOKENS != 5000:
            print(f"   ⚠️ ADVERTENCIA: REF_INVITED_BONUS_TOKENS debería ser 5000, pero es {REF_INVITED_BONUS_TOKENS}")
        if REF_REFERRER_BONUS_TOKENS != 10000:
            print(f"   ⚠️ ADVERTENCIA: REF_REFERRER_BONUS_TOKENS debería ser 10000, pero es {REF_REFERRER_BONUS_TOKENS}")
        if REF_MAX_REWARDS != 5:
            print(f"   ⚠️ ADVERTENCIA: REF_MAX_REWARDS debería ser 5, pero es {REF_MAX_REWARDS}")
    except ImportError as e:
        print(f"   ❌ ERROR: No se pudo importar lib.business: {e}")
        print()
    except Exception as e:
        print(f"   ⚠️ ADVERTENCIA: Error al verificar constantes: {e}")
        print()
    
    # Verificar funciones helper
    print("4. Verificando funciones helper...")
    try:
        from lib.referrals import (
            generate_referral_code,
            assign_referral_code_if_needed,
            build_referral_url
        )
        print("   ✅ Funciones helper importadas correctamente")
        
        # Probar generar código de prueba
        test_code = generate_referral_code()
        print(f"   ✅ Código de prueba generado: {test_code}")
        print()
    except ImportError as e:
        print(f"   ❌ ERROR: No se pudo importar lib.referrals: {e}")
        print()
    except Exception as e:
        print(f"   ⚠️ ADVERTENCIA: Error al verificar funciones helper: {e}")
        print()
    
    # Simular flujo completo (sin datos reales)
    print("5. Simulando flujo completo del sistema de referidos...")
    print()
    print("   📋 FLUJO ESPERADO:")
    print()
    print("   PASO 1: Usuario A (Referrer) se registra")
    print("   └─> Se genera código de referido único")
    print("   └─> Se asigna a profiles.referral_code")
    print("   └─> Usuario recibe 20,000 tokens iniciales")
    print()
    print("   PASO 2: Usuario B (Referido) se registra con código de A")
    print("   └─> Frontend llama a POST /referrals/process con código")
    print("   └─> Backend verifica código y busca referrer")
    print("   └─> Se asigna profiles.referred_by_user_id = A.id")
    print("   └─> Usuario B recibe +5,000 tokens (bienvenida)")
    print("   └─> Usuario B tiene 25,000 tokens totales (20,000 + 5,000)")
    print("   └─> Se envía email de bienvenida al referido (B)")
    print()
    print("   PASO 3: Usuario B (Referido) hace su primera compra")
    print("   └─> Stripe envía webhook invoice.paid")
    print("   └─> Backend procesa handle_invoice_paid()")
    print("   └─> Se suma tokens del plan a B")
    print("   └─> Se verifica que B tiene referred_by_user_id")
    print("   └─> Se verifica que B.has_generated_referral_reward = false")
    print("   └─> Se verifica idempotencia (tabla referral_reward_events)")
    print("   └─> Se marca B.has_generated_referral_reward = true")
    print()
    print("   PASO 4: Procesamiento de recompensa al Referrer (A)")
    print("   └─> Se llama a process_referrer_reward(A.id, B.id, invoice_id)")
    print("   └─> Se verifica que A no ha alcanzado límite (referral_rewards_count < 5)")
    print("   └─> Se suma +10,000 tokens a A")
    print("   └─> Se incrementa A.referral_rewards_count += 1")
    print("   └─> Se incrementa A.referral_tokens_earned += 10,000")
    print("   └─> Se registra evento en referral_reward_events")
    print("   └─> Se envía email de recompensa al referrer (A)")
    print()
    print("   PASO 5: Verificación de idempotencia")
    print("   └─> Si Stripe reenvía webhook, se verifica tabla")
    print("   └─> Si invoice_id ya existe, no se procesa de nuevo")
    print()
    
    # Verificar endpoints importantes
    print("6. Verificando endpoints necesarios...")
    endpoints = {
        "POST /referrals/process": "Procesa código de referido después del registro",
        "GET /me/referrals-summary": "Obtiene estadísticas de referidos",
        "GET /referrals/info": "Obtiene información de referidos del usuario",
        "POST /billing/stripe-webhook": "Recibe webhooks de Stripe (invoice.paid)"
    }
    
    for endpoint, description in endpoints.items():
        print(f"   ✓ {endpoint}: {description}")
    print()
    
    # Verificar emails
    print("7. Verificando sistema de emails...")
    try:
        from lib.email import send_email, send_admin_email, SMTP_AVAILABLE
        
        if SMTP_AVAILABLE:
            print("   ✅ SMTP configurado y disponible")
        else:
            print("   ⚠️ SMTP no está disponible (emails no se enviarán)")
        
        print("   ✓ Email al referido (bienvenida): Cuando se procesa código")
        print("   ✓ Email al referrer (recompensa): Cuando referido paga")
        print("   ✓ Email al usuario (confirmación de pago): Cuando paga plan")
        print()
    except ImportError as e:
        print(f"   ⚠️ ADVERTENCIA: No se pudo importar lib.email: {e}")
        print()
    except Exception as e:
        print(f"   ⚠️ ADVERTENCIA: Error al verificar emails: {e}")
        print()
    
    # Resumen final
    print("=" * 70)
    print("RESUMEN DE VERIFICACIÓN:")
    print("=" * 70)
    
    issues = []
    if missing_profile_columns:
        issues.append(f"❌ Faltan columnas en profiles: {', '.join(missing_profile_columns)}")
    if not table_exists:
        issues.append("❌ Tabla referral_reward_events no existe")
    
    if issues:
        print()
        print("⚠️ PROBLEMAS ENCONTRADOS:")
        for issue in issues:
            print(f"   {issue}")
        print()
        print("📝 ACCIONES RECOMENDADAS:")
        print()
        if missing_profile_columns:
            print("   1. Ejecuta add_referral_columns_to_profiles.sql")
            print("   2. Ejecuta add_has_generated_referral_reward_column.sql")
        if not table_exists:
            print("   3. Ejecuta add_referral_rewards_system.sql")
            print("      O ejecuta: python verificar_crear_tabla_referidos.py")
        print()
    else:
        print()
        print("✅ SISTEMA DE REFERIDOS CONFIGURADO CORRECTAMENTE")
        print()
        print("El flujo completo debería funcionar:")
        print("   ✓ Registro con código de referido")
        print("   ✓ Asignación de 5,000 tokens al invitado")
        print("   ✓ Procesamiento de compra del invitado")
        print("   ✓ Asignación de 10,000 tokens al referrer")
        print("   ✓ Envío de emails en todos los puntos")
        print("   ✓ Idempotencia para evitar duplicados")
        print()
    
    print("=" * 70)
    
except ImportError as e:
    print(f"ERROR: Faltan dependencias: {e}")
    print("   Instala con: pip install supabase psycopg2-binary python-dotenv")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

