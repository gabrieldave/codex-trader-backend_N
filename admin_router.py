"""
Router de administración para endpoints protegidos de admin.
Proporciona métricas y estadísticas del sistema.
"""
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from supabase import create_client
import os
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def get_env(key):
    """Obtiene variable de entorno y limpia comillas."""
    value = os.getenv(key, "")
    if not value:
        return ""
    return value.strip('"').strip("'").strip()

def _derive_rest_url_from_db(db_url: str) -> str:
    """
    Deriva la URL REST de Supabase desde una URL de conexión a la base de datos.
    """
    if not db_url:
        raise ValueError("SUPABASE_DB_URL is empty, cannot derive REST URL")
    
    if not db_url.startswith(("postgresql://", "postgres://")):
        raise ValueError(f"SUPABASE_DB_URL debe empezar con 'postgresql://' o 'postgres://'. Recibido: {db_url[:50]}...")
    
    try:
        parsed = urlparse(db_url)
    except Exception as e:
        raise ValueError(f"Error al parsear SUPABASE_DB_URL: {e}. URL recibida: {db_url[:100]}")
    
    host = parsed.hostname or ""
    username = parsed.username or ""
    
    # Caso 1: URL de pooler (ej: aws-0-us-west-1.pooler.supabase.com)
    if "pooler.supabase.com" in host or "pooler.supabase.co" in host:
        if username and username.startswith("postgres."):
            project_ref = username.replace("postgres.", "")
            if project_ref:
                return f"https://{project_ref}.supabase.co"
        raise ValueError(f"No se pudo extraer project_ref desde username en URL de pooler.")
    
    # Caso 2: Conexión directa (ej: db.xxx.supabase.co)
    if "db." in host and ".supabase.co" in host:
        project_ref = host.replace("db.", "").replace(".supabase.co", "")
        if project_ref:
            return f"https://{project_ref}.supabase.co"
    
    # Si no coincide con ningún patrón, intentar usar el host directamente
    if ".supabase.co" in host:
        return f"https://{host}"
    
    raise ValueError(f"No se pudo derivar URL REST desde: {db_url[:100]}")

# Obtener variables de entorno usando la misma lógica que main.py
SUPABASE_REST_URL_ENV = get_env("SUPABASE_REST_URL")
SUPABASE_URL_LEGACY = get_env("SUPABASE_URL")
SUPABASE_DB_URL = get_env("SUPABASE_DB_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY")

# Intentar obtener URL REST de Supabase (misma lógica que main.py)
SUPABASE_REST_URL = None

if SUPABASE_REST_URL_ENV:
    SUPABASE_REST_URL = SUPABASE_REST_URL_ENV
elif SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("https://"):
    SUPABASE_REST_URL = SUPABASE_URL_LEGACY
elif SUPABASE_DB_URL:
    try:
        SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_DB_URL)
    except Exception as e:
        logger.error(f"❌ Error al derivar URL REST desde SUPABASE_DB_URL: {e}")
        if SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("postgresql://"):
            try:
                SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_URL_LEGACY)
            except Exception as e2:
                logger.error(f"❌ Error al derivar URL REST desde SUPABASE_URL: {e2}")
elif SUPABASE_URL_LEGACY and SUPABASE_URL_LEGACY.startswith("postgresql://"):
    try:
        SUPABASE_REST_URL = _derive_rest_url_from_db(SUPABASE_URL_LEGACY)
    except Exception as e:
        logger.error(f"❌ Error al derivar URL REST desde SUPABASE_URL: {e}")

# Inicializar cliente de Supabase con service key (para bypass de RLS)
supabase_admin_client = None
if SUPABASE_REST_URL and SUPABASE_SERVICE_KEY:
    try:
        supabase_admin_client = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        logger.info("✅ Cliente de Supabase admin inicializado")
    except Exception as e:
        logger.error(f"❌ Error al inicializar cliente de Supabase admin: {e}")
else:
    if not SUPABASE_REST_URL:
        logger.warning("⚠️ SUPABASE_REST_URL no configurada. Endpoints de admin no funcionarán.")
    if not SUPABASE_SERVICE_KEY:
        logger.warning("⚠️ SUPABASE_SERVICE_KEY no configurada. Endpoints de admin no funcionarán.")

# Crear router
admin_router = APIRouter(prefix="/admin", tags=["admin"])


async def get_admin_user(authorization: Optional[str] = Header(None)):
    """
    Valida que el usuario sea administrador.
    Por ahora, verifica que el token sea válido y que el usuario tenga un campo is_admin.
    En producción, deberías implementar una lógica más robusta de verificación de admin.
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Token de autorización requerido"
        )
    
    try:
        # Extraer token del header
        if authorization.startswith("Bearer "):
            token = authorization.replace("Bearer ", "").strip()
        else:
            token = authorization.strip()
        
        if not token:
            raise HTTPException(
                status_code=401,
                detail="Token vacío"
            )
        
        # Validar token con Supabase
        # Crear cliente temporal para validar token
        if not SUPABASE_REST_URL:
            raise HTTPException(
                status_code=500,
                detail="SUPABASE_REST_URL no configurada. Configura SUPABASE_REST_URL, SUPABASE_URL o SUPABASE_DB_URL en las variables de entorno."
            )
        
        if not SUPABASE_SERVICE_KEY:
            raise HTTPException(
                status_code=500,
                detail="SUPABASE_SERVICE_KEY no configurada"
            )
        
        # Usar el cliente admin para validar el token del usuario
        temp_client = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        user_response = temp_client.auth.get_user(token)
        
        if not user_response.user:
            raise HTTPException(
                status_code=401,
                detail="Token inválido"
            )
        
        user_id = user_response.user.id
        
        # Verificar si el usuario es admin
        # Por ahora, verificamos si existe un campo is_admin en profiles
        # O puedes usar una lista de emails de admin en variables de entorno
        admin_emails = os.getenv("ADMIN_EMAILS", "").strip('"').strip("'").strip()
        if admin_emails:
            admin_list = [email.strip() for email in admin_emails.split(",")]
            if user_response.user.email in admin_list:
                return user_response.user
        
        # Alternativa: verificar campo is_admin en profiles
        try:
            if not SUPABASE_REST_URL:
                raise ValueError("SUPABASE_REST_URL no configurada")
            temp_client = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
            profile_response = temp_client.table("profiles").select("is_admin").eq("id", user_id).execute()
            if profile_response.data and profile_response.data[0].get("is_admin", False):
                return user_response.user
        except:
            pass
        
        # Si no es admin, rechazar
        raise HTTPException(
            status_code=403,
            detail="Acceso denegado: se requieren permisos de administrador"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al validar admin: {error_msg}")
        raise HTTPException(
            status_code=401,
            detail=f"Error al validar token de admin: {error_msg[:100]}"
        )


@admin_router.get("/metrics")
async def get_system_metrics(admin_user = Depends(get_admin_user)):
    """
    Obtiene métricas de uso total del sistema.
    
    Retorna:
    - Total de eventos de Estudio Profundo (deep)
    - Total de eventos de Consulta Rápida (fast)
    - Total de tokens gastados
    - Total de costos estimados
    """
    if not supabase_admin_client:
        raise HTTPException(
            status_code=500,
            detail="Cliente de administración no disponible"
        )
    
    try:
        # Obtener todos los eventos de uso de modelos
        usage_response = supabase_admin_client.table("model_usage_events").select("*").execute()
        
        if not usage_response.data:
            return {
                "total_deep_events": 0,
                "total_fast_events": 0,
                "total_tokens": 0,
                "total_tokens_input": 0,
                "total_tokens_output": 0,
                "total_cost_usd": 0.0,
                "total_events": 0
            }
        
        events = usage_response.data
        
        # Clasificar eventos como "deep" o "fast" basándose en tokens totales
        # Estudio Profundo generalmente usa más tokens (>3000 tokens totales)
        # Consulta Rápida usa menos tokens (<=3000 tokens totales)
        deep_events = []
        fast_events = []
        total_tokens = 0
        total_tokens_input = 0
        total_tokens_output = 0
        total_cost = 0.0
        
        for event in events:
            tokens_input = event.get("tokens_input", 0) or 0
            tokens_output = event.get("tokens_output", 0) or 0
            tokens_total = tokens_input + tokens_output
            cost = float(event.get("cost_estimated_usd", 0) or 0)
            
            total_tokens += tokens_total
            total_tokens_input += tokens_input
            total_tokens_output += tokens_output
            total_cost += cost
            
            # Clasificar: si usa más de 3000 tokens, es probablemente "deep"
            if tokens_total > 3000:
                deep_events.append(event)
            else:
                fast_events.append(event)
        
        # Obtener total de usuarios únicos
        try:
            users_response = supabase_admin_client.table("profiles").select("id", count="exact").execute()
            total_users = users_response.count if hasattr(users_response, 'count') else len(users_response.data) if users_response.data else 0
        except Exception as e:
            logger.warning(f"⚠️ Error al obtener total de usuarios: {e}")
            total_users = 0
        
        return {
            "total_deep_events": len(deep_events),
            "total_fast_events": len(fast_events),
            "total_tokens": total_tokens,
            "total_tokens_input": total_tokens_input,
            "total_tokens_output": total_tokens_output,
            "total_cost_usd": round(total_cost, 6),
            "total_events": len(events),
            "deep_events_percentage": round((len(deep_events) / len(events) * 100) if events else 0, 2),
            "fast_events_percentage": round((len(fast_events) / len(events) * 100) if events else 0, 2),
            "total_users": total_users
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al obtener métricas: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener métricas: {error_msg[:200]}"
        )


@admin_router.get("/top-fast-users")
async def get_top_fast_users(admin_user = Depends(get_admin_user), limit: int = 10):
    """
    Obtiene los usuarios con mayor cantidad de eventos de tipo "fast" (Consultas Rápidas).
    Útil para detectar abuso del plan "Ilimitado" antes de que se convierta en costo real.
    """
    if not supabase_admin_client:
        raise HTTPException(
            status_code=500,
            detail="Cliente de administración no disponible"
        )
    
    try:
        # Obtener todos los eventos de uso de modelos
        usage_response = supabase_admin_client.table("model_usage_events").select("*").execute()
        
        if not usage_response.data:
            return {"users": []}
        
        events = usage_response.data
        
        # Contar fast_events por usuario
        user_fast_counts: dict[str, int] = {}
        user_ids = set()
        
        for event in events:
            tokens_input = event.get("tokens_input", 0) or 0
            tokens_output = event.get("tokens_output", 0) or 0
            tokens_total = tokens_input + tokens_output
            
            # Clasificar como "fast" si usa <= 3000 tokens
            if tokens_total <= 3000:
                user_id = event.get("user_id")
                if user_id:
                    user_ids.add(user_id)
                    user_fast_counts[user_id] = user_fast_counts.get(user_id, 0) + 1
        
        # Obtener emails de los usuarios
        user_emails: dict[str, str] = {}
        if user_ids:
            try:
                # Obtener emails desde auth.users o profiles
                profiles_response = supabase_admin_client.table("profiles").select("id, email").in_("id", list(user_ids)).execute()
                if profiles_response.data:
                    for profile in profiles_response.data:
                        user_emails[profile.get("id")] = profile.get("email", "Usuario desconocido")
            except Exception as e:
                logger.warning(f"⚠️ Error al obtener emails de usuarios: {e}")
        
        # Crear lista de usuarios ordenada por cantidad de fast_events
        top_users = [
            {
                "user_id": user_id,
                "email": user_emails.get(user_id, f"Usuario {user_id[:8]}..."),
                "fast_events_count": count
            }
            for user_id, count in user_fast_counts.items()
        ]
        
        # Ordenar por cantidad descendente y limitar
        top_users.sort(key=lambda x: x["fast_events_count"], reverse=True)
        top_users = top_users[:limit]
        
        return {"users": top_users}
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al obtener usuarios top: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener usuarios top: {error_msg[:200]}"
        )


@admin_router.delete("/users/{user_id}")
async def delete_user(user_id: str, admin_user = Depends(get_admin_user)):
    """
    Elimina un usuario del sistema completamente.
    
    Esto eliminará:
    - El usuario de auth.users
    - Su perfil de profiles (automáticamente por CASCADE)
    - Todos los datos relacionados
    
    ⚠️ ADVERTENCIA: Esta acción es irreversible.
    """
    if not supabase_admin_client:
        raise HTTPException(
            status_code=500,
            detail="Cliente de administración no disponible"
        )
    
    try:
        # Verificar que el usuario existe primero
        try:
            profile_response = supabase_admin_client.table("profiles").select("id, email").eq("id", user_id).execute()
            if not profile_response.data:
                raise HTTPException(
                    status_code=404,
                    detail=f"Usuario con ID {user_id} no encontrado"
                )
            user_email = profile_response.data[0].get("email", "N/A")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"⚠️ Error al verificar usuario: {e}")
        
        # Eliminar usuario usando función RPC de Supabase
        # Primero intentar usar la función SQL delete_user_by_id
        try:
            delete_response = supabase_admin_client.rpc('delete_user_by_id', {'user_id_to_delete': user_id}).execute()
            
            logger.info(f"✅ Usuario {user_id} ({user_email}) eliminado exitosamente")
            return {
                "success": True,
                "message": f"Usuario {user_email} eliminado exitosamente",
                "user_id": user_id,
                "user_email": user_email
            }
        except Exception as rpc_error:
            error_str = str(rpc_error).lower()
            
            # Si la función RPC no existe, intentar usar la API REST de Supabase Admin
            if "function" in error_str and "does not exist" in error_str:
                logger.warning(f"⚠️ Función delete_user_by_id no existe. Ejecuta delete_user_function.sql en Supabase.")
                
                # Método alternativo: Usar API REST de Supabase Admin para eliminar usuario
                # Necesitamos hacer una petición HTTP directa
                try:
                    import requests
                    
                    # Construir URL de Admin API de Supabase
                    admin_api_url = f"{SUPABASE_REST_URL}/auth/v1/admin/users/{user_id}"
                    headers = {
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Content-Type": "application/json"
                    }
                    
                    # Eliminar usuario usando Admin API
                    response = requests.delete(admin_api_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200 or response.status_code == 204:
                        logger.info(f"✅ Usuario {user_id} ({user_email}) eliminado exitosamente vía Admin API")
                        return {
                            "success": True,
                            "message": f"Usuario {user_email} eliminado exitosamente",
                            "user_id": user_id,
                            "user_email": user_email
                        }
                    elif response.status_code == 404:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Usuario con ID {user_id} no encontrado en auth.users"
                        )
                    else:
                        error_detail = response.text[:200] if response.text else "Error desconocido"
                        raise HTTPException(
                            status_code=response.status_code,
                            detail=f"Error al eliminar usuario: {error_detail}"
                        )
                except ImportError:
                    logger.error("❌ requests no está instalado. Instala con: pip install requests")
                    raise HTTPException(
                        status_code=500,
                        detail="Librería 'requests' no disponible. Instala con: pip install requests"
                    )
                except Exception as api_error:
                    logger.error(f"❌ Error al usar Admin API: {api_error}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error al eliminar usuario usando Admin API: {str(api_error)[:200]}"
                    )
            else:
                # Otro tipo de error en RPC
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al eliminar usuario: {str(rpc_error)[:200]}"
                )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al eliminar usuario: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al eliminar usuario: {error_msg[:200]}"
        )


@admin_router.post("/users/{user_id}/deactivate")
async def deactivate_user(user_id: str, admin_user = Depends(get_admin_user)):
    """
    Desactiva un usuario sin eliminarlo completamente.
    
    Esto marca al usuario como inactivo, pero mantiene sus datos.
    Útil si quieres desactivar temporalmente el acceso.
    """
    if not supabase_admin_client:
        raise HTTPException(
            status_code=500,
            detail="Cliente de administración no disponible"
        )
    
    try:
        # Verificar que el usuario existe
        profile_response = supabase_admin_client.table("profiles").select("id, email").eq("id", user_id).execute()
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Usuario con ID {user_id} no encontrado"
            )
        
        user_email = profile_response.data[0].get("email", "N/A")
        
        # Intentar actualizar el usuario en auth.users para desactivarlo
        # Nota: Supabase Python client no tiene método directo para esto
        # Necesitamos usar la API REST de Supabase Admin
        
        # Por ahora, podemos agregar un campo "is_active" en profiles si no existe
        # O usar el campo "banned_until" de auth.users si está disponible
        
        # Método alternativo: Eliminar tokens o cambiar email para bloquear acceso
        # Por ahora, vamos a establecer tokens a 0 y agregar un campo de desactivación
        
        update_response = supabase_admin_client.table("profiles").update({
            "tokens_restantes": 0,
            # Si tienes un campo is_active, desactivarlo aquí
        }).eq("id", user_id).execute()
        
        if update_response.data:
            logger.info(f"✅ Usuario {user_id} ({user_email}) desactivado exitosamente")
            return {
                "success": True,
                "message": f"Usuario {user_email} desactivado exitosamente (tokens establecidos a 0)",
                "user_id": user_id,
                "user_email": user_email
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="No se pudo desactivar el usuario"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al desactivar usuario: {error_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al desactivar usuario: {error_msg[:200]}"
        )

