"""
Calculadora de Rentabilidad para CODEX TRADER
Calcula costos reales, precios de venta y planes de tokens
"""
import sys

# Configurar encoding para Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ============================================================================
# PRECIOS DE APIs (actualizados a Noviembre 2024)
# ============================================================================

# DeepSeek Chat (el que estás usando)
DEEPSEEK_PRICING = {
    "input_per_1M": 0.14,      # $0.14 por millón de tokens de entrada
    "output_per_1M": 0.28,     # $0.28 por millón de tokens de salida
    "name": "DeepSeek Chat"
}

# OpenAI GPT-3.5-turbo (para comparación)
OPENAI_PRICING = {
    "input_per_1M": 0.50,      # $0.50 por millón de tokens de entrada
    "output_per_1M": 1.50,     # $1.50 por millón de tokens de salida
    "name": "GPT-3.5 Turbo"
}

# OpenAI GPT-4 (para comparación premium)
OPENAI_GPT4_PRICING = {
    "input_per_1M": 10.00,     # $10.00 por millón de tokens de entrada
    "output_per_1M": 30.00,    # $30.00 por millón de tokens de salida
    "name": "GPT-4"
}

# ============================================================================
# FUNCIONES DE CÁLCULO
# ============================================================================

def calcular_costo_real(input_tokens, output_tokens, pricing):
    """Calcula el costo real en USD"""
    costo_input = (input_tokens / 1_000_000) * pricing["input_per_1M"]
    costo_output = (output_tokens / 1_000_000) * pricing["output_per_1M"]
    costo_total = costo_input + costo_output
    return costo_input, costo_output, costo_total

def calcular_precio_venta(costo_real, margen_ganancia=3.0):
    """
    Calcula el precio de venta con margen de ganancia
    margen_ganancia: multiplicador (3.0 = 300% de margen, o 200% de ganancia)
    """
    precio_venta = costo_real * margen_ganancia
    ganancia = precio_venta - costo_real
    porcentaje_ganancia = (ganancia / costo_real) * 100
    return precio_venta, ganancia, porcentaje_ganancia

def calcular_tokens_por_dolar(costo_real_por_consulta, tokens_por_consulta):
    """
    Calcula cuántos tokens puedes dar por cada dólar cobrado
    Si cobras $1, puedes dar: $1 / costo_real = número de consultas que puedes pagar
    Luego: número de consultas * tokens por consulta = tokens totales
    """
    consultas_por_dolar = 1.0 / costo_real_por_consulta
    tokens_por_dolar = consultas_por_dolar * tokens_por_consulta
    return tokens_por_dolar

def sugerir_planes(precio_mensual, costo_real_por_consulta, tokens_por_consulta, margen=3.0, factor_seguridad=0.7):
    """
    Sugiere planes basados en precio mensual
    Calcula cuántos tokens puedes dar considerando el margen de ganancia
    factor_seguridad: factor de seguridad (0.7 = 70% del cálculo teórico para ser conservador)
    """
    # Costo máximo que puedes permitirte con el margen
    costo_maximo = precio_mensual / margen
    
    # Aplicar factor de seguridad (ser más conservador)
    costo_maximo_seguro = costo_maximo * factor_seguridad
    
    # Número de consultas que puedes pagar
    consultas_disponibles = costo_maximo_seguro / costo_real_por_consulta
    
    # Tokens totales que puedes dar
    tokens_disponibles = int(consultas_disponibles * tokens_por_consulta)
    
    return {
        "tokens_mensuales": tokens_disponibles,
        "consultas_rapidas": int(tokens_disponibles / 5000),  # ~5000 tokens por consulta rápida
        "consultas_profundo": int(tokens_disponibles / 9000),  # ~9000 tokens por consulta profundo
        "costo_real_maximo": costo_maximo,
        "costo_real_seguro": costo_maximo_seguro,
        "consultas_disponibles": int(consultas_disponibles)
    }

def crear_planes_sugeridos(costo_real_por_consulta, tokens_por_consulta):
    """Crea planes sugeridos con diferentes precios"""
    planes = []
    
    precios = [10, 25, 50, 100]
    nombres = ["Plan Básico", "Plan Intermedio", "Plan Premium", "Plan Pro"]
    
    for precio, nombre in zip(precios, nombres):
        plan_data = sugerir_planes(precio, costo_real_por_consulta, tokens_por_consulta)
        plan = {
            "nombre": nombre,
            "precio_mensual": precio,
            **plan_data
        }
        planes.append(plan)
    
    return planes

# ============================================================================
# ANÁLISIS DE TUS CONSULTAS REALES
# ============================================================================

print("=" * 80)
print("CALCULADORA DE RENTABILIDAD - CODEX TRADER")
print("=" * 80)
print()

# Datos de tus consultas reales
consulta_rapida = {
    "nombre": "Consulta Rápida",
    "input_tokens": 4566,
    "output_tokens": 300,
    "total_tokens": 4866
}

consulta_profundo = {
    "nombre": "Consulta Estudio Profundo",
    "input_tokens": 6867,
    "output_tokens": 1956,
    "total_tokens": 8823
}

consultas = [consulta_rapida, consulta_profundo]

# ============================================================================
# ANÁLISIS CON DEEPSEEK (tu proveedor actual)
# ============================================================================

print("📊 ANÁLISIS DE COSTOS REALES (DeepSeek Chat)")
print("=" * 80)
print()

for consulta in consultas:
    costo_input, costo_output, costo_total = calcular_costo_real(
        consulta["input_tokens"],
        consulta["output_tokens"],
        DEEPSEEK_PRICING
    )
    
    print(f"🔹 {consulta['nombre']}:")
    print(f"   Input tokens: {consulta['input_tokens']:,}")
    print(f"   Output tokens: {consulta['output_tokens']:,}")
    print(f"   Total tokens: {consulta['total_tokens']:,}")
    print(f"   💰 Costo real: ${costo_total:.6f} USD")
    print(f"      - Input: ${costo_input:.6f}")
    print(f"      - Output: ${costo_output:.6f}")
    print()

# Costo total de las 2 consultas
costo_total_input = (11433 / 1_000_000) * DEEPSEEK_PRICING["input_per_1M"]
costo_total_output = (2256 / 1_000_000) * DEEPSEEK_PRICING["output_per_1M"]
costo_total_2_consultas = costo_total_input + costo_total_output

print(f"📈 RESUMEN DE LAS 2 CONSULTAS:")
print(f"   Total tokens: 13,689")
print(f"   💰 Costo total real: ${costo_total_2_consultas:.6f} USD")
print(f"      - Input (11,433 tokens): ${costo_total_input:.6f}")
print(f"      - Output (2,256 tokens): ${costo_total_output:.6f}")
print()

# ============================================================================
# CÁLCULO DE PRECIOS DE VENTA
# ============================================================================

print("=" * 80)
print("💵 ANÁLISIS DE PRECIOS DE VENTA")
print("=" * 80)
print()

# Promedio de tokens por consulta (mezcla 50/50 rápido/profundo)
promedio_tokens_por_consulta = (consulta_rapida["total_tokens"] + consulta_profundo["total_tokens"]) / 2
costo_promedio_por_consulta = calcular_costo_real(
    (consulta_rapida["input_tokens"] + consulta_profundo["input_tokens"]) / 2,
    (consulta_rapida["output_tokens"] + consulta_profundo["output_tokens"]) / 2,
    DEEPSEEK_PRICING
)[2]

print(f"📊 Promedio por consulta:")
print(f"   Tokens promedio: {promedio_tokens_por_consulta:,.0f}")
print(f"   Costo promedio: ${costo_promedio_por_consulta:.6f} USD")
print()

# Diferentes márgenes de ganancia
margenes = [2.0, 2.5, 3.0, 4.0, 5.0]

print("💡 Precios de venta sugeridos (por consulta):")
print()
for margen in margenes:
    precio, ganancia, porcentaje = calcular_precio_venta(costo_promedio_por_consulta, margen)
    print(f"   Margen {margen}x ({porcentaje:.0f}% ganancia):")
    print(f"      Precio de venta: ${precio:.4f} USD")
    print(f"      Ganancia: ${ganancia:.6f} USD")
    print()

# ============================================================================
# SISTEMA DE TOKENS INTERNO
# ============================================================================

print("=" * 80)
print("🎯 SISTEMA DE TOKENS INTERNO")
print("=" * 80)
print()

# Usando margen 3x como referencia
margen_recomendado = 3.0
precio_por_consulta, _, _ = calcular_precio_venta(costo_promedio_por_consulta, margen_recomendado)
tokens_por_dolar = calcular_tokens_por_dolar(costo_promedio_por_consulta, promedio_tokens_por_consulta)

print(f"💰 Con margen {margen_recomendado}x:")
print(f"   Precio por consulta: ${precio_por_consulta:.4f} USD")
print(f"   Tokens por dólar: {tokens_por_dolar:,.0f} tokens/$")
print()
print("📦 Esto significa que por cada dólar que cobres, puedes dar aproximadamente")
print(f"   {tokens_por_dolar:,.0f} tokens a tus usuarios.")
print()

# ============================================================================
# PLANES SUGERIDOS
# ============================================================================

print("=" * 80)
print("📋 PLANES SUGERIDOS PARA USUARIOS")
print("=" * 80)
print()

planes = crear_planes_sugeridos(costo_promedio_por_consulta, promedio_tokens_por_consulta)

for plan in planes:
    costo_real = plan['costo_real_maximo']
    costo_seguro = plan['costo_real_seguro']
    ganancia = plan['precio_mensual'] - costo_real
    ganancia_segura = plan['precio_mensual'] - costo_seguro
    print(f"🔹 {plan['nombre']}: ${plan['precio_mensual']}/mes")
    print(f"   Tokens mensuales: {plan['tokens_mensuales']:,}")
    print(f"   Consultas estimadas (modo rápido): ~{plan['consultas_rapidas']}")
    print(f"   Consultas estimadas (modo profundo): ~{plan['consultas_profundo']}")
    print(f"   Consultas estimadas (mezcla 50/50): ~{(plan['consultas_rapidas'] + plan['consultas_profundo']) // 2}")
    print(f"   💰 Tu costo real (conservador): ${costo_seguro:.2f} USD")
    print(f"   💰 Tu costo real máximo: ${costo_real:.2f} USD")
    print(f"   💵 Tu ganancia (conservadora): ${ganancia_segura:.2f} USD ({ganancia_segura/plan['precio_mensual']*100:.1f}%)")
    print()

# ============================================================================
# TOKENS INICIALES PARA NUEVOS USUARIOS
# ============================================================================

print("=" * 80)
print("🎁 TOKENS INICIALES PARA NUEVOS USUARIOS")
print("=" * 80)
print()

# Opciones de tokens iniciales
opciones_tokens_iniciales = [
    {"nombre": "Prueba gratuita pequeña", "tokens": 5_000, "consultas_rapidas": 1, "consultas_profundo": 0},
    {"nombre": "Prueba gratuita mediana", "tokens": 10_000, "consultas_rapidas": 2, "consultas_profundo": 1},
    {"nombre": "Prueba gratuita generosa", "tokens": 20_000, "consultas_rapidas": 4, "consultas_profundo": 2},
    {"nombre": "Bienvenida estándar", "tokens": 15_000, "consultas_rapidas": 3, "consultas_profundo": 1},
]

for opcion in opciones_tokens_iniciales:
    costo = calcular_costo_real(
        opcion["tokens"] * 0.7,  # Estimado: 70% input, 30% output
        opcion["tokens"] * 0.3,
        DEEPSEEK_PRICING
    )[2]
    print(f"🔹 {opcion['nombre']}: {opcion['tokens']:,} tokens")
    print(f"   Costo para ti: ${costo:.4f} USD")
    print(f"   Permite: ~{opcion['consultas_rapidas']} consultas rápidas o ~{opcion['consultas_profundo']} consultas profundas")
    print()

# ============================================================================
# COMPARACIÓN CON OTROS PROVEEDORES
# ============================================================================

print("=" * 80)
print("⚖️ COMPARACIÓN CON OTROS PROVEEDORES")
print("=" * 80)
print()

proveedores = [DEEPSEEK_PRICING, OPENAI_PRICING, OPENAI_GPT4_PRICING]

for consulta in consultas:
    print(f"📊 {consulta['nombre']}:")
    for provider in proveedores:
        costo_input, costo_output, costo_total = calcular_costo_real(
            consulta["input_tokens"],
            consulta["output_tokens"],
            provider
        )
        print(f"   {provider['name']}: ${costo_total:.6f} USD")
    print()

# ============================================================================
# RECOMENDACIONES FINALES
# ============================================================================

print("=" * 80)
print("✅ RECOMENDACIONES FINALES")
print("=" * 80)
print()

print("1. 💰 COSTO REAL POR CONSULTA:")
print(f"   - Rápida: ${calcular_costo_real(consulta_rapida['input_tokens'], consulta_rapida['output_tokens'], DEEPSEEK_PRICING)[2]:.6f} USD")
print(f"   - Profundo: ${calcular_costo_real(consulta_profundo['input_tokens'], consulta_profundo['output_tokens'], DEEPSEEK_PRICING)[2]:.6f} USD")
print()

print("2. 💵 PRECIO DE VENTA RECOMENDADO (margen 3x):")
print(f"   - Por consulta: ${precio_por_consulta:.4f} USD")
print(f"   - O usar sistema de tokens: {tokens_por_dolar:,.0f} tokens por dólar")
print()

print("3. 🎁 TOKENS INICIALES RECOMENDADOS:")
print("   - Prueba gratuita: 10,000 - 15,000 tokens")
print("   - Permite probar el servicio sin costo alto para ti")
print()

print("4. 📦 PLANES RECOMENDADOS (con margen 3x):")
for plan in planes:
    print(f"   - {plan['nombre']} (${plan['precio_mensual']}/mes): {plan['tokens_mensuales']:,} tokens")
print()

print("5. ⚠️ IMPORTANTE:")
print("   - Los precios de DeepSeek pueden cambiar")
print("   - Monitorea tus costos reales regularmente")
print("   - Ajusta los planes según el uso real de tus usuarios")
print("   - Considera un margen de seguridad del 20-30% adicional")
print()

print("=" * 80)

