"""
Módulo de configuración y utilidades para Stripe.
Configura el cliente de Stripe y proporciona funciones auxiliares.
"""
import os
from typing import Dict, Optional

# Intentar importar stripe
# IMPORTANTE: Importar directamente desde el paquete oficial de PyPI
# Usar import absoluto para evitar conflictos con este módulo (lib.stripe)
try:
    import importlib
    import sys
    
    # Si stripe ya está en sys.modules, verificar que sea el correcto
    if 'stripe' in sys.modules:
        existing_stripe = sys.modules['stripe']
        # Si es este mismo módulo (lib.stripe), eliminarlo y reinstalar
        if hasattr(existing_stripe, '__file__') and 'lib/stripe.py' in existing_stripe.__file__:
            del sys.modules['stripe']
    
    # Importar el paquete oficial de stripe desde PyPI
    stripe = importlib.import_module('stripe')
    
    # Verificar que stripe sea el módulo correcto (tiene __version__ y checkout)
    if hasattr(stripe, '__version__') and hasattr(stripe, 'checkout') and hasattr(stripe, 'error'):
        STRIPE_IMPORTED = True
        # Log de la versión para debugging
        stripe_version = getattr(stripe, '__version__', 'unknown')
        print(f"✅ Stripe importado correctamente - Versión: {stripe_version}")
    else:
        STRIPE_IMPORTED = False
        has_version = hasattr(stripe, '__version__') if stripe else False
        has_checkout = hasattr(stripe, 'checkout') if stripe else False
        stripe = None
        print(f"⚠️ WARNING: El módulo stripe importado no parece ser el paquete oficial (tiene __version__: {has_version}, tiene checkout: {has_checkout})")
except ImportError as e:
    STRIPE_IMPORTED = False
    stripe = None
    print(f"⚠️ WARNING: No se pudo importar stripe: {e}")
except Exception as e:
    STRIPE_IMPORTED = False
    stripe = None
    print(f"⚠️ WARNING: Error al importar stripe: {e}")

# Obtener la secret key de Stripe desde variables de entorno
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip('"').strip("'").strip()

# Configurar el cliente de Stripe solo si está disponible
if STRIPE_SECRET_KEY and STRIPE_IMPORTED:
    stripe.api_key = STRIPE_SECRET_KEY
elif not STRIPE_SECRET_KEY:
    # No lanzar error, solo advertir (para permitir que el backend funcione sin Stripe)
    print("WARNING: STRIPE_SECRET_KEY no esta configurada. Las funciones de Stripe no estaran disponibles.")

# Obtener Webhook Secret desde variables de entorno
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip('"').strip("'").strip()

# Obtener Cupón de Uso Justo desde variables de entorno
STRIPE_FAIR_USE_COUPON_ID = os.getenv("STRIPE_FAIR_USE_COUPON_ID", "").strip('"').strip("'").strip()

# Obtener Price IDs desde variables de entorno
STRIPE_PRICE_IDS: Dict[str, str] = {
    "explorer": os.getenv("STRIPE_PRICE_ID_EXPLORER", "").strip('"').strip("'").strip(),
    "trader": os.getenv("STRIPE_PRICE_ID_TRADER", "").strip('"').strip("'").strip(),
    "pro": os.getenv("STRIPE_PRICE_ID_PRO", "").strip('"').strip("'").strip(),
    "institucional": os.getenv("STRIPE_PRICE_ID_INSTITUCIONAL", "").strip('"').strip("'").strip(),
}

# Mapa inverso: Price ID -> Plan Code (para identificar el plan desde una invoice)
def get_plan_code_from_price_id(price_id: str) -> Optional[str]:
    """
    Obtiene el código de plan desde un Price ID de Stripe.
    
    Args:
        price_id: Price ID de Stripe
        
    Returns:
        El código de plan o None si no se encuentra
    """
    for plan_code, stripe_price_id in STRIPE_PRICE_IDS.items():
        if stripe_price_id == price_id:
            return plan_code
    return None

# Validar que todos los Price IDs estén configurados
for plan_code, price_id in STRIPE_PRICE_IDS.items():
    if not price_id:
        print(f"WARNING: STRIPE_PRICE_ID_{plan_code.upper()} no esta configurado")


def get_stripe_price_id(plan_code: str) -> Optional[str]:
    """
    Obtiene el Price ID de Stripe para un plan dado.
    
    Args:
        plan_code: Código del plan ('explorer', 'trader', 'pro', 'institucional')
        
    Returns:
        El Price ID de Stripe o None si no existe
    """
    return STRIPE_PRICE_IDS.get(plan_code.lower())


def is_valid_plan_code(plan_code: str) -> bool:
    """
    Valida si un código de plan es válido.
    
    Args:
        plan_code: Código del plan a validar
        
    Returns:
        True si el código es válido, False en caso contrario
    """
    return plan_code.lower() in STRIPE_PRICE_IDS.keys()

