#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para recrear el índice vectorial HNSW con parámetros seguros
Elimina el índice anterior y crea uno nuevo con m=16, ef_construction=64
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse, urlencode, parse_qs

# Configurar encoding para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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

def recreate_index_safe():
    """
    Recrea el índice vectorial HNSW con parámetros seguros.
    
    Pasos:
    1. Conecta a Supabase usando SUPABASE_DB_URL
    2. Configura timeouts ilimitados
    3. Elimina el índice anterior si existe
    4. Crea un nuevo índice con m=16, ef_construction=64
    5. Verifica que el índice quede válido
    """
    print("=" * 60)
    print("RECREACIÓN DE ÍNDICE VECTORIAL HNSW (Parámetros Seguros)")
    print("=" * 60)
    print()
    
    # Obtener SUPABASE_DB_URL
    DB_URL = get_env("SUPABASE_DB_URL")
    
    if not DB_URL:
        print("[ERROR] SUPABASE_DB_URL no está configurada")
        print()
        print("Configura SUPABASE_DB_URL en tu archivo .env")
        print("Ejemplo:")
        print("  SUPABASE_DB_URL=postgresql://postgres.xxx:password@aws-1-us-east-1.pooler.supabase.com:5432/postgres")
        return False
    
    # Limpiar URL de parámetros inválidos
    parsed = urlparse(DB_URL)
    valid_params = {}
    if parsed.query:
        params = parse_qs(parsed.query)
        valid_keys = ['connect_timeout', 'application_name', 'sslmode', 'sslrootcert']
        for key in valid_keys:
            if key in params:
                value = params[key][0] if isinstance(params[key], list) else params[key]
                valid_params[key] = value
    
    if 'connect_timeout' not in valid_params:
        valid_params['connect_timeout'] = '300'  # 5 minutos
    if 'application_name' not in valid_params:
        valid_params['application_name'] = 'index_recreation'
    
    clean_query = urlencode(valid_params) if valid_params else ''
    clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if clean_query:
        clean_url += f"?{clean_query}"
    
    try:
        print("[1/6] Conectando a la base de datos...")
        conn = psycopg2.connect(clean_url)
        conn.autocommit = True  # Necesario para DROP INDEX y CREATE INDEX
        cur = conn.cursor()
        print("     ✓ Conexión establecida")
        print()
        
        print("[2/6] Configurando timeouts ilimitados...")
        cur.execute("SET statement_timeout = '0'")
        cur.execute("SET lock_timeout = '0'")
        print("     ✓ Timeouts configurados (statement_timeout=0, lock_timeout=0)")
        print()
        
        print("[3/6] Eliminando índice anterior si existe...")
        drop_index_sql = "DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_m32_ef64"
        cur.execute(drop_index_sql)
        print("     ✓ Índice anterior eliminado (o no existía)")
        print()
        
        print("[4/6] Creando nuevo índice HNSW con parámetros seguros...")
        print("     Parámetros: m=16, ef_construction=64")
        print("     (Esto puede tardar varios minutos, por favor espera...)")
        print()
        
        create_index_sql = """
        CREATE INDEX knowledge_vec_idx_hnsw_safe 
        ON vecs.knowledge 
        USING hnsw (vec vector_cosine_ops) 
        WITH (m = 16, ef_construction = 64);
        """
        
        cur.execute(create_index_sql)
        print("     ✓ Comando CREATE INDEX ejecutado")
        print()
        
        print("[5/6] Verificando que el índice se creó correctamente...")
        verify_sql = """
        SELECT 
            i.indexname,
            i.indexdef,
            idx.indisvalid
        FROM pg_indexes i
        JOIN pg_class c ON c.relname = i.indexname
        JOIN pg_index idx ON idx.indexrelid = c.oid
        WHERE i.schemaname = 'vecs' 
          AND i.tablename = 'knowledge'
          AND i.indexname = 'knowledge_vec_idx_hnsw_safe';
        """
        
        cur.execute(verify_sql)
        results = cur.fetchall()
        
        if results:
            index_name, index_def, indisvalid = results[0]
            print(f"     ✓ Índice encontrado: {index_name}")
            print(f"     ✓ Definición: {index_def[:80]}...")
            print()
            
            print("[6/6] Verificando estado del índice (indisvalid)...")
            if indisvalid:
                print("     ✓ Índice válido (indisvalid = true)")
                print()
                print("=" * 60)
                print("[OK] Proceso completado exitosamente!")
                print("=" * 60)
                print()
                print("El nuevo índice 'knowledge_vec_idx_hnsw_safe' está activo y listo para usar.")
                cur.close()
                conn.close()
                return True
            else:
                print("     ⚠ Índice creado pero aún no válido (indisvalid = false)")
                print("     Esto es normal si el índice se está construyendo en segundo plano.")
                print("     Espera unos minutos y verifica nuevamente.")
                cur.close()
                conn.close()
                return True
        else:
            print("     ⚠ Índice no encontrado inmediatamente después de la creación")
            print("     Esto puede ser normal si el índice se está construyendo en segundo plano.")
            print("     Verifica más tarde con:")
            print("       SELECT indexname FROM pg_indexes WHERE schemaname='vecs' AND tablename='knowledge';")
            cur.close()
            conn.close()
            return True
        
    except psycopg2.OperationalError as e:
        print(f"[ERROR] Error de conexión: {e}")
        print()
        print("Verifica:")
        print("   1. Que SUPABASE_DB_URL sea correcta")
        print("   2. Que Connection pooling esté habilitado en Supabase")
        print("   3. Que Network Restrictions esté deshabilitado")
        return False
    except psycopg2.ProgrammingError as e:
        print(f"[ERROR] Error SQL: {e}")
        print()
        print("Posibles causas:")
        print("   - La tabla vecs.knowledge no existe")
        print("   - La columna 'vec' no existe o no es tipo vector")
        print("   - La extensión pgvector no está instalada")
        return False
    except Exception as e:
        print(f"[ERROR] Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = recreate_index_safe()
    sys.exit(0 if success else 1)













