"""
Router para endpoints de debug y diagnóstico.
Solo disponible en desarrollo o para administradores.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from lib.dependencies import get_user, supabase_client
from routers.users import get_tokens

logger = logging.getLogger(__name__)

# Crear router
debug_router = APIRouter(tags=["debug"])

@debug_router.get("/debug/tokens")
async def debug_tokens(user = Depends(get_user)) -> Dict[str, Any]:
    """
    Endpoint de debug para verificar el estado de tokens del usuario.
    Útil para diagnóstico sin necesidad de consola del navegador.
    """
    try:
        user_id = user.id
        user_email = user.email if hasattr(user, 'email') else "N/A"
        
        logger.info(f"🔍 [DEBUG] Verificando tokens para usuario: {user_id}")
        
        # Obtener perfil completo
        try:
            profile_response = supabase_client.table("profiles").select(
                "id, email, tokens_restantes, current_plan, referral_code, created_at"
            ).eq("id", user_id).execute()
            
            if not profile_response.data:
                return {
                    "status": "error",
                    "message": "Perfil no encontrado",
                    "user_id": str(user_id),
                    "user_email": user_email,
                    "tokens_restantes": None
                }
            
            profile = profile_response.data[0]
            
            return {
                "status": "success",
                "user_id": str(user_id),
                "user_email": user_email,
                "tokens_restantes": profile.get("tokens_restantes", 0),
                "current_plan": profile.get("current_plan", "N/A"),
                "referral_code": profile.get("referral_code", "N/A"),
                "created_at": profile.get("created_at", "N/A"),
                "message": f"✅ Tokens obtenidos: {profile.get('tokens_restantes', 0):,}"
            }
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ [DEBUG] Error al obtener perfil: {error_msg}")
            return {
                "status": "error",
                "message": f"Error al obtener perfil: {error_msg}",
                "user_id": str(user_id),
                "user_email": user_email,
                "tokens_restantes": None
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ [DEBUG] Error inesperado: {e}")
        return {
            "status": "error",
            "message": f"Error inesperado: {str(e)}",
            "tokens_restantes": None
        }

