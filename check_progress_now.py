import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import psutil
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

# Contar archivos en data/
data_dir = "./data"
total_files = 0
if os.path.exists(data_dir):
    supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md', '.doc'}
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            if os.path.splitext(file)[1].lower() in supported_extensions:
                total_files += 1

print("=" * 80)
print("📊 ESTADO ACTUAL Y PROGRESO")
print("=" * 80)

# Verificar procesos
print("\n🔍 PROCESOS ACTIVOS:")
ingest_processes = []
monitor_processes = []

for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
            cmdline = ' '.join(proc.info['cmdline'])
            if 'ingest_improved.py' in cmdline.lower() or 'ingest_parallel_tier3.py' in cmdline.lower():
                proc_obj = psutil.Process(proc.info['pid'])
                ingest_processes.append({
                    'pid': proc.info['pid'],
                    'memory_mb': proc_obj.memory_info().rss / (1024**2),
                    'cpu': proc_obj.cpu_percent(interval=0.5),
                    'status': proc_obj.status()
                })
            elif 'master_monitor.py' in cmdline.lower():
                proc_obj = psutil.Process(proc.info['pid'])
                monitor_processes.append({
                    'pid': proc.info['pid'],
                    'memory_mb': proc_obj.memory_info().rss / (1024**2),
                    'cpu': proc_obj.cpu_percent(interval=0.5),
                    'status': proc_obj.status()
                })
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if ingest_processes:
    print(f"   ✅ Proceso de ingest: {len(ingest_processes)} proceso(s) activo(s)")
    for proc in ingest_processes:
        print(f"      PID: {proc['pid']} | Mem: {proc['memory_mb']:.1f} MB | CPU: {proc['cpu']:.1f}% | Estado: {proc['status']}")
else:
    print("   ⚠️  No hay proceso de ingest corriendo")

if monitor_processes:
    print(f"   ✅ Monitor maestro: {len(monitor_processes)} proceso(s) activo(s)")
    for proc in monitor_processes:
        print(f"      PID: {proc['pid']} | Mem: {proc['memory_mb']:.1f} MB | CPU: {proc['cpu']:.1f}% | Estado: {proc['status']}")
else:
    print("   ⚠️  No hay monitor maestro corriendo")

# Obtener batch_size actual
print("\n📦 CONFIGURACIÓN:")
try:
    with open('ingest_improved.py', 'r', encoding='utf-8') as f:
        import re
        content = f.read()
        # Buscar batch_size activo (no en comentarios)
        lines = content.split('\n')
        batch_size = None
        for line in lines:
            stripped = line.strip()
            # Ignorar comentarios y buscar línea activa
            if not stripped.startswith('#') and 'batch_size' in stripped:
                match = re.search(r'batch_size\s*=\s*(\d+)', stripped)
                if match:
                    batch_size = int(match.group(1))
                    break
        if batch_size is not None:
            print(f"   batch_size: {batch_size}")
        else:
            print(f"   ⚠️  No se pudo leer batch_size")
except Exception as e:
    print(f"   ⚠️  Error leyendo batch_size: {e}")

# Contar archivos indexados
print("\n📚 PROGRESO:")
print(f"   Total de archivos: {total_files}")

try:
    conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
    conn.set_session(autocommit=False)
    cur = conn.cursor()
    
    # Timeout corto
    cur.execute("SET statement_timeout = '15s'")
    
    print("   Consultando base de datos...")
    
    cur.execute(f"""
        SELECT COUNT(DISTINCT metadata->>'file_name') as count
        FROM vecs.{config.VECTOR_COLLECTION_NAME}
        WHERE metadata->>'file_name' IS NOT NULL
    """)
    
    indexed_count = cur.fetchone()[0]
    
    # Contar chunks
    cur.execute(f"""
        SELECT COUNT(*) as total
        FROM vecs.{config.VECTOR_COLLECTION_NAME}
    """)
    
    total_chunks = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    print(f"   ✅ Archivos indexados: {indexed_count}")
    print(f"   📦 Chunks totales: {total_chunks:,}")
    
    if total_files > 0:
        progress = (indexed_count / total_files * 100)
        remaining = total_files - indexed_count
        print(f"\n📈 PROGRESO:")
        print(f"   {progress:.2f}% completado")
        print(f"   {indexed_count} de {total_files} archivos")
        print(f"   {remaining} archivos pendientes")
        
        # Barra de progreso
        bar_length = 50
        filled = int(bar_length * (indexed_count / total_files))
        bar = '█' * filled + '░' * (bar_length - filled)
        print(f"\n   [{bar}] {progress:.1f}%")
        
except psycopg2.errors.QueryCanceled:
    print("   ⚠️  La consulta está tardando mucho (hay MUCHOS datos)")
    print("   💡 Esto es buena señal - significa que hay muchos archivos indexados")
except Exception as e:
    print(f"   ❌ Error consultando base de datos: {e}")

print("\n" + "=" * 80)

