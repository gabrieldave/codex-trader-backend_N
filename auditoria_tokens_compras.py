"""
Script de Auditoría: Tokens en Compras
Verifica que los tokens se sumen correctamente cuando se hace una compra
"""

import os
import sys
from datetime import datetime

# Configurar encoding para Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from dotenv import load_dotenv

# Función para limpiar caracteres nulos
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
print("AUDITORÍA: TOKENS EN COMPRAS")
print("="*70)
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Verificar imports
try:
    from supabase import create_client, Client
    import stripe
except ImportError as e:
    print(f"❌ Error al importar dependencias: {e}")
    sys.exit(1)

# Configurar Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip('"').strip("'").strip()
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip('"').strip("'").strip()

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Variables de entorno de Supabase no configuradas")
    sys.exit(1)

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurar Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip('"').strip("'").strip()
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

print("1. VERIFICACIÓN DE CONFIGURACIÓN")
print("-" * 70)
print(f"✅ Supabase URL: {SUPABASE_URL[:30]}...")
print(f"✅ Supabase Key: {'Configurado' if SUPABASE_KEY else '❌ NO CONFIGURADO'}")
print(f"{'✅' if STRIPE_SECRET_KEY else '❌'} Stripe Secret Key: {'Configurado' if STRIPE_SECRET_KEY else 'NO CONFIGURADO'}")
print()

# Verificar planes
print("2. VERIFICACIÓN DE PLANES")
print("-" * 70)
try:
    from plans import get_all_plans
    plans = get_all_plans()
    print(f"✅ Planes encontrados: {len(plans)}\n")
    for plan in plans:
        print(f"   - {plan.code}: {plan.name}")
        print(f"     Tokens: {plan.tokens_per_month:,}")
        print(f"     Precio: ${plan.price_usd:.2f} USD")
        print()
except Exception as e:
    print(f"⚠️ Error al obtener planes: {e}\n")

# Verificar función handle_checkout_session_completed
print("3. ANÁLISIS DEL CÓDIGO: handle_checkout_session_completed")
print("-" * 70)

issues = []
warnings = []

# Verificar lógica de tokens
print("📋 Flujo de tokens en checkout.session.completed:\n")
print("   1. Se obtiene plan_code desde metadata")
print("   2. Se obtiene tokens_per_month desde el plan")
print("   3. Se obtienen tokens_restantes actuales del usuario")
print("   4. Se suman: new_tokens = current_tokens + tokens_per_month")
print("   5. Se actualiza: update_data['tokens_restantes'] = new_tokens")
print("   6. Se ejecuta: supabase_client.table('profiles').update(update_data).eq('id', user_id).execute()")
print()

# Verificar posibles problemas
print("🔍 Posibles problemas identificados:\n")

# Problema 1: Si plan_code no está en metadata
print("   ⚠️ PROBLEMA 1: Si plan_code no está en metadata")
print("      - tokens_per_month será None")
print("      - update_data['tokens_restantes'] nunca se agrega")
print("      - Los tokens NO se actualizan")
print()

issues.append({
    "type": "CRITICAL",
    "description": "Si plan_code no está en metadata del checkout, los tokens no se suman",
    "location": "handle_checkout_session_completed línea ~3114-3161",
    "fix": "Agregar validación y logging para detectar cuando plan_code falta"
})

# Problema 2: Si tokens_per_month es None
print("   ⚠️ PROBLEMA 2: Si tokens_per_month es None")
print("      - El código tiene un fallback en línea 3160-3161")
print("      - Pero solo se ejecuta si hay un error al obtener tokens actuales")
print("      - Si plan_code existe pero plan no se encuentra, tokens_per_month es None")
print()

warnings.append({
    "type": "WARNING",
    "description": "Si el plan no se encuentra, tokens_per_month será None y no se suman tokens",
    "location": "handle_checkout_session_completed línea ~3115-3119",
    "fix": "Agregar logging cuando plan no se encuentra"
})

# Problema 3: Si update_response.data está vacío
print("   ⚠️ PROBLEMA 3: Si update_response.data está vacío")
print("      - El código verifica if update_response.data en línea 3183")
print("      - Si está vacío, solo imprime warning pero no lanza error")
print("      - Los tokens pueden no haberse actualizado")
print()

warnings.append({
    "type": "WARNING",
    "description": "Si update_response.data está vacío, no hay confirmación de que los tokens se actualizaron",
    "location": "handle_checkout_session_completed línea ~3181-3183",
    "fix": "Agregar logging más detallado y verificar que la actualización fue exitosa"
})

# Verificar usuarios recientes con compras
print("4. VERIFICACIÓN DE USUARIOS CON COMPRAS RECIENTES")
print("-" * 70)

try:
    # Buscar usuarios con stripe_customer_id (han hecho checkout)
    profiles_with_stripe = supabase_client.table("profiles").select(
        "id, email, current_plan, tokens_restantes, stripe_customer_id, created_at"
    ).not_.is_("stripe_customer_id", "null").order("created_at", desc=True).limit(10).execute()
    
    if profiles_with_stripe.data:
        print(f"✅ Usuarios con stripe_customer_id encontrados: {len(profiles_with_stripe.data)}\n")
        
        for profile in profiles_with_stripe.data:
            user_id = profile.get("id")
            email = profile.get("email", "N/A")
            plan = profile.get("current_plan", "N/A")
            tokens = profile.get("tokens_restantes", 0)
            customer_id = profile.get("stripe_customer_id", "N/A")
            
            print(f"   👤 Usuario: {email}")
            print(f"      ID: {user_id}")
            print(f"      Plan: {plan}")
            print(f"      Tokens actuales: {tokens:,}")
            print(f"      Stripe Customer: {customer_id[:20]}...")
            
            # Verificar si el plan tiene tokens esperados
            if plan and plan != "N/A":
                try:
                    from plans import get_plan_by_code
                    plan_info = get_plan_by_code(plan)
                    if plan_info:
                        expected_tokens = plan_info.tokens_per_month
                        if tokens < expected_tokens:
                            print(f"      ⚠️ ADVERTENCIA: Tokens ({tokens:,}) menores que esperados ({expected_tokens:,})")
                        else:
                            print(f"      ✅ Tokens dentro del rango esperado")
                except:
                    pass
            print()
    else:
        print("⚠️ No se encontraron usuarios con stripe_customer_id\n")
        
except Exception as e:
    print(f"❌ Error al verificar usuarios: {e}\n")

# Verificar pagos recientes
print("5. VERIFICACIÓN DE PAGOS RECIENTES")
print("-" * 70)

try:
    payments = supabase_client.table("stripe_payments").select(
        "user_id, plan_code, amount_usd, payment_date"
    ).order("payment_date", desc=True).limit(10).execute()
    
    if payments.data:
        print(f"✅ Pagos recientes encontrados: {len(payments.data)}\n")
        
        for payment in payments.data:
            user_id = payment.get("user_id")
            plan_code = payment.get("plan_code", "N/A")
            amount = payment.get("amount_usd", 0)
            date = payment.get("payment_date", "N/A")
            
            # Obtener tokens actuales del usuario
            try:
                user_profile = supabase_client.table("profiles").select(
                    "email, tokens_restantes, current_plan"
                ).eq("id", user_id).execute()
                
                if user_profile.data:
                    user_email = user_profile.data[0].get("email", "N/A")
                    user_tokens = user_profile.data[0].get("tokens_restantes", 0)
                    user_plan = user_profile.data[0].get("current_plan", "N/A")
                    
                    print(f"   💰 Pago: ${amount:.2f} USD")
                    print(f"      Usuario: {user_email}")
                    print(f"      Plan: {plan_code} (actual: {user_plan})")
                    print(f"      Tokens actuales: {user_tokens:,}")
                    print(f"      Fecha: {date}")
                    
                    # Verificar si el plan del pago coincide con el plan actual
                    if plan_code != user_plan and user_plan != "N/A":
                        print(f"      ⚠️ ADVERTENCIA: Plan del pago ({plan_code}) no coincide con plan actual ({user_plan})")
                    
                    print()
            except Exception as e:
                print(f"      ⚠️ Error al obtener perfil del usuario: {e}\n")
    else:
        print("⚠️ No se encontraron pagos en stripe_payments\n")
        
except Exception as e:
    print(f"⚠️ Error al verificar pagos (tabla puede no existir): {e}\n")

# Resumen de problemas
print("6. RESUMEN DE PROBLEMAS IDENTIFICADOS")
print("-" * 70)

if issues:
    print("\n❌ PROBLEMAS CRÍTICOS:\n")
    for i, issue in enumerate(issues, 1):
        print(f"   {i}. {issue['description']}")
        print(f"      Ubicación: {issue['location']}")
        print(f"      Solución: {issue['fix']}")
        print()

if warnings:
    print("\n⚠️ ADVERTENCIAS:\n")
    for i, warning in enumerate(warnings, 1):
        print(f"   {i}. {warning['description']}")
        print(f"      Ubicación: {warning['location']}")
        print(f"      Solución: {warning['fix']}")
        print()

if not issues and not warnings:
    print("✅ No se identificaron problemas obvios en el código\n")

# Recomendaciones
print("7. RECOMENDACIONES")
print("-" * 70)
print("""
   1. Agregar logging detallado en handle_checkout_session_completed:
      - Log cuando plan_code no está en metadata
      - Log cuando plan no se encuentra
      - Log cuando tokens_per_month es None
      - Log del valor de update_data antes de actualizar
      - Log del resultado de la actualización

   2. Agregar validación:
      - Verificar que plan_code existe antes de continuar
      - Verificar que tokens_per_month no es None antes de sumar
      - Verificar que update_response.data no está vacío

   3. Agregar métricas:
      - Contar cuántas veces falla la actualización de tokens
      - Monitorear usuarios con tokens menores a lo esperado

   4. Probar el flujo completo:
      - Crear un checkout de prueba
      - Verificar que el webhook se recibe
      - Verificar que los tokens se suman correctamente
""")

print("\n" + "="*70)
print("Auditoría completada")
print("="*70)

