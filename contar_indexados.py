"""
📊 CONTAR ARCHIVOS INDEXADOS
============================

Script rápido para contar archivos y chunks indexados.
"""

import os
import sys
import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv

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
    print("⚠️  Faltan variables de entorno")
    sys.exit(1)

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

try:
    import config
    collection_name = config.VECTOR_COLLECTION_NAME
except ImportError:
    collection_name = "knowledge"

def contar_indexados():
    """Cuenta archivos y chunks indexados"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=20)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '60s'")
        
        print("📊 Contando archivos indexados...")
        
        # Intentar contar archivos únicos (puede ser lento)
        try:
            cur.execute(f"""
                SELECT COUNT(DISTINCT metadata->>'file_name') as count
                FROM vecs.{collection_name}
                WHERE metadata->>'file_name' IS NOT NULL
            """)
            files_count = cur.fetchone()[0] if cur.rowcount > 0 else 0
            print(f"✅ Archivos únicos indexados: {files_count}")
        except Exception as e:
            print(f"⚠️  Error contando archivos (puede ser timeout): {e}")
            files_count = None
        
        # Contar chunks totales (más rápido)
        try:
            cur.execute(f"""
                SELECT COUNT(*) as count
                FROM vecs.{collection_name}
            """)
            chunks_count = cur.fetchone()[0] if cur.rowcount > 0 else 0
            print(f"✅ Chunks totales: {chunks_count:,}")
        except Exception as e:
            print(f"⚠️  Error contando chunks: {e}")
            chunks_count = None
        
        # Intentar obtener estadísticas adicionales
        if files_count is not None and chunks_count is not None:
            avg_chunks = chunks_count / files_count if files_count > 0 else 0
            print(f"📈 Promedio de chunks por archivo: {avg_chunks:.1f}")
        
        # Contar desde tabla documents si existe
        try:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM documents
            """)
            docs_count = cur.fetchone()[0] if cur.rowcount > 0 else 0
            if docs_count > 0:
                print(f"📚 Documentos registrados en tabla 'documents': {docs_count}")
        except:
            pass  # Tabla puede no existir
        
        cur.close()
        conn.close()
        
        return files_count, chunks_count
        
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None, None

if __name__ == "__main__":
    print("="*80)
    print("📊 CONTEO DE ARCHIVOS INDEXADOS")
    print("="*80)
    print()
    
    files, chunks = contar_indexados()
    
    print()
    print("="*80)
    
    if files is not None:
        print(f"📚 TOTAL DE ARCHIVOS INDEXADOS: {files}")
    else:
        print("⚠️  No se pudo obtener el conteo de archivos")
    
    if chunks is not None:
        print(f"📦 TOTAL DE CHUNKS: {chunks:,}")
    else:
        print("⚠️  No se pudo obtener el conteo de chunks")
    
    print("="*80)















