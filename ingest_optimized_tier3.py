"""
🚀 INGESTIÓN OPTIMIZADA PARA TIER 3
====================================

Versión optimizada con:
- Batch size óptimo (32-64 archivos)
- Procesamiento paralelo (hasta 10 workers)
- Manejo automático de rate limits
- Reintentos inteligentes
- Validación de tokens por batch
"""

import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.supabase import SupabaseVectorStore
import time
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import config
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from queue import Queue
import requests

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = get_env("OPENAI_API_KEY")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not all([SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY, SUPABASE_DB_PASSWORD]):
    raise ValueError("Faltan variables de entorno necesarias")

# Configuración para Tier 3
TIER3_RPM_LIMIT = 5000
TIER3_TPM_LIMIT = 5000000  # 5M tokens/minuto
TIER3_TPD_LIMIT = 100000000  # 100M tokens/día

# Usar 80% de capacidad para seguridad
RPM_TARGET = int(TIER3_RPM_LIMIT * 0.8)  # 4,000 RPM
TPM_TARGET = int(TIER3_TPM_LIMIT * 0.8)  # 4M TPM

# Batch size óptimo (rango recomendado: 32-64)
BATCH_SIZE = 50  # Punto medio del rango óptimo

# Workers paralelos (hasta 10 según recomendación)
MAX_WORKERS = 5  # Empezar conservador, se puede aumentar

# Locks para thread safety
rate_limit_lock = threading.Lock()
stats_lock = threading.Lock()

# Estadísticas globales
stats = {
    'processed': 0,
    'failed': 0,
    'total_requests': 0,
    'total_tokens': 0,
    'rate_limit_hits': 0,
    'retries': 0
}

# Embed model
embed_model = OpenAIEmbedding(model="text-embedding-3-small")

# Configurar Supabase
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

vector_store = SupabaseVectorStore(
    postgres_connection_string=postgres_connection_string,
    collection_name=config.VECTOR_COLLECTION_NAME
)

storage_context = StorageContext.from_defaults(vector_store=vector_store)

def check_rate_limit_with_backoff(func, max_retries=5):
    """Ejecuta función con reintentos y backoff exponencial para rate limits"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_str = str(e).lower()
            if 'rate limit' in error_str or '429' in error_str:
                with stats_lock:
                    stats['rate_limit_hits'] += 1
                    stats['retries'] += 1
                
                wait_time = (2 ** attempt) + (attempt * 0.5)  # Backoff exponencial
                print(f"   ⚠️  Rate limit detectado, esperando {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                raise
    raise Exception(f"Error después de {max_retries} intentos")

def estimate_tokens(text):
    """Estima tokens aproximados (1 token ≈ 4 caracteres)"""
    return len(text) // 4

def process_file_batch(file_batch, batch_num, total_batches):
    """Procesa un batch de archivos"""
    global stats
    
    batch_start = time.time()
    successful = 0
    failed = 0
    
    print(f"\n📦 Lote {batch_num}/{total_batches} ({len(file_batch)} archivos)")
    
    try:
        # Cargar documentos
        all_documents = []
        failed_files = []
        
        for file_path in file_batch:
            try:
                reader = SimpleDirectoryReader(input_files=[file_path])
                file_docs = reader.load_data()
                
                # Validar tokens estimados
                total_text = " ".join([doc.text for doc in file_docs])
                estimated_tokens = estimate_tokens(total_text)
                
                # Si excede límite por archivo, dividir
                max_tokens_per_file = 800000  # Límite conservador por archivo
                if estimated_tokens > max_tokens_per_file:
                    print(f"   ⚠️  {os.path.basename(file_path)}: {estimated_tokens:,} tokens (muy grande, dividiendo...)")
                    # Dividir en chunks más pequeños
                    chunk_size = len(file_docs) // 2
                    for i in range(0, len(file_docs), chunk_size):
                        all_documents.extend(file_docs[i:i+chunk_size])
                else:
                    all_documents.extend(file_docs)
                    
            except Exception as e:
                file_name = os.path.basename(file_path)
                failed_files.append(file_name)
                print(f"   ⚠️  Error cargando {file_name}: {type(e).__name__}")
                failed += 1
                continue
        
        if not all_documents:
            print(f"   ⚠️  No hay documentos para procesar en este lote")
            with stats_lock:
                stats['failed'] += len(file_batch)
            return
        
        # Validar tokens totales del batch
        total_text = " ".join([doc.text for doc in all_documents])
        batch_tokens = estimate_tokens(total_text)
        
        if batch_tokens > TPM_TARGET:
            print(f"   ⚠️  Batch muy grande ({batch_tokens:,} tokens), dividiendo...")
            # Dividir batch en dos
            mid = len(all_documents) // 2
            return process_file_batch(file_batch[:len(file_batch)//2], batch_num, total_batches) + \
                   process_file_batch(file_batch[len(file_batch)//2:], batch_num, total_batches)
        
        print(f"   ✓ {len(all_documents)} documentos cargados (~{batch_tokens:,} tokens estimados)")
        
        # Agregar a índice con manejo de rate limits
        def add_to_index():
            index = VectorStoreIndex.from_documents(
                all_documents,
                storage_context=storage_context,
                embed_model=embed_model,
                show_progress=False
            )
            return index
        
        try:
            index = check_rate_limit_with_backoff(add_to_index)
            
            successful = len(file_batch) - len(failed_files)
            batch_time = time.time() - batch_start
            
            with stats_lock:
                stats['processed'] += successful
                stats['failed'] += failed
                stats['total_tokens'] += batch_tokens
                stats['total_requests'] += len(all_documents)
            
            print(f"   ✅ Procesados {successful} archivos en {batch_time:.1f}s")
            print(f"   📊 Tokens: ~{batch_tokens:,} | Requests: {len(all_documents)}")
            
        except Exception as e:
            print(f"   ❌ Error agregando a índice: {e}")
            with stats_lock:
                stats['failed'] += len(file_batch)
            
    except Exception as e:
        print(f"   ❌ Error procesando lote: {e}")
        with stats_lock:
            stats['failed'] += len(file_batch)
    
    return successful, failed

def get_indexed_files():
    """Obtiene lista de archivos ya indexados"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '15s'")
        
        cur.execute(f"""
            SELECT DISTINCT metadata->>'file_name' as file_name
            FROM vecs.{config.VECTOR_COLLECTION_NAME}
            WHERE metadata->>'file_name' IS NOT NULL
        """)
        
        indexed = {row[0] for row in cur.fetchall()}
        cur.close()
        conn.close()
        return indexed
    except Exception as e:
        print(f"⚠️  Error obteniendo archivos indexados: {e}")
        return set()

def get_files_to_process():
    """Obtiene lista de archivos pendientes de procesar"""
    data_dir = "./data"
    supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md', '.doc'}
    
    all_files = []
    if os.path.exists(data_dir):
        for root, dirs, files in os.walk(data_dir):
            for file in files:
                if os.path.splitext(file)[1].lower() in supported_extensions:
                    file_path = os.path.join(root, file)
                    all_files.append(file_path)
    
    indexed_files = get_indexed_files()
    
    # Filtrar archivos ya indexados
    files_to_process = [
        f for f in all_files 
        if os.path.basename(f) not in indexed_files
    ]
    
    return files_to_process, len(all_files)

def main():
    print("=" * 80)
    print("🚀 INGESTIÓN OPTIMIZADA PARA TIER 3")
    print("=" * 80)
    print(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("✨ Características:")
    print(f"   • Batch size: {BATCH_SIZE} archivos")
    print(f"   • Workers paralelos: {MAX_WORKERS}")
    print(f"   • RPM objetivo: {RPM_TARGET:,} (80% de {TIER3_RPM_LIMIT:,})")
    print(f"   • TPM objetivo: {TPM_TARGET:,} (80% de {TIER3_TPM_LIMIT:,})")
    print(f"   • Manejo automático de rate limits")
    print(f"   • Reintentos con backoff exponencial")
    print()
    
    # Obtener archivos a procesar
    files_to_process, total_files = get_files_to_process()
    
    if not files_to_process:
        print("✅ Todos los archivos ya están indexados.")
        return
    
    print(f"📚 Archivos a procesar: {len(files_to_process)}/{total_files}")
    print()
    
    # Dividir en batches
    batches = []
    for i in range(0, len(files_to_process), BATCH_SIZE):
        batches.append(files_to_process[i:i + BATCH_SIZE])
    
    total_batches = len(batches)
    print(f"📦 Total de lotes: {total_batches}")
    print()
    
    start_time = time.time()
    
    # Procesar batches en paralelo
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        
        for i, batch in enumerate(batches, 1):
            future = executor.submit(process_file_batch, batch, i, total_batches)
            futures.append((future, i))
        
        # Monitorear progreso
        completed = 0
        for future, batch_num in futures:
            try:
                future.result()
                completed += 1
                
                with stats_lock:
                    current_processed = stats['processed']
                    current_failed = stats['failed']
                    elapsed = time.time() - start_time
                    rate = current_processed / elapsed if elapsed > 0 else 0
                    remaining = len(files_to_process) - current_processed
                    eta = remaining / rate if rate > 0 else 0
                
                print(f"\n📊 Progreso: {completed}/{total_batches} lotes | "
                      f"{current_processed} archivos procesados | "
                      f"Velocidad: {rate:.2f} archivos/s | "
                      f"ETA: {int(eta//60)}m {int(eta%60)}s")
                
            except Exception as e:
                print(f"   ❌ Error en lote {batch_num}: {e}")
    
    # Resumen final
    total_time = time.time() - start_time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = int(total_time % 60)
    
    print("\n" + "=" * 80)
    print("📊 RESUMEN FINAL")
    print("=" * 80)
    print(f"Archivos procesados: {stats['processed']}/{len(files_to_process)}")
    print(f"Archivos fallidos: {stats['failed']}")
    print(f"Tiempo total: {hours}h {minutes}m {seconds}s")
    print(f"Velocidad promedio: {stats['processed']/total_time:.2f} archivos/segundo" if total_time > 0 else "N/A")
    print(f"\n📈 Estadísticas:")
    print(f"   • Total requests: {stats['total_requests']:,}")
    print(f"   • Total tokens estimados: {stats['total_tokens']:,}")
    print(f"   • Rate limit hits: {stats['rate_limit_hits']}")
    print(f"   • Reintentos: {stats['retries']}")
    print(f"\n✅ Proceso completado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()















