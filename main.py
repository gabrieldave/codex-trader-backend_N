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

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request, BackgroundTasks
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

# IMPORTANTE: Inicializar dependencias compartidas ANTES de incluir routers
from lib.dependencies import init_dependencies, get_user
from lib.config_shared import init_shared_config

# Obtener ADMIN_EMAILS para init_dependencies
ADMIN_EMAILS_ENV = get_env("ADMIN_EMAILS")
ADMIN_EMAILS_LIST = []
if ADMIN_EMAILS_ENV:
    ADMIN_EMAILS_LIST = [email.strip() for email in ADMIN_EMAILS_ENV.split(",") if email.strip()]

# Obtener SUPABASE_ANON_KEY para init_dependencies
SUPABASE_ANON_KEY = get_env("SUPABASE_ANON_KEY")

# Inicializar dependencias compartidas
init_dependencies(
    client=supabase_client,
    rest_url=SUPABASE_REST_URL,
    service_key=SUPABASE_SERVICE_KEY,
    anon_key=SUPABASE_ANON_KEY,
    admin_emails=ADMIN_EMAILS_LIST
)

# Inicializar configuración compartida
init_shared_config(
    client=supabase_client,
    chat_model=modelo_por_defecto,
    embedder=local_embedder,
    rag_available=RAG_AVAILABLE,
    stripe_available=STRIPE_AVAILABLE,
    frontend_url=FRONTEND_URL,
    backend_url=BACKEND_URL,
    deepseek_key=DEEPSEEK_API_KEY,
    openai_key=OPENAI_API_KEY,
    anthropic_key=ANTHROPIC_API_KEY,
    google_key=GOOGLE_API_KEY,
    cohere_key=COHERE_API_KEY
)

logger.info("✅ Dependencias compartidas inicializadas")

# Importar y registrar todos los routers (después de inicializar dependencias)
try:
    from routers.admin import admin_router
    app.include_router(admin_router)
    logger.info("✅ Router de administración registrado")
except Exception as e:
    logger.warning(f"⚠️ No se pudo registrar router de administración: {e}")

try:
    from routers.chat import chat_router
    app.include_router(chat_router)
    logger.info("✅ Router de chat registrado")
except Exception as e:
    logger.warning(f"⚠️ No se pudo registrar router de chat: {e}")

try:
    from routers.billing import billing_router
    app.include_router(billing_router)
    logger.info("✅ Router de billing registrado")
except Exception as e:
    logger.warning(f"⚠️ No se pudo registrar router de billing: {e}")

try:
    from routers.users import users_router
    app.include_router(users_router)
    logger.info("✅ Router de usuarios registrado")
except Exception as e:
    logger.warning(f"⚠️ No se pudo registrar router de usuarios: {e}")

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

# NOTA: Las funciones get_user y get_user_supabase_client ahora están en lib.dependencies
# Los modelos QueryInput, NewConversationInput, etc. ahora están en routers.models
# Los endpoints de chat ahora están en routers.chat

# Endpoints raíz y de salud (se mantienen en main.py)

# Endpoint raíz para verificar que el servidor está funcionando
@app.get("/")
async def root():
    """
    Endpoint raíz para verificar que el servidor está funcionando.
    """
    return {
        "message": "Codex Trader API está funcionando",
        "status": "ready",
        "version": "modular",
        "routers": {
            "admin": "/admin",
            "chat": "/chat",
            "billing": "/billing",
            "users": "/tokens, /me, /users, /referrals"
        },
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

# Las funciones is_admin_user y get_admin_user ahora están en lib.dependencies
# Los endpoints de admin ahora están en routers.admin
# Los endpoints de usuarios ahora están en routers.users
# Los endpoints de referidos ahora están en routers.users
