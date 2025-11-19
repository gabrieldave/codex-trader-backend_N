"""
Configuración compartida para los routers.
Contiene variables globales que se inicializan en main.py.
"""
# Variables globales que se inicializan en main.py
# IMPORTANTE: Estas variables se inicializan en main.py usando init_shared_config()
supabase_client = None
modelo_por_defecto = None
local_embedder = None
RAG_AVAILABLE = False
STRIPE_AVAILABLE = False
FRONTEND_URL = None
BACKEND_URL = None
DEEPSEEK_API_KEY = None
OPENAI_API_KEY = None
ANTHROPIC_API_KEY = None
GOOGLE_API_KEY = None
COHERE_API_KEY = None

# Modelo de visión para análisis de imágenes
# Nombres posibles: "gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro-vision", "gemini-1.5-pro"
VISION_MODEL = "gemini-1.5-flash-latest"


def init_shared_config(
    client,
    chat_model: str = None,
    embedder=None,
    rag_available: bool = False,
    stripe_available: bool = False,
    frontend_url: str = None,
    backend_url: str = None,
    deepseek_key: str = None,
    openai_key: str = None,
    anthropic_key: str = None,
    google_key: str = None,
    cohere_key: str = None
):
    """
    Inicializa la configuración compartida.
    Debe llamarse desde main.py después de configurar todo.
    """
    global supabase_client, modelo_por_defecto, local_embedder, RAG_AVAILABLE
    global STRIPE_AVAILABLE, FRONTEND_URL, BACKEND_URL
    global DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, COHERE_API_KEY
    
    supabase_client = client
    modelo_por_defecto = chat_model
    local_embedder = embedder
    RAG_AVAILABLE = rag_available
    STRIPE_AVAILABLE = stripe_available
    FRONTEND_URL = frontend_url
    BACKEND_URL = backend_url
    DEEPSEEK_API_KEY = deepseek_key
    OPENAI_API_KEY = openai_key
    ANTHROPIC_API_KEY = anthropic_key
    GOOGLE_API_KEY = google_key
    COHERE_API_KEY = cohere_key

