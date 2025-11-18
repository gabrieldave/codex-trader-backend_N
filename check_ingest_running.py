import os
import sys
import subprocess

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def find_ingest_processes():
    """Busca procesos de Python que estén ejecutando scripts de ingestión"""
    ingest_scripts = ['ingest.py', 'ingest_improved.py']
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
                    if 'ingest' in line.lower() and 'python' in line.lower():
                        parts = line.split(',')
                        if len(parts) >= 3:
                            try:
                                pid = parts[-2].strip()
                                cmdline = parts[-1].strip()
                                for script in ingest_scripts:
                                    if script.lower() in cmdline.lower():
                                        running_processes.append({
                                            'pid': pid,
                                            'script': script,
                                            'cmdline': cmdline
                                        })
                            except:
                                continue
        else:
            # Linux/Mac: usar ps
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'python' in line.lower() and 'ingest' in line.lower():
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                pid = parts[1]
                                cmdline = ' '.join(parts[10:])
                                for script in ingest_scripts:
                                    if script.lower() in cmdline.lower():
                                        running_processes.append({
                                            'pid': pid,
                                            'script': script,
                                            'cmdline': cmdline
                                        })
                            except:
                                continue
    except Exception as e:
        # Si falla, intentar método alternativo simple
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq python.exe', '/FO', 'CSV'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and 'python.exe' in result.stdout:
                # Hay procesos de Python, pero no podemos verificar cuáles son
                # Asumir que podría haber uno corriendo
                print("⚠️  Se detectaron procesos de Python corriendo.")
                print("   No se pudo verificar si alguno es de ingestión.")
                print("   Verifica manualmente con: tasklist | findstr python")
        except:
            pass
    
    return running_processes

print("=" * 80)
print("🔍 VERIFICACIÓN DE PROCESOS DE INGESTIÓN")
print("=" * 80)
print()

try:
    processes = find_ingest_processes()
    
    if processes:
        print(f"⚠️  Se encontraron {len(processes)} proceso(s) de ingestión corriendo:\n")
        for i, proc in enumerate(processes, 1):
            print(f"{i}. PID: {proc['pid']}")
            print(f"   Script: {proc['script']}")
            print(f"   Comando: {proc['cmdline']}")
            print()
        
        print("=" * 80)
        print("⚠️  ADVERTENCIA")
        print("=" * 80)
        print()
        print("Si ejecutas otro proceso de ingestión ahora:")
        print("  ❌ Podría intentar indexar los mismos archivos dos veces")
        print("  ❌ Consumiría el doble de recursos (CPU, memoria, API calls)")
        print("  ❌ Podría crear duplicados en la base de datos")
        print("  ❌ Podría causar conflictos de escritura")
        print("  ❌ Gastarías más tokens de OpenAI innecesariamente")
        print()
        print("✅ RECOMENDACIÓN: Deja que el proceso actual termine.")
        print("   Usa 'python monitor_ingest.py' para monitorear el progreso.")
        print()
    else:
        print("✅ No hay procesos de ingestión corriendo actualmente.")
        print("   Puedes ejecutar 'python ingest_improved.py' de forma segura.")
        print()
        
except ImportError:
    print("⚠️  La librería 'psutil' no está instalada.")
    print("   Instálala con: pip install psutil")
    print()
    print("Mientras tanto, verifica manualmente con:")
    print("   tasklist | findstr python")
    print()

print("=" * 80)

