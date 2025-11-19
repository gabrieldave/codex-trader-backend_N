"""
Router para endpoints de usuarios, tokens, uso y referidos.
"""
import os
import logging
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from datetime import datetime

from lib.dependencies import get_user
from lib.dependencies import supabase_client
from lib.config_shared import FRONTEND_URL
from routers.models import TokenReloadInput, NotifyRegistrationInput, ProcessReferralInput

logger = logging.getLogger(__name__)

# Crear router
users_router = APIRouter(tags=["users"])


@users_router.get("/tokens")
async def get_tokens(user = Depends(get_user)):
    """
    Endpoint para consultar los tokens restantes del usuario autenticado.
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Obteniendo tokens para usuario: {user_id}")
        
        # Usar el cliente global con SERVICE_KEY (las políticas RLS permiten service_role)
        try:
            profile_response = supabase_client.table("profiles").select("tokens_restantes, email").eq("id", user_id).execute()
        except Exception as db_error:
            error_msg = str(db_error)
            logger.error(f"❌ Error al consultar tabla 'profiles': {error_msg}")
            # Si la tabla no existe, retornar valores por defecto
            if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                logger.warning("⚠️ La tabla 'profiles' no existe. Retornando valores por defecto.")
                return {
                    "tokens_restantes": 0,
                    "email": user.email if hasattr(user, 'email') else ""
                }
            raise
        
        if not profile_response.data:
            logger.warning(f"⚠️ Perfil no encontrado para usuario: {user_id}")
            # En lugar de lanzar error 404, retornar valores por defecto
            # Esto permite que el frontend funcione aunque el perfil no exista aún
            logger.info(f"ℹ️ Retornando valores por defecto para usuario: {user_id}")
            return {
                "tokens_restantes": 0,
                "email": user.email if hasattr(user, 'email') else ""
            }
        
        tokens_restantes = profile_response.data[0].get("tokens_restantes", 0)
        email = profile_response.data[0].get("email", user.email if hasattr(user, 'email') else "")
        logger.info(f"✅ Tokens obtenidos: {tokens_restantes} para {email}")
        
        return {
            "tokens_restantes": tokens_restantes,
            "email": email
        }
    except HTTPException as http_ex:
        # Si es un error de autenticación (401), re-lanzarlo
        if http_ex.status_code == 401:
            raise
        # Para otros errores HTTP, retornar valores por defecto
        logger.warning(f"⚠️ Error HTTP {http_ex.status_code} en /tokens: {http_ex.detail}")
        return {
            "tokens_restantes": 0,
            "email": ""
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error en /tokens: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        
        # En lugar de lanzar error 500, retornar valores por defecto
        # Esto permite que el frontend funcione aunque haya problemas temporales
        logger.warning("⚠️ Retornando valores por defecto debido a error")
        try:
            return {
                "tokens_restantes": 0,
                "email": user.email if hasattr(user, 'email') else ""
            }
        except:
            return {
                "tokens_restantes": 0,
                "email": ""
            }


@users_router.post("/tokens/reload")
async def reload_tokens(token_input: TokenReloadInput, user = Depends(get_user)):
    """
    Endpoint para recargar tokens al perfil del usuario.
    Permite recargar incluso si los tokens están en negativo.
    """
    try:
        user_id = user.id
        
        if token_input.cantidad <= 0:
            raise HTTPException(
                status_code=400,
                detail="La cantidad debe ser mayor a 0"
            )
        
        # Obtener tokens actuales (pueden ser negativos)
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_actuales = profile_response.data[0]["tokens_restantes"]
        # Permitir recarga incluso con tokens negativos
        nuevos_tokens = tokens_actuales + token_input.cantidad
        
        # Actualizar tokens y resetear flag de email de recarga (para permitir nuevo email)
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": nuevos_tokens,
            "tokens_reload_email_sent": False  # Resetear flag para permitir nuevo email
        }).eq("id", user_id).execute()
        
        # Obtener email del usuario para enviar notificaciones
        user_email = user.email
        
        # IMPORTANTE: Enviar emails de notificación (admin y usuario) en segundo plano
        try:
            from lib.email import send_admin_email, send_email
            import threading
            
            # 1) EMAIL AL ADMIN: Notificación de recarga de tokens
            def send_admin_email_background():
                try:
                    admin_html = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                            <h2 style="color: white; margin: 0; font-size: 24px;">💰 Recarga de Tokens</h2>
                        </div>
                        
                        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                            <p style="font-size: 16px; margin-bottom: 20px;">
                                Un usuario ha recargado tokens en Codex Trader.
                            </p>
                            
                            <div style="background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                <ul style="list-style: none; padding: 0; margin: 0;">
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">Email del usuario:</strong> 
                                        <span style="color: #333;">{user_email}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">ID de usuario:</strong> 
                                        <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">Tokens anteriores:</strong> 
                                        <span style="color: #333;">{tokens_actuales:,}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #2563eb;">Tokens recargados:</strong> 
                                        <span style="color: #10b981; font-weight: bold;">+{token_input.cantidad:,}</span>
                                    </li>
                                    <li style="margin-bottom: 0;">
                                        <strong style="color: #2563eb;">Tokens totales ahora:</strong> 
                                        <span style="color: #333; font-weight: bold; font-size: 18px;">{nuevos_tokens:,}</span>
                                    </li>
                                </ul>
                            </div>
                            
                            <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                            </p>
                        </div>
                    </body>
                    </html>
                    """
                    send_admin_email("💰 Recarga de Tokens - Codex Trader", admin_html)
                except Exception as e:
                    print(f"⚠️ Error al enviar email al admin por recarga de tokens: {e}")
            
            # 2) EMAIL AL USUARIO: Confirmación de recarga
            def send_user_email_background():
                try:
                    if user_email:
                        # Verificar si ya se envió el email de confirmación de recarga (flag en base de datos)
                        try:
                            profile_check = supabase_client.table("profiles").select("tokens_reload_email_sent").eq("id", user_id).execute()
                            reload_email_already_sent = profile_check.data[0].get("tokens_reload_email_sent", False) if profile_check.data else False
                            
                            if reload_email_already_sent:
                                print(f"⚠️ Email de confirmación de recarga ya fue enviado anteriormente para {user_email}. Saltando envío.")
                                return
                        except Exception as check_error:
                            # Si falla la verificación, continuar con el envío (no crítico)
                            print(f"⚠️ Error al verificar flag tokens_reload_email_sent: {check_error}. Continuando con envío.")
                        
                        user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                        # Construir URL del app antes del f-string
                        frontend_url = FRONTEND_URL or os.getenv("FRONTEND_URL", "https://www.codextrader.tech")
                        frontend_url = frontend_url.strip('"').strip("'").strip()
                        app_url = frontend_url.rstrip('/')  # Usar la raíz del sitio, no /app
                        
                        user_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h1 style="color: white; margin: 0; font-size: 28px;">✅ Tokens Recargados Exitosamente</h1>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Hola <strong>{user_name}</strong>,
                                </p>
                                
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Tu recarga de tokens se ha procesado correctamente.
                                </p>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; border-left: 4px solid #10b981; margin: 20px 0;">
                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                        <li style="margin-bottom: 10px; color: #333;">
                                            <strong>Tokens anteriores:</strong> {tokens_actuales:,}
                                        </li>
                                        <li style="margin-bottom: 10px; color: #333;">
                                            <strong>Tokens recargados:</strong> <span style="color: #10b981; font-weight: bold;">+{token_input.cantidad:,}</span>
                                        </li>
                                        <li style="margin-bottom: 0; color: #333;">
                                            <strong>Tokens totales ahora:</strong> <span style="color: #059669; font-weight: bold; font-size: 20px;">{nuevos_tokens:,}</span>
                                        </li>
                                    </ul>
                                </div>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{app_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                        🚀 Continuar usando Codex Trader
                                    </a>
                                </div>
                                
                                <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                    Si no realizaste esta recarga, por favor contáctanos respondiendo a este correo.
                                </p>
                            </div>
                        </body>
                        </html>
                        """
                        result = send_email(
                            to=user_email,
                            subject="✅ Tokens recargados exitosamente - Codex Trader",
                            html=user_html
                        )
                        
                        # Marcar flag en base de datos si el email se envió exitosamente
                        if result:
                            try:
                                supabase_client.table("profiles").update({
                                    "tokens_reload_email_sent": True
                                }).eq("id", user_id).execute()
                                print(f"✅ Flag tokens_reload_email_sent marcado en base de datos para {user_id}")
                            except Exception as flag_error:
                                print(f"⚠️ No se pudo marcar flag tokens_reload_email_sent: {flag_error} (no crítico)")
                except Exception as e:
                    print(f"⚠️ Error al enviar email al usuario por recarga de tokens: {e}")
            
            # Enviar emails en background threads
            admin_thread = threading.Thread(target=send_admin_email_background, daemon=True)
            admin_thread.start()
            
            user_thread = threading.Thread(target=send_user_email_background, daemon=True)
            user_thread.start()
            
        except Exception as email_error:
            # No es crítico si falla el email
            print(f"⚠️ Error al preparar envío de emails por recarga de tokens: {email_error}")
        
        return {
            "mensaje": f"Tokens recargados exitosamente",
            "tokens_anteriores": tokens_actuales,
            "tokens_recargados": token_input.cantidad,
            "tokens_totales": nuevos_tokens
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al recargar tokens: {str(e)}"
        )


@users_router.post("/tokens/reset")
async def reset_tokens(
    user = Depends(get_user), 
    cantidad: int = Query(20000, description="Cantidad de tokens a establecer")
):
    """
    Endpoint de emergencia para resetear tokens a un valor específico.
    Útil cuando los tokens están en negativo y necesitas resetearlos.
    """
    try:
        user_id = user.id
        
        if cantidad < 0:
            raise HTTPException(
                status_code=400,
                detail="La cantidad debe ser mayor o igual a 0"
            )
        
        # Obtener perfil para verificar que existe
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_anteriores = profile_response.data[0]["tokens_restantes"]
        
        # Actualizar tokens directamente
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": cantidad
        }).eq("id", user_id).execute()
        
        return {
            "mensaje": f"Tokens reseteados exitosamente",
            "tokens_anteriores": tokens_anteriores,
            "tokens_totales": cantidad
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al resetear tokens: {str(e)}"
        )


@users_router.get("/me/is-admin")
async def check_is_admin(user = Depends(get_user)):
    """
    Endpoint para verificar si el usuario autenticado es administrador.
    Retorna True si el usuario tiene is_admin=True en profiles o está en ADMIN_EMAILS.
    """
    try:
        user_id = user.id
        
        # Verificar lista de emails de admin
        admin_emails = os.getenv("ADMIN_EMAILS", "").strip('"').strip("'").strip()
        if admin_emails:
            admin_list = [email.strip().lower() for email in admin_emails.split(",")]
            if user.email and user.email.lower() in admin_list:
                return {"is_admin": True}
        
        # Verificar campo is_admin en profiles
        try:
            profile_response = supabase_client.table("profiles").select("is_admin").eq("id", user_id).execute()
            if profile_response.data and profile_response.data[0].get("is_admin", False):
                return {"is_admin": True}
        except Exception as e:
            logger.warning(f"⚠️ Error al verificar is_admin en profiles: {e}")
        
        return {"is_admin": False}
    except Exception as e:
        logger.error(f"❌ Error al verificar si usuario es admin: {e}")
        return {"is_admin": False}


@users_router.get("/me/usage")
async def get_user_usage(user = Depends(get_user)):
    """
    Obtiene información sobre el uso de tokens y estado de uso justo del usuario.
    
    Retorna:
    - tokens_monthly_limit: Límite mensual de tokens según el plan
    - tokens_restantes: Tokens restantes actuales
    - usage_percent: Porcentaje de uso (0-100)
    - fair_use_warning_shown: Si se mostró aviso suave al 80%
    - fair_use_discount_eligible: Si es elegible para descuento al 90%
    - fair_use_discount_used: Si ya usó el descuento en este ciclo
    """
    try:
        user_id = user.id
        
        # Intentar obtener columnas de uso justo, pero manejar si no existen
        try:
            profile_response = supabase_client.table("profiles").select(
                "tokens_restantes, tokens_monthly_limit, current_plan, fair_use_warning_shown, "
                "fair_use_discount_eligible, fair_use_discount_used, fair_use_discount_eligible_at"
            ).eq("id", user_id).execute()
        except Exception as e:
            # Si falla por columnas faltantes, intentar solo con columnas básicas
            logger.warning(f"Error al obtener columnas de uso justo, intentando solo columnas básicas: {e}")
            profile_response = supabase_client.table("profiles").select(
                "tokens_restantes, current_plan"
            ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        tokens_restantes = profile.get("tokens_restantes", 0) or 0
        tokens_monthly_limit = profile.get("tokens_monthly_limit", 0) or 0
        current_plan = profile.get("current_plan")
        
        # Si tokens_monthly_limit es 0 o None, intentar obtenerlo del plan actual
        if tokens_monthly_limit == 0 and current_plan:
            try:
                from plans import get_plan_by_code
                plan = get_plan_by_code(current_plan)
                if plan:
                    tokens_monthly_limit = plan.tokens_per_month
                    logger.info(f"⚠️ tokens_monthly_limit no estaba configurado, usando valor del plan {current_plan}: {tokens_monthly_limit}")
            except Exception as e:
                logger.warning(f"Error al obtener tokens del plan: {e}")
        
        # Calcular porcentaje de uso solo si tokens_monthly_limit existe
        usage_percent = 0.0
        tokens_usados = 0
        if tokens_monthly_limit > 0:
            # tokens_usados = cuántos tokens del límite mensual se han usado
            # Si tokens_restantes > tokens_monthly_limit, significa que tiene tokens extra (paquetes)
            # En ese caso, tokens_usados = 0 (no ha usado nada del límite mensual)
            tokens_usados = max(0, tokens_monthly_limit - tokens_restantes)
            usage_percent = (tokens_usados / tokens_monthly_limit) * 100
            # Asegurar que no sea negativo ni mayor a 100%
            usage_percent = max(0.0, min(100.0, usage_percent))
        
        result = {
            "tokens_restantes": tokens_restantes,
            "current_plan": current_plan
        }
        
        # Agregar campos de uso justo solo si existen
        if tokens_monthly_limit > 0:
            result["tokens_monthly_limit"] = tokens_monthly_limit
            result["tokens_usados"] = tokens_usados
            result["usage_percent"] = usage_percent
        
        # Intentar agregar campos de fair use si existen
        if "fair_use_warning_shown" in profile:
            result["fair_use_warning_shown"] = profile.get("fair_use_warning_shown", False)
        if "fair_use_discount_eligible" in profile:
            result["fair_use_discount_eligible"] = profile.get("fair_use_discount_eligible", False)
        if "fair_use_discount_used" in profile:
            result["fair_use_discount_used"] = profile.get("fair_use_discount_used", False)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener información de uso: {str(e)}"
        )


@users_router.post("/users/notify-registration")
async def notify_user_registration(
    input_data: Optional[NotifyRegistrationInput] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Notifica al administrador sobre un nuevo registro de usuario.
    
    Este endpoint debe llamarse desde el frontend después de que un usuario
    se registra exitosamente. Envía un email al administrador con la información
    del nuevo usuario.
    
    Puede llamarse de dos formas:
    1. Con token de autenticación en el header (usuario ya logueado)
    2. Con token_hash de confirmación en el body (después de confirmar email)
    
    IMPORTANTE: El envío de email se hace en segundo plano y no bloquea la respuesta.
    """
    logger.info("=" * 60)
    logger.info("[API] POST /users/notify-registration recibido")
    logger.info(f"   Authorization header presente: {bool(authorization)}")
    logger.info(f"   Token_hash en body: {bool(input_data and input_data.token_hash)}")
    logger.info(f"   User_id en body: {bool(input_data and input_data.user_id)}")
    logger.info(f"   Triggered_by: {input_data.triggered_by if input_data else 'None'}")
    logger.info(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[API] POST /users/notify-registration recibido")
    print(f"   Authorization header presente: {bool(authorization)}")
    print(f"   Token_hash en body: {bool(input_data and input_data.token_hash)}")
    print(f"   User_id en body: {bool(input_data and input_data.user_id)}")
    print(f"   Triggered_by: {input_data.triggered_by if input_data else 'None'}")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        user = None
        
        # Intentar obtener usuario desde el token de autenticación
        if authorization:
            try:
                logger.info("[DEBUG] Intentando obtener usuario desde token de autenticación...")
                logger.info(f"[DEBUG] Token (primeros 20 chars): {authorization[:20] if authorization else 'None'}...")
                print(f"   [DEBUG] Intentando obtener usuario desde token de autenticación...")
                print(f"   [DEBUG] Token (primeros 20 chars): {authorization[:20] if authorization else 'None'}...")
                user = await get_user(authorization)
                logger.info(f"[OK] Usuario obtenido desde token: {user.email if user else 'None'}")
                logger.info(f"[DEBUG] User ID: {user.id if user else 'None'}")
                print(f"   [OK] Usuario obtenido desde token: {user.email if user else 'None'}")
                print(f"   [DEBUG] User ID: {user.id if user else 'None'}")
            except HTTPException as e:
                logger.warning(f"[WARNING] Error al obtener usuario desde token: {e.detail}")
                logger.warning(f"[DEBUG] Status code: {e.status_code}")
                print(f"   [WARNING] Error al obtener usuario desde token: {e.detail}")
                print(f"   [DEBUG] Status code: {e.status_code}")
                # Si falla la autenticación, continuar para intentar con token_hash
                pass
            except Exception as e:
                logger.error(f"[ERROR] Excepción inesperada al obtener usuario: {e}", exc_info=True)
                print(f"   [ERROR] Excepción inesperada al obtener usuario: {e}")
                import traceback
                traceback.print_exc()
                pass
        
        # Si no hay usuario autenticado pero hay user_id (desde trigger), obtener usuario directamente
        if not user and input_data and input_data.user_id:
            try:
                print(f"   [TRIGGER] Intentando obtener usuario desde user_id: {input_data.user_id}")
                logger.info(f"[TRIGGER] Intentando obtener usuario desde user_id: {input_data.user_id}")
                # Obtener usuario directamente desde Supabase usando service key
                user_response = supabase_client.auth.admin.get_user_by_id(input_data.user_id)
                if user_response and user_response.user:
                    user = user_response.user
                    print(f"   [OK] Usuario obtenido desde user_id (trigger): {user.email if user else 'None'}")
                    logger.info(f"[OK] Usuario obtenido desde user_id (trigger): {user.email if user else 'None'}")
                else:
                    print(f"   [ERROR] No se pudo obtener usuario desde user_id")
                    logger.warning(f"[ERROR] No se pudo obtener usuario desde user_id: {input_data.user_id}")
            except Exception as e:
                print(f"   [ERROR] Error al obtener usuario desde user_id: {str(e)}")
                logger.error(f"[ERROR] Error al obtener usuario desde user_id: {str(e)}")
                # Continuar para intentar con token_hash si está disponible
        
        # Si no hay usuario autenticado pero hay token_hash, verificar el token_hash
        if not user and input_data and input_data.token_hash:
            try:
                print(f"   Intentando verificar token_hash...")
                # Verificar el token_hash con Supabase
                verify_response = supabase_client.auth.verify_otp({
                    "type": "email",
                    "token_hash": input_data.token_hash
                })
                if verify_response.user:
                    user = verify_response.user
                    print(f"   [OK] Usuario obtenido desde token_hash: {user.email if user else 'None'}")
                else:
                    print(f"   [ERROR] Token_hash invalido: no se obtuvo usuario")
                    raise HTTPException(
                        status_code=401,
                        detail="Token de confirmación inválido"
                    )
            except Exception as e:
                print(f"   [ERROR] Error al verificar token_hash: {str(e)}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Error al verificar token de confirmación: {str(e)}"
                )
        
        # Si aún no hay usuario, error
        if not user:
            print(f"   [ERROR] No se pudo obtener usuario. Authorization: {bool(authorization)}, Token_hash: {bool(input_data and input_data.token_hash)}, User_id: {bool(input_data and input_data.user_id)}")
            logger.error(f"[ERROR] No se pudo obtener usuario. Authorization: {bool(authorization)}, Token_hash: {bool(input_data and input_data.token_hash)}, User_id: {bool(input_data and input_data.user_id)}")
            raise HTTPException(
                status_code=401,
                detail="Se requiere autenticación (header Authorization), token_hash de confirmación, o user_id (desde trigger) en el body"
            )
        
        user_id = user.id
        user_email = user.email
        logger.info(f"[EMAIL] Procesando emails para usuario: {user_email} (ID: {user_id})")
        print(f"   [EMAIL] Procesando emails para usuario: {user_email} (ID: {user_id})")
        
        # PROTECCIÓN CONTRA DUPLICADOS: Verificar si ya se enviaron los emails de bienvenida
        # Usar un sistema de cache en memoria para evitar duplicados en la misma sesión
        # También verificar en la base de datos si existe un flag (opcional, se puede agregar después)
        import hashlib
        
        # Crear una clave única para este usuario en esta sesión
        cache_key = f"welcome_email_sent_{user_id}"
        
        # Cache simple en memoria (se puede mejorar con Redis en producción)
        if not hasattr(notify_user_registration, '_email_cache'):
            notify_user_registration._email_cache = {}
        
        # Limpiar cache antiguo (más de 1 hora)
        current_time = time.time()
        notify_user_registration._email_cache = {
            k: v for k, v in notify_user_registration._email_cache.items()
            if current_time - v < 3600  # 1 hora
        }
        
        # Verificar si ya se envió en los últimos 5 minutos
        if cache_key in notify_user_registration._email_cache:
            sent_time = notify_user_registration._email_cache[cache_key]
            time_since_sent = current_time - sent_time
            if time_since_sent < 300:  # 5 minutos
                logger.warning(f"[WARNING] Emails de bienvenida ya enviados recientemente para {user_email} (hace {int(time_since_sent)} segundos). Ignorando solicitud duplicada.")
                print(f"   [WARNING] Emails de bienvenida ya enviados recientemente. Ignorando solicitud duplicada.")
                return {
                    "success": True,
                    "message": "Emails ya fueron enviados anteriormente",
                    "already_sent": True
                }
        
        # Importar constantes de negocio y helpers de referidos
        from lib.business import (
            INITIAL_FREE_TOKENS,
            REF_INVITED_BONUS_TOKENS,
            REF_REFERRER_BONUS_TOKENS,
            REF_MAX_REWARDS,
            APP_NAME
        )
        from lib.referrals import assign_referral_code_if_needed, build_referral_url
        
        # IMPORTANTE: Asignar referral_code ANTES de obtener el perfil y enviar emails
        logger.info(f"[REFERRALS] Verificando/asignando referral_code para usuario {user_id}...")
        referral_code = assign_referral_code_if_needed(supabase_client, user_id)
        
        if not referral_code:
            logger.error(f"[REFERRALS] ERROR: No se pudo asignar referral_code al usuario {user_id}")
            # Intentar obtener el código del perfil como fallback
            try:
                profile_check = supabase_client.table("profiles").select("referral_code").eq("id", user_id).execute()
                if profile_check.data and profile_check.data[0].get("referral_code"):
                    referral_code = profile_check.data[0]["referral_code"]
                    logger.info(f"[REFERRALS] Código encontrado en perfil: {referral_code}")
                else:
                    referral_code = "No disponible"
                    logger.warning(f"[REFERRALS] Usuario {user_id} no tiene referral_code y no se pudo generar")
            except Exception as e:
                logger.error(f"[REFERRALS] Error al verificar código en perfil: {e}")
                referral_code = "No disponible"
        
        # Construir referral_url usando FRONTEND_URL
        referral_url = build_referral_url(referral_code)
        logger.info(f"[REFERRALS] Referral URL construida: {referral_url}")
        
        # Obtener información del perfil del usuario
        # Intentar obtener todas las columnas disponibles, manejando errores si alguna no existe
        try:
            # Primero intentar obtener todas las columnas (incluyendo referral_code si existe)
            profile_response = supabase_client.table("profiles").select(
                "referral_code, referred_by_user_id, current_plan, created_at, tokens_restantes, welcome_email_sent"
            ).eq("id", user_id).execute()
        except Exception as e:
            # Si falla porque referral_code no existe, intentar sin esa columna
            logger.warning(f"[WARNING] Error al obtener perfil con referral_code, intentando sin esa columna: {e}")
            try:
                profile_response = supabase_client.table("profiles").select(
                    "referred_by_user_id, current_plan, created_at, tokens_restantes"
                ).eq("id", user_id).execute()
            except Exception as e2:
                logger.error(f"[ERROR] Error al obtener perfil: {e2}")
                profile_response = None
        
        if not profile_response or not profile_response.data:
            # Si no hay perfil, el usuario acaba de registrarse
            # El perfil se creará automáticamente por el trigger
            profile_data = {}
        else:
            profile_data = profile_response.data[0]
        
        # Verificar si ya se envió el email de bienvenida (flag en base de datos)
        # PERMITIR reenvío si viene del trigger o si se solicita explícitamente
        welcome_email_already_sent = profile_data.get("welcome_email_sent", False)
        force_resend = input_data and getattr(input_data, 'force_resend', False)
        is_trigger_call = input_data and input_data.triggered_by == 'database_trigger'
        
        if welcome_email_already_sent and not force_resend and not is_trigger_call:
            logger.info(f"[EMAIL] Email de bienvenida ya fue enviado anteriormente para {user_email}. Saltando envío.")
            print(f"   [INFO] Email de bienvenida ya fue enviado anteriormente. Saltando envío.")
            return {
                "success": True,
                "message": "Email de bienvenida ya fue enviado anteriormente",
                "already_sent": True
            }
        
        if welcome_email_already_sent and (force_resend or is_trigger_call):
            logger.info(f"[EMAIL] Reenviando email de bienvenida para {user_email} (force_resend={force_resend}, is_trigger={is_trigger_call})")
            print(f"   [INFO] Reenviando email de bienvenida (force_resend={force_resend}, is_trigger={is_trigger_call})")
        
        # Asegurar que tenemos el referral_code (usar el que acabamos de asignar o el del perfil)
        if not referral_code or referral_code == "No disponible":
            referral_code = profile_data.get("referral_code") or referral_code or "No disponible"
        
        # Si aún no hay código, intentar asignarlo una vez más
        if not referral_code or referral_code == "No disponible":
            logger.warning(f"[REFERRALS] Reintentando asignar código...")
            referral_code = assign_referral_code_if_needed(supabase_client, user_id)
            if referral_code:
                referral_url = build_referral_url(referral_code)
                logger.info(f"[REFERRALS] Código asignado en segundo intento: {referral_code}")
        
        referred_by_id = profile_data.get("referred_by_user_id")
        current_plan = profile_data.get("current_plan")
        if not current_plan:
            current_plan = "Sin plan (modo prueba)"
        created_at = profile_data.get("created_at")
        initial_tokens = profile_data.get("tokens_restantes", INITIAL_FREE_TOKENS)
        
        # Obtener información del referrer si existe
        referrer_info = "No aplica"
        if referred_by_id:
            try:
                referrer_response = supabase_client.table("profiles").select("email").eq("id", referred_by_id).execute()
                if referrer_response.data:
                    referrer_info = f"{referrer_response.data[0].get('email', 'N/A')} (ID: {referred_by_id})"
                else:
                    referrer_info = f"ID: {referred_by_id}"
            except Exception:
                referrer_info = f"ID: {referred_by_id}"
        
        # IMPORTANTE: Enviar email de notificación al admin
        # Esto se hace en segundo plano y no bloquea la respuesta
        try:
            from lib.email import send_admin_email
            
            # Formatear fecha
            try:
                if created_at:
                    if isinstance(created_at, str):
                        if "T" in created_at:
                            date_obj = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            date_obj = datetime.fromisoformat(created_at)
                        formatted_date = date_obj.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        formatted_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                else:
                    formatted_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                formatted_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h2 style="color: white; margin: 0; font-size: 24px;">Nuevo registro en Codex Trader</h2>
                </div>
                
                <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <p style="font-size: 16px; margin-bottom: 20px;">
                        Se ha registrado un nuevo usuario en Codex Trader.
                    </p>
                    
                    <div style="background: #f9fafb; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <ul style="list-style: none; padding: 0; margin: 0;">
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Email:</strong> 
                                <span style="color: #333;">{user_email}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">ID de usuario:</strong> 
                                <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Fecha de registro:</strong> 
                                <span style="color: #333;">{formatted_date}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Plan actual:</strong> 
                                <span style="color: #333;">{current_plan}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Tokens iniciales asignados:</strong> 
                                <span style="color: #333;">{INITIAL_FREE_TOKENS:,} tokens</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Código de referido:</strong> 
                                <span style="color: #333; font-family: monospace; font-weight: bold;">{referral_code if referral_code and referral_code != "No disponible" else "No disponible (error al generar)"}</span>
                            </li>
                            <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                <strong style="color: #2563eb;">Enlace de invitación:</strong> 
                                <span style="color: #333; font-size: 12px; word-break: break-all;">
                                    <a href="{referral_url}" style="color: #2563eb; text-decoration: none;">{referral_url}</a>
                                </span>
                            </li>
                            <li style="margin-bottom: 0;">
                                <strong style="color: #2563eb;">Registrado por referido:</strong> 
                                <span style="color: #333;">{referrer_info}</span>
                            </li>
                        </ul>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Enviar email en segundo plano (no bloquea)
            # IMPORTANTE: Enviar directamente en lugar de usar threads para evitar problemas
            # Los threads pueden no ejecutarse correctamente en algunos entornos
            print(f"   [EMAIL] Enviando email al admin...")
            try:
                result = send_admin_email("Nuevo registro en Codex Trader", html_content)
                if result:
                    print(f"   [OK] Email al admin enviado correctamente")
                else:
                    print(f"   [ERROR] Error al enviar email al admin (revisa logs anteriores)")
            except Exception as e:
                print(f"   [ERROR] ERROR al enviar email al admin: {e}")
                import traceback
                traceback.print_exc()
        except Exception as email_error:
            # No es crítico si falla el email
            print(f"   [WARNING] No se pudo enviar email de notificacion de registro: {email_error}")
        
        # IMPORTANTE: Enviar email de bienvenida al usuario
        # Esto se hace en segundo plano y no bloquea la respuesta
        try:
            from lib.email import send_email
            
            # Construir enlaces usando FRONTEND_URL (normalizar sin barra final)
            base_url = (FRONTEND_URL or os.getenv("FRONTEND_URL", "https://www.codextrader.tech")).rstrip('/')
            # Usar build_referral_url para consistencia (usa /?ref= en lugar de /registro?ref=)
            referral_url = build_referral_url(referral_code)
            app_url = base_url  # Usar la raíz del sitio, no /app
            
            # Obtener nombre del usuario desde el email (parte antes del @)
            user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
            
            # Obtener contraseña si está disponible en input_data (usar getattr para evitar errores si no existe)
            user_password = None
            if input_data:
                try:
                    user_password = getattr(input_data, 'password', None)
                except (AttributeError, TypeError):
                    user_password = None
            
            # Construir sección de credenciales si hay contraseña
            credentials_section = ""
            if user_password:
                credentials_section = f"""
                    <!-- Bloque: Tus credenciales de acceso -->
                    <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 2px solid #10b981; padding: 25px; border-radius: 12px; margin: 30px 0; box-shadow: 0 4px 6px rgba(16, 185, 129, 0.1);">
                        <h3 style="color: #059669; margin-top: 0; font-size: 20px; margin-bottom: 15px; text-align: center;">
                            🔐 Tus credenciales de acceso
                        </h3>
                        <p style="font-size: 14px; color: #065f46; margin-bottom: 20px; text-align: center;">
                            Guarda esta información de forma segura. La necesitarás para iniciar sesión:
                        </p>
                        <div style="background: #ffffff; padding: 20px; border-radius: 8px; border: 1px dashed #10b981; margin: 15px 0;">
                            <div style="margin-bottom: 15px;">
                                <p style="margin: 0 0 5px 0; font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">
                                    📧 Usuario (Email):
                                </p>
                                <p style="margin: 0; font-size: 16px; font-weight: 700; color: #1f2937; font-family: monospace; word-break: break-all; padding: 10px; background: #f9fafb; border-radius: 6px;">
                                    {user_email}
                                </p>
                            </div>
                            <div>
                                <p style="margin: 0 0 5px 0; font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600;">
                                    🔑 Contraseña:
                                </p>
                                <p style="margin: 0; font-size: 16px; font-weight: 700; color: #1f2937; font-family: monospace; padding: 10px; background: #f9fafb; border-radius: 6px; letter-spacing: 2px;">
                                    {user_password}
                                </p>
                            </div>
                        </div>
                        <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; border-radius: 6px; margin-top: 15px;">
                            <p style="margin: 0; font-size: 13px; color: #92400e; line-height: 1.5;">
                                <strong>⚠️ Importante:</strong> Después de confirmar tu email, deberás iniciar sesión manualmente usando estas credenciales. No se iniciará sesión automáticamente por seguridad.
                            </p>
                        </div>
                    </div>
                """
            else:
                credentials_section = f"""
                    <!-- Bloque: Información de acceso -->
                    <div style="background: #f0f9ff; border-left: 4px solid #3b82f6; padding: 20px; border-radius: 8px; margin: 30px 0;">
                        <p style="margin: 0; font-size: 14px; color: #1e40af; line-height: 1.6;">
                            <strong>📧 Tu usuario:</strong> {user_email}<br>
                            <strong>🔑 Tu contraseña:</strong> La que ingresaste al registrarte
                        </p>
                        <p style="margin: 10px 0 0 0; font-size: 13px; color: #1e40af;">
                            Después de confirmar tu email, deberás iniciar sesión manualmente usando estas credenciales.
                        </p>
                    </div>
                """
            
            welcome_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; font-size: 28px;">🧠📈 Bienvenido a Codex Trader</h1>
                </div>
                
                <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <!-- Bloque: Tu cuenta -->
                    <div style="margin-bottom: 30px;">
                        <p style="font-size: 16px; margin-bottom: 20px;">
                            Hola <strong>{user_email}</strong>, bienvenido a Codex Trader.
                        </p>
                        
                        {credentials_section}
                        
                        <div style="background: #f9fafb; padding: 20px; border-radius: 8px; border-left: 4px solid #2563eb; margin-top: 20px;">
                            <ul style="list-style: none; padding: 0; margin: 0;">
                                <li style="margin-bottom: 10px; color: #333;">
                                    <strong>Plan actual:</strong> Modo prueba (sin suscripción)
                                </li>
                                <li style="margin-bottom: 10px; color: #333;">
                                    <strong>Tokens iniciales:</strong> {INITIAL_FREE_TOKENS:,} para probar el asistente
                                </li>
                                <li style="margin-bottom: 0; color: #333;">
                                    <strong>Acceso al asistente:</strong> 
                                    <a href="{app_url}" style="color: #2563eb; text-decoration: none; font-weight: bold;">Empieza aquí</a>
                                </li>
                            </ul>
                        </div>
                    </div>
                    
                    <!-- Bloque: ¿Qué puedes hacer con Codex? -->
                    <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb;">
                        <h3 style="color: #2563eb; margin-top: 0; font-size: 18px;">¿Qué puedes hacer con Codex?</h3>
                        <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                            <li style="margin-bottom: 10px;">Pedir explicaciones claras sobre gestión de riesgo, tamaño de posición y drawdown.</li>
                            <li style="margin-bottom: 10px;">Profundizar en psicología del trader y disciplina.</li>
                            <li style="margin-bottom: 10px;">Analizar setups, ideas de estrategia y marcos temporales.</li>
                            <li style="margin-bottom: 0;">Usarlo como cerebro de estudio apoyado en contenido profesional de trading.</li>
                        </ul>
                    </div>
                    
                    <!-- Botón de llamada a la acción -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{app_url}" style="display: inline-block; background: #2563eb; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                            🚀 Empieza aquí
                        </a>
                    </div>
                    
                    <!-- Bloque: Invita a tus amigos y gana tokens -->
                    <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 30px 0; border-left: 4px solid #f59e0b;">
                        <h3 style="color: #92400e; margin-top: 0; font-size: 18px;">💎 Invita a tus amigos y gana tokens</h3>
                        <p style="margin-bottom: 15px; color: #78350f;">
                            Comparte tu enlace personal y ambos ganan:
                        </p>
                        <ul style="margin: 15px 0; padding-left: 20px; color: #78350f;">
                            <li style="margin-bottom: 10px;">
                                Tu amigo recibe <strong>+{REF_INVITED_BONUS_TOKENS:,} tokens de bienvenida</strong> cuando activa su primer plan de pago.
                            </li>
                            <li style="margin-bottom: 15px;">
                                Tú ganas <strong>+{REF_REFERRER_BONUS_TOKENS:,} tokens</strong> por cada amigo que pague su primer plan (hasta {REF_MAX_REWARDS} referidos con recompensa completa).
                            </li>
                        </ul>
                        <div style="background: white; padding: 15px; border-radius: 6px; margin: 15px 0; border: 2px dashed #d97706;">
                            <p style="margin: 5px 0; font-size: 14px; color: #666;"><strong>Tu código de referido:</strong></p>
                            <p style="margin: 5px 0; font-size: 18px; font-weight: bold; color: #2563eb; word-break: break-all; font-family: monospace;">{referral_code if referral_code and referral_code != "No disponible" else "Se generará en unos minutos"}</p>
                            <p style="margin: 10px 0 5px 0; font-size: 14px; color: #666;"><strong>Tu enlace de invitación:</strong></p>
                            <p style="margin: 5px 0; font-size: 14px; color: #2563eb; word-break: break-all;">
                                <a href="{referral_url}" style="color: #2563eb; text-decoration: none;">{referral_url}</a>
                            </p>
                        </div>
                    </div>
                    
                    <!-- Bloque final: Disclaimer -->
                    <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                        Codex Trader es una herramienta educativa. No ofrecemos asesoría financiera personalizada ni recomendaciones directas de compra/venta. Los resultados pasados no garantizan rendimientos futuros. Cada cliente es responsable de sus decisiones en el mercado.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Verificar configuración SMTP antes de intentar enviar
            from lib.email import SMTP_AVAILABLE, SMTP_HOST, SMTP_USER, EMAIL_FROM
            logger.info("[EMAIL] ========================================")
            logger.info("[EMAIL] INICIANDO ENVIO DE EMAIL DE BIENVENIDA")
            logger.info("[EMAIL] ========================================")
            logger.info(f"[EMAIL] SMTP_AVAILABLE: {SMTP_AVAILABLE}")
            logger.info(f"[EMAIL] SMTP_HOST: {SMTP_HOST}")
            logger.info(f"[EMAIL] SMTP_USER: {SMTP_USER}")
            logger.info(f"[EMAIL] EMAIL_FROM: {EMAIL_FROM}")
            logger.info(f"[EMAIL] Destinatario: {user_email}")
            print(f"   [EMAIL] ========================================")
            print(f"   [EMAIL] INICIANDO ENVIO DE EMAIL DE BIENVENIDA")
            print(f"   [EMAIL] ========================================")
            print(f"   [EMAIL] SMTP_AVAILABLE: {SMTP_AVAILABLE}")
            print(f"   [EMAIL] SMTP_HOST: {SMTP_HOST}")
            print(f"   [EMAIL] SMTP_USER: {SMTP_USER}")
            print(f"   [EMAIL] EMAIL_FROM: {EMAIL_FROM}")
            print(f"   [EMAIL] Destinatario: {user_email}")
            
            if not SMTP_AVAILABLE:
                logger.error("[ERROR] SMTP no está configurado. No se puede enviar email de bienvenida.")
                logger.error("[ERROR] Verifica que estas variables estén configuradas en Railway:")
                logger.error("[ERROR]   - SMTP_HOST")
                logger.error("[ERROR]   - SMTP_USER")
                logger.error("[ERROR]   - SMTP_PASS")
                logger.error("[ERROR]   - EMAIL_FROM")
                print(f"   [ERROR] SMTP no está configurado. Verifica variables de entorno en Railway.")
            else:
                logger.info(f"[EMAIL] Enviando email de bienvenida a {user_email}...")
                print(f"   [EMAIL] Enviando email de bienvenida a {user_email}...")
                try:
                    result = send_email(
                        to=user_email,
                        subject="🧠📈 Bienvenido a Codex Trader",
                        html=welcome_html
                    )
                    logger.info(f"[EMAIL] Resultado de send_email: {result}")
                    print(f"   [EMAIL] Resultado de send_email: {result}")
                    if result:
                        logger.info(f"[OK] Email de bienvenida enviado correctamente a {user_email}")
                        print(f"   [OK] Email de bienvenida enviado correctamente a {user_email}")
                        
                        # Marcar flag en base de datos para evitar duplicados
                        try:
                            supabase_client.table("profiles").update({
                                "welcome_email_sent": True
                            }).eq("id", user_id).execute()
                            logger.info(f"[OK] Flag welcome_email_sent marcado en base de datos para {user_id}")
                            print(f"   [OK] Flag welcome_email_sent marcado en base de datos")
                        except Exception as flag_error:
                            logger.warning(f"[WARNING] No se pudo marcar flag welcome_email_sent: {flag_error}")
                            print(f"   [WARNING] No se pudo marcar flag welcome_email_sent (no crítico)")
                    else:
                        logger.error("[ERROR] Error al enviar email de bienvenida (revisa logs anteriores)")
                        print(f"   [ERROR] Error al enviar email de bienvenida (revisa logs anteriores)")
                        print(f"   [ERROR] Verifica SMTP_AVAILABLE y configuración de email")
                        # NO marcar cache ni flag si el email falló
                        raise Exception("Email de bienvenida falló al enviarse")
                except Exception as e:
                    logger.error(f"[ERROR] ERROR al enviar email de bienvenida: {e}", exc_info=True)
                    print(f"   [ERROR] ERROR al enviar email de bienvenida: {e}")
                    import traceback
                    traceback.print_exc()
                    # NO marcar cache ni flag si el email falló
                    raise  # Re-lanzar el error para que no se marque el cache
            logger.info("[EMAIL] ========================================")
            print(f"   [EMAIL] ========================================")
        except Exception as welcome_error:
            # Si falla el email de bienvenida, NO marcar cache ni flag
            logger.error(f"[ERROR] No se pudo enviar email de bienvenida: {welcome_error}")
            print(f"   [ERROR] No se pudo enviar email de bienvenida: {welcome_error}")
            # NO marcar cache - permitir reintentos
            return {
                "success": False,
                "message": f"Error al enviar email de bienvenida: {str(welcome_error)}",
                "error": "smtp_error"
            }
        
        # Marcar en cache que los emails fueron enviados (SOLO si llegamos aquí sin errores)
        try:
            notify_user_registration._email_cache[cache_key] = time.time()
            logger.info(f"[OK] Emails enviados y marcados en cache para {user_email}")
        except:
            pass  # Si falla el cache, no es crítico
        
        logger.info("[OK] Endpoint completado exitosamente. Emails enviados directamente.")
        print(f"   [OK] Endpoint completado exitosamente. Emails enviados directamente.")
        return {
            "success": True,
            "message": "Registro notificado correctamente"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        # No lanzar error, solo registrar
        logger.error("=" * 60)
        logger.error(f"[ERROR] ERROR en endpoint notify-registration: {str(e)}", exc_info=True)
        logger.error("=" * 60)
        print(f"   [ERROR] ERROR en endpoint notify-registration: {str(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "message": "Error al notificar registro, pero el usuario fue creado correctamente"
        }


@users_router.get("/me/referrals-summary")
async def get_referrals_summary(user = Depends(get_user)):
    """
    Obtiene un resumen de estadísticas de referidos del usuario actual.
    
    Retorna:
    - totalInvited: Total de usuarios que se registraron con el código de referido
    - totalPaid: Total de usuarios que pagaron su primera suscripción
    - referralRewardsCount: Cantidad de referidos que ya generaron recompensa (máximo 5)
    - referralTokensEarned: Tokens totales ganados por referidos
    - referralCode: Código de referido del usuario
    """
    try:
        user_id = user.id
        
        # Obtener información del perfil del usuario
        profile_response = supabase_client.table("profiles").select(
            "referral_code, referral_rewards_count, referral_tokens_earned"
        ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        referral_code = profile.get("referral_code")
        referral_rewards_count = profile.get("referral_rewards_count", 0)
        referral_tokens_earned = profile.get("referral_tokens_earned", 0)
        
        # Contar total de usuarios que se registraron con este código de referido
        total_invited_response = supabase_client.table("profiles").select(
            "id"
        ).eq("referred_by_user_id", user_id).execute()
        
        total_invited = len(total_invited_response.data) if total_invited_response.data else 0
        
        # Contar usuarios que ya pagaron (tienen has_generated_referral_reward = true)
        total_paid_response = supabase_client.table("profiles").select(
            "id"
        ).eq("referred_by_user_id", user_id).eq("has_generated_referral_reward", True).execute()
        
        total_paid = len(total_paid_response.data) if total_paid_response.data else 0
        
        return {
            "totalInvited": total_invited,
            "totalPaid": total_paid,
            "referralRewardsCount": referral_rewards_count,
            "referralTokensEarned": referral_tokens_earned,
            "referralCode": referral_code
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener resumen de referidos: {str(e)}"
        )


@users_router.post("/referrals/process")
async def process_referral(
    referral_input: ProcessReferralInput,
    user = Depends(get_user)
):
    """
    Procesa un código de referido después del registro de un usuario.
    
    Este endpoint debe llamarse después de que un usuario se registra con un código
    de referido (por ejemplo, desde ?ref=XXXX en la URL de registro).
    
    Recibe:
    - referral_code: Código de referido del usuario que invitó
    
    Actualiza:
    - referred_by_user_id: ID del usuario que invitó
    
    Retorna:
    - success: True si se procesó correctamente
    - message: Mensaje descriptivo
    """
    try:
        user_id = user.id
        referral_code = referral_input.referral_code.strip().upper()
        
        if not referral_code:
            raise HTTPException(
                status_code=400,
                detail="El código de referido no puede estar vacío"
            )
        
        # OPTIMIZACIÓN: Obtener toda la información necesaria en una sola consulta
        profile_response = supabase_client.table("profiles").select(
            "referred_by_user_id, referral_code, tokens_restantes"
        ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        existing_referrer = profile.get("referred_by_user_id")
        if existing_referrer:
            # Usuario ya tiene un referido asignado (ya usó un código antes)
            raise HTTPException(
                status_code=400,
                detail="Este usuario ya tiene un código de referido asignado. Solo puedes usar un código de referido al registrarte."
            )
        
        # Verificar que el usuario no se esté refiriendo a sí mismo
        user_referral_code = profile.get("referral_code")
        if user_referral_code == referral_code:
            raise HTTPException(
                status_code=400,
                detail="No puedes usar tu propio código de referido"
            )
        
        # Buscar al usuario que tiene ese código de referido
        referrer_response = supabase_client.table("profiles").select("id, email, referral_code").eq("referral_code", referral_code).execute()
        
        if not referrer_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Código de referido inválido: {referral_code}"
            )
        
        referrer_id = referrer_response.data[0]["id"]
        
        # OPTIMIZACIÓN: Calcular tokens directamente sin consulta adicional
        welcome_bonus = 5000
        current_tokens = profile.get("tokens_restantes", 0) or 0
        new_tokens = current_tokens + welcome_bonus
        
        # Actualizar perfil y tokens en una sola operación
        update_response = supabase_client.table("profiles").update({
            "referred_by_user_id": referrer_id,
            "tokens_restantes": new_tokens
        }).eq("id", user_id).execute()
        
        if update_response.data:
            # IMPORTANTE: Enviar email de notificación al admin sobre nuevo registro
            # Esto se hace en segundo plano y no bloquea la respuesta
            try:
                from lib.email import send_admin_email
                import threading
                
                # Obtener información del usuario y referrer para el email
                user_email = user.email
                referrer_email = referrer_response.data[0].get('email', 'N/A')
                
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <h2 style="color: #2563eb;">Nuevo registro en Codex Trader</h2>
                    <p>Se ha registrado un nuevo usuario en Codex Trader.</p>
                    <ul>
                        <li><strong>Email:</strong> {user_email}</li>
                        <li><strong>Fecha de registro:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</li>
                        <li><strong>Registrado por referido:</strong> {referrer_email} (ID: {referrer_id})</li>
                        <li><strong>Código de referido usado:</strong> {referral_code}</li>
                    </ul>
                </body>
                </html>
                """
                
                # Enviar email en segundo plano (no bloquea)
                def send_email_background():
                    try:
                        send_admin_email("Nuevo registro en Codex Trader", html_content)
                    except Exception as e:
                        print(f"WARNING: Error al enviar email en background: {e}")
                
                email_thread = threading.Thread(target=send_email_background, daemon=True)
                email_thread.start()
            except Exception as email_error:
                # No es crítico si falla el email
                print(f"WARNING: No se pudo enviar email de notificación de registro: {email_error}")
            
            # Retornar respuesta inmediatamente sin esperar emails
            return {
                "success": True,
                "message": f"Referido procesado correctamente. Fuiste referido por {referrer_response.data[0].get('email', 'usuario')}. ¡Recibiste {welcome_bonus:,} tokens de bienvenida!",
                "referrer_id": referrer_id,
                "welcome_bonus": welcome_bonus
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar el perfil con el referido"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar referido: {str(e)}"
        )


@users_router.get("/referrals/info")
async def get_referral_info(user = Depends(get_user)):
    """
    Obtiene información sobre el sistema de referidos del usuario actual.
    
    Retorna:
    - referral_code: Código de referido del usuario
    - referred_by_user_id: ID del usuario que lo invitó (si aplica)
    - referral_rewards_count: Cantidad de referidos que han generado recompensa
    - referral_tokens_earned: Tokens totales obtenidos por referidos
    """
    try:
        user_id = user.id
        
        profile_response = supabase_client.table("profiles").select(
            "referral_code, referred_by_user_id, referral_rewards_count, referral_tokens_earned"
        ).eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        profile = profile_response.data[0]
        
        return {
            "referral_code": profile.get("referral_code"),
            "referred_by_user_id": profile.get("referred_by_user_id"),
            "referral_rewards_count": profile.get("referral_rewards_count", 0),
            "referral_tokens_earned": profile.get("referral_tokens_earned", 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener información de referidos: {str(e)}"
        )

