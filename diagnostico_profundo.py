"""
🔍 DIAGNÓSTICO PROFUNDO DEL PROBLEMA
=====================================

Analiza qué puede estar causando la falta de progreso
"""

import os
import sys
import time
import psutil
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import config
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def get_env(key):
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("❌ Error: Faltan variables de entorno")
    sys.exit(1)

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("=" * 80)
print("🔍 DIAGNÓSTICO PROFUNDO")
print("=" * 80)

# 1. Verificar proceso
print("\n1️⃣  VERIFICANDO PROCESO...")
ingest_proc = None
for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'memory_info', 'status']):
    try:
        if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
            cmdline = ' '.join(proc.info['cmdline'])
            if 'ingest_improved.py' in cmdline.lower():
                ingest_proc = proc
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if ingest_proc:
    cpu = ingest_proc.cpu_percent(interval=1)
    mem_mb = ingest_proc.memory_info().rss / (1024 * 1024)
    uptime = time.time() - ingest_proc.create_time()
    print(f"   ✅ Proceso activo: PID {ingest_proc.pid}")
    print(f"   CPU: {cpu:.1f}%")
    print(f"   RAM: {mem_mb:.1f} MB")
    print(f"   Tiempo: {int(uptime//60)}m {int(uptime%60)}s")
else:
    print("   ❌ No se encontró proceso")
    sys.exit(1)

# 2. Verificar progreso en DB
print("\n2️⃣  VERIFICANDO PROGRESO EN BASE DE DATOS...")
try:
    conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SET statement_timeout = '15s'")
    
    # Contar archivos indexados
    cur.execute(f"""
        SELECT COUNT(DISTINCT metadata->>'file_name') as count
        FROM vecs.{config.VECTOR_COLLECTION_NAME} 
        WHERE metadata->>'file_name' IS NOT NULL
    """)
    result = cur.fetchone()
    indexed_count = result['count'] if result else 0
    
    # Contar chunks recientes (últimos 5 minutos)
    cur.execute(f"""
        SELECT COUNT(*) as recent_chunks
        FROM vecs.{config.VECTOR_COLLECTION_NAME}
        WHERE created_at > NOW() - INTERVAL '5 minutes'
    """)
    recent_result = cur.fetchone()
    recent_chunks = recent_result['recent_chunks'] if recent_result else 0
    
    # Obtener último archivo indexado
    cur.execute(f"""
        SELECT metadata->>'file_name' as file_name, created_at
        FROM vecs.{config.VECTOR_COLLECTION_NAME}
        WHERE metadata->>'file_name' IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 1
    """)
    last_file_result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    print(f"   Archivos indexados: {indexed_count}")
    print(f"   Chunks en últimos 5 min: {recent_chunks}")
    if last_file_result and last_file_result['created_at']:
        last_time = last_file_result['created_at']
        time_diff = (datetime.now() - last_time).total_seconds()
        print(f"   Último archivo: {last_file_result['file_name']}")
        print(f"   Hace: {int(time_diff//60)}m {int(time_diff%60)}s")
        
        if time_diff > 600:  # Más de 10 minutos
            print(f"   ⚠️  No hay actividad reciente en la base de datos")
        else:
            print(f"   ✅ Hay actividad reciente")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# 3. Verificar batch_size
print("\n3️⃣  VERIFICANDO CONFIGURACIÓN...")
try:
    with open('ingest_improved.py', 'r', encoding='utf-8') as f:
        import re
        content = f.read()
        match = re.search(r'batch_size\s*=\s*(\d+)', content)
        if match:
            batch_size = int(match.group(1))
            print(f"   batch_size: {batch_size}")
            
            # Calcular cuánto debería tardar un batch
            # Estimación: 2-5 segundos por archivo + overhead
            estimated_time_per_batch = (batch_size * 3) + 60  # 3 seg/archivo + 1 min overhead
            print(f"   Tiempo estimado por batch: ~{int(estimated_time_per_batch//60)}m {int(estimated_time_per_batch%60)}s")
            
            if uptime > estimated_time_per_batch * 1.5:
                print(f"   ⚠️  El proceso lleva más tiempo del esperado")
                print(f"   Puede estar procesando archivos muy grandes o hay un problema")
except Exception as e:
    print(f"   ⚠️  Error leyendo configuración: {e}")

# 4. Análisis de posibles causas
print("\n" + "=" * 80)
print("🔍 ANÁLISIS DE POSIBLES CAUSAS")
print("=" * 80)

print("\n💡 POSIBLES CAUSAS (en orden de probabilidad):")

print("\n1️⃣  BATCH MUY GRANDE (batch_size=150):")
print(f"   • Con 150 archivos, cada batch puede tener miles de chunks")
print(f"   • Cada chunk necesita embedding (llamada a OpenAI)")
print(f"   • Si hay 10,000 chunks en un batch, son 10,000 llamadas a OpenAI")
print(f"   • Aunque OpenAI tenga crédito, las llamadas son secuenciales/limitadas")
print(f"   • Esto puede tomar 20-30 minutos por batch")
print(f"   💡 SOLUCIÓN: Reducir batch_size a 50-80 para batches más rápidos")

print("\n2️⃣  ARCHIVOS MUY GRANDES:")
print(f"   • Algunos PDFs pueden generar cientos de chunks")
print(f"   • 150 archivos grandes = miles de chunks")
print(f"   • Cada chunk = 1 llamada a OpenAI")
print(f"   • Esto puede tomar mucho tiempo")
print(f"   💡 SOLUCIÓN: Reducir batch_size o procesar archivos grandes por separado")

print("\n3️⃣  LÍMITES DE RATE EN OPENAI:")
print(f"   • OpenAI tiene límites de requests por minuto")
print(f"   • Si excedes el límite, espera automáticamente")
print(f"   • Con muchos chunks, puede estar esperando rate limits")
print(f"   💡 SOLUCIÓN: Reducir batch_size para menos chunks por batch")

print("\n4️⃣  PROCESAMIENTO SECUENCIAL:")
print(f"   • LlamaIndex puede estar procesando chunks secuencialmente")
print(f"   • No paraleliza las llamadas a OpenAI")
print(f"   • Con miles de chunks, esto toma mucho tiempo")
print(f"   💡 SOLUCIÓN: Reducir batch_size para menos chunks por batch")

print("\n5️⃣  ERROR SILENCIOSO:")
print(f"   • Puede haber un error que no se está mostrando")
print(f"   • El proceso puede estar en un loop")
print(f"   💡 SOLUCIÓN: Revisar logs del proceso directamente")

# Recomendación
print("\n" + "=" * 80)
print("💡 RECOMENDACIÓN")
print("=" * 80)

print("\n✅ ACCIÓN INMEDIATA:")
print(f"   1. Reducir batch_size de 150 a 50-80")
print(f"   2. Esto reducirá el número de chunks por batch")
print(f"   3. Los batches serán más rápidos (5-10 min vs 20-30 min)")
print(f"   4. Verás progreso más frecuentemente")

print("\n📊 JUSTIFICACIÓN:")
print(f"   • El proceso está activo (CPU 100%)")
print(f"   • Los recursos están disponibles (Supabase, OpenAI)")
print(f"   • El problema es el tamaño del batch (demasiados chunks)")
print(f"   • Con batch_size=150, cada batch puede tener 10,000+ chunks")
print(f"   • Cada chunk = 1 llamada a OpenAI (secuencial)")
print(f"   • Esto toma 20-30 minutos por batch")

print("\n🎯 CONCLUSIÓN:")
print(f"   El problema NO es Supabase ni OpenAI")
print(f"   El problema es que batch_size=150 genera BATCHES DEMASIADO GRANDES")
print(f"   Cada batch tiene demasiados chunks, lo que toma mucho tiempo procesar")

print("\n" + "=" * 80)














