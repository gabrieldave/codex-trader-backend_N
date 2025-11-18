"""
Módulo de configuración y utilidades para Stripe.
Configura el cliente de Stripe y proporciona funciones auxiliares.
"""
import os
from typing import Dict, Optional

# Intentar importar stripe
# IMPORTANTE: Importar directamente desde el paquete oficial de PyPI
# Este módulo se llama lib.stripe, pero necesitamos importar el paquete 'stripe' de PyPI
# Para evitar conflictos, verificamos el __file__ del módulo importado
try:
    import sys
    import importlib.util
    
    # Guardar referencia temporal si existe
    old_stripe = None
    if 'stripe' in sys.modules:
        old_module = sys.modules['stripe']
        # Si es este mismo módulo (lib/stripe.py), eliminarlo
        if hasattr(old_module, '__file__') and old_module.__file__ and 'lib/stripe.py' in old_module.__file__:
            old_stripe = sys.modules.pop('stripe', None)
    
    # Importar el paquete oficial de stripe desde PyPI usando import absoluto
    # Usar __import__ para forzar importación del paquete de PyPI, no del módulo local
    try:
        import pkg_resources
        # Verificar que el paquete stripe esté instalado
        try:
            stripe_dist = pkg_resources.get_distribution('stripe')
            stripe_version_from_pkg = stripe_dist.version
        except:
            stripe_version_from_pkg = None
        
        # Importar usando __import__ con fromlist para asegurar que es el paquete, no el módulo
        stripe_package = __import__('stripe', fromlist=['__version__'])
        stripe = stripe_package
        
        # Verificar que stripe sea el paquete oficial (tiene __version__ y checkout)
        if hasattr(stripe, '__version__') and hasattr(stripe, 'checkout') and hasattr(stripe, 'error'):
            STRIPE_IMPORTED = True
            stripe_version = getattr(stripe, '__version__', stripe_version_from_pkg or 'unknown')
            print(f"✅ Stripe importado correctamente - Versión: {stripe_version}")
        else:
            STRIPE_IMPORTED = False
            has_version = hasattr(stripe, '__version__')
            has_checkout = hasattr(stripe, 'checkout')
            stripe = None
            print(f"⚠️ WARNING: El módulo stripe importado no parece ser el paquete oficial (tiene __version__: {has_version}, tiene checkout: {has_checkout})")
    except (ImportError, Exception):
        # Si __import__ falla, intentar con importlib
        import importlib
        stripe = importlib.import_module('stripe')
        if hasattr(stripe, '__version__') and hasattr(stripe, 'checkout') and hasattr(stripe, 'error'):
            STRIPE_IMPORTED = True
            stripe_version = getattr(stripe, '__version__', 'unknown')
            print(f"✅ Stripe importado correctamente - Versión: {stripe_version}")
        else:
            STRIPE_IMPORTED = False
            stripe = None
            print("⚠️ WARNING: El módulo stripe importado no parece ser el paquete oficial")
except ImportError as e:
    STRIPE_IMPORTED = False
    stripe = None
    error_msg = str(e) if e else 'Unknown error'
    print(f"⚠️ WARNING: No se pudo importar stripe: {error_msg}")
except Exception as e:
    STRIPE_IMPORTED = False
    stripe = None
    error_msg = str(e) if e else 'Unknown error'
    print(f"⚠️ WARNING: Error al importar stripe: {error_msg}")

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

