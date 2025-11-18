"""
⚙️ CONFIGURACIÓN REDUCIDA PARA EVITAR SOBRECARGA
=================================================

Usa esta configuración cuando reanudes la ingesta para evitar sobrecargar Supabase.
"""

# Copia este contenido a config_ingesta.py cuando reanudes

# Workers reducidos (de 15 a 5)
MAX_WORKERS = 5

# Batch size reducido (de 30 a 20)
EMBEDDING_BATCH_SIZE = 20

# Resto de configuración igual
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Rate limits (mantener al 70% pero con menos workers)
OPENAI_RPM_TARGET = 2000  # Reducido de 3500
OPENAI_TPM_TARGET = 2000000  # Reducido de 3500000

print("="*80)
print("⚙️  CONFIGURACIÓN REDUCIDA")
print("="*80)
print()
print("📋 Cambios aplicados:")
print(f"   - MAX_WORKERS: 15 → {MAX_WORKERS}")
print(f"   - EMBEDDING_BATCH_SIZE: 30 → {EMBEDDING_BATCH_SIZE}")
print(f"   - RPM Target: 3500 → {OPENAI_RPM_TARGET}")
print(f"   - TPM Target: 3,500,000 → {OPENAI_TPM_TARGET:,}")
print()
print("💡 Para aplicar:")
print("   1. Copia estos valores a config_ingesta.py")
print("   2. O reemplaza el archivo completo")
print("   3. Ejecuta solo 1 proceso de ingesta (no 3)")
print("="*80)












