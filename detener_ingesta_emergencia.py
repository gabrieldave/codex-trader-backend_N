"""
🚨 DETENER INGESTA POR EMERGENCIA
===================================

Detiene los procesos de ingesta debido a sobrecarga en Supabase.
"""

import os
import sys
import psutil
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def get_ingest_processes():
    """Obtiene procesos de ingesta"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if any(keyword in cmdline.lower() for keyword in ['ingest_parallel_tier3', 'ingest_optimized_rag', 'ingest_optimized_tier3']) and 'monitor' not in cmdline.lower():
                    processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def main():
    print("="*80)
    print("🚨 DETENCIÓN DE EMERGENCIA - SOBRECARGA EN SUPABASE")
    print("="*80)
    print()
    print("📊 Análisis de la situación:")
    print("   - Memory Supabase: Solo 77.95 MB libre de 1.8 GB (CRÍTICO)")
    print("   - CPU I/O Wait: 75.87% (sobrecarga de disco)")
    print("   - Base de datos: 5.05 GB / 8 GB (63%, pero creciendo)")
    print()
    print("🔴 ACCIÓN: Deteniendo procesos de ingesta para aliviar carga")
    print()
    
    procesos = get_ingest_processes()
    
    if not procesos:
        print("✅ No hay procesos de ingesta activos")
        return
    
    print(f"🛑 Deteniendo {len(procesos)} proceso(s)...")
    print()
    
    for proc in procesos:
        try:
            cpu = proc.cpu_percent(interval=0.1)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            print(f"   Deteniendo PID {proc.pid} (CPU: {cpu:.1f}%, RAM: {mem_mb:.0f} MB)...")
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"   ⚠️  Error con PID {proc.pid}: {e}")
    
    print()
    print("⏳ Esperando 5 segundos para cierre limpio...")
    time.sleep(5)
    
    # Verificar si aún están corriendo
    procesos_restantes = get_ingest_processes()
    if procesos_restantes:
        print(f"⚠️  {len(procesos_restantes)} proceso(s) aún activo(s), forzando cierre...")
        for proc in procesos_restantes:
            try:
                print(f"   Forzando cierre de PID {proc.pid}...")
                proc.kill()
            except:
                pass
        time.sleep(2)
    
    # Verificación final
    procesos_finales = get_ingest_processes()
    if procesos_finales:
        print(f"❌ Aún quedan {len(procesos_finales)} proceso(s) activo(s)")
    else:
        print("✅ Todos los procesos han sido detenidos correctamente")
    
    print()
    print("="*80)
    print("📝 PRÓXIMOS PASOS:")
    print("="*80)
    print("1. ✅ Espera 5-10 minutos para que Supabase se estabilice")
    print("2. 📊 Verifica el dashboard de Supabase (memoria, CPU, IOPS)")
    print("3. 🔧 Cuando reanudes, usa configuración reducida:")
    print("   - MAX_WORKERS = 5 (en lugar de 15)")
    print("   - Solo 1 proceso (en lugar de 3)")
    print("   - EMBEDDING_BATCH_SIZE = 20 (en lugar de 30)")
    print("4. 📈 Monitorea constantemente el uso de recursos")
    print("="*80)

if __name__ == "__main__":
    main()























