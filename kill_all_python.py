import psutil
import sys

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80)
print("🛑 TERMINANDO TODOS LOS PROCESOS DE PYTHON")
print("=" * 80)
print()

found_processes = []

# Buscar todos los procesos de Python
for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
    try:
        if proc.info['name'] == 'python.exe':
            proc_obj = psutil.Process(proc.info['pid'])
            mem_mb = proc_obj.memory_info().rss / (1024**2)
            uptime = (psutil.time.time() - proc.info['create_time']) / 60
            cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else 'N/A'
            
            found_processes.append({
                'pid': proc.info['pid'],
                'cmdline': cmdline[:100],  # Limitar longitud
                'memory': mem_mb,
                'uptime': uptime,
                'process': proc_obj
            })
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        continue

if not found_processes:
    print("✅ No se encontraron procesos de Python corriendo")
    print()
else:
    print(f"⚠️  Encontrados {len(found_processes)} proceso(s) de Python:")
    print()
    
    for proc_info in found_processes:
        print(f"📌 PID: {proc_info['pid']}")
        print(f"   Comando: {proc_info['cmdline']}")
        print(f"   Memoria: {proc_info['memory']:.2f} MB")
        print(f"   Tiempo activo: {proc_info['uptime']:.1f} minutos")
        print()
    
    print("=" * 80)
    print("🛑 TERMINANDO PROCESOS...")
    print("=" * 80)
    print()
    
    killed_count = 0
    failed_count = 0
    
    for proc_info in found_processes:
        try:
            pid = proc_info['pid']
            proc_obj = proc_info['process']
            
            print(f"🔄 Terminando PID {pid}...")
            
            # Intentar terminar de forma suave primero
            try:
                proc_obj.terminate()
                # Esperar un poco para que termine suavemente
                try:
                    proc_obj.wait(timeout=3)
                    print(f"   ✅ Proceso {pid} terminado correctamente")
                    killed_count += 1
                except psutil.TimeoutExpired:
                    # Si no termina suavemente, forzar
                    print(f"   ⚠️  Proceso no respondió, forzando terminación...")
                    proc_obj.kill()
                    proc_obj.wait(timeout=2)
                    print(f"   ✅ Proceso {pid} terminado forzadamente")
                    killed_count += 1
            except psutil.NoSuchProcess:
                print(f"   ℹ️  Proceso {pid} ya no existe")
                killed_count += 1
            except Exception as e:
                print(f"   ❌ Error terminando proceso {pid}: {e}")
                failed_count += 1
                
        except Exception as e:
            print(f"   ❌ Error con proceso {proc_info['pid']}: {e}")
            failed_count += 1
    
    print()
    print("=" * 80)
    print("📊 RESUMEN")
    print("=" * 80)
    print(f"✅ Procesos terminados: {killed_count}")
    if failed_count > 0:
        print(f"❌ Procesos con errores: {failed_count}")
    print()
    
    # Verificar que no queden procesos
    print("🔍 Verificando que no queden procesos...")
    remaining = []
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] == 'python.exe':
                remaining.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if remaining:
        print(f"⚠️  Aún quedan {len(remaining)} proceso(s) de Python: {remaining}")
        print("   (Pueden ser procesos del sistema o de otros usuarios)")
    else:
        print("✅ Todos los procesos de Python han sido terminados")
    
    print()
    print("=" * 80)




















