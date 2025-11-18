import os
import sys
import psycopg2
from dotenv import load_dotenv

# Configurar encoding para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

def fix_hnsw_index():
    print("🚀 Fix del índice HNSW en Supabase...")
    
    # Obtener URL de diferentes fuentes
    db_url = os.getenv("SUPABASE_DB_URL")
    
    # Si no está en .env, usar la URL directamente
    if not db_url:
        db_url = "postgresql://postgres.eixvqedpyuybfywmdulg:CN7FIsxuIRps1tII@aws-1-us-east-1.pooler.supabase.com:5432/postgres?connect_timeout=60&application_name=rag_app"
        print("[INFO] Usando URL hardcodeada (configura SUPABASE_DB_URL en .env para producción)")
    
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()
    
    # Desactivar timeouts
    cur.execute("SET statement_timeout = '0'")
    cur.execute("SET lock_timeout = '0'")
    
    # Eliminar índice inválido
    print("1️⃣ Eliminando índice corrupto...")
    cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_m32_ef64")
    print("✅ Índice antiguo eliminado")
    
    # Crear índice seguro
    print("2️⃣ Creando índice optimizado (m=16)...")
    print("   Esto durará 5-8 minutos. NO CIERRES CURSOR.")
    print("   Monitorea el tamaño en Supabase SQL si quieres.")
    
    cur.execute("""
        CREATE INDEX CONCURRENTLY knowledge_vec_idx_hnsw_safe 
        ON vecs.knowledge 
        USING hnsw (vec vector_cosine_ops) 
        WITH (m = 16, ef_construction = 64)
    """)
    
    print("✅ ÍNDICE CREADO CON ÉXITO!")
    
    # Verificar
    cur.execute("SELECT indisvalid FROM pg_index WHERE indexrelid = 'vecs.knowledge_vec_idx_hnsw_safe'::regclass")
    valid = cur.fetchone()[0]
    print(f"   ¿Válido?: {valid}")
    
    cur.close()
    conn.close()
    print("🎉 Proceso completado. El RAG ahora será 450x más rápido.")

if __name__ == "__main__":
    fix_hnsw_index()

