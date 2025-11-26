import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
from supabase import create_client
import psycopg2
from psycopg2.extras import RealDictCursor

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Función para obtener variables de entorno manejando BOM y comillas
def get_env(key):
    """Obtiene una variable de entorno, manejando BOM y variaciones de nombre"""
    value = os.getenv(key, "")
    if not value:
        # Intentar con posibles variaciones (BOM, espacios, etc.)
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener las variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not SUPABASE_DB_PASSWORD:
    raise ValueError("Faltan variables de entorno necesarias")

# Extraer el project_ref de la URL de Supabase
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")

# Construir la cadena de conexión
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("=" * 80)
print("VERIFICACIÓN DE ARCHIVOS NUEVOS EN LA CARPETA DATA")
print("=" * 80)

# 1. Obtener lista de archivos en la carpeta data
print("\n1. Escaneando archivos en la carpeta ./data...")
data_files = []
data_dir = "./data"

if not os.path.exists(data_dir):
    print(f"   ✗ La carpeta {data_dir} no existe")
    sys.exit(1)

# Extensiones de archivos soportados
supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md'}

for root, dirs, files in os.walk(data_dir):
    for file in files:
        file_path = os.path.join(root, file)
        file_ext = os.path.splitext(file)[1].lower()
        if file_ext in supported_extensions:
            rel_path = os.path.relpath(file_path, data_dir)
            file_size = os.path.getsize(file_path)
            file_mtime = os.path.getmtime(file_path)
            data_files.append({
                'name': file,
                'path': rel_path,
                'full_path': file_path,
                'size': file_size,
                'modified': file_mtime,
                'extension': file_ext
            })

print(f"   ✓ Encontrados {len(data_files)} archivos en ./data")
print(f"   - PDFs: {len([f for f in data_files if f['extension'] == '.pdf'])}")
print(f"   - EPUBs: {len([f for f in data_files if f['extension'] == '.epub'])}")
print(f"   - TXTs: {len([f for f in data_files if f['extension'] == '.txt'])}")
print(f"   - Otros: {len([f for f in data_files if f['extension'] not in ['.pdf', '.epub', '.txt']])}")

# 2. Conectar a Supabase y obtener archivos indexados
print("\n2. Consultando archivos indexados en Supabase...")
try:
    conn = psycopg2.connect(postgres_connection_string)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Consultar archivos indexados desde vecs.knowledge
    cur.execute("""
        SELECT DISTINCT 
            metadata->>'file_name' as file_name,
            metadata->>'file_path' as file_path,
            COUNT(*) as chunks
        FROM vecs.knowledge 
        WHERE metadata->>'file_name' IS NOT NULL
        GROUP BY metadata->>'file_name', metadata->>'file_path'
        ORDER BY file_name
    """)
    
    indexed_files = cur.fetchall()
    indexed_file_names = {row['file_name']: row for row in indexed_files}
    
    print(f"   ✓ Encontrados {len(indexed_files)} archivos únicos indexados en Supabase")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"   ✗ Error al consultar Supabase: {e}")
    import traceback
    traceback.print_exc()
    indexed_file_names = {}

# 3. Comparar y encontrar archivos nuevos
print("\n3. Comparando archivos locales vs indexados...")
new_files = []
already_indexed = []
not_found_in_index = []

for file_info in data_files:
    file_name = file_info['name']
    # Normalizar el nombre para comparación (sin espacios extra, lowercase)
    normalized_name = file_name.lower().strip()
    
    # Buscar si el archivo está indexado (comparar por nombre)
    found = False
    for indexed_name, indexed_data in indexed_file_names.items():
        if indexed_name and normalized_name == indexed_name.lower().strip():
            found = True
            already_indexed.append({
                'local': file_info,
                'indexed': indexed_data
            })
            break
    
    if not found:
        new_files.append(file_info)

# También verificar archivos indexados que no están en local
indexed_not_local = []
for indexed_name, indexed_data in indexed_file_names.items():
    if indexed_name:
        found_local = False
        for file_info in data_files:
            if file_info['name'].lower().strip() == indexed_name.lower().strip():
                found_local = True
                break
        if not found_local:
            indexed_not_local.append(indexed_data)

# 4. Mostrar resultados
print("\n" + "=" * 80)
print("RESUMEN")
print("=" * 80)
print(f"Total archivos en ./data: {len(data_files)}")
print(f"Archivos indexados en Supabase: {len(indexed_file_names)}")
print(f"Archivos nuevos (no indexados): {len(new_files)}")
print(f"Archivos ya indexados: {len(already_indexed)}")
print(f"Archivos indexados pero no en local: {len(indexed_not_local)}")

if new_files:
    print("\n" + "=" * 80)
    print(f"📁 ARCHIVOS NUEVOS QUE NECESITAN SER PROCESADOS ({len(new_files)}):")
    print("=" * 80)
    for i, file_info in enumerate(new_files[:50], 1):  # Mostrar primeros 50
        size_mb = file_info['size'] / (1024 * 1024)
        print(f"{i:3d}. {file_info['name']}")
        print(f"     Tamaño: {size_mb:.2f} MB | Tipo: {file_info['extension']}")
        print(f"     Ruta: {file_info['path']}")
    
    if len(new_files) > 50:
        print(f"\n     ... y {len(new_files) - 50} archivos más")
    
    print(f"\n💡 Para procesar estos archivos, ejecuta: python ingest.py")
else:
    print("\n✓ Todos los archivos en ./data ya están indexados en Supabase")

if indexed_not_local:
    print("\n" + "=" * 80)
    print(f"⚠️  ARCHIVOS INDEXADOS PERO NO ENCONTRADOS EN LOCAL ({len(indexed_not_local)}):")
    print("=" * 80)
    for i, indexed_data in enumerate(indexed_not_local[:20], 1):  # Mostrar primeros 20
        print(f"{i:3d}. {indexed_data['file_name']}")
        if indexed_data.get('chunks'):
            print(f"     Chunks: {indexed_data['chunks']}")

print("\n" + "=" * 80)
print("VERIFICACIÓN COMPLETA")
print("=" * 80)




























