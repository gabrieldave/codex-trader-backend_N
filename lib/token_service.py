"""
Servicio para gestión de tokens: verificación de saldo, descuento y uso justo.
"""
import os
import json
import threading
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import HTTPException

from lib.dependencies import supabase_client
from lib.model_usage import log_model_usage_from_response

logger = logging.getLogger(__name__)


class TokenService:
    """Servicio para gestionar tokens de usuarios."""
    
    def __init__(self):
        self.supabase = supabase_client
    
    def verify_token_balance(self, user_id: str) -> int:
        """
        Verifica el saldo de tokens del usuario.
        
        Args:
            user_id: ID del usuario
            
        Returns:
            tokens_restantes: Cantidad de tokens disponibles
            
        Raises:
            HTTPException: Si el perfil no existe o los tokens están agotados
        """
        profile_response = self.supabase.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_restantes = profile_response.data[0]["tokens_restantes"]
        
        if tokens_restantes <= 0:
            # Enviar email al usuario cuando los tokens se agoten (solo una vez)
            self._send_tokens_exhausted_email(user_id)
            
            raise HTTPException(
                status_code=402,
                detail="Tokens agotados. Por favor, recarga."
            )
        
        return tokens_restantes
    
    def _send_tokens_exhausted_email(self, user_id: str):
        """Envía email al usuario cuando los tokens se agotan (solo una vez)."""
        try:
            from lib.email import send_email
            
            # Verificar si ya se envió el email de tokens agotados
            profile_check = self.supabase.table("profiles").select("email, tokens_exhausted_email_sent").eq("id", user_id).execute()
            user_email = profile_check.data[0].get("email") if profile_check.data else None
            email_already_sent = profile_check.data[0].get("tokens_exhausted_email_sent", False) if profile_check.data else False
            
            if user_email and not email_already_sent:
                def send_tokens_exhausted_email():
                    try:
                        user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                        frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                        billing_url = f"{frontend_url.rstrip('/')}/billing"
                        
                        user_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h1 style="color: white; margin: 0; font-size: 28px;">⚠️ Tus Tokens se Han Agotado</h1>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Hola <strong>{user_name}</strong>,
                                </p>
                                
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Te informamos que tus tokens se han agotado. Para continuar usando Codex Trader, necesitas recargar tokens.
                                </p>
                                
                                <div style="background: #fee2e2; padding: 20px; border-radius: 8px; border-left: 4px solid #ef4444; margin: 20px 0;">
                                    <p style="margin: 0; color: #991b1b; font-weight: bold; font-size: 18px;">
                                        Tokens restantes: 0
                                    </p>
                                </div>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                    <h3 style="color: #059669; margin-top: 0; font-size: 18px;">💡 Opciones para continuar:</h3>
                                    <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                                        <li style="margin-bottom: 10px;">Recargar tokens desde tu panel de cuenta</li>
                                        <li style="margin-bottom: 10px;">Actualizar a un plan con más tokens mensuales</li>
                                        <li style="margin-bottom: 0;">Contactarnos si necesitas ayuda</li>
                                    </ul>
                                </div>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{billing_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                        💰 Recargar Tokens
                                    </a>
                                </div>
                                
                                <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                    Si tienes alguna pregunta, no dudes en contactarnos respondiendo a este correo.
                                </p>
                            </div>
                        </body>
                        </html>
                        """
                        send_email(
                            to=user_email,
                            subject="⚠️ Tus tokens se han agotado - Codex Trader",
                            html=user_html
                        )
                        
                        # Marcar que el email fue enviado
                        self.supabase.table("profiles").update({
                            "tokens_exhausted_email_sent": True
                        }).eq("id", user_id).execute()
                        
                        logger.info(f"✅ Email de tokens agotados enviado a {user_email}")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al enviar email de tokens agotados: {e}")
                
                email_thread = threading.Thread(target=send_tokens_exhausted_email, daemon=True)
                email_thread.start()
        except Exception as email_error:
            logger.warning(f"⚠️ Error al preparar email de tokens agotados: {email_error}")
    
    def deduct_tokens(
        self,
        user_id: str,
        tokens_used: int,
        tokens_restantes: int,
        chat_model: str,
        input_tokens: int,
        output_tokens: int,
        query_preview: str,
        response_mode: str
    ) -> int:
        """
        Descuenta tokens del usuario y maneja la lógica de uso justo.
        
        Args:
            user_id: ID del usuario
            tokens_used: Tokens totales usados
            tokens_restantes: Tokens restantes antes del descuento
            chat_model: Modelo de IA usado
            input_tokens: Tokens de entrada
            output_tokens: Tokens de salida
            query_preview: Vista previa de la consulta
            response_mode: Modo de respuesta (fast/deep)
            
        Returns:
            nuevos_tokens: Tokens restantes después del descuento
        """
        nuevos_tokens = tokens_restantes - tokens_used
        
        # Registrar uso del modelo (no crítico si falla)
        try:
            log_model_usage_from_response(
                user_id=str(user_id),
                model=chat_model,
                tokens_input=input_tokens,
                tokens_output=output_tokens
            )
        except Exception as usage_error:
            logger.warning(f"[BG] Error al registrar uso de modelo: {usage_error}")
        
        # Guardar log en archivo local
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "user_id": str(user_id),
                "model": chat_model,
                "query_preview": (query_preview[:50] + "...") if len(query_preview) > 50 else query_preview,
                "response_mode": response_mode,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": tokens_used,
                "tokens_antes": tokens_restantes,
                "tokens_despues": nuevos_tokens
            }
            log_file = "tokens_log.json"
            log_data = []
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r", encoding="utf-8") as f:
                        log_data = json.load(f)
                except Exception:
                    log_data = []
            log_data.append(log_entry)
            if len(log_data) > 100:
                log_data = log_data[-100:]
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[BG] ⚠ No se pudo guardar log de tokens: {e}")
        
        # Preparar datos de actualización
        update_data = {
            "tokens_restantes": nuevos_tokens
        }
        
        # Lógica de uso justo (fair use)
        try:
            profile_fair_use = self.supabase.table("profiles").select(
                "tokens_monthly_limit, fair_use_warning_shown, fair_use_discount_eligible, fair_use_discount_used, fair_use_email_sent, current_plan, email"
            ).eq("id", user_id).execute()
            
            if profile_fair_use.data:
                profile = profile_fair_use.data[0]
                tokens_monthly_limit = profile.get("tokens_monthly_limit") or 0
                
                if tokens_monthly_limit > 0:
                    tokens_usados_total = tokens_monthly_limit - nuevos_tokens
                    usage_percent = (tokens_usados_total / tokens_monthly_limit) * 100
                    
                    # Aviso al 80% de uso
                    if usage_percent >= 80 and not profile.get("fair_use_warning_shown", False):
                        update_data["fair_use_warning_shown"] = True
                        logger.info(f"[BG] WARNING: Usuario {user_id} alcanzó 80% de uso ({usage_percent:.1f}%)")
                        self._send_80_percent_alert(user_id, user_email=profile.get("email"), current_plan=profile.get("current_plan"), tokens_monthly_limit=tokens_monthly_limit, nuevos_tokens=nuevos_tokens, usage_percent=usage_percent)
                    
                    # Elegibilidad para descuento al 90% de uso
                    if usage_percent >= 90 and not profile.get("fair_use_discount_eligible", False):
                        update_data["fair_use_discount_eligible"] = True
                        update_data["fair_use_discount_eligible_at"] = datetime.utcnow().isoformat()
                        logger.info(f"[BG] Usuario {user_id} alcanzó 90% de uso ({usage_percent:.1f}%) - Elegible para descuento del 20%")
                        
                        if not profile.get("fair_use_email_sent", False):
                            self._send_90_percent_alert(user_id, profile_fair_use.data[0], nuevos_tokens, tokens_monthly_limit, usage_percent)
        except Exception as e:
            error_str = str(e)
            if "42703" not in error_str and "PGRST205" not in error_str and "does not exist" not in error_str.lower():
                logger.warning(f"[BG] Columnas de uso justo no disponibles: {e}")
        
        # Actualizar tokens en la base de datos
        try:
            self.supabase.table("profiles").update(update_data).eq("id", user_id).execute()
            logger.info(f"[BG] Tokens descontados: {tokens_used}")
            logger.info(f"[BG] Tokens restantes después: {nuevos_tokens}")
        except Exception as e:
            logger.error(f"[BG] ERROR al actualizar tokens: {e}")
        
        return nuevos_tokens
    
    def _send_80_percent_alert(self, user_id: str, user_email: Optional[str], current_plan: Optional[str], tokens_monthly_limit: int, nuevos_tokens: int, usage_percent: float):
        """Envía alerta al admin cuando un usuario alcanza el 80% de uso."""
        try:
            from lib.email import send_admin_email
            
            def send_admin_80_percent_email():
                try:
                    admin_html = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                            <h2 style="color: white; margin: 0; font-size: 24px;">⚠️ Alerta: Usuario alcanzó 80% de límite</h2>
                        </div>
                        
                        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                            <p style="font-size: 16px; margin-bottom: 20px;">
                                Un usuario ha alcanzado el <strong>80% de su límite mensual de tokens</strong>.
                            </p>
                            
                            <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                                <ul style="list-style: none; padding: 0; margin: 0;">
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #92400e;">Email del usuario:</strong> 
                                        <span style="color: #333;">{user_email or 'N/A'}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #92400e;">ID de usuario:</strong> 
                                        <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #92400e;">Plan actual:</strong> 
                                        <span style="color: #333;">{current_plan or 'N/A'}</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #92400e;">Límite mensual:</strong> 
                                        <span style="color: #333;">{tokens_monthly_limit:,} tokens</span>
                                    </li>
                                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                        <strong style="color: #92400e;">Tokens restantes:</strong> 
                                        <span style="color: #333;">{nuevos_tokens:,} tokens</span>
                                    </li>
                                    <li style="margin-bottom: 0;">
                                        <strong style="color: #92400e;">Porcentaje usado:</strong> 
                                        <span style="color: #d97706; font-weight: bold; font-size: 18px;">{usage_percent:.1f}%</span>
                                    </li>
                                </ul>
                            </div>
                            
                            <p style="font-size: 14px; color: #666; margin-top: 20px;">
                                <strong>Nota:</strong> El usuario recibirá un aviso suave. Si alcanza el 90%, será elegible para un descuento del 20%.
                            </p>
                            
                            <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                            </p>
                        </div>
                    </body>
                    </html>
                    """
                    send_admin_email("⚠️ Alerta: Usuario alcanzó 80% de límite de tokens", admin_html)
                except Exception as e:
                    logger.warning(f"[BG] ⚠️ Error al enviar email al admin por 80% de uso: {e}")
            
            admin_thread = threading.Thread(target=send_admin_80_percent_email, daemon=True)
            admin_thread.start()
        except Exception as e:
            logger.warning(f"[BG] ⚠️ Error al preparar email al admin por 80% de uso: {e}")
    
    def _send_90_percent_alert(self, user_id: str, profile: Dict[str, Any], nuevos_tokens: int, tokens_monthly_limit: int, usage_percent: float):
        """Envía alerta al usuario y admin cuando alcanza el 90% de uso."""
        try:
            user_email = profile.get("email")
            if not user_email:
                return
            
            plan_name = "tu plan actual"
            current_plan_code_for_email = profile.get("current_plan")
            if current_plan_code_for_email:
                from plans import get_plan_by_code
                plan_info = get_plan_by_code(current_plan_code_for_email)
                if plan_info:
                    plan_name = plan_info.name
            
            plan_code_for_thread = current_plan_code_for_email
            plan_name_for_thread = plan_name
            
            def send_90_percent_email_background():
                try:
                    from lib.email import send_email, send_admin_email
                    from plans import get_plan_by_code, CODEX_PLANS
                    
                    frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                    planes_url = f"{frontend_url.rstrip('/')}/planes"
                    
                    suggested_plan_code = "trader"
                    if plan_code_for_thread:
                        current_plan_index = next((i for i, p in enumerate(CODEX_PLANS) if p.code == plan_code_for_thread), -1)
                        if current_plan_index >= 0 and current_plan_index < len(CODEX_PLANS) - 1:
                            suggested_plan_code = CODEX_PLANS[current_plan_index + 1].code
                    
                    suggested_plan = get_plan_by_code(suggested_plan_code)
                    
                    # Email al usuario
                    email_html = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 12px;">
                            <h1 style="color: white; margin: 0;">🚨 Alerta de Uso</h1>
                        </div>
                        <div style="background: white; padding: 30px; border-radius: 8px; margin-top: 20px;">
                            <p>Has alcanzado el <strong>90% de tu límite</strong> en tu plan <strong>{plan_name_for_thread}</strong>.</p>
                            <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                <p><strong>📊 Tu uso actual:</strong></p>
                                <p>Tokens restantes: <strong>{nuevos_tokens:,}</strong> de <strong>{tokens_monthly_limit:,}</strong></p>
                                <p>Porcentaje usado: <strong>{usage_percent:.1f}%</strong></p>
                            </div>
                            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 25px; border-radius: 10px; text-align: center; margin: 25px 0;">
                                <h2 style="margin: 0 0 10px 0;">🎁 ¡Descuento Especial del 20%!</h2>
                                <p>Te ofrecemos un <strong>20% de descuento</strong> para actualizar tu plan.</p>
                                <div style="background: white; color: #f5576c; padding: 15px 30px; border-radius: 8px; font-size: 24px; font-weight: bold; margin: 15px 0; display: inline-block;">CUPON20</div>
                            </div>
                            <div style="text-align: center; margin: 30px 0;">
                                <a href="{planes_url}" style="display: inline-block; background: #667eea; color: white; padding: 15px 40px; text-decoration: none; border-radius: 8px; font-weight: bold;">Ver Planes y Aprovechar Descuento</a>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    send_email(
                        to=user_email,
                        subject="🚨 Has alcanzado el 90% de tu límite - Descuento del 20% disponible",
                        html=email_html
                    )
                    
                    self.supabase.table("profiles").update({
                        "fair_use_email_sent": True
                    }).eq("id", user_id).execute()
                    
                    logger.info(f"[BG] ✅ Email de alerta al 90% enviado a {user_email}")
                    
                    # Email al admin
                    admin_html_90 = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                            <h2 style="color: white; margin: 0; font-size: 24px;">🚨 ALERTA CRÍTICA: Usuario alcanzó 90% de límite</h2>
                        </div>
                        
                        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                            <p>Un usuario ha alcanzado el <strong>90% de su límite mensual de tokens</strong>.</p>
                            <div style="background: #fee2e2; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                <p><strong>Email:</strong> {user_email}</p>
                                <p><strong>ID:</strong> {user_id}</p>
                                <p><strong>Plan:</strong> {plan_name_for_thread}</p>
                                <p><strong>Uso:</strong> {usage_percent:.1f}%</p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    send_admin_email("🚨 ALERTA CRÍTICA: Usuario alcanzó 90% de límite de tokens", admin_html_90)
                    logger.info(f"[BG] ✅ Email al admin enviado por 90% de uso de usuario {user_id}")
                except Exception as e:
                    logger.warning(f"[BG] ⚠️ Error al enviar email de alerta al 90%: {e}")
            
            email_thread = threading.Thread(target=send_90_percent_email_background, daemon=True)
            email_thread.start()
        except Exception as e:
            logger.warning(f"[BG] ⚠️ Error al preparar envío de email al 90%: {e}")


# Instancia global del servicio
token_service = TokenService()

