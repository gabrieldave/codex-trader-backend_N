#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para crear índice vectorial usando psql directamente
Esto evita timeouts del SQL Editor de Supabase
"""

import os
import sys
import subprocess
import tempfile
from dotenv import load_dotenv

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
print("CREACION DE INDICE VECTORIAL CON psql")
print("=" * 60)
print()

# Obtener SUPABASE_DB_URL (puede estar en diferentes variables)
DB_URL = get_env("SUPABASE_DB_URL")

# Si no está, intentar construir desde otras variables
if not DB_URL:
    SUPABASE_URL = get_env("SUPABASE_URL")
    SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")
    
    if SUPABASE_URL and SUPABASE_DB_PASSWORD:
        # Construir URL desde componentes
        from urllib.parse import quote_plus
        project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
        encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
        # Intentar con connection pooling
        DB_URL = f"postgresql://postgres.{project_ref}:{encoded_password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
        print(f"[INFO] Construyendo URL desde componentes...")
    else:
        print("[ERROR] SUPABASE_DB_URL no esta configurada")
        print("Configura SUPABASE_DB_URL en tu archivo .env")
        print("O configura SUPABASE_URL y SUPABASE_DB_PASSWORD")
        sys.exit(1)

print("[*] Conectando a la base de datos...")
print()

# Crear archivo SQL temporal
sql_content = """-- Configurar timeout ilimitado
SET statement_timeout = '0';

-- Crear índice HNSW CONCURRENTLY
CREATE INDEX CONCURRENTLY IF NOT EXISTS knowledge_vec_idx_hnsw_m32_ef64 
ON vecs.knowledge 
USING hnsw (vec vector_cosine_ops) 
WITH (m = 32, ef_construction = 64);

-- Verificar que el índice se creó
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE schemaname = 'vecs' 
  AND tablename = 'knowledge'
  AND indexname LIKE '%hnsw%'
ORDER BY indexname;
"""

# Crear archivo temporal
with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
    f.write(sql_content)
    sql_file = f.name

try:
    print("[*] Ejecutando comandos SQL...")
    print()
    
    # Ejecutar psql
    result = subprocess.run(
        ['psql', DB_URL, '-f', sql_file],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    
    # Mostrar salida
    if result.stdout:
        print(result.stdout)
    
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    if result.returncode == 0:
        print()
        print("[OK] Proceso completado!")
        print()
        print("[IMPORTANTE]")
        print("   - El indice se esta creando en segundo plano (CONCURRENTLY)")
        print("   - Puede tardar varios minutos dependiendo del tamano de la tabla")
        print("   - Las busquedas mejoraran gradualmente mientras se construye")
    else:
        print()
        print(f"[ERROR] Hubo un error al crear el indice (codigo: {result.returncode})")
        sys.exit(1)

except FileNotFoundError:
    print("[ERROR] psql no esta instalado o no esta en el PATH")
    print()
    print("Instalacion:")
    print("  - macOS: brew install libpq")
    print("  - Linux: apt-get install postgresql-client")
    print("  - Windows: Instala PostgreSQL o usa WSL")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Error al ejecutar psql: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    # Limpiar archivo temporal
    try:
        os.unlink(sql_file)
    except:
        pass

