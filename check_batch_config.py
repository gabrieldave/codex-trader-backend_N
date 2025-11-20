import os
import sys
import subprocess
import re

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def get_batch_size_from_file():
    """Lee el batch_size del archivo ingest_improved.py"""
    try:
        with open('ingest_improved.py', 'r', encoding='utf-8') as f:
            content = f.read()
            # Buscar batch_size = número
            match = re.search(r'batch_size\s*=\s*(\d+)', content)
            if match:
                return int(match.group(1))
    except Exception as e:
        print(f"⚠️  Error al leer el archivo: {e}")
    return None

def find_ingest_processes():
    """Busca procesos de Python ejecutando ingest_improved.py"""
    running_processes = []
    
    try:
        if sys.platform == 'win32':
            # Windows: usar wmic para obtener información detallada
            result = subprocess.run(
                ['wmic', 'process', 'where', 'name="python.exe"', 'get', 'ProcessId,CommandLine', '/format:csv'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'ingest_improved.py' in line.lower():
                        parts = line.split(',')
                        if len(parts) >= 3:
                            try:
                                pid = parts[-2].strip()
                                cmdline = parts[-1].strip()
                                running_processes.append({
                                    'pid': pid,
                                    'cmdline': cmdline
                                })
                            except:
                                continue
    except Exception as e:
        pass
    
    return running_processes

print("=" * 80)
print("🔍 VERIFICACIÓN DE CONFIGURACIÓN DE BATCH")
print("=" * 80)
print()

# Verificar batch_size en el archivo
batch_size = get_batch_size_from_file()
if batch_size:
    print(f"📝 Configuración en ingest_improved.py:")
    print(f"   batch_size = {batch_size}")
    print()
else:
    print("⚠️  No se pudo leer el batch_size del archivo")
    print()

# Verificar si hay procesos corriendo
print("🔍 Verificando procesos en ejecución...")
processes = find_ingest_processes()

if processes:
    print(f"\n✅ Se encontró {len(processes)} proceso(s) de ingest_improved.py corriendo:")
    for i, proc in enumerate(processes, 1):
        print(f"\n   Proceso {i}:")
        print(f"   • PID: {proc['pid']}")
        print(f"   • Comando: {proc['cmdline'][:100]}...")
    
    print(f"\n💡 El proceso está usando batch_size = {batch_size}")
    print("   (configuración actual del archivo)")
    print()
    print("⚠️  NOTA: Si el proceso se inició ANTES del cambio,")
    print("   seguirá usando el batch_size anterior hasta que lo reinicies.")
    print()
    print("   Para aplicar el nuevo batch_size:")
    print("   1. Detén el proceso actual (Ctrl+C o cierra la ventana)")
    print("   2. Ejecuta nuevamente: python ingest_improved.py")
else:
    print("\n❌ No hay procesos de ingest_improved.py corriendo actualmente.")
    print()
    print(f"💡 La próxima vez que ejecutes ingest_improved.py,")
    print(f"   usará batch_size = {batch_size}")
    print()

print("=" * 80)





















