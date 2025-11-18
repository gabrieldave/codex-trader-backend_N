"""
Módulo para registrar y calcular costos de uso de modelos de IA.
Proporciona funciones para registrar cada llamada a modelos y calcular costos estimados.
"""
import os
from typing import Optional
from supabase import create_client
import config

# Obtener variables de entorno de Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip('"').strip("'").strip()
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip('"').strip("'").strip()

# Inicializar cliente de Supabase si está disponible
supabase_client = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as e:
        print(f"⚠️ No se pudo inicializar cliente de Supabase para model_usage: {e}")


def extract_provider_from_model(model: str) -> str:
    """
    Extrae el nombre del proveedor desde el nombre del modelo.
    
    Args:
        model: Nombre del modelo (ej: "deepseek/deepseek-chat", "gpt-3.5-turbo")
        
    Returns:
        Nombre del proveedor (ej: "deepseek", "openai", "anthropic")
    """
    model_lower = model.lower()
    
    if "deepseek" in model_lower:
        return "deepseek"
    elif "gpt" in model_lower or "openai" in model_lower:
        return "openai"
    elif "claude" in model_lower or "anthropic" in model_lower:
        return "anthropic"
    elif "gemini" in model_lower or "google" in model_lower:
        return "google"
    elif "cohere" in model_lower:
        return "cohere"
    else:
        # Si no se puede determinar, usar el primer segmento del modelo
        parts = model.split("/")
        return parts[0] if len(parts) > 1 else "unknown"


def calculate_cost_usd(
    provider: str,
    model: str,
    tokens_input: int,
    tokens_output: int
) -> float:
    """
    Calcula el costo estimado en USD para una llamada al modelo.
    
    Args:
        provider: Proveedor del modelo (ej: "deepseek", "openai")
        model: Nombre del modelo (ej: "deepseek-chat", "gpt-3.5-turbo")
        tokens_input: Cantidad de tokens de entrada
        tokens_output: Cantidad de tokens de salida
        
    Returns:
        Costo estimado en USD
    """
    try:
        cost_input_per_million, cost_output_per_million = config.get_model_costs(provider, model)
        
        cost_input = (tokens_input / 1_000_000) * cost_input_per_million
        cost_output = (tokens_output / 1_000_000) * cost_output_per_million
        
        total_cost = cost_input + cost_output
        
        return round(total_cost, 6)  # Redondear a 6 decimales
    except Exception as e:
        print(f"⚠️ Error al calcular costo para {provider}/{model}: {e}")
        return 0.0


def log_model_usage(
    user_id: Optional[str],
    provider: str,
    model: str,
    tokens_input: int,
    tokens_output: int
) -> bool:
    """
    Registra el uso de un modelo de IA en la base de datos.
    
    Esta función es robusta y no lanza excepciones para no bloquear el flujo principal.
    Si falla, solo registra el error en los logs.
    
    Args:
        user_id: ID del usuario (puede ser None si no está asociado a un usuario)
        provider: Proveedor del modelo (ej: "deepseek", "openai")
        model: Nombre del modelo (ej: "deepseek-chat", "gpt-3.5-turbo")
        tokens_input: Cantidad de tokens de entrada
        tokens_output: Cantidad de tokens de salida
        
    Returns:
        True si se registró correctamente, False en caso contrario
    """
    if not supabase_client:
        print("⚠️ Cliente de Supabase no disponible para registrar uso de modelo")
        return False
    
    try:
        # Calcular costo estimado
        cost_estimated_usd = calculate_cost_usd(provider, model, tokens_input, tokens_output)
        
        # Preparar datos para insertar
        usage_data = {
            "user_id": user_id,
            "provider": provider,
            "model": model,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "cost_estimated_usd": cost_estimated_usd
        }
        
        # Insertar en la base de datos
        result = supabase_client.table("model_usage_events").insert(usage_data).execute()
        
        if result.data:
            print(f"✅ Uso de modelo registrado: {provider}/{model} - ${cost_estimated_usd:.6f} USD")
            return True
        else:
            print(f"⚠️ No se pudo registrar uso de modelo: {provider}/{model}")
            return False
            
    except Exception as e:
        # No lanzar excepción, solo registrar el error
        print(f"⚠️ Error al registrar uso de modelo (no crítico): {e}")
        return False


def log_model_usage_from_response(
    user_id: Optional[str],
    model: str,
    tokens_input: int,
    tokens_output: int
) -> bool:
    """
    Versión simplificada que extrae el proveedor automáticamente desde el nombre del modelo.
    
    Args:
        user_id: ID del usuario (puede ser None)
        model: Nombre completo del modelo (ej: "deepseek/deepseek-chat")
        tokens_input: Cantidad de tokens de entrada
        tokens_output: Cantidad de tokens de salida
        
    Returns:
        True si se registró correctamente, False en caso contrario
    """
    provider = extract_provider_from_model(model)
    return log_model_usage(user_id, provider, model, tokens_input, tokens_output)

