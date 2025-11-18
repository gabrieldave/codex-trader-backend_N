"""
🔍 VERIFICAR CONFIGURACIÓN DE DEEPSEEK
======================================

Verifica que DeepSeek esté configurado correctamente.
"""

import os
import sys
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def get_env(key):
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

print("="*80)
print("🔍 VERIFICACIÓN DE CONFIGURACIÓN DEEPSEEK")
print("="*80)
print()

# Verificar API keys
deepseek_key = get_env("DEEPSEEK_API_KEY")
openai_key = get_env("OPENAI_API_KEY")
chat_model = get_env("CHAT_MODEL")

print("📋 Variables de Entorno:")
print()

if deepseek_key:
    preview = deepseek_key[:10] + "..." if len(deepseek_key) > 10 else deepseek_key
    print(f"✅ DEEPSEEK_API_KEY: Configurada ({preview})")
else:
    print("❌ DEEPSEEK_API_KEY: NO configurada")

if openai_key:
    preview = openai_key[:10] + "..." if len(openai_key) > 10 else openai_key
    print(f"✅ OPENAI_API_KEY: Configurada ({preview})")
else:
    print("⚠️  OPENAI_API_KEY: NO configurada")

if chat_model:
    print(f"✅ CHAT_MODEL: {chat_model}")
else:
    print("⚠️  CHAT_MODEL: No configurado (usará detección automática)")

print()
print("="*80)
print("🔧 CONFIGURACIÓN QUE SE USARÁ:")
print("="*80)
print()

# Simular la lógica de main.py
if chat_model:
    if "deepseek" in chat_model.lower() and openai_key:
        print("⚠️  CHAT_MODEL está configurado como DeepSeek, pero OPENAI_API_KEY está disponible")
        print("   El sistema puede priorizar OpenAI")
        modelo_final = "gpt-3.5-turbo"
    else:
        modelo_final = chat_model
        print(f"✅ Usando modelo configurado: {modelo_final}")
else:
    if openai_key:
        modelo_final = "gpt-3.5-turbo"
        print(f"✅ Usando OpenAI/ChatGPT: {modelo_final} (OPENAI_API_KEY disponible)")
    elif deepseek_key:
        modelo_final = "deepseek-chat"
        print(f"✅ Usando DeepSeek: {modelo_final} (DEEPSEEK_API_KEY disponible)")
    else:
        modelo_final = "gpt-3.5-turbo"
        print(f"⚠️  Usando fallback: {modelo_final} (no hay API keys configuradas)")

print()
print("="*80)
print("💡 RECOMENDACIONES:")
print("="*80)
print()

if not deepseek_key and not openai_key:
    print("❌ No hay API keys configuradas")
    print("   Configura DEEPSEEK_API_KEY o OPENAI_API_KEY en tu archivo .env")
elif deepseek_key and modelo_final != "deepseek-chat":
    print("⚠️  Para usar DeepSeek, configura:")
    print("   CHAT_MODEL=deepseek-chat")
    print("   en tu archivo .env")
elif modelo_final == "deepseek-chat":
    print("✅ DeepSeek está configurado correctamente")
    print("   El backend usará DeepSeek cuando se inicie")
else:
    print(f"ℹ️  El sistema usará {modelo_final}")
    print("   Si quieres usar DeepSeek, configura CHAT_MODEL=deepseek-chat")

print()
print("="*80)











