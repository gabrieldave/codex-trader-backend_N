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
    
    # Intentar con diferentes nombres de modelo si el primero falla
    model_names = [
        VISION_MODEL,  # Intentar primero con el configurado
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro-vision",
        "gemini-pro"
    ]
    
    model = None
    last_error = None
    
    for model_name in model_names:
        try:
            model = genai.GenerativeModel(model_name)
            # Hacer una prueba rápida para verificar que el modelo funciona
            logger.info(f"Intentando usar modelo: {model_name}")
            break
        except Exception as e:
            last_error = e
            logger.warning(f"Modelo {model_name} no disponible: {e}")
            continue
    
    if model is None:
        raise ValueError(
            f"No se pudo inicializar ningún modelo de Gemini. Último error: {last_error}. "
            f"Modelos intentados: {', '.join(model_names)}. "
            "Verifica que GOOGLE_API_KEY sea válida y que tengas acceso a los modelos de Gemini."
        )
    
    # Convertir los bytes de la imagen a un objeto PIL Image
    image = Image.open(io.BytesIO(image_bytes))
    
    # Prompt del sistema para análisis técnico de trading
    system_prompt = """Actúa como un experto analista técnico de trading institucional. Analiza esta imagen detalladamente. Identifica: 1) El activo y la temporalidad (si son visibles), 2) La tendencia principal, 3) Patrones de velas o figuras chartistas clave, 4) Niveles de soporte y resistencia visibles, 5) Lectura de indicadores (si los hay). Sé técnico, preciso y conciso."""
    
    # Generar el análisis - si falla, intentar con otros modelos
    response = None
    last_error = None
    
    if model:
        try:
            response = model.generate_content([system_prompt, image])
        except Exception as e:
            last_error = e
            logger.warning(f"Error con modelo {VISION_MODEL}: {e}")
            # Intentar con modelos alternativos
            alternative_models = [
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-pro-vision",
                "gemini-pro"
            ]
            
            for alt_model_name in alternative_models:
                if alt_model_name == VISION_MODEL:
                    continue  # Ya lo intentamos
                try:
                    logger.info(f"Intentando modelo alternativo: {alt_model_name}")
                    alt_model = genai.GenerativeModel(alt_model_name)
                    response = alt_model.generate_content([system_prompt, image])
                    logger.info(f"✅ Modelo {alt_model_name} funcionó correctamente")
                    break
                except Exception as alt_error:
                    logger.warning(f"Modelo {alt_model_name} también falló: {alt_error}")
                    last_error = alt_error
                    continue
    
    if response is None:
        raise Exception(
            f"No se pudo generar contenido con ningún modelo de Gemini. "
            f"Último error: {last_error}. "
            "Verifica que GOOGLE_API_KEY sea válida y que tengas acceso a los modelos de visión de Gemini."
        )
    
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

