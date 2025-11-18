import psutil
import sys

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("ESTADO ACTUAL DEL SISTEMA")
print("=" * 80)
print()

# Buscar proceso de ingest
ingest_found = False
optimizer_found = False

for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
            cmdline = ' '.join(proc.info['cmdline'])
            
            if 'ingest_improved.py' in cmdline.lower():
                ingest_found = True
                proc_obj = psutil.Process(proc.info['pid'])
                mem_mb = proc_obj.memory_info().rss / (1024**2)
                cpu = proc_obj.cpu_percent(interval=0.5)
                uptime = (psutil.time.time() - proc.info['create_time']) / 60
                
                print("PROCESO DE INGEST:")
                print(f"   PID: {proc.info['pid']}")
                print(f"   Memoria: {mem_mb:.2f} MB")
                print(f"   CPU: {cpu:.1f}%")
                print(f"   Tiempo corriendo: {uptime:.1f} minutos")
                print()
            
            if 'optimize_and_monitor.py' in cmdline.lower():
                optimizer_found = True
                proc_obj = psutil.Process(proc.info['pid'])
                mem_mb = proc_obj.memory_info().rss / (1024**2)
                cpu = proc_obj.cpu_percent(interval=0.5)
                uptime = (psutil.time.time() - proc.info['create_time']) / 60
                
                print("OPTIMIZADOR:")
                print(f"   PID: {proc.info['pid']}")
                print(f"   Memoria: {mem_mb:.2f} MB")
                print(f"   CPU: {cpu:.1f}%")
                print(f"   Tiempo corriendo: {uptime:.1f} minutos")
                print()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if not ingest_found:
    print("⚠️  No se encontró proceso de ingest corriendo")
    print()

if not optimizer_found:
    print("⚠️  No se encontró optimizador corriendo")
    print()

# Leer batch_size actual
try:
    with open('ingest_improved.py', 'r', encoding='utf-8') as f:
        import re
        content = f.read()
        # Buscar batch_size activo (no en comentarios)
        # Buscar líneas que no empiecen con # y contengan batch_size =
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
            print(f"batch_size configurado: {batch_size}")
            print()
except Exception as e:
    print(f"⚠️  Error leyendo batch_size: {e}")

# Recursos del sistema
try:
    mem = psutil.virtual_memory()
    print("RECURSOS DEL SISTEMA:")
    print(f"   RAM Total: {mem.total / (1024**3):.2f} GB")
    print(f"   RAM Disponible: {mem.available / (1024**3):.2f} GB")
    print(f"   RAM Usada: {mem.used / (1024**3):.2f} GB ({mem.percent:.1f}%)")
    print(f"   CPU: {psutil.cpu_percent(interval=1):.1f}%")
except Exception as e:
    print(f"⚠️  Error obteniendo recursos: {e}")

print()
print("=" * 80)

