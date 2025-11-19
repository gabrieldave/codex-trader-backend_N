"""
Script para reenviar el email de bienvenida a un usuario específico.
Útil cuando el email no llegó o el usuario necesita recibirlo de nuevo.
"""
import os
import sys
import requests
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Obtener configuración
BACKEND_URL = os.getenv("BACKEND_URL", "https://api.codextrader.tech")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

def reenviar_email_bienvenida(user_email: str):
    """
    Reenvía el email de bienvenida a un usuario específico.
    
    Args:
        user_email: Email del usuario al que se le reenviará el email
    """
    print(f"🔄 Reenviando email de bienvenida a: {user_email}")
    
    # Endpoint del backend
    url = f"{BACKEND_URL}/users/notify-registration"
    
    # Headers con autenticación
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
    }
    
    # Body con force_resend=True para forzar el reenvío
    body = {
        "email": user_email,
        "force_resend": True,
        "triggered_by": "manual_script"
    }
    
    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Email de bienvenida reenviado exitosamente")
            print(f"   Resultado: {result.get('message', 'OK')}")
            return True
        else:
            print(f"❌ Error al reenviar email: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False

def main():
    """Función principal"""
    if len(sys.argv) < 2:
        print("Uso: python reenviar_email_bienvenida.py <email>")
        print("\nEjemplo:")
        print("  python reenviar_email_bienvenida.py usuario@example.com")
        sys.exit(1)
    
    user_email = sys.argv[1].strip()
    
    if not user_email or "@" not in user_email:
        print("❌ Error: Email inválido")
        sys.exit(1)
    
    # Verificar configuración
    if not SUPABASE_SERVICE_KEY:
        print("⚠️  ADVERTENCIA: SUPABASE_SERVICE_KEY no está configurado")
        print("   El script intentará sin autenticación (puede fallar)")
        respuesta = input("   ¿Continuar? (s/n): ")
        if respuesta.lower() != 's':
            sys.exit(0)
    
    # Reenviar email
    success = reenviar_email_bienvenida(user_email)
    
    if success:
        print("\n✅ Proceso completado")
        sys.exit(0)
    else:
        print("\n❌ El proceso falló")
        sys.exit(1)

if __name__ == "__main__":
    main()

