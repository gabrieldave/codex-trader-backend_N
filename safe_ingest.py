"""
Script seguro de ingestión que previene ejecuciones múltiples
"""
import os
import sys
import fcntl  # Para Linux/Mac
import msvcrt  # Para Windows
from pathlib import Path

# Importar el script de ingestión mejorado
import ingest_improved

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

LOCK_FILE = Path(__file__).parent / '.ingest.lock'

def acquire_lock():
    """Intenta adquirir un lock para prevenir ejecuciones múltiples"""
    try:
        if sys.platform == 'win32':
            # Windows: usar msvcrt para locking
            lock_file = open(LOCK_FILE, 'w')
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except IOError:
                lock_file.close()
                return None
        else:
            # Linux/Mac: usar fcntl
            lock_file = open(LOCK_FILE, 'w')
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock_file.write(str(os.getpid()))
                lock_file.flush()
                return lock_file
            except IOError:
                lock_file.close()
                return None
    except Exception as e:
        print(f"⚠️  Error al crear lock file: {e}")
        return None

def release_lock(lock_file):
    """Libera el lock"""
    try:
        if lock_file:
            lock_file.close()
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception as e:
        print(f"⚠️  Error al liberar lock: {e}")

if __name__ == "__main__":
    print("=" * 80)
    print("🔒 INGESTIÓN SEGURA (con protección contra ejecuciones múltiples)")
    print("=" * 80)
    print()
    
    # Intentar adquirir lock
    lock_file = acquire_lock()
    
    if lock_file is None:
        print("❌ ERROR: Ya hay un proceso de ingestión corriendo.")
        print()
        print("Si estás seguro de que no hay otro proceso corriendo,")
        print("elimina manualmente el archivo de lock:")
        print(f"   {LOCK_FILE}")
        print()
        print("O verifica procesos corriendo con:")
        print("   python check_ingest_running.py")
        sys.exit(1)
    
    try:
        print("✅ Lock adquirido. Iniciando ingestión...")
        print()
        
        # Ejecutar el script de ingestión mejorado
        # (El código de ingest_improved.py se ejecutará automáticamente al importarlo)
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"\n\n❌ Error durante la ingestión: {e}")
        import traceback
        traceback.print_exc()
    finally:
        release_lock(lock_file)
        print("\n🔓 Lock liberado")

