# Scripts de Codex Trader

Este directorio contiene scripts auxiliares para automatizar tareas del sistema.

## send_daily_cost_report.py

Script para enviar reportes periódicos de costos e ingresos por email al administrador.

### Uso

```bash
# Reporte de ayer (por defecto)
python scripts/send_daily_cost_report.py

# Reporte de los últimos 7 días
python scripts/send_daily_cost_report.py --days 7

# Reporte de los últimos 30 días
python scripts/send_daily_cost_report.py --days 30
```

### Configuración de CRON

Para ejecutar este script automáticamente todos los días, puedes configurar un CRON job en tu plataforma de hosting:

#### Railway

1. Ve a tu proyecto en Railway
2. Agrega un nuevo servicio "Cron Job"
3. Configura:
   - **Comando**: `python scripts/send_daily_cost_report.py`
   - **Schedule**: `0 9 * * *` (ejecuta todos los días a las 9:00 AM UTC)
   - **Working Directory**: `/backend` (o la ruta donde está este script)
4. Asegúrate de configurar todas las variables de entorno necesarias:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASS`
   - `EMAIL_FROM`
   - `ADMIN_EMAIL`

#### Render

1. Ve a tu dashboard de Render
2. Crea un nuevo "Cron Job"
3. Configura:
   - **Comando**: `python scripts/send_daily_cost_report.py`
   - **Schedule**: `0 9 * * *` (ejecuta todos los días a las 9:00 AM UTC)
   - **Working Directory**: `/backend` (o la ruta donde está este script)
4. Configura las variables de entorno necesarias (mismas que Railway)

#### Servidor Linux (crontab)

```bash
# Editar crontab
crontab -e

# Agregar línea (ejecuta todos los días a las 9:00 AM)
0 9 * * * cd /ruta/al/backend && /usr/bin/python3 scripts/send_daily_cost_report.py >> /var/log/codex_cost_report.log 2>&1
```

#### Windows (Task Scheduler)

1. Abre Task Scheduler
2. Crea una nueva tarea básica
3. Configura:
   - **Trigger**: Diariamente a las 9:00 AM
   - **Action**: Iniciar un programa
   - **Programa**: `python.exe` (o la ruta completa a tu Python)
   - **Argumentos**: `scripts\send_daily_cost_report.py`
   - **Directorio de inicio**: `C:\ruta\al\backend`

### Formato del Schedule (Cron)

El formato de schedule es: `minuto hora día mes día-semana`

Ejemplos:
- `0 9 * * *` - Todos los días a las 9:00 AM
- `0 0 * * *` - Todos los días a medianoche
- `0 9 * * 1` - Todos los lunes a las 9:00 AM
- `0 9 1 * *` - El primer día de cada mes a las 9:00 AM

### Notas

- Asegúrate de que todas las variables de entorno estén configuradas
- El script requiere acceso a la base de datos de Supabase
- El email se envía a `ADMIN_EMAIL` configurado en `.env`
- Si el script falla, verifica los logs para ver el error específico

