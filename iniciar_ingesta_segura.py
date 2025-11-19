"""
🚀 INICIAR INGESTA DE FORMA SEGURA
===================================

Inicia la ingesta con configuración reducida y monitoreo.
"""

import os
import sys
import subprocess
import time

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    print("="*80)
    print("🚀 INICIANDO INGESTA CON CONFIGURACIÓN REDUCIDA")
    print("="*80)
    print()
    
    # Verificar configuración
    try:
        import config_ingesta
        print("📋 Configuración actual:")
        print(f"   - Workers: {config_ingesta.MAX_WORKERS}")
        print(f"   - Batch size: {config_ingesta.EMBEDDING_BATCH_SIZE}")
        print(f"   - RPM Target: {config_ingesta.OPENAI_RPM_TARGET}")
        print(f"   - TPM Target: {config_ingesta.OPENAI_TPM_TARGET:,}")
        print()
        
        if config_ingesta.MAX_WORKERS > 10:
            print("⚠️  ADVERTENCIA: Workers muy altos para situación actual")
            print("   Considera reducir a 5 workers")
            print()
    except Exception as e:
        print(f"⚠️  Error leyendo configuración: {e}")
        print()
    
    print("✅ Iniciando proceso de ingesta...")
    print("💡 El proceso se ejecutará en esta ventana")
    print("   Presiona Ctrl+C para detener")
    print()
    print("="*80)
    print()
    
    # Ejecutar ingesta
    try:
        subprocess.run([sys.executable, "ingest_optimized_rag.py"], check=True)
    except KeyboardInterrupt:
        print("\n\n⚠️  Ingesta detenida por el usuario")
    except Exception as e:
        print(f"\n❌ Error ejecutando ingesta: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
















