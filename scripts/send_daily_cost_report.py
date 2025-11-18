#!/usr/bin/env python3
"""
Script para enviar reporte diario de costos e ingresos por email.

Este script puede ejecutarse manualmente o configurarse como un CRON job
para enviar reportes periódicos automáticamente.

USO:
    # Reporte de ayer (por defecto)
    python scripts/send_daily_cost_report.py
    
    # Reporte de los últimos 7 días
    python scripts/send_daily_cost_report.py --days 7
    
    # Reporte de los últimos 30 días
    python scripts/send_daily_cost_report.py --days 30

CONFIGURACIÓN DE CRON:
    
    Para ejecutar este script automáticamente todos los días, puedes configurar
    un CRON job en tu plataforma de hosting:
    
    1. RAILWAY:
       - Ve a tu proyecto en Railway
       - Agrega un nuevo servicio "Cron Job"
       - Comando: python scripts/send_daily_cost_report.py
       - Schedule: 0 9 * * * (ejecuta todos los días a las 9:00 AM UTC)
       - Asegúrate de que el working directory sea el directorio del backend
       - Configura las variables de entorno necesarias (SUPABASE_URL, SUPABASE_SERVICE_KEY, etc.)
    
    2. RENDER:
       - Ve a tu dashboard de Render
       - Crea un nuevo "Cron Job"
       - Comando: python scripts/send_daily_cost_report.py
       - Schedule: 0 9 * * * (ejecuta todos los días a las 9:00 AM UTC)
       - Working Directory: /backend (o la ruta donde está este script)
       - Configura las variables de entorno necesarias
    
    3. SERVIDOR LINUX (crontab):
       # Editar crontab
       crontab -e
       
       # Agregar línea (ejecuta todos los días a las 9:00 AM)
       0 9 * * * cd /ruta/al/backend && /usr/bin/python3 scripts/send_daily_cost_report.py >> /var/log/codex_cost_report.log 2>&1
    
    4. WINDOWS (Task Scheduler):
       - Abre Task Scheduler
       - Crea una nueva tarea básica
       - Trigger: Diariamente a las 9:00 AM
       - Action: Iniciar un programa
       - Programa: python.exe
       - Argumentos: scripts\send_daily_cost_report.py
       - Directorio de inicio: C:\ruta\al\backend

NOTAS:
    - Asegúrate de que todas las variables de entorno estén configuradas
    - El script requiere acceso a la base de datos de Supabase
    - El email se envía a ADMIN_EMAIL configurado en .env
"""
import sys
import os
import argparse

# Agregar el directorio raíz al path para importar módulos
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.cost_reports import send_daily_cost_report


def main():
    parser = argparse.ArgumentParser(
        description="Envía un reporte de costos e ingresos por email al administrador"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Número de días hacia atrás para el reporte (por defecto: 1 = ayer)"
    )
    
    args = parser.parse_args()
    
    print(f"Iniciando envío de reporte de costos (últimos {args.days} días)...")
    
    success = send_daily_cost_report(days=args.days)
    
    if success:
        print("✅ Reporte enviado exitosamente")
        sys.exit(0)
    else:
        print("❌ Error al enviar reporte")
        sys.exit(1)


if __name__ == "__main__":
    main()

