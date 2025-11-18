import os
import sys
import time
import json
import shutil

# Configurar DEEPSEEK_API_KEY antes de importar litellm
if not os.getenv("DEEPSEEK_API_KEY"):
    os.environ["DEEPSEEK_API_KEY"] = "sk-b1f67777518e4e6a88cceee08d409937"

# Renombrar temporalmente .env si existe para evitar que litellm lo cargue (tiene caracteres nulos)
_env_backup = None
if os.path.exists(".env"):
    try:
        _env_backup = ".env.backup"
        if os.path.exists(_env_backup):
            os.remove(_env_backup)
        shutil.move(".env", _env_backup)
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo renombrar .env: {e}")

from dotenv import load_dotenv, find_dotenv
from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor, as_completed
from litellm import completion
from tqdm import tqdm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from httpx import RemoteProtocolError, ConnectError, ReadError
from httpcore import ReadError as HttpcoreReadError

# Restaurar .env después de importar litellm
if _env_backup and os.path.exists(_env_backup):
    try:
        shutil.move(_env_backup, ".env")
    except Exception as e:
        print(f"ADVERTENCIA: No se pudo restaurar .env: {e}")

# --- CONFIGURACIÓN ---
# Cargar variables de entorno (solo si no hay backup, para evitar problemas con caracteres nulos)
_env_file = None
if not _env_backup:
    _env_file = find_dotenv()
    if _env_file:
        try:
            load_dotenv(dotenv_path=_env_file, override=False)
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo cargar .env: {e}")
    _runtime_env = os.getenv("ENV_FILE")
    if _runtime_env and os.path.exists(_runtime_env):
        try:
            load_dotenv(dotenv_path=_runtime_env, override=True)
        except Exception as e:
            print(f"ADVERTENCIA: No se pudo cargar .env.runtime: {e}")

# Función para obtener variables de entorno (igual que en main.py)
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

# Credenciales de Supabase - leer directamente del archivo .env (si existe)
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")

# Si no se encontraron, intentar leerlas del archivo .env directamente (ignorando caracteres nulos)
if (not SUPABASE_URL or not SUPABASE_SERVICE_KEY):
    env_files = [".env", ".env.backup"] if _env_backup and os.path.exists(".env.backup") else [".env"]
    for env_file in env_files:
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    # Filtrar caracteres nulos
                    content = content.replace('\x00', '')
                    for line in content.split('\n'):
                        line = line.strip()
                        if '=' in line and not line.startswith('#'):
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key == 'SUPABASE_URL' and not SUPABASE_URL and value:
                                SUPABASE_URL = value
                                os.environ['SUPABASE_URL'] = value
                                print(f"OK: SUPABASE_URL cargada desde {env_file}")
                            elif key == 'SUPABASE_SERVICE_KEY' and not SUPABASE_SERVICE_KEY and value:
                                SUPABASE_SERVICE_KEY = value
                                os.environ['SUPABASE_SERVICE_KEY'] = value
                                print(f"OK: SUPABASE_SERVICE_KEY cargada desde {env_file}")
                if SUPABASE_URL and SUPABASE_SERVICE_KEY:
                    break
            except Exception as e:
                print(f"ADVERTENCIA: Error al leer {env_file}: {e}")

# Obtener DEEPSEEK_API_KEY - ya está configurada al inicio del script
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Debug: mostrar estado de las variables
print(f"\nEstado de variables:")
print(f"  SUPABASE_URL: {'OK' if SUPABASE_URL else 'FALTA'}")
print(f"  SUPABASE_SERVICE_KEY: {'OK' if SUPABASE_SERVICE_KEY else 'FALTA'}")
print(f"  DEEPSEEK_API_KEY: {'OK' if DEEPSEEK_API_KEY else 'FALTA'}")

# Si falta alguna variable crítica, intentar leerla del backup
if (not SUPABASE_URL or not SUPABASE_SERVICE_KEY) and _env_backup and os.path.exists(_env_backup):
    print(f"\nLeyendo variables faltantes desde backup...")
    try:
        with open(_env_backup, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            content = content.replace('\x00', '')
            for line in content.split('\n'):
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key == 'SUPABASE_URL' and not SUPABASE_URL and value:
                        SUPABASE_URL = value
                        os.environ['SUPABASE_URL'] = value
                        print(f"OK: SUPABASE_URL cargada")
                    elif key == 'SUPABASE_SERVICE_KEY' and not SUPABASE_SERVICE_KEY and value:
                        SUPABASE_SERVICE_KEY = value
                        os.environ['SUPABASE_SERVICE_KEY'] = value
                        print(f"OK: SUPABASE_SERVICE_KEY cargada")
    except Exception as e:
        print(f"ADVERTENCIA: Error al leer variables del backup: {e}") 

# Definiciones de la BD
DOCUMENTS_TABLE = "documents"
CHUNKS_TABLE = "book_chunks"

# Modelo y parámetros para la clasificación
CLASSIFICATION_MODEL = "deepseek/deepseek-chat"
MAX_WORKERS = 4 # Tarea limitada por red, 4 es conservador.

# Lista de categorías para guiar al LLM
CATEGORIES = [
    "Psicología del Trading",
    "Análisis Técnico (Gráficos)",
    "Análisis Fundamental/Valoración",
    "Gestión de Riesgo y Posición",
    "Estrategia de Opciones/Futuros",
    "Introducción/Conceptos Básicos",
    "Automatización/Algorítmico",
    "Economía/Mercados Globales",
    "Biografía/Historias de Traders",
    "General/Inversión"
]

# --- ESTRATEGIA DE REINTENTOS PARA ERRORES DE RED ---
retryable_exceptions = (RemoteProtocolError, ConnectError, ReadError, HttpcoreReadError)

retry_strategy = retry(
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(retryable_exceptions)
)

# --- LÓGICA DEL LLM (CON PROMPT MÁS ESTRICTO) ---

def classify_document_llm(excerpt: str) -> str:
    """Llama a DeepSeek para clasificar el documento y extraer metadatos."""
    
    system_prompt = (
        "Eres un experto en clasificación bibliográfica. Tu tarea es analizar un extracto de texto sobre finanzas "
        "y devolver **ESTRICTAMENTE** una respuesta en formato JSON. No incluyas ningún texto, explicación o comentario fuera del objeto JSON. "
        "Clasifica la CATEGORY usando solo uno de los siguientes valores: "
        f"{', '.join(CATEGORIES)}. Si no aplica, usa 'General/Inversión'. "
        "El JSON debe tener las claves: 'title', 'author', 'category'."
    )
    
    user_prompt = f"Por favor, clasifica este documento y extrae el título y el autor. Texto: ```{excerpt[:2000]}...```"

    try:
        response = completion(
            model=CLASSIFICATION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            api_key=DEEPSEEK_API_KEY,
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=60
        )
        # Devolvemos el string JSON puro
        return response.choices[0].message.content

    except Exception as e:
        print(f"Error en LiteLLM durante la llamada: {e}")
        return None

# --- LÓGICA DE PROCESAMIENTO (CON RETRY EN LA FUNCIÓN PRINCIPAL) ---

@retry_strategy
def process_single_doc(doc_id: str, supabase_client: Client):
    """Procesa un solo documento: extrae texto, llama al LLM y actualiza la BD."""
    
    # 1. Obtener los primeros chunks (si hay error de red aquí, se reintenta)
    res_chunks = supabase_client.table(CHUNKS_TABLE).select('content') \
        .eq('doc_id', doc_id).limit(3).execute()
    
    if not res_chunks.data:
        return doc_id, "ERROR: No se encontraron chunks para el documento."
        
    excerpt = " ".join([d['content'] for d in res_chunks.data])
    
    # 2. Llamar al clasificador LLM
    llm_result_str = classify_document_llm(excerpt)
    
    if not llm_result_str:
        return doc_id, "FALLO: LLM no devolvió una respuesta válida."
    
    try:
        # 3. Limpiar el JSON de caracteres de control inválidos antes de parsear
        import re
        # Eliminar caracteres de control excepto \n, \r, \t
        cleaned_json = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', llm_result_str)
        
        # Intentar parsear la respuesta JSON
        metadata = json.loads(cleaned_json)
        
        # Validar que tenga las claves necesarias
        if not all(key in metadata for key in ['title', 'author', 'category']):
            return doc_id, "FALLO: JSON incompleto. Faltan claves requeridas."
        
        # 4. Actualizar la tabla documents (si hay error de red aquí, se reintenta)
        supabase_client.table(DOCUMENTS_TABLE).update({
            'title': metadata.get('title'),
            'author': metadata.get('author'),
            'category': metadata.get('category'),
            'updated_at': "now()"
        }).eq('doc_id', doc_id).execute()
        
        return doc_id, f"COMPLETADO. Categoría: {metadata.get('category')}"
        
    except json.JSONDecodeError as e:
        print(f"FALLO CRITICO DE PARSEO JSON: {llm_result_str[:200]}... | Error: {e}")
        return doc_id, "FALLO: JSON invalido. Reintentar manualmente."
    except Exception as e:
        return doc_id, f"FALLO: Error al actualizar BD. Error: {e}"



# --- ORQUESTADOR PRINCIPAL ---

def main():
    # Usar variable global para poder modificarla si es necesario
    global DEEPSEEK_API_KEY
    
    # Verificar si DEEPSEEK_API_KEY está disponible (puede estar en Railway)
    if not DEEPSEEK_API_KEY:
        # Intentar obtenerla desde las variables de entorno del sistema (Railway)
        DEEPSEEK_API_KEY_env = os.getenv("DEEPSEEK_API_KEY")
        if DEEPSEEK_API_KEY_env:
            DEEPSEEK_API_KEY = DEEPSEEK_API_KEY_env.strip('"').strip("'").strip()
            print(f"OK: DEEPSEEK_API_KEY obtenida desde variables de entorno del sistema")
    
    if not DEEPSEEK_API_KEY:
        print("Error: DEEPSEEK_API_KEY no encontrada.")
        print("Por favor, configura DEEPSEEK_API_KEY en:")
        print("  1. Archivo .env local, o")
        print("  2. Variables de entorno del sistema (Railway)")
        print(f"\nEstado actual:")
        print(f"  SUPABASE_URL encontrada: {bool(SUPABASE_URL)}")
        print(f"  SUPABASE_SERVICE_KEY encontrada: {bool(SUPABASE_SERVICE_KEY)}")
        print(f"  DEEPSEEK_API_KEY encontrada: {bool(DEEPSEEK_API_KEY)}")
        sys.exit(1)

    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    except Exception as e:
        print(f"Error al conectar con Supabase: {e}")
        sys.exit(1)

    # Buscar documentos que aún no tienen categoría (o que tienen 'general' o 'General/Inversión')
    res = supabase_client.table(DOCUMENTS_TABLE).select('doc_id', count='exact') \
        .or_('category.eq.general,category.eq.General/Inversión,category.is.null').execute()
    
    if res.count == 0:
        print("OK: Todos los documentos ya estan clasificados!")
        return

    doc_ids_to_process = [d['doc_id'] for d in res.data]
    
    print(f"============================================================")
    print(f"Encontrados {len(doc_ids_to_process)} documentos para clasificar.")
    print(f"============================================================")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Usamos tqdm para barra de progreso visible
        future_to_doc = {executor.submit(process_single_doc, doc_id, supabase_client): doc_id for doc_id in doc_ids_to_process}
        
        results = []
        for future in tqdm(as_completed(future_to_doc), total=len(doc_ids_to_process), desc="Clasificando documentos"):
            doc_id, status = future.result()
            results.append((doc_id, status))

    end_time = time.time()
    print(f"\n--- CLASIFICACIÓN FINALIZADA ---")
    print(f"Tiempo total: {(end_time - start_time):.2f} segundos")
    
    # Reporte de fallos (opcional)
    fallos = [res for res in results if 'FALLO' in res[1] or 'ERROR' in res[1]]
    if fallos:
        print(f"ADVERTENCIA: {len(fallos)} documentos fallaron la clasificacion. (Ver errores arriba)")

if __name__ == "__main__":
    main()
