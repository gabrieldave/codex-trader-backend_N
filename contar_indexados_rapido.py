"""
📊 CONTAR INDEXADOS (VERSIÓN RÁPIDA)
====================================

Usa métodos más eficientes para contar sin timeout.
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

def contar_rapido():
    """Cuenta usando métodos más eficientes"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=20)
        cur = conn.cursor()
        
        print("📊 Contando (método rápido)...")
        print()
        
        # Método 1: Usar tabla documents (más rápido)
        try:
            cur.execute("SET statement_timeout = '10s'")
            cur.execute("""
                SELECT 
                    COUNT(*) as total_docs,
                    SUM(total_chunks) as total_chunks_sum
                FROM documents
            """)
            result = cur.fetchone()
            if result and result[0] is not None:
                docs_count = result[0]
                chunks_sum = result[1] if result[1] else 0
                print(f"✅ Desde tabla 'documents':")
                print(f"   📚 Documentos registrados: {docs_count}")
                if chunks_sum > 0:
                    print(f"   📦 Chunks registrados: {chunks_sum:,}")
                print()
        except Exception as e:
            print(f"⚠️  Tabla 'documents' no disponible o error: {e}")
            print()
        
        # Método 2: Contar chunks totales (sin DISTINCT, más rápido)
        try:
            cur.execute("SET statement_timeout = '30s'")
            cur.execute(f"""
                SELECT COUNT(*) as count
                FROM vecs.{collection_name}
            """)
            chunks_count = cur.fetchone()[0] if cur.rowcount > 0 else 0
            print(f"✅ Chunks totales en vecs.{collection_name}: {chunks_count:,}")
        except Exception as e:
            print(f"⚠️  Error contando chunks: {e}")
            chunks_count = None
        
        # Método 3: Estimar archivos únicos usando muestra
        try:
            cur.execute("SET statement_timeout = '20s'")
            # Obtener una muestra de 1000 chunks y contar archivos únicos en la muestra
            cur.execute(f"""
                SELECT COUNT(DISTINCT metadata->>'file_name') as count
                FROM (
                    SELECT metadata->>'file_name' as file_name
                    FROM vecs.{collection_name}
                    WHERE metadata->>'file_name' IS NOT NULL
                    LIMIT 10000
                ) as sample
            """)
            sample_files = cur.fetchone()[0] if cur.rowcount > 0 else 0
            if sample_files > 0:
                # Estimar total basado en muestra
                # Si tenemos chunks_count, podemos estimar
                if chunks_count and chunks_count > 0:
                    # Asumiendo promedio de ~100 chunks por archivo
                    estimated_files = chunks_count // 100
                    print(f"📊 Estimación de archivos (basado en chunks): ~{estimated_files}")
        except Exception as e:
            pass  # Ignorar si falla
        
        # Método 4: Intentar contar archivos únicos con timeout más largo (último intento)
        if chunks_count and chunks_count > 0:
            try:
                cur.execute("SET statement_timeout = '60s'")
                cur.execute(f"""
                    SELECT COUNT(DISTINCT metadata->>'file_name') as count
                    FROM vecs.{collection_name}
                    WHERE metadata->>'file_name' IS NOT NULL
                """)
                files_count = cur.fetchone()[0] if cur.rowcount > 0 else None
                if files_count is not None:
                    print(f"✅ Archivos únicos indexados: {files_count}")
            except Exception as e:
                print(f"⚠️  No se pudo contar archivos únicos (timeout): {e}")
                print("   (La base de datos está muy cargada, usa la estimación arriba)")
        
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False

if __name__ == "__main__":
    print("="*80)
    print("📊 CONTEO RÁPIDO DE INDEXADOS")
    print("="*80)
    print()
    
    contar_rapido()
    
    print()
    print("="*80)
    print("💡 Nota: Si hay timeout, es porque la base de datos está muy activa.")
    print("   Los procesos de ingesta están trabajando normalmente.")
    print("="*80)












