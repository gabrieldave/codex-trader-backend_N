"""
Módulo para generar y enviar reportes periódicos de costos e ingresos.
Proporciona funciones para crear reportes diarios y semanales.
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from supabase import create_client

# Cargar variables de entorno
load_dotenv()

# Configurar cliente de Supabase (se inicializará cuando se necesite)
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def _derive_rest_url_from_db(db_url: str) -> str:
    """
    Deriva la URL REST de Supabase desde una URL de conexión a la base de datos.
    
    Acepta algo como:
    postgresql://postgres:pass@db.eixvqedpyuybfywmdulg.supabase.co:5432/postgres
    
    y devuelve:
    https://eixvqedpyuybfywmdulg.supabase.co
    """
    if not db_url:
        raise ValueError("SUPABASE_DB_URL is empty, cannot derive REST URL")
    
    from urllib.parse import urlparse
    parsed = urlparse(db_url)
    host = parsed.hostname or ""
    username = parsed.username or ""
    
    # Caso 1: URL de pooler (ej: aws-0-us-west-1.pooler.supabase.com)
    # En este caso, el project_ref está en el username (formato: postgres.xxx)
    if "pooler.supabase.com" in host or "pooler.supabase.co" in host:
        if username and username.startswith("postgres."):
            # Extraer project_ref del username: postgres.xxx -> xxx
            project_ref = username.replace("postgres.", "")
            if project_ref:
                return f"https://{project_ref}.supabase.co"
        raise ValueError(
            f"No se pudo extraer project_ref desde username en URL de pooler. "
            f"Username esperado: 'postgres.xxx', recibido: '{username}'. "
            f"URL completa: {db_url[:100]}"
        )
    
    # Caso 2: Conexión directa (ej: db.xxx.supabase.co)
    if host.startswith("db."):
        host = host[3:]  # Remover prefijo "db."
    
    # Verificar que el host termine en .supabase.co (no .com)
    if not host.endswith(".supabase.co"):
        raise ValueError(
            f"Hostname no es válido para URL REST de Supabase: {host}. "
            f"URL completa: {db_url[:100]}"
        )
    
    if not host:
        raise ValueError(f"No se pudo extraer el hostname de SUPABASE_DB_URL: {db_url}")
    
    return f"https://{host}"

def get_supabase_client():
    """Obtiene el cliente de Supabase, inicializándolo si es necesario."""
    if not SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_SERVICE_KEY debe estar configurado en .env")
    
    # Intentar obtener URL REST de Supabase
    SUPABASE_REST_URL_ENV = os.getenv("SUPABASE_REST_URL")
    SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
    SUPABASE_URL_LEGACY = os.getenv("SUPABASE_URL")
    
    if SUPABASE_REST_URL_ENV:
        SUPABASE_REST_URL = SUPABASE_REST_URL_ENV
    elif SUPABASE_DB_URL:
        SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_DB_URL)
    elif SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("https://"):
        SUPABASE_REST_URL = SUPABASE_URL_LEGACY
    elif SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("postgresql://"):
        SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_URL_LEGACY)
    else:
        raise ValueError(
            "No se pudo determinar la URL REST de Supabase. "
            "Configura SUPABASE_REST_URL o SUPABASE_DB_URL en .env"
        )
    
    return create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)


def get_cost_summary_data(from_date: str, to_date: str) -> Dict[str, Any]:
    """
    Obtiene los datos de costos e ingresos para un rango de fechas.
    
    Esta función reutiliza la lógica del endpoint /admin/cost-summary
    pero puede ser llamada directamente sin autenticación.
    
    Args:
        from_date: Fecha de inicio en formato YYYY-MM-DD
        to_date: Fecha de fin en formato YYYY-MM-DD
        
    Returns:
        Diccionario con los datos del resumen de costos
    """
    try:
        # Intentar importar pytz para manejo de timezone
        try:
            import pytz
            utc = pytz.UTC
        except ImportError:
            from datetime import timezone
            utc = timezone.utc
            pytz = None
        
        # Parsear fechas
        date_from = datetime.strptime(from_date, "%Y-%m-%d")
        date_to = datetime.strptime(to_date, "%Y-%m-%d")
        # Ajustar a inicio y fin del día
        date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Convertir a UTC
        if pytz:
            date_from_utc = utc.localize(date_from)
            date_to_utc = utc.localize(date_to)
        else:
            from datetime import timezone
            utc = timezone.utc
            date_from_utc = date_from.replace(tzinfo=utc)
            date_to_utc = date_to.replace(tzinfo=utc)
        
        # Obtener cliente de Supabase
        supabase_client = get_supabase_client()
        
        # Consultar costos de modelos agrupados por día
        usage_response = supabase_client.table("model_usage_events").select(
            "tokens_input, tokens_output, cost_estimated_usd, created_at"
        ).gte("created_at", date_from_utc.isoformat()).lte("created_at", date_to_utc.isoformat()).execute()
        
        # Agrupar costos por día
        daily_costs = {}
        total_tokens_input = 0
        total_tokens_output = 0
        total_cost_usd = 0.0
        
        if usage_response.data:
            for event in usage_response.data:
                created_at = event.get("created_at")
                if created_at:
                    # Extraer fecha (sin hora)
                    event_date = created_at.split("T")[0] if "T" in created_at else created_at.split(" ")[0]
                    
                    if event_date not in daily_costs:
                        daily_costs[event_date] = {
                            "tokens_input": 0,
                            "tokens_output": 0,
                            "cost_estimated_usd": 0.0
                        }
                    
                    daily_costs[event_date]["tokens_input"] += event.get("tokens_input", 0)
                    daily_costs[event_date]["tokens_output"] += event.get("tokens_output", 0)
                    daily_costs[event_date]["cost_estimated_usd"] += float(event.get("cost_estimated_usd", 0))
                    
                    total_tokens_input += event.get("tokens_input", 0)
                    total_tokens_output += event.get("tokens_output", 0)
                    total_cost_usd += float(event.get("cost_estimated_usd", 0))
        
        # Consultar ingresos de Stripe agrupados por día
        payments_response = supabase_client.table("stripe_payments").select(
            "amount_usd, payment_date"
        ).gte("payment_date", date_from_utc.isoformat()).lte("payment_date", date_to_utc.isoformat()).execute()
        
        # Agrupar ingresos por día
        daily_revenue = {}
        total_revenue_usd = 0.0
        
        if payments_response.data:
            for payment in payments_response.data:
                payment_date_str = payment.get("payment_date")
                if payment_date_str:
                    # Extraer fecha (sin hora)
                    payment_date = payment_date_str.split("T")[0] if "T" in payment_date_str else payment_date_str.split(" ")[0]
                    
                    if payment_date not in daily_revenue:
                        daily_revenue[payment_date] = 0.0
                    
                    amount = float(payment.get("amount_usd", 0))
                    daily_revenue[payment_date] += amount
                    total_revenue_usd += amount
        
        # Combinar datos diarios
        daily_summary = []
        current_date = date_from.date()
        end_date = date_to.date()
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            costs = daily_costs.get(date_str, {
                "tokens_input": 0,
                "tokens_output": 0,
                "cost_estimated_usd": 0.0
            })
            
            revenue = daily_revenue.get(date_str, 0.0)
            margin = revenue - costs["cost_estimated_usd"]
            
            daily_summary.append({
                "date": date_str,
                "tokens_input": costs["tokens_input"],
                "tokens_output": costs["tokens_output"],
                "cost_estimated_usd": round(costs["cost_estimated_usd"], 6),
                "revenue_usd": round(revenue, 2),
                "margin_usd": round(margin, 2)
            })
            
            current_date += timedelta(days=1)
        
        # Calcular margen total
        margin_usd = total_revenue_usd - total_cost_usd
        
        return {
            "from": from_date,
            "to": to_date,
            "daily": daily_summary,
            "totals": {
                "tokens_input": total_tokens_input,
                "tokens_output": total_tokens_output,
                "cost_estimated_usd": round(total_cost_usd, 6),
                "revenue_usd": round(total_revenue_usd, 2),
                "margin_usd": round(margin_usd, 2),
                "margin_percent": round((margin_usd / total_revenue_usd * 100) if total_revenue_usd > 0 else 0, 2)
            }
        }
        
    except Exception as e:
        raise Exception(f"Error al obtener resumen de costos: {str(e)}")


def format_cost_report_html(summary_data: Dict[str, Any], period_name: str = "Período") -> str:
    """
    Formatea los datos del resumen de costos en HTML para enviar por email.
    
    Args:
        summary_data: Datos del resumen obtenidos de get_cost_summary_data
        period_name: Nombre del período (ej: "Ayer", "Últimos 7 días")
        
    Returns:
        String HTML formateado
    """
    totals = summary_data["totals"]
    daily = summary_data["daily"]
    
    # Formatear fecha
    from_date = summary_data["from"]
    to_date = summary_data["to"]
    date_range = f"{from_date} a {to_date}"
    if from_date == to_date:
        date_range = from_date
    
    # Construir tabla de días
    daily_rows = ""
    for day in daily:
        cost_color = "#dc2626" if day["cost_estimated_usd"] > 0 else "#666"
        revenue_color = "#16a34a" if day["revenue_usd"] > 0 else "#666"
        margin_color = "#16a34a" if day["margin_usd"] >= 0 else "#dc2626"
        
        daily_rows += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb;">{day['date']}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right; color: {cost_color};">${day['cost_estimated_usd']:.6f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right; color: {revenue_color};">${day['revenue_usd']:.2f}</td>
            <td style="padding: 8px; border-bottom: 1px solid #e5e7eb; text-align: right; color: {margin_color};">${day['margin_usd']:.2f}</td>
        </tr>
        """
    
    # Color del margen total
    margin_color = "#16a34a" if totals["margin_usd"] >= 0 else "#dc2626"
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 24px;">📊 Resumen de Costos e Ingresos</h1>
            <p style="color: white; margin: 10px 0 0 0; opacity: 0.9;">{period_name} - {date_range}</p>
        </div>
        
        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #2563eb; margin-top: 0;">Resumen Total</h2>
            
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0;">
                <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; border-left: 4px solid #2563eb;">
                    <p style="margin: 0; font-size: 12px; color: #666; text-transform: uppercase;">Tokens Input</p>
                    <p style="margin: 5px 0 0 0; font-size: 20px; font-weight: bold; color: #2563eb;">{totals['tokens_input']:,}</p>
                </div>
                <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; border-left: 4px solid #2563eb;">
                    <p style="margin: 0; font-size: 12px; color: #666; text-transform: uppercase;">Tokens Output</p>
                    <p style="margin: 5px 0 0 0; font-size: 20px; font-weight: bold; color: #2563eb;">{totals['tokens_output']:,}</p>
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0;">
                <div style="background: #fef2f2; padding: 15px; border-radius: 8px; border-left: 4px solid #dc2626;">
                    <p style="margin: 0; font-size: 12px; color: #666; text-transform: uppercase;">Costo Total</p>
                    <p style="margin: 5px 0 0 0; font-size: 18px; font-weight: bold; color: #dc2626;">${totals['cost_estimated_usd']:.6f}</p>
                </div>
                <div style="background: #f0fdf4; padding: 15px; border-radius: 8px; border-left: 4px solid #16a34a;">
                    <p style="margin: 0; font-size: 12px; color: #666; text-transform: uppercase;">Ingresos Total</p>
                    <p style="margin: 5px 0 0 0; font-size: 18px; font-weight: bold; color: #16a34a;">${totals['revenue_usd']:.2f}</p>
                </div>
                <div style="background: {'#f0fdf4' if totals['margin_usd'] >= 0 else '#fef2f2'}; padding: 15px; border-radius: 8px; border-left: 4px solid {margin_color};">
                    <p style="margin: 0; font-size: 12px; color: #666; text-transform: uppercase;">Margen Neto</p>
                    <p style="margin: 5px 0 0 0; font-size: 18px; font-weight: bold; color: {margin_color};">
                        ${totals['margin_usd']:.2f}
                        <span style="font-size: 14px; font-weight: normal;">({totals['margin_percent']:.2f}%)</span>
                    </p>
                </div>
            </div>
            
            <h2 style="color: #2563eb; margin-top: 30px;">Desglose Diario</h2>
            
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <thead>
                    <tr style="background: #f3f4f6;">
                        <th style="padding: 12px; text-align: left; border-bottom: 2px solid #d1d5db; font-weight: bold;">Fecha</th>
                        <th style="padding: 12px; text-align: right; border-bottom: 2px solid #d1d5db; font-weight: bold;">Costo (USD)</th>
                        <th style="padding: 12px; text-align: right; border-bottom: 2px solid #d1d5db; font-weight: bold;">Ingresos (USD)</th>
                        <th style="padding: 12px; text-align: right; border-bottom: 2px solid #d1d5db; font-weight: bold;">Margen (USD)</th>
                    </tr>
                </thead>
                <tbody>
                    {daily_rows}
                </tbody>
            </table>
            
            <p style="font-size: 12px; color: #999; margin-top: 30px; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                Reporte generado automáticamente por Codex Trader
            </p>
        </div>
    </body>
    </html>
    """
    
    return html


def send_daily_cost_report(days: int = 1) -> bool:
    """
    Genera y envía un reporte de costos por email al administrador.
    
    Args:
        days: Número de días hacia atrás para el reporte (1 = ayer, 7 = últimos 7 días)
        
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    try:
        from lib.email import send_admin_email
        
        # Calcular fechas
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        from_date_str = start_date.strftime("%Y-%m-%d")
        to_date_str = end_date.strftime("%Y-%m-%d")
        
        # Determinar nombre del período
        if days == 1:
            period_name = "Resumen de Ayer"
        elif days == 7:
            period_name = "Resumen Semanal (Últimos 7 días)"
        else:
            period_name = f"Resumen de los últimos {days} días"
        
        # Obtener datos del resumen
        print(f"Generando reporte de costos para {from_date_str} a {to_date_str}...")
        summary_data = get_cost_summary_data(from_date_str, to_date_str)
        
        # Formatear HTML
        html_content = format_cost_report_html(summary_data, period_name)
        
        # Enviar email
        subject = f"📊 {period_name} - Codex Trader"
        success = send_admin_email(subject, html_content)
        
        if success:
            print(f"✅ Reporte de costos enviado exitosamente: {period_name}")
        else:
            print(f"❌ Error al enviar reporte de costos: {period_name}")
        
        return success
        
    except Exception as e:
        print(f"❌ Error al generar reporte de costos: {str(e)}")
        return False

