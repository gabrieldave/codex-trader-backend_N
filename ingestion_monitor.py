"""
📊 MONITOR PROFESIONAL DE INGESTA RAG
======================================

Monitor en tiempo real del proceso de ingesta con:
- Contadores thread-safe
- Estimaciones de velocidad y ETA
- Métricas de calidad de datos
- Visualización con rich (opcional)
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path

# Intentar importar rich, si no está disponible usar prints simples
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("⚠️  rich no está disponible. Usando salida simple. Instala con: pip install rich")

from dotenv import load_dotenv
import logging

# Importar config_ingesta solo si está disponible
try:
    import config_ingesta
    EMBEDDING_BATCH_SIZE = config_ingesta.EMBEDDING_BATCH_SIZE
except ImportError:
    EMBEDDING_BATCH_SIZE = 30  # Default

load_dotenv()

logger = logging.getLogger(__name__)

# Importar error_logger para resumen de errores
try:
    from error_logger import get_error_summary, get_recent_errors
    ERROR_LOGGER_AVAILABLE = True
except ImportError:
    ERROR_LOGGER_AVAILABLE = False

# Configuración
MONITOR_UPDATE_INTERVAL = int(os.getenv("MONITOR_UPDATE_INTERVAL", "5"))  # segundos
MAX_PROBLEMATIC_FILES_DETAIL = int(os.getenv("MAX_PROBLEMATIC_FILES_DETAIL", "20"))
REPORT_FILE_PATH = os.getenv("REPORT_FILE_PATH", "ingestion_report_{timestamp}.md")

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

console = Console() if RICH_AVAILABLE else None

# ============================================================================
# CLASES DE DATOS
# ============================================================================

@dataclass
class FileStats:
    """Estadísticas de un archivo procesado"""
    file_name: str
    file_path: str
    chunks_generated: int = 0
    status: str = "pending"  # pending, processing, completed, failed, suspicious
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error_message: Optional[str] = None
    is_suspicious: bool = False  # < 5 chunks

@dataclass
class MonitorStats:
    """Estadísticas globales del monitor"""
    total_files: int = 0
    files_processed: int = 0
    files_failed: int = 0
    files_suspicious: int = 0
    files_duplicated: int = 0  # Archivos duplicados saltados
    files_reindexed: int = 0    # Archivos reindexados
    total_chunks: int = 0
    total_errors: int = 0
    rate_limit_retries: int = 0
    network_errors: int = 0
    other_errors: int = 0
    start_time: float = field(default_factory=time.time)
    last_update_time: float = field(default_factory=time.time)
    
    # Métricas de velocidad
    files_per_minute: float = 0.0
    chunks_per_minute: float = 0.0
    
    # Métricas de rate limits (estimadas)
    estimated_rpm: float = 0.0
    estimated_tpm: float = 0.0
    
    # Calidad de datos
    min_chunks_per_file: int = float('inf')
    max_chunks_per_file: int = 0
    avg_chunks_per_file: float = 0.0
    
    # Archivos problemáticos
    suspicious_files: List[str] = field(default_factory=list)
    failed_files: List[Dict] = field(default_factory=list)
    duplicated_files: List[Dict] = field(default_factory=list)  # Archivos duplicados
    reindexed_files: List[Dict] = field(default_factory=list)    # Archivos reindexados
    
    # Historial de procesamiento
    file_stats: Dict[str, FileStats] = field(default_factory=dict)

# ============================================================================
# CLASE MONITOR
# ============================================================================

class IngestionMonitor:
    """Monitor thread-safe para el proceso de ingesta"""
    
    def __init__(self, total_files: int, update_interval: int = MONITOR_UPDATE_INTERVAL):
        self.stats = MonitorStats()
        self.stats.total_files = total_files
        self.update_interval = update_interval
        self.lock = threading.Lock()
        self.running = True
        self.monitor_thread = None
        
        # Inicializar rich si está disponible
        if RICH_AVAILABLE:
            self.console = Console()
            self.progress = None
            self.live = None
        else:
            self.console = None
    
    def start(self):
        """Inicia el monitor en un thread separado"""
        self.stats.start_time = time.time()
        self.stats.last_update_time = time.time()
        
        if RICH_AVAILABLE:
            self._start_rich_monitor()
        else:
            self._start_simple_monitor()
    
    def _start_rich_monitor(self):
        """Inicia monitor con rich"""
        self.monitor_thread = threading.Thread(target=self._rich_monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _start_simple_monitor(self):
        """Inicia monitor simple (sin rich)"""
        self.monitor_thread = threading.Thread(target=self._simple_monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def _rich_monitor_loop(self):
        """Loop del monitor con rich"""
        from rich.live import Live
        from rich.table import Table
        from rich.panel import Panel
        
        while self.running:
            try:
                table = self._create_rich_table()
                panel = Panel(table, title="📊 Monitor de Ingesta RAG", border_style="blue")
                
                if not hasattr(self, '_live') or self._live is None:
                    self._live = Live(panel, console=self.console, refresh_per_second=2)
                    self._live.start()
                else:
                    self._live.update(panel)
                
                time.sleep(self.update_interval)
            except Exception as e:
                print(f"Error en monitor: {e}")
                time.sleep(self.update_interval)
    
    def _simple_monitor_loop(self):
        """Loop del monitor simple"""
        while self.running:
            self._print_simple_update()
            time.sleep(self.update_interval)
    
    def _create_rich_table(self) -> Table:
        """Crea tabla de estadísticas con rich"""
        from rich.table import Table
        
        with self.lock:
            stats = self.stats
            elapsed = time.time() - stats.start_time
            progress_pct = (stats.files_processed / stats.total_files * 100) if stats.total_files > 0 else 0
            remaining = stats.total_files - stats.files_processed
            
            # Calcular ETA
            if stats.files_per_minute > 0:
                eta_minutes = remaining / stats.files_per_minute
                eta_str = f"{int(eta_minutes // 60)}h {int(eta_minutes % 60)}m"
            else:
                eta_str = "Calculando..."
        
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Métrica", style="cyan", width=25)
        table.add_column("Valor", style="green", width=30)
        
        table.add_row("📚 Progreso", f"{stats.files_processed}/{stats.total_files} ({progress_pct:.1f}%)")
        table.add_row("⏱️  Tiempo transcurrido", f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s")
        table.add_row("⚡ Velocidad", f"{stats.files_per_minute:.2f} archivos/min | {stats.chunks_per_minute:.0f} chunks/min")
        table.add_row("🎯 ETA", eta_str)
        table.add_row("📦 Chunks totales", f"{stats.total_chunks:,}")
        table.add_row("✅ Archivos completados", f"{stats.files_processed}")
        table.add_row("❌ Archivos fallidos", f"{stats.files_failed}")
        table.add_row("⚠️  Archivos sospechosos", f"{stats.files_suspicious}")
        table.add_row("⏭️  Archivos duplicados", f"{stats.files_duplicated}")
        table.add_row("🔄 Archivos reindexados", f"{stats.files_reindexed}")
        table.add_row("🔄 Reintentos (429)", f"{stats.rate_limit_retries}")
        table.add_row("📊 RPM estimado", f"{stats.estimated_rpm:.0f}/{3500} ({stats.estimated_rpm/3500*100:.1f}%)")
        table.add_row("📊 TPM estimado", f"{stats.estimated_tpm:,.0f}/{3_500_000:,} ({stats.estimated_tpm/3_500_000*100:.1f}%)")
        
        return table
    
    def _print_simple_update(self):
        """Imprime actualización simple (sin rich)"""
        with self.lock:
            stats = self.stats
            elapsed = time.time() - stats.start_time
            progress_pct = (stats.files_processed / stats.total_files * 100) if stats.total_files > 0 else 0
            remaining = stats.total_files - stats.files_processed
            
            if stats.files_per_minute > 0:
                eta_minutes = remaining / stats.files_per_minute
                eta_str = f"{int(eta_minutes // 60)}h {int(eta_minutes % 60)}m"
            else:
                eta_str = "Calculando..."
        
        print("\n" + "="*80)
        print(f"📊 MONITOR DE INGESTA RAG - {datetime.now().strftime('%H:%M:%S')}")
        print("="*80)
        print(f"📚 Progreso: {stats.files_processed}/{stats.total_files} ({progress_pct:.1f}%)")
        print(f"⏱️  Tiempo: {int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m {int(elapsed % 60)}s")
        print(f"⚡ Velocidad: {stats.files_per_minute:.2f} archivos/min | {stats.chunks_per_minute:.0f} chunks/min")
        print(f"🎯 ETA: {eta_str}")
        print(f"📦 Chunks: {stats.total_chunks:,}")
        print(f"✅ Completados: {stats.files_processed} | ❌ Fallidos: {stats.files_failed} | ⚠️  Sospechosos: {stats.files_suspicious}")
        print(f"⏭️  Duplicados: {stats.files_duplicated} | 🔄 Reindexados: {stats.files_reindexed}")
        print(f"🔄 Reintentos 429: {stats.rate_limit_retries}")
        print(f"📊 RPM: {stats.estimated_rpm:.0f}/3500 ({stats.estimated_rpm/3500*100:.1f}%) | TPM: {stats.estimated_tpm:,.0f}/3,500,000 ({stats.estimated_tpm/3_500_000*100:.1f}%)")
        print("="*80)
    
    # ========================================================================
    # MÉTODOS DE REGISTRO (THREAD-SAFE)
    # ========================================================================
    
    def on_file_started(self, file_name: str, file_path: str):
        """Registra inicio de procesamiento de un archivo"""
        with self.lock:
            file_stats = FileStats(
                file_name=file_name,
                file_path=file_path,
                status="processing",
                start_time=time.time()
            )
            self.stats.file_stats[file_name] = file_stats
    
    def on_file_completed(self, file_name: str, chunks_generated: int, is_suspicious: bool = False):
        """Registra completado de un archivo"""
        with self.lock:
            if file_name in self.stats.file_stats:
                file_stats = self.stats.file_stats[file_name]
                file_stats.status = "completed"
                file_stats.end_time = time.time()
                file_stats.chunks_generated = chunks_generated
                file_stats.is_suspicious = is_suspicious
            else:
                file_stats = FileStats(
                    file_name=file_name,
                    file_path=file_name,
                    status="completed",
                    chunks_generated=chunks_generated,
                    is_suspicious=is_suspicious,
                    end_time=time.time()
                )
                self.stats.file_stats[file_name] = file_stats
            
            self.stats.files_processed += 1
            self.stats.total_chunks += chunks_generated
            
            if is_suspicious:
                self.stats.files_suspicious += 1
                self.stats.suspicious_files.append(file_name)
            
            # Actualizar métricas de calidad
            if chunks_generated < self.stats.min_chunks_per_file:
                self.stats.min_chunks_per_file = chunks_generated
            if chunks_generated > self.stats.max_chunks_per_file:
                self.stats.max_chunks_per_file = chunks_generated
            
            # Recalcular promedio
            if self.stats.files_processed > 0:
                self.stats.avg_chunks_per_file = self.stats.total_chunks / self.stats.files_processed
            
            # Actualizar métricas de velocidad
            self._update_velocity_metrics()
    
    def on_file_duplicate(self, file_name: str, doc_id: str):
        """Registra un archivo duplicado (saltado)"""
        with self.lock:
            self.stats.files_duplicated += 1
            self.stats.duplicated_files.append({
                'file_name': file_name,
                'doc_id': doc_id,
                'timestamp': datetime.now().isoformat()
            })
            logger.info(f"⏭️  Duplicado detectado: {file_name} (doc_id: {doc_id[:8]}...)")
    
    def on_file_reindex(self, file_name: str, doc_id: str, deleted_chunks: int):
        """Registra un archivo reindexado"""
        with self.lock:
            self.stats.files_reindexed += 1
            self.stats.reindexed_files.append({
                'file_name': file_name,
                'doc_id': doc_id,
                'deleted_chunks': deleted_chunks,
                'timestamp': datetime.now().isoformat()
            })
            logger.info(f"🔄 Reindexando: {file_name} (eliminados {deleted_chunks} chunks anteriores)")
    
    def on_file_error(self, file_name: str, error_message: str, error_type: str = "other"):
        """Registra error en procesamiento de un archivo"""
        with self.lock:
            if file_name in self.stats.file_stats:
                file_stats = self.stats.file_stats[file_name]
                file_stats.status = "failed"
                file_stats.end_time = time.time()
                file_stats.error_message = error_message
            else:
                file_stats = FileStats(
                    file_name=file_name,
                    file_path=file_name,
                    status="failed",
                    error_message=error_message,
                    end_time=time.time()
                )
                self.stats.file_stats[file_name] = file_stats
            
            self.stats.files_failed += 1
            self.stats.total_errors += 1
            
            # Clasificar error
            if error_type == "rate_limit" or "429" in str(error_message):
                self.stats.rate_limit_retries += 1
            elif error_type == "network":
                self.stats.network_errors += 1
            else:
                self.stats.other_errors += 1
            
            self.stats.failed_files.append({
                'file_name': file_name,
                'error': error_message,
                'error_type': error_type,
                'timestamp': datetime.now().isoformat()
            })
            
            self._update_velocity_metrics()
    
    def on_rate_limit_retry(self):
        """Registra un reintento por rate limit"""
        with self.lock:
            self.stats.rate_limit_retries += 1
    
    def on_chunk_batch_processed(self, chunks_count: int, estimated_tokens: int):
        """Registra procesamiento de un batch de chunks"""
        with self.lock:
            # Estimar RPM y TPM
            now = time.time()
            elapsed_minutes = (now - self.stats.start_time) / 60
            
            if elapsed_minutes > 0:
                # RPM aproximado: cada batch es una request
                self.stats.estimated_rpm = (self.stats.total_chunks / EMBEDDING_BATCH_SIZE) / elapsed_minutes
                # TPM aproximado: chunks * 256 tokens (estimación conservadora)
                self.stats.estimated_tpm = (self.stats.total_chunks * 256) / elapsed_minutes
    
    def _update_velocity_metrics(self):
        """Actualiza métricas de velocidad"""
        now = time.time()
        elapsed_minutes = (now - self.stats.start_time) / 60
        
        if elapsed_minutes > 0:
            self.stats.files_per_minute = self.stats.files_processed / elapsed_minutes
            self.stats.chunks_per_minute = self.stats.total_chunks / elapsed_minutes
        
        self.stats.last_update_time = now
    
    def stop(self):
        """Detiene el monitor"""
        self.running = False
        if hasattr(self, '_live') and self._live is not None:
            self._live.stop()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def get_stats(self) -> MonitorStats:
        """Obtiene una copia de las estadísticas"""
        with self.lock:
            # Crear copia profunda de las estadísticas
            import copy
            return copy.deepcopy(self.stats)

# ============================================================================
# GENERADOR DE REPORTE
# ============================================================================

def generate_report(monitor: IngestionMonitor, output_file: Optional[str] = None) -> str:
    """Genera reporte final en formato markdown"""
    stats = monitor.get_stats()
    
    # Calcular tiempo total
    total_time = time.time() - stats.start_time
    hours = int(total_time // 3600)
    minutes = int((total_time % 3600) // 60)
    seconds = int(total_time % 60)
    
    start_datetime = datetime.fromtimestamp(stats.start_time)
    end_datetime = datetime.now()
    
    # Generar nombre de archivo
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = REPORT_FILE_PATH.format(timestamp=timestamp)
    
    report = f"""# 📊 Reporte de Ingesta RAG

**Fecha de generación**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📅 Información de Ejecución

- **Fecha y hora de inicio**: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}
- **Fecha y hora de finalización**: {end_datetime.strftime('%Y-%m-%d %H:%M:%S')}
- **Tiempo total de ejecución**: {hours}h {minutes}m {seconds}s

---

## 📈 Resumen General

| Métrica | Valor |
|---------|-------|
| **Archivos totales** | {stats.total_files} |
| **Archivos procesados correctamente** | {stats.files_processed} |
| **Archivos con errores** | {stats.files_failed} |
| **Archivos sospechosos** (< 5 chunks) | {stats.files_suspicious} |
| **Archivos duplicados saltados** | {stats.files_duplicated} |
| **Archivos reindexados** | {stats.files_reindexed} |
| **Chunks totales generados** | {stats.total_chunks:,} |
| **Promedio de chunks por archivo** | {stats.avg_chunks_per_file:.1f} |
| **Mínimo de chunks por archivo** | {stats.min_chunks_per_file if stats.min_chunks_per_file != float('inf') else 0} |
| **Máximo de chunks por archivo** | {stats.max_chunks_per_file} |

---

## ⚠️ Advertencias y Problemas

### Archivos Duplicados Saltados

"""
    
    if stats.duplicated_files:
        files_to_show = stats.duplicated_files[:MAX_PROBLEMATIC_FILES_DETAIL]
        remaining = len(stats.duplicated_files) - MAX_PROBLEMATIC_FILES_DETAIL
        
        for dup in files_to_show:
            report += f"- `{dup['file_name']}` (doc_id: {dup['doc_id'][:16]}...)\n"
        
        if remaining > 0:
            report += f"\n*... y {remaining} archivo(s) duplicado(s) más*\n"
    else:
        report += "*No se encontraron archivos duplicados.*\n"
    
    report += "\n### Archivos Reindexados\n\n"
    
    if stats.reindexed_files:
        files_to_show = stats.reindexed_files[:MAX_PROBLEMATIC_FILES_DETAIL]
        remaining = len(stats.reindexed_files) - MAX_PROBLEMATIC_FILES_DETAIL
        
        for reidx in files_to_show:
            report += f"- `{reidx['file_name']}` (doc_id: {reidx['doc_id'][:16]}...)\n"
            report += f"  - Chunks eliminados: {reidx['deleted_chunks']}\n"
        
        if remaining > 0:
            report += f"\n*... y {remaining} archivo(s) reindexado(s) más*\n"
    else:
        report += "*No se reindexaron archivos.*\n"
    
    report += "\n### Archivos Sospechosos (< 5 chunks)\n\n"

"""
    
    if stats.suspicious_files:
        # Mostrar primeros N en detalle
        files_to_show = stats.suspicious_files[:MAX_PROBLEMATIC_FILES_DETAIL]
        remaining = len(stats.suspicious_files) - MAX_PROBLEMATIC_FILES_DETAIL
        
        for file_name in files_to_show:
            file_stat = stats.file_stats.get(file_name)
            chunks = file_stat.chunks_generated if file_stat else "N/A"
            report += f"- `{file_name}` ({chunks} chunks)\n"
        
        if remaining > 0:
            report += f"\n*... y {remaining} archivo(s) más con menos de 5 chunks*\n"
    else:
        report += "*No se encontraron archivos sospechosos.*\n"
    
    report += "\n### Archivos con Error Total\n\n"
    
    if stats.failed_files:
        files_to_show = stats.failed_files[:MAX_PROBLEMATIC_FILES_DETAIL]
        remaining = len(stats.failed_files) - MAX_PROBLEMATIC_FILES_DETAIL
        
        for failed in files_to_show:
            report += f"- `{failed['file_name']}`\n"
            report += f"  - Error: {failed.get('error', 'Desconocido')}\n"
            report += f"  - Tipo: {failed.get('error_type', 'other')}\n"
            report += f"  - Timestamp: {failed.get('timestamp', 'N/A')}\n\n"
        
        if remaining > 0:
            report += f"*... y {remaining} archivo(s) más con errores*\n"
    else:
        report += "*No se encontraron archivos con errores totales.*\n"
    
    report += f"""
---

## ⚡ Métricas de Rendimiento

| Métrica | Valor |
|---------|-------|
| **Velocidad promedio (archivos/minuto)** | {stats.files_per_minute:.2f} |
| **Velocidad promedio (chunks/minuto)** | {stats.chunks_per_minute:.0f} |
| **RPM estimado promedio** | {stats.estimated_rpm:.0f} / 3,500 ({stats.estimated_rpm/3500*100:.1f}%) |
| **TPM estimado promedio** | {stats.estimated_tpm:,.0f} / 3,500,000 ({stats.estimated_tpm/3_500_000*100:.1f}%) |

---

## 🔄 Notas de Ejecución

- **Reintentos por rate limit (429)**: {stats.rate_limit_retries}
- **Errores de red**: {stats.network_errors}
- **Otros errores**: {stats.other_errors}
- **Total de errores**: {stats.total_errors}

---
"""
    
    # Agregar resumen de errores desde Supabase si está disponible
    if ERROR_LOGGER_AVAILABLE:
        try:
            error_summary = get_error_summary()
            recent_errors = get_recent_errors(limit=10)
            
            report += f"""
## 🔴 Resumen de Errores Registrados en Supabase

| Métrica | Valor |
|---------|-------|
| **Total de errores** | {error_summary.get('total_errors', 0)} |
| **Archivos afectados** | {error_summary.get('unique_files_affected', 0)} |

### Errores por Tipo

"""
            errors_by_type = error_summary.get('errors_by_type', {})
            if errors_by_type:
                for error_type, count in errors_by_type.items():
                    report += f"- **{error_type}**: {count}\n"
            else:
                report += "*No se registraron errores en Supabase.*\n"
            
            if recent_errors:
                report += "\n### Errores Recientes (Primeros 10)\n\n"
                for i, error in enumerate(recent_errors[:10], 1):
                    report += f"{i}. **{error.get('filename', 'N/A')}**\n"
                    report += f"   - Tipo: {error.get('error_type', 'N/A')}\n"
                    report += f"   - Mensaje: {error.get('error_message', 'N/A')[:100]}...\n"
                    report += f"   - Fecha: {error.get('created_at', 'N/A')}\n\n"
        except Exception as e:
            report += f"\n⚠️  Error obteniendo resumen de errores: {e}\n"
    
    report += """
---

---

## 📊 Distribución de Chunks por Archivo

"""
    
    if stats.files_processed > 0:
        # Calcular distribución
        chunks_distribution = defaultdict(int)
        for file_stat in stats.file_stats.values():
            if file_stat.status == "completed":
                chunks_distribution[file_stat.chunks_generated] += 1
        
        report += "| Rango de Chunks | Número de Archivos |\n"
        report += "|-----------------|-------------------|\n"
        
        # Agrupar en rangos
        ranges = [
            (0, 5, "0-5 (sospechosos)"),
            (5, 20, "5-20"),
            (20, 50, "20-50"),
            (50, 100, "50-100"),
            (100, 200, "100-200"),
            (200, float('inf'), "200+")
        ]
        
        for min_chunks, max_chunks, label in ranges:
            count = sum(1 for chunks, files in chunks_distribution.items() 
                       if min_chunks <= chunks < max_chunks)
            report += f"| {label} | {count} |\n"
    
    report += f"""
---

## ✅ Conclusión

"""
    
    # Determinar estado final
    has_issues = stats.files_failed > 0 or stats.files_suspicious > 0 or stats.files_duplicated > 0
    
    if stats.files_failed == 0 and stats.files_suspicious == 0 and stats.files_duplicated == 0:
        report += "✅ **Ingesta completada exitosamente sin errores ni advertencias.**\n"
    elif stats.files_failed == 0:
        issues = []
        if stats.files_suspicious > 0:
            issues.append(f"{stats.files_suspicious} archivo(s) sospechoso(s)")
        if stats.files_duplicated > 0:
            issues.append(f"{stats.files_duplicated} archivo(s) duplicado(s) saltado(s)")
        report += f"⚠️  **Ingesta completada con {', '.join(issues)} que requieren revisión manual.**\n"
    else:
        report += f"❌ **Ingesta completada con {stats.files_failed} error(es)"
        if stats.files_suspicious > 0:
            report += f", {stats.files_suspicious} archivo(s) sospechoso(s)"
        if stats.files_duplicated > 0:
            report += f", {stats.files_duplicated} archivo(s) duplicado(s)"
        report += ".**\n"
    
    report += f"""
- **Tasa de éxito**: {(stats.files_processed / stats.total_files * 100) if stats.total_files > 0 else 0:.1f}%
- **Archivos nuevos procesados**: {stats.files_processed}
- **Archivos duplicados saltados**: {stats.files_duplicated}
- **Archivos reindexados**: {stats.files_reindexed}
- **Chunks promedio por archivo**: {stats.avg_chunks_per_file:.1f}
- **Uso de capacidad OpenAI**: {stats.estimated_rpm/3500*100:.1f}% RPM, {stats.estimated_tpm/3_500_000*100:.1f}% TPM

---

*Reporte generado automáticamente por el sistema de ingesta RAG*
"""
    
    # Guardar archivo
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
    except Exception as e:
        print(f"⚠️  Error guardando reporte: {e}")
        # Usar nombre alternativo
        output_file = f"ingestion_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
    
    return report, output_file

