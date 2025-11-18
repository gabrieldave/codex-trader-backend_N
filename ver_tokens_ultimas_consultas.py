"""
Script para ver el consumo de tokens de las últimas consultas
"""
import json
import os
import sys
from datetime import datetime

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

log_file = "tokens_log.json"

if not os.path.exists(log_file):
    print("=" * 60)
    print("No se encontró el archivo de logs de tokens.")
    print("=" * 60)
    print()
    print("El archivo se creará automáticamente cuando hagas consultas.")
    print("Asegúrate de que el backend esté corriendo y haz algunas consultas.")
    sys.exit(0)

try:
    with open(log_file, 'r', encoding='utf-8') as f:
        logs = json.load(f)
    
    if not logs:
        print("No hay logs de tokens aún.")
        sys.exit(0)
    
    print("=" * 60)
    print(f"CONSUMO DE TOKENS - ÚLTIMAS {len(logs)} CONSULTAS")
    print("=" * 60)
    print()
    
    # Mostrar las últimas consultas (más recientes primero)
    logs_reverse = list(reversed(logs))
    
    total_input = 0
    total_output = 0
    total_tokens = 0
    
    for i, log in enumerate(logs_reverse, 1):
        timestamp = log.get('timestamp', 'N/A')
        try:
            dt = datetime.fromisoformat(timestamp)
            timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            timestamp_str = timestamp
        
        modelo = log.get('model', 'N/A')
        modo = log.get('response_mode', 'N/A')
        query = log.get('query_preview', 'N/A')
        input_tokens = log.get('input_tokens', 0)
        output_tokens = log.get('output_tokens', 0)
        total = log.get('total_tokens', 0)
        
        total_input += input_tokens
        total_output += output_tokens
        total_tokens += total
        
        print(f"Consulta #{i} - {timestamp_str}")
        print(f"  Modo: {modo}")
        print(f"  Modelo: {modelo}")
        print(f"  Pregunta: {query}")
        print(f"  Input tokens: {input_tokens}")
        print(f"  Output tokens: {output_tokens}")
        print(f"  Total tokens: {total}")
        print()
    
    print("=" * 60)
    print("RESUMEN TOTAL")
    print("=" * 60)
    print(f"Total de consultas: {len(logs)}")
    print(f"Total input tokens: {total_input}")
    print(f"Total output tokens: {total_output}")
    print(f"Total tokens usados: {total_tokens}")
    print("=" * 60)
    
    # Si hay exactamente 2 consultas, mostrar resumen específico
    if len(logs) >= 2:
        print()
        print("=" * 60)
        print("ÚLTIMAS 2 CONSULTAS (las más recientes)")
        print("=" * 60)
        for i, log in enumerate(logs_reverse[:2], 1):
            timestamp = log.get('timestamp', 'N/A')
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                timestamp_str = timestamp
            
            modo = log.get('response_mode', 'N/A')
            query = log.get('query_preview', 'N/A')
            total = log.get('total_tokens', 0)
            
            print(f"\nConsulta {i} ({timestamp_str}):")
            print(f"  Modo: {modo}")
            print(f"  Pregunta: {query}")
            print(f"  Tokens usados: {total}")
        
        total_ultimas_2 = sum(log.get('total_tokens', 0) for log in logs_reverse[:2])
        print(f"\nTotal de las últimas 2 consultas: {total_ultimas_2} tokens")
        print("=" * 60)

except Exception as e:
    print(f"Error al leer logs: {e}")
    import traceback
    traceback.print_exc()












