"""
Script para mostrar los últimos logs de consumo de tokens del backend
Lee los logs de la consola o crea un archivo de log si no existe
"""
import os
import sys
from datetime import datetime

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 60)
print("LOGS DE CONSUMO DE TOKENS")
print("=" * 60)
print()
print("Los logs de tokens se imprimen en la consola del backend.")
print()
print("Busca en la ventana del backend las siguientes líneas:")
print()
print("  [INFO] Tokens de entrada (input): X tokens")
print("  [INFO] Tokens de salida (output): Y tokens")
print("  [INFO] Total de tokens usados: Z tokens")
print("  [INFO] Tokens descontados: Z tokens")
print("  [INFO] Tokens restantes después: N tokens")
print()
print("=" * 60)
print()
print("Si quieres guardar los logs automáticamente, puedes:")
print("1. Redirigir la salida del backend a un archivo:")
print("   python main.py > logs.txt 2>&1")
print()
print("2. O modificar el código para guardar en un archivo de log")
print()
print("¿Quieres que modifique el código para guardar logs en un archivo?")
print("(Esto guardaría cada consulta con timestamp y consumo de tokens)")

















