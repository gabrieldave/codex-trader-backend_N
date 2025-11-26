"""
Archivo de configuración para personalizar el chatbot según el dominio/tema.

Este archivo permite reutilizar el código base para diferentes proyectos:
- Cocina
- Psicología
- Trading
- Medicina
- Cualquier otro dominio

Simplemente modifica los valores según tu proyecto.
"""

# ============================================================================
# CONFIGURACIÓN DEL DOMINIO/TEMA
# ============================================================================

# Nombre del dominio/tema de tu proyecto
DOMAIN_NAME = "trading"

# Descripción del asistente (se usa en el prompt del sistema)
ASSISTANT_DESCRIPTION = """Eres CODEX TRADER, un asistente experto en trading y psicología del trading. 
Tu objetivo es proporcionar respuestas útiles basándote en el contexto proporcionado.

INSTRUCCIONES GENERALES:
- Explica conceptos de manera clara y con ejemplos prácticos cuando sea relevante
- Si el contexto contiene información específica, úsala para enriquecer tu respuesta
- Estructura tus respuestas de manera organizada (puedes usar viñetas o párrafos)
- Si mencionas estrategias o técnicas, explica cómo aplicarlas
- Sé específico y evita respuestas genéricas o vagas
- Si el contexto no es suficiente, indica qué información adicional sería útil

IMPORTANTE: El modo de respuesta (Rápida o Estudio profundo) determinará la longitud y detalle de tu respuesta. Sigue las instrucciones del modo seleccionado.

Responde siempre en español y de manera profesional."""

# Título de la API (aparece en la documentación de FastAPI)
API_TITLE = "Chat Bot API - Trading"

# Descripción de la API
API_DESCRIPTION = "API para consultar documentos indexados sobre trading con sistema de tokens"

# Nombre de la colección de vectores en Supabase
# Puedes usar el mismo nombre para todos los proyectos o cambiarlo por dominio
VECTOR_COLLECTION_NAME = "knowledge"

# Carpeta donde están los documentos a indexar
DATA_DIRECTORY = "./data"

# ============================================================================
# CONFIGURACIÓN AVANZADA (opcional)
# ============================================================================

# Número de documentos similares a recuperar para el contexto
# Aumentado a 8 para obtener más contexto y respuestas más completas
SIMILARITY_TOP_K = 8

# Temperatura del modelo (creatividad: 0.0 = conservador, 1.0 = creativo)
MODEL_TEMPERATURE = 0.7

# Tokens iniciales para nuevos usuarios
# Recomendación: 15,000 tokens (costo: ~$0.0027 USD, permite 3 consultas rápidas o 1-2 profundas)
INITIAL_TOKENS = 15000

# ============================================================================
# MULTIPLICADORES DE TOKENS (para cobro premium)
# ============================================================================
# Estos multiplicadores se aplican al cobrar tokens al usuario para garantizar
# rentabilidad y reflejar el valor real del servicio

# Multiplicador para modo "Estudio Profundo" (1.5x = 50% extra)
# Razón: más contexto RAG (15 chunks vs 5), respuestas más elaboradas
TOKEN_MULTIPLIER_DEEP_MODE = 1.5

# Multiplicador para análisis de imágenes (2x = 100% extra)
# Razón: costo adicional de API Gemini + valor premium del servicio visual
TOKEN_MULTIPLIER_IMAGE_ANALYSIS = 2.0

# Nota: Cuando se sube una imagen, se aplican AMBOS multiplicadores
# Imagen + Estudio Profundo = 1.5 * 2.0 = 3x los tokens base

# ============================================================================
# CONFIGURACIÓN DE COSTOS DE MODELOS DE IA (USD por millón de tokens)
# ============================================================================
# Estos valores se usan para calcular el costo estimado de cada llamada
# Actualiza estos valores si cambian los precios de los proveedores

# DeepSeek Chat (precios reales actualizados)
DEEPSEEK_INPUT_COST_PER_MILLION = 0.14   # USD por millón de tokens de entrada
DEEPSEEK_OUTPUT_COST_PER_MILLION = 0.28  # USD por millón de tokens de salida

# OpenAI
OPENAI_GPT35_TURBO_INPUT_COST_PER_MILLION = 0.50   # USD por millón de tokens de entrada
OPENAI_GPT35_TURBO_OUTPUT_COST_PER_MILLION = 1.50  # USD por millón de tokens de salida
OPENAI_GPT4_INPUT_COST_PER_MILLION = 30.00         # USD por millón de tokens de entrada
OPENAI_GPT4_OUTPUT_COST_PER_MILLION = 60.00        # USD por millón de tokens de salida

# Anthropic (Claude)
ANTHROPIC_CLAUDE_HAIKU_INPUT_COST_PER_MILLION = 0.25   # USD por millón de tokens de entrada
ANTHROPIC_CLAUDE_HAIKU_OUTPUT_COST_PER_MILLION = 1.25  # USD por millón de tokens de salida
ANTHROPIC_CLAUDE_SONNET_INPUT_COST_PER_MILLION = 3.00  # USD por millón de tokens de entrada
ANTHROPIC_CLAUDE_SONNET_OUTPUT_COST_PER_MILLION = 15.00 # USD por millón de tokens de salida
ANTHROPIC_CLAUDE_OPUS_INPUT_COST_PER_MILLION = 15.00   # USD por millón de tokens de entrada
ANTHROPIC_CLAUDE_OPUS_OUTPUT_COST_PER_MILLION = 75.00  # USD por millón de tokens de salida

# Google (Gemini)
GOOGLE_GEMINI_PRO_INPUT_COST_PER_MILLION = 0.50   # USD por millón de tokens de entrada
GOOGLE_GEMINI_PRO_OUTPUT_COST_PER_MILLION = 1.50 # USD por millón de tokens de salida

# Google Gemini Flash (precios reales actualizados)
GOOGLE_GEMINI_FLASH_INPUT_COST_PER_MILLION = 0.075   # USD por millón de tokens de entrada
GOOGLE_GEMINI_FLASH_OUTPUT_COST_PER_MILLION = 0.30   # USD por millón de tokens de salida

# Cohere
COHERE_COMMAND_INPUT_COST_PER_MILLION = 1.00   # USD por millón de tokens de entrada
COHERE_COMMAND_OUTPUT_COST_PER_MILLION = 3.00  # USD por millón de tokens de salida

# Función helper para obtener costos por proveedor y modelo
def get_model_costs(provider: str, model: str) -> tuple[float, float]:
    """
    Obtiene los costos de entrada y salida para un proveedor y modelo específicos.
    
    Args:
        provider: Proveedor del modelo (ej: "deepseek", "openai", "anthropic")
        model: Nombre del modelo (ej: "deepseek-chat", "gpt-3.5-turbo")
        
    Returns:
        Tupla (costo_input, costo_output) en USD por millón de tokens
    """
    provider_lower = provider.lower()
    model_lower = model.lower()
    
    # DeepSeek
    if provider_lower == "deepseek" or "deepseek" in model_lower:
        return (DEEPSEEK_INPUT_COST_PER_MILLION, DEEPSEEK_OUTPUT_COST_PER_MILLION)
    
    # OpenAI
    elif provider_lower == "openai" or "gpt" in model_lower or "openai" in model_lower:
        if "gpt-4" in model_lower or "gpt4" in model_lower:
            return (OPENAI_GPT4_INPUT_COST_PER_MILLION, OPENAI_GPT4_OUTPUT_COST_PER_MILLION)
        else:
            return (OPENAI_GPT35_TURBO_INPUT_COST_PER_MILLION, OPENAI_GPT35_TURBO_OUTPUT_COST_PER_MILLION)
    
    # Anthropic (Claude)
    elif provider_lower == "anthropic" or "claude" in model_lower:
        if "opus" in model_lower:
            return (ANTHROPIC_CLAUDE_OPUS_INPUT_COST_PER_MILLION, ANTHROPIC_CLAUDE_OPUS_OUTPUT_COST_PER_MILLION)
        elif "sonnet" in model_lower:
            return (ANTHROPIC_CLAUDE_SONNET_INPUT_COST_PER_MILLION, ANTHROPIC_CLAUDE_SONNET_OUTPUT_COST_PER_MILLION)
        else:
            return (ANTHROPIC_CLAUDE_HAIKU_INPUT_COST_PER_MILLION, ANTHROPIC_CLAUDE_HAIKU_OUTPUT_COST_PER_MILLION)
    
    # Google (Gemini)
    elif provider_lower == "google" or "gemini" in model_lower:
        # Detectar si es Gemini Flash (más barato)
        if "flash" in model_lower:
            return (GOOGLE_GEMINI_FLASH_INPUT_COST_PER_MILLION, GOOGLE_GEMINI_FLASH_OUTPUT_COST_PER_MILLION)
        else:
            return (GOOGLE_GEMINI_PRO_INPUT_COST_PER_MILLION, GOOGLE_GEMINI_PRO_OUTPUT_COST_PER_MILLION)
    
    # Cohere
    elif provider_lower == "cohere" or "cohere" in model_lower:
        return (COHERE_COMMAND_INPUT_COST_PER_MILLION, COHERE_COMMAND_OUTPUT_COST_PER_MILLION)
    
    # Default: usar costos de DeepSeek como fallback
    else:
        print(f"⚠️ Costos no configurados para {provider}/{model}, usando costos de DeepSeek como fallback")
        return (DEEPSEEK_INPUT_COST_PER_MILLION, DEEPSEEK_OUTPUT_COST_PER_MILLION)

# ============================================================================
# EJEMPLOS DE CONFIGURACIÓN PARA OTROS DOMINIOS
# ============================================================================

# Para un proyecto de COCINA:
# DOMAIN_NAME = "cocina"
# ASSISTANT_DESCRIPTION = "Eres un asistente experto en cocina, recetas y técnicas culinarias. Responde basándote en el contexto proporcionado."
# API_TITLE = "Chat Bot API - Cocina"
# API_DESCRIPTION = "API para consultar recetas y técnicas culinarias indexadas con sistema de tokens"

# Para un proyecto de PSICOLOGÍA:
# DOMAIN_NAME = "psicologia"
# ASSISTANT_DESCRIPTION = "Eres un asistente experto en psicología y salud mental. Responde basándote en el contexto proporcionado."
# API_TITLE = "Chat Bot API - Psicología"
# API_DESCRIPTION = "API para consultar documentos sobre psicología indexados con sistema de tokens"

# Para un proyecto de MEDICINA:
# DOMAIN_NAME = "medicina"
# ASSISTANT_DESCRIPTION = "Eres un asistente experto en medicina y salud. Responde basándote en el contexto proporcionado."
# API_TITLE = "Chat Bot API - Medicina"
# API_DESCRIPTION = "API para consultar documentos médicos indexados con sistema de tokens"

