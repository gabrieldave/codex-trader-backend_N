import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

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

# Obtener las variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("Error: Faltan variables de entorno")
    exit(1)

# Construir la cadena de conexión
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("=" * 70)
print("DATOS INDEXADOS EN SUPABASE")
print("=" * 70)

try:
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor()
    
    # Contar total
    cur.execute("SELECT COUNT(*) FROM vecs.knowledge")
    total = cur.fetchone()[0]
    print(f"\n📊 Total de documentos indexados: {total}")
    
    # Mostrar resumen por archivo
    print("\n📁 Archivos indexados:")
    cur.execute("""
        SELECT 
            metadata->>'file_name' as archivo,
            COUNT(*) as chunks,
            MIN(metadata->>'page_label') as primera_pagina,
            MAX(metadata->>'page_label') as ultima_pagina
        FROM vecs.knowledge 
        GROUP BY metadata->>'file_name'
        ORDER BY chunks DESC
    """)
    
    files = cur.fetchall()
    for i, (archivo, chunks, primera, ultima) in enumerate(files, 1):
        print(f"\n   {i}. {archivo}")
        print(f"      - Chunks: {chunks}")
        print(f"      - Páginas: {primera} - {ultima}")
    
    # Mostrar algunos ejemplos de contenido
    print("\n\n📄 Ejemplos de contenido indexado:")
    cur.execute("""
        SELECT 
            id,
            metadata->>'file_name' as archivo,
            metadata->>'page_label' as pagina,
            jsonb_extract_path_text(metadata, '_node_content')::jsonb->>'text' as contenido
        FROM vecs.knowledge 
        WHERE jsonb_extract_path_text(metadata, '_node_content')::jsonb->>'text' != ''
        LIMIT 5
    """)
    
    examples = cur.fetchall()
    for i, (doc_id, archivo, pagina, contenido) in enumerate(examples, 1):
        print(f"\n   Ejemplo {i}:")
        print(f"   - Archivo: {archivo}")
        print(f"   - Página: {pagina}")
        print(f"   - Contenido (primeros 200 chars): {contenido[:200] if contenido else 'N/A'}...")
    
    cur.close()
    conn.close()
    
    print("\n" + "=" * 70)
    print("✅ Los datos están en: vecs.knowledge (esquema vecs)")
    print("=" * 70)
    
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()

