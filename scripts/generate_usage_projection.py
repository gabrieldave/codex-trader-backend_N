"""
Genera un reporte operativo de consumo de modelos y proyecciones de margen.

- Reutiliza las métricas guardadas en Supabase (tabla model_usage_events y stripe_payments)
- Calcula costo promedio por token, clasificación fast/deep y desglose por proveedor
- Proyecta ingresos/márgenes semanales para diferentes cantidades de usuarios

Uso:
    python scripts/generate_usage_projection.py --days 7 --users 100 1000
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List

# Agregar el directorio raíz del backend al path para que Python encuentre los módulos
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

# Función helper para limpiar variables de entorno (igual que en main.py)
def get_env(key: str, default: str = "") -> str:
    """Obtiene variable de entorno y limpia comillas."""
    value = os.getenv(key, default)
    if not value:
        return default
    return value.strip('"').strip("'").strip()

# Importar funciones necesarias
from lib.cost_reports import get_cost_summary_data, get_supabase_client
from plans import CODEX_PLANS, CodexPlan

# Cache para el cliente de Supabase
_supabase_client_cache = None

def _fix_malformed_url(url: str) -> str:
    """Intenta corregir URLs mal formateadas (ej: con = en lugar de :)"""
    if not url:
        return url
    # Si la URL tiene "=" en lugares donde debería tener ":", intentar corregir
    if "=" in url and ("postgresql" in url or "postgres" in url):
        # Caso 1: postgresql=//usuario=password@host=puerto
        # Debería ser: postgresql://usuario:password@host:puerto
        if "postgresql=" in url:
            url = url.replace("postgresql=", "postgresql://")
        elif "postgres=" in url:
            url = url.replace("postgres=", "postgres://")
        
        # Corregir doble barra si existe
        url = url.replace(":////", "://")
        
        # Reemplazar "=" antes de "@" (usuario=password@) por ":"
        url = re.sub(r'([^@/])=([^@/]+)@', r'\1:\2@', url)
        # Reemplazar "=" después de "@" y antes de números (host=puerto) por ":"
        url = re.sub(r'@([^:]+)=(\d+)', r'@\1:\2', url)
    return url

def get_supabase_client_cached():
    """Obtiene el cliente de Supabase con caché y mejor manejo de errores."""
    global _supabase_client_cache
    if _supabase_client_cache is None:
        # Intentar usar SUPABASE_REST_URL directamente primero (más confiable)
        supabase_rest_url = get_env("SUPABASE_REST_URL")
        supabase_service_key = get_env("SUPABASE_SERVICE_KEY")
        
        # Depuración
        if supabase_rest_url:
            print(f"[DEBUG] SUPABASE_REST_URL encontrada: {supabase_rest_url[:40]}...")
        else:
            print(f"[DEBUG] SUPABASE_REST_URL no encontrada")
        
        if supabase_rest_url and supabase_rest_url.startswith("https://"):
            # Usar URL REST directamente
            if not supabase_service_key:
                raise ValueError("SUPABASE_SERVICE_KEY debe estar configurada cuando se usa SUPABASE_REST_URL")
            from supabase import create_client
            _supabase_client_cache = create_client(supabase_rest_url, supabase_service_key)
            print(f"[OK] Conectado a Supabase usando SUPABASE_REST_URL directamente")
        else:
            # Intentar corregir SUPABASE_DB_URL si está mal formateada
            db_url = get_env("SUPABASE_DB_URL")
            if db_url and ("=" in db_url and "://" not in db_url.replace("=", "")):
                print("[!] Detectada URL mal formateada, intentando corregir...")
                db_url_fixed = _fix_malformed_url(db_url)
                if db_url_fixed != db_url:
                    os.environ["SUPABASE_DB_URL"] = db_url_fixed
                    print(f"[OK] URL corregida")
            
            # Intentar usar la función de cost_reports (que deriva desde DB_URL)
            try:
                _supabase_client_cache = get_supabase_client()
                # Obtener la URL que se está usando (para depuración)
                try:
                    rest_url = get_env("SUPABASE_REST_URL") or "derivada desde DB_URL"
                    print(f"[OK] Conectado a Supabase (URL: {rest_url[:30]}...)")
                except:
                    print(f"[OK] Conectado a Supabase usando configuracion derivada")
            except Exception as e:
                error_msg = str(e)
                print("\n[ERROR] Error de configuracion de Supabase:")
                print(f"   {error_msg}")
                print("\n[SOLUCIONES]")
                print("   1. Configura SUPABASE_REST_URL directamente (recomendado):")
                print("      set SUPABASE_REST_URL=https://xxx.supabase.co")
                print("   2. O configura SUPABASE_DB_URL con la URL de PostgreSQL")
                print("   3. Asegurate de tener SUPABASE_SERVICE_KEY configurada")
                print("\n[DEBUG] Variables actuales:")
                print(f"   SUPABASE_REST_URL: {'Configurada' if supabase_rest_url else 'No configurada'}")
                db_url_debug = get_env("SUPABASE_DB_URL")
                print(f"   SUPABASE_DB_URL: {'Configurada' if db_url_debug else 'No configurada'}")
                if db_url_debug:
                    # Mostrar solo los primeros y últimos caracteres por seguridad
                    masked = db_url_debug[:20] + "..." + db_url_debug[-20:] if len(db_url_debug) > 40 else db_url_debug
                    print(f"      Valor: {masked}")
                print(f"   SUPABASE_SERVICE_KEY: {'Configurada' if supabase_service_key else 'No configurada'}")
                raise
    return _supabase_client_cache

# Configuración por defecto
DEFAULT_DAYS = 7
DEFAULT_USER_SCENARIOS = [100, 1000]
# Distribución estimada de planes de pago (suma 1.0). Ajusta según datos reales.
DEFAULT_PLAN_DISTRIBUTION = {
    "explorer": 0.55,
    "trader": 0.30,
    "pro": 0.12,
    "institucional": 0.03,
}

FAST_THRESHOLD = 3_000  # tokens totales <= 3k => consulta rápida


@dataclass
class UsageSummary:
    total_tokens_input: int
    total_tokens_output: int
    total_cost_usd: float
    fast_events: int
    deep_events: int
    fast_tokens: int
    deep_tokens: int
    provider_costs: Dict[str, float]
    user_count: int

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_input + self.total_tokens_output

    @property
    def avg_cost_per_token(self) -> float:
        return (self.total_cost_usd / self.total_tokens) if self.total_tokens else 0.0

    @property
    def fast_pct(self) -> float:
        return (self.fast_events / (self.fast_events + self.deep_events)) * 100 if (self.fast_events + self.deep_events) else 0.0


def _normalize_distribution(distribution: Dict[str, float]) -> Dict[str, float]:
    total = sum(distribution.values())
    if total == 0:
        raise ValueError("La distribución de planes no puede sumar 0")
    return {k: v / total for k, v in distribution.items()}


def fetch_usage_events(days: int) -> List[dict]:
    try:
        client = get_supabase_client_cached()
    except Exception as e:
        print(f"[ERROR] Error al conectar con Supabase: {e}")
        print("\n[TIP] Asegurate de tener configuradas las variables de entorno:")
        print("   - SUPABASE_REST_URL o SUPABASE_DB_URL")
        print("   - SUPABASE_SERVICE_KEY")
        raise
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    events: List[dict] = []
    page_size = 1000
    offset = 0

    while True:
        query = (
            client.table("model_usage_events")
            .select("user_id, provider, model, tokens_input, tokens_output, cost_estimated_usd, created_at")
            .gte("created_at", start_date.isoformat())
            .lte("created_at", end_date.isoformat())
            .order("created_at", desc=False)
            .range(offset, offset + page_size - 1)
        )
        response = query.execute()
        batch = response.data or []
        events.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return events


def build_usage_summary(events: Iterable[dict]) -> UsageSummary:
    total_input = 0
    total_output = 0
    total_cost = 0.0
    fast_events = deep_events = 0
    fast_tokens = deep_tokens = 0
    provider_costs: Dict[str, float] = defaultdict(float)
    users = set()

    for event in events:
        tokens_input = event.get("tokens_input") or 0
        tokens_output = event.get("tokens_output") or 0
        tokens_total = tokens_input + tokens_output
        cost = float(event.get("cost_estimated_usd") or 0.0)
        provider = (event.get("provider") or "desconocido").lower()
        user_id = event.get("user_id")

        total_input += tokens_input
        total_output += tokens_output
        total_cost += cost
        provider_costs[provider] += cost
        if user_id:
            users.add(user_id)

        if tokens_total > FAST_THRESHOLD:
            deep_events += 1
            deep_tokens += tokens_total
        else:
            fast_events += 1
            fast_tokens += tokens_total

    return UsageSummary(
        total_tokens_input=total_input,
        total_tokens_output=total_output,
        total_cost_usd=round(total_cost, 6),
        fast_events=fast_events,
        deep_events=deep_events,
        fast_tokens=fast_tokens,
        deep_tokens=deep_tokens,
        provider_costs=dict(provider_costs),
        user_count=len(users),
    )


def project_margins(
    cost_per_token: float,
    plan_distribution: Dict[str, float],
    user_counts: Iterable[int],
) -> List[Dict[str, float]]:
    normalized = _normalize_distribution(plan_distribution)
    plan_lookup: Dict[str, CodexPlan] = {plan.code: plan for plan in CODEX_PLANS}
    projections: List[Dict[str, float]] = []

    for users in user_counts:
        monthly_revenue = 0.0
        monthly_cost = 0.0
        detail = []

        for plan_code, fraction in normalized.items():
            plan = plan_lookup.get(plan_code)
            if not plan:
                continue

            plan_users = math.floor(users * fraction)
            plan_revenue = plan.price_usd * plan_users
            plan_cost = plan.tokens_per_month * cost_per_token * plan_users

            monthly_revenue += plan_revenue
            monthly_cost += plan_cost

            detail.append(
                {
                    "plan": plan.name,
                    "usuarios": plan_users,
                    "ingreso_mensual": round(plan_revenue, 2),
                    "costo_mensual": round(plan_cost, 4),
                    "margen_mensual": round(plan_revenue - plan_cost, 2),
                }
            )

        weekly_revenue = monthly_revenue / 4
        weekly_cost = monthly_cost / 4
        projections.append(
            {
                "usuarios_totales": users,
                "ingreso_semanal": round(weekly_revenue, 2),
                "costo_semanal": round(weekly_cost, 4),
                "margen_semanal": round(weekly_revenue - weekly_cost, 2),
                "detalle": detail,
            }
        )

    return projections


def print_report(summary: UsageSummary, projections: List[Dict[str, float]], cost_summary: dict, days: int):
    print("========== CONSUMO REAL ==========")
    print(f"Días analizados: {days}")
    print(f"Usuarios únicos: {summary.user_count}")
    print(f"Tokens totales: {summary.total_tokens:,}")
    print(f"  - Input: {summary.total_tokens_input:,}")
    print(f"  - Output: {summary.total_tokens_output:,}")
    print(f"Costo total modelos: ${summary.total_cost_usd:.6f}")
    print(f"Costo promedio por token: ${summary.avg_cost_per_token:.10f}")
    total_events = summary.fast_events + summary.deep_events
    print(f"Eventos totales: {total_events} (Fast: {summary.fast_events}, Deep: {summary.deep_events}, {summary.fast_pct:.1f}% fast)")
    print("Costo por proveedor (USD):")
    for provider, cost in summary.provider_costs.items():
        print(f"  - {provider}: ${cost:.6f}")

    print("\n========== INGRESOS / COSTOS (Stripe) ==========")
    totals = cost_summary["totals"]
    print(f"Ingresos USD: ${totals['revenue_usd']:.2f}")
    print(f"Costo USD (tabla): ${totals['cost_estimated_usd']:.6f}")
    print(f"Margen USD: ${totals['margin_usd']:.2f} ({totals['margin_percent']:.2f}%)")

    print("\n========== PROYECCIONES SEMANALES ==========")
    for proj in projections:
        print(f"- {proj['usuarios_totales']} usuarios")
        print(f"  Ingreso semanal: ${proj['ingreso_semanal']:.2f}")
        print(f"  Costo semanal:   ${proj['costo_semanal']:.4f}")
        print(f"  Margen semanal:  ${proj['margen_semanal']:.2f}")
        for detail in proj["detalle"]:
            print(
                f"    · {detail['plan']}: {detail['usuarios']} usuarios | "
                f"+${detail['ingreso_mensual']:.2f}/mes | "
                f"Cost ${detail['costo_mensual']:.4f}/mes | "
                f"Margen ${detail['margen_mensual']:.2f}/mes"
            )
        print("")


def main():
    parser = argparse.ArgumentParser(description="Generar reporte de consumo y proyecciones.")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Número de días a analizar (default: 7)")
    parser.add_argument("--users", type=int, nargs="+", default=DEFAULT_USER_SCENARIOS, help="Cantidad de usuarios para escenarios (default: 100 1000)")
    args = parser.parse_args()

    try:
        print(f"[*] Generando reporte para los ultimos {args.days} dias...")
        events = fetch_usage_events(args.days)
        if not events:
            print(f"[!] No se encontraron eventos de uso en los ultimos {args.days} dias.")
            print("    Esto puede ser normal si el sistema esta recien iniciado.")
            return

        print(f"[OK] Encontrados {len(events)} eventos de uso")
        summary = build_usage_summary(events)
        
        print("[*] Calculando resumen de costos...")
        try:
            cost_summary = get_cost_summary_data(
                (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d"),
            )
        except Exception as e:
            print(f"[!] Error al obtener resumen de costos: {e}")
            print("    Continuando sin datos de ingresos de Stripe...")
            cost_summary = {
                "totals": {
                    "revenue_usd": 0.0,
                    "cost_estimated_usd": summary.total_cost_usd,
                    "margin_usd": -summary.total_cost_usd,
                    "margin_percent": 0.0
                }
            }
        
        print("[*] Generando proyecciones...")
        projections = project_margins(summary.avg_cost_per_token, DEFAULT_PLAN_DISTRIBUTION, args.users)
        print_report(summary, projections, cost_summary, args.days)
        
    except KeyboardInterrupt:
        print("\n[!] Interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

