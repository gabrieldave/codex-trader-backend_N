"""
Servicio para análisis de imágenes con Gemini 1.5 Flash.
"""
import logging
import asyncio
from typing import Optional
import google.generativeai as genai
from PIL import Image
import io

from lib.config_shared import GOOGLE_API_KEY, VISION_MODEL

logger = logging.getLogger(__name__)


def _analyze_image_sync(image_bytes: bytes) -> str:
    """
    Función síncrona interna para analizar la imagen.
    Se ejecuta en un executor para no bloquear el event loop.
    """
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY no está configurado. Configura la variable de entorno GOOGLE_API_KEY.")
    
    # Configurar el cliente de Google Generative AI
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # Crear el modelo de visión
    model = genai.GenerativeModel(VISION_MODEL)
    
    # Convertir los bytes de la imagen a un objeto PIL Image
    image = Image.open(io.BytesIO(image_bytes))
    
    # Prompt del sistema para análisis técnico de trading
    system_prompt = """Actúa como un experto analista técnico de trading institucional. Analiza esta imagen detalladamente. Identifica: 1) El activo y la temporalidad (si son visibles), 2) La tendencia principal, 3) Patrones de velas o figuras chartistas clave, 4) Niveles de soporte y resistencia visibles, 5) Lectura de indicadores (si los hay). Sé técnico, preciso y conciso."""
    
    # Generar el análisis
    response = model.generate_content([system_prompt, image])
    
    # Extraer el texto de la respuesta
    if response and response.text:
        return response.text
    else:
        logger.warning("La respuesta del modelo no contiene texto")
        return "No se pudo generar un análisis de la imagen."


async def analyze_image(image_bytes: bytes) -> str:
    """
    Analiza una imagen usando Gemini 1.5 Flash y devuelve un análisis técnico de trading.
    
    Args:
        image_bytes: Bytes de la imagen a analizar
        
    Returns:
        str: Texto del análisis técnico
        
    Raises:
        ValueError: Si GOOGLE_API_KEY no está configurado
        Exception: Si hay un error al analizar la imagen
    """
    try:
        # Ejecutar la función síncrona en un executor para no bloquear el event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _analyze_image_sync, image_bytes)
        return result
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error al analizar la imagen con Gemini: {e}")
        raise Exception(f"Error al analizar la imagen: {str(e)}")

