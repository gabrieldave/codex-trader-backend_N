#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para crear índice vectorial directamente usando psycopg2
Esto evita timeouts del SQL Editor de Supabase y no requiere psql
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

print("=" * 60)
print("CREACION DE INDICE VECTORIAL (Directo con psycopg2)")
print("=" * 60)
print()

# Obtener SUPABASE_DB_URL
DB_URL = get_env("SUPABASE_DB_URL")

# Si no está configurada, usar la URL por defecto (puedes pasar como argumento también)
if not DB_URL and len(sys.argv) > 1:
    DB_URL = sys.argv[1]
    print(f"[INFO] Usando URL proporcionada como argumento")
elif not DB_URL:
    print("[ERROR] SUPABASE_DB_URL no esta configurada")
    print()
    print("Opciones:")
    print("  1. Configura SUPABASE_DB_URL en tu archivo .env")
    print("  2. Ejecuta: python create_index_direct.py \"tu_url_aqui\"")
    print()
    print("Ejemplo de URL:")
    print("  postgresql://postgres.xxx:password@aws-1-us-east-1.pooler.supabase.com:5432/postgres")
    sys.exit(1)

# Limpiar URL de parámetros inválidos (igual que en main.py)
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
    valid_params['application_name'] = 'index_creation'

clean_query = urlencode(valid_params) if valid_params else ''
clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
if clean_query:
    clean_url += f"?{clean_query}"

print("[*] Conectando a la base de datos...")
print()

try:
    # Conectar a la base de datos
    conn = psycopg2.connect(clean_url)
    conn.set_session(autocommit=True)  # Necesario para CONCURRENTLY
    cur = conn.cursor()
    
    print("[*] Configurando timeout ilimitado...")
    cur.execute("SET statement_timeout = '0'")
    
    print("[*] Creando indice HNSW CONCURRENTLY...")
    print("    (Esto puede tardar varios minutos, por favor espera...)")
    print()
    
    # Crear índice CONCURRENTLY
    create_index_sql = """
    CREATE INDEX CONCURRENTLY IF NOT EXISTS knowledge_vec_idx_hnsw_m32_ef64 
    ON vecs.knowledge 
    USING hnsw (vec vector_cosine_ops) 
    WITH (m = 32, ef_construction = 64);
    """
    
    cur.execute(create_index_sql)
    
    print("[OK] Comando CREATE INDEX CONCURRENTLY ejecutado!")
    print()
    print("[*] Verificando indice...")
    print()
    
    # Verificar que el índice se creó
    verify_sql = """
    SELECT 
        indexname, 
        indexdef 
    FROM pg_indexes 
    WHERE schemaname = 'vecs' 
      AND tablename = 'knowledge'
      AND indexname LIKE '%hnsw%'
    ORDER BY indexname;
    """
    
    cur.execute(verify_sql)
    results = cur.fetchall()
    
    if results:
        print("Indices HNSW encontrados:")
        print("-" * 60)
        for row in results:
            print(f"Nombre: {row[0]}")
            print(f"Definicion: {row[1][:100]}...")
            print()
    else:
        print("[INFO] El indice se esta creando en segundo plano")
        print("       Puede tardar varios minutos. Verifica mas tarde con:")
        print("       SELECT indexname FROM pg_indexes WHERE schemaname='vecs' AND tablename='knowledge';")
    
    cur.close()
    conn.close()
    
    print("=" * 60)
    print("[OK] Proceso completado!")
    print("=" * 60)
    print()
    print("[IMPORTANTE]")
    print("   - El indice se esta creando en segundo plano (CONCURRENTLY)")
    print("   - Puede tardar varios minutos dependiendo del tamano de la tabla")
    print("   - Las busquedas mejoraran gradualmente mientras se construye")
    print("   - No bloquea la tabla durante la creacion")
    print()
    print("[TIP] Para verificar el progreso, ejecuta:")
    print("   SELECT indexname, indexdef FROM pg_indexes")
    print("   WHERE schemaname='vecs' AND tablename='knowledge'")
    print("   AND indexname LIKE '%hnsw%';")
    
except psycopg2.OperationalError as e:
    print(f"[ERROR] Error de conexion: {e}")
    print()
    print("Verifica:")
    print("   1. Que SUPABASE_DB_URL sea correcta")
    print("   2. Que Connection pooling este habilitado en Supabase")
    print("   3. Que Network Restrictions este deshabilitado")
    sys.exit(1)
except psycopg2.ProgrammingError as e:
    print(f"[ERROR] Error SQL: {e}")
    print()
    print("Posibles causas:")
    print("   - La tabla vecs.knowledge no existe")
    print("   - La columna 'vec' no existe o no es tipo vector")
    print("   - La extension pgvector no esta instalada")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Error inesperado: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

