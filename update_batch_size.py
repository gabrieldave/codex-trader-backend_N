"""
🔧 ACTUALIZADOR DE BATCH_SIZE
==============================

Actualiza el batch_size en ingest_improved.py
"""

import sys
import re

def update_batch_size(new_size):
    """Actualiza el batch_size en ingest_improved.py"""
    try:
        with open('ingest_improved.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Buscar y reemplazar batch_size
        pattern = r'batch_size\s*=\s*\d+\s*#.*'
        replacement = f'batch_size = {new_size}  # Actualizado por calculate_optimal_batch.py'
        
        new_content = re.sub(pattern, replacement, content)
        
        # Si no encontró el patrón con comentario, buscar sin comentario
        if new_content == content:
            pattern = r'batch_size\s*=\s*\d+'
            replacement = f'batch_size = {new_size}  # Actualizado por calculate_optimal_batch.py'
            new_content = re.sub(pattern, replacement, content)
        
        with open('ingest_improved.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        print(f"✅ batch_size actualizado a {new_size}")
        return True
    except Exception as e:
        print(f"❌ Error actualizando batch_size: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            new_size = int(sys.argv[1])
            update_batch_size(new_size)
        except ValueError:
            print("❌ Error: El batch_size debe ser un número entero")
    else:
        print("Uso: python update_batch_size.py <nuevo_batch_size>")
        print("Ejemplo: python update_batch_size.py 30")
















