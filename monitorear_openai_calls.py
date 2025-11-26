"""
🔍 MONITOREO DE LLAMADAS A OPENAI
==================================

Monitorea las llamadas a OpenAI para verificar rate limiting y cuellos de botella
"""

import os
import sys
import time
import psutil
import requests
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def get_env(key):
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

print("=" * 80)
print("🔍 MONITOREO DE LLAMADAS A OPENAI")
print("=" * 80)

# Buscar proceso de ingest
ingest_proc = None
for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
    try:
        if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
            cmdline = ' '.join(proc.info['cmdline'])
            if 'ingest_improved.py' in cmdline.lower():
                ingest_proc = proc
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        continue

if not ingest_proc:
    print("❌ No se encontró proceso de ingest corriendo")
    sys.exit(1)

print(f"\n✅ Proceso encontrado: PID {ingest_proc.pid}")
print(f"Monitoreando conexiones de red y actividad de OpenAI...")
print(f"\n⏳ Monitoreando durante 2 minutos...")
print(f"(Presiona Ctrl+C para detener antes)\n")

# Monitorear conexiones de red
openai_connections = []
api_calls_timestamps = []
start_time = time.time()
monitor_duration = 120  # 2 minutos

print("=" * 80)
print("📊 MONITOREO EN TIEMPO REAL")
print("=" * 80)

try:
    check_count = 0
    while time.time() - start_time < monitor_duration:
        check_count += 1
        current_time = time.time()
        elapsed = current_time - start_time
        
        # Obtener conexiones de red
        try:
            connections = ingest_proc.net_connections()
            openai_conns = []
            
            for conn in connections:
                if conn.status == 'ESTABLISHED':
                    # OpenAI usa api.openai.com
                    if 'openai' in str(conn.remote_address).lower() or conn.remote_address[0] in ['52.152.96.252', '20.14.246.208', '20.14.246.209']:
                        openai_conns.append(conn)
            
            if openai_conns:
                openai_connections.extend(openai_conns)
                api_calls_timestamps.append(current_time)
                print(f"[{int(elapsed//60)}m {int(elapsed%60)}s] ✅ {len(openai_conns)} conexión(es) activa(s) con OpenAI")
            else:
                if check_count % 10 == 0:  # Mostrar cada 10 checks
                    print(f"[{int(elapsed//60)}m {int(elapsed%60)}s] ⏳ Esperando llamadas a OpenAI...")
        
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"⚠️  Error accediendo al proceso: {e}")
            break
        except Exception as e:
            # Ignorar errores menores
            pass
        
        time.sleep(2)  # Verificar cada 2 segundos

except KeyboardInterrupt:
    print("\n\n⏹️  Monitoreo detenido por el usuario")

# Análisis de resultados
print("\n" + "=" * 80)
print("📊 ANÁLISIS DE RESULTADOS")
print("=" * 80)

total_time = time.time() - start_time
unique_connections = len(set(str(c.remote_address) for c in openai_connections if c))

print(f"\n📈 ESTADÍSTICAS:")
print(f"   Tiempo monitoreado: {int(total_time//60)}m {int(total_time%60)}s")
print(f"   Conexiones detectadas: {len(openai_connections)}")
print(f"   Conexiones únicas: {unique_connections}")
print(f"   Timestamps de actividad: {len(api_calls_timestamps)}")

# Análisis de frecuencia
if len(api_calls_timestamps) > 1:
    intervals = []
    for i in range(1, len(api_calls_timestamps)):
        interval = api_calls_timestamps[i] - api_calls_timestamps[i-1]
        intervals.append(interval)
    
    if intervals:
        avg_interval = sum(intervals) / len(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)
        calls_per_minute = 60 / avg_interval if avg_interval > 0 else 0
        
        print(f"\n⏱️  FRECUENCIA DE LLAMADAS:")
        print(f"   Intervalo promedio: {avg_interval:.2f} segundos")
        print(f"   Intervalo mínimo: {min_interval:.2f} segundos")
        print(f"   Intervalo máximo: {max_interval:.2f} segundos")
        print(f"   Llamadas por minuto: ~{calls_per_minute:.1f}")
        
        # Verificar rate limiting
        print(f"\n🔍 ANÁLISIS DE RATE LIMITING:")
        
        # OpenAI tiene diferentes límites según el plan
        # Típicamente: 3,500 RPM (requests per minute) para tier 1
        # O 10,000 TPM (tokens per minute)
        
        if calls_per_minute > 3000:
            print(f"   ⚠️  MUY ALTA: {calls_per_minute:.0f} llamadas/minuto")
            print(f"   Puede estar cerca del límite de rate limiting")
        elif calls_per_minute > 1000:
            print(f"   ⚠️  ALTA: {calls_per_minute:.0f} llamadas/minuto")
            print(f"   Puede estar experimentando rate limiting")
        elif calls_per_minute > 100:
            print(f"   ✅ MODERADA: {calls_per_minute:.0f} llamadas/minuto")
            print(f"   Probablemente no hay rate limiting")
        else:
            print(f"   ✅ BAJA: {calls_per_minute:.0f} llamadas/minuto")
            print(f"   No hay rate limiting")
        
        # Verificar si hay pausas largas (posible rate limiting)
        long_pauses = [i for i in intervals if i > 5]
        if long_pauses:
            print(f"\n⚠️  PAUSAS LARGAS DETECTADAS:")
            print(f"   {len(long_pauses)} pausa(s) de más de 5 segundos")
            print(f"   Esto puede indicar rate limiting o esperas")
            print(f"   Pausa más larga: {max(long_pauses):.1f} segundos")
        else:
            print(f"\n✅ NO HAY PAUSAS LARGAS:")
            print(f"   Las llamadas son consistentes")
            print(f"   No hay evidencia de rate limiting")
        
        # Verificar si es secuencial
        if avg_interval < 0.5:
            print(f"\n✅ PROCESAMIENTO PARALELO:")
            print(f"   Intervalo muy corto ({avg_interval:.2f}s)")
            print(f"   Probablemente hay múltiples llamadas en paralelo")
        elif avg_interval < 2:
            print(f"\n⚠️  PROCESAMIENTO SEMI-SECUENCIAL:")
            print(f"   Intervalo moderado ({avg_interval:.2f}s)")
            print(f"   Puede haber algo de paralelismo limitado")
        else:
            print(f"\n⚠️  PROCESAMIENTO SECUENCIAL:")
            print(f"   Intervalo largo ({avg_interval:.2f}s)")
            print(f"   Las llamadas son secuenciales, no paralelas")
            print(f"   Esto explica la lentitud con batch_size=150")

elif len(api_calls_timestamps) == 1:
    print(f"\n⚠️  SOLO UNA LLAMADA DETECTADA:")
    print(f"   Puede estar esperando la primera respuesta")
    print(f"   O las llamadas son muy lentas")
else:
    print(f"\n❌ NO SE DETECTARON LLAMADAS A OPENAI:")
    print(f"   Esto puede indicar:")
    print(f"   • El proceso no está haciendo llamadas")
    print(f"   • Está en otra fase (cargando archivos, etc.)")
    print(f"   • Hay un problema con las conexiones")

# Verificar uso de CPU durante el monitoreo
print(f"\n💻 USO DE RECURSOS:")
try:
    cpu_samples = []
    for _ in range(10):
        cpu = ingest_proc.cpu_percent(interval=0.5)
        cpu_samples.append(cpu)
        time.sleep(0.5)
    
    avg_cpu = sum(cpu_samples) / len(cpu_samples)
    print(f"   CPU promedio: {avg_cpu:.1f}%")
    
    if avg_cpu > 80:
        print(f"   ✅ CPU alto - Está procesando activamente")
    elif avg_cpu > 40:
        print(f"   ⚠️  CPU moderado - Puede estar esperando")
    else:
        print(f"   ⚠️  CPU bajo - Puede estar bloqueado o esperando")
except:
    pass

# Conclusiones
print(f"\n" + "=" * 80)
print("🎯 CONCLUSIONES")
print("=" * 80)

if len(api_calls_timestamps) > 10:
    if avg_interval > 2:
        print(f"\n✅ CONFIRMADO: El problema es procesamiento SECUENCIAL")
        print(f"   • Las llamadas a OpenAI son secuenciales")
        print(f"   • Con batch_size=150 y miles de chunks, esto toma mucho tiempo")
        print(f"   • Cada chunk espera al anterior")
        print(f"\n💡 SOLUCIÓN:")
        print(f"   Reducir batch_size a 50-80 para menos chunks por batch")
        print(f"   Esto reducirá el tiempo total aunque sea secuencial")
    elif calls_per_minute > 1000:
        print(f"\n✅ CONFIRMADO: Posible RATE LIMITING")
        print(f"   • Demasiadas llamadas por minuto")
        print(f"   • OpenAI puede estar limitando las requests")
        print(f"\n💡 SOLUCIÓN:")
        print(f"   Reducir batch_size para menos llamadas simultáneas")
    else:
        print(f"\n✅ Las llamadas a OpenAI están funcionando normalmente")
        print(f"   • No hay rate limiting evidente")
        print(f"   • El problema puede ser el tamaño del batch")
else:
    print(f"\n⚠️  No se detectaron suficientes llamadas para concluir")
    print(f"   • El proceso puede estar en otra fase")
    print(f"   • O las llamadas son muy lentas")
    print(f"\n💡 RECOMENDACIÓN:")
    print(f"   Monitorear por más tiempo o verificar logs del proceso")

print("\n" + "=" * 80)
























