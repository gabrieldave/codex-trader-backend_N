"""
Script para verificar la configuración del webhook de Stripe y diagnosticar problemas.
"""
import os
from dotenv import load_dotenv

load_dotenv()

def get_env(key: str, default: str = None) -> str:
    """Obtener variable de entorno limpiando comillas"""
    value = os.getenv(key, default)
    if value:
        return value.strip('"').strip("'").strip()
    return value

print("=" * 60)
print("VERIFICACION DE CONFIGURACION DE WEBHOOK STRIPE")
print("=" * 60)
print()

# 1. Verificar STRIPE_SECRET_KEY
stripe_secret = get_env("STRIPE_SECRET_KEY")
if stripe_secret:
    print(f"OK: STRIPE_SECRET_KEY configurada (primeros 10 chars: {stripe_secret[:10]}...)")
else:
    print("ERROR: STRIPE_SECRET_KEY no configurada")

print()

# 2. Verificar STRIPE_WEBHOOK_SECRET
webhook_secret = get_env("STRIPE_WEBHOOK_SECRET")
if webhook_secret:
    print(f"OK: STRIPE_WEBHOOK_SECRET configurada (primeros 10 chars: {webhook_secret[:10]}...)")
else:
    print("ERROR: STRIPE_WEBHOOK_SECRET no configurada")
    print("   Esta es CRITICA para verificar que los webhooks vienen de Stripe")

print()

# 3. Verificar BACKEND_URL
backend_url = get_env("BACKEND_URL") or get_env("NEXT_PUBLIC_BACKEND_URL") or "https://api.codextrader.tech"
print(f"Backend URL: {backend_url}")
webhook_url = f"{backend_url}/billing/stripe-webhook"
print(f"Webhook URL que debe configurarse en Stripe: {webhook_url}")

print()
print("=" * 60)
print("INSTRUCCIONES PARA CONFIGURAR WEBHOOK EN STRIPE")
print("=" * 60)
print()
print("1. Ve a https://dashboard.stripe.com/webhooks")
print("2. Click en 'Add endpoint' o 'Add webhook endpoint'")
print(f"3. Endpoint URL: {webhook_url}")
print("4. Selecciona los eventos a escuchar:")
print("   - checkout.session.completed")
print("   - invoice.paid")
print("5. Click en 'Add endpoint'")
print("6. Copia el 'Signing secret' (empieza con whsec_)")
print("7. Configura STRIPE_WEBHOOK_SECRET en Railway con ese valor")
print()
print("=" * 60)
print("VERIFICACION DE RESEND")
print("=" * 60)
print()

resend_key = get_env("RESEND_API_KEY")
if resend_key:
    print(f"OK: RESEND_API_KEY configurada (primeros 10 chars: {resend_key[:10]}...)")
else:
    print("ERROR: RESEND_API_KEY no configurada")
    print("   Los emails NO se enviaran sin esta clave")

print()

email_from = get_env("EMAIL_FROM")
if email_from:
    print(f"OK: EMAIL_FROM configurado: {email_from}")
else:
    print("ERROR: EMAIL_FROM no configurado")
    print("   Debe ser: Codex Trader <noreply@mail.codextrader.tech>")

print()
print("=" * 60)
print("VERIFICACION DE PLANES")
print("=" * 60)
print()

try:
    from plans import get_plan_by_code
    plan = get_plan_by_code("explorer")
    if plan:
        print(f"OK: Plan 'explorer' encontrado")
        print(f"   Nombre: {plan.name}")
        print(f"   Tokens/mes: {plan.tokens_per_month:,}")
        print(f"   Precio: ${plan.price_usd:.2f} USD")
    else:
        print("ERROR: Plan 'explorer' NO encontrado en plans.py")
except Exception as e:
    print(f"ERROR: No se pudo verificar planes: {e}")

print()
print("=" * 60)

