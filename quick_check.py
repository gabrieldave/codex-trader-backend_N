import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

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
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

try:
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Contar total de documentos
    cur.execute("SELECT COUNT(*) as total FROM vecs.knowledge")
    total_docs = cur.fetchone()['total']
    
    # Contar archivos únicos
    cur.execute("""
        SELECT COUNT(DISTINCT metadata->>'file_name') as count
        FROM vecs.knowledge 
        WHERE metadata->>'file_name' IS NOT NULL
    """)
    unique_files = cur.fetchone()['count']
    
    # Obtener algunos archivos recientes con sus chunks
    cur.execute("""
        SELECT 
            metadata->>'file_name' as file_name,
            COUNT(*) as chunks
        FROM vecs.knowledge 
        WHERE metadata->>'file_name' IS NOT NULL
        GROUP BY metadata->>'file_name'
        ORDER BY chunks DESC
        LIMIT 10
    """)
    recent_files = cur.fetchall()
    
    print("=" * 60)
    print("ESTADO ACTUAL DE LA BASE DE DATOS")
    print("=" * 60)
    print(f"Total de documentos (chunks): {total_docs:,}")
    print(f"Archivos únicos indexados: {unique_files}")
    print(f"\nTop 10 archivos por número de chunks:")
    for i, file_info in enumerate(recent_files, 1):
        print(f"  {i:2d}. {file_info['file_name']}: {file_info['chunks']} chunks")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")




























