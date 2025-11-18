"""
📊 BARRA DE PROGRESO VISUAL DE INGESTA
======================================

Muestra una barra de progreso en tiempo real del proceso de indexación.
"""

import os
import sys
import time
import psutil
import psycopg2
from datetime import datetime, timedelta
from urllib.parse import quote_plus
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

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("⚠️  Faltan variables de entorno")
    sys.exit(1)

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

try:
    import config
    collection_name = config.VECTOR_COLLECTION_NAME
except ImportError:
    collection_name = "knowledge"

# Intentar usar rich para barra de progreso bonita
try:
    from rich.console import Console
    from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

def get_chunks_count():
    """Obtiene conteo de chunks usando estadísticas"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=15)
        cur = conn.cursor()
        cur.execute("SET statement_timeout = '20s'")
        
        # Usar estadísticas de PostgreSQL (más rápido)
        cur.execute("""
            SELECT n_live_tup
            FROM pg_stat_user_tables
            WHERE schemaname = 'vecs' AND relname = %s
        """, (collection_name,))
        
        result = cur.fetchone()
        count = result[0] if result and result[0] else 0
        
        cur.close()
        conn.close()
        return count
    except:
        return None

def get_ingest_processes():
    """Obtiene procesos de ingesta"""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                if any(keyword in cmdline.lower() for keyword in ['ingest_optimized_rag', 'ingest_parallel_tier3', 'ingest_optimized_tier3']) and 'monitor' not in cmdline.lower() and 'barra' not in cmdline.lower():
                    processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

def get_total_files_estimate():
    """Estima total de archivos basado en chunks"""
    chunks = get_chunks_count()
    if chunks:
        # Estimación: promedio 100 chunks por archivo
        return int(chunks / 100)
    return None

def format_number(num):
    """Formatea número con separadores de miles"""
    return f"{num:,}"

def crear_barra_progreso_simple(porcentaje, ancho=50):
    """Crea barra de progreso simple con caracteres ASCII"""
    lleno = int(ancho * porcentaje / 100)
    vacio = ancho - lleno
    barra = "█" * lleno + "░" * vacio
    return f"[{barra}] {porcentaje:.1f}%"

def mostrar_progreso_simple():
    """Muestra progreso sin rich"""
    print("="*80)
    print("📊 BARRA DE PROGRESO DE INGESTA")
    print("="*80)
    print("Presiona Ctrl+C para salir\n")
    
    last_chunks = None
    start_time = time.time()
    start_chunks = None
    
    try:
        while True:
            # Verificar procesos
            processes = get_ingest_processes()
            has_process = len(processes) > 0
            
            # Obtener chunks
            chunks = get_chunks_count()
            
            if chunks is None:
                print("⚠️  No se puede obtener conteo (timeout)")
                time.sleep(10)
                continue
            
            # Inicializar contador de inicio
            if start_chunks is None:
                start_chunks = chunks
                last_chunks = chunks
            
            # Calcular incremento
            incremento = chunks - last_chunks if last_chunks else 0
            total_incremento = chunks - start_chunks if start_chunks else 0
            
            # Calcular tiempo
            elapsed = time.time() - start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            
            # Estimar archivos
            estimated_files = chunks // 100 if chunks else 0
            
            # Calcular velocidad
            if elapsed > 0:
                chunks_per_min = (total_incremento / elapsed) * 60
                files_per_min = chunks_per_min / 100
            else:
                chunks_per_min = 0
                files_per_min = 0
            
            # Limpiar pantalla (simular)
            print("\033[2J\033[H", end="")  # ANSI escape codes para limpiar
            
            print("="*80)
            print("📊 PROGRESO DE INDEXACIÓN")
            print("="*80)
            print(f"⏰ Tiempo transcurrido: {hours}h {minutes}m {seconds}s")
            print()
            
            # Barra de progreso (basada en chunks, ya que no sabemos el total exacto)
            # Usar un estimado basado en incremento
            if chunks_per_min > 0:
                # Estimar progreso basado en velocidad
                print(f"📦 Chunks indexados: {format_number(chunks)}")
                print(f"   Incremento: +{format_number(incremento)} desde última verificación")
                print()
                print(f"📚 Archivos estimados: ~{format_number(estimated_files)}")
                print()
                print(f"⚡ Velocidad: {chunks_per_min:.0f} chunks/min | {files_per_min:.2f} archivos/min")
            else:
                print(f"📦 Chunks indexados: {format_number(chunks)}")
                print(f"📚 Archivos estimados: ~{format_number(estimated_files)}")
            
            print()
            
            # Estado del proceso
            if has_process:
                print("🔄 Estado: PROCESO ACTIVO")
                for proc in processes:
                    try:
                        cpu = proc.cpu_percent(interval=0.1)
                        mem_mb = proc.memory_info().rss / (1024 * 1024)
                        print(f"   PID {proc.pid}: CPU {cpu:.1f}% | RAM {mem_mb:.0f} MB")
                    except:
                        pass
            else:
                print("⏸️  Estado: SIN PROCESOS ACTIVOS")
                print("   (Puede estar terminando o en pausa)")
            
            print()
            print("="*80)
            print("💡 Presiona Ctrl+C para salir")
            
            last_chunks = chunks
            
            time.sleep(5)  # Actualizar cada 5 segundos
            
    except KeyboardInterrupt:
        print("\n\n✅ Monitor detenido")
        if chunks:
            print(f"📦 Chunks finales: {format_number(chunks)}")
            print(f"📚 Archivos estimados: ~{format_number(estimated_files)}")

def mostrar_progreso_rich():
    """Muestra progreso con rich (más bonito)"""
    console = Console()
    
    processes = get_ingest_processes()
    has_process = len(processes) > 0
    
    if not has_process:
        console.print("[yellow]⚠️  No se detectan procesos de ingesta activos[/yellow]")
        console.print("[dim]Esperando a que se inicie el proceso...[/dim]")
        return
    
    last_chunks = None
    start_time = time.time()
    start_chunks = None
    
    try:
        with Live(console=console, refresh_per_second=2) as live:
            while True:
                chunks = get_chunks_count()
                
                if chunks is None:
                    live.update(Panel("[red]⚠️  Error obteniendo conteo[/red]", title="Error"))
                    time.sleep(5)
                    continue
                
                if start_chunks is None:
                    start_chunks = chunks
                    last_chunks = chunks
                
                incremento = chunks - last_chunks if last_chunks else 0
                total_incremento = chunks - start_chunks if start_chunks else 0
                
                elapsed = time.time() - start_time
                hours = int(elapsed // 3600)
                minutes = int((elapsed % 3600) // 60)
                seconds = int(elapsed % 60)
                
                estimated_files = chunks // 100
                
                if elapsed > 0:
                    chunks_per_min = (total_incremento / elapsed) * 60
                    files_per_min = chunks_per_min / 100
                else:
                    chunks_per_min = 0
                    files_per_min = 0
                
                # Crear tabla de progreso
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Métrica", style="cyan", width=30)
                table.add_column("Valor", style="green", width=50)
                
                table.add_row("📦 Chunks Indexados", f"{format_number(chunks)} (+{format_number(incremento)})")
                table.add_row("📚 Archivos Estimados", f"~{format_number(estimated_files)}")
                table.add_row("⚡ Velocidad", f"{chunks_per_min:.0f} chunks/min | {files_per_min:.2f} archivos/min")
                table.add_row("⏱️  Tiempo", f"{hours}h {minutes}m {seconds}s")
                
                # Barra de progreso visual
                if chunks_per_min > 0:
                    # Estimar progreso (usar un porcentaje basado en incremento)
                    # Como no sabemos el total, usamos un indicador de actividad
                    progress_pct = min(100, (total_incremento / max(1, chunks_per_min * elapsed / 60)) * 100) if chunks_per_min > 0 else 0
                    
                    bar_width = 50
                    filled = int(bar_width * progress_pct / 100)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    
                    table.add_row("📊 Progreso", f"[green]{bar}[/green] {progress_pct:.1f}%")
                
                # Estado
                status = "🔄 ACTIVO" if has_process else "⏸️  PAUSADO"
                table.add_row("🔄 Estado", status)
                
                # Info de procesos
                if processes:
                    for proc in processes:
                        try:
                            cpu = proc.cpu_percent(interval=0.1)
                            mem_mb = proc.memory_info().rss / (1024 * 1024)
                            table.add_row(f"   PID {proc.pid}", f"CPU: {cpu:.1f}% | RAM: {mem_mb:.0f} MB")
                        except:
                            pass
                
                panel = Panel(table, title="[bold cyan]📊 Progreso de Indexación[/bold cyan]", border_style="blue")
                live.update(panel)
                
                last_chunks = chunks
                
                # Verificar si terminó
                processes = get_ingest_processes()
                if not processes and elapsed > 300:  # 5 minutos sin procesos
                    console.print("\n[bold green]✅ Ingesta completada![/bold green]")
                    break
                
                time.sleep(2)  # Actualizar cada 2 segundos
                
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Monitor detenido[/yellow]")
        if chunks:
            console.print(f"[green]📦 Chunks finales: {format_number(chunks)}[/green]")

def main():
    if RICH_AVAILABLE:
        mostrar_progreso_rich()
    else:
        mostrar_progreso_simple()

if __name__ == "__main__":
    main()












