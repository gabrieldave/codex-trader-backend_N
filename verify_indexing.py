import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import config

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv()

def get_env(key):
    """Obtiene una variable de entorno"""
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

# Obtener variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("❌ Error: Faltan variables de entorno")
    sys.exit(1)

# Construir conexión
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

# Obtener configuración
DATA_DIRECTORY = config.DATA_DIRECTORY if hasattr(config, 'DATA_DIRECTORY') else "./data"
COLLECTION_NAME = config.VECTOR_COLLECTION_NAME if hasattr(config, 'VECTOR_COLLECTION_NAME') else "knowledge"

def format_size(size_bytes):
    """Formatea el tamaño en bytes a formato legible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

def get_files_from_directory():
    """Obtiene lista de archivos del directorio"""
    if not os.path.exists(DATA_DIRECTORY):
        return {}
    
    supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md', '.doc'}
    files_dict = {}
    
    for root, dirs, files in os.walk(DATA_DIRECTORY):
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in supported_extensions:
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                files_dict[file] = {
                    'size': file_size,
                    'path': file_path,
                    'extension': file_ext
                }
    
    return files_dict

def get_indexed_files_from_db():
    """Obtiene información detallada de archivos indexados desde la base de datos"""
    try:
        conn = psycopg2.connect(postgres_connection_string)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Obtener archivos indexados con estadísticas
        cur.execute(f"""
            SELECT 
                metadata->>'file_name' as file_name,
                COUNT(*) as chunk_count
            FROM vecs.{COLLECTION_NAME}
            WHERE metadata->>'file_name' IS NOT NULL
            GROUP BY metadata->>'file_name'
            ORDER BY file_name
        """)
        
        indexed_files = {}
        for row in cur.fetchall():
            indexed_files[row['file_name']] = {
                'chunk_count': row['chunk_count']
            }
        
        # Obtener estadísticas generales
        cur.execute(f"""
            SELECT 
                COUNT(DISTINCT metadata->>'file_name') as total_files,
                COUNT(*) as total_chunks,
                COUNT(DISTINCT metadata->>'file_id') as total_documents
            FROM vecs.{COLLECTION_NAME}
            WHERE metadata->>'file_name' IS NOT NULL
        """)
        
        stats = cur.fetchone()
        
        cur.close()
        conn.close()
        
        return indexed_files, stats
        
    except Exception as e:
        print(f"❌ Error al conectar con la base de datos: {e}")
        import traceback
        traceback.print_exc()
        return {}, None

print("=" * 80)
print("✅ VERIFICACIÓN DE INDEXACIÓN")
print("=" * 80)
print(f"\n📂 Directorio de datos: {DATA_DIRECTORY}")
print(f"🗄️  Colección en Supabase: {COLLECTION_NAME}")
print()

# Obtener archivos del directorio
print("📋 Analizando archivos en el directorio...")
files_in_dir = get_files_from_directory()
total_files = len(files_in_dir)
total_size = sum(f['size'] for f in files_in_dir.values())

print(f"   • Total de archivos encontrados: {total_files}")
print(f"   • Tamaño total: {format_size(total_size)}")
print()

# Obtener archivos indexados
print("🔍 Consultando archivos indexados en Supabase...")
indexed_files, stats = get_indexed_files_from_db()

if stats is None:
    print("❌ No se pudo obtener información de la base de datos")
    sys.exit(1)

print(f"   • Archivos indexados en DB: {stats['total_files']}")
print(f"   • Chunks totales creados: {stats['total_chunks']:,}")
print(f"   • Documentos únicos: {stats['total_documents']}")
print()

# Comparar archivos
print("=" * 80)
print("📊 COMPARACIÓN DE ARCHIVOS")
print("=" * 80)

indexed_count = len(indexed_files)
missing_files = []
extra_files = []

# Archivos que están en el directorio pero no indexados
for file_name in files_in_dir:
    if file_name not in indexed_files:
        missing_files.append(file_name)

# Archivos que están indexados pero no en el directorio (puede ser normal si se movieron)
for file_name in indexed_files:
    if file_name not in files_in_dir:
        extra_files.append(file_name)

# Mostrar resumen
print(f"\n✅ Archivos correctamente indexados: {indexed_count}/{total_files}")
if indexed_count > 0:
    percentage = (indexed_count / total_files * 100) if total_files > 0 else 0
    print(f"   Progreso: {percentage:.1f}%")
    print()

# Mostrar archivos indexados (primeros 10)
if indexed_files:
    print("✅ Archivos indexados correctamente (primeros 10):")
    for i, (file_name, info) in enumerate(list(indexed_files.items())[:10], 1):
        file_size = files_in_dir.get(file_name, {}).get('size', 0)
        print(f"   {i:3d}. {file_name}")
        print(f"       • Chunks: {info['chunk_count']:,} | Tamaño: {format_size(file_size)}")
    if len(indexed_files) > 10:
        print(f"   ... y {len(indexed_files) - 10} archivos más indexados")
    print()

# Mostrar archivos faltantes (si hay)
if missing_files:
    print(f"⏳ Archivos pendientes de indexar: {len(missing_files)}")
    print("   Primeros 10 archivos pendientes:")
    for i, file_name in enumerate(missing_files[:10], 1):
        file_size = files_in_dir.get(file_name, {}).get('size', 0)
        print(f"   {i:3d}. {file_name} ({format_size(file_size)})")
    if len(missing_files) > 10:
        print(f"   ... y {len(missing_files) - 10} archivos más pendientes")
    print()

# Mostrar archivos extra (indexados pero no en directorio)
if extra_files:
    print(f"ℹ️  Archivos indexados pero no encontrados en directorio: {len(extra_files)}")
    print("   (Esto puede ser normal si moviste o eliminaste archivos)")
    for i, file_name in enumerate(extra_files[:5], 1):
        info = indexed_files[file_name]
        print(f"   {i}. {file_name} ({info['chunk_count']:,} chunks)")
    if len(extra_files) > 5:
        print(f"   ... y {len(extra_files) - 5} archivos más")
    print()

# Verificación de calidad
print("=" * 80)
print("🔍 VERIFICACIÓN DE CALIDAD")
print("=" * 80)

# Verificar que los archivos indexados tienen chunks
files_without_chunks = []
for file_name, info in indexed_files.items():
    if info['chunk_count'] == 0:
        files_without_chunks.append(file_name)

if files_without_chunks:
    print(f"⚠️  Advertencia: {len(files_without_chunks)} archivos indexados sin chunks:")
    for file_name in files_without_chunks[:5]:
        print(f"   • {file_name}")
    if len(files_without_chunks) > 5:
        print(f"   ... y {len(files_without_chunks) - 5} más")
else:
    print("✅ Todos los archivos indexados tienen chunks creados")

# Verificar tamaño promedio de chunks
if indexed_count > 0 and stats['total_chunks'] > 0:
    avg_chunks_per_file = stats['total_chunks'] / indexed_count
    print(f"\n📊 Estadísticas:")
    print(f"   • Promedio de chunks por archivo: {avg_chunks_per_file:.1f}")
    print(f"   • Chunks totales: {stats['total_chunks']:,}")
    
    # Verificar archivos con muy pocos chunks (posible problema)
    low_chunk_files = [
        (name, info['chunk_count']) 
        for name, info in indexed_files.items() 
        if info['chunk_count'] < 5
    ]
    if low_chunk_files:
        print(f"\n⚠️  Advertencia: {len(low_chunk_files)} archivos con menos de 5 chunks:")
        print("   (Estos archivos pueden no haberse indexado completamente)")
        for file_name, chunk_count in low_chunk_files[:5]:
            print(f"   • {file_name}: {chunk_count} chunks")
        if len(low_chunk_files) > 5:
            print(f"   ... y {len(low_chunk_files) - 5} más")

print()
print("=" * 80)
print("📝 RESUMEN FINAL")
print("=" * 80)
print(f"✅ Archivos indexados correctamente: {indexed_count}/{total_files}")
if total_files > 0:
    progress = (indexed_count / total_files * 100)
    print(f"📈 Progreso: {progress:.1f}%")
print(f"📦 Chunks totales en la base de datos: {stats['total_chunks']:,}")
print()

if indexed_count == total_files and not missing_files:
    print("🎉 ¡ÉXITO! Todos los archivos están correctamente indexados.")
elif indexed_count > 0:
    print(f"⚠️  Proceso en curso: {len(missing_files)} archivos pendientes de indexar.")
else:
    print("❌ No se encontraron archivos indexados. Ejecuta ingest.py o ingest_improved.py primero.")

print("=" * 80)

