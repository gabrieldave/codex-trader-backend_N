"""
🛑 DETENER TODOS LOS PROCESOS PYTHON ACTIVOS
=============================================

Detiene todos los procesos Python activos (monitores, verificaciones, etc.)
"""

import os
import sys
import psutil
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def detener_todos_procesos():
    """Detiene todos los procesos Python excepto este script"""
    print("="*80)
    print("🛑 DETENIENDO TODOS LOS PROCESOS PYTHON ACTIVOS")
    print("="*80)
    print()
    
    current_pid = os.getpid()
    procesos_detenidos = []
    procesos_omitidos = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Solo procesos Python
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                # No detener este script
                if proc.pid == current_pid:
                    continue
                
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                
                # Detener todos los procesos Python
                print(f"🛑 Deteniendo PID {proc.pid}...")
                print(f"   Comando: {cmdline[:80]}...")
                
                try:
                    proc.terminate()
                    procesos_detenidos.append((proc.pid, cmdline))
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    procesos_omitidos.append((proc.pid, str(e)))
                    print(f"   ⚠️  Error: {e}")
                
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    print()
    print("⏳ Esperando 3 segundos para cierre limpio...")
    time.sleep(3)
    
    # Verificar si aún están corriendo y forzar si es necesario
    procesos_restantes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                if proc.pid == current_pid:
                    continue
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                # Verificar si es uno de los que intentamos detener
                if any(pid == proc.pid for pid, _ in procesos_detenidos):
                    print(f"⚠️  PID {proc.pid} aún activo, forzando cierre...")
                    try:
                        proc.kill()
                    except:
                        pass
                    procesos_restantes.append(proc.pid)
        except:
            pass
    
    print()
    print("="*80)
    print("📊 RESUMEN")
    print("="*80)
    print(f"✅ Procesos detenidos: {len(procesos_detenidos)}")
    
    if procesos_detenidos:
        print()
        print("Detenidos:")
        for pid, cmdline in procesos_detenidos:
            print(f"   - PID {pid}: {cmdline[:60]}...")
    
    if procesos_restantes:
        print(f"⚠️  Procesos que requirieron cierre forzado: {len(procesos_restantes)}")
        for pid in procesos_restantes:
            print(f"   - PID {pid}")
    
    if procesos_omitidos:
        print(f"⚠️  Procesos omitidos: {len(procesos_omitidos)}")
        for pid, error in procesos_omitidos:
            print(f"   - PID {pid}: {error}")
    
    print()
    print("="*80)
    print("✅ Todos los procesos han sido detenidos")
    print("="*80)

if __name__ == "__main__":
    detener_todos_procesos()











