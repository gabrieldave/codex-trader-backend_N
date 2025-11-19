"""
📊 CONTEO FINAL DE INDEXADOS
=============================

Obtiene el conteo más preciso posible.
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

def contar():
    """Obtiene conteo usando múltiples métodos"""
    print("="*80)
    print("📊 CONTEO DE ARCHIVOS INDEXADOS")
    print("="*80)
    print()
    
    # Método 1: Estadísticas de PostgreSQL (más rápido)
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=20)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                n_live_tup as estimated_rows
            FROM pg_stat_user_tables
            WHERE schemaname = 'vecs' AND relname = %s
        """, (collection_name,))
        
        result = cur.fetchone()
        if result and result[0] is not None:
            estimated_chunks = result[0]
            print(f"📦 Chunks (estadísticas PG): {estimated_chunks:,}")
            
            # Estimar archivos (promedio conservador: 100 chunks/archivo)
            estimated_files_conservador = estimated_chunks // 100
            # Estimar archivos (promedio optimista: 50 chunks/archivo)
            estimated_files_optimista = estimated_chunks // 50
            
            print(f"📚 Archivos estimados: ~{estimated_files_conservador} - ~{estimated_files_optimista}")
            print(f"   (Basado en 50-100 chunks por archivo promedio)")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Error obteniendo estadísticas: {e}")
    
    # Método 2: Intentar contar exacto con nueva conexión
    try:
        print("\n🔄 Intentando conteo exacto...")
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=20)
        conn.autocommit = True  # Evitar problemas de transacción
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '30s'")
        
        cur.execute(f"""
            SELECT COUNT(*) as count
            FROM vecs.{collection_name}
        """)
        
        chunks_exact = cur.fetchone()[0] if cur.rowcount > 0 else None
        if chunks_exact is not None:
            print(f"✅ Chunks exactos: {chunks_exact:,}")
            
            # Estimar archivos
            estimated_files = chunks_exact // 100
            print(f"📚 Archivos estimados: ~{estimated_files} (basado en 100 chunks/archivo)")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Timeout en conteo exacto: {e}")
        print("   (Normal cuando la BD está muy activa)")
    
    print()
    print("="*80)
    print("💡 Nota: Los procesos están trabajando activamente.")
    print("   El conteo exacto puede dar timeout cuando hay mucha actividad.")
    print("="*80)

if __name__ == "__main__":
    contar()
















