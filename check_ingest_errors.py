import psutil
import sys
import os
from datetime import datetime

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("DIAGNOSTICO DEL PROCESO DE INGEST")
print("=" * 80)
print()

# Buscar proceso de ingest
ingest_proc = None
for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'status']):
    try:
        if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
            cmdline = ' '.join(proc.info['cmdline'])
            if 'ingest_improved.py' in cmdline.lower():
                ingest_proc = psutil.Process(proc.info['pid'])
                print(f"PROCESO ENCONTRADO:")
                print(f"   PID: {proc.info['pid']}")
                print(f"   Estado: {proc.info['status']}")
                print(f"   Tiempo corriendo: {(psutil.time.time() - proc.info['create_time']) / 60:.1f} minutos")
                print()
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if not ingest_proc:
    print("NO se encontró proceso de ingest corriendo")
    print()
    sys.exit(1)

# Verificar recursos
try:
    mem_info = ingest_proc.memory_info()
    cpu_percent = ingest_proc.cpu_percent(interval=1)
    print(f"RECURSOS DEL PROCESO:")
    print(f"   Memoria: {mem_info.rss / (1024**2):.2f} MB")
    print(f"   CPU: {cpu_percent:.1f}%")
    print()
except Exception as e:
    print(f"Error obteniendo recursos: {e}")
    print()

# Verificar si el proceso está activo
if ingest_proc.status() == 'running':
    print("Estado: PROCESO ACTIVO")
else:
    print(f"Estado: {ingest_proc.status()} (puede estar bloqueado o terminado)")
print()

# Verificar archivos pendientes
try:
    from dotenv import load_dotenv
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from urllib.parse import quote_plus
    import config
    
    load_dotenv()
    
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip('"').strip("'").strip()
    SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "").strip('"').strip("'").strip()
    
    if SUPABASE_URL and SUPABASE_DB_PASSWORD:
        project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
        encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
        postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"
        
        conn = psycopg2.connect(postgres_connection_string)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Contar archivos indexados
        cur.execute(f"""
            SELECT COUNT(DISTINCT metadata->>'file_name') as count
            FROM vecs.{config.VECTOR_COLLECTION_NAME} 
            WHERE metadata->>'file_name' IS NOT NULL
        """)
        indexed_count = cur.fetchone()['count']
        
        # Contar archivos en directorio
        total_files = 0
        if os.path.exists(config.DATA_DIRECTORY):
            supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md'}
            for root, dirs, files in os.walk(config.DATA_DIRECTORY):
                for file in files:
                    if os.path.splitext(file)[1].lower() in supported_extensions:
                        total_files += 1
        
        pending = total_files - indexed_count
        
        print(f"ARCHIVOS:")
        print(f"   Total: {total_files}")
        print(f"   Indexados: {indexed_count}")
        print(f"   Pendientes: {pending}")
        print()
        
        cur.close()
        conn.close()
except Exception as e:
    print(f"Error verificando archivos: {e}")
    print()

# Verificar batch_size actual
try:
    with open('ingest_improved.py', 'r', encoding='utf-8') as f:
        import re
        content = f.read()
        match = re.search(r'batch_size\s*=\s*(\d+)', content)
        if match:
            batch_size = int(match.group(1))
            print(f"BATCH_SIZE CONFIGURADO: {batch_size}")
            if batch_size > 5000:
                print(f"   ADVERTENCIA: batch_size muy grande ({batch_size})")
                print(f"   Esto puede causar problemas de memoria o timeouts")
            print()
except Exception as e:
    print(f"Error leyendo batch_size: {e}")
    print()

print("=" * 80)
print("RECOMENDACIONES:")
print("=" * 80)
print()
print("Si el proceso está 'rechazando' archivos, puede ser por:")
print("1. batch_size demasiado grande causando timeouts")
print("2. Errores al cargar archivos individuales")
print("3. Problemas de conexión con la base de datos")
print()
print("Para ver los errores en tiempo real, revisa la ventana")
print("donde ejecutaste ingest_improved.py")
print()















