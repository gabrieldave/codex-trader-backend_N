"""
Dependencias compartidas para los routers.
Contiene funciones de autenticación y utilidades comunes.
"""
import os
import logging
import asyncio
from typing import Optional
from fastapi import HTTPException, Header
from supabase import create_client

logger = logging.getLogger(__name__)

# Variables globales que se inicializan en main.py
# Estas se importan desde main después de la inicialización
# IMPORTANTE: Estas variables se inicializan en main.py usando init_dependencies()
supabase_client = None
SUPABASE_REST_URL = None
SUPABASE_SERVICE_KEY = None
SUPABASE_ANON_KEY = None
ADMIN_EMAILS = []


def init_dependencies(
    client,
    rest_url: str,
    service_key: str,
    anon_key: Optional[str] = None,
    admin_emails: list = None
):
    """
    Inicializa las dependencias globales.
    Debe llamarse desde main.py después de configurar Supabase.
    """
    global supabase_client, SUPABASE_REST_URL, SUPABASE_SERVICE_KEY, SUPABASE_ANON_KEY, ADMIN_EMAILS
    supabase_client = client
    SUPABASE_REST_URL = rest_url
    SUPABASE_SERVICE_KEY = service_key
    SUPABASE_ANON_KEY = anon_key or ""
    ADMIN_EMAILS = admin_emails or []


def get_user_supabase_client(token: str):
    """
    Crea un cliente de Supabase usando el token JWT del usuario.
    Esto asegura que las consultas se hagan con el contexto correcto del usuario.
    """
    # Usar SUPABASE_ANON_KEY si está disponible (mejor para RLS)
    # Si no está disponible, usar SERVICE_KEY (las políticas RLS que creamos permiten service_role)
    api_key = SUPABASE_ANON_KEY if SUPABASE_ANON_KEY else SUPABASE_SERVICE_KEY
    
    client = create_client(SUPABASE_REST_URL, api_key)
    
    # Si usamos ANON_KEY, establecer el token del usuario para que RLS funcione
    # Si usamos SERVICE_KEY, las políticas que creamos permiten las consultas
    if SUPABASE_ANON_KEY and hasattr(client, 'postgrest'):
        try:
            # Establecer el token del usuario en postgrest
            client.postgrest.auth(token)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo establecer token en cliente: {e}")
            # Continuar de todas formas, las políticas de service_role deberían funcionar
    
    return client


async def get_user(authorization: Optional[str] = Header(None)):
    """
    Valida el token JWT de Supabase y devuelve el objeto usuario.
    Lanza HTTPException 401 si el token es inválido o no está presente.
    """
    if not authorization:
        logger.warning("⚠️ get_user: No se recibió header Authorization")
        raise HTTPException(
            status_code=401,
            detail="Token de autorización requerido. Incluye 'Authorization: Bearer <token>' en los headers."
        )
    
    # Extraer el token del header "Bearer <token>"
    try:
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            logger.warning("⚠️ get_user: Token vacío después de extraer 'Bearer '")
            raise HTTPException(
                status_code=401,
                detail="Formato de token inválido. Usa 'Bearer <token>'"
            )
    except Exception as e:
        logger.warning(f"⚠️ get_user: Error al extraer token: {e}")
        raise HTTPException(
            status_code=401,
            detail="Formato de token inválido. Usa 'Bearer <token>'"
        )
    
    # Validar el token con Supabase
    try:
        logger.debug(f"🔐 get_user: Validando token (primeros 20 chars: {token[:20]}...)")
        
        # Verificar que el cliente esté inicializado
        if not supabase_client:
            logger.error("❌ get_user: supabase_client no está inicializado")
            raise HTTPException(
                status_code=500,
                detail="Error de configuración del servidor. Contacta al administrador."
            )
        
        # Verificar que la URL esté configurada
        if not SUPABASE_REST_URL:
            logger.error("❌ get_user: SUPABASE_REST_URL no está configurada")
            raise HTTPException(
                status_code=500,
                detail="Error de configuración del servidor. Contacta al administrador."
            )
        
        # Reintentos para errores de DNS/conexión temporales
        max_retries = 3
        retry_delay = 0.5  # segundos
        last_error = None
        
        for attempt in range(max_retries):
            try:
                user_response = supabase_client.auth.get_user(token)
                if not user_response.user:
                    logger.warning("⚠️ get_user: user_response.user es None")
                    raise HTTPException(
                        status_code=401,
                        detail="Token inválido o expirado"
                    )
                logger.debug(f"✅ get_user: Usuario validado: {user_response.user.email}")
                return user_response.user
            except HTTPException:
                raise
            except Exception as e:
                error_msg = str(e)
                last_error = e
                
                # Errores de DNS/conexión que pueden ser temporales
                dns_errors = [
                    "name resolution",
                    "Name or service not known",
                    "getaddrinfo failed",
                    "Temporary failure",
                    "Connection refused",
                    "Network is unreachable",
                    "Failed to resolve",
                    "ETIMEDOUT",
                    "ECONNREFUSED"
                ]
                
                is_dns_error = any(keyword.lower() in error_msg.lower() for keyword in dns_errors)
                
                if is_dns_error and attempt < max_retries - 1:
                    logger.warning(f"⚠️ get_user: Error de DNS/conexión (intento {attempt + 1}/{max_retries}): {error_msg[:80]}")
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Backoff exponencial
                    continue
                else:
                    break
        
        # Si llegamos aquí, todos los reintentos fallaron
        error_msg = str(last_error) if last_error else "Error desconocido"
        
        # Errores comunes que son esperados (token expirado, sesión inválida, etc.)
        expected_errors = [
            "Session from session_id claim in JWT does not exist",
            "Token has expired",
            "Invalid token",
            "JWT expired",
            "Session not found"
        ]
        
        is_expected_error = any(expected in error_msg for expected in expected_errors)
        
        # Errores de conexión/DNS (críticos)
        connection_keywords = [
            "name resolution",
            "Name or service not known",
            "getaddrinfo failed",
            "Connection refused",
            "Network is unreachable",
            "Failed to resolve",
            "Temporary failure",
            "ETIMEDOUT",
            "ECONNREFUSED"
        ]
        is_connection_error = any(keyword.lower() in error_msg.lower() for keyword in connection_keywords)
        
        if is_connection_error:
            logger.error(f"❌ get_user: ERROR DE CONEXIÓN con Supabase después de {max_retries} intentos: {error_msg}")
            logger.error(f"   URL configurada: {SUPABASE_REST_URL[:60] if SUPABASE_REST_URL else 'No configurada'}...")
            logger.error(f"   Esto indica un problema de red/DNS en Railway. El servicio se recuperará automáticamente.")
            raise HTTPException(
                status_code=503,
                detail="Servicio temporalmente no disponible. Intenta de nuevo en unos segundos."
            )
        elif is_expected_error:
            # Log como warning en lugar de error, ya que es un caso esperado
            logger.debug(f"⚠️ get_user: Token inválido o expirado (esperado): {error_msg[:80]}")
        else:
            logger.error(f"❌ get_user: Error al validar token con Supabase: {error_msg}")
            # Log más detallado del error solo si no es un error esperado
            if "Invalid API key" in error_msg or "Invalid URL" in error_msg:
                logger.error(f"❌ Posible problema con configuración de Supabase: URL={SUPABASE_REST_URL[:50] if SUPABASE_REST_URL else 'No configurada'}...")
        
        raise HTTPException(
            status_code=401,
            detail=f"Token inválido o expirado. Por favor, inicia sesión nuevamente."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ get_user: Error inesperado: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error interno del servidor."
        )


def is_admin_user(user) -> bool:
    """
    Verifica si un usuario es administrador.
    
    Args:
        user: Objeto usuario de Supabase
        
    Returns:
        True si el usuario es admin, False en caso contrario
    """
    if not user or not user.email:
        return False
    
    # Verificar si el email está en la lista de admins
    if user.email.lower() in [email.lower() for email in ADMIN_EMAILS]:
        return True
    
    # Verificar en la base de datos si el usuario tiene rol de admin
    try:
        profile = supabase_client.table("profiles").select("is_admin").eq("id", user.id).execute()
        if profile.data and profile.data[0].get("is_admin", False):
            return True
    except Exception as e:
        logger.warning(f"⚠️ Error al verificar is_admin en profiles: {e}")
    
    return False

