import os
import sys
import re
import zipfile
import io
import shutil
import asyncio
from urllib.parse import quote_plus
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

# Agregar el directorio actual al path de Python para que pueda encontrar módulos locales
# Esto es necesario en Railway donde el path puede ser diferente
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Asegurar que el directorio lib esté en el path
lib_dir = os.path.join(current_dir, "lib")
if os.path.exists(lib_dir) and lib_dir not in sys.path:
    sys.path.insert(0, lib_dir)

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
# from llama_index.core import VectorStoreIndex
# from llama_index.embeddings.openai import OpenAIEmbedding
# from llama_index.vector_stores.supabase import SupabaseVectorStore
from supabase import create_client
import litellm
from sentence_transformers import SentenceTransformer
import uvicorn
from typing import Optional, List, Dict
import config
from sqlalchemy import create_engine, text

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Configurar logging a archivo
import logging
from datetime import datetime
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backend.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno de forma robusta desde .env
# - Busca primero en el CWD (por si uvicorn se lanza desde otra carpeta)
# - Si no lo encuentra, intenta al lado de este archivo main.py
# - No sobreescribe valores ya presentes en el entorno
_env_file = find_dotenv(filename=".env", usecwd=True)
if not _env_file:
    candidate = Path(__file__).parent / ".env"
    if candidate.exists():
        _env_file = str(candidate)
if _env_file:
    load_dotenv(dotenv_path=_env_file, override=False)

# Si existe un archivo .env.runtime, cargarlo con prioridad
_runtime_env = find_dotenv(filename=".env.runtime", usecwd=True)
if not _runtime_env:
    candidate_runtime = Path(__file__).parent / ".env.runtime"
    if candidate_runtime.exists():
        _runtime_env = str(candidate_runtime)
if _runtime_env:
    load_dotenv(dotenv_path=_runtime_env, override=True)

# Importar módulo de Stripe (opcional, solo si está configurado)
try:
    from lib.stripe_config import get_stripe_price_id, is_valid_plan_code, get_plan_code_from_price_id, STRIPE_WEBHOOK_SECRET
    # Importar stripe - lib.stripe_config ya lo importó correctamente, solo lo obtenemos de sys.modules
    import stripe
    # Verificar que stripe.api_key esté configurado y que stripe tenga checkout
    if hasattr(stripe, 'api_key') and stripe.api_key:
        # Verificar que stripe tenga checkout (error es opcional en algunas versiones)
        if hasattr(stripe, 'checkout'):
            STRIPE_AVAILABLE = True
        else:
            logger.warning("⚠️ Stripe importado pero no tiene checkout. Verifica la versión de stripe.")
            STRIPE_AVAILABLE = False
    else:
        STRIPE_AVAILABLE = False
        logger.warning("⚠️ Stripe importado pero STRIPE_SECRET_KEY no está configurada en Railway. Verifica las variables de entorno.")
except (ImportError, ValueError, Exception) as e:
    STRIPE_AVAILABLE = False
    STRIPE_WEBHOOK_SECRET = None
    logger.warning(f"⚠️ Stripe no está disponible: {e}")

# Función para obtener variables de entorno manejando BOM y comillas
def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    value = os.getenv(key, "")
    if not value:
        # Intentar con posibles variaciones (BOM, espacios, etc.)
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener las variables de entorno
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = get_env("OPENAI_API_KEY")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")
DEEPSEEK_API_KEY = get_env("DEEPSEEK_API_KEY")  # Opcional, LiteLLM puede usar la key directamente
ANTHROPIC_API_KEY = get_env("ANTHROPIC_API_KEY")  # Para Claude
GOOGLE_API_KEY = get_env("GOOGLE_API_KEY")  # Para Gemini
COHERE_API_KEY = get_env("COHERE_API_KEY")  # Para Cohere

# Variables de entorno para Stripe (opcionales, solo necesarias si se usa Stripe)
# Detectar si estamos en producción (Render/Railway) o desarrollo
is_production = os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PRODUCTION")
default_frontend_url = "https://codextrader.tech" if is_production else "http://localhost:3000"
FRONTEND_URL = get_env("FRONTEND_URL") or default_frontend_url

# URL del backend (opcional, para construir URLs absolutas si es necesario)
default_backend_url = "https://api.codextrader.tech" if is_production else "http://localhost:8000"
BACKEND_URL = get_env("BACKEND_URL") or default_backend_url

# ============================================================================
# LÓGICA PARA OBTENER URL REST DE SUPABASE
# ============================================================================
# SUPABASE_URL puede estar configurada con la URL de Postgres (postgresql://...)
# Por eso derivamos la URL REST desde SUPABASE_REST_URL o SUPABASE_DB_URL

def _derive_rest_url_from_db(db_url: str) -> str:
    """
    Deriva la URL REST de Supabase desde una URL de conexión a la base de datos.
    
    Acepta varios formatos:
    1. Conexión directa: postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres
    2. Connection pooling: postgresql://postgres.xxx:pass@aws-0-us-west-1.pooler.supabase.com:6543/postgres
    
    y devuelve:
    https://xxx.supabase.co
    """
    if not db_url:
        raise ValueError("SUPABASE_DB_URL is empty, cannot derive REST URL")
    
    # Validar que sea una URL válida antes de parsear
    if not db_url.startswith(("postgresql://", "postgres://")):
        raise ValueError(f"SUPABASE_DB_URL debe empezar con 'postgresql://' o 'postgres://'. Recibido: {db_url[:50]}...")
    
    from urllib.parse import urlparse
    try:
        parsed = urlparse(db_url)
    except Exception as e:
        raise ValueError(f"Error al parsear SUPABASE_DB_URL: {e}. URL recibida: {db_url[:100]}")
    
    host = parsed.hostname or ""
    username = parsed.username or ""
    
    # Caso 1: URL de pooler (ej: aws-0-us-west-1.pooler.supabase.com)
    # En este caso, el project_ref está en el username (formato: postgres.xxx)
    if "pooler.supabase.com" in host or "pooler.supabase.co" in host:
        if username and username.startswith("postgres."):
            # Extraer project_ref del username: postgres.xxx -> xxx
            project_ref = username.replace("postgres.", "")
            if project_ref:
                return f"https://{project_ref}.supabase.co"
        raise ValueError(
            f"No se pudo extraer project_ref desde username en URL de pooler. "
            f"Username esperado: 'postgres.xxx', recibido: '{username}'. "
            f"URL completa: {db_url[:100]}"
        )
    
    # Caso 2: Conexión directa (ej: db.xxx.supabase.co)
    if host.startswith("db."):
        host = host[3:]  # Remover prefijo "db."
    
    # Verificar que el host termine en .supabase.co (no .com)
    if not host.endswith(".supabase.co"):
        raise ValueError(
            f"Hostname no es válido para URL REST de Supabase: {host}. "
            f"URL completa: {db_url[:100]}"
        )
    
    if not host:
        raise ValueError(f"No se pudo extraer el hostname de SUPABASE_DB_URL: {db_url}")
    
    return f"https://{host}"

# Intentar obtener URL REST de Supabase
# PRIORIDAD: 1) SUPABASE_REST_URL, 2) SUPABASE_URL (si es REST), 3) SUPABASE_DB_URL, 4) SUPABASE_URL (si es Postgres)
SUPABASE_REST_URL_ENV = get_env("SUPABASE_REST_URL")
SUPABASE_URL_LEGACY = get_env("SUPABASE_URL")
SUPABASE_DB_URL = get_env("SUPABASE_DB_URL")

if SUPABASE_REST_URL_ENV:
    SUPABASE_REST_URL = SUPABASE_REST_URL_ENV
    pass  # Ya configurado
elif SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("https://"):
    # Si SUPABASE_URL es una URL REST válida (prioridad sobre DB_URL)
    SUPABASE_REST_URL = SUPABASE_URL_LEGACY
elif SUPABASE_DB_URL:
    try:
        SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_DB_URL)
        logger.info(f"✅ URL REST derivada desde SUPABASE_DB_URL: {SUPABASE_REST_URL}")
    except Exception as e:
        logger.error(f"❌ Error al derivar URL REST desde SUPABASE_DB_URL: {e}")
        logger.error(f"   SUPABASE_DB_URL recibida: {SUPABASE_DB_URL[:50]}...")
        # Intentar usar SUPABASE_URL si está disponible
        if SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("postgresql://"):
            try:
                SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_URL_LEGACY)
                logger.info(f"✅ URL REST derivada desde SUPABASE_URL: {SUPABASE_REST_URL}")
            except Exception as e2:
                logger.error(f"❌ Error también con SUPABASE_URL: {e2}")
                raise RuntimeError(
                    f"No se pudo determinar la URL REST de Supabase. "
                    f"Error con SUPABASE_DB_URL: {e}. "
                    f"Error con SUPABASE_URL: {e2}. "
                    "Configura SUPABASE_URL con formato: https://xxx.supabase.co"
                )
        else:
            raise RuntimeError(
                f"No se pudo determinar la URL REST de Supabase. "
                f"Error: {e}. "
                "Configura SUPABASE_URL con formato: https://xxx.supabase.co"
            )
elif SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("postgresql://"):
    # Si SUPABASE_URL es una URL de Postgres, derivar desde ahí
    try:
        SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_URL_LEGACY)
    except Exception as e:
        raise RuntimeError(
            f"No se pudo determinar la URL REST de Supabase. "
            f"Error al parsear SUPABASE_URL: {e}. "
            "Configura SUPABASE_URL con formato: https://xxx.supabase.co"
        )
else:
    # Detectar si estamos en Render o Railway
    platform = "Railway"
    if os.getenv("RENDER"):
        platform = "Render"
    elif os.getenv("RAILWAY_ENVIRONMENT"):
        platform = "Railway"
    
    raise ValueError(
        f"Faltan variables de entorno obligatorias: SUPABASE_URL (o SUPABASE_REST_URL o SUPABASE_DB_URL). "
        f"Asegúrate de tenerlas configuradas en {platform}.\n"
        "Configura una de estas variables:\n"
        "  - SUPABASE_URL (URL REST directa, ej: https://xxx.supabase.co) [RECOMENDADO]\n"
        "  - SUPABASE_REST_URL (URL REST directa, ej: https://xxx.supabase.co)\n"
        "  - SUPABASE_DB_URL (URL de Postgres, ej: postgresql://postgres:pass@db.xxx.supabase.co:5432/postgres)\n"
    )

# Para RAG y otras funciones que necesitan el project_ref, derivarlo desde la URL REST
# Extraer project_ref de la URL REST (formato: https://[project_ref].supabase.co)
SUPABASE_PROJECT_REF = SUPABASE_REST_URL.replace("https://", "").replace(".supabase.co", "")

# Verificar que las variables estén definidas
# OPENAI_API_KEY o DEEPSEEK_API_KEY son opcionales (al menos una debe estar)
# SUPABASE_DB_URL es opcional para el backend (solo se usa en RAG)
has_ai_key = bool(OPENAI_API_KEY or DEEPSEEK_API_KEY)
if not SUPABASE_SERVICE_KEY or not has_ai_key:
    missing = []
    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_KEY")
    if not has_ai_key:
        missing.append("OPENAI_API_KEY o DEEPSEEK_API_KEY (al menos una)")
    
    # Detectar si estamos en Render o Railway
    platform = "Render"
    if os.getenv("RAILWAY_ENVIRONMENT"):
        platform = "Railway"
    elif os.getenv("RENDER"):
        platform = "Render"
    
    raise ValueError(
        f"Faltan variables de entorno obligatorias: {', '.join(missing)}. "
        f"Asegúrate de tenerlas configuradas en {platform}."
    )

# RAG ahora usa sentence-transformers local, solo necesita SUPABASE_DB_URL
RAG_AVAILABLE = bool(SUPABASE_DB_URL)

# Configurar las API keys en las variables de entorno para LiteLLM
# LiteLLM detecta automáticamente las API keys desde variables de entorno
if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
if DEEPSEEK_API_KEY:
    os.environ["DEEPSEEK_API_KEY"] = DEEPSEEK_API_KEY
if ANTHROPIC_API_KEY:
    os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
if GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
if COHERE_API_KEY:
    os.environ["COHERE_API_KEY"] = COHERE_API_KEY

# Verificar si hay un modelo configurado manualmente (tiene prioridad)
chat_model_env = get_env("CHAT_MODEL")
if chat_model_env:
    # Para LiteLLM, DeepSeek necesita el formato "deepseek/deepseek-chat"
    # Si el usuario puso solo "deepseek-chat", agregamos el prefijo
    if chat_model_env.lower() == "deepseek-chat" or chat_model_env.lower().startswith("deepseek-chat"):
        chat_model_clean = "deepseek/deepseek-chat"
    elif chat_model_env.lower().startswith("deepseek/"):
        # Ya tiene el formato correcto
        chat_model_clean = chat_model_env.strip()
    else:
        # Otro modelo, usar tal cual
        chat_model_clean = chat_model_env.strip()
    
    # Si CHAT_MODEL está configurado, usarlo SIEMPRE (tiene prioridad absoluta)
    # Respetar la configuración del usuario, NO cambiar a OpenAI aunque esté disponible
    modelo_por_defecto = chat_model_clean
else:
    # Si no hay CHAT_MODEL, priorizar DeepSeek si está disponible
    if DEEPSEEK_API_KEY:
        # LiteLLM requiere el formato "deepseek/deepseek-chat"
        modelo_por_defecto = "deepseek/deepseek-chat"
    elif OPENAI_API_KEY:
        modelo_por_defecto = "gpt-3.5-turbo"
    else:
        # Fallback final
        modelo_por_defecto = "gpt-3.5-turbo"
# Inicializar componentes RAG solo si SUPABASE_DB_URL está configurado
vector_store = None
index = None
query_engine = None
embed_model = None
local_embedder = None

if RAG_AVAILABLE:
    try:

        # Usar el project_ref derivado desde la URL REST
        project_ref = SUPABASE_PROJECT_REF

        # Definir el modelo de embedding de OpenAI (mismo que en ingest.py)
        # embed_model = OpenAIEmbedding(model="text-embedding-3-small")
        # Inicializar embedder LOCAL para retrieval (MiniLM 384d)
        try:
            local_embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")
        except Exception:
            local_embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # ✅ Obtener SUPABASE_DB_URL desde variables de entorno
        # Esta debe ser la URL completa de conexión PostgreSQL (con connection pooling)
        from urllib.parse import urlparse
        import os
        
        database_url = os.getenv("SUPABASE_DB_URL")
        
        # Log para diagnóstico (sin contraseña completa)
        if database_url:
            parsed_debug = urlparse(database_url)
            logger.info(f"📋 SUPABASE_DB_URL detectada: {parsed_debug.scheme}://{parsed_debug.hostname}:{parsed_debug.port or 5432}")
            if "pooler" not in database_url:
                logger.warning(f"⚠️ ADVERTENCIA: SUPABASE_DB_URL no parece usar Connection Pooling (no contiene 'pooler')")
        
        if not database_url:
            raise ValueError("❌ SUPABASE_DB_URL no está configurada. Esta variable es OBLIGATORIA para RAG.\n\n"
                           "Configura SUPABASE_DB_URL con el formato completo:\n"
                           "postgresql://postgres.xxx:password@aws-1-us-east-1.pooler.supabase.com:5432/postgres\n\n"
                           "Obtén esta URL en:\n"
                           "1. Ve a Supabase Dashboard → Settings → Database\n"
                           "2. Connection string → Connection pooling (modo Session)\n"
                           "3. Copia la URL completa y configúrala en Render/Railway como SUPABASE_DB_URL")
        
        # Limpiar la URL (remover comillas si las tiene)
        database_url = database_url.strip('"').strip("'").strip()
        
        # Validar formato
        if not database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError(f"❌ SUPABASE_DB_URL debe empezar con 'postgresql://' o 'postgres://'\n"
                           f"Recibido: {database_url[:50]}...")
        
        # Parsear URL para limpiar parámetros inválidos para psycopg2
        # psycopg2 NO acepta: pool_timeout, pool_pre_ping, pool_size, max_overflow, pool_recycle
        # Solo acepta parámetros estándar de PostgreSQL: connect_timeout, application_name, etc.
        parsed = urlparse(database_url)
        
        # Asegurar que la contraseña esté codificada correctamente si tiene caracteres especiales
        if parsed.password:
            from urllib.parse import quote_plus, unquote
            # Decodificar primero para obtener la contraseña original, luego codificar correctamente
            decoded_password = unquote(parsed.password)
            encoded_password = quote_plus(decoded_password)
            # Reconstruir netloc con la contraseña codificada
            if encoded_password != parsed.password:
                auth = f"{parsed.username}:{encoded_password}" if parsed.username else encoded_password
                netloc = f"{auth}@{parsed.hostname}" if parsed.hostname else auth
                if parsed.port:
                    netloc = f"{netloc}:{parsed.port}"
                # Crear nuevo objeto ParseResult con la contraseña codificada
                from urllib.parse import ParseResult
                parsed = ParseResult(
                    parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment
                )
        
        # Reconstruir URL solo con parámetros válidos para psycopg2
        valid_params = {}
        if parsed.query:
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            
            # Parámetros válidos para psycopg2
            valid_keys = ['connect_timeout', 'application_name', 'sslmode', 'sslrootcert']
            
            for key in valid_keys:
                if key in params:
                    # Tomar el primer valor si hay múltiples
                    value = params[key][0] if isinstance(params[key], list) else params[key]
                    valid_params[key] = value
        
        # Asegurar que connect_timeout esté configurado (mínimo 60 segundos para consultas vectoriales largas)
        if 'connect_timeout' not in valid_params:
            valid_params['connect_timeout'] = '120'  # 2 minutos para consultas vectoriales
        else:
            # Aumentar timeout si es muy bajo
            try:
                current_timeout = int(valid_params['connect_timeout'])
                if current_timeout < 120:
                    valid_params['connect_timeout'] = '120'
            except (ValueError, TypeError):
                valid_params['connect_timeout'] = '120'
        
        # Asegurar application_name
        if 'application_name' not in valid_params:
            valid_params['application_name'] = 'rag_app'
        
        # Construir la URL limpia
        from urllib.parse import urlencode
        clean_query = urlencode(valid_params) if valid_params else ''
        connection_string = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_query:
            connection_string += f"?{clean_query}"
        
        # Log de conexión con detalles para diagnóstico
        hostname = parsed.hostname or "N/A"
        port = parsed.port or 5432
        username = parsed.username or "N/A"
        # Log parcial de la URL (sin contraseña completa por seguridad)
        # Conexión a base de datos configurada
        
        # Detectar si es pooler
        is_pooler = "pooler.supabase.com" in hostname or "pooler.supabase.co" in hostname
        
        # Advertencia si usa puerto 6543 (Transaction pooler) en lugar de 5432 (Session pooler)
        if port == 6543:
            logger.warning(f"⚠️ Usando puerto 6543 (Transaction pooler). Para Session pooler usa puerto 5432.")
        
        try:
            # Crear vector store
            # logger.debug(f"Creando SupabaseVectorStore con collection: {config.VECTOR_COLLECTION_NAME}")
            # vector_store = SupabaseVectorStore(
            #     postgres_connection_string=connection_string,
            #     collection_name=config.VECTOR_COLLECTION_NAME
            # )
            
            # Intentar crear índice vectorial usando vecs (opcional, el RAG funciona sin él)
            try:
                import vecs
                vecs_connection_string = database_url.strip('"').strip("'").strip()
                
                # Verificar que la URL use pooler (no conexión directa)
                if "db." in vecs_connection_string and ".supabase.co" in vecs_connection_string and "pooler" not in vecs_connection_string:
                    logger.warning(f"⚠️ ADVERTENCIA: La URL parece ser conexión directa (db.xxx.supabase.co). "
                                 f"Railway requiere Connection Pooling. Verifica SUPABASE_DB_URL.")
                    logger.warning(f"   URL recibida: {vecs_connection_string[:80]}...")
                    # No intentar conectar con conexión directa en Railway
                    raise ValueError("URL de conexión directa detectada. Railway requiere Connection Pooling.")
                
                parsed_original = urlparse(vecs_connection_string)
                
                # Log para diagnóstico (sin contraseña completa)
                logger.info(f"🔗 Conectando con vecs a: {parsed_original.scheme}://{parsed_original.hostname}:{parsed_original.port or 5432}")
                
                if parsed_original.query:
                    from urllib.parse import parse_qs, urlencode
                    params_original = parse_qs(parsed_original.query)
                    valid_keys = ['connect_timeout', 'application_name', 'sslmode', 'sslrootcert']
                    valid_params_original = {}
                    for key in valid_keys:
                        if key in params_original:
                            value = params_original[key][0] if isinstance(params_original[key], list) else params_original[key]
                            valid_params_original[key] = value
                    
                    clean_query_original = urlencode(valid_params_original) if valid_params_original else ''
                    vecs_connection_string = f"{parsed_original.scheme}://{parsed_original.netloc}{parsed_original.path}"
                    if clean_query_original:
                        vecs_connection_string += f"?{clean_query_original}"
                
                vx = vecs.create_client(vecs_connection_string)
                
                try:
                    collection = vx.get_collection(config.VECTOR_COLLECTION_NAME)
                    try:
                        collection.create_index(measure='cosine_distance')
                    except Exception:
                        pass  # Índice ya existe o no se puede crear, no es crítico
                except Exception:
                    pass  # Colección no existe, el RAG usa match_documents_384 con book_chunks
            except Exception:
                pass  # vecs no disponible o error, el RAG funciona sin él
            
            # Intentar cargar el índice para verificar la conexión realmente funciona
            # logger.info("Verificando conexión con consulta de prueba...")
            
            # test_index = VectorStoreIndex.from_vector_store(
            #     vector_store=vector_store,
            #     embed_model=embed_model
            # )
            
            # logger.info("✅ Conexión exitosa a Supabase")
            # # Usar el índice de prueba
            # index = test_index
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Error al conectar a Supabase: {error_msg}")
            raise Exception(
                f"No se pudo conectar a Supabase usando SUPABASE_DB_URL.\n"
                f"Error: {error_msg}\n\n"
                f"Verifica:\n"
                f"1. Que SUPABASE_DB_URL esté configurada correctamente en Render/Railway\n"
                f"2. Que la URL sea válida y tenga el formato correcto:\n"
                f"   postgresql://postgres.xxx:password@aws-X-us-Y-Z.pooler.supabase.com:PORT/postgres\n"
                f"3. Que Connection pooling esté HABILITADO en Supabase\n"
                f"4. Que Network Restrictions esté DESHABILITADO en Supabase\n"
                f"5. Que la región y puerto en la URL sean correctos\n\n"
                f"Para obtener la URL correcta:\n"
                f"1. Ve a Supabase Dashboard → Settings → Database\n"
                f"2. Connection string → Connection pooling (modo Session)\n"
                f"3. Copia la URL completa y configúrala en Render/Railway como SUPABASE_DB_URL\n"
            )
        
        # NOTA: El sistema RAG usa match_documents_384 RPC con book_chunks
        # No necesita vector_store ni index de LlamaIndex
        # Solo necesita local_embedder (ya inicializado) y SUPABASE_DB_URL (ya verificado)
        
        # Verificar que el embedder local esté inicializado (requisito crítico)
        if local_embedder is None:
            raise Exception(
                f"No se pudo inicializar el embedder local.\n"
                f"El sistema RAG requiere sentence-transformers para generar embeddings de consultas."
            )
        
        pass  # Log final se muestra después de inicializar Supabase
    except Exception as e:
        # Log más detallado del error
        error_msg = str(e)
        
        # Detectar si es un error crítico que realmente deshabilita el RAG
        is_critical_error = (
            "Network is unreachable" in error_msg or 
            "connection" in error_msg.lower() or
            "could not translate host name" in error_msg.lower() or
            "FATAL" in error_msg or
            "embedder local" in error_msg.lower()
        )
        
        if is_critical_error:
            logger.error(f"❌ Error crítico al inicializar sistema RAG: {error_msg}")
            
            # Detectar plataforma para mensajes específicos
            platform = "Render"
            if os.getenv("RAILWAY_ENVIRONMENT"):
                platform = "Railway"
            elif os.getenv("RENDER"):
                platform = "Render"
            
            # Mensaje más específico según el tipo de error
            if "Network is unreachable" in error_msg or "connection" in error_msg.lower():
                logger.warning("⚠️ No se pudo conectar a la base de datos de Supabase. Verifica:")
                logger.warning(f"   1. Que SUPABASE_DB_URL esté configurado correctamente en {platform}")
                logger.warning(f"   2. Que el servidor de Supabase esté accesible desde {platform}")
                logger.warning("   3. Que no haya restricciones de firewall bloqueando la conexión")
            elif "embedder local" in error_msg.lower():
                logger.warning("⚠️ No se pudo inicializar el embedder local (sentence-transformers)")
                logger.warning("   El RAG requiere el embedder para generar embeddings de consultas")
            
            logger.warning("El sistema continuará sin RAG. Las funciones de autenticación y otros endpoints seguirán funcionando.")
            RAG_AVAILABLE = False
            
            # IMPORTANTE: Enviar email al admin sobre el error crítico
            try:
                from lib.email import send_critical_error_email
                import threading
                import traceback
                
                def send_error_email_background():
                    try:
                        error_details = traceback.format_exc()[:2000]  # Limitar a 2000 caracteres
                        send_critical_error_email(
                            error_type="RAG Initialization Error",
                            error_message=f"Error crítico al inicializar sistema RAG: {error_msg[:500]}",
                            error_details=error_details,
                            context={
                                "Platform": platform,
                                "RAG Available": "False",
                                "Error Type": "Critical System Error"
                            }
                        )
                    except Exception as email_err:
                        print(f"⚠️ Error al enviar email de error crítico: {email_err}")
                
                error_thread = threading.Thread(target=send_error_email_background, daemon=True)
                error_thread.start()
            except Exception as email_error:
                print(f"⚠️ Error al preparar email de error crítico: {email_error}")
        else:
            # Error no crítico (como vecs.knowledge no existe)
            logger.warning(f"⚠️ Advertencia al inicializar sistema RAG: {error_msg[:200]}")
            # NO deshabilitar RAG, continuar normalmente
        
        vector_store = None
        index = None
        query_engine = None
        embed_model = None

# Inicializar cliente de Supabase para autenticación (usar URL REST)
supabase_status = "❌ Error"
try:
    supabase_client = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
    supabase_status = "✅ OK"
except Exception as e:
    logger.error(f"❌ Error al inicializar cliente de Supabase: {e}")
    raise RuntimeError(f"No se pudo inicializar cliente de Supabase: {e}")

# Log final de estado del sistema - Todos los componentes importantes
logger.info("=" * 80)
logger.info("🚀 SISTEMA INICIADO - RESUMEN DE COMPONENTES")
logger.info("=" * 80)
logger.info(f"✅ Modelo de IA: {modelo_por_defecto}")
logger.info(f"✅ Supabase: {supabase_status}")
if RAG_AVAILABLE:
    logger.info("✅ RAG: ACTIVO (Metodología propia basada en checksums, sin índices OpenAI)")
    logger.info("   └─ Usa: match_documents_384 + all-MiniLM-L6-v2 (384d) + book_chunks")
else:
    logger.info("⚠️  RAG: DESACTIVADO (SUPABASE_DB_URL no configurada)")
logger.info(f"{'✅' if STRIPE_AVAILABLE else '⚠️ '} Stripe: {'disponible' if STRIPE_AVAILABLE else 'no configurado'}")
logger.info("✅ Hash/Checksum: OK (Sistema anti-duplicados activo)")
logger.info(f"🌐 Backend URL: {BACKEND_URL}")
logger.info(f"🌐 Frontend URL: {FRONTEND_URL}")
logger.info("=" * 80)

# Inicializar FastAPI
app = FastAPI(title=config.API_TITLE, description=config.API_DESCRIPTION)

# IMPORTANTE: Configurar CORS PRIMERO, antes de cualquier router o middleware
# Configurar CORS para permitir peticiones desde el frontend
# Define los orígenes permitidos (incluyendo variaciones comunes)
origins = [
    "https://www.codextrader.tech",
    "https://codextrader.tech",
    "http://localhost:3000",
    "http://localhost:8080",
]

# Añadir FRONTEND_URL si está configurado y no está ya en la lista
if FRONTEND_URL:
    # Normalizar FRONTEND_URL (sin barra final, sin /app)
    frontend_url_clean = FRONTEND_URL.rstrip('/').replace('/app', '')
    if frontend_url_clean not in origins:
        origins.append(frontend_url_clean)
    # Asegurar que también incluya la versión con www si corresponde
    if 'codextrader.tech' in frontend_url_clean and 'www.' not in frontend_url_clean:
        www_version = frontend_url_clean.replace('https://codextrader.tech', 'https://www.codextrader.tech')
        if www_version not in origins:
            origins.append(www_version)

logger.info(f"🌐 CORS configurado - Orígenes permitidos: {origins}")

# IMPORTANTE: Configurar CORS ANTES de cualquier otro middleware o router
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Importar y registrar router de administración (después de CORS)
try:
    from admin_router import admin_router
    app.include_router(admin_router)
    logger.info("✅ Router de administración registrado")
except Exception as e:
    logger.warning(f"⚠️ No se pudo registrar router de administración: {e}")

# Endpoint OPTIONS explícito para preflight requests
@app.options("/{full_path:path}")
async def options_handler(full_path: str, request: Request):
    """Maneja requests OPTIONS (preflight) para CORS"""
    from fastapi.responses import Response
    origin = request.headers.get("origin")
    if origin in origins:
        return Response(
            content="OK",
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Credentials": "true",
            }
        )
    return Response(content="OK", status_code=200)

# Función helper para crear un cliente de Supabase con el token del usuario
def get_user_supabase_client(token: str):
    """
    Crea un cliente de Supabase usando el token JWT del usuario.
    Esto asegura que las consultas se hagan con el contexto correcto del usuario.
    """
    # Usar SUPABASE_ANON_KEY si está disponible (mejor para RLS)
    # Si no está disponible, usar SERVICE_KEY (las políticas RLS que creamos permiten service_role)
    from supabase import create_client
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    
    # Preferir ANON_KEY para respetar RLS correctamente
    api_key = SUPABASE_ANON_KEY if SUPABASE_ANON_KEY else SUPABASE_SERVICE_KEY
    
    client = create_client(SUPABASE_REST_URL, api_key)
    
    # Si usamos ANON_KEY, establecer el token del usuario para que RLS funcione
    # Si usamos SERVICE_KEY, las políticas que creamos permiten las consultas
    if SUPABASE_ANON_KEY and hasattr(client, 'postgrest'):
        try:
            # Establecer el token del usuario en postgrest
            client.postgrest.auth(token)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo establecer token en cliente: {e}")
            # Continuar de todas formas, las políticas de service_role deberían funcionar
    
    return client

# Función helper para obtener y validar el usuario desde el token JWT
async def get_user(authorization: Optional[str] = Header(None)):
    """
    Valida el token JWT de Supabase y devuelve el objeto usuario.
    Lanza HTTPException 401 si el token es inválido o no está presente.
    """
    if not authorization:
        logger.warning("⚠️ get_user: No se recibió header Authorization")
        raise HTTPException(
            status_code=401,
            detail="Token de autorización requerido. Incluye 'Authorization: Bearer <token>' en los headers."
        )
    
    # Extraer el token del header "Bearer <token>"
    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            logger.warning("⚠️ get_user: Token vacío después de extraer 'Bearer '")
            raise HTTPException(
                status_code=401,
                detail="Formato de token inválido. Usa 'Bearer <token>'"
            )
    except Exception as e:
        logger.warning(f"⚠️ get_user: Error al extraer token: {e}")
        raise HTTPException(
            status_code=401,
            detail="Formato de token inválido. Usa 'Bearer <token>'"
        )
    
    # Validar el token con Supabase
    try:
        logger.debug(f"🔐 get_user: Validando token (primeros 20 chars: {token[:20]}...)")
        user_response = supabase_client.auth.get_user(token)
        if not user_response.user:
            logger.warning("⚠️ get_user: user_response.user es None")
            raise HTTPException(
                status_code=401,
                detail="Token inválido o expirado"
            )
        logger.debug(f"✅ get_user: Usuario validado: {user_response.user.email}")
        # Retornar el usuario sin modificar (el objeto User de Supabase no permite atributos arbitrarios)
        return user_response.user
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ get_user: Error al validar token con Supabase: {error_msg}")
        # Log más detallado del error
        if "Invalid API key" in error_msg or "Invalid URL" in error_msg:
            logger.error(f"❌ Posible problema con configuración de Supabase: URL={SUPABASE_REST_URL[:50]}...")
        raise HTTPException(
            status_code=401,
            detail=f"Error al validar token: {error_msg[:100]}"
        )

# Modelo Pydantic para la entrada de consulta
class QueryInput(BaseModel):
    query: str
    conversation_id: Optional[str] = None  # ID de la conversación (opcional, se crea nueva si no se proporciona)
    response_mode: Optional[str] = 'fast'  # 'fast' o 'deep'
    category: Optional[str] = None  # Categoría para filtrar documentos (opcional)

# Modelo para crear nueva conversación
class NewConversationInput(BaseModel):
    title: Optional[str] = None  # Título opcional (se genera desde la primera pregunta si no se proporciona)

# Endpoint POST /chat (también disponible como /chat-simple para compatibilidad con frontend)
@app.post("/chat")
@app.post("/chat-simple")
async def chat(query_input: QueryInput, user = Depends(get_user)):
    """
    Endpoint para hacer consultas sobre los documentos indexados.
    
    Requiere autenticación mediante token JWT de Supabase.
    Verifica tokens disponibles, ejecuta la consulta con LiteLLM (Deepseek por defecto),
    y descuenta los tokens usados del perfil del usuario.
    """
    
    def is_simple_greeting(message: str) -> bool:
        """
        Detecta si el mensaje es solo un saludo simple sin contenido de trading.
        Retorna True si es solo un saludo, False si contiene contenido de trading.
        """
        # Normalizar el mensaje: minúsculas, sin espacios extra, sin emojis
        normalized = re.sub(r'[^\w\s]', '', message.lower().strip())
        words = normalized.split()
        
        # Si el mensaje es muy largo, probablemente no es solo un saludo
        if len(words) > 5:
            return False
        
        # Lista de saludos simples (español e inglés)
        simple_greetings = [
            'hola', 'hi', 'hello', 'hey',
            'buenas', 'buen', 'día', 'day',
            'qué', 'tal', 'what', 'up',
            'saludos', 'greetings',
            'buenos', 'días', 'mornings', 'afternoon', 'evening',
            'good', 'morning', 'afternoon', 'evening',
            'there', 'hola qué tal', 'hi there', 'hello there', 'hey there'
        ]
        
        # Verificar si todas las palabras son saludos simples
        all_greetings = all(word in simple_greetings for word in words if word)
        
        # Palabras relacionadas con trading que indican que NO es solo un saludo
        trading_keywords = [
            'trading', 'trader', 'mercado', 'market', 'operar', 'trade',
            'estrategia', 'strategy', 'riesgo', 'risk', 'capital', 'money',
            'análisis', 'analysis', 'gráfico', 'chart', 'indicador', 'indicator',
            'soporte', 'support', 'resistencia', 'resistance', 'tendencia', 'trend',
            'compra', 'venta', 'buy', 'sell', 'precio', 'price', 'acción', 'stock',
            'forex', 'crypto', 'bitcoin', 'cripto', 'divisa', 'currency',
            'psicología', 'psychology', 'emociones', 'emotions', 'disciplina', 'discipline',
            'swing', 'scalping', 'intradía', 'intraday', 'day trading', 'daytrading',
            'explicar', 'explain', 'qué es', 'what is', 'cómo', 'how', 'cuál', 'which'
        ]
        
        # Si contiene palabras de trading, NO es solo un saludo
        has_trading_content = any(keyword in normalized for keyword in trading_keywords)
        
        # Es solo un saludo si: todas las palabras son saludos Y no hay contenido de trading
        return all_greetings and not has_trading_content and len(words) > 0
    
    # Declarar variables globales al inicio de la función
    global vector_store, index, embed_model
    
    try:
        # Obtener el ID del usuario
        user_id = user.id
        
        # Paso A: Verificar tokens disponibles
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_restantes = profile_response.data[0]["tokens_restantes"]
        
        if tokens_restantes <= 0:
            # IMPORTANTE: Enviar email al usuario cuando los tokens se agoten (solo una vez)
            try:
                from lib.email import send_email
                import threading
                from datetime import datetime
                
                # Verificar si ya se envió el email de tokens agotados (usar un flag en el perfil)
                profile_check = supabase_client.table("profiles").select("email, tokens_exhausted_email_sent").eq("id", user_id).execute()
                user_email = profile_check.data[0].get("email") if profile_check.data else None
                email_already_sent = profile_check.data[0].get("tokens_exhausted_email_sent", False) if profile_check.data else False
                
                if user_email and not email_already_sent:
                    def send_tokens_exhausted_email():
                        try:
                            user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                            # Construir URL de billing antes del f-string
                            import os
                            frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                            billing_url = f"{frontend_url.rstrip('/')}/billing"
                            
                            user_html = f"""
                            <html>
                            <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                    <h1 style="color: white; margin: 0; font-size: 28px;">⚠️ Tus Tokens se Han Agotado</h1>
                                </div>
                                
                                <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                    <p style="font-size: 16px; margin-bottom: 20px;">
                                        Hola <strong>{user_name}</strong>,
                                    </p>
                                    
                                    <p style="font-size: 16px; margin-bottom: 20px;">
                                        Te informamos que tus tokens se han agotado. Para continuar usando Codex Trader, necesitas recargar tokens.
                                    </p>
                                    
                                    <div style="background: #fee2e2; padding: 20px; border-radius: 8px; border-left: 4px solid #ef4444; margin: 20px 0;">
                                        <p style="margin: 0; color: #991b1b; font-weight: bold; font-size: 18px;">
                                            Tokens restantes: 0
                                        </p>
                                    </div>
                                    
                                    <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                        <h3 style="color: #059669; margin-top: 0; font-size: 18px;">💡 Opciones para continuar:</h3>
                                        <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                                            <li style="margin-bottom: 10px;">Recargar tokens desde tu panel de cuenta</li>
                                            <li style="margin-bottom: 10px;">Actualizar a un plan con más tokens mensuales</li>
                                            <li style="margin-bottom: 0;">Contactarnos si necesitas ayuda</li>
                                        </ul>
                                    </div>
                                    
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="{billing_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                            💰 Recargar Tokens
                                        </a>
                                    </div>
                                    
                                    <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                        Si tienes alguna pregunta, no dudes en contactarnos respondiendo a este correo.
                                    </p>
                                </div>
                            </body>
                            </html>
                            """
                            send_email(
                                to=user_email,
                                subject="⚠️ Tus tokens se han agotado - Codex Trader",
                                html=user_html
                            )
                            
                            # Marcar que el email fue enviado
                            supabase_client.table("profiles").update({
                                "tokens_exhausted_email_sent": True
                            }).eq("id", user_id).execute()
                            
                            print(f"✅ Email de tokens agotados enviado a {user_email}")
                        except Exception as e:
                            print(f"⚠️ Error al enviar email de tokens agotados: {e}")
                    
                    email_thread = threading.Thread(target=send_tokens_exhausted_email, daemon=True)
                    email_thread.start()
            except Exception as email_error:
                print(f"⚠️ Error al preparar email de tokens agotados: {email_error}")
            
            raise HTTPException(
                status_code=402,
                detail="Tokens agotados. Por favor, recarga."
            )
        
        # Verificar si es solo un saludo simple (evitar búsqueda RAG para acelerar respuesta)
        is_greeting = is_simple_greeting(query_input.query)
        
        # Inicializar variables para fuentes y SYSTEM_PROMPT
        context_text = ""
        sources_text = ""
        SYSTEM_PROMPT = None
        citation_list = ""
        source_list = []
        retrieved_chunks = []
        respuesta_texto = ""  # Inicializar aquí para evitar errores si falla LiteLLM
        tokens_usados = 0  # Inicializar aquí para evitar errores si falla LiteLLM
        nuevos_tokens = tokens_restantes  # Inicializar con tokens actuales para evitar errores
        conversation_id = query_input.conversation_id  # Inicializar aquí para evitar errores
        
        if is_greeting:
            # Para saludos simples, saltarse RAG completamente (contexto vacío)
            logger.info("ℹ️  Saludo simple detectado - RAG omitido (respuesta rápida sin contexto)")
            contexto = ""
        elif not RAG_AVAILABLE or local_embedder is None:
            # Si RAG no está disponible, usar contexto vacío
            if not RAG_AVAILABLE:
                logger.warning("RAG no disponible: SUPABASE_DB_URL no configurada. Respondiendo sin contexto de documentos.")
            elif local_embedder is None:
                logger.warning("RAG no disponible: Embedder local no inicializado. Respondiendo sin contexto de documentos.")
            contexto = ""
        else:
            # Obtener contexto usando embeddings locales + RPC en Supabase (sin OpenAI)
            import time
            start_time = time.time()
            logger.info("=" * 80)
            logger.info("🔍 CONSULTANDO RAG - Metodología propia (checksums, sin índices OpenAI)")
            logger.info(f"📝 Consulta: {query_input.query[:100]}{'...' if len(query_input.query) > 100 else ''}")
            logger.info("─" * 80)
            try:
                if local_embedder is None:
                    raise RuntimeError("Embedder local MiniLM no inicializado")
                # Generar embedding local (384d) con SentenceTransformer
                logger.info("⚙️  Generando embedding con all-MiniLM-L6-v2 (384 dimensiones)...")
                query_vec = local_embedder.encode([query_input.query], show_progress_bar=False)[0]
                query_embedding = query_vec.tolist()
                
                # Determinar match_count según el modo de respuesta
                # Modo Estudio Profundo: más chunks para más contexto
                # Modo Rápido: menos chunks para respuestas más rápidas
                is_deep_mode = query_input.response_mode and (
                    query_input.response_mode.lower() == 'deep' or 
                    query_input.response_mode.lower() == 'estudio profundo' or
                    query_input.response_mode.lower() == 'profundo'
                )
                
                if is_deep_mode:
                    # Modo Estudio Profundo: 15 chunks para máximo contexto
                    match_count = 15
                    logger.info(f"📚 Modo Estudio Profundo: usando {match_count} chunks para contexto amplio")
                else:
                    # Modo Rápido: 5 chunks para respuestas rápidas
                    match_count = 5
                    logger.info(f"⚡ Modo Rápido: usando {match_count} chunks para respuesta rápida")
                
                logger.info(f"🔎 Buscando en book_chunks usando match_documents_384 (top {match_count})...")
                payload = {"query_embedding": query_embedding, "match_count": match_count}
                # Agregar category_filter si se proporciona una categoría
                if query_input.category:
                    payload["category_filter"] = query_input.category
                    logger.info(f"📂 Filtro de categoría aplicado: {query_input.category}")
                rpc = supabase_client.rpc("match_documents_384", payload).execute()
                rows = rpc.data or []
                context_chunks = rows
                retrieved_chunks = rows  # Variable para verificar si hay chunks recuperados
                logger.info(f"🔍 [DEBUG] retrieved_chunks asignado: {len(retrieved_chunks) if retrieved_chunks else 0} chunks")
                logger.info(f"🔍 [DEBUG] retrieved_chunks es truthy: {bool(retrieved_chunks)}")
                
                # Extraer doc_id únicos de los chunks para buscar los nombres de archivo
                doc_ids = set()
                for row in rows:
                    metadata = row.get("metadata", {})
                    if isinstance(metadata, dict):
                        doc_id = metadata.get("doc_id")
                        if doc_id:
                            doc_ids.add(doc_id)
                
                # Consultar la tabla documents para obtener los filename asociados
                doc_id_to_filename = {}
                if doc_ids:
                    try:
                        docs_response = supabase_client.table("documents").select("doc_id, filename").in_("doc_id", list(doc_ids)).execute()
                        if docs_response.data:
                            for doc in docs_response.data:
                                doc_id_to_filename[doc.get("doc_id")] = doc.get("filename", "Documento desconocido")
                        logger.info(f"📚 Fuentes encontradas: {len(doc_id_to_filename)} documentos únicos")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al obtener nombres de archivo: {str(e)[:100]}")
                
                # Construcción condicional de contexto y citación basada en response_mode
                # is_deep_mode ya está definido arriba, reutilizamos la variable
                if is_deep_mode:
                    # Lógica de Citación (Para modo detallado/Estudio Profundo)
                    context_components = []
                    unique_sources = {}
                    source_index = 1
                    
                    for chunk in rows:
                        # Extraer doc_id y content
                        metadata = chunk.get("metadata", {})
                        if isinstance(metadata, dict):
                            doc_id = metadata.get("doc_id")
                        else:
                            doc_id = None
                        
                        chunk_content = chunk.get("content", "")
                        
                        # Obtener filename desde la tabla documents o metadata
                        if doc_id and doc_id in doc_id_to_filename:
                            source_filename = doc_id_to_filename[doc_id]
                        else:
                            # Fallback: intentar obtener desde metadata
                            if isinstance(metadata, dict):
                                source_filename = metadata.get("source_file") or metadata.get("file_name") or doc_id or "Documento desconocido"
                            else:
                                source_filename = "Documento desconocido"
                        
                        # Crear referencia única por fuente
                        if source_filename not in unique_sources:
                            unique_sources[source_filename] = source_index
                            source_index += 1
                        
                        source_tag = f"[Fuente {unique_sources[source_filename]}]"
                        context_components.append(f"{source_tag} {chunk_content}")
                    
                    contexto = "\n---\n".join(context_components)
                    logger.info(f"🔍 [DEBUG] contexto construido (Estudio Profundo): {len(contexto)} caracteres, context_components={len(context_components)}")
                    logger.info(f"🔍 [DEBUG] Primeros 200 caracteres de contexto: {contexto[:200] if contexto else 'VACÍO'}")
                    
                    # Crear la lista final de fuentes para el LLM
                    citation_list = "\n".join([
                        f"[{index}]: {filename}" 
                        for filename, index in sorted(unique_sources.items(), key=lambda x: x[1])
                    ])
                    
                    sources_text = citation_list
                    logger.info(f"📚 Modo Estudio Profundo: {len(unique_sources)} fuentes únicas con citación")
                else:
                    # Lógica Rápida (Para modo veloz, sin citación)
                    context_content = [chunk.get("content", "") for chunk in rows if chunk.get("content")]
                    contexto = "\n---\n".join(context_content)
                    logger.info(f"🔍 [DEBUG] contexto construido (Modo Rápido): {len(contexto)} caracteres, context_content={len(context_content)}")
                    logger.info(f"🔍 [DEBUG] Primeros 200 caracteres de contexto: {contexto[:200] if contexto else 'VACÍO'}")
                    sources_text = ""
                    citation_list = ""
                    logger.info("⚡ Modo rápido: sin citación de fuentes")
                
                duration = time.time() - start_time
                logger.info("─" * 80)
                logger.info(f"✅ RAG EXITOSO: {len(context_chunks)} chunks recuperados en {duration:.2f}s")
                logger.info(f"📊 Contexto generado: {len(contexto)} caracteres")
                logger.info(f"📚 Fuentes utilizadas: {len(unique_sources) if is_deep_mode else 0} documentos")
                logger.info("=" * 80)
            except Exception as e:
                error_msg = str(e)
                # Si la función RPC no existe, es un error no crítico
                if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
                    logger.warning(f"⚠️ La función RPC 'match_documents_384' no existe en Supabase")
                    logger.warning("ℹ️ Ejecuta el script SQL 'create_match_documents_384_function.sql' en Supabase SQL Editor")
                    logger.warning("ℹ️ Continuando sin contexto RAG para esta consulta")
                elif "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                    logger.warning(f"⚠️ La tabla 'book_chunks' no existe en Supabase")
                    logger.warning("ℹ️ Los libros deben ser indexados primero usando ingest_masiva_local.py")
                    logger.warning("ℹ️ Continuando sin contexto RAG para esta consulta")
                else:
                    logger.error(f"Error en búsqueda RPC RAG: {error_msg[:200]}")
                contexto = ""
                context_text = ""
                sources_text = ""
                citation_list = ""
                source_list = []
                retrieved_chunks = []
        
        # DEBUG: Verificar valores antes de decidir si llamar a LiteLLM
        logger.info(f"🔍 [DEBUG] ANTES DE DECISIÓN LLM:")
        logger.info(f"🔍 [DEBUG] - contexto: {len(contexto) if contexto else 0} caracteres (vacío: {not contexto or contexto.strip() == ''})")
        logger.info(f"🔍 [DEBUG] - retrieved_chunks: {len(retrieved_chunks) if retrieved_chunks else 0} chunks")
        logger.info(f"🔍 [DEBUG] - is_greeting: {is_greeting}")
        logger.info(f"🔍 [DEBUG] - context_text: {len(context_text) if context_text else 0} caracteres")
        if contexto and len(contexto) > 0:
            logger.info(f"🔍 [DEBUG] - contexto NO está vacío, debería proceder con RAG")
        else:
            logger.warning(f"🔍 [DEBUG] - ⚠️ contexto ESTÁ VACÍO, podría entrar en fallback")
        
        # Crear el prompt con contexto y pregunta
        # Si es un saludo, usar un prompt más simple sin contexto RAG
        if is_greeting:
            # Para saludos, el prompt es simplemente el mensaje del usuario
            prompt = query_input.query
            SYSTEM_PROMPT = None
        else:
            # Determinar si es modo "Estudio Profundo" (deep) o modo rápido
            is_deep_mode = query_input.response_mode and (
                query_input.response_mode.lower() == 'deep' or 
                query_input.response_mode.lower() == 'estudio profundo' or
                query_input.response_mode.lower() == 'profundo'
            )
            
            if is_deep_mode and sources_text:
                # Prompt que pide Citaciones (Modo Estudio Profundo)
                SYSTEM_PROMPT = f"""Eres Codex Trader, un experto financiero y asistente de RAG. Tu tarea es responder a la pregunta del usuario ÚNICAMENTE basándote en el contexto proporcionado.

Sigue estrictamente estas reglas:

1. Proporciona un resumen conciso y detallado.

2. POR CADA HECHO que utilices, debes **citar inmediatamente la fuente** usando el formato [Fuente X] al final de la frase.

3. Al final de la respuesta, bajo el encabezado 'Fuentes Utilizadas:', lista todas las fuentes citadas.

Contexto Recuperado:

---

{contexto}

---

Fuentes a Listar:

---

{sources_text}

---

"""
                prompt = query_input.query
            else:
                # Lógica Rápida (Para modo veloz, sin citación)
                SYSTEM_PROMPT = f"""Eres Codex Trader, un experto financiero. Responde a la pregunta basándote ÚNICAMENTE en el contexto. Sé extremadamente conciso (3-4 párrafos máximo).

Contexto:

---

{contexto}

---

"""
                prompt = query_input.query
        
        # Verificar si hay chunks recuperados antes de llamar a LiteLLM
        # Los saludos no necesitan chunks, así que se procesan normalmente
        logger.info(f"🔍 Verificando chunks: retrieved_chunks={len(retrieved_chunks) if retrieved_chunks else 0}, is_greeting={is_greeting}")
        logger.info(f"🔍 [DEBUG] CONDICIÓN: retrieved_chunks={bool(retrieved_chunks)}, is_greeting={is_greeting}, resultado={bool(retrieved_chunks) or is_greeting}")
        if retrieved_chunks or is_greeting:
            logger.info("✅ Procediendo con llamada a LiteLLM")
            logger.info(f"🔍 [DEBUG] contexto que se usará en prompt: {len(contexto) if contexto else 0} caracteres")
            # Ejecutar la consulta usando LiteLLM con Deepseek
            # Usar el modelo configurado al inicio (ya tiene prioridad: CHAT_MODEL > Deepseek > OpenAI)
            chat_model = modelo_por_defecto
            if not chat_model:
                # Fallback de seguridad (no debería llegar aquí)
                if DEEPSEEK_API_KEY:
                    chat_model = "deepseek/deepseek-chat"  # Formato correcto para LiteLLM
                else:
                    chat_model = "gpt-3.5-turbo"
            
            # REGLA CRÍTICA SOBRE SALUDOS (máxima prioridad, se aplica antes de RAG y modo de respuesta)
        greetings_instruction = """

REGLA CRÍTICA SOBRE SALUDOS (OBEDECE ESTO SIEMPRE):

1. Si el mensaje del usuario es SOLO un saludo o algo social muy corto,

   por ejemplo en español:
   - "hola"
   - "buenas"
   - "buen día"
   - "qué tal"
   - "hey"
   - "saludos"
   - "hola, qué tal"
   - o variaciones similares con o sin emojis,

   o en inglés:
   - "hi"
   - "hello"
   - "hey"
   - "good morning"
   - "good afternoon"
   - "good evening"
   - "what's up"
   - "hi there"
   - "hello there"
   - "hey there"
   - "good day"
   - o variaciones similares con o sin emojis,

   Y NO contiene ninguna palabra relacionada con trading, mercados, dinero, estrategia, gestión de riesgo, análisis, etc.,

   ENTONCES:

   - NO uses el contexto de RAG.
   - NO generes una explicación larga.
   - NO uses encabezados, ni listas, ni markdown complejo.

   En esos casos, responde SOLO con:

   - 1 o 2 frases muy cortas:

     *Primero*, un saludo amable.

     *Segundo*, una frase diciendo en qué puedes ayudar (trading, gestión de riesgo, psicología, estrategias).

     Y termina con una pregunta breve invitando a que el usuario formule su duda.

   Ejemplo de estilo:

     Usuario: "hola"

     Asistente: "¡Hola! Soy Codex Trader, tu asistente de IA especializado en trading. 

     Puedo ayudarte con gestión de riesgo, análisis técnico, psicología del trader y diseño de estrategias. 

     ¿Sobre qué tema de trading te gustaría que empecemos?"

2. Si el mensaje del usuario incluye ya alguna pregunta o tema de trading

   (por ejemplo: "hola, explícame gestión de riesgo" o "hola, qué es el day trading"),

   ENTONCES:

   - Trátalo como una pregunta normal de trading.

   - Aplica el modo de respuesta (Rápida o Estudio profundo) según corresponda.
"""
        
        # Construir instrucción de modo de respuesta según el modo seleccionado
        response_mode = query_input.response_mode or 'fast'
        if response_mode == 'fast':
            mode_instruction = """

═══════════════════════════════════════════════════════════════
MODO: RESPUESTA RÁPIDA (OBLIGATORIO - RESPETA ESTO ESTRICTAMENTE)
═══════════════════════════════════════════════════════════════

RESPUESTA MÁXIMA: 1-2 PÁRRAFOS CORTOS. NADA MÁS.

REGLAS ESTRICTAS:
- Máximo 1-2 párrafos cortos (3-5 oraciones cada uno)
- Ve directo al punto, sin introducciones largas
- NO uses encabezados (##, ###)
- NO uses listas de viñetas extensas
- NO des ejemplos detallados
- NO expliques conceptos secundarios
- Si la pregunta es amplia, menciona solo las ideas principales
- Al final, puedes mencionar brevemente que el usuario puede pedir más detalles si lo desea

EJEMPLO DE LONGITUD CORRECTA:
"La gestión de riesgo es fundamental en trading. Consiste en limitar las pérdidas potenciales usando stop loss y calculando el tamaño de posición según tu capital disponible. Nunca arriesgues más del 1-2% de tu cuenta por operación."

Si excedes 2 párrafos, estás violando el modo Rápida.
"""
        else:  # 'deep'
            mode_instruction = """

═══════════════════════════════════════════════════════════════
MODO: ESTUDIO PROFUNDO (OBLIGATORIO - RESPETA ESTO ESTRICTAMENTE)
═══════════════════════════════════════════════════════════════

RESPUESTA MÍNIMA: 5+ PÁRRAFOS O MÁS. DESARROLLA COMPLETAMENTE.

REGLAS ESTRICTAS:
- Mínimo 5 párrafos, preferiblemente más
- Primero: RESUMEN en 3-5 viñetas con las ideas clave
- Después: DESARROLLO COMPLETO con secciones y subtítulos (usa ##, ###)
- Incluye ejemplos prácticos y casos de uso
- Explica conceptos relacionados y contexto
- Estructura con: Introducción → Desarrollo → Ejemplos → Conclusiones
- Sé exhaustivo pero claro
- Usa markdown para organizar: encabezados, listas, negritas

EJEMPLO DE ESTRUCTURA:
## Resumen de Ideas Clave
- Idea 1
- Idea 2
- Idea 3

## Desarrollo Completo

### Subtema 1
[Párrafo 1: Explicación detallada...]
[Párrafo 2: Ejemplos y casos...]

### Subtema 2
[Párrafo 3: Más detalles...]
[Párrafo 4: Aplicaciones prácticas...]

### Subtema 3
[Párrafo 5: Conclusiones y recomendaciones...]

Si tienes menos de 5 párrafos, estás violando el modo Estudio Profundo.
"""
        
        # Construir el system_prompt según si es saludo o no
        # Si SYSTEM_PROMPT ya está definido (modo Estudio Profundo con citación), usarlo directamente
        if SYSTEM_PROMPT:
            system_prompt = SYSTEM_PROMPT
            # Ajustar max_tokens para modo Estudio Profundo
            max_tokens = 4000  # Más tokens para respuestas largas con citación
        elif is_greeting:
            # Para saludos: system prompt simple y directo, SIN modo de respuesta
            system_prompt = """Eres CODEX TRADER, un asistente de IA especializado en trading.

INSTRUCCIONES PARA SALUDOS:
- Responde SOLO con 1-2 frases muy cortas
- Saluda amablemente
- Menciona brevemente en qué puedes ayudar (trading, gestión de riesgo, psicología, estrategias)
- Termina con una pregunta breve invitando al usuario a formular su duda
- NO uses encabezados, ni listas, ni markdown
- NO des explicaciones largas

Ejemplo: "¡Hola! Soy Codex Trader, tu asistente de IA especializado en trading. Puedo ayudarte con gestión de riesgo, análisis técnico, psicología del trader y diseño de estrategias. ¿Sobre qué tema de trading te gustaría que empecemos?"

Responde siempre en español."""
            # Para saludos, limitar tokens a 100 para forzar respuestas cortas
            max_tokens = 100
        else:
            # Para preguntas normales: system prompt completo con modo de respuesta
            system_prompt = config.ASSISTANT_DESCRIPTION + '\n\n' + greetings_instruction + '\n\n' + mode_instruction
            # Ajustar max_tokens según el modo
            if response_mode == 'fast':
                max_tokens = 300  # Limitar tokens para forzar respuestas cortas (1-2 párrafos)
            else:  # 'deep'
                max_tokens = 4000  # Más tokens para respuestas largas (5+ párrafos)
        
        # Preparar parámetros para LiteLLM
        litellm_params = {
            "model": chat_model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": config.MODEL_TEMPERATURE,
            "max_tokens": max_tokens
        }
        
        # Configurar la API key según el modelo ANTES de hacer la llamada
        # Esto asegura que LiteLLM tenga la key correcta
        
        # Configurar la API key según el modelo
        # LiteLLM detecta automáticamente las API keys desde variables de entorno,
        # pero podemos configurarlas explícitamente si es necesario
        if chat_model.startswith("deepseek") or "deepseek" in chat_model.lower():
            if DEEPSEEK_API_KEY:
                litellm_params["api_key"] = DEEPSEEK_API_KEY
                print(f"✓ API Key de Deepseek configurada")
            else:
                raise HTTPException(
                    status_code=500,
                    detail="DEEPSEEK_API_KEY no está configurada pero se intentó usar Deepseek"
                )
        elif chat_model.startswith("claude") or "anthropic" in chat_model.lower():
            if ANTHROPIC_API_KEY:
                litellm_params["api_key"] = ANTHROPIC_API_KEY
                print(f"✓ API Key de Anthropic (Claude) configurada")
            # LiteLLM también puede usar ANTHROPIC_API_KEY desde variables de entorno
        elif chat_model.startswith("gemini") or "google" in chat_model.lower():
            if GOOGLE_API_KEY:
                litellm_params["api_key"] = GOOGLE_API_KEY
                print(f"✓ API Key de Google (Gemini) configurada")
            # LiteLLM también puede usar GOOGLE_API_KEY desde variables de entorno
        elif chat_model.startswith("command") or "cohere" in chat_model.lower():
            if COHERE_API_KEY:
                litellm_params["api_key"] = COHERE_API_KEY
                print(f"✓ API Key de Cohere configurada")
            # LiteLLM también puede usar COHERE_API_KEY desde variables de entorno
        elif chat_model.startswith("gpt") or "openai" in chat_model.lower():
            if not OPENAI_API_KEY:
                raise HTTPException(
                    status_code=500,
                    detail="OPENAI_API_KEY no está configurada pero se intentó usar OpenAI/ChatGPT"
                )
            # Asegurar que la API key esté en las variables de entorno
            os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
            # También pasarla explícitamente en los parámetros
            litellm_params["api_key"] = OPENAI_API_KEY
            print(f"✓ API Key de OpenAI configurada para {chat_model}")
        # Para otros modelos, LiteLLM intentará detectar la API key automáticamente
        
        # Log para debugging (solo mostrar primeros caracteres de la query)
        logger.info(f"📤 Enviando consulta a {chat_model} (query: {query_input.query[:50]}...)")
        
        try:
            response = litellm.completion(**litellm_params)
            logger.info(f"✓ Respuesta recibida de {chat_model}")
        except Exception as e:
            logger.error(f"❌ Error en llamada a LiteLLM: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al generar respuesta con LiteLLM: {str(e)}"
            )
        
        # Obtener la respuesta y los tokens usados
        if not response or not response.choices or len(response.choices) == 0:
            logger.error("❌ Respuesta de LiteLLM vacía o sin choices")
            respuesta_texto = "Lo siento, hubo un error al generar la respuesta. Por favor, intenta nuevamente."
        else:
            respuesta_texto = response.choices[0].message.content
            if not respuesta_texto or respuesta_texto.strip() == "":
                logger.warning("⚠️ Respuesta de LiteLLM está vacía")
                respuesta_texto = "Lo siento, no pude generar una respuesta. Por favor, intenta reformular tu pregunta."
            else:
                logger.info(f"✅ Respuesta generada: {len(respuesta_texto)} caracteres")
                
                # Añadir la lista de fuentes al final de la respuesta si es modo "Estudio Profundo"
                is_deep_mode = query_input.response_mode and (
                    query_input.response_mode.lower() == 'deep' or 
                    query_input.response_mode.lower() == 'estudio profundo' or
                    query_input.response_mode.lower() == 'profundo'
                )
                
                if is_deep_mode and citation_list:
                    respuesta_texto += "\n\n---\n**FUENTES DETALLADAS**:\n" + citation_list
                    logger.info(f"📚 Lista de fuentes añadida a la respuesta: {len(citation_list)} caracteres")
        
        # Extraer información detallada de uso de tokens de LiteLLM
        usage = response.usage if hasattr(response, 'usage') else None
        
        # Inicializar variables de tokens
        input_tokens = 0
        output_tokens = 0
        total_tokens_usados = 0
        
        if usage:
            # LiteLLM puede devolver usage como objeto o dict
            if isinstance(usage, dict):
                # Si es un diccionario
                input_tokens = usage.get('prompt_tokens', usage.get('input_tokens', 0))
                output_tokens = usage.get('completion_tokens', usage.get('output_tokens', 0))
                total_tokens_usados = usage.get('total_tokens', 0)
            else:
                # Si es un objeto
                if hasattr(usage, 'prompt_tokens'):
                    input_tokens = usage.prompt_tokens
                elif hasattr(usage, 'input_tokens'):
                    input_tokens = usage.input_tokens
                
                if hasattr(usage, 'completion_tokens'):
                    output_tokens = usage.completion_tokens
                elif hasattr(usage, 'output_tokens'):
                    output_tokens = usage.output_tokens
                
                if hasattr(usage, 'total_tokens'):
                    total_tokens_usados = usage.total_tokens
            
            # Si total_tokens_usados es 0 pero tenemos input y output, calcularlo
            if total_tokens_usados == 0 and (input_tokens > 0 or output_tokens > 0):
                total_tokens_usados = input_tokens + output_tokens
        
        # Si no se pudieron obtener los tokens, usar un estimado basado en la longitud
        if total_tokens_usados == 0:
            # Estimación aproximada: 1 token ≈ 4 caracteres
            input_tokens = len(prompt) // 4
            output_tokens = len(respuesta_texto) // 4
            total_tokens_usados = max(100, input_tokens + output_tokens)
            print(f"⚠ No se pudo obtener usage de LiteLLM, usando estimación")
        
        # IMPORTANTE: Registrar uso del modelo para monitoreo de costos
        # Esta llamada es no-bloqueante y no afecta el flujo principal si falla
        try:
            from lib.model_usage import log_model_usage_from_response
            log_model_usage_from_response(
                user_id=str(user_id),
                model=chat_model,
                tokens_input=input_tokens,
                tokens_output=output_tokens
            )
        except Exception as e:
            # No es crítico si falla el logging, solo registrar el error
            print(f"WARNING: Error al registrar uso de modelo (no critico): {e}")
        
        # Loggear información detallada de tokens y costos
        print("=" * 60)
        print(f"[INFO] Consulta procesada:")
        print(f"  Modelo: {chat_model}")
        print(f"  Input tokens: {input_tokens}")
        print(f"  Output tokens: {output_tokens}")
        print(f"  Total tokens: {total_tokens_usados}")
        print(f"  Tokens restantes antes: {tokens_restantes}")
        print("=" * 60)
        
        # Usar total_tokens_usados para el descuento (mantener compatibilidad)
        tokens_usados = total_tokens_usados
        
        # Paso B: Calcular nuevos tokens antes de guardar el log
        nuevos_tokens = tokens_restantes - tokens_usados
    
        # Guardar log de tokens en archivo para consulta posterior
        try:
            from datetime import datetime
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": str(user_id),
                "model": chat_model,
                "query_preview": query_input.query[:50] + "..." if len(query_input.query) > 50 else query_input.query,
                "response_mode": response_mode,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens_usados,
                "tokens_antes": tokens_restantes,
                "tokens_despues": nuevos_tokens
            }
            
            # Guardar en archivo JSON (append)
            import json
            log_file = "tokens_log.json"
            log_data = []
            
            # Leer logs existentes si el archivo existe
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_data = json.load(f)
                except:
                    log_data = []
            
            # Agregar nuevo log (mantener solo los últimos 100)
            log_data.append(log_entry)
            if len(log_data) > 100:
                log_data = log_data[-100:]
            
            # Guardar
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            # Si falla el logging, no es crítico, solo imprimir error
            print(f"⚠ No se pudo guardar log de tokens: {e}")
        
        # Paso C: Descontar tokens de la base de datos y verificar uso justo
    
        # IMPORTANTE: Lógica de uso justo (Fair Use)
        # Obtener información del perfil para calcular porcentaje de uso
        # Manejar el caso cuando las columnas no existen (compatibilidad con esquemas antiguos)
        update_data = {
            "tokens_restantes": nuevos_tokens
        }
        
        try:
            profile_fair_use = supabase_client.table("profiles").select(
                "tokens_monthly_limit, fair_use_warning_shown, fair_use_discount_eligible, fair_use_discount_used"
            ).eq("id", user_id).execute()
            
            if profile_fair_use.data:
                profile = profile_fair_use.data[0]
                tokens_monthly_limit = profile.get("tokens_monthly_limit") or 0
                
                if tokens_monthly_limit > 0:
                    # Calcular porcentaje de uso
                    tokens_usados_total = tokens_monthly_limit - nuevos_tokens
                    usage_percent = (tokens_usados_total / tokens_monthly_limit) * 100
                    
                    # Aviso suave al 80% de uso
                    if usage_percent >= 80 and not profile.get("fair_use_warning_shown", False):
                        update_data["fair_use_warning_shown"] = True
                        print(f"WARNING: Usuario {user_id} alcanzo 80% de uso ({usage_percent:.1f}%)")
                        
                        # Enviar email al admin cuando se alcanza el 80%
                        try:
                            from lib.email import send_admin_email
                            from datetime import datetime
                            import threading
                            
                            # Obtener email del usuario
                            user_email_response = supabase_client.table("profiles").select("email, current_plan").eq("id", user_id).execute()
                            user_email = user_email_response.data[0].get("email") if user_email_response.data else None
                            current_plan = user_email_response.data[0].get("current_plan", "N/A") if user_email_response.data else "N/A"
                            
                            def send_admin_80_percent_email():
                                try:
                                    admin_html = f"""
                                    <html>
                                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                        <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                                            <h2 style="color: white; margin: 0; font-size: 24px;">⚠️ Alerta: Usuario alcanzó 80% de límite</h2>
                                        </div>
                                        
                                        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                            <p style="font-size: 16px; margin-bottom: 20px;">
                                                Un usuario ha alcanzado el <strong>80% de su límite mensual de tokens</strong>.
                                            </p>
                                            
                                            <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                                                <ul style="list-style: none; padding: 0; margin: 0;">
                                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                        <strong style="color: #92400e;">Email del usuario:</strong> 
                                                        <span style="color: #333;">{user_email or 'N/A'}</span>
                                                    </li>
                                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                        <strong style="color: #92400e;">ID de usuario:</strong> 
                                                        <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                                    </li>
                                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                        <strong style="color: #92400e;">Plan actual:</strong> 
                                                        <span style="color: #333;">{current_plan}</span>
                                                    </li>
                                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                        <strong style="color: #92400e;">Límite mensual:</strong> 
                                                        <span style="color: #333;">{tokens_monthly_limit:,} tokens</span>
                                                    </li>
                                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                        <strong style="color: #92400e;">Tokens restantes:</strong> 
                                                        <span style="color: #333;">{nuevos_tokens:,} tokens</span>
                                                    </li>
                                                    <li style="margin-bottom: 0;">
                                                        <strong style="color: #92400e;">Porcentaje usado:</strong> 
                                                        <span style="color: #d97706; font-weight: bold; font-size: 18px;">{usage_percent:.1f}%</span>
                                                    </li>
                                                </ul>
                                            </div>
                                            
                                            <p style="font-size: 14px; color: #666; margin-top: 20px;">
                                                <strong>Nota:</strong> El usuario recibirá un aviso suave. Si alcanza el 90%, será elegible para un descuento del 20%.
                                            </p>
                                            
                                            <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                                Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                                            </p>
                                        </div>
                                    </body>
                                    </html>
                                    """
                                    send_admin_email("⚠️ Alerta: Usuario alcanzó 80% de límite de tokens", admin_html)
                                except Exception as e:
                                    print(f"⚠️ Error al enviar email al admin por 80% de uso: {e}")
                            
                            admin_thread = threading.Thread(target=send_admin_80_percent_email, daemon=True)
                            admin_thread.start()
                        except Exception as e:
                            print(f"⚠️ Error al preparar email al admin por 80% de uso: {e}")
                    
                    # Elegibilidad para descuento al 90% de uso
                    if usage_percent >= 90 and not profile.get("fair_use_discount_eligible", False):
                        from datetime import datetime
                        update_data["fair_use_discount_eligible"] = True
                        update_data["fair_use_discount_eligible_at"] = datetime.utcnow().isoformat()
                        print(f"🔔 Usuario {user_id} alcanzó 90% de uso ({usage_percent:.1f}%) - Elegible para descuento del 20%")
                        
                        # Enviar email de alerta al 90% (solo una vez)
                        if not profile.get("fair_use_email_sent", False):
                            try:
                                # Obtener email del usuario
                                user_email_response = supabase_client.table("profiles").select("email").eq("id", user_id).execute()
                                user_email = user_email_response.data[0].get("email") if user_email_response.data else None
                                
                                if user_email:
                                    # Obtener información del plan
                                    plan_name = "tu plan actual"
                                    current_plan_code_for_email = None
                                    if profile_fair_use.data:
                                        current_plan_code_for_email = profile_fair_use.data[0].get("current_plan")
                                        if current_plan_code_for_email:
                                            from plans import get_plan_by_code
                                            plan_info = get_plan_by_code(current_plan_code_for_email)
                                            if plan_info:
                                                plan_name = plan_info.name
                                    
                                    # Guardar variables para usar en el thread
                                    plan_code_for_thread = current_plan_code_for_email
                                    plan_name_for_thread = plan_name
                                    
                                    # Enviar email en background (no bloquea)
                                    import threading
                                    def send_90_percent_email_background():
                                        try:
                                            from lib.email import send_email
                                            from plans import get_plan_by_code, CODEX_PLANS
                                            import os
                                            
                                            # Construir URL de planes antes del f-string
                                            frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                                            planes_url = f"{frontend_url.rstrip('/')}/planes"
                                            
                                            # Determinar plan sugerido
                                            suggested_plan_code = "trader"
                                            if plan_code_for_thread:
                                                current_plan_index = next((i for i, p in enumerate(CODEX_PLANS) if p.code == plan_code_for_thread), -1)
                                                if current_plan_index >= 0 and current_plan_index < len(CODEX_PLANS) - 1:
                                                    suggested_plan_code = CODEX_PLANS[current_plan_index + 1].code
                                            
                                            suggested_plan = get_plan_by_code(suggested_plan_code)
                                            suggested_plan_name = suggested_plan.name if suggested_plan else "Trader"
                                            
                                            # Template de email atractivo
                                            email_html = f"""
                                            <!DOCTYPE html>
                                            <html>
                                            <head>
                                                <meta charset="UTF-8">
                                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                                                <style>
                                                    body {{
                                                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                                                        line-height: 1.6;
                                                        color: #333;
                                                        max-width: 600px;
                                                        margin: 0 auto;
                                                        padding: 20px;
                                                        background-color: #f4f4f4;
                                                    }}
                                                    .container {{
                                                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                                        border-radius: 12px;
                                                        padding: 30px;
                                                        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                                                    }}
                                                    .content {{
                                                        background: white;
                                                        border-radius: 8px;
                                                        padding: 30px;
                                                        margin-top: 20px;
                                                    }}
                                                    .header {{
                                                        text-align: center;
                                                        color: white;
                                                        margin-bottom: 20px;
                                                    }}
                                                    .header h1 {{
                                                        margin: 0;
                                                        font-size: 28px;
                                                        font-weight: bold;
                                                    }}
                                                    .alert-badge {{
                                                        background: #ff6b6b;
                                                        color: white;
                                                        padding: 12px 24px;
                                                        border-radius: 25px;
                                                        display: inline-block;
                                                        font-weight: bold;
                                                        font-size: 16px;
                                                        margin: 20px 0;
                                                    }}
                                                    .discount-box {{
                                                        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                                                        color: white;
                                                        padding: 25px;
                                                        border-radius: 10px;
                                                        text-align: center;
                                                        margin: 25px 0;
                                                        box-shadow: 0 5px 15px rgba(245, 87, 108, 0.3);
                                                    }}
                                                    .discount-box h2 {{
                                                        margin: 0 0 10px 0;
                                                        font-size: 32px;
                                                        font-weight: bold;
                                                    }}
                                                    .discount-box p {{
                                                        margin: 5px 0;
                                                        font-size: 18px;
                                                    }}
                                                    .coupon-code {{
                                                        background: white;
                                                        color: #f5576c;
                                                        padding: 15px 30px;
                                                        border-radius: 8px;
                                                        font-size: 24px;
                                                        font-weight: bold;
                                                        letter-spacing: 3px;
                                                        margin: 15px 0;
                                                        display: inline-block;
                                                    }}
                                                    .button {{
                                                        display: inline-block;
                                                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                                        color: white;
                                                        padding: 15px 40px;
                                                        text-decoration: none;
                                                        border-radius: 8px;
                                                        font-weight: bold;
                                                        font-size: 18px;
                                                        margin: 20px 0;
                                                        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
                                                        transition: transform 0.2s;
                                                    }}
                                                    .button:hover {{
                                                        transform: translateY(-2px);
                                                    }}
                                                    .stats {{
                                                        background: #f8f9fa;
                                                        padding: 20px;
                                                        border-radius: 8px;
                                                        margin: 20px 0;
                                                        border-left: 4px solid #667eea;
                                                    }}
                                                    .stats p {{
                                                        margin: 8px 0;
                                                        font-size: 16px;
                                                    }}
                                                    .footer {{
                                                        text-align: center;
                                                        color: #666;
                                                        font-size: 12px;
                                                        margin-top: 30px;
                                                        padding-top: 20px;
                                                        border-top: 1px solid #eee;
                                                    }}
                                                </style>
                                            </head>
                                            <body>
                                                <div class="container">
                                                    <div class="header">
                                                        <h1>🚨 Alerta de Uso</h1>
                                                    </div>
                                                    <div class="content">
                                                        <div style="text-align: center;">
                                                            <div class="alert-badge">Has alcanzado el 90% de tu límite</div>
                                                        </div>
                                                        
                                                        <h2 style="color: #333; margin-top: 30px;">¡Hola! 👋</h2>
                                                        <p style="color: #555; font-size: 16px;">
                                                            Te escribimos porque has usado aproximadamente <strong>{usage_percent:.1f}%</strong> de los tokens disponibles en tu plan <strong>{plan_name_for_thread}</strong>.
                                                        </p>
                                                        
                                                        <div class="stats">
                                                            <p><strong>📊 Tu uso actual:</strong></p>
                                                            <p>Tokens restantes: <strong>{nuevos_tokens:,}</strong> de <strong>{tokens_monthly_limit:,}</strong></p>
                                                            <p>Porcentaje usado: <strong>{usage_percent:.1f}%</strong></p>
                                                        </div>
                                                        
                                                        <div class="discount-box">
                                                            <h2>🎁 ¡Descuento Especial del 20%!</h2>
                                                            <p>Como agradecimiento por ser parte de Codex Trader, te ofrecemos un <strong>20% de descuento</strong> para que puedas:</p>
                                                            <ul style="text-align: left; display: inline-block; margin: 15px 0;">
                                                                <li>Subir a un plan superior con más tokens</li>
                                                                <li>Continuar usando Codex Trader sin interrupciones</li>
                                                                <li>Acceder a más análisis detallados</li>
                                                            </ul>
                                                            <div class="coupon-code">CUPON20</div>
                                                            <p style="font-size: 14px; margin-top: 10px;">Este cupón se aplicará automáticamente al hacer checkout</p>
                                                        </div>
                                                        
                                                        <div style="text-align: center; margin: 30px 0;">
                                                            <a href="{planes_url}" class="button">Ver Planes y Aprovechar Descuento</a>
                                                        </div>
                                                        
                                                        <p style="color: #666; font-size: 14px; margin-top: 30px;">
                                                            <strong>💡 Recomendación:</strong> Te sugerimos considerar el plan <strong>{suggested_plan_name}</strong> que te dará más tokens y acceso a más funcionalidades.
                                                        </p>
                                                        
                                                        <p style="color: #666; font-size: 14px;">
                                                            Si tienes alguna pregunta, no dudes en contactarnos. Estamos aquí para ayudarte.
                                                        </p>
                                                        
                                                        <div class="footer">
                                                            <p>Este es un email automático de Codex Trader</p>
                                                            <p>Si no reconoces este mensaje, puedes ignorarlo.</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </body>
                                            </html>
                                            """
                                            
                                            send_email(
                                                to=user_email,
                                                subject=f"🚨 Has alcanzado el 90% de tu límite - Descuento del 20% disponible",
                                                html=email_html
                                            )
                                            
                                            # Marcar que el email fue enviado
                                            supabase_client.table("profiles").update({
                                                "fair_use_email_sent": True
                                            }).eq("id", user_id).execute()
                                            
                                            print(f"✅ Email de alerta al 90% enviado a {user_email}")
                                            
                                            # IMPORTANTE: También enviar email al admin cuando se alcanza el 90%
                                            try:
                                                from lib.email import send_admin_email
                                                
                                                admin_html_90 = f"""
                                                <html>
                                                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                                    <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                                                        <h2 style="color: white; margin: 0; font-size: 24px;">🚨 ALERTA CRÍTICA: Usuario alcanzó 90% de límite</h2>
                                                    </div>
                                                    
                                                    <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                                            Un usuario ha alcanzado el <strong>90% de su límite mensual de tokens</strong>. Se le ha ofrecido un descuento del 20% para actualizar su plan.
                                                        </p>
                                                        
                                                        <div style="background: #fee2e2; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ef4444;">
                                                            <ul style="list-style: none; padding: 0; margin: 0;">
                                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                                    <strong style="color: #991b1b;">Email del usuario:</strong> 
                                                                    <span style="color: #333;">{user_email}</span>
                                                                </li>
                                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                                    <strong style="color: #991b1b;">ID de usuario:</strong> 
                                                                    <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                                                </li>
                                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                                    <strong style="color: #991b1b;">Plan actual:</strong> 
                                                                    <span style="color: #333;">{plan_name_for_thread}</span>
                                                                </li>
                                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                                    <strong style="color: #991b1b;">Límite mensual:</strong> 
                                                                    <span style="color: #333;">{tokens_monthly_limit:,} tokens</span>
                                                                </li>
                                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                                    <strong style="color: #991b1b;">Tokens restantes:</strong> 
                                                                    <span style="color: #333;">{nuevos_tokens:,} tokens</span>
                                                                </li>
                                                                <li style="margin-bottom: 0;">
                                                                    <strong style="color: #991b1b;">Porcentaje usado:</strong> 
                                                                    <span style="color: #dc2626; font-weight: bold; font-size: 20px;">{usage_percent:.1f}%</span>
                                                                </li>
                                                            </ul>
                                                        </div>
                                                        
                                                        <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin: 20px 0;">
                                                            <p style="margin: 0; font-size: 14px; color: #92400e;">
                                                                <strong>💡 Acción tomada:</strong> Se le ha enviado un email al usuario con un descuento del 20% para actualizar su plan. Plan sugerido: <strong>{suggested_plan_name}</strong>
                                                            </p>
                                                        </div>
                                                        
                                                        <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                                            Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                                                        </p>
                                                    </div>
                                                </body>
                                                </html>
                                                """
                                                send_admin_email("🚨 ALERTA CRÍTICA: Usuario alcanzó 90% de límite de tokens", admin_html_90)
                                                print(f"✅ Email de alerta al admin enviado por 90% de uso de usuario {user_id}")
                                            except Exception as admin_error:
                                                print(f"⚠️ Error al enviar email al admin por 90% de uso: {admin_error}")
                                        except Exception as e:
                                            print(f"⚠️ Error al enviar email de alerta al 90%: {e}")
                                    
                                    email_thread = threading.Thread(target=send_90_percent_email_background, daemon=True)
                                    email_thread.start()
                            except Exception as e:
                                print(f"⚠️ Error al preparar envío de email al 90%: {e}")
        except Exception as e:
            # Si las columnas no existen, continuar sin la lógica de uso justo
            # Verificar si es un error de columna no existente (código 42703) o tabla no encontrada (PGRST205)
            error_str = str(e)
            if "42703" in error_str or "PGRST205" in error_str or "does not exist" in error_str.lower():
                # Solo mostrar warning en modo debug, no en producción
                pass
            else:
                # Para otros errores, mostrar el warning
                logger.warning(f"Columnas de uso justo no disponibles (puede que no estén creadas): {e}")
            # Continuar sin actualizar campos de uso justo
        
        try:
            supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
            print(f"[INFO] Tokens descontados: {tokens_usados} tokens")
            print(f"[INFO] Tokens restantes después: {nuevos_tokens} tokens")
        except Exception as e:
            # Si falla la actualización, aún devolvemos la respuesta pero registramos el error
            print(f"ERROR: Error al actualizar tokens: {str(e)}")
        
        # Paso C: Crear o usar sesión de chat y guardar mensajes
        # conversation_id ya está inicializado al inicio de la función
        try:
            # Si no hay conversation_id, crear una nueva sesión
            if not conversation_id:
                # Crear nueva sesión de chat
                session_response = supabase_client.table("chat_sessions").insert({
                    "user_id": user_id,
                    "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
                }).execute()
                
                if session_response.data and len(session_response.data) > 0:
                    conversation_id = session_response.data[0]["id"]
                    print(f"[INFO] Nueva sesión de chat creada: {conversation_id}")
                else:
                    print(f"[WARN] No se pudo crear sesión de chat, continuando sin guardar historial")
            else:
                # Si hay conversation_id, verificar que existe y pertenece al usuario
                try:
                    session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
                    if not session_check.data:
                        # La sesión no existe o no pertenece al usuario, crear una nueva
                        print(f"[WARN] Sesión {conversation_id} no encontrada o no pertenece al usuario, creando nueva sesión")
                        session_response = supabase_client.table("chat_sessions").insert({
                            "user_id": user_id,
                            "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
                        }).execute()
                        if session_response.data and len(session_response.data) > 0:
                            conversation_id = session_response.data[0]["id"]
                except Exception as e:
                    print(f"[WARN] Error verificando sesión: {e}, creando nueva sesión")
                    session_response = supabase_client.table("chat_sessions").insert({
                        "user_id": user_id,
                        "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
                    }).execute()
                    if session_response.data and len(session_response.data) > 0:
                        conversation_id = session_response.data[0]["id"]
        except Exception as e:
            # Si la tabla no existe o hay error, continuar sin guardar historial
            print(f"[WARN] No se pudo guardar historial (puede que la tabla no exista aún): {str(e)}")
            import traceback
            traceback.print_exc()
        
        # Guardar mensajes si tenemos conversation_id
        if conversation_id:
            try:
                # Guardar mensaje del usuario
                supabase_client.table("conversations").insert({
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_role": "user",
                    "message_content": query_input.query,
                    "tokens_used": 0
                }).execute()
                
                # Guardar respuesta del asistente
                supabase_client.table("conversations").insert({
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_role": "assistant",
                    "message_content": respuesta_texto,
                    "tokens_used": tokens_usados
                }).execute()
                
                # Actualizar updated_at de la sesión (se hace automáticamente con el trigger, pero lo hacemos explícitamente también)
                supabase_client.table("chat_sessions").update({
                    "updated_at": "now()"
                }).eq("id", conversation_id).execute()
            except Exception as e:
                # Si la tabla no existe o hay error, continuar sin guardar historial
                print(f"[WARN] No se pudo guardar historial (puede que la tabla no exista aún): {str(e)}")
                import traceback
                traceback.print_exc()
        
            # Devolver la respuesta inmediatamente después de procesar exitosamente LiteLLM
            # Esto evita que el bloque else del fallback sobrescriba la respuesta
            logger.info(f"📤 Devolviendo respuesta exitosa: {len(respuesta_texto) if respuesta_texto else 0} caracteres, tokens_usados={tokens_usados}, conversation_id={conversation_id}")
            # NOTA: El return aquí termina la función, evitando que el else se ejecute
            return {
                "response": respuesta_texto,
                "tokens_usados": tokens_usados,
                "tokens_restantes": nuevos_tokens,
                "conversation_id": conversation_id
            }
        else:
            # Si no hay chunks recuperados y no es saludo, usar un prompt genérico
            logger.warning("⚠️ No se encontraron chunks en RAG. Respondiendo sin contexto específico.")
            respuesta_texto = "Lo siento, no pude encontrar información específica en la biblioteca para responder tu pregunta. Por favor, reformula tu consulta o intenta con términos más generales relacionados con trading."
            tokens_usados = 0
            nuevos_tokens = tokens_restantes
            # conversation_id ya está inicializado al inicio de la función
            logger.info(f"📤 Respuesta preparada (sin chunks): {len(respuesta_texto)} caracteres")
            
            # Devolver la respuesta con información de tokens y conversation_id
            logger.info(f"📤 Devolviendo respuesta: {len(respuesta_texto) if respuesta_texto else 0} caracteres, tokens_usados={tokens_usados}, conversation_id={conversation_id}")
            return {
                "response": respuesta_texto,
                "tokens_usados": tokens_usados,
                "tokens_restantes": nuevos_tokens,
                "conversation_id": conversation_id
            }
    
    except HTTPException:
        # Re-lanzar excepciones HTTP (como tokens agotados)
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al procesar consulta: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        # En lugar de devolver error 500, devolver una respuesta de error amigable
        return {
            "response": f"Lo siento, hubo un error al procesar tu consulta. Por favor, intenta nuevamente. Error: {error_msg[:100]}",
            "tokens_usados": 0,
            "tokens_restantes": 0,
            "conversation_id": None,
            "error": True
        }

# Endpoint raíz para verificar que el servidor está funcionando
@app.get("/")
async def root():
    return {
        "message": "Chat Bot API está funcionando",
        "status": "ready",
        "modelo_ia": modelo_por_defecto or "No configurado",
        "endpoints": {
            "chat": "/chat (POST) - Requiere autenticación",
            "tokens": "/tokens (GET) - Requiere autenticación",
            "tokens_reload": "/tokens/reload (POST) - Requiere autenticación",
            "tokens_reset": "/tokens/reset (POST) - Requiere autenticación",
            "chat_sessions": "/chat-sessions (GET) - Lista de sesiones de chat",
            "chat_sessions_messages": "/chat-sessions/{id}/messages (GET) - Mensajes de una sesión",
            "create_chat_session": "/chat-sessions (POST) - Crear nueva sesión",
            "delete_chat_session": "/chat-sessions/{id} (DELETE) - Eliminar sesión",
            "update_chat_session": "/chat-sessions/{id} (PATCH) - Actualizar título",
            "health": "/health (GET)",
            "docs": "/docs"
        }
    }

# Endpoint de salud
@app.get("/health")
async def health():
    return {"status": "healthy", "message": "El motor de chat está listo"}

# RUTA TEMPORAL DE EMERGENCIA - DESCARGAR TODO EL CÓDIGO COMO ZIP
# ⚠️ ESTA RUTA SE ELIMINARÁ AUTOMÁTICAMENTE DESPUÉS DE SER USADA
_emergency_route_used = False  # Flag para controlar si la ruta ya fue usada

@app.get("/download-emergency-xyz789")
async def download_emergency_code():
    """
    Ruta temporal de emergencia para descargar todo el código del proyecto como archivo ZIP.
    Esta ruta se eliminará automáticamente después de ser usada una vez.
    """
    global _emergency_route_used
    
    # Verificar si la ruta ya fue usada
    if _emergency_route_used:
        raise HTTPException(status_code=404, detail="Ruta temporal ya fue eliminada")
    
    try:
        logger.warning("⚠️ RUTA TEMPORAL DE EMERGENCIA ACCEDIDA - Generando ZIP con todo el código...")
        
        # Obtener el directorio raíz del proyecto
        project_root = Path(__file__).parent
        
        # Crear un buffer en memoria para el ZIP
        zip_buffer = io.BytesIO()
        
        # Leer .gitignore para excluir archivos
        gitignore_path = project_root / ".gitignore"
        ignore_patterns = []
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Convertir patrones de .gitignore a patrones de path
                        if line.endswith('/'):
                            ignore_patterns.append(line[:-1])
                        else:
                            ignore_patterns.append(line)
        
        # Función para verificar si un archivo debe ser ignorado
        def should_ignore(file_path: Path) -> bool:
            relative_path = file_path.relative_to(project_root)
            path_str = str(relative_path).replace('\\', '/')
            
            for pattern in ignore_patterns:
                # Patrón simple de coincidencia
                if pattern in path_str or path_str.startswith(pattern):
                    return True
                # Verificar si es un directorio completo
                if '/' in path_str:
                    parts = path_str.split('/')
                    if pattern in parts:
                        return True
            return False
        
        # Crear el archivo ZIP
        files_added = 0
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Recorrer todos los archivos del proyecto
            for root, dirs, files in os.walk(project_root):
                # Filtrar directorios a ignorar
                dirs[:] = [d for d in dirs if not should_ignore(Path(root) / d)]
                
                for file in files:
                    file_path = Path(root) / file
                    try:
                        # Verificar si el archivo debe ser ignorado
                        if should_ignore(file_path):
                            continue
                        
                        # Obtener la ruta relativa para el ZIP
                        relative_path = file_path.relative_to(project_root)
                        
                        # Leer y agregar el archivo al ZIP
                        try:
                            with open(file_path, 'rb') as f:
                                zip_file.writestr(str(relative_path), f.read())
                            files_added += 1
                        except (PermissionError, IOError) as e:
                            logger.warning(f"⚠️ No se pudo leer {relative_path}: {e}")
                            continue
                    except Exception as e:
                        logger.warning(f"⚠️ Error procesando {file_path}: {e}")
                        continue
        
        logger.info(f"✅ ZIP generado con {files_added} archivos")
        
        # Preparar la respuesta con el archivo ZIP
        zip_buffer.seek(0)
        zip_data = zip_buffer.read()
        
        # Crear respuesta con el archivo ZIP
        response = Response(
            content=zip_data,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=emergency-code-backup.zip",
                "Content-Length": str(len(zip_data))
            }
        )
        
        # ⚠️ DESHABILITAR LA RUTA DESPUÉS DE SERVIR EL ARCHIVO
        # Marcar la ruta como usada inmediatamente para evitar accesos concurrentes
        _emergency_route_used = True
        
        # Eliminar la ruta después de un breve delay para asegurar que la descarga comience
        async def disable_route_after_delay():
            await asyncio.sleep(3)  # Esperar 3 segundos para que la descarga comience
            try:
                # Intentar eliminar la ruta de la aplicación
                routes_to_remove = [route for route in app.routes if hasattr(route, 'path') and route.path == "/download-emergency-xyz789"]
                for route in routes_to_remove:
                    app.routes.remove(route)
                logger.warning("🗑️ RUTA TEMPORAL /download-emergency-xyz789 ELIMINADA DEL ROUTER")
            except Exception as e:
                logger.error(f"❌ Error al eliminar ruta temporal del router: {e}")
            finally:
                # Asegurar que el flag esté marcado incluso si falla la eliminación del router
                _emergency_route_used = True
        
        # Ejecutar la eliminación en segundo plano
        asyncio.create_task(disable_route_after_delay())
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Error al generar ZIP de emergencia: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al generar archivo ZIP: {str(e)}")

# Endpoint para consultar tokens restantes del usuario
@app.get("/tokens")
async def get_tokens(user = Depends(get_user)):
    """
    Endpoint para consultar los tokens restantes del usuario autenticado.
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Obteniendo tokens para usuario: {user_id}")
        
        # Usar el cliente global con SERVICE_KEY (las políticas RLS permiten service_role)
        try:
            profile_response = supabase_client.table("profiles").select("tokens_restantes, email").eq("id", user_id).execute()
        except Exception as db_error:
            error_msg = str(db_error)
            logger.error(f"❌ Error al consultar tabla 'profiles': {error_msg}")
            # Si la tabla no existe, retornar valores por defecto
            if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                logger.warning("⚠️ La tabla 'profiles' no existe. Retornando valores por defecto.")
                return {
                    "tokens_restantes": 0,
                    "email": user.email if hasattr(user, 'email') else ""
                }
            raise
        
        if not profile_response.data:
            logger.warning(f"⚠️ Perfil no encontrado para usuario: {user_id}")
            # En lugar de lanzar error 404, retornar valores por defecto
            # Esto permite que el frontend funcione aunque el perfil no exista aún
            logger.info(f"ℹ️ Retornando valores por defecto para usuario: {user_id}")
            return {
                "tokens_restantes": 0,
                "email": user.email if hasattr(user, 'email') else ""
            }
        
        tokens_restantes = profile_response.data[0].get("tokens_restantes", 0)
        email = profile_response.data[0].get("email", user.email if hasattr(user, 'email') else "")
        logger.info(f"✅ Tokens obtenidos: {tokens_restantes} para {email}")
        
        return {
            "tokens_restantes": tokens_restantes,
            "email": email
        }
    except HTTPException as http_ex:
        # Si es un error de autenticación (401), re-lanzarlo
        if http_ex.status_code == 401:
            raise
        # Para otros errores HTTP, retornar valores por defecto
        logger.warning(f"⚠️ Error HTTP {http_ex.status_code} en /tokens: {http_ex.detail}")
        return {
            "tokens_restantes": 0,
            "email": ""
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error en /tokens: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        
        # En lugar de lanzar error 500, retornar valores por defecto
        # Esto permite que el frontend funcione aunque haya problemas temporales
        logger.warning("⚠️ Retornando valores por defecto debido a error")
        try:
            return {
                "tokens_restantes": 0,
                "email": user.email if hasattr(user, 'email') else ""
            }
        except:
            return {
                "tokens_restantes": 0,
                "email": ""
            }

# Modelo para recargar tokens
class TokenReloadInput(BaseModel):
    cantidad: int

# Endpoint para recargar tokens
@app.post("/tokens/reload")
async def reload_tokens(token_input: TokenReloadInput, user = Depends(get_user)):
    """
    Endpoint para recargar tokens al perfil del usuario.
    Permite recargar incluso si los tokens están en negativo.
    """
    try:
        user_id = user.id
        
        if token_input.cantidad <= 0:
            raise HTTPException(
                status_code=400,
                detail="La cantidad debe ser mayor a 0"
            )
        
        # Obtener tokens actuales (pueden ser negativos)
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_actuales = profile_response.data[0]["tokens_restantes"]
        # Permitir recarga incluso con tokens negativos
        nuevos_tokens = tokens_actuales + token_input.cantidad
        
        # Si los tokens quedan negativos después de la recarga, establecer mínimo en 0
        # (opcional, puedes comentar esta línea si quieres permitir negativos)
        # nuevos_tokens = max(0, nuevos_tokens)
        
        # Actualizar tokens y resetear flag de email de recarga (para permitir nuevo email)
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": nuevos_tokens,
            "tokens_reload_email_sent": False  # Resetear flag para permitir nuevo email
        }).eq("id", user_id).execute()
        
        # Obtener email del usuario para enviar notificaciones
        user_email = user.email
        
        # IMPORTANTE: Enviar emails de notificación (admin y usuario) en segundo plano
        try:
            from lib.email import send_admin_email, send_email
            from datetime import datetime
            import threading
            
            # 1) EMAIL AL ADMIN: Notificación de recarga de tokens
            def send_admin_email_background():
                try:
                    admin_html = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                            <h2 style="color: white; margin: 0; font-size: 24px;">💰 Recarga de Tokens</h2>
                        </div>
                        
                        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                            <p style="font-size: 16px; margin-bottom: 20px;">
                                Un usuario ha recargado tokens en Codex Trader.
                            </p>
                            
                            <div style="background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                <ul style="list-style: none; padding: 0; margin: 0;">
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">Email del usuario:</strong> 
                                        <span style="color: #333;">{user_email}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">ID de usuario:</strong> 
                                        <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">Tokens anteriores:</strong> 
                                        <span style="color: #333;">{tokens_actuales:,}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">Tokens recargados:</strong> 
                                        <span style="color: #10b981; font-weight: bold;">+{token_input.cantidad:,}</span>
                                    </li>
                                    <li style="margin-bottom: 0;">
                                        <strong style="color: #2563eb;">Tokens totales ahora:</strong> 
                                        <span style="color: #333; font-weight: bold; font-size: 18px;">{nuevos_tokens:,}</span>
                                    </li>
                                </ul>
                            </div>
                            
                            <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                            </p>
                        </div>
                    </body>
                    </html>
                    """
                    send_admin_email("💰 Recarga de Tokens - Codex Trader", admin_html)
                except Exception as e:
                    print(f"⚠️ Error al enviar email al admin por recarga de tokens: {e}")
            
            # 2) EMAIL AL USUARIO: Confirmación de recarga
            def send_user_email_background():
                try:
                    if user_email:
                        # Verificar si ya se envió el email de confirmación de recarga (flag en base de datos)
                        try:
                            profile_check = supabase_client.table("profiles").select("tokens_reload_email_sent").eq("id", user_id).execute()
                            reload_email_already_sent = profile_check.data[0].get("tokens_reload_email_sent", False) if profile_check.data else False
                            
                            if reload_email_already_sent:
                                print(f"⚠️ Email de confirmación de recarga ya fue enviado anteriormente para {user_email}. Saltando envío.")
                                return
                        except Exception as check_error:
                            # Si falla la verificación, continuar con el envío (no crítico)
                            print(f"⚠️ Error al verificar flag tokens_reload_email_sent: {check_error}. Continuando con envío.")
                        
                        user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                        # Construir URL del app antes del f-string
                        import os
                        frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                        app_url = frontend_url.rstrip('/')  # Usar la raíz del sitio, no /app
                        
                        user_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h1 style="color: white; margin: 0; font-size: 28px;">✅ Tokens Recargados Exitosamente</h1>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Hola <strong>{user_name}</strong>,
                                </p>
                                
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Tu recarga de tokens se ha procesado correctamente.
                                </p>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; border-left: 4px solid #10b981; margin: 20px 0;">
                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                        <li style="margin-bottom: 10px; color: #333;">
                                            <strong>Tokens anteriores:</strong> {tokens_actuales:,}
                                        </li>
                                        <li style="margin-bottom: 10px; color: #333;">
                                            <strong>Tokens recargados:</strong> <span style="color: #10b981; font-weight: bold;">+{token_input.cantidad:,}</span>
                                        </li>
                                        <li style="margin-bottom: 0; color: #333;">
                                            <strong>Tokens totales ahora:</strong> <span style="color: #059669; font-weight: bold; font-size: 20px;">{nuevos_tokens:,}</span>
                                        </li>
                                    </ul>
                                </div>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{app_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                        🚀 Continuar usando Codex Trader
                                    </a>
                                </div>
                                
                                <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                    Si no realizaste esta recarga, por favor contáctanos respondiendo a este correo.
                                </p>
                            </div>
                        </body>
                        </html>
                        """
                        result = send_email(
                            to=user_email,
                            subject="✅ Tokens recargados exitosamente - Codex Trader",
                            html=user_html
                        )
                        
                        # Marcar flag en base de datos si el email se envió exitosamente
                        if result:
                            try:
                                supabase_client.table("profiles").update({
                                    "tokens_reload_email_sent": True
                                }).eq("id", user_id).execute()
                                print(f"✅ Flag tokens_reload_email_sent marcado en base de datos para {user_id}")
                            except Exception as flag_error:
                                print(f"⚠️ No se pudo marcar flag tokens_reload_email_sent: {flag_error} (no crítico)")
                except Exception as e:
                    print(f"⚠️ Error al enviar email al usuario por recarga de tokens: {e}")
            
            # Enviar emails en background threads
            admin_thread = threading.Thread(target=send_admin_email_background, daemon=True)
            admin_thread.start()
            
            user_thread = threading.Thread(target=send_user_email_background, daemon=True)
            user_thread.start()
            
        except Exception as email_error:
            # No es crítico si falla el email
            print(f"⚠️ Error al preparar envío de emails por recarga de tokens: {email_error}")
        
        return {
            "mensaje": f"Tokens recargados exitosamente",
            "tokens_anteriores": tokens_actuales,
            "tokens_recargados": token_input.cantidad,
            "tokens_totales": nuevos_tokens
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al recargar tokens: {str(e)}"
        )

# Endpoint de emergencia para resetear tokens (útil para desarrollo)
@app.post("/tokens/reset")
async def reset_tokens(
    user = Depends(get_user), 
    cantidad: int = Query(20000, description="Cantidad de tokens a establecer")
):
    """
    Endpoint de emergencia para resetear tokens a un valor específico.
    Útil cuando los tokens están en negativo y necesitas resetearlos.
    """
    try:
        user_id = user.id
        
        if cantidad < 0:
            raise HTTPException(
                status_code=400,
                detail="La cantidad debe ser mayor o igual a 0"
            )
        
        # Obtener perfil para verificar que existe
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_anteriores = profile_response.data[0]["tokens_restantes"]
        
        # Actualizar tokens directamente
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": cantidad
        }).eq("id", user_id).execute()
        
        return {
            "mensaje": f"Tokens reseteados exitosamente",
            "tokens_anteriores": tokens_anteriores,
            "tokens_totales": cantidad
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al resetear tokens: {str(e)}"
        )

# Endpoint para obtener lista de sesiones de chat
@app.get("/chat-sessions")
async def get_chat_sessions(user = Depends(get_user), limit: int = 50):
    """
    Endpoint para obtener la lista de sesiones de chat del usuario autenticado.
    Devuelve las sesiones ordenadas por fecha de actualización (más recientes primero).
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Obteniendo sesiones de chat para usuario: {user_id}")
        
        # Usar el cliente global con SERVICE_KEY (las políticas RLS permiten service_role)
        try:
            # Obtener sesiones de chat ordenadas por fecha de actualización (más recientes primero)
            sessions_response = supabase_client.table("chat_sessions").select(
                "id, title, created_at, updated_at"
            ).eq("user_id", user_id).order("updated_at", desc=True).limit(limit).execute()
        except Exception as db_error:
            error_msg = str(db_error)
            logger.error(f"❌ Error al consultar tabla 'chat_sessions': {error_msg}")
            # Si la tabla no existe, retornar lista vacía en lugar de error
            if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                logger.warning("⚠️ La tabla 'chat_sessions' no existe. Retornando lista vacía.")
                return {
                    "sessions": [],
                    "total": 0
                }
            raise
        
        if not sessions_response.data:
            logger.info(f"ℹ️ No hay sesiones para usuario: {user_id}")
            return {
                "sessions": [],
                "total": 0
            }
        
        logger.info(f"✅ Sesiones obtenidas: {len(sessions_response.data)} para usuario: {user_id}")
        
        return {
            "sessions": sessions_response.data,
            "total": len(sessions_response.data)
        }
    except HTTPException as http_ex:
        # Si es un error de autenticación (401), re-lanzarlo
        if http_ex.status_code == 401:
            raise
        # Para otros errores HTTP, retornar lista vacía
        logger.warning(f"⚠️ Error HTTP {http_ex.status_code} en /chat-sessions: {http_ex.detail}")
        return {
            "sessions": [],
            "total": 0
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error en /chat-sessions: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        # Si es un error de conexión a Supabase, dar mensaje más claro
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            logger.warning("⚠️ Error de conexión con Supabase. Retornando lista vacía.")
            return {
                "sessions": [],
                "total": 0
            }
        # Si la tabla no existe, retornar lista vacía en lugar de error
        if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
            logger.warning("⚠️ La tabla 'chat_sessions' no existe. Retornando lista vacía.")
            return {
                "sessions": [],
                "total": 0
            }
        # En lugar de devolver error 500, retornar lista vacía
        logger.warning("⚠️ Retornando lista vacía debido a error")
        return {
            "sessions": [],
            "total": 0
        }

# Endpoint para obtener mensajes de una conversación específica
@app.get("/chat-sessions/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str, user = Depends(get_user), limit: int = 100):
    """
    Endpoint para obtener los mensajes de una conversación específica.
    """
    try:
        user_id = user.id
        
        # Verificar que la conversación pertenezca al usuario
        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada o no pertenece al usuario"
            )
        
        # Obtener mensajes de la conversación ordenados por fecha de creación
        messages_response = supabase_client.table("conversations").select(
            "id, message_role, message_content, tokens_used, created_at"
        ).eq("conversation_id", conversation_id).eq("user_id", user_id).order("created_at", desc=False).limit(limit).execute()
        
        if not messages_response.data:
            return {
                "messages": [],
                "total": 0
            }
        
        return {
            "messages": messages_response.data,
            "total": len(messages_response.data)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener mensajes: {str(e)}"
        )

# Modelo para crear nueva conversación
class CreateChatSessionInput(BaseModel):
    title: Optional[str] = None

# Endpoint para crear una nueva conversación
@app.post("/chat-sessions")
async def create_chat_session(create_input: Optional[CreateChatSessionInput] = None, user = Depends(get_user)):
    """
    Endpoint para crear una nueva sesión de chat.
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Creando nueva sesión de chat para usuario: {user_id}")
        
        try:
            # Crear nueva sesión de chat
            new_session = supabase_client.table("chat_sessions").insert({
                "user_id": user_id,
                "title": create_input.title if create_input and create_input.title else "Nueva conversación"
            }).execute()
            
            if not new_session.data:
                logger.warning("⚠️ No se recibieron datos al crear sesión")
                # Retornar una sesión temporal en lugar de error
                import uuid
                return {
                    "session": {
                        "id": str(uuid.uuid4()),
                        "user_id": str(user_id),
                        "title": create_input.title if create_input and create_input.title else "Nueva conversación",
                        "created_at": None,
                        "updated_at": None
                    },
                    "message": "Sesión creada (temporal)"
                }
            
            logger.info(f"✅ Sesión creada exitosamente: {new_session.data[0]['id']}")
            return {
                "session": new_session.data[0],
                "message": "Conversación creada exitosamente"
            }
        except Exception as db_error:
            error_msg = str(db_error)
            logger.error(f"❌ Error al crear sesión en BD: {error_msg}")
            logger.error(f"❌ Traceback completo: {str(db_error)}", exc_info=True)
            # Retornar una sesión temporal en lugar de error 500
            import uuid
            return {
                "session": {
                    "id": str(uuid.uuid4()),
                    "user_id": str(user_id),
                    "title": create_input.title if create_input and create_input.title else "Nueva conversación",
                    "created_at": None,
                    "updated_at": None
                },
                "message": "Sesión creada (temporal debido a error en BD)"
            }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error general al crear conversación: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        # Retornar una sesión temporal en lugar de error 500
        import uuid
        return {
            "session": {
                "id": str(uuid.uuid4()),
                "user_id": str(user.id) if hasattr(user, 'id') else None,
                "title": "Nueva conversación",
                "created_at": None,
                "updated_at": None
            },
            "message": "Sesión creada (temporal debido a error)"
        }

# ============================================================================
# ENDPOINTS DE BILLING / STRIPE
# ============================================================================

# Modelo para crear checkout session
class CheckoutSessionInput(BaseModel):
    planCode: str  # 'explorer', 'trader', 'pro', 'institucional'

# Endpoint para crear una sesión de checkout de Stripe
# RUTA: POST /billing/create-checkout-session
# ARCHIVO: main.py (línea ~1050)
@app.post("/billing/create-checkout-session")
async def create_checkout_session(
    checkout_input: CheckoutSessionInput,
    request: Request,
    user = Depends(get_user)
):
    """
    Crea una sesión de checkout de Stripe para suscripciones.
    
    Recibe:
    - planCode: Código del plan ('explorer', 'trader', 'pro', 'institucional')
    
    Retorna:
    - url: URL de la sesión de checkout de Stripe para redirigir al usuario
    
    TODO: Asociar la sesión con el usuario logueado:
    - Agregar metadata a la Checkout Session con userId y email del usuario
    - Esto permitirá identificar al usuario cuando Stripe envíe el webhook
    """
    logger.info(f"🔔 Creando checkout session - Método: {request.method}, Plan: {checkout_input.planCode}, Usuario: {user.email}")
    
    if not STRIPE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Stripe no está configurado. Verifica las variables de entorno STRIPE_SECRET_KEY y los Price IDs."
        )
    
    try:
        # URL del frontend (usar la variable global ya configurada)
        # Asegurarse de que no tenga /app al final y eliminar cualquier /app si está presente
        frontend_base_url = FRONTEND_URL.rstrip('/')
        # Eliminar explícitamente /app si está al final
        if frontend_base_url.endswith('/app'):
            frontend_base_url = frontend_base_url[:-4]  # Eliminar '/app'
        frontend_base_url = frontend_base_url.rstrip('/')  # Asegurar que no termine en /
        
        # Normalizar: si la URL no tiene www pero el dominio es codextrader.tech, añadir www
        # Esto asegura consistencia con el dominio real
        if 'codextrader.tech' in frontend_base_url and 'www.' not in frontend_base_url:
            frontend_base_url = frontend_base_url.replace('https://codextrader.tech', 'https://www.codextrader.tech')
            frontend_base_url = frontend_base_url.replace('http://codextrader.tech', 'http://www.codextrader.tech')
        
        logger.info(f"🌐 FRONTEND_URL configurada: {FRONTEND_URL}, frontend_base_url procesada: {frontend_base_url}")
        
        plan_code = checkout_input.planCode.lower()
        
        # Validar que el código de plan sea válido
        if not is_valid_plan_code(plan_code):
            raise HTTPException(
                status_code=400,
                detail=f"Código de plan inválido: {plan_code}. Debe ser uno de: explorer, trader, pro, institucional"
            )
        
        # Obtener el Price ID de Stripe para el plan
        price_id = get_stripe_price_id(plan_code)
        if not price_id:
            raise HTTPException(
                status_code=500,
                detail=f"Price ID no configurado para el plan: {plan_code}. Verifica STRIPE_PRICE_ID_{plan_code.upper()} en .env"
            )
        
        # Obtener userId y email del usuario autenticado
        user_id = user.id
        user_email = user.email
        
        # IMPORTANTE: Verificar elegibilidad para descuento de uso justo (Fair Use)
        # Si el usuario es elegible y aún no ha usado el descuento, aplicar cupón automáticamente
        discounts = None
        from lib.stripe_config import STRIPE_FAIR_USE_COUPON_ID
        
        if STRIPE_FAIR_USE_COUPON_ID:
            try:
                # Intentar obtener información del perfil del usuario con columnas de fair use
                profile_response = supabase_client.table("profiles").select(
                    "fair_use_discount_eligible, fair_use_discount_used"
                ).eq("id", user_id).execute()
                
                if profile_response.data:
                    profile = profile_response.data[0]
                    fair_use_eligible = profile.get("fair_use_discount_eligible", False)
                    fair_use_used = profile.get("fair_use_discount_used", False)
                    
                    # Aplicar cupón si es elegible y aún no lo ha usado
                    if fair_use_eligible and not fair_use_used:
                        discounts = [{"coupon": STRIPE_FAIR_USE_COUPON_ID}]
                        logger.info(f"✅ Aplicando cupón de uso justo (20% OFF) para usuario {user_id}")
            except Exception as e:
                # Si las columnas no existen, simplemente no aplicar descuento
                error_msg = str(e)
                if "does not exist" in error_msg or "42703" in error_msg:
                    logger.warning(f"⚠️ Columnas de fair use no disponibles, omitiendo descuento: {error_msg[:100]}")
                else:
                    logger.warning(f"⚠️ Error al verificar elegibilidad de fair use: {error_msg[:100]}")
                # Continuar sin descuento
        
        metadata = {
            "user_id": user_id,
            "user_email": user_email,
            "plan_code": plan_code
        }
        
        # Si se aplicó descuento, agregarlo a metadata para tracking
        # IMPORTANTE: Marcar el descuento como usado ANTES de crear la sesión
        if discounts:
            metadata["fair_use_discount_applied"] = "true"
            try:
                # Marcar el descuento como usado inmediatamente
                supabase_client.table("profiles").update({
                    "fair_use_discount_used": True
                }).eq("id", user_id).execute()
                logger.info(f"✅ Descuento de uso justo marcado como usado para usuario {user_id}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo marcar descuento como usado (no crítico): {e}")
        
        # Asegurar que la URL de éxito apunte a la raíz (/) y no a /app
        success_url = f"{frontend_base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_base_url}/?checkout=cancelled"
        
        logger.info(f"🔗 URLs de checkout configuradas - Success: {success_url}, Cancel: {cancel_url}")
        
        # Crear la sesión de checkout de Stripe
        checkout_session_params = {
            "mode": "subscription",
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "customer_email": user_email,  # Pre-llenar el email del usuario
        }
        
        # Agregar descuentos solo si el usuario es elegible
        if discounts:
            checkout_session_params["discounts"] = discounts
        
        session = stripe.checkout.Session.create(**checkout_session_params)
        
        return {"url": session.url}
        
    except HTTPException:
        raise
    except Exception as e:
        # Verificar si es un error de Stripe (manejar sin stripe.error si no está disponible)
        error_type = type(e).__name__
        if 'Stripe' in error_type or 'stripe' in str(type(e)).lower():
            raise HTTPException(
                status_code=500,
                detail=f"Error de Stripe: {str(e)}"
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear sesión de checkout: {str(e)}"
        )

# Endpoint para recibir webhooks de Stripe
# RUTA: POST /billing/stripe-webhook
# IMPORTANTE: Este endpoint NO requiere autenticación normal, Stripe lo firma con webhook_secret
@app.post("/billing/stripe-webhook")
async def stripe_webhook(request: Request):
    logger.info("🔔 Webhook endpoint llamado")
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        # Verificar que el webhook secret esté configurado
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        if not webhook_secret:
            logger.error("❌ STRIPE_WEBHOOK_SECRET no está configurado")
            return JSONResponse(
                content={"status": "error", "message": "Webhook secret no configurado"},
                status_code=500
            )
        
        logger.info(f"🔐 Verificando firma del webhook...")
        
        # Verifica webhook
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        
        logger.info(f"✅ Webhook recibido y verificado: {event['type']}")
        
        # Procesa eventos
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            logger.info(f"🛒 Procesando checkout.session.completed para sesión: {session.get('id')}")
            # Llamar a la función que procesa el checkout y actualiza tokens
            await handle_checkout_session_completed(session)
        elif event["type"] == "invoice.paid":
            invoice = event["data"]["object"]
            logger.info(f"💰 Procesando invoice.paid para invoice: {invoice.get('id')}")
            # Llamar a la función que procesa la renovación mensual
            await handle_invoice_paid(invoice)
            
        return {"status": "success"}
        
    except Exception as e:
        # Verificar si es un error de firma de Stripe (puede no tener stripe.error en algunas versiones)
        error_type = type(e).__name__
        error_str = str(e).lower()
        if hasattr(stripe, 'error') and hasattr(stripe.error, 'SignatureVerificationError'):
            # Si stripe.error está disponible, verificar tipo específico
            if isinstance(e, stripe.error.SignatureVerificationError):
                logger.error(f"❌ Error de firma webhook: {e}")
                return JSONResponse(
                    content={"status": "invalid_signature"},
                    status_code=400
                )
        elif 'SignatureVerificationError' in error_type or ('signature' in error_str and 'webhook' in error_str):
            logger.error(f"❌ Error de firma webhook: {e}")
            return JSONResponse(
                content={"status": "invalid_signature"},
                status_code=400
            )
        
        logger.error(f"❌ Error webhook: {e}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )


async def handle_checkout_session_completed(session: dict):
    """
    Maneja el evento checkout.session.completed de Stripe.
    
    Actualiza en la base de datos:
    - stripe_customer_id: ID del cliente en Stripe
    - current_plan: Plan seleccionado desde metadata
    - current_period_end: Fecha de expiración de la suscripción
    
    IMPORTANTE: Este es el lugar donde se actualiza current_plan y stripe_customer_id
    después de que un usuario completa el checkout.
    """
    try:
        # Extraer información de la sesión
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_code = metadata.get("plan_code")
        
        if not user_id:
            print(f"⚠️ checkout.session.completed sin user_id en metadata: {session.get('id')}")
            return
        
        if not customer_id:
            print(f"⚠️ checkout.session.completed sin customer_id: {session.get('id')}")
            return
        
        # Obtener información de la suscripción para current_period_end
        current_period_end = None
        if subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(subscription_id)
                current_period_end = subscription.current_period_end
            except Exception as e:
                print(f"⚠️ Error al obtener suscripción {subscription_id}: {str(e)}")
        
        # Obtener información del plan para establecer tokens iniciales
        tokens_per_month = None
        plan = None
        if plan_code:
            from plans import get_plan_by_code
            plan = get_plan_by_code(plan_code)
            if plan:
                tokens_per_month = plan.tokens_per_month
                logger.info(f"✅ Plan encontrado: {plan_code} -> {tokens_per_month:,} tokens/mes")
            else:
                logger.error(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado en plans.py")
                print(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado. Los tokens NO se sumarán.")
        else:
            logger.error(f"❌ ERROR CRÍTICO: plan_code no está en metadata del checkout session")
            print(f"❌ ERROR CRÍTICO: plan_code no está en metadata. Session ID: {session.get('id')}")
            print(f"   Metadata disponible: {metadata}")
        
        # Preparar datos para actualizar
        # IMPORTANTE: Aquí se actualiza current_plan, stripe_customer_id y tokens en la tabla profiles
        # El frontend puede leer estos valores desde /app/billing o en el chat
        update_data = {
            "stripe_customer_id": customer_id,
        }
        
        if plan_code:
            update_data["current_plan"] = plan_code
            # Obtener tokens actuales del usuario para sumar en lugar de resetear
            try:
                profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
                current_tokens = 0
                if profile_response.data and profile_response.data[0].get("tokens_restantes") is not None:
                    current_tokens = profile_response.data[0]["tokens_restantes"]
                
                # Sumar tokens del nuevo plan a los tokens existentes
                if tokens_per_month:
                    new_tokens = current_tokens + tokens_per_month
                    update_data["tokens_restantes"] = new_tokens
                    logger.info(f"💰 Tokens sumados para usuario {user_id}: {current_tokens:,} + {tokens_per_month:,} = {new_tokens:,}")
                    print(f"💰 Tokens sumados para usuario {user_id}: {current_tokens:,} + {tokens_per_month:,} = {new_tokens:,}")
                    
                    # Actualizar tokens_monthly_limit con el máximo entre el límite actual y el nuevo plan
                    try:
                        current_limit = profile_response.data[0].get("tokens_monthly_limit", 0) if profile_response.data else 0
                        update_data["tokens_monthly_limit"] = max(current_limit, tokens_per_month)
                    except Exception as e:
                        logger.warning(f"No se pudo actualizar tokens_monthly_limit (columna puede no existir): {e}")
                    
                    # Resetear campos de uso justo solo si es la primera suscripción
                    if current_tokens == 0:
                        update_data["fair_use_warning_shown"] = False
                        update_data["fair_use_discount_eligible"] = False
                        update_data["fair_use_discount_used"] = False
                        update_data["fair_use_discount_eligible_at"] = None
                        update_data["fair_use_email_sent"] = False
                else:
                    # CRÍTICO: Si tokens_per_month es None, los tokens NO se sumarán
                    logger.error(f"❌ ERROR CRÍTICO: tokens_per_month es None para plan_code '{plan_code}'. Los tokens NO se sumarán.")
                    print(f"❌ ERROR CRÍTICO: tokens_per_month es None. Los tokens NO se actualizarán.")
                    print(f"   Esto puede ocurrir si:")
                    print(f"   1. El plan '{plan_code}' no existe en plans.py")
                    print(f"   2. El plan no tiene tokens_per_month definido")
            except Exception as e:
                logger.error(f"Error al obtener tokens actuales, usando tokens del plan directamente: {e}")
                print(f"⚠️ Error al obtener tokens actuales: {e}")
                # Fallback: usar tokens del plan si hay error
                if tokens_per_month:
                    update_data["tokens_restantes"] = tokens_per_month
                    logger.info(f"💰 Fallback: Tokens establecidos a {tokens_per_month:,} (sin sumar)")
                else:
                    logger.error(f"❌ ERROR: No se pueden establecer tokens porque tokens_per_month es None")
                    print(f"❌ ERROR: No se pueden establecer tokens porque tokens_per_month es None")
        
        # IMPORTANTE: Si el usuario usó el descuento de uso justo, marcarlo
        # Verificar en metadata si se aplicó el descuento
        if metadata.get("fair_use_discount_applied") == "true":
            # Verificar que el usuario tenía elegibilidad antes de marcar como usado
            profile_check = supabase_client.table("profiles").select(
                "fair_use_discount_eligible"
            ).eq("id", user_id).execute()
            
            if profile_check.data and profile_check.data[0].get("fair_use_discount_eligible", False):
                update_data["fair_use_discount_used"] = True
                print(f"✅ Descuento de uso justo marcado como usado para usuario {user_id}")
        
        if current_period_end:
            # Convertir timestamp de Unix a datetime ISO
            from datetime import datetime
            update_data["current_period_end"] = datetime.fromtimestamp(current_period_end).isoformat()
        
        # Actualizar el perfil del usuario
        logger.info(f"📝 Actualizando perfil con datos: {update_data}")
        print(f"📝 Actualizando perfil con: plan={plan_code}, tokens_restantes={'sumados' if 'tokens_restantes' in update_data else 'NO incluidos'}")
        
        update_response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
        
        if update_response.data:
            # Verificar que tokens_restantes se actualizó correctamente
            updated_profile = update_response.data[0]
            updated_tokens = updated_profile.get("tokens_restantes")
            
            if "tokens_restantes" in update_data:
                expected_tokens = update_data["tokens_restantes"]
                if updated_tokens == expected_tokens:
                    logger.info(f"✅ Perfil actualizado correctamente para usuario {user_id}: plan={plan_code}, tokens={updated_tokens:,}")
                    print(f"✅ Perfil actualizado: plan={plan_code}, tokens={updated_tokens:,}")
                else:
                    logger.error(f"❌ ERROR: Tokens no coinciden. Esperado: {expected_tokens:,}, Actual: {updated_tokens}")
                    print(f"❌ ERROR: Tokens no coinciden. Esperado: {expected_tokens:,}, Actual: {updated_tokens}")
            else:
                logger.warning(f"⚠️ ADVERTENCIA: tokens_restantes no se incluyó en la actualización")
                print(f"⚠️ ADVERTENCIA: tokens_restantes no se actualizó (no estaba en update_data)")
                print(f"✅ Perfil actualizado para usuario {user_id}: plan={plan_code}, customer={customer_id}")
        else:
            logger.error(f"❌ ERROR: update_response.data está vacío. La actualización puede haber fallado.")
            print(f"❌ ERROR: update_response.data está vacío. La actualización puede haber fallado.")
            print(f"   Verifica que el usuario {user_id} existe en la tabla profiles")
        
        # IMPORTANTE: Registrar pago inicial en tabla stripe_payments para análisis de ingresos (solo si la actualización fue exitosa)
        if update_response.data:
            try:
                from datetime import datetime
                # Obtener monto desde Stripe (necesitamos obtener la invoice o subscription)
                amount_usd = None
                payment_date = None
                
                if subscription_id:
                    try:
                        subscription = stripe.Subscription.retrieve(subscription_id)
                        # Obtener la última invoice pagada
                        if subscription.latest_invoice:
                            invoice_obj = stripe.Invoice.retrieve(subscription.latest_invoice)
                            amount_usd = invoice_obj.amount_paid / 100.0 if invoice_obj.amount_paid else None
                            payment_date = datetime.fromtimestamp(invoice_obj.created).isoformat() if invoice_obj.created else None
                    except Exception as e:
                        print(f"⚠️ Error al obtener invoice desde subscription: {e}")
                
                # Si no se pudo obtener desde subscription, usar precio del plan
                if amount_usd is None and plan_code:
                    from plans import get_plan_by_code
                    plan = get_plan_by_code(plan_code)
                    if plan:
                        amount_usd = plan.price_usd
                        payment_date = datetime.utcnow().isoformat()
                
                # Insertar en tabla de pagos si tenemos los datos
                if amount_usd is not None:
                    payment_data = {
                        "invoice_id": f"checkout-{session.get('id', 'unknown')}",
                        "customer_id": customer_id,
                        "user_id": user_id,
                        "plan_code": plan_code,
                        "amount_usd": amount_usd,
                        "currency": "usd",
                        "payment_date": payment_date or datetime.utcnow().isoformat()
                    }
                    
                    try:
                        payment_response = supabase_client.table("stripe_payments").insert(payment_data).execute()
                        if payment_response.data:
                            print(f"✅ Pago inicial registrado: ${amount_usd:.2f} USD para usuario {user_id} (plan: {plan_code})")
                    except Exception as insert_error:
                        # Si ya existe, no es crítico
                        print(f"⚠️ Pago ya registrado o error al insertar: {insert_error}")
            except Exception as payment_error:
                # No es crítico si falla el registro de pago
                print(f"⚠️ Error al registrar pago inicial (no crítico): {payment_error}")
            
            # IMPORTANTE: Enviar email al admin cuando hay una primera compra (checkout.session.completed)
            # IMPORTANTE: Obtener información del usuario y plan ANTES de enviar emails
            try:
                from lib.email import send_admin_email
                from datetime import datetime
                import threading
                
                # Obtener información del usuario y plan
                user_info_response = supabase_client.table("profiles").select("email").eq("id", user_id).execute()
                user_email = user_info_response.data[0].get("email") if user_info_response.data else "N/A"
                
                plan_name = plan_code
                plan_price = None
                if plan_code:
                    from plans import get_plan_by_code
                    plan_info = get_plan_by_code(plan_code)
                    if plan_info:
                        plan_name = plan_info.name
                        plan_price = plan_info.price_usd
                
                # Obtener monto desde Stripe si está disponible
                amount_usd = plan_price  # Fallback al precio del plan
                if subscription_id:
                    try:
                        subscription = stripe.Subscription.retrieve(subscription_id)
                        if subscription.latest_invoice:
                            invoice_obj = stripe.Invoice.retrieve(subscription.latest_invoice)
                            if invoice_obj.amount_paid:
                                amount_usd = invoice_obj.amount_paid / 100.0
                    except Exception as e:
                        logger.warning(f"No se pudo obtener monto desde Stripe, usando precio del plan: {e}")
                
                if amount_usd is None:
                    amount_usd = plan_price or 0.0
                
                def send_admin_checkout_email():
                    try:
                        admin_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h2 style="color: white; margin: 0; font-size: 24px;">🎉 Nueva Compra - Checkout Completado</h2>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Un usuario ha completado el checkout y activado su suscripción en Codex Trader.
                                </p>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Email del usuario:</strong> 
                                            <span style="color: #333;">{user_email}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">ID de usuario:</strong> 
                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Plan adquirido:</strong> 
                                            <span style="color: #333; font-weight: bold;">{plan_name} ({plan_code})</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Tokens asignados:</strong> 
                                            <span style="color: #333;">{tokens_per_month:,} tokens</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Customer ID (Stripe):</strong> 
                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{customer_id}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Subscription ID (Stripe):</strong> 
                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{subscription_id or 'N/A'}</span>
                                        </li>
                                        <li style="margin-bottom: 0;">
                                            <strong style="color: #059669;">Monto pagado:</strong> 
                                            <span style="color: #10b981; font-weight: bold; font-size: 18px;">${amount_usd:.2f} USD</span>
                                        </li>
                                    </ul>
                                </div>
                                
                                <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                    Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                                </p>
                            </div>
                        </body>
                        </html>
                        """
                        send_admin_email("🎉 Nueva Compra - Checkout Completado - Codex Trader", admin_html)
                    except Exception as e:
                        print(f"⚠️ Error al enviar email al admin por checkout completado: {e}")
                
                # IMPORTANTE: También enviar email al usuario confirmando su compra y tokens recibidos
                def send_user_checkout_email():
                    try:
                        from lib.email import send_email
                        from datetime import datetime
                        import os
                        
                        # Obtener información del plan
                        plan_name = plan_code
                        plan_price = None
                        if plan_code:
                            from plans import get_plan_by_code
                            plan_info = get_plan_by_code(plan_code)
                            if plan_info:
                                plan_name = plan_info.name
                                plan_price = plan_info.price_usd
                        
                        # Obtener fecha de renovación
                        next_renewal_str = "N/A"
                        if current_period_end:
                            from datetime import datetime
                            next_renewal = datetime.fromtimestamp(current_period_end)
                            next_renewal_str = next_renewal.strftime('%d/%m/%Y')
                        
                        # Construir URL del frontend
                        frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                        app_url = frontend_url.rstrip('/')
                        
                        user_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h1 style="color: white; margin: 0; font-size: 28px;">¡Pago Exitoso! 🎉</h1>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Hola <strong>{user_email}</strong>,
                                </p>
                                
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    ¡Gracias por tu compra! Tu suscripción a <strong>{plan_name}</strong> ha sido activada exitosamente.
                                </p>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                    <h3 style="color: #059669; margin-top: 0;">Detalles de tu suscripción:</h3>
                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Plan:</strong> 
                                            <span style="color: #333; font-weight: bold;">{plan_name}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Tokens recibidos:</strong> 
                                            <span style="color: #10b981; font-weight: bold; font-size: 18px;">{tokens_per_month:,} tokens</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Monto pagado:</strong> 
                                            <span style="color: #333; font-weight: bold;">${plan_price:.2f} USD</span>
                                        </li>
                                        <li style="margin-bottom: 0;">
                                            <strong style="color: #059669;">Próxima renovación:</strong> 
                                            <span style="color: #333;">{next_renewal_str}</span>
                                        </li>
                                    </ul>
                                </div>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{app_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                        🚀 Empezar a usar Codex Trader
                                    </a>
                                </div>
                                
                                <p style="font-size: 14px; color: #666; margin-top: 30px;">
                                    <strong>¿Qué puedes hacer ahora?</strong>
                                </p>
                                <ul style="color: #333; line-height: 1.8;">
                                    <li>Hacer consultas al asistente de IA especializado en trading</li>
                                    <li>Acceder a tu biblioteca profesional de contenido</li>
                                    <li>Ver tu uso de tokens en el panel de cuenta</li>
                                </ul>
                                
                                <p style="font-size: 12px; color: #666; margin-top: 30px; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                                    Si no reconoces este pago, contáctanos respondiendo a este correo.
                                </p>
                            </div>
                        </body>
                        </html>
                        """
                        send_email(
                            to=user_email,
                            subject=f"¡Pago exitoso! Tu plan {plan_name} está activo - Codex Trader",
                            html=user_html
                        )
                        logger.info(f"✅ Email de confirmación de compra enviado a {user_email}")
                    except Exception as e:
                        logger.error(f"❌ Error al enviar email al usuario por checkout completado: {e}")
                        print(f"⚠️ Error al enviar email al usuario por checkout completado: {e}")
                
                # Enviar emails en background (no bloquea)
                admin_thread = threading.Thread(target=send_admin_checkout_email, daemon=True)
                admin_thread.start()
                
                user_thread = threading.Thread(target=send_user_checkout_email, daemon=True)
                user_thread.start()
            except Exception as email_error:
                print(f"⚠️ Error al preparar emails por checkout completado: {email_error}")
                logger.error(f"❌ Error al preparar emails por checkout completado: {email_error}")
        else:
            print(f"⚠️ No se encontró perfil para usuario {user_id}")
            
    except Exception as e:
        print(f"❌ Error en handle_checkout_session_completed: {str(e)}")
        raise


async def handle_invoice_paid(invoice: dict):
    """
    Maneja el evento invoice.paid de Stripe (renovación mensual).
    
    Actualiza en la base de datos:
    - current_plan: Plan determinado desde el price_id de la invoice
    - tokens_restantes: Tokens del mes basados en el plan
    - current_period_end: Fecha de fin del período de facturación
    
    IMPORTANTE: Este es el lugar donde se actualiza tokens_restantes cada mes
    cuando se renueva la suscripción. El frontend puede leer este valor
    desde /app/billing o en el chat para mostrar el saldo actual.
    """
    try:
        # Extraer información de la invoice
        customer_id = invoice.get("customer")
        subscription_id = invoice.get("subscription")
        
        if not customer_id:
            print(f"⚠️ invoice.paid sin customer_id: {invoice.get('id')}")
            return
        
        # Buscar el usuario por stripe_customer_id (obtener también email y plan anterior)
        profile_response = supabase_client.table("profiles").select("id, email, current_plan").eq("stripe_customer_id", customer_id).execute()
        
        if not profile_response.data:
            print(f"⚠️ No se encontró usuario con stripe_customer_id: {customer_id}")
            return
        
        user_id = profile_response.data[0]["id"]
        user_email = profile_response.data[0].get("email", "")
        previous_plan = profile_response.data[0].get("current_plan")
        
        # Determinar si es nueva suscripción o renovación
        is_new_subscription = previous_plan is None or previous_plan == ""
        event_type = "nueva suscripción" if is_new_subscription else "renovación"
        
        # Obtener el price_id de la invoice para determinar el plan
        line_items = invoice.get("lines", {}).get("data", [])
        if not line_items:
            print(f"⚠️ invoice.paid sin line_items: {invoice.get('id')}")
            return
        
        # El primer line_item debería tener el price del plan
        price_id = line_items[0].get("price", {}).get("id")
        if not price_id:
            print(f"⚠️ invoice.paid sin price_id en line_items: {invoice.get('id')}")
            return
        
        # Determinar el plan desde el price_id
        plan_code = get_plan_code_from_price_id(price_id)
        if not plan_code:
            print(f"⚠️ No se encontró plan para price_id: {price_id}")
            return
        
        # Obtener información del plan para calcular tokens
        from plans import get_plan_by_code
        plan = get_plan_by_code(plan_code)
        if not plan:
            print(f"⚠️ No se encontró plan con código: {plan_code}")
            return
        
        tokens_per_month = plan.tokens_per_month
        
        # Obtener current_period_end desde la invoice
        period_end = None
        if line_items[0].get("period"):
            period_end_timestamp = line_items[0]["period"].get("end")
            if period_end_timestamp:
                from datetime import datetime
                period_end = datetime.fromtimestamp(period_end_timestamp).isoformat()
        
        # IMPORTANTE: Sumar tokens al renovar suscripción (no resetear)
        # Esto se hace cada vez que se paga una invoice (renovación mensual)
        # El frontend puede leer estos valores desde GET /me/usage
        try:
            # Obtener tokens actuales para sumar en lugar de resetear
            profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
            current_tokens = 0
            if profile_response.data and profile_response.data[0].get("tokens_restantes") is not None:
                current_tokens = profile_response.data[0]["tokens_restantes"]
            
            # Sumar tokens del plan a los tokens existentes
            new_tokens = current_tokens + tokens_per_month
            logger.info(f"💰 Renovación: Tokens sumados para usuario {user_id}: {current_tokens} + {tokens_per_month} = {new_tokens}")
        except Exception as e:
            logger.error(f"Error al obtener tokens actuales en renovación, usando tokens del plan: {e}")
            new_tokens = tokens_per_month
        
        update_data = {
            "current_plan": plan_code,
            "tokens_restantes": new_tokens  # Sumar tokens en lugar de resetear
        }
        
        # Intentar actualizar tokens_monthly_limit solo si la columna existe
        try:
            update_data["tokens_monthly_limit"] = tokens_per_month
            update_data["fair_use_warning_shown"] = False  # Resetear aviso suave
            update_data["fair_use_discount_eligible"] = False  # Resetear elegibilidad para descuento
            update_data["fair_use_discount_used"] = False  # Resetear uso de descuento
            update_data["fair_use_discount_eligible_at"] = None  # Resetear fecha de elegibilidad
            update_data["fair_use_email_sent"] = False  # Resetear flag de email enviado
        except Exception as e:
            logger.warning(f"No se pudo actualizar campos de uso justo (columnas pueden no existir): {e}")
        
        if period_end:
            update_data["current_period_end"] = period_end
        
        # IMPORTANTE: Lógica de recompensas de referidos
        # Verificar si este es el primer pago del usuario (para dar recompensa al que invita)
        invoice_id = invoice.get("id")
        process_referral_reward = False
        
        if invoice_id:
            # Verificar si ya se procesó esta recompensa (idempotencia)
            reward_event_check = supabase_client.table("referral_reward_events").select("id").eq("invoice_id", invoice_id).execute()
            
            if not reward_event_check.data:
                # Esta invoice no ha sido procesada antes, verificar si es primera suscripción
                profile_check = supabase_client.table("profiles").select(
                    "referred_by_user_id, has_generated_referral_reward"
                ).eq("id", user_id).execute()
                
                if profile_check.data:
                    referred_by_id = profile_check.data[0].get("referred_by_user_id")
                    has_generated_reward = profile_check.data[0].get("has_generated_referral_reward", False)
                    
                    # Si fue referido y aún no ha generado recompensa, procesar
                    if referred_by_id and not has_generated_reward:
                        process_referral_reward = True
        
        # Si es el primer pago, marcar que ya generó recompensa
        if process_referral_reward:
            update_data["has_generated_referral_reward"] = True
        
        # Actualizar el perfil del usuario
        update_response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
        
        if update_response.data:
            print(f"✅ Suscripción renovada para usuario {user_id}: plan={plan_code}, tokens={tokens_per_month}")
            
            # IMPORTANTE: Registrar pago en tabla stripe_payments para análisis de ingresos
            try:
                from datetime import datetime
                
                # Obtener monto de la invoice
                amount_total = invoice.get("amount_paid", invoice.get("amount_due", 0))
                amount_usd = amount_total / 100.0  # Stripe usa centavos
                currency = invoice.get("currency", "usd").upper()
                
                # Obtener fecha del pago
                payment_date = None
                if invoice.get("status_transitions", {}).get("paid_at"):
                    payment_date = invoice["status_transitions"]["paid_at"]
                elif invoice.get("created"):
                    payment_date = invoice["created"]
                
                # Convertir timestamp a datetime ISO si es necesario
                if payment_date and isinstance(payment_date, (int, float)):
                    payment_date = datetime.fromtimestamp(payment_date).isoformat()
                
                # Insertar en tabla de pagos (con manejo de duplicados)
                payment_data = {
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "plan_code": plan_code,
                    "amount_usd": amount_usd,
                    "currency": currency,
                    "payment_date": payment_date or datetime.utcnow().isoformat()
                }
                
                # Intentar insertar (puede fallar si ya existe por el UNIQUE constraint)
                try:
                    payment_response = supabase_client.table("stripe_payments").insert(payment_data).execute()
                    if payment_response.data:
                        print(f"✅ Pago registrado: ${amount_usd:.2f} USD para usuario {user_id} (plan: {plan_code})")
                except Exception as insert_error:
                    # Si ya existe, actualizar en lugar de insertar
                    try:
                        supabase_client.table("stripe_payments").update({
                            "amount_usd": amount_usd,
                            "plan_code": plan_code,
                            "payment_date": payment_date or datetime.utcnow().isoformat()
                        }).eq("invoice_id", invoice_id).execute()
                        print(f"✅ Pago actualizado: ${amount_usd:.2f} USD para invoice {invoice_id}")
                    except Exception as update_error:
                        print(f"⚠️ No se pudo registrar/actualizar pago: {update_error}")
            except Exception as payment_error:
                # No es crítico si falla el registro de pago
                print(f"⚠️ Error al registrar pago (no crítico): {payment_error}")
            
            # Procesar recompensa al que invita (si aplica)
            if process_referral_reward:
                await process_referrer_reward(user_id, referred_by_id, invoice_id)
            
            # IMPORTANTE: Enviar emails de notificación (admin y usuario)
            # Esto se hace en segundo plano y no bloquea el procesamiento del webhook
            try:
                from lib.email import send_admin_email, send_email
                from datetime import datetime
                import threading
                
                # Obtener información adicional para los emails
                plan_name = plan.name
                # Obtener monto de la invoice (ya se calculó arriba, pero lo recalculamos aquí para seguridad)
                amount_total = invoice.get("amount_paid", invoice.get("amount_due", 0))
                amount_usd = amount_total / 100.0  # Stripe usa centavos
                
                # Formatear fecha de pago (obtener directamente desde invoice)
                payment_date_str = None
                if invoice.get("status_transitions", {}).get("paid_at"):
                    payment_date_str = datetime.fromtimestamp(invoice["status_transitions"]["paid_at"]).strftime('%Y-%m-%d %H:%M:%S')
                elif invoice.get("created"):
                    payment_date_str = datetime.fromtimestamp(invoice["created"]).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    payment_date_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                
                # Formatear fecha de próxima renovación
                next_renewal_str = "N/A"
                if period_end:
                    try:
                        if isinstance(period_end, str):
                            if "T" in period_end:
                                dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
                            else:
                                dt = datetime.fromisoformat(period_end)
                        else:
                            dt = period_end
                        next_renewal_str = dt.strftime('%d/%m/%Y')
                    except:
                        next_renewal_str = str(period_end)
                
                # 1) EMAIL AL ADMIN: Notificación de pago
                def send_admin_email_background():
                    try:
                        admin_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                            <h2 style="color: #2563eb;">Nuevo pago en Codex Trader</h2>
                            <p>Se ha procesado un pago de suscripción en Codex Trader.</p>
                            <ul>
                                <li><strong>Email del usuario:</strong> {user_email}</li>
                                <li><strong>ID de usuario:</strong> {user_id}</li>
                                <li><strong>Plan:</strong> {plan_name} ({plan_code})</li>
                                <li><strong>Monto:</strong> ${amount_usd:.2f} USD</li>
                                <li><strong>Fecha del pago:</strong> {payment_date_str}</li>
                                <li><strong>Tipo de evento:</strong> {event_type}</li>
                                <li><strong>Invoice ID:</strong> {invoice_id}</li>
                            </ul>
                        </body>
                        </html>
                        """
                        send_admin_email("Nuevo pago en Codex Trader", admin_html)
                    except Exception as e:
                        print(f"WARNING: Error al enviar email al admin: {e}")
                
                # 2) EMAIL AL USUARIO: Confirmación de activación/renovación
                def send_user_email_background():
                    try:
                        if user_email:
                            user_html = f"""
                            <html>
                            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                                <h2 style="color: #2563eb;">Tu plan {plan_name} en Codex Trader está activo</h2>
                                <p>Hola {user_email.split('@')[0] if '@' in user_email else 'usuario'},</p>
                                <p>Tu plan <strong>{plan_name}</strong> en Codex Trader ha sido {'activado' if is_new_subscription else 'renovado'} correctamente.</p>
                                
                                <h3 style="color: #2563eb; margin-top: 20px;">Resumen:</h3>
                                <ul>
                                    <li><strong>Plan:</strong> {plan_name}</li>
                                    <li><strong>Precio:</strong> ${amount_usd:.2f} USD</li>
                                    <li><strong>Tokens disponibles este mes:</strong> {tokens_per_month:,}</li>
                                    <li><strong>Próxima renovación:</strong> {next_renewal_str}</li>
                                </ul>
                                
                                <h3 style="color: #2563eb; margin-top: 20px;">Recuerda:</h3>
                                <ul>
                                    <li>Puedes ver tu uso de tokens en el panel de cuenta.</li>
                                    <li>Tienes acceso al modelo de IA especializado en trading y tu biblioteca profesional.</li>
                                </ul>
                                
                                <p style="margin-top: 30px; color: #666; font-size: 12px;">
                                    Si no reconoces este pago, contáctanos respondiendo a este correo.
                                </p>
                            </body>
                            </html>
                            """
                            send_email(
                                to=user_email,
                                subject=f"Tu plan {plan_name} en Codex Trader está activo",
                                html=user_html
                            )
                    except Exception as e:
                        print(f"WARNING: Error al enviar email al usuario: {e}")
                
                # Enviar emails en background (no bloquea)
                admin_thread = threading.Thread(target=send_admin_email_background, daemon=True)
                admin_thread.start()
                
                user_thread = threading.Thread(target=send_user_email_background, daemon=True)
                user_thread.start()
                
            except Exception as email_error:
                # No es crítico si falla el envío de emails
                print(f"WARNING: Error al enviar emails de notificación (no crítico): {email_error}")
        else:
            print(f"⚠️ No se pudo actualizar perfil para usuario {user_id}")
            
    except Exception as e:
        print(f"❌ Error en handle_invoice_paid: {str(e)}")
        raise


async def process_referrer_reward(user_id: str, referrer_id: str, invoice_id: str):
    """
    Procesa la recompensa de 10,000 tokens para el usuario que invitó.
    
    IMPORTANTE: Esta función es idempotente y verifica:
    - Que el referrer no haya alcanzado el límite de 5 recompensas
    - Que esta invoice no haya sido procesada antes
    
    Args:
        user_id: ID del usuario que pagó (invitado)
        referrer_id: ID del usuario que invitó
        invoice_id: ID de la invoice de Stripe (para idempotencia)
    """
    try:
        # Obtener información del referrer
        referrer_response = supabase_client.table("profiles").select(
            "id, referral_rewards_count, tokens_restantes"
        ).eq("id", referrer_id).execute()
        
        if not referrer_response.data:
            print(f"⚠️ No se encontró referrer con ID: {referrer_id}")
            return
        
        referrer = referrer_response.data[0]
        rewards_count = referrer.get("referral_rewards_count", 0)
        
        # Verificar límite de 5 recompensas
        if rewards_count >= 5:
            print(f"ℹ️ Referrer {referrer_id} ya alcanzó el límite de 5 recompensas")
            return
        
        # Verificar idempotencia: esta invoice no debe haber sido procesada
        reward_event_check = supabase_client.table("referral_reward_events").select("id").eq("invoice_id", invoice_id).execute()
        if reward_event_check.data:
            print(f"ℹ️ Recompensa para invoice {invoice_id} ya fue procesada (idempotencia)")
            return
        
        # Recompensa: 10,000 tokens
        reward_amount = 10000
        
        # Sumar tokens al referrer
        current_tokens = referrer.get("tokens_restantes", 0) or 0
        new_tokens = current_tokens + reward_amount
        
        # Actualizar referrer: tokens, contador y tokens ganados
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": new_tokens,
            "referral_rewards_count": rewards_count + 1,
            "referral_tokens_earned": referrer.get("referral_tokens_earned", 0) + reward_amount
        }).eq("id", referrer_id).execute()
        
        if update_response.data:
            # Registrar evento para idempotencia
            event_response = supabase_client.table("referral_reward_events").insert({
                "invoice_id": invoice_id,
                "user_id": user_id,
                "referrer_id": referrer_id,
                "reward_type": "first_payment",
                "tokens_granted": reward_amount
            }).execute()
            
            if event_response.data:
                print(f"✅ Recompensa otorgada: {reward_amount:,} tokens a referrer {referrer_id} por invitado {user_id} (invoice: {invoice_id})")
                
                # IMPORTANTE: Enviar email al referrer notificando la recompensa
                try:
                    from lib.email import send_email
                    from datetime import datetime
                    import threading
                    
                    # Obtener email del referrer
                    referrer_email_response = supabase_client.table("profiles").select(
                        "email"
                    ).eq("id", referrer_id).execute()
                    
                    # Obtener email del usuario que pagó (invitado)
                    invited_user_response = supabase_client.table("profiles").select(
                        "email"
                    ).eq("id", user_id).execute()
                    
                    referrer_email = referrer_email_response.data[0].get("email") if referrer_email_response.data else None
                    invited_user_email = invited_user_response.data[0].get("email") if invited_user_response.data else "un usuario"
                    
                    if referrer_email:
                        def send_referrer_reward_email():
                            try:
                                # Construir URL del frontend
                                frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                                app_url = frontend_url.rstrip('/')
                                
                                referrer_html = f"""
                                <html>
                                <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                    <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                        <h1 style="color: white; margin: 0; font-size: 28px;">¡Recompensa de Referido! 🎉</h1>
                                    </div>
                                    
                                    <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            Hola <strong>{referrer_email.split('@')[0] if '@' in referrer_email else 'trader'}</strong>,
                                        </p>
                                        
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            ¡Excelentes noticias! Uno de tus referidos ha pagado su primera suscripción y has ganado una recompensa.
                                        </p>
                                        
                                        <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                            <h3 style="color: #059669; margin-top: 0;">Detalles de tu recompensa:</h3>
                                            <ul style="list-style: none; padding: 0; margin: 0;">
                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                    <strong style="color: #059669;">Referido:</strong> 
                                                    <span style="color: #333;">{invited_user_email}</span>
                                                </li>
                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                    <strong style="color: #059669;">Tokens recibidos:</strong> 
                                                    <span style="color: #10b981; font-weight: bold; font-size: 18px;">+{reward_amount:,} tokens</span>
                                                </li>
                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                    <strong style="color: #059669;">Total de bonos usados:</strong> 
                                                    <span style="color: #333;">{rewards_count + 1} / 5</span>
                                                </li>
                                                <li style="margin-bottom: 0;">
                                                    <strong style="color: #059669;">Tokens totales ganados por referidos:</strong> 
                                                    <span style="color: #333; font-weight: bold;">{referrer.get("referral_tokens_earned", 0) + reward_amount:,} tokens</span>
                                                </li>
                                            </ul>
                                        </div>
                                        
                                        <div style="text-align: center; margin: 30px 0;">
                                            <a href="{app_url}/invitar" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                                📊 Ver mis estadísticas de referidos
                                            </a>
                                        </div>
                                        
                                        <p style="font-size: 14px; color: #666; margin-top: 30px;">
                                            <strong>¿Quieres ganar más tokens?</strong> Comparte tu enlace de referido con más traders. 
                                            Puedes ganar hasta 5 bonos de 10,000 tokens cada uno.
                                        </p>
                                        
                                        <p style="font-size: 12px; color: #666; margin-top: 30px; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                                            ¡Gracias por compartir Codex Trader con otros traders!
                                        </p>
                                    </div>
                                </body>
                                </html>
                                """
                                
                                send_email(
                                    to=referrer_email,
                                    subject=f"¡Ganaste {reward_amount:,} tokens por tu referido! - Codex Trader",
                                    html=referrer_html
                                )
                                print(f"✅ Email de recompensa enviado a referrer {referrer_email}")
                            except Exception as e:
                                print(f"⚠️ Error al enviar email de recompensa al referrer: {e}")
                        
                        # Enviar email en background (no bloquea)
                        email_thread = threading.Thread(target=send_referrer_reward_email, daemon=True)
                        email_thread.start()
                    else:
                        print(f"⚠️ No se encontró email para referrer {referrer_id}")
                except Exception as email_error:
                    # No es crítico si falla el email
                    print(f"⚠️ Error al enviar email de recompensa (no crítico): {email_error}")
            else:
                print(f"⚠️ Recompensa otorgada pero no se pudo registrar evento para invoice {invoice_id}")
        else:
            print(f"⚠️ No se pudo actualizar referrer {referrer_id}")
            
    except Exception as e:
        print(f"❌ Error al procesar recompensa de referrer: {str(e)}")
        # No lanzar excepción para no romper el webhook principal

# ============================================================================
# FUNCIONES UTILITARIAS DE TOKENS Y RECOMPENSAS
# ============================================================================

def add_tokens_to_user(user_id: str, amount: int, reason: str = "Bonus") -> bool:
    """
    Suma tokens a un usuario de forma segura.
    
    Esta función es idempotente y puede usarse para:
    - Bonus de referidos
    - Descuentos
    - Campañas
    - Cualquier otro tipo de recompensa
    
    Args:
        user_id: ID del usuario
        amount: Cantidad de tokens a sumar (puede ser negativo para restar)
        reason: Razón del cambio (para logging)
        
    Returns:
        True si se actualizó correctamente, False en caso contrario
    """
    try:
        # Obtener tokens actuales
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            print(f"⚠️ No se encontró perfil para usuario {user_id}")
            return False
        
        current_tokens = profile_response.data[0]["tokens_restantes"] or 0
        new_tokens = current_tokens + amount
        
        # Actualizar tokens
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": new_tokens
        }).eq("id", user_id).execute()
        
        if update_response.data:
            print(f"✅ Tokens actualizados para usuario {user_id}: {current_tokens} + {amount} = {new_tokens} ({reason})")
            return True
        else:
            print(f"⚠️ No se pudo actualizar tokens para usuario {user_id}")
            return False
            
    except Exception as e:
        print(f"❌ Error al sumar tokens a usuario {user_id}: {str(e)}")
        return False

# ============================================================================
# ENDPOINTS DE USO JUSTO (FAIR USE)
# ============================================================================

# Endpoint para verificar si el usuario es administrador
@app.get("/me/is-admin")
async def check_is_admin(user = Depends(get_user)):
    """
    Endpoint para verificar si el usuario autenticado es administrador.
    Retorna True si el usuario tiene is_admin=True en profiles o está en ADMIN_EMAILS.
    """
    try:
        user_id = user.id
        
        # Verificar lista de emails de admin
        admin_emails = os.getenv("ADMIN_EMAILS", "").strip('"').strip("'").strip()
        if admin_emails:
            admin_list = [email.strip().lower() for email in admin_emails.split(",")]
            if user.email and user.email.lower() in admin_list:
                return {"is_admin": True}
        
        # Verificar campo is_admin en profiles
        try:
            profile_response = supabase_client.table("profiles").select("is_admin").eq("id", user_id).execute()
            if profile_response.data and profile_response.data[0].get("is_admin", False):
                return {"is_admin": True}
        except Exception as e:
            logger.warning(f"⚠️ Error al verificar is_admin en profiles: {e}")
        
        return {"is_admin": False}
    except Exception as e:
        logger.error(f"❌ Error al verificar si usuario es admin: {e}")
        return {"is_admin": False}

# Endpoint para obtener información de uso del usuario actual
# RUTA: GET /me/usage
# ARCHIVO: main.py (línea ~1545)
@app.get("/me/usage")
async def get_user_usage(user = Depends(get_user)):
    """
    Obtiene información sobre el uso de tokens y estado de uso justo del usuario.
    
    Retorna:
    - tokens_monthly_limit: Límite mensual de tokens según el plan
    - tokens_restantes: Tokens restantes actuales
    - usage_percent: Porcentaje de uso (0-100)
    - fair_use_warning_shown: Si se mostró aviso suave al 80%
    - fair_use_discount_eligible: Si es elegible para descuento al 90%
    - fair_use_discount_used: Si ya usó el descuento en este ciclo
    
    IMPORTANTE: El frontend puede usar esta información para mostrar:
    - Estado de uso en el chat
    - Avisos de uso justo
    - Elegibilidad para descuento del 20% en la página de billing
    """
    try:
        user_id = user.id
        
        # Intentar obtener columnas de uso justo, pero manejar si no existen
        try:
            profile_response = supabase_client.table("profiles").select(
                "tokens_restantes, tokens_monthly_limit, current_plan, fair_use_warning_shown, "
                "fair_use_discount_eligible, fair_use_discount_used, fair_use_discount_eligible_at"
            ).eq("id", user_id).execute()
        except Exception as e:
            # Si falla por columnas faltantes, intentar solo con columnas básicas
            logger.warning(f"Error al obtener columnas de uso justo, intentando solo columnas básicas: {e}")
            profile_response = supabase_client.table("profiles").select(
                "tokens_restantes, current_plan"
            ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        tokens_restantes = profile.get("tokens_restantes", 0) or 0
        tokens_monthly_limit = profile.get("tokens_monthly_limit", 0) or 0
        current_plan = profile.get("current_plan")
        
        # Si tokens_monthly_limit es 0 o None, intentar obtenerlo del plan actual
        if tokens_monthly_limit == 0 and current_plan:
            try:
                from plans import get_plan_by_code
                plan = get_plan_by_code(current_plan)
                if plan:
                    tokens_monthly_limit = plan.tokens_per_month
                    logger.info(f"⚠️ tokens_monthly_limit no estaba configurado, usando valor del plan {current_plan}: {tokens_monthly_limit}")
            except Exception as e:
                logger.warning(f"Error al obtener tokens del plan: {e}")
        
        # Calcular porcentaje de uso solo si tokens_monthly_limit existe
        usage_percent = 0.0
        tokens_usados = 0
        if tokens_monthly_limit > 0:
            # tokens_usados = cuántos tokens del límite mensual se han usado
            # Si tokens_restantes > tokens_monthly_limit, significa que tiene tokens extra (paquetes)
            # En ese caso, tokens_usados = 0 (no ha usado nada del límite mensual)
            tokens_usados = max(0, tokens_monthly_limit - tokens_restantes)
            usage_percent = (tokens_usados / tokens_monthly_limit) * 100
            # Asegurar que no sea negativo ni mayor a 100%
            usage_percent = max(0.0, min(100.0, usage_percent))
        
        result = {
            "tokens_restantes": tokens_restantes,
            "current_plan": current_plan
        }
        
        # Agregar campos de uso justo solo si existen
        if tokens_monthly_limit > 0:
            result["tokens_monthly_limit"] = tokens_monthly_limit
            result["tokens_usados"] = tokens_usados
            result["usage_percent"] = usage_percent
        
        # Intentar agregar campos de fair use si existen
        if "fair_use_warning_shown" in profile:
            result["fair_use_warning_shown"] = profile.get("fair_use_warning_shown", False)
        if "fair_use_discount_eligible" in profile:
            result["fair_use_discount_eligible"] = profile.get("fair_use_discount_eligible", False)
        if "fair_use_discount_used" in profile:
            result["fair_use_discount_used"] = profile.get("fair_use_discount_used", False)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener información de uso: {str(e)}"
        )

# ============================================================================
# FUNCIONES DE ADMINISTRACIÓN
# ============================================================================

# TODO: Implementar un sistema de roles más robusto
# Por ahora, usamos una lista de emails de administradores
# En producción, deberías usar un sistema de roles en la base de datos
ADMIN_EMAILS = [
    "david.del.rio.colin@gmail.com",  # Administrador principal (email real en Supabase)
    "todossomostr4ders@gmail.com",  # Email alternativo
    # Agrega aquí más emails de administradores si es necesario
    # Ejemplo: "admin@codextrader.mx"
]

def is_admin_user(user) -> bool:
    """
    Verifica si un usuario es administrador.
    
    TODO: Implementar un sistema de roles más robusto:
    - Agregar campo 'role' o 'is_admin' a la tabla profiles
    - O crear una tabla de roles separada
    - Por ahora, usa una lista de emails en ADMIN_EMAILS
    
    Args:
        user: Objeto usuario de Supabase
        
    Returns:
        True si el usuario es admin, False en caso contrario
    """
    if not user or not user.email:
        return False
    
    # Verificar si el email está en la lista de admins
    if user.email.lower() in [email.lower() for email in ADMIN_EMAILS]:
        return True
    
    # TODO: Verificar en la base de datos si el usuario tiene rol de admin
    # Ejemplo:
    # profile = supabase_client.table("profiles").select("is_admin").eq("id", user.id).execute()
    # return profile.data[0].get("is_admin", False) if profile.data else False
    
    return False

# ============================================================================
# ENDPOINTS DE ADMINISTRACIÓN
# ============================================================================

# Endpoint para crear índice vectorial en la base de datos
# RUTA: POST /admin/create-vector-index
# IMPORTANTE: Este endpoint es solo para administradores
@app.post("/admin/create-vector-index")
async def create_vector_index(
    index_type: str = Query("hnsw", description="Tipo de índice: 'hnsw' o 'ivfflat'"),
    lists: int = Query(10, description="Número de lists para IVFFlat (solo si index_type='ivfflat')"),
    m: int = Query(32, description="Parámetro m para HNSW (solo si index_type='hnsw')"),
    ef_construction: int = Query(64, description="Parámetro ef_construction para HNSW (solo si index_type='hnsw')"),
    user = Depends(get_user)
):
    """
    Crea un índice vectorial en la tabla vecs.knowledge para optimizar búsquedas RAG.
    
    IMPORTANTE: Este endpoint es solo para administradores.
    La creación del índice puede tardar varios minutos dependiendo del tamaño de la tabla.
    El índice se crea con CONCURRENTLY para no bloquear la tabla durante la creación.
    
    Parámetros:
    - index_type: Tipo de índice ('hnsw' o 'ivfflat')
      - 'hnsw': Más rápido de crear, mejor para muchas búsquedas, usa más espacio
      - 'ivfflat': Más lento de crear, mejor para tablas grandes, usa menos espacio
    - lists: Número de lists para IVFFlat (default: 10, menor = menos memoria pero más rápido)
    - m: Parámetro m para HNSW (default: 32, mayor = más preciso pero más espacio)
    - ef_construction: Parámetro ef_construction para HNSW (default: 64)
    
    Retorna:
    - status: Estado de la operación
    - message: Mensaje descriptivo
    - index_name: Nombre del índice creado
    """
    # Verificar que el usuario es administrador
    if not is_admin_user(user):
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Este endpoint es solo para administradores."
        )
    
    try:
        # Obtener URL de conexión
        database_url = os.getenv("SUPABASE_DB_URL")
        if not database_url:
            raise HTTPException(
                status_code=500,
                detail="SUPABASE_DB_URL no está configurada"
            )
        
        # Limpiar la URL de parámetros inválidos (misma lógica que en inicialización RAG)
        from urllib.parse import urlparse, urlencode
        parsed = urlparse(database_url.strip('"').strip("'").strip())
        
        valid_params = {}
        if parsed.query:
            from urllib.parse import parse_qs
            params = parse_qs(parsed.query)
            valid_keys = ['connect_timeout', 'application_name', 'sslmode', 'sslrootcert']
            for key in valid_keys:
                if key in params:
                    value = params[key][0] if isinstance(params[key], list) else params[key]
                    valid_params[key] = value
        
        if 'connect_timeout' not in valid_params:
            valid_params['connect_timeout'] = '300'  # 5 minutos para crear índice
        if 'application_name' not in valid_params:
            valid_params['application_name'] = 'index_creation'
        
        clean_query = urlencode(valid_params) if valid_params else ''
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_query:
            clean_url += f"?{clean_query}"
        
        logger.info(f"🔧 Iniciando creación de índice vectorial...")
        logger.info(f"   Tipo: {index_type}")
        logger.info(f"   Usuario: {user.email}")
        
        # Crear engine con AUTOCOMMIT para que CONCURRENTLY funcione
        engine = create_engine(clean_url, isolation_level="AUTOCOMMIT")
        
        index_name = f"knowledge_vec_idx_{index_type}_{m if index_type == 'hnsw' else lists}"
        
        with engine.connect() as conn:
            # Eliminar índice anterior si existe (para recrear)
            logger.info(f"   Eliminando índice anterior si existe: {index_name}")
            conn.execute(text(f"DROP INDEX IF EXISTS vecs.{index_name}"))
            
            # Crear índice según el tipo
            if index_type == "hnsw":
                logger.info(f"   Creando índice HNSW con m={m}, ef_construction={ef_construction}")
                sql = f"""
                    CREATE INDEX CONCURRENTLY {index_name}
                    ON vecs.knowledge 
                    USING hnsw (vec vector_cosine_ops) 
                    WITH (m = {m}, ef_construction = {ef_construction})
                """
            elif index_type == "ivfflat":
                logger.info(f"   Creando índice IVFFlat con lists={lists}")
                sql = f"""
                    CREATE INDEX CONCURRENTLY {index_name}
                    ON vecs.knowledge 
                    USING ivfflat (vec vector_cosine_ops) 
                    WITH (lists = {lists})
                """
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Tipo de índice inválido: {index_type}. Usa 'hnsw' o 'ivfflat'"
                )
            
            # Ejecutar creación de índice
            logger.info("   Ejecutando CREATE INDEX CONCURRENTLY (puede tardar varios minutos)...")
            conn.execute(text(sql))
            logger.info(f"✅ Índice {index_name} creado exitosamente")
        
        return {
            "status": "success",
            "message": f"Índice vectorial {index_type} creado exitosamente",
            "index_name": index_name,
            "index_type": index_type,
            "note": "El índice se está construyendo en segundo plano. Las búsquedas mejorarán gradualmente."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al crear índice vectorial: {error_msg}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Mensajes de error más descriptivos
        if "No space left on device" in error_msg:
            raise HTTPException(
                status_code=507,
                detail="No hay suficiente espacio en disco. Libera espacio antes de crear el índice."
            )
        elif "timeout" in error_msg.lower():
            raise HTTPException(
                status_code=504,
                detail="Timeout al crear el índice. Intenta con menos 'lists' (IVFFlat) o menor 'm' (HNSW)."
            )
        elif "already exists" in error_msg.lower():
            raise HTTPException(
                status_code=409,
                detail=f"El índice ya existe. Elimínalo primero o usa un nombre diferente."
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Error al crear índice: {error_msg[:200]}"
            )

# Endpoint para restablecer contraseña de un usuario (solo admin)
# RUTA: POST /admin/reset-user-password
# IMPORTANTE: Este endpoint es solo para administradores
@app.post("/admin/reset-user-password")
async def reset_user_password(
    user_email: str = Query(..., description="Email del usuario al que se le reseteará la contraseña"),
    send_email: bool = Query(True, description="Enviar email con la nueva contraseña"),
    user = Depends(get_user)
):
    """
    Restablece la contraseña de un usuario y genera una contraseña temporal.
    
    IMPORTANTE: Este endpoint es solo para administradores.
    
    Parámetros:
    - user_email: Email del usuario al que se le reseteará la contraseña
    - send_email: Si se debe enviar un email con la nueva contraseña (default: True)
    
    Retorna:
    - status: Estado de la operación
    - message: Mensaje descriptivo
    - temp_password: Contraseña temporal generada (IMPORTANTE: guarda esto)
    - reset_link: Link de reset de contraseña (alternativa)
    """
    # Verificar que el usuario es administrador
    if not is_admin_user(user):
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Este endpoint es solo para administradores."
        )
    
    try:
        import secrets
        import string
        
        # Generar contraseña temporal segura
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        temp_password = ''.join(secrets.choice(alphabet) for i in range(16))
        
        logger.info(f"🔧 Restableciendo contraseña para usuario: {user_email}")
        logger.info(f"   Solicitado por admin: {user.email}")
        
        # Buscar el usuario por email
        user_response = supabase_client.auth.admin.list_users()
        
        target_user = None
        for u in user_response.users:
            if u.email and u.email.lower() == user_email.lower():
                target_user = u
                break
        
        if not target_user:
            raise HTTPException(
                status_code=404,
                detail=f"Usuario con email {user_email} no encontrado"
            )
        
        # Actualizar la contraseña del usuario usando admin API
        update_response = supabase_client.auth.admin.update_user_by_id(
            target_user.id,
            {"password": temp_password}
        )
        
        if not update_response.user:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar la contraseña del usuario"
            )
        
        logger.info(f"✅ Contraseña temporal generada para {user_email}")
        
        # Generar link de reset como alternativa
        reset_link_response = supabase_client.auth.admin.generate_link({
            "type": "recovery",
            "email": user_email,
        })
        
        reset_link = reset_link_response.properties.action_link if hasattr(reset_link_response, 'properties') else None
        
        # Enviar email con la contraseña temporal si se solicita
        if send_email:
            try:
                from lib.email import send_email
                email_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2 style="color: #2563eb;">Restablecimiento de Contraseña - Codex Trader</h2>
                    <p>Hola,</p>
                    <p>Se ha generado una <strong>contraseña temporal</strong> para tu cuenta:</p>
                    <div style="background-color: #f3f4f6; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="font-size: 18px; font-family: monospace; margin: 0;"><strong>{temp_password}</strong></p>
                    </div>
                    <p><strong>⚠️ IMPORTANTE:</strong></p>
                    <ul>
                        <li>Esta es una contraseña temporal</li>
                        <li>Cambia tu contraseña después de iniciar sesión</li>
                        <li>No compartas esta contraseña con nadie</li>
                    </ul>
                    <p>Puedes iniciar sesión con esta contraseña temporal y luego cambiarla en tu perfil.</p>
                    <p style="margin-top: 30px; color: #666; font-size: 12px;">
                        Si no solicitaste este restablecimiento, contacta al administrador inmediatamente.
                    </p>
                </body>
                </html>
                """
                
                send_email(
                    to=user_email,
                    subject="Contraseña Temporal - Codex Trader",
                    html=email_html
                )
                logger.info(f"✅ Email con contraseña temporal enviado a {user_email}")
            except Exception as email_error:
                logger.warning(f"⚠️ No se pudo enviar email (la contraseña sigue siendo válida): {email_error}")
        
        return {
            "status": "success",
            "message": f"Contraseña temporal generada para {user_email}",
            "temp_password": temp_password,
            "reset_link": reset_link,
            "note": "⚠️ GUARDA ESTA CONTRASEÑA TEMPORAL. Se ha enviado por email si send_email=true."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al restablecer contraseña: {error_msg}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al restablecer contraseña: {error_msg[:200]}"
        )

# Endpoint para obtener resumen de costos e ingresos
# RUTA: GET /admin/cost-summary?from=YYYY-MM-DD&to=YYYY-MM-DD
# ARCHIVO: main.py (línea ~1800)
# IMPORTANTE: Este endpoint es solo para administradores
@app.get("/admin/cost-summary")
async def get_cost_summary(
    from_date: str = Query(..., description="Fecha de inicio (YYYY-MM-DD)"),
    to_date: str = Query(..., description="Fecha de fin (YYYY-MM-DD)"),
    user = Depends(get_user)
):
    """
    Obtiene un resumen de costos e ingresos para el rango de fechas especificado.
    
    IMPORTANTE: Este endpoint es solo para administradores.
    Verifica que el usuario tenga permisos de administrador antes de procesar.
    
    Retorna:
    - from: Fecha de inicio
    - to: Fecha de fin
    - daily: Array con resumen diario (costos e ingresos por día)
    - totals: Totales agregados (costos, ingresos, margen)
    
    TODO: Implementar sistema de roles más robusto para verificar permisos de admin
    """
    # Verificar que el usuario es administrador
    if not is_admin_user(user):
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado. Este endpoint es solo para administradores."
        )
    
    try:
        from datetime import datetime, timedelta
        try:
            import pytz
        except ImportError:
            # Si pytz no está disponible, usar timezone de datetime
            from datetime import timezone
            pytz = None
        
        # Parsear fechas
        try:
            date_from = datetime.strptime(from_date, "%Y-%m-%d")
            date_to = datetime.strptime(to_date, "%Y-%m-%d")
            # Ajustar a inicio y fin del día
            date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
            date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Formato de fecha inválido. Use YYYY-MM-DD"
            )
        
        # Validar rango de fechas
        if date_from > date_to:
            raise HTTPException(
                status_code=400,
                detail="La fecha de inicio debe ser anterior a la fecha de fin"
            )
        
        # Convertir a UTC para consultas
        if pytz:
            utc = pytz.UTC
            date_from_utc = date_from.replace(tzinfo=utc)
            date_to_utc = date_to.replace(tzinfo=utc)
        else:
            from datetime import timezone
            utc = timezone.utc
            date_from_utc = date_from.replace(tzinfo=utc)
            date_to_utc = date_to.replace(tzinfo=utc)
        
        # Consultar costos de modelos agrupados por día
        usage_response = supabase_client.table("model_usage_events").select(
            "tokens_input, tokens_output, cost_estimated_usd, created_at"
        ).gte("created_at", date_from_utc.isoformat()).lte("created_at", date_to_utc.isoformat()).execute()
        
        # Agrupar costos por día
        daily_costs = {}
        total_tokens_input = 0
        total_tokens_output = 0
        total_cost_usd = 0.0
        
        if usage_response.data:
            for event in usage_response.data:
                created_at = event.get("created_at")
                if created_at:
                    # Extraer fecha (sin hora)
                    event_date = created_at.split("T")[0] if "T" in created_at else created_at.split(" ")[0]
                    
                    if event_date not in daily_costs:
                        daily_costs[event_date] = {
                            "tokens_input": 0,
                            "tokens_output": 0,
                            "cost_estimated_usd": 0.0
                        }
                    
                    daily_costs[event_date]["tokens_input"] += event.get("tokens_input", 0)
                    daily_costs[event_date]["tokens_output"] += event.get("tokens_output", 0)
                    daily_costs[event_date]["cost_estimated_usd"] += float(event.get("cost_estimated_usd", 0))
                    
                    total_tokens_input += event.get("tokens_input", 0)
                    total_tokens_output += event.get("tokens_output", 0)
                    total_cost_usd += float(event.get("cost_estimated_usd", 0))
        
        # Consultar ingresos de Stripe agrupados por día
        payments_response = supabase_client.table("stripe_payments").select(
            "amount_usd, payment_date"
        ).gte("payment_date", date_from_utc.isoformat()).lte("payment_date", date_to_utc.isoformat()).execute()
        
        # Agrupar ingresos por día
        daily_revenue = {}
        total_revenue_usd = 0.0
        
        if payments_response.data:
            for payment in payments_response.data:
                payment_date_str = payment.get("payment_date")
                if payment_date_str:
                    # Extraer fecha (sin hora)
                    payment_date = payment_date_str.split("T")[0] if "T" in payment_date_str else payment_date_str.split(" ")[0]
                    
                    if payment_date not in daily_revenue:
                        daily_revenue[payment_date] = 0.0
                    
                    amount = float(payment.get("amount_usd", 0))
                    daily_revenue[payment_date] += amount
                    total_revenue_usd += amount
        
        # Combinar datos diarios
        daily_summary = []
        current_date = date_from.date()
        end_date = date_to.date()
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            costs = daily_costs.get(date_str, {
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_estimated_usd": 0.0
            })
            
            revenue = daily_revenue.get(date_str, 0.0)
            
            daily_summary.append({
                "date": date_str,
                "tokens_input": costs["tokens_input"],
                "tokens_output": costs["tokens_output"],
                "cost_estimated_usd": round(costs["cost_estimated_usd"], 6),
                "revenue_usd": round(revenue, 2)
            })
            
            current_date += timedelta(days=1)
        
        # Calcular margen
        margin_usd = total_revenue_usd - total_cost_usd
        
        return {
            "from": from_date,
            "to": to_date,
            "daily": daily_summary,
            "totals": {
                "tokens_input": total_tokens_input,
                "tokens_output": total_tokens_output,
                "cost_estimated_usd": round(total_cost_usd, 6),
                "revenue_usd": round(total_revenue_usd, 2),
                "margin_usd": round(margin_usd, 2),
                "margin_percent": round((margin_usd / total_revenue_usd * 100) if total_revenue_usd > 0 else 0, 2)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener resumen de costos: {str(e)}"
        )

# ============================================================================
# ENDPOINTS DE DEBUG (SOLO PARA DESARROLLO)
# ============================================================================

# TODO: DESACTIVAR O PROTEGER ESTE ENDPOINT EN PRODUCCIÓN
# Este endpoint es solo para pruebas de email durante el desarrollo.
# En producción, deberías:
# - Desactivarlo completamente, o
# - Protegerlo con autenticación de administrador, o
# - Restringirlo solo a ciertos IPs

class TestEmailInput(BaseModel):
    """Modelo para el endpoint de prueba de email"""
    to: Optional[str] = None

@app.get("/debug/test-email")
async def test_email_get(to: Optional[str] = None):
    """
    Endpoint GET temporal SOLO PARA PRUEBAS de envío de emails.
    
    IMPORTANTE: Este endpoint es solo para desarrollo.
    TODO: Desactivar o proteger con auth en producción.
    
    Query params (opcional):
        ?to=email@ejemplo.com  // Opcional, usa ADMIN_EMAIL si no se proporciona
    
    Returns:
        JSON con success: true si no hubo error aparente
    """
    try:
        from lib.email import send_email, ADMIN_EMAIL
        
        # Determinar destinatario
        recipient = to if to else ADMIN_EMAIL
        
        if not recipient:
            return {
                "success": False,
                "error": "No se proporciono destinatario y ADMIN_EMAIL no esta configurado"
            }
        
        # Enviar email de prueba
        subject = "Prueba SMTP Codex"
        html_content = "<p>Este es un correo de prueba desde el backend de Codex Trader.</p>"
        
        # El envío se hace síncronamente pero no bloquea el servidor si falla
        # Si falla, send_email registra el error pero no lanza excepción
        result = send_email(
            to=recipient,
            subject=subject,
            html=html_content
        )
        
        if result:
            return {
                "success": True,
                "message": f"Email de prueba enviado a {recipient}",
                "recipient": recipient
            }
        else:
            return {
                "success": False,
                "error": "Error al enviar email (revisa los logs del servidor para mas detalles)",
                "recipient": recipient
            }
            
    except Exception as e:
        # Capturar cualquier error inesperado
        print(f"ERROR: Error inesperado en test-email: {e}")
        return {
            "success": False,
            "error": f"Error inesperado: {str(e)}"
        }

@app.post("/debug/test-email")
async def test_email_post(input_data: Optional[TestEmailInput] = None):
    """
    Endpoint temporal SOLO PARA PRUEBAS de envío de emails.
    
    IMPORTANTE: Este endpoint es solo para desarrollo.
    TODO: Desactivar o proteger con auth en producción.
    
    Body (opcional):
        {
            "to": "email@ejemplo.com"  // Opcional, usa ADMIN_EMAIL si no se proporciona
        }
    
    Returns:
        JSON con success: true si no hubo error aparente
    """
    try:
        from lib.email import send_email, ADMIN_EMAIL
        
        # Determinar destinatario
        recipient = None
        if input_data and input_data.to:
            recipient = input_data.to
        else:
            recipient = ADMIN_EMAIL
        
        if not recipient:
            return {
                "success": False,
                "error": "No se proporcionó destinatario y ADMIN_EMAIL no está configurado"
            }
        
        # Enviar email de prueba
        subject = "Prueba SMTP Codex"
        html_content = "<p>Este es un correo de prueba desde el backend de Codex Trader.</p>"
        
        # El envío se hace síncronamente pero no bloquea el servidor si falla
        # Si falla, send_email registra el error pero no lanza excepción
        result = send_email(
            to=recipient,
            subject=subject,
            html=html_content
        )
        
        if result:
            return {
                "success": True,
                "message": f"Email de prueba enviado a {recipient}"
            }
        else:
            return {
                "success": False,
                "error": "Error al enviar email (revisa los logs del servidor para más detalles)"
            }
            
    except Exception as e:
        # Capturar cualquier error inesperado
        print(f"ERROR: Error inesperado en test-email: {e}")
        return {
            "success": False,
            "error": f"Error inesperado: {str(e)}"
        }

# ============================================================================
# ENDPOINTS DE USUARIOS
# ============================================================================

# Endpoint para notificar registro de nuevo usuario
# RUTA: POST /users/notify-registration
# ARCHIVO: main.py (línea ~2025)
# IMPORTANTE: Este endpoint debe llamarse desde el frontend después del registro
# También puede llamarse con un token_hash de confirmación en el body
# O con user_id directamente (desde trigger de base de datos)
class NotifyRegistrationInput(BaseModel):
    token_hash: Optional[str] = None
    user_id: Optional[str] = None
    email: Optional[str] = None
    triggered_by: Optional[str] = None

@app.post("/users/notify-registration")
async def notify_user_registration(
    input_data: Optional[NotifyRegistrationInput] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Notifica al administrador sobre un nuevo registro de usuario.
    
    Este endpoint debe llamarse desde el frontend después de que un usuario
    se registra exitosamente. Envía un email al administrador con la información
    del nuevo usuario.
    
    Puede llamarse de dos formas:
    1. Con token de autenticación en el header (usuario ya logueado)
    2. Con token_hash de confirmación en el body (después de confirmar email)
    
    IMPORTANTE: El envío de email se hace en segundo plano y no bloquea la respuesta.
    """
    from datetime import datetime
    logger.info("=" * 60)
    logger.info("[API] POST /users/notify-registration recibido")
    logger.info(f"   Authorization header presente: {bool(authorization)}")
    logger.info(f"   Token_hash en body: {bool(input_data and input_data.token_hash)}")
    logger.info(f"   User_id en body: {bool(input_data and input_data.user_id)}")
    logger.info(f"   Triggered_by: {input_data.triggered_by if input_data else 'None'}")
    logger.info(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[API] POST /users/notify-registration recibido")
    print(f"   Authorization header presente: {bool(authorization)}")
    print(f"   Token_hash en body: {bool(input_data and input_data.token_hash)}")
    print(f"   User_id en body: {bool(input_data and input_data.user_id)}")
    print(f"   Triggered_by: {input_data.triggered_by if input_data else 'None'}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        user = None
        
        # Intentar obtener usuario desde el token de autenticación
        if authorization:
            try:
                logger.info("[DEBUG] Intentando obtener usuario desde token de autenticación...")
                logger.info(f"[DEBUG] Token (primeros 20 chars): {authorization[:20] if authorization else 'None'}...")
                print(f"   [DEBUG] Intentando obtener usuario desde token de autenticación...")
                print(f"   [DEBUG] Token (primeros 20 chars): {authorization[:20] if authorization else 'None'}...")
                user = await get_user(authorization)
                logger.info(f"[OK] Usuario obtenido desde token: {user.email if user else 'None'}")
                logger.info(f"[DEBUG] User ID: {user.id if user else 'None'}")
                print(f"   [OK] Usuario obtenido desde token: {user.email if user else 'None'}")
                print(f"   [DEBUG] User ID: {user.id if user else 'None'}")
            except HTTPException as e:
                logger.warning(f"[WARNING] Error al obtener usuario desde token: {e.detail}")
                logger.warning(f"[DEBUG] Status code: {e.status_code}")
                print(f"   [WARNING] Error al obtener usuario desde token: {e.detail}")
                print(f"   [DEBUG] Status code: {e.status_code}")
                # Si falla la autenticación, continuar para intentar con token_hash
                pass
            except Exception as e:
                logger.error(f"[ERROR] Excepción inesperada al obtener usuario: {e}", exc_info=True)
                print(f"   [ERROR] Excepción inesperada al obtener usuario: {e}")
                import traceback
                traceback.print_exc()
                pass
        
        # Si no hay usuario autenticado pero hay user_id (desde trigger), obtener usuario directamente
        if not user and input_data and input_data.user_id:
            try:
                print(f"   [TRIGGER] Intentando obtener usuario desde user_id: {input_data.user_id}")
                logger.info(f"[TRIGGER] Intentando obtener usuario desde user_id: {input_data.user_id}")
                # Obtener usuario directamente desde Supabase usando service key
                user_response = supabase_client.auth.admin.get_user_by_id(input_data.user_id)
                if user_response and user_response.user:
                    user = user_response.user
                    print(f"   [OK] Usuario obtenido desde user_id (trigger): {user.email if user else 'None'}")
                    logger.info(f"[OK] Usuario obtenido desde user_id (trigger): {user.email if user else 'None'}")
                else:
                    print(f"   [ERROR] No se pudo obtener usuario desde user_id")
                    logger.warning(f"[ERROR] No se pudo obtener usuario desde user_id: {input_data.user_id}")
            except Exception as e:
                print(f"   [ERROR] Error al obtener usuario desde user_id: {str(e)}")
                logger.error(f"[ERROR] Error al obtener usuario desde user_id: {str(e)}")
                # Continuar para intentar con token_hash si está disponible
        
        # Si no hay usuario autenticado pero hay token_hash, verificar el token_hash
        if not user and input_data and input_data.token_hash:
            try:
                print(f"   Intentando verificar token_hash...")
                # Verificar el token_hash con Supabase
                verify_response = supabase_client.auth.verify_otp({
                    "type": "email",
                    "token_hash": input_data.token_hash
                })
                if verify_response.user:
                    user = verify_response.user
                    print(f"   [OK] Usuario obtenido desde token_hash: {user.email if user else 'None'}")
                else:
                    print(f"   [ERROR] Token_hash invalido: no se obtuvo usuario")
                    raise HTTPException(
                        status_code=401,
                        detail="Token de confirmación inválido"
                    )
            except Exception as e:
                print(f"   [ERROR] Error al verificar token_hash: {str(e)}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Error al verificar token de confirmación: {str(e)}"
                )
        
        # Si aún no hay usuario, error
        if not user:
            print(f"   [ERROR] No se pudo obtener usuario. Authorization: {bool(authorization)}, Token_hash: {bool(input_data and input_data.token_hash)}, User_id: {bool(input_data and input_data.user_id)}")
            logger.error(f"[ERROR] No se pudo obtener usuario. Authorization: {bool(authorization)}, Token_hash: {bool(input_data and input_data.token_hash)}, User_id: {bool(input_data and input_data.user_id)}")
            raise HTTPException(
                status_code=401,
                detail="Se requiere autenticación (header Authorization), token_hash de confirmación, o user_id (desde trigger) en el body"
            )
        
        user_id = user.id
        user_email = user.email
        logger.info(f"[EMAIL] Procesando emails para usuario: {user_email} (ID: {user_id})")
        print(f"   [EMAIL] Procesando emails para usuario: {user_email} (ID: {user_id})")
        
        # PROTECCIÓN CONTRA DUPLICADOS: Verificar si ya se enviaron los emails de bienvenida
        # Usar un sistema de cache en memoria para evitar duplicados en la misma sesión
        # También verificar en la base de datos si existe un flag (opcional, se puede agregar después)
        import hashlib
        import time
        
        # Crear una clave única para este usuario en esta sesión
        cache_key = f"welcome_email_sent_{user_id}"
        
        # Cache simple en memoria (se puede mejorar con Redis en producción)
        if not hasattr(notify_user_registration, '_email_cache'):
            notify_user_registration._email_cache = {}
        
        # Limpiar cache antiguo (más de 1 hora)
        current_time = time.time()
        notify_user_registration._email_cache = {
            k: v for k, v in notify_user_registration._email_cache.items()
            if current_time - v < 3600  # 1 hora
        }
        
        # Verificar si ya se envió en los últimos 5 minutos
        if cache_key in notify_user_registration._email_cache:
            sent_time = notify_user_registration._email_cache[cache_key]
            time_since_sent = current_time - sent_time
            if time_since_sent < 300:  # 5 minutos
                logger.warning(f"[WARNING] Emails de bienvenida ya enviados recientemente para {user_email} (hace {int(time_since_sent)} segundos). Ignorando solicitud duplicada.")
                print(f"   [WARNING] Emails de bienvenida ya enviados recientemente. Ignorando solicitud duplicada.")
                return {
                    "success": True,
                    "message": "Emails ya fueron enviados anteriormente",
                    "already_sent": True
                }
        
        # Importar constantes de negocio y helpers de referidos
        from lib.business import (
            INITIAL_FREE_TOKENS,
            REF_INVITED_BONUS_TOKENS,
            REF_REFERRER_BONUS_TOKENS,
            REF_MAX_REWARDS,
            APP_NAME
        )
        from lib.referrals import assign_referral_code_if_needed, build_referral_url
        
        # IMPORTANTE: Asignar referral_code ANTES de obtener el perfil y enviar emails
        logger.info(f"[REFERRALS] Verificando/asignando referral_code para usuario {user_id}...")
        referral_code = assign_referral_code_if_needed(supabase_client, user_id)
        
        if not referral_code:
            logger.error(f"[REFERRALS] ERROR: No se pudo asignar referral_code al usuario {user_id}")
            # Intentar obtener el código del perfil como fallback
            try:
                profile_check = supabase_client.table("profiles").select("referral_code").eq("id", user_id).execute()
                if profile_check.data and profile_check.data[0].get("referral_code"):
                    referral_code = profile_check.data[0]["referral_code"]
                    logger.info(f"[REFERRALS] Código encontrado en perfil: {referral_code}")
                else:
                    referral_code = "No disponible"
                    logger.warning(f"[REFERRALS] Usuario {user_id} no tiene referral_code y no se pudo generar")
            except Exception as e:
                logger.error(f"[REFERRALS] Error al verificar código en perfil: {e}")
                referral_code = "No disponible"
        
        # Construir referral_url usando FRONTEND_URL
        referral_url = build_referral_url(referral_code)
        logger.info(f"[REFERRALS] Referral URL construida: {referral_url}")
        
        # Obtener información del perfil del usuario
        # Intentar obtener todas las columnas disponibles, manejando errores si alguna no existe
        try:
            # Primero intentar obtener todas las columnas (incluyendo referral_code si existe)
            profile_response = supabase_client.table("profiles").select(
                "referral_code, referred_by_user_id, current_plan, created_at, tokens_restantes, welcome_email_sent"
            ).eq("id", user_id).execute()
        except Exception as e:
            # Si falla porque referral_code no existe, intentar sin esa columna
            logger.warning(f"[WARNING] Error al obtener perfil con referral_code, intentando sin esa columna: {e}")
            try:
                profile_response = supabase_client.table("profiles").select(
                    "referred_by_user_id, current_plan, created_at, tokens_restantes"
                ).eq("id", user_id).execute()
            except Exception as e2:
                logger.error(f"[ERROR] Error al obtener perfil: {e2}")
                profile_response = None
        
        if not profile_response or not profile_response.data:
            # Si no hay perfil, el usuario acaba de registrarse
            # El perfil se creará automáticamente por el trigger
            profile_data = {}
        else:
            profile_data = profile_response.data[0]
        
        # Verificar si ya se envió el email de bienvenida (flag en base de datos)
        welcome_email_already_sent = profile_data.get("welcome_email_sent", False)
        if welcome_email_already_sent:
            logger.info(f"[EMAIL] Email de bienvenida ya fue enviado anteriormente para {user_email}. Saltando envío.")
            print(f"   [INFO] Email de bienvenida ya fue enviado anteriormente. Saltando envío.")
            return {
                "success": True,
                "message": "Email de bienvenida ya fue enviado anteriormente",
                "already_sent": True
            }
        
        # Asegurar que tenemos el referral_code (usar el que acabamos de asignar o el del perfil)
        if not referral_code or referral_code == "No disponible":
            referral_code = profile_data.get("referral_code") or referral_code or "No disponible"
        
        # Si aún no hay código, intentar asignarlo una vez más
        if not referral_code or referral_code == "No disponible":
            logger.warning(f"[REFERRALS] Reintentando asignar código...")
            referral_code = assign_referral_code_if_needed(supabase_client, user_id)
            if referral_code:
                referral_url = build_referral_url(referral_code)
                logger.info(f"[REFERRALS] Código asignado en segundo intento: {referral_code}")
        
        referred_by_id = profile_data.get("referred_by_user_id")
        current_plan = profile_data.get("current_plan")
        if not current_plan:
            current_plan = "Sin plan (modo prueba)"
        created_at = profile_data.get("created_at")
        initial_tokens = profile_data.get("tokens_restantes", INITIAL_FREE_TOKENS)
        
        # Obtener información del referrer si existe
        referrer_info = "No aplica"
        if referred_by_id:
            try:
                referrer_response = supabase_client.table("profiles").select("email").eq("id", referred_by_id).execute()
                if referrer_response.data:
                    referrer_info = f"{referrer_response.data[0].get('email', 'N/A')} (ID: {referred_by_id})"
                else:
                    referrer_info = f"ID: {referred_by_id}"
            except Exception:
                referrer_info = f"ID: {referred_by_id}"
        
        # IMPORTANTE: Enviar email de notificación al admin
        # Esto se hace en segundo plano y no bloquea la respuesta
        try:
            from lib.email import send_admin_email
            from datetime import datetime
            
            # Formatear fecha
            try:
                if created_at:
                    if isinstance(created_at, str):
                        if "T" in created_at:
                            date_obj = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            date_obj = datetime.fromisoformat(created_at)
                        formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        formatted_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    formatted_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                formatted_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h2 style="color: white; margin: 0; font-size: 24px;">Nuevo registro en Codex Trader</h2>
                </div>
                
                <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <p style="font-size: 16px; margin-bottom: 20px;">
                        Se ha registrado un nuevo usuario en Codex Trader.
                    </p>
                    
                    <div style="background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <ul style="list-style: none; padding: 0; margin: 0;">
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Email:</strong> 
                                <span style="color: #333;">{user_email}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">ID de usuario:</strong> 
                                <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Fecha de registro:</strong> 
                                <span style="color: #333;">{formatted_date}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Plan actual:</strong> 
                                <span style="color: #333;">{current_plan}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Tokens iniciales asignados:</strong> 
                                <span style="color: #333;">{INITIAL_FREE_TOKENS:,} tokens</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Código de referido:</strong> 
                                <span style="color: #333; font-family: monospace; font-weight: bold;">{referral_code if referral_code and referral_code != "No disponible" else "No disponible (error al generar)"}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Enlace de invitación:</strong> 
                                <span style="color: #333; font-size: 12px; word-break: break-all;">
                                    <a href="{referral_url}" style="color: #2563eb; text-decoration: none;">{referral_url}</a>
                                </span>
                            </li>
                            <li style="margin-bottom: 0;">
                                <strong style="color: #2563eb;">Registrado por referido:</strong> 
                                <span style="color: #333;">{referrer_info}</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Enviar email en segundo plano (no bloquea)
            # IMPORTANTE: Enviar directamente en lugar de usar threads para evitar problemas
            # Los threads pueden no ejecutarse correctamente en algunos entornos
            print(f"   [EMAIL] Enviando email al admin...")
            try:
                result = send_admin_email("Nuevo registro en Codex Trader", html_content)
                if result:
                    print(f"   [OK] Email al admin enviado correctamente")
                else:
                    print(f"   [ERROR] Error al enviar email al admin (revisa logs anteriores)")
            except Exception as e:
                print(f"   [ERROR] ERROR al enviar email al admin: {e}")
                import traceback
                traceback.print_exc()
        except Exception as email_error:
            # No es crítico si falla el email
            print(f"   [WARNING] No se pudo enviar email de notificacion de registro: {email_error}")
        
        # IMPORTANTE: Enviar email de bienvenida al usuario
        # Esto se hace en segundo plano y no bloquea la respuesta
        try:
            from lib.email import send_email
            
            # Construir enlaces usando FRONTEND_URL (normalizar sin barra final)
            base_url = FRONTEND_URL.rstrip('/')
            # Usar build_referral_url para consistencia (usa /?ref= en lugar de /registro?ref=)
            referral_url = build_referral_url(referral_code)
            app_url = base_url  # Usar la raíz del sitio, no /app
            
            # Obtener nombre del usuario desde el email (parte antes del @)
            user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
            
            welcome_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">🧠📈 Bienvenido a Codex Trader</h1>
                </div>
                
                <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <!-- Bloque: Tu cuenta -->
                    <div style="margin-bottom: 30px;">
                        <p style="font-size: 16px; margin-bottom: 20px;">
                            Hola <strong>{user_email}</strong>, bienvenido a Codex Trader.
                        </p>
                        
                        <div style="background: #f9fafb; padding: 20px; border-radius: 8px; border-left: 4px solid #2563eb;">
                            <ul style="list-style: none; padding: 0; margin: 0;">
                                <li style="margin-bottom: 10px; color: #333;">
                                    <strong>Plan actual:</strong> Modo prueba (sin suscripción)
                                </li>
                                <li style="margin-bottom: 10px; color: #333;">
                                    <strong>Tokens iniciales:</strong> {INITIAL_FREE_TOKENS:,} para probar el asistente
                                </li>
                                <li style="margin-bottom: 0; color: #333;">
                                    <strong>Acceso al asistente:</strong> 
                                    <a href="{app_url}" style="color: #2563eb; text-decoration: none; font-weight: bold;">Empieza aquí</a>
                                </li>
                            </ul>
                        </div>
                    </div>
                    
                    <!-- Bloque: ¿Qué puedes hacer con Codex? -->
                    <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb;">
                        <h3 style="color: #2563eb; margin-top: 0; font-size: 18px;">¿Qué puedes hacer con Codex?</h3>
                        <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                            <li style="margin-bottom: 10px;">Pedir explicaciones claras sobre gestión de riesgo, tamaño de posición y drawdown.</li>
                            <li style="margin-bottom: 10px;">Profundizar en psicología del trader y disciplina.</li>
                            <li style="margin-bottom: 10px;">Analizar setups, ideas de estrategia y marcos temporales.</li>
                            <li style="margin-bottom: 0;">Usarlo como cerebro de estudio apoyado en contenido profesional de trading.</li>
                        </ul>
                    </div>
                    
                    <!-- Botón de llamada a la acción -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{app_url}" style="display: inline-block; background: #2563eb; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            🚀 Empieza aquí
                        </a>
                    </div>
                    
                    <!-- Bloque: Invita a tus amigos y gana tokens -->
                    <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 30px 0; border-left: 4px solid #f59e0b;">
                        <h3 style="color: #92400e; margin-top: 0; font-size: 18px;">💎 Invita a tus amigos y gana tokens</h3>
                        <p style="margin-bottom: 15px; color: #78350f;">
                            Comparte tu enlace personal y ambos ganan:
                        </p>
                        <ul style="margin: 15px 0; padding-left: 20px; color: #78350f;">
                            <li style="margin-bottom: 10px;">
                                Tu amigo recibe <strong>+{REF_INVITED_BONUS_TOKENS:,} tokens de bienvenida</strong> cuando activa su primer plan de pago.
                            </li>
                            <li style="margin-bottom: 15px;">
                                Tú ganas <strong>+{REF_REFERRER_BONUS_TOKENS:,} tokens</strong> por cada amigo que pague su primer plan (hasta {REF_MAX_REWARDS} referidos con recompensa completa).
                            </li>
                        </ul>
                        <div style="background: white; padding: 15px; border-radius: 6px; margin: 15px 0; border: 2px dashed #d97706;">
                            <p style="margin: 5px 0; font-size: 14px; color: #666;"><strong>Tu código de referido:</strong></p>
                            <p style="margin: 5px 0; font-size: 18px; font-weight: bold; color: #2563eb; word-break: break-all; font-family: monospace;">{referral_code if referral_code and referral_code != "No disponible" else "Se generará en unos minutos"}</p>
                            <p style="margin: 10px 0 5px 0; font-size: 14px; color: #666;"><strong>Tu enlace de invitación:</strong></p>
                            <p style="margin: 5px 0; font-size: 14px; color: #2563eb; word-break: break-all;">
                                <a href="{referral_url}" style="color: #2563eb; text-decoration: none;">{referral_url}</a>
                            </p>
                        </div>
                    </div>
                    
                    <!-- Bloque final: Disclaimer -->
                    <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                        Codex Trader es una herramienta educativa. No ofrecemos asesoría financiera personalizada ni recomendaciones directas de compra/venta. Los resultados pasados no garantizan rendimientos futuros. Cada cliente es responsable de sus decisiones en el mercado.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Verificar configuración SMTP antes de intentar enviar
            from lib.email import SMTP_AVAILABLE, SMTP_HOST, SMTP_USER, EMAIL_FROM
            logger.info("[EMAIL] ========================================")
            logger.info("[EMAIL] INICIANDO ENVIO DE EMAIL DE BIENVENIDA")
            logger.info("[EMAIL] ========================================")
            logger.info(f"[EMAIL] SMTP_AVAILABLE: {SMTP_AVAILABLE}")
            logger.info(f"[EMAIL] SMTP_HOST: {SMTP_HOST}")
            logger.info(f"[EMAIL] SMTP_USER: {SMTP_USER}")
            logger.info(f"[EMAIL] EMAIL_FROM: {EMAIL_FROM}")
            logger.info(f"[EMAIL] Destinatario: {user_email}")
            print(f"   [EMAIL] ========================================")
            print(f"   [EMAIL] INICIANDO ENVIO DE EMAIL DE BIENVENIDA")
            print(f"   [EMAIL] ========================================")
            print(f"   [EMAIL] SMTP_AVAILABLE: {SMTP_AVAILABLE}")
            print(f"   [EMAIL] SMTP_HOST: {SMTP_HOST}")
            print(f"   [EMAIL] SMTP_USER: {SMTP_USER}")
            print(f"   [EMAIL] EMAIL_FROM: {EMAIL_FROM}")
            print(f"   [EMAIL] Destinatario: {user_email}")
            
            if not SMTP_AVAILABLE:
                logger.error("[ERROR] SMTP no está configurado. No se puede enviar email de bienvenida.")
                logger.error("[ERROR] Verifica que estas variables estén configuradas en Railway:")
                logger.error("[ERROR]   - SMTP_HOST")
                logger.error("[ERROR]   - SMTP_USER")
                logger.error("[ERROR]   - SMTP_PASS")
                logger.error("[ERROR]   - EMAIL_FROM")
                print(f"   [ERROR] SMTP no está configurado. Verifica variables de entorno en Railway.")
            else:
                logger.info(f"[EMAIL] Enviando email de bienvenida a {user_email}...")
                print(f"   [EMAIL] Enviando email de bienvenida a {user_email}...")
                try:
                    result = send_email(
                        to=user_email,
                        subject="🧠📈 Bienvenido a Codex Trader",
                        html=welcome_html
                    )
                    logger.info(f"[EMAIL] Resultado de send_email: {result}")
                    print(f"   [EMAIL] Resultado de send_email: {result}")
                    if result:
                        logger.info(f"[OK] Email de bienvenida enviado correctamente a {user_email}")
                        print(f"   [OK] Email de bienvenida enviado correctamente a {user_email}")
                        
                        # Marcar flag en base de datos para evitar duplicados
                        try:
                            supabase_client.table("profiles").update({
                                "welcome_email_sent": True
                            }).eq("id", user_id).execute()
                            logger.info(f"[OK] Flag welcome_email_sent marcado en base de datos para {user_id}")
                            print(f"   [OK] Flag welcome_email_sent marcado en base de datos")
                        except Exception as flag_error:
                            logger.warning(f"[WARNING] No se pudo marcar flag welcome_email_sent: {flag_error}")
                            print(f"   [WARNING] No se pudo marcar flag welcome_email_sent (no crítico)")
                    else:
                        logger.error("[ERROR] Error al enviar email de bienvenida (revisa logs anteriores)")
                        print(f"   [ERROR] Error al enviar email de bienvenida (revisa logs anteriores)")
                        print(f"   [ERROR] Verifica SMTP_AVAILABLE y configuración de email")
                        # NO marcar cache ni flag si el email falló
                        raise Exception("Email de bienvenida falló al enviarse")
                except Exception as e:
                    logger.error(f"[ERROR] ERROR al enviar email de bienvenida: {e}", exc_info=True)
                    print(f"   [ERROR] ERROR al enviar email de bienvenida: {e}")
                    import traceback
                    traceback.print_exc()
                    # NO marcar cache ni flag si el email falló
                    raise  # Re-lanzar el error para que no se marque el cache
            logger.info("[EMAIL] ========================================")
            print(f"   [EMAIL] ========================================")
        except Exception as welcome_error:
            # Si falla el email de bienvenida, NO marcar cache ni flag
            logger.error(f"[ERROR] No se pudo enviar email de bienvenida: {welcome_error}")
            print(f"   [ERROR] No se pudo enviar email de bienvenida: {welcome_error}")
            # NO marcar cache - permitir reintentos
            return {
                "success": False,
                "message": f"Error al enviar email de bienvenida: {str(welcome_error)}",
                "error": "smtp_error"
            }
        
        # Marcar en cache que los emails fueron enviados (SOLO si llegamos aquí sin errores)
        try:
            notify_user_registration._email_cache[cache_key] = time.time()
            logger.info(f"[OK] Emails enviados y marcados en cache para {user_email}")
        except:
            pass  # Si falla el cache, no es crítico
        
        logger.info("[OK] Endpoint completado exitosamente. Emails enviados directamente.")
        print(f"   [OK] Endpoint completado exitosamente. Emails enviados directamente.")
        return {
            "success": True,
            "message": "Registro notificado correctamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # No lanzar error, solo registrar
        logger.error("=" * 60)
        logger.error(f"[ERROR] ERROR en endpoint notify-registration: {str(e)}", exc_info=True)
        logger.error("=" * 60)
        print(f"   [ERROR] ERROR en endpoint notify-registration: {str(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "message": "Error al notificar registro, pero el usuario fue creado correctamente"
        }

# ============================================================================
# ENDPOINTS DE REFERIDOS
# ============================================================================

# Endpoint para obtener resumen de estadísticas de referidos
# RUTA: GET /me/referrals-summary
# ARCHIVO: main.py (línea ~1695)
@app.get("/me/referrals-summary")
async def get_referrals_summary(user = Depends(get_user)):
    """
    Obtiene un resumen de estadísticas de referidos del usuario actual.
    
    Retorna:
    - totalInvited: Total de usuarios que se registraron con el código de referido
    - totalPaid: Total de usuarios que pagaron su primera suscripción
    - referralRewardsCount: Cantidad de referidos que ya generaron recompensa (máximo 5)
    - referralTokensEarned: Tokens totales ganados por referidos
    - referralCode: Código de referido del usuario
    """
    try:
        user_id = user.id
        
        # Obtener información del perfil del usuario
        profile_response = supabase_client.table("profiles").select(
            "referral_code, referral_rewards_count, referral_tokens_earned"
        ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        referral_code = profile.get("referral_code")
        referral_rewards_count = profile.get("referral_rewards_count", 0)
        referral_tokens_earned = profile.get("referral_tokens_earned", 0)
        
        # Contar total de usuarios que se registraron con este código de referido
        total_invited_response = supabase_client.table("profiles").select(
            "id"
        ).eq("referred_by_user_id", user_id).execute()
        
        total_invited = len(total_invited_response.data) if total_invited_response.data else 0
        
        # Contar usuarios que ya pagaron (tienen has_generated_referral_reward = true)
        total_paid_response = supabase_client.table("profiles").select(
            "id"
        ).eq("referred_by_user_id", user_id).eq("has_generated_referral_reward", True).execute()
        
        total_paid = len(total_paid_response.data) if total_paid_response.data else 0
        
        return {
            "totalInvited": total_invited,
            "totalPaid": total_paid,
            "referralRewardsCount": referral_rewards_count,
            "referralTokensEarned": referral_tokens_earned,
            "referralCode": referral_code
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener resumen de referidos: {str(e)}"
        )

# Modelo para procesar referido
class ProcessReferralInput(BaseModel):
    referral_code: str  # Código de referido del usuario que invitó

# Endpoint para procesar un código de referido después del registro
# RUTA: POST /referrals/process
# ARCHIVO: main.py (línea ~1370)
@app.post("/referrals/process")
async def process_referral(
    referral_input: ProcessReferralInput,
    user = Depends(get_user)
):
    """
    Procesa un código de referido después del registro de un usuario.
    
    Este endpoint debe llamarse después de que un usuario se registra con un código
    de referido (por ejemplo, desde ?ref=XXXX en la URL de registro).
    
    Recibe:
    - referral_code: Código de referido del usuario que invitó
    
    Actualiza:
    - referred_by_user_id: ID del usuario que invitó
    
    Retorna:
    - success: True si se procesó correctamente
    - message: Mensaje descriptivo
    """
    try:
        user_id = user.id
        referral_code = referral_input.referral_code.strip().upper()
        
        if not referral_code:
            raise HTTPException(
                status_code=400,
                detail="El código de referido no puede estar vacío"
            )
        
        # Verificar que el usuario no tenga ya un referido asignado
        profile_response = supabase_client.table("profiles").select("referred_by_user_id").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        existing_referrer = profile_response.data[0].get("referred_by_user_id")
        if existing_referrer:
            raise HTTPException(
                status_code=400,
                detail="Este usuario ya tiene un referido asignado"
            )
        
        # Verificar que el usuario no se esté refiriendo a sí mismo
        user_profile = supabase_client.table("profiles").select("referral_code").eq("id", user_id).execute()
        if user_profile.data and user_profile.data[0].get("referral_code") == referral_code:
            raise HTTPException(
                status_code=400,
                detail="No puedes usar tu propio código de referido"
            )
        
        # Buscar al usuario que tiene ese código de referido
        referrer_response = supabase_client.table("profiles").select("id, email, referral_code").eq("referral_code", referral_code).execute()
        
        if not referrer_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Código de referido inválido: {referral_code}"
            )
        
        referrer_id = referrer_response.data[0]["id"]
        
        # Actualizar el perfil del usuario con referred_by_user_id
        update_response = supabase_client.table("profiles").update({
            "referred_by_user_id": referrer_id
        }).eq("id", user_id).execute()
        
        if update_response.data:
            # Aplicar bono de bienvenida de 5,000 tokens al usuario referido
            welcome_bonus = 5000
            add_tokens_to_user(user_id, welcome_bonus, "Bono de bienvenida por referido")
            
            # IMPORTANTE: Enviar email de notificación al admin sobre nuevo registro
            # Esto se hace en segundo plano y no bloquea la respuesta
            try:
                from lib.email import send_admin_email
                from datetime import datetime
                
                # Obtener información del usuario y referrer para el email
                user_email = user.email
                referrer_email = referrer_response.data[0].get('email', 'N/A')
                
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <h2 style="color: #2563eb;">Nuevo registro en Codex Trader</h2>
                    <p>Se ha registrado un nuevo usuario en Codex Trader.</p>
                    <ul>
                        <li><strong>Email:</strong> {user_email}</li>
                        <li><strong>Fecha de registro:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</li>
                        <li><strong>Registrado por referido:</strong> {referrer_email} (ID: {referrer_id})</li>
                        <li><strong>Código de referido usado:</strong> {referral_code}</li>
                    </ul>
                </body>
                </html>
                """
                
                # Enviar email en segundo plano (no bloquea)
                # Usar threading para ejecutar en background
                import threading
                def send_email_background():
                    try:
                        send_admin_email("Nuevo registro en Codex Trader", html_content)
                    except Exception as e:
                        print(f"WARNING: Error al enviar email en background: {e}")
                
                email_thread = threading.Thread(target=send_email_background, daemon=True)
                email_thread.start()
            except Exception as email_error:
                # No es crítico si falla el email
                print(f"WARNING: No se pudo enviar email de notificación de registro: {email_error}")
            
            return {
                "success": True,
                "message": f"Referido procesado correctamente. Fuiste referido por {referrer_response.data[0].get('email', 'usuario')}. ¡Recibiste {welcome_bonus:,} tokens de bienvenida!",
                "referrer_id": referrer_id,
                "welcome_bonus": welcome_bonus
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar el perfil con el referido"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar referido: {str(e)}"
        )

# Endpoint para obtener información del referido del usuario actual
# RUTA: GET /referrals/info
# ARCHIVO: main.py (línea ~1450)
@app.get("/referrals/info")
async def get_referral_info(user = Depends(get_user)):
    """
    Obtiene información sobre el sistema de referidos del usuario actual.
    
    Retorna:
    - referral_code: Código de referido del usuario
    - referred_by_user_id: ID del usuario que lo invitó (si aplica)
    - referral_rewards_count: Cantidad de referidos que han generado recompensa
    - referral_tokens_earned: Tokens totales obtenidos por referidos
    """
    try:
        user_id = user.id
        
        profile_response = supabase_client.table("profiles").select(
            "referral_code, referred_by_user_id, referral_rewards_count, referral_tokens_earned"
        ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        
        return {
            "referral_code": profile.get("referral_code"),
            "referred_by_user_id": profile.get("referred_by_user_id"),
            "referral_rewards_count": profile.get("referral_rewards_count", 0),
            "referral_tokens_earned": profile.get("referral_tokens_earned", 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener información de referidos: {str(e)}"
        )

# ============================================================================
# ENDPOINTS DE CHAT SESSIONS
# ============================================================================

# Endpoint para eliminar una conversación
@app.delete("/chat-sessions/{conversation_id}")
async def delete_chat_session(conversation_id: str, user = Depends(get_user)):
    """
    Endpoint para eliminar una sesión de chat y todos sus mensajes.
    """
    try:
        user_id = user.id
        
        # Verificar que la conversación pertenezca al usuario
        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada o no pertenece al usuario"
            )
        
        # Eliminar la sesión (los mensajes se eliminarán automáticamente por CASCADE)
        supabase_client.table("chat_sessions").delete().eq("id", conversation_id).execute()
        
        return {
            "message": "Conversación eliminada exitosamente"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al eliminar conversación: {str(e)}"
        )

# Endpoint para actualizar el título de una conversación
@app.patch("/chat-sessions/{conversation_id}")
async def update_chat_session(conversation_id: str, title: str, user = Depends(get_user)):
    """
    Endpoint para actualizar el título de una sesión de chat.
    """
    try:
        user_id = user.id
        
        # Verificar que la conversación pertenezca al usuario
        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada o no pertenece al usuario"
            )
        
        # Actualizar el título
        updated_session = supabase_client.table("chat_sessions").update({
            "title": title,
            "updated_at": "now()"
        }).eq("id", conversation_id).execute()
        
        if not updated_session.data:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar conversación"
            )
        
        return {
            "session": updated_session.data[0],
            "message": "Título actualizado exitosamente"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar conversación: {str(e)}"
        )

# Ejecutar el servidor
if __name__ == "__main__":
    import socket
    
    # Función para encontrar un puerto disponible
    def find_free_port(start_port=8000):
        port = start_port
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('0.0.0.0', port))
                    return port
            except OSError:
                port += 1
                if port > start_port + 10:  # Limitar búsqueda a 10 puertos
                    raise Exception(f"No se pudo encontrar un puerto disponible entre {start_port} y {start_port + 10}")
    
    # Railway y otras plataformas proporcionan PORT como variable de entorno
    # Si no está disponible, usar 8000 por defecto (desarrollo local)
    port = int(os.getenv("PORT", 8000))
    print(f"✓ Iniciando servidor en puerto {port}")
    
    # Importar webhook de nuevo usuario (solución alternativa)
    try:
        from webhook_new_user import create_webhook_endpoint
        create_webhook_endpoint(app, supabase_client)
        print("Webhook de nuevo usuario configurado correctamente")
    except Exception as e:
        print(f"WARNING: No se pudo configurar webhook de nuevo usuario: {e}")
    
    # ============================================================================
    # ENDPOINTS PARA EMAILS PROGRAMADOS (Recordatorio de Renovación y Recuperación)
    # ============================================================================
    
    @app.post("/admin/send-renewal-reminders")
    async def send_renewal_reminders(user = Depends(get_user)):
        """
        Envía emails de recordatorio de renovación a usuarios cuya suscripción vence en 3 días.
        
        IMPORTANTE: Este endpoint es solo para administradores.
        Se puede ejecutar manualmente o programar con un cron job.
        """
        if not is_admin_user(user):
            raise HTTPException(
                status_code=403,
                detail="Acceso denegado. Este endpoint es solo para administradores."
            )
        
        try:
            from lib.email import send_email
            from datetime import datetime, timedelta
            import threading
            
            # Calcular fecha objetivo (3 días desde ahora)
            target_date = datetime.utcnow() + timedelta(days=3)
            target_date_str = target_date.strftime('%Y-%m-%d')
            
            # Buscar usuarios con current_period_end en 3 días (con margen de 1 día)
            start_date = target_date - timedelta(days=1)
            end_date = target_date + timedelta(days=1)
            
            # Obtener usuarios con suscripciones activas que vencen en ~3 días
            profiles_response = supabase_client.table("profiles").select(
                "id, email, current_plan, current_period_end, renewal_reminder_sent"
            ).not_.is_("current_period_end", "null").not_.eq("current_plan", "null").execute()
            
            if not profiles_response.data:
                return {
                    "status": "success",
                    "message": "No se encontraron usuarios con suscripciones activas",
                    "reminders_sent": 0
                }
            
            reminders_sent = 0
            errors = []
            
            for profile in profiles_response.data:
                try:
                    period_end_str = profile.get("current_period_end")
                    if not period_end_str:
                        continue
                    
                    # Parsear fecha
                    if isinstance(period_end_str, str):
                        if "T" in period_end_str:
                            period_end = datetime.fromisoformat(period_end_str.replace("Z", "+00:00"))
                        else:
                            period_end = datetime.fromisoformat(period_end_str)
                    else:
                        continue
                    
                    # Verificar si está dentro del rango (2-4 días)
                    days_until_renewal = (period_end - datetime.utcnow()).days
                    
                    if 2 <= days_until_renewal <= 4:
                        # Verificar si ya se envió el recordatorio
                        if profile.get("renewal_reminder_sent", False):
                            continue
                        
                        user_email = profile.get("email")
                        user_id = profile.get("id")
                        current_plan = profile.get("current_plan", "N/A")
                        
                        if not user_email:
                            continue
                        
                        # Obtener nombre del plan
                        plan_name = current_plan
                        from plans import get_plan_by_code
                        plan_info = get_plan_by_code(current_plan)
                        if plan_info:
                            plan_name = plan_info.name
                        
                        def send_renewal_reminder_email():
                            try:
                                user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                                renewal_date = period_end.strftime('%d/%m/%Y')
                                
                                # Construir URL de billing antes del f-string
                                import os
                                frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                                billing_url = f"{frontend_url.rstrip('/')}/billing"  # Mantener /billing para facturación
                                
                                html = f"""
                                <html>
                                <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                    <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                        <h1 style="color: white; margin: 0; font-size: 28px;">⏰ Recordatorio de Renovación</h1>
                                    </div>
                                    
                                    <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            Hola <strong>{user_name}</strong>,
                                        </p>
                                        
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            Tu suscripción al plan <strong>{plan_name}</strong> se renovará automáticamente en <strong>{days_until_renewal} días</strong> (el {renewal_date}).
                                        </p>
                                        
                                        <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                                            <h3 style="color: #92400e; margin-top: 0; font-size: 18px;">📋 Resumen de tu suscripción:</h3>
                                            <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                                                <li style="margin-bottom: 10px;"><strong>Plan actual:</strong> {plan_name}</li>
                                                <li style="margin-bottom: 10px;"><strong>Próxima renovación:</strong> {renewal_date}</li>
                                                <li style="margin-bottom: 0;"><strong>Días restantes:</strong> {days_until_renewal} días</li>
                                            </ul>
                                        </div>
                                        
                                        <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                            <h3 style="color: #059669; margin-top: 0; font-size: 18px;">💡 ¿Qué debes saber?</h3>
                                            <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                                                <li style="margin-bottom: 10px;">La renovación es automática, no necesitas hacer nada</li>
                                                <li style="margin-bottom: 10px;">Se cargará el monto correspondiente a tu método de pago registrado</li>
                                                <li style="margin-bottom: 0;">Recibirás tus tokens mensuales al momento de la renovación</li>
                                            </ul>
                                        </div>
                                        
                                        <div style="text-align: center; margin: 30px 0;">
                                            <a href="{billing_url}" style="display: inline-block; background: #f59e0b; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                                Ver Detalles de Facturación
                                            </a>
                                        </div>
                                        
                                        <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                            Si deseas cancelar o modificar tu suscripción, puedes hacerlo desde tu panel de cuenta.
                                        </p>
                                    </div>
                                </body>
                                </html>
                                """
                                
                                send_email(
                                    to=user_email,
                                    subject=f"⏰ Recordatorio: Tu suscripción se renueva en {days_until_renewal} días - Codex Trader",
                                    html=html
                                )
                                
                                # Marcar que el recordatorio fue enviado
                                supabase_client.table("profiles").update({
                                    "renewal_reminder_sent": True
                                }).eq("id", user_id).execute()
                                
                                print(f"✅ Recordatorio de renovación enviado a {user_email}")
                            except Exception as e:
                                print(f"⚠️ Error al enviar recordatorio a {user_email}: {e}")
                                errors.append(f"Error con {user_email}: {str(e)}")
                        
                        email_thread = threading.Thread(target=send_renewal_reminder_email, daemon=True)
                        email_thread.start()
                        reminders_sent += 1
                        
                except Exception as e:
                    errors.append(f"Error procesando perfil: {str(e)}")
                    continue
            
            return {
                "status": "success",
                "message": f"Proceso completado. {reminders_sent} recordatorios enviados.",
                "reminders_sent": reminders_sent,
                "errors": errors if errors else None
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al enviar recordatorios de renovación: {str(e)}"
            )
    
    @app.post("/admin/send-inactive-user-recovery")
    async def send_inactive_user_recovery(
        days_inactive: int = Query(30, description="Días de inactividad para considerar usuario inactivo"),
        user = Depends(get_user)
    ):
        """
        Envía emails de recuperación a usuarios inactivos.
        
        IMPORTANTE: Este endpoint es solo para administradores.
        Se puede ejecutar manualmente o programar con un cron job.
        
        Parámetros:
        - days_inactive: Número de días de inactividad (default: 30)
        """
        if not is_admin_user(user):
            raise HTTPException(
                status_code=403,
                detail="Acceso denegado. Este endpoint es solo para administradores."
            )
        
        try:
            from lib.email import send_email
            from datetime import datetime, timedelta
            import threading
            
            # Calcular fecha límite de inactividad
            inactive_since = datetime.utcnow() - timedelta(days=days_inactive)
            
            # Buscar usuarios inactivos (sin actividad reciente en conversations o chat_sessions)
            # Primero obtener todos los usuarios con perfiles
            profiles_response = supabase_client.table("profiles").select(
                "id, email, current_plan, created_at, inactive_recovery_email_sent"
            ).execute()
            
            if not profiles_response.data:
                return {
                    "status": "success",
                    "message": "No se encontraron usuarios",
                    "emails_sent": 0
                }
            
            emails_sent = 0
            errors = []
            
            for profile in profiles_response.data:
                try:
                    user_id = profile.get("id")
                    user_email = profile.get("email")
                    
                    if not user_email:
                        continue
                    
                    # Verificar si ya se envió el email de recuperación
                    if profile.get("inactive_recovery_email_sent", False):
                        continue
                    
                    # Buscar última actividad en conversations
                    last_activity = None
                    try:
                        conversations_response = supabase_client.table("conversations").select(
                            "updated_at"
                        ).eq("user_id", user_id).order("updated_at", desc=True).limit(1).execute()
                        
                        if conversations_response.data:
                            last_activity_str = conversations_response.data[0].get("updated_at")
                            if last_activity_str:
                                if isinstance(last_activity_str, str):
                                    if "T" in last_activity_str:
                                        last_activity = datetime.fromisoformat(last_activity_str.replace("Z", "+00:00"))
                                    else:
                                        last_activity = datetime.fromisoformat(last_activity_str)
                    except Exception:
                        pass
                    
                    # Si no hay actividad en conversations, usar created_at del perfil
                    if not last_activity:
                        created_at_str = profile.get("created_at")
                        if created_at_str:
                            if isinstance(created_at_str, str):
                                if "T" in created_at_str:
                                    last_activity = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                                else:
                                    last_activity = datetime.fromisoformat(created_at_str)
                    
                    # Verificar si el usuario está inactivo
                    if last_activity and last_activity < inactive_since:
                        def send_recovery_email():
                            try:
                                user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                                days_since_activity = (datetime.utcnow() - last_activity).days
                                
                                # Construir URL del app antes del f-string
                                import os
                                frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                                app_url = frontend_url.rstrip('/')  # Usar la raíz del sitio, no /app
                                
                                html = f"""
                                <html>
                                <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                    <div style="background: linear-gradient(135deg, #8b5cf6 0%, #7c3aed 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                        <h1 style="color: white; margin: 0; font-size: 28px;">👋 Te Extrañamos en Codex Trader</h1>
                                    </div>
                                    
                                    <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            Hola <strong>{user_name}</strong>,
                                        </p>
                                        
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            Hace <strong>{days_since_activity} días</strong> que no te vemos por Codex Trader. ¡Esperamos que vuelvas pronto!
                                        </p>
                                        
                                        <div style="background: #f3e8ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #8b5cf6;">
                                            <h3 style="color: #7c3aed; margin-top: 0; font-size: 18px;">💡 ¿Sabías que...?</h3>
                                            <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                                                <li style="margin-bottom: 10px;">Puedes hacer preguntas sobre gestión de riesgo y análisis técnico</li>
                                                <li style="margin-bottom: 10px;">Tienes acceso a una biblioteca profesional de trading</li>
                                                <li style="margin-bottom: 0;">El asistente está disponible 24/7 para ayudarte</li>
                                            </ul>
                                        </div>
                                        
                                        <div style="text-align: center; margin: 30px 0;">
                                            <a href="{app_url}" style="display: inline-block; background: #8b5cf6; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                                🚀 Volver a Codex Trader
                                            </a>
                                        </div>
                                        
                                        <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                            Si tienes alguna pregunta o sugerencia, no dudes en contactarnos.
                                        </p>
                                    </div>
                                </body>
                                </html>
                                """
                                
                                send_email(
                                    to=user_email,
                                    subject="👋 Te extrañamos en Codex Trader - Vuelve pronto",
                                    html=html
                                )
                                
                                # Marcar que el email fue enviado
                                supabase_client.table("profiles").update({
                                    "inactive_recovery_email_sent": True
                                }).eq("id", user_id).execute()
                                
                                print(f"✅ Email de recuperación enviado a {user_email}")
                            except Exception as e:
                                print(f"⚠️ Error al enviar email de recuperación a {user_email}: {e}")
                                errors.append(f"Error con {user_email}: {str(e)}")
                        
                        email_thread = threading.Thread(target=send_recovery_email, daemon=True)
                        email_thread.start()
                        emails_sent += 1
                        
                except Exception as e:
                    errors.append(f"Error procesando perfil: {str(e)}")
                    continue
            
            return {
                "status": "success",
                "message": f"Proceso completado. {emails_sent} emails de recuperación enviados.",
                "emails_sent": emails_sent,
                "days_inactive": days_inactive,
                "errors": errors if errors else None
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error al enviar emails de recuperación: {str(e)}"
            )
    
    uvicorn.run(app, host="0.0.0.0", port=port)

