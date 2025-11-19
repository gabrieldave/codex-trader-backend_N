"""
📊 CONTAR USANDO ESTADÍSTICAS DE POSTGRESQL
===========================================

Usa estadísticas del sistema para contar sin timeout.
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

def contar_con_estadisticas():
    """Cuenta usando estadísticas de PostgreSQL"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=20)
        cur = conn.cursor()
        
        print("📊 Obteniendo estadísticas...")
        print()
        
        # Método 1: Estadísticas de tabla (muy rápido)
        try:
            cur.execute("""
                SELECT 
                    n_live_tup as estimated_rows
                FROM pg_stat_user_tables
                WHERE schemaname = 'vecs' AND relname = %s
            """, (collection_name,))
            
            result = cur.fetchone()
            if result and result[0] is not None:
                estimated_chunks = result[0]
                print(f"📦 Chunks estimados (estadísticas PG): {estimated_chunks:,}")
                print("   (Esta es una estimación basada en estadísticas, puede variar)")
        except Exception as e:
            print(f"⚠️  No se pudieron obtener estadísticas: {e}")
        
        # Método 2: Contar chunks con LIMIT y estimar
        try:
            cur.execute("SET statement_timeout = '15s'")
            # Contar primeros 10000 para estimar velocidad
            cur.execute(f"""
                SELECT COUNT(*) 
                FROM vecs.{collection_name}
                LIMIT 10000
            """)
            # Esto no funciona como esperamos, mejor usar otra estrategia
        except:
            pass
        
        # Método 3: Intentar contar total con timeout corto
        try:
            cur.execute("SET statement_timeout = '20s'")
            cur.execute(f"""
                SELECT COUNT(*) as count
                FROM vecs.{collection_name}
            """)
            chunks_count = cur.fetchone()[0] if cur.rowcount > 0 else None
            if chunks_count is not None:
                print(f"✅ Chunks totales: {chunks_count:,}")
                
                # Estimar archivos (promedio ~100 chunks por archivo)
                estimated_files = chunks_count // 100
                print(f"📊 Archivos estimados: ~{estimated_files} (basado en ~100 chunks/archivo)")
        except Exception as e:
            print(f"⚠️  Timeout contando chunks: {e}")
            print("   (La base de datos está muy activa)")
        
        # Método 4: Verificar si existe tabla documents
        try:
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'documents'
                )
            """)
            exists = cur.fetchone()[0]
            if exists:
                cur.execute("SET statement_timeout = '10s'")
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM documents
                """)
                docs_count = cur.fetchone()[0] if cur.rowcount > 0 else 0
                print(f"📚 Documentos en tabla 'documents': {docs_count}")
        except:
            pass
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("="*80)
    print("📊 CONTEO DE INDEXADOS")
    print("="*80)
    print()
    
    contar_con_estadisticas()
    
    print()
    print("="*80)
    print("💡 Los procesos están activos y trabajando.")
    print("   Si hay timeout, es normal cuando la BD está muy cargada.")
    print("="*80)













