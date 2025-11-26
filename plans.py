"""
Definición centralizada de planes de suscripción de Codex Trader.
Este archivo mantiene la misma información que frontend/lib/plans.ts
para garantizar consistencia entre frontend y backend.

NOTA SOBRE CONSUMO DE TOKENS:
- Consulta rápida: ~400 tokens (multiplicador 1.0x)
- Análisis profundo (texto): ~1,800 tokens (multiplicador 1.5x)
- Análisis profundo con imagen: ~7,500 tokens (multiplicador 3.0x)

Los análisis con imágenes (gráficas) consumen aproximadamente 4x más tokens
que los análisis de texto debido al procesamiento adicional con Gemini.
"""

from typing import Literal, Optional
from dataclasses import dataclass

PlanCode = Literal["explorer", "trader", "pro", "institucional"]


@dataclass
class CodexPlan:
    """Plan de suscripción de Codex Trader"""
    code: PlanCode
    name: str
    price_usd: float
    tokens_per_month: int
    approx_deep_analyses: int
    badge: str
    short_description: str
    full_description: str


CODEX_PLANS: list[CodexPlan] = [
    CodexPlan(
        code="explorer",
        name="Explorer",
        price_usd=9.99,
        tokens_per_month=150_000,
        approx_deep_analyses=17,
        badge="Para empezar en serio",
        short_description="17 estudios de mercado completos al mes.",
        full_description=(
            "Accede a hasta 17 análisis profundos al mes. Ideal para traders "
            "que analizan 3–4 oportunidades por semana y quieren validar sus "
            "ideas con contenido profesional. Nota: análisis con imagen consumen ~4x más tokens."
        )
    ),
    CodexPlan(
        code="trader",
        name="Trader",
        price_usd=19.99,
        tokens_per_month=400_000,
        approx_deep_analyses=45,
        badge="Trader activo",
        short_description="45 análisis profundos cada mes.",
        full_description=(
            "Pensado para traders activos que revisan el mercado todos los días. "
            "Hasta 45 consultas profundas al mes para gestionar riesgo, psicología "
            "y setups diarios."
        )
    ),
    CodexPlan(
        code="pro",
        name="Pro",
        price_usd=39.99,
        tokens_per_month=1_000_000,
        approx_deep_analyses=113,
        badge="Para analistas serios",
        short_description="113 consultas detalladas al mes.",
        full_description=(
            "Para analistas serios que hacen backtesting, análisis multi-libro y "
            "creación de sistemas. Aproximadamente 4 análisis profundos al día "
            "durante todo el mes."
        )
    ),
    CodexPlan(
        code="institucional",
        name="Institucional",
        price_usd=99.99,
        tokens_per_month=3_000_000,
        approx_deep_analyses=340,
        badge="Equipos y fondos",
        short_description="Hasta 340 análisis mensuales para equipos.",
        full_description=(
            "Diseñado para equipos, mesas de trading y fondos familiares. "
            "Hasta 340 análisis profundos compartidos entre 3–5 traders."
        )
    )
]


def get_plan_by_code(code: PlanCode) -> Optional[CodexPlan]:
    """
    Obtiene un plan por su código.
    
    Args:
        code: Código del plan a buscar
        
    Returns:
        El plan encontrado o None si no existe
    """
    return next((p for p in CODEX_PLANS if p.code == code), None)


def get_all_plans() -> list[CodexPlan]:
    """
    Obtiene todos los planes disponibles.
    
    Returns:
        Lista con todos los planes
    """
    return CODEX_PLANS.copy()


def is_valid_plan_code(code: str) -> bool:
    """
    Verifica si un código de plan es válido.
    
    Args:
        code: Código a verificar
        
    Returns:
        True si el código es válido, False en caso contrario
    """
    return any(p.code == code for p in CODEX_PLANS)

