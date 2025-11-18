"""
Helper functions para el sistema de referidos de Codex Trader.
Proporciona funciones para generar y asignar códigos de referido.
"""
import os
import random
import string
from typing import Optional
from supabase import Client


def generate_referral_code() -> str:
    """
    Genera un código de referido único.
    Formato: 8-10 caracteres alfanuméricos en mayúsculas.
    Ejemplo: "A7K9Q2LM"
    
    Returns:
        Un código de referido único
    """
    # Generar código de 8-10 caracteres alfanuméricos en mayúsculas
    length = random.randint(8, 10)
    characters = string.ascii_uppercase + string.digits
    # Excluir caracteres que pueden confundirse (0, O, I, 1)
    characters = characters.replace('0', '').replace('O', '').replace('I', '').replace('1', '')
    
    code = ''.join(random.choice(characters) for _ in range(length))
    return code


def assign_referral_code_if_needed(
    supabase_client: Client,
    user_id: str,
    max_attempts: int = 10
) -> Optional[str]:
    """
    Asigna un código de referido a un usuario si no tiene uno.
    
    Args:
        supabase_client: Cliente de Supabase
        user_id: ID del usuario
        max_attempts: Número máximo de intentos para generar un código único
        
    Returns:
        El código de referido asignado o None si falla
    """
    try:
        # Verificar si el usuario ya tiene un código
        profile_response = supabase_client.table("profiles").select(
            "referral_code"
        ).eq("id", user_id).execute()
        
        if profile_response.data and profile_response.data[0].get("referral_code"):
            # Ya tiene código, retornarlo
            existing_code = profile_response.data[0]["referral_code"]
            print(f"[REFERRALS] Usuario {user_id} ya tiene código: {existing_code}")
            return existing_code
        
        # No tiene código, generar uno único
        attempts = 0
        while attempts < max_attempts:
            new_code = generate_referral_code()
            
            # Verificar si el código ya existe
            check_response = supabase_client.table("profiles").select(
                "id"
            ).eq("referral_code", new_code).execute()
            
            if not check_response.data:
                # Código único encontrado, asignarlo
                update_response = supabase_client.table("profiles").update({
                    "referral_code": new_code
                }).eq("id", user_id).execute()
                
                if update_response.data:
                    print(f"[REFERRALS] Código asignado exitosamente: {new_code} para usuario {user_id}")
                    return new_code
                else:
                    print(f"[REFERRALS] Error al actualizar perfil con código {new_code}")
                    attempts += 1
            else:
                # Código ya existe, intentar otro
                attempts += 1
                print(f"[REFERRALS] Código {new_code} ya existe, intentando otro...")
        
        # Si llegamos aquí, no se pudo generar un código único
        print(f"[REFERRALS] ERROR: No se pudo generar código único después de {max_attempts} intentos")
        return None
        
    except Exception as e:
        print(f"[REFERRALS] ERROR al asignar código de referido: {e}")
        import traceback
        traceback.print_exc()
        return None


def build_referral_url(referral_code: Optional[str]) -> str:
    """
    Construye la URL de invitación usando FRONTEND_URL.
    
    Args:
        referral_code: Código de referido (puede ser None)
        
    Returns:
        URL completa de invitación o URL base de registro si no hay código
    """
    base_url = os.getenv("FRONTEND_URL", "http://localhost:3000").strip('"').strip("'").strip()
    base_url = base_url.rstrip('/')  # Normalizar sin barra final
    
    if referral_code and referral_code.strip() and referral_code != "No disponible":
        # Codificar el código para URL
        from urllib.parse import quote
        encoded_code = quote(referral_code)
        # Usar la raíz del sitio (/) ya que el frontend detecta ?ref= en la página principal
        return f"{base_url}/?ref={encoded_code}"
    else:
        # Fallback: solo URL base sin código
        return base_url
