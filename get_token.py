import os
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carga tus variables .env
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
# IMPORTANTE: Usa la clave 'anon', no la 'service_key'.
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Error: SUPABASE_URL o SUPABASE_ANON_KEY no están en el .env")
    exit()

# --- ⬇️ DAVID: EDITA ESTAS LÍNEAS ⬇️ ---
TEST_USER_EMAIL = "david.del.rio.colin@gmail.com"  # (Tu email de prueba)
TEST_USER_PASSWORD = "Mila1308@@"          # (Tu contraseña de prueba)
# --- ⬆️ DAVID: EDITA ESTAS LÍNEAS ⬆️ ---

try:
    # Usa la clave ANON para simular un cliente
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    logger.info(f"Intentando iniciar sesión como {TEST_USER_EMAIL}...")

    # Inicia sesión
    response = supabase.auth.sign_in_with_password({
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })

    # Imprime el token
    access_token = response.session.access_token
    print("\n\n--- ¡TOKEN OBTENIDO! ÚSALO EN TU PRUEBA --- \n")
    print(access_token)
    print("\n---------------------------------------------\n")

except Exception as e:
    logger.error(f"\nError al obtener el token: {e}")
    logger.error("Verifica que:")
    logger.error("  1. Las variables SUPABASE_URL y SUPABASE_ANON_KEY estén en tu .env")
    logger.error("  2. El email y password de prueba sean correctos.")
    logger.error("  3. El usuario haya confirmado su email si tienes la 'Confirmación de Email' activa en Supabase.")

