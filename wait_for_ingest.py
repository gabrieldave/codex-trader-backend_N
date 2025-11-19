import os
import sys
import time
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

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
    print("Error: Faltan variables de entorno")
    sys.exit(1)

# Construir conexión
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

# Contar archivos en data
def count_files_in_data():
    data_dir = "./data"
    if not os.path.exists(data_dir):
        return 0
    
    supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md'}
    count = 0
    for root, dirs, files in os.walk(data_dir):
        for file in files:
            file_ext = os.path.splitext(file)[1].lower()
            if file_ext in supported_extensions:
                count += 1
    return count

# Contar archivos indexados
def count_indexed_files():
    try:
        conn = psycopg2.connect(postgres_connection_string)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT COUNT(DISTINCT metadata->>'file_name') as count
            FROM vecs.knowledge 
            WHERE metadata->>'file_name' IS NOT NULL
        """)
        
        result = cur.fetchone()
        count = result['count'] if result else 0
        
        cur.close()
        conn.close()
        return count
    except Exception as e:
        return 0

print("=" * 80)
print("MONITOR DE INGESTIÓN - Esperando a que termine...")
print("=" * 80)

total_files = count_files_in_data()
print(f"\nTotal de archivos a procesar: {total_files}")
print("Monitoreando progreso cada 60 segundos...")
print("Presiona Ctrl+C para detener el monitoreo\n")

last_count = 0
start_time = time.time()
check_interval = 60  # Verificar cada 60 segundos
no_progress_count = 0
max_no_progress = 3  # Si no hay progreso después de 3 checks, avisar

try:
    while True:
        indexed_count = count_indexed_files()
        elapsed_time = time.time() - start_time
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)
        
        if indexed_count > last_count:
            progress = (indexed_count / total_files * 100) if total_files > 0 else 0
            rate = indexed_count / elapsed_time if elapsed_time > 0 else 0
            
            print(f"[{hours:02d}:{minutes:02d}:{seconds:02d}] ✓ Progreso: {indexed_count}/{total_files} archivos ({progress:.1f}%)")
            
            if rate > 0:
                remaining_files = total_files - indexed_count
                remaining_time = remaining_files / rate if rate > 0 else 0
                remaining_hours = int(remaining_time // 3600)
                remaining_minutes = int((remaining_time % 3600) // 60)
                print(f"         Velocidad: {rate:.3f} archivos/seg")
                if remaining_time > 0:
                    print(f"         Tiempo estimado: {remaining_hours}h {remaining_minutes}m")
            
            last_count = indexed_count
            no_progress_count = 0
            
            # Si todos los archivos están indexados, terminar
            if indexed_count >= total_files:
                print("\n" + "=" * 80)
                print("✅ ¡PROCESO COMPLETADO!")
                print("=" * 80)
                print(f"Total de archivos indexados: {indexed_count}")
                total_time = elapsed_time
                print(f"Tiempo total: {int(total_time//3600)}h {int((total_time%3600)//60)}m {int(total_time%60)}s")
                print("\n🎉 Todos los archivos han sido procesados exitosamente!")
                break
        else:
            no_progress_count += 1
            if no_progress_count >= max_no_progress:
                print(f"[{hours:02d}:{minutes:02d}:{seconds:02d}] ⏳ Esperando... ({indexed_count} archivos indexados hasta ahora)")
                no_progress_count = 0
        
        time.sleep(check_interval)
        
except KeyboardInterrupt:
    print("\n\nMonitoreo detenido por el usuario")
    indexed_count = count_indexed_files()
    print(f"\nEstado actual: {indexed_count}/{total_files} archivos indexados")
    if indexed_count < total_files:
        print("El proceso de ingestión puede seguir corriendo en segundo plano.")

except Exception as e:
    print(f"\nError en el monitoreo: {e}")
    import traceback
    traceback.print_exc()




















