import os
import sys
import time
import psycopg2

# Preguntar URL si no está en .env
url = os.getenv("SUPABASE_DB_URL")
if not url:
    url = input("🔑 Pega tu SUPABASE_DB_URL (postgresql://...): ")

print("🚀 Conectando a Supabase...")
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

# FASE 1: LIMPIEZA
print("1️⃣ Eliminando índices HNSW anteriores...")
cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_m32_ef64")
cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_safe")
print("✅ Limpieza completada")

# FASE 2: CREAR ÍNDICE SEGURO
print("2️⃣ Creando índice HNSW (m=16, ef_construction=64)...")
print("   ⏱️ ESTO TARDA 5-8 MINUTOS - NO CIERRES CURSOR")
print("   📊 Monitoreo en tiempo real:")

cur.execute("SET statement_timeout = '0'")
start_time = time.time()

# Ejecutar CREATE INDEX
cur.execute("""
    CREATE INDEX CONCURRENTLY knowledge_vec_idx_hnsw_safe 
    ON vecs.knowledge 
    USING hnsw (vec vector_cosine_ops) 
    WITH (m = 16, ef_construction = 64)
""")

# Monitorear cada 30s
while True:
    try:
        cur.execute("SELECT pg_size_pretty(pg_relation_size('vecs.knowledge_vec_idx_hnsw_safe'::regclass))")
        size = cur.fetchone()[0]
        elapsed = int(time.time() - start_time)
        print(f"   ⏳ Tamaño: {size} - Tiempo: {elapsed}s")
        
        if size and size != '0 bytes':
            time.sleep(30)
        else:
            break
    except:
        break

print(f"✅ ÍNDICE CREADO en {int(time.time()-start_time)} segundos")

# FASE 3: VERIFICAR VALIDEZ
print("3️⃣ Verificando índice...")
cur.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = 'vecs.knowledge_vec_idx_hnsw_safe'::regclass")
is_valid = cur.fetchone()[0]

if is_valid:
    print("✅ ÍNDICE VÁLIDO Y FUNCIONAL")
    
    # FASE 4: PRUEBA DE VELOCIDAD
    print("4️⃣ Prueba de velocidad RAG...")
    cur.execute("""
        EXPLAIN (ANALYZE, TIMING) 
        SELECT vec <=> (SELECT vec FROM vecs.knowledge LIMIT 1) 
        FROM vecs.knowledge 
        ORDER BY vec <=> (SELECT vec FROM vecs.knowledge LIMIT 1) 
        LIMIT 8
    """)
    result = cur.fetchone()[0]
    # Extraer tiempo de la cadena
    import re
    time_match = re.search(r'Execution Time: (\d+\.\d+)', result)
    if time_match:
        print(f"⚡ Tiempo de consulta: {time_match.group(1)} ms")
    else:
        print("⚡ Consulta ejecutada (revisa Supabase para tiempo exacto)")
else:
    print("❌ ÍNDICE INVÁLIDO - Requiere intervención manual")

cur.close()
conn.close()















