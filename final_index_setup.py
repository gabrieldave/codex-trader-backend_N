import psycopg2
import time
import re
import sys
import io

# Configurar UTF-8 para Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# URL DIRECTA (sin variables de entorno)
SUPABASE_URL = "postgresql://postgres.eixvqedpyuybfywmdulg:CN7FIsxuIRps1tII@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

print("🚀 CONEXIÓN DIRECTA A SUPABASE ESTABLECIDA")
print("1️⃣ Eliminando índices anteriores...")

conn = psycopg2.connect(SUPABASE_URL)
conn.autocommit = True
cur = conn.cursor()

# Limpieza
cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_m32_ef64")
cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_safe")
print("✅ Limpieza completada")

# Creación
print("2️⃣ Creando índice HNSW seguro (m=16)...")
print("   ⏱️ ESTO TARDA 5-8 MINUTOS - NO CIERRES CURSOR")
print("   📊 Monitoreo:")

cur.execute("SET statement_timeout = '0'")
start_time = time.time()

cur.execute("""
    CREATE INDEX CONCURRENTLY knowledge_vec_idx_hnsw_safe 
    ON vecs.knowledge 
    USING hnsw (vec vector_cosine_ops) 
    WITH (m = 16, ef_construction = 64)
""")

# Monitorear mientras crece
while True:
    try:
        cur.execute("SELECT pg_size_pretty(pg_relation_size('vecs.knowledge_vec_idx_hnsw_safe'::regclass))")
        size = cur.fetchone()[0]
        elapsed = int(time.time() - start_time)
        print(f"   ⏳ {size} - {elapsed}s")
        
        if size and size != '0 bytes':
            time.sleep(30)
        else:
            break
    except:
        break

print(f"✅ CREACIÓN FINALIZADA en {int(time.time()-start_time)}s")

# Verificación
print("3️⃣ Verificando validez...")
cur.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = 'vecs.knowledge_vec_idx_hnsw_safe'::regclass")
is_valid = cur.fetchone()[0]

if is_valid:
    print("✅ ÍNDICE VÁLIDO")
    
    # Prueba de velocidad
    print("4️⃣ Prueba de velocidad RAG...")
    cur.execute("""
        EXPLAIN (ANALYZE, TIMING) 
        SELECT vec <=> (SELECT vec FROM vecs.knowledge LIMIT 1) 
        FROM vecs.knowledge 
        ORDER BY vec <=> (SELECT vec FROM vecs.knowledge LIMIT 1) 
        LIMIT 8
    """)
    result = cur.fetchone()[0]
    time_match = re.search(r'Execution Time: (\d+\.\d+)', result)
    if time_match:
        print(f"⚡ Tiempo final: {time_match.group(1)} ms")
else:
    print("❌ ÍNDICE INVÁLIDO - PROBLEMA CRÍTICO")

cur.close()
conn.close()

