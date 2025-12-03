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


def _get_available_models():
    """
    Obtiene la lista de modelos disponibles de Gemini.
    """
    try:
        models = genai.list_models()
        available_models = []
        for model in models:
            # Filtrar solo modelos que soporten generateContent
            if 'generateContent' in model.supported_generation_methods:
                available_models.append(model.name.replace('models/', ''))
        return available_models
    except Exception as e:
        logger.warning(f"Error al listar modelos: {e}")
        return []


def _analyze_image_sync(image_bytes: bytes) -> str:
    """
    Función síncrona interna para analizar la imagen.
    Se ejecuta en un executor para no bloquear el event loop.
    """
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY no está configurado. Configura la variable de entorno GOOGLE_API_KEY.")
    
    # Configurar el cliente de Google Generative AI
    genai.configure(api_key=GOOGLE_API_KEY)
    
    # IMPORTANTE: PRIMERO listar modelos disponibles, luego usar los que realmente existen
    # Orden de fallback basado en COSTO (más barato primero)
    # Gemini Flash: $0.075/$0.30 (más barato)
    # Gemini Pro: $0.50/$1.50 (más caro)
    
    model = None
    model_name_used = None
    last_error = None
    models_tried = []
    
    # PRIMERO: Obtener lista de modelos disponibles
    logger.info("Obteniendo lista de modelos disponibles de Gemini...")
    available_models = _get_available_models()
    
    if available_models:
        logger.info(f"Modelos disponibles: {', '.join(available_models[:5])}...")
        
        # Construir lista de modelos a intentar en orden de costo (más barato primero)
        models_to_try = []
        
        # 1. Primero intentar el modelo configurado si está disponible
        if VISION_MODEL in available_models:
            models_to_try.append(VISION_MODEL)
            logger.info(f"✅ Modelo configurado disponible: {VISION_MODEL}")
        
        # 2. Luego agregar todos los modelos Flash disponibles (más baratos)
        flash_models = [m for m in available_models if 'flash' in m.lower()]
        # Ordenar Flash por versión (2.5, 2.0, 1.5) - más reciente primero suele ser más barato
        flash_models.sort(key=lambda x: (
            '2.5' in x, '2.0' in x, '1.5' in x,
            x.count('-'),  # Menos guiones = más simple = usualmente más barato
        ), reverse=True)
        for flash_model in flash_models:
            if flash_model not in models_to_try:
                models_to_try.append(flash_model)
        
        # 3. Finalmente agregar modelos Pro disponibles (más caros, solo como último recurso)
        pro_models = [m for m in available_models if 'pro' in m.lower() and 'flash' not in m.lower()]
        for pro_model in pro_models:
            if pro_model not in models_to_try:
                models_to_try.append(pro_model)
        
        # Intentar cada modelo en orden de costo (más barato primero)
        for model_name in models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                model_name_used = model_name
                if model_name == VISION_MODEL:
                    logger.info(f"✅ Usando modelo configurado: {model_name} (más barato)")
                else:
                    logger.info(f"⚠️ Usando modelo disponible (por costo): {model_name}")
                break
            except Exception as e:
                last_error = e
                models_tried.append(model_name)
                logger.warning(f"Modelo {model_name} no disponible: {e}")
                continue
    else:
        # Si no podemos listar modelos, intentar modelos conocidos como fallback
        logger.warning("No se pudieron listar modelos, usando lista por defecto")
        fallback_models = [
            "gemini-2.5-flash",  # Modelo que estaba funcionando
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            VISION_MODEL,
            "gemini-1.5-pro",
            "gemini-pro-vision",
            "gemini-pro"
        ]
        
        for model_name in fallback_models:
            try:
                model = genai.GenerativeModel(model_name)
                model_name_used = model_name
                logger.info(f"✅ Modelo {model_name} inicializado correctamente")
                break
            except Exception as e:
                last_error = e
                models_tried.append(model_name)
                logger.warning(f"Modelo {model_name} no disponible: {e}")
                continue
    
    if model is None:
        error_msg = (
            f"No se pudo inicializar ningún modelo de Gemini. Último error: {last_error}. "
            f"Modelo configurado: {VISION_MODEL}. "
            f"Modelos intentados: {', '.join(models_tried[:5])}. "
        )
        try:
            available_models = _get_available_models()
            if available_models:
                error_msg += f"Modelos disponibles en tu cuenta: {', '.join(available_models[:10])}. "
        except:
            pass
        error_msg += "Verifica que GOOGLE_API_KEY sea válida y que tengas acceso a los modelos de Gemini."
        raise ValueError(error_msg)
    
    # Convertir los bytes de la imagen a un objeto PIL Image
    image = Image.open(io.BytesIO(image_bytes))
    
    # Prompt del sistema para análisis técnico de trading
    system_prompt = """Actúa como un experto analista técnico de trading institucional. Analiza esta imagen detalladamente. Identifica: 1) El activo y la temporalidad (si son visibles), 2) La tendencia principal, 3) Patrones de velas o figuras chartistas clave, 4) Niveles de soporte y resistencia visibles, 5) Lectura de indicadores (si los hay). Sé técnico, preciso y conciso."""
    
    # Generar el análisis - si falla, intentar con otros modelos disponibles
    response = None
    last_error = None
    
    if model:
        try:
            response = model.generate_content([system_prompt, image])
        except Exception as e:
            last_error = e
            logger.warning(f"Error al generar contenido con modelo {model_name_used}: {e}")
            # Intentar con otros modelos disponibles como último recurso
            # Buscar otros modelos Flash disponibles que no hayamos usado
            if available_models and model_name_used:
                alternative_flash = [m for m in available_models if 'flash' in m.lower() and m != model_name_used]
                alternative_flash.sort(key=lambda x: ('2.5' in x, '2.0' in x, '1.5' in x), reverse=True)
                
                for alt_model_name in alternative_flash:
                    try:
                        logger.info(f"⚠️ Intentando modelo Flash alternativo: {alt_model_name}")
                        alt_model = genai.GenerativeModel(alt_model_name)
                        response = alt_model.generate_content([system_prompt, image])
                        logger.info(f"✅ Modelo alternativo {alt_model_name} funcionó correctamente")
                        break
                    except Exception as alt_error:
                        logger.warning(f"Modelo alternativo {alt_model_name} también falló: {alt_error}")
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

