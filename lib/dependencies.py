"""
Dependencias compartidas para los routers.
Contiene funciones de autenticación y utilidades comunes.
"""
import os
import logging
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
        is_connection_error = any(keyword in error_msg for keyword in [
            "Name or service not known",
            "getaddrinfo failed",
            "Connection refused",
            "Network is unreachable",
            "Failed to resolve"
        ])
        
        if is_connection_error:
            logger.error(f"❌ get_user: ERROR DE CONEXIÓN con Supabase: {error_msg}")
            logger.error(f"   URL configurada: {SUPABASE_REST_URL[:60] if SUPABASE_REST_URL else 'No configurada'}...")
            logger.error(f"   Esto indica un problema de red o configuración. Verifica:")
            logger.error(f"   1. Que SUPABASE_REST_URL esté correctamente configurada en Railway")
            logger.error(f"   2. Que la URL sea accesible desde Railway")
            raise HTTPException(
                status_code=503,
                detail="Servicio temporalmente no disponible. Error de conexión con la base de datos."
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

