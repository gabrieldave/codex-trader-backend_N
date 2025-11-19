"""
🔧 CONFIGURAR DEEPSEEK COMO MODELO PREDETERMINADO
=================================================

Asegura que DeepSeek sea el modelo usado, incluso si OpenAI está disponible.
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
print("🔧 CONFIGURANDO DEEPSEEK")
print("="*80)
print()

# Verificar que DeepSeek esté configurado
deepseek_key = get_env("DEEPSEEK_API_KEY")
chat_model = get_env("CHAT_MODEL")

if not deepseek_key:
    print("❌ DEEPSEEK_API_KEY no está configurada")
    print("   Configúrala en tu archivo .env")
    sys.exit(1)

print(f"✅ DEEPSEEK_API_KEY: Configurada")
print()

# Verificar/corregir CHAT_MODEL
if chat_model:
    # Limpiar el modelo (quitar "deepseek/" si está)
    chat_model_clean = chat_model.replace("deepseek/", "").replace("deepseek-", "deepseek-")
    if "deepseek" not in chat_model_clean.lower():
        chat_model_clean = "deepseek-chat"
    
    if chat_model != chat_model_clean:
        print(f"⚠️  CHAT_MODEL actual: {chat_model}")
        print(f"✅ CHAT_MODEL corregido: {chat_model_clean}")
        print()
        print("💡 Para usar DeepSeek, asegúrate de que en tu .env tengas:")
        print(f"   CHAT_MODEL={chat_model_clean}")
    else:
        print(f"✅ CHAT_MODEL: {chat_model}")
else:
    print("⚠️  CHAT_MODEL no está configurado")
    print("   El sistema usará detección automática")
    print()
    print("💡 Para forzar DeepSeek, agrega a tu .env:")
    print("   CHAT_MODEL=deepseek-chat")

print()
print("="*80)
print("📝 NOTA IMPORTANTE:")
print("="*80)
print()
print("El código en main.py tiene esta lógica:")
print("  - Si CHAT_MODEL=deepseek-chat Y hay OPENAI_API_KEY")
print("    → Puede priorizar OpenAI sobre DeepSeek")
print()
print("Para FORZAR DeepSeek, asegúrate de que:")
print("  1. CHAT_MODEL=deepseek-chat (sin 'deepseek/' al inicio)")
print("  2. O comenta/elimina la lógica que prioriza OpenAI")
print()
print("="*80)
















