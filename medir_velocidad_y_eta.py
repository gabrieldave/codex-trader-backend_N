"""
⚡ MEDIR VELOCIDAD Y CALCULAR HORA DE FINALIZACIÓN
==================================================
"""

import os
import sys
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
import config
import time
from datetime import datetime, timedelta

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

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("❌ Error: Faltan variables de entorno")
    sys.exit(1)

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

def get_indexed_count():
    """Obtiene número de archivos indexados"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor()
        # Aumentar timeout para consultas grandes
        cur.execute("SET statement_timeout = '60s'")
        
        # Usar aproximación más rápida si hay muchos datos
        try:
            cur.execute(f"""
                SELECT COUNT(DISTINCT metadata->>'file_name') as count
                FROM vecs.{config.VECTOR_COLLECTION_NAME}
                WHERE metadata->>'file_name' IS NOT NULL
            """)
            count = cur.fetchone()[0]
        except psycopg2.errors.QueryCanceled:
            # Si timeout, usar método alternativo más rápido
            print("   ⚠️  Consulta lenta, usando método alternativo...")
            cur.execute(f"""
                SELECT COUNT(*) as total_chunks
                FROM vecs.{config.VECTOR_COLLECTION_NAME}
            """)
            total_chunks = cur.fetchone()[0]
            # Estimar basado en chunks promedio por archivo (~100)
            count = int(total_chunks / 100)
            print(f"   💡 Estimado basado en {total_chunks:,} chunks totales")
        
        cur.close()
        conn.close()
        return count
    except Exception as e:
        print(f"⚠️  Error obteniendo conteo: {e}")
        return None

def get_total_files():
    """Cuenta archivos totales en data/"""
    data_dir = "./data"
    total = 0
    if os.path.exists(data_dir):
        supported_extensions = {'.pdf', '.epub', '.txt', '.docx', '.md', '.doc'}
        for root, dirs, files in os.walk(data_dir):
            for file in files:
                if os.path.splitext(file)[1].lower() in supported_extensions:
                    total += 1
    return total

print("=" * 80)
print("⚡ MEDICIÓN DE VELOCIDAD Y CÁLCULO DE ETA")
print("=" * 80)
print(f"Tiempo actual: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Primera medición
print("📊 Primera medición...")
indexed_1 = get_indexed_count()
total_files = get_total_files()
time_1 = time.time()

if indexed_1 is None:
    print("❌ No se pudo obtener el conteo inicial")
    sys.exit(1)

print(f"   Archivos indexados: {indexed_1}/{total_files}")
print(f"   Pendientes: {total_files - indexed_1}")
print()

# Esperar 30 segundos para medir velocidad
print("⏳ Esperando 30 segundos para medir velocidad...")
time.sleep(30)

# Segunda medición
print("📊 Segunda medición...")
indexed_2 = get_indexed_count()
time_2 = time.time()

if indexed_2 is None:
    print("❌ No se pudo obtener el conteo final")
    sys.exit(1)

print(f"   Archivos indexados: {indexed_2}/{total_files}")
print()

# Calcular velocidad
elapsed_seconds = time_2 - time_1
elapsed_minutes = elapsed_seconds / 60
files_processed = indexed_2 - indexed_1

if elapsed_minutes > 0:
    files_per_minute = files_processed / elapsed_minutes
    files_per_hour = files_per_minute * 60
else:
    files_per_minute = 0
    files_per_hour = 0

# Calcular tiempo restante
remaining = total_files - indexed_2
progress = (indexed_2 / total_files * 100) if total_files > 0 else 0

if files_per_minute > 0:
    minutes_remaining = remaining / files_per_minute
    hours_remaining = minutes_remaining / 60
    
    # Calcular hora de finalización
    finish_time = datetime.now() + timedelta(minutes=minutes_remaining)
else:
    minutes_remaining = 0
    hours_remaining = 0
    finish_time = None

# Mostrar resultados
print("=" * 80)
print("📈 RESULTADOS")
print("=" * 80)
print()

print(f"📊 PROGRESO:")
print(f"   • Archivos indexados: {indexed_2}/{total_files} ({progress:.2f}%)")
print(f"   • Archivos pendientes: {remaining}")
print()

print(f"⚡ VELOCIDAD:")
print(f"   • Archivos procesados en {elapsed_seconds:.1f}s: {files_processed}")
print(f"   • Velocidad: {files_per_minute:.2f} archivos/minuto")
print(f"   • Velocidad: {files_per_hour:.1f} archivos/hora")
print()

if files_per_minute > 0:
    hours_int = int(hours_remaining)
    minutes_int = int(minutes_remaining % 60)
    seconds_int = int((minutes_remaining % 1) * 60)
    
    print(f"⏱️  TIEMPO ESTIMADO:")
    if hours_int > 0:
        print(f"   • Tiempo restante: {hours_int}h {minutes_int}m {seconds_int}s")
    else:
        print(f"   • Tiempo restante: {minutes_int}m {seconds_int}s")
    print(f"   • Horas restantes: {hours_remaining:.2f} horas")
    print()
    
    if finish_time:
        print(f"🎯 HORA DE FINALIZACIÓN ESTIMADA:")
        print(f"   • Fecha: {finish_time.strftime('%Y-%m-%d')}")
        print(f"   • Hora: {finish_time.strftime('%H:%M:%S')}")
        print()
        
        # Calcular tiempo hasta finalización en formato legible
        now = datetime.now()
        time_diff = finish_time - now
        
        hours = int(time_diff.total_seconds() // 3600)
        minutes = int((time_diff.total_seconds() % 3600) // 60)
        seconds = int(time_diff.total_seconds() % 60)
        
        print(f"   • Tiempo restante: {hours}h {minutes}m {seconds}s")
else:
    print("⚠️  No se pudo calcular velocidad (proceso puede estar detenido)")

print()
print("=" * 80)

# Análisis adicional
if files_per_minute > 0:
    print()
    print("💡 ANÁLISIS:")
    
    if files_per_minute < 5:
        print("   ⚠️  Velocidad baja (< 5 archivos/min)")
        print("   💡 Considera aumentar workers o verificar conexión")
    elif files_per_minute < 15:
        print("   ✅ Velocidad moderada (5-15 archivos/min)")
        print("   💡 Puedes aumentar workers para más velocidad")
    elif files_per_minute < 30:
        print("   ✅ Velocidad buena (15-30 archivos/min)")
        print("   💡 Sistema funcionando bien")
    else:
        print("   🚀 Velocidad excelente (> 30 archivos/min)")
        print("   💡 Sistema optimizado al máximo")
    
    print()
    print("=" * 80)

