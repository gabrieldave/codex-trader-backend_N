"""
Router para endpoints de billing y Stripe.
"""
import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
import threading

from lib.dependencies import get_user, supabase_client
from lib.config_shared import STRIPE_AVAILABLE, FRONTEND_URL
from routers.models import CheckoutSessionInput

# Importar stripe y funciones de configuración
try:
    from lib.stripe_config import (
        get_stripe_price_id,
        is_valid_plan_code,
        get_plan_code_from_price_id,
        STRIPE_WEBHOOK_SECRET,
        STRIPE_FAIR_USE_COUPON_ID
    )
    import stripe
except ImportError:
    stripe = None
    get_stripe_price_id = None
    is_valid_plan_code = None
    get_plan_code_from_price_id = None
    STRIPE_WEBHOOK_SECRET = None
    STRIPE_FAIR_USE_COUPON_ID = None

logger = logging.getLogger(__name__)

# Crear router
billing_router = APIRouter(tags=["billing"])


@billing_router.post("/billing/create-checkout-session")
async def create_checkout_session(
    checkout_input: CheckoutSessionInput,
    request: Request,
    user = Depends(get_user)
):
    """
    Crea una sesión de checkout de Stripe para suscripciones.
    
    Recibe:
    - planCode: Código del plan ('explorer', 'trader', 'pro', 'institucional')
    
    Retorna:
    - url: URL de la sesión de checkout de Stripe para redirigir al usuario
    """
    logger.info(f"🔔 Creando checkout session - Método: {request.method}, Plan: {checkout_input.planCode}, Usuario: {user.email}")
    
    if not STRIPE_AVAILABLE or not stripe:
        raise HTTPException(
            status_code=503,
            detail="Stripe no está configurado. Verifica las variables de entorno STRIPE_SECRET_KEY y los Price IDs."
        )
    
    try:
        # URL del frontend (usar la variable global ya configurada)
        frontend_base_url = (FRONTEND_URL or os.getenv("FRONTEND_URL", "https://www.codextrader.tech")).rstrip('/')
        # Eliminar explícitamente /app si está al final
        if frontend_base_url.endswith('/app'):
            frontend_base_url = frontend_base_url[:-4]
        frontend_base_url = frontend_base_url.rstrip('/')
        
        # Normalizar: si la URL no tiene www pero el dominio es codextrader.tech, añadir www
        if 'codextrader.tech' in frontend_base_url and 'www.' not in frontend_base_url:
            frontend_base_url = frontend_base_url.replace('https://codextrader.tech', 'https://www.codextrader.tech')
            frontend_base_url = frontend_base_url.replace('http://codextrader.tech', 'http://www.codextrader.tech')
        
        logger.info(f"🌐 FRONTEND_URL configurada: {FRONTEND_URL}, frontend_base_url procesada: {frontend_base_url}")
        
        plan_code = checkout_input.planCode.lower()
        
        # Validar que el código de plan sea válido
        if not is_valid_plan_code or not is_valid_plan_code(plan_code):
            raise HTTPException(
                status_code=400,
                detail=f"Código de plan inválido: {plan_code}. Debe ser uno de: explorer, trader, pro, institucional"
            )
        
        # Obtener el Price ID de Stripe para el plan
        price_id = get_stripe_price_id(plan_code) if get_stripe_price_id else None
        if not price_id:
            raise HTTPException(
                status_code=500,
                detail=f"Price ID no configurado para el plan: {plan_code}. Verifica STRIPE_PRICE_ID_{plan_code.upper()} en .env"
            )
        
        # Obtener userId y email del usuario autenticado
        user_id = user.id
        user_email = user.email
        
        # IMPORTANTE: Verificar elegibilidad para descuento de uso justo (Fair Use)
        discounts = None
        if STRIPE_FAIR_USE_COUPON_ID:
            try:
                profile_response = supabase_client.table("profiles").select(
                    "fair_use_discount_eligible, fair_use_discount_used"
                ).eq("id", user_id).execute()
                
                if profile_response.data:
                    profile = profile_response.data[0]
                    fair_use_eligible = profile.get("fair_use_discount_eligible", False)
                    fair_use_used = profile.get("fair_use_discount_used", False)
                    
                    # Aplicar cupón si es elegible y aún no lo ha usado
                    if fair_use_eligible and not fair_use_used:
                        discounts = [{"coupon": STRIPE_FAIR_USE_COUPON_ID}]
                        logger.info(f"✅ Aplicando cupón de uso justo (20% OFF) para usuario {user_id}")
            except Exception as e:
                error_msg = str(e)
                if "does not exist" in error_msg or "42703" in error_msg:
                    logger.warning(f"⚠️ Columnas de fair use no disponibles, omitiendo descuento: {error_msg[:100]}")
                else:
                    logger.warning(f"⚠️ Error al verificar elegibilidad de fair use: {error_msg[:100]}")
        
        metadata = {
            "user_id": user_id,
            "user_email": user_email,
            "plan_code": plan_code
        }
        
        # Si se aplicó descuento, agregarlo a metadata para tracking
        if discounts:
            metadata["fair_use_discount_applied"] = "true"
            try:
                supabase_client.table("profiles").update({
                    "fair_use_discount_used": True
                }).eq("id", user_id).execute()
                logger.info(f"✅ Descuento de uso justo marcado como usado para usuario {user_id}")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo marcar descuento como usado (no crítico): {e}")
        
        # Asegurar que la URL de éxito apunte a la raíz (/) y no a /app
        success_url = f"{frontend_base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_base_url}/?checkout=cancelled"
        
        logger.info(f"🔗 URLs de checkout configuradas - Success: {success_url}, Cancel: {cancel_url}")
        
        # Crear la sesión de checkout de Stripe
        checkout_session_params = {
            "mode": "subscription",
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": metadata,
            "customer_email": user_email,
        }
        
        # Agregar descuentos solo si el usuario es elegible
        if discounts:
            checkout_session_params["discounts"] = discounts
        
        session = stripe.checkout.Session.create(**checkout_session_params)
        
        return {"url": session.url}
        
    except HTTPException:
        raise
    except Exception as e:
        error_type = type(e).__name__
        if 'Stripe' in error_type or 'stripe' in str(type(e)).lower():
            raise HTTPException(
                status_code=500,
                detail=f"Error de Stripe: {str(e)}"
            )
        raise HTTPException(
            status_code=500,
            detail=f"Error al crear sesión de checkout: {str(e)}"
        )


@billing_router.post("/billing/stripe-webhook")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint para recibir webhooks de Stripe.
    IMPORTANTE: Este endpoint NO requiere autenticación normal, Stripe lo firma con webhook_secret
    """
    logger.info("🔔 Webhook endpoint llamado")
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        # Verificar que el webhook secret esté configurado
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET") or STRIPE_WEBHOOK_SECRET
        if not webhook_secret:
            logger.error("❌ STRIPE_WEBHOOK_SECRET no está configurado")
            return JSONResponse(
                content={"status": "error", "message": "Webhook secret no configurado"},
                status_code=500
            )
        
        logger.info(f"🔐 Verificando firma del webhook...")
        
        # Verifica webhook
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        
        logger.info(f"✅ Webhook recibido y verificado: {event['type']}")
        
        # IMPORTANTE: Procesar eventos en background para responder rápidamente a Stripe
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            logger.info(f"🛒 Procesando checkout.session.completed para sesión: {session.get('id')} (en background)")
            background_tasks.add_task(handle_checkout_session_completed, session)
        elif event["type"] == "invoice.paid":
            invoice = event["data"]["object"]
            logger.info(f"💰 Procesando invoice.paid para invoice: {invoice.get('id')} (en background)")
            background_tasks.add_task(handle_invoice_paid, invoice)
        
        # Responder inmediatamente a Stripe (no esperar el procesamiento)
        return {"status": "success"}
        
    except Exception as e:
        error_type = type(e).__name__
        error_str = str(e).lower()
        if hasattr(stripe, 'error') and hasattr(stripe.error, 'SignatureVerificationError'):
            if isinstance(e, stripe.error.SignatureVerificationError):
                logger.error(f"❌ Error de firma webhook: {e}")
                return JSONResponse(
                    content={"status": "invalid_signature"},
                    status_code=400
                )
        elif 'SignatureVerificationError' in error_type or ('signature' in error_str and 'webhook' in error_str):
            logger.error(f"❌ Error de firma webhook: {e}")
            return JSONResponse(
                content={"status": "invalid_signature"},
                status_code=400
            )
        
        logger.error(f"❌ Error webhook: {e}")
        return JSONResponse(
            content={"status": "error", "message": str(e)},
            status_code=500
        )


async def handle_checkout_session_completed(session: dict):
    """
    Maneja el evento checkout.session.completed de Stripe.
    
    Actualiza en la base de datos:
    - stripe_customer_id: ID del cliente en Stripe
    - current_plan: Plan seleccionado desde metadata
    - current_period_end: Fecha de expiración de la suscripción
    - tokens_restantes: Tokens sumados del plan
    """
    try:
        # Extraer información de la sesión
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        metadata = session.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_code = metadata.get("plan_code")
        
        if not user_id:
            print(f"⚠️ checkout.session.completed sin user_id en metadata: {session.get('id')}")
            return
        
        if not customer_id:
            print(f"⚠️ checkout.session.completed sin customer_id: {session.get('id')}")
            return
        
        # Obtener información de la suscripción para current_period_end
        current_period_end = None
        if subscription_id:
            try:
                subscription = stripe.Subscription.retrieve(subscription_id)
                current_period_end = subscription.current_period_end
            except Exception as e:
                print(f"⚠️ Error al obtener suscripción {subscription_id}: {str(e)}")
        
        # Obtener información del plan para establecer tokens iniciales
        tokens_per_month = None
        plan = None
        if plan_code:
            from plans import get_plan_by_code
            plan = get_plan_by_code(plan_code)
            if plan:
                tokens_per_month = plan.tokens_per_month
                logger.info(f"✅ Plan encontrado: {plan_code} -> {tokens_per_month:,} tokens/mes")
            else:
                logger.error(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado en plans.py")
                print(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado. Los tokens NO se sumarán.")
        else:
            logger.error(f"❌ ERROR CRÍTICO: plan_code no está en metadata del checkout session")
            print(f"❌ ERROR CRÍTICO: plan_code no está en metadata. Session ID: {session.get('id')}")
            print(f"   Metadata disponible: {metadata}")
        
        # Preparar datos para actualizar
        update_data = {
            "stripe_customer_id": customer_id,
        }
        
        if plan_code:
            update_data["current_plan"] = plan_code
            # Obtener tokens actuales del usuario para sumar en lugar de resetear
            try:
                profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
                current_tokens = 0
                if profile_response.data and profile_response.data[0].get("tokens_restantes") is not None:
                    current_tokens = profile_response.data[0]["tokens_restantes"]
                
                # Sumar tokens del nuevo plan a los tokens existentes
                if tokens_per_month:
                    new_tokens = current_tokens + tokens_per_month
                    update_data["tokens_restantes"] = new_tokens
                    logger.info(f"💰 Tokens sumados para usuario {user_id}: {current_tokens:,} + {tokens_per_month:,} = {new_tokens:,}")
                    print(f"💰 Tokens sumados para usuario {user_id}: {current_tokens:,} + {tokens_per_month:,} = {new_tokens:,}")
                    
                    # Actualizar tokens_monthly_limit con el máximo entre el límite actual y el nuevo plan
                    try:
                        current_limit = profile_response.data[0].get("tokens_monthly_limit", 0) if profile_response.data else 0
                        update_data["tokens_monthly_limit"] = max(current_limit, tokens_per_month)
                    except Exception as e:
                        logger.warning(f"No se pudo actualizar tokens_monthly_limit (columna puede no existir): {e}")
                    
                    # Resetear campos de uso justo solo si es la primera suscripción
                    if current_tokens == 0:
                        update_data["fair_use_warning_shown"] = False
                        update_data["fair_use_discount_eligible"] = False
                        update_data["fair_use_discount_used"] = False
                        update_data["fair_use_discount_eligible_at"] = None
                        update_data["fair_use_email_sent"] = False
                else:
                    logger.error(f"❌ ERROR CRÍTICO: tokens_per_month es None para plan_code '{plan_code}'. Los tokens NO se sumarán.")
                    print(f"❌ ERROR CRÍTICO: tokens_per_month es None. Los tokens NO se actualizarán.")
            except Exception as e:
                logger.error(f"Error al obtener tokens actuales, usando tokens del plan directamente: {e}")
                print(f"⚠️ Error al obtener tokens actuales: {e}")
                # Fallback: usar tokens del plan si hay error
                if tokens_per_month:
                    update_data["tokens_restantes"] = tokens_per_month
                    logger.info(f"💰 Fallback: Tokens establecidos a {tokens_per_month:,} (sin sumar)")
                else:
                    logger.error(f"❌ ERROR: No se pueden establecer tokens porque tokens_per_month es None")
                    print(f"❌ ERROR: No se pueden establecer tokens porque tokens_per_month es None")
        
        # IMPORTANTE: Si el usuario usó el descuento de uso justo, marcarlo
        if metadata.get("fair_use_discount_applied") == "true":
            profile_check = supabase_client.table("profiles").select(
                "fair_use_discount_eligible"
            ).eq("id", user_id).execute()
            
            if profile_check.data and profile_check.data[0].get("fair_use_discount_eligible", False):
                update_data["fair_use_discount_used"] = True
                print(f"✅ Descuento de uso justo marcado como usado para usuario {user_id}")
        
        if current_period_end:
            update_data["current_period_end"] = datetime.fromtimestamp(current_period_end).isoformat()
        
        # Actualizar el perfil del usuario
        logger.info(f"📝 Actualizando perfil con datos: {update_data}")
        print(f"📝 Actualizando perfil con: plan={plan_code}, tokens_restantes={'sumados' if 'tokens_restantes' in update_data else 'NO incluidos'}")
        
        update_response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
        
        if update_response.data:
            # Verificar que tokens_restantes se actualizó correctamente
            updated_profile = update_response.data[0]
            updated_tokens = updated_profile.get("tokens_restantes")
            
            if "tokens_restantes" in update_data:
                expected_tokens = update_data["tokens_restantes"]
                if updated_tokens == expected_tokens:
                    logger.info(f"✅ Perfil actualizado correctamente para usuario {user_id}: plan={plan_code}, tokens={updated_tokens:,}")
                    print(f"✅ Perfil actualizado: plan={plan_code}, tokens={updated_tokens:,}")
                else:
                    logger.error(f"❌ ERROR: Tokens no coinciden. Esperado: {expected_tokens:,}, Actual: {updated_tokens}")
                    print(f"❌ ERROR: Tokens no coinciden. Esperado: {expected_tokens:,}, Actual: {updated_tokens}")
            else:
                logger.warning(f"⚠️ ADVERTENCIA: tokens_restantes no se incluyó en la actualización")
                print(f"⚠️ ADVERTENCIA: tokens_restantes no se actualizó (no estaba en update_data)")
                print(f"✅ Perfil actualizado para usuario {user_id}: plan={plan_code}, customer={customer_id}")
        else:
            logger.error(f"❌ ERROR: update_response.data está vacío. La actualización puede haber fallado.")
            print(f"❌ ERROR: update_response.data está vacío. La actualización puede haber fallado.")
            print(f"   Verifica que el usuario {user_id} existe en la tabla profiles")
        
        # IMPORTANTE: Registrar pago inicial en tabla stripe_payments para análisis de ingresos
        if update_response.data:
            try:
                # Obtener monto desde Stripe
                amount_usd = None
                payment_date = None
                
                if subscription_id:
                    try:
                        subscription = stripe.Subscription.retrieve(subscription_id)
                        if subscription.latest_invoice:
                            invoice_obj = stripe.Invoice.retrieve(subscription.latest_invoice)
                            amount_usd = invoice_obj.amount_paid / 100.0 if invoice_obj.amount_paid else None
                            payment_date = datetime.fromtimestamp(invoice_obj.created).isoformat() if invoice_obj.created else None
                    except Exception as e:
                        print(f"⚠️ Error al obtener invoice desde subscription: {e}")
                
                # Si no se pudo obtener desde subscription, usar precio del plan
                if amount_usd is None and plan_code:
                    from plans import get_plan_by_code
                    plan = get_plan_by_code(plan_code)
                    if plan:
                        amount_usd = plan.price_usd
                        payment_date = datetime.utcnow().isoformat()
                
                # Insertar en tabla de pagos si tenemos los datos
                if amount_usd is not None:
                    payment_data = {
                        "invoice_id": f"checkout-{session.get('id', 'unknown')}",
                        "customer_id": customer_id,
                        "user_id": user_id,
                        "plan_code": plan_code,
                        "amount_usd": amount_usd,
                        "currency": "usd",
                        "payment_date": payment_date or datetime.utcnow().isoformat()
                    }
                    
                    try:
                        payment_response = supabase_client.table("stripe_payments").insert(payment_data).execute()
                        if payment_response.data:
                            print(f"✅ Pago inicial registrado: ${amount_usd:.2f} USD para usuario {user_id} (plan: {plan_code})")
                    except Exception as insert_error:
                        print(f"⚠️ Pago ya registrado o error al insertar: {insert_error}")
            except Exception as payment_error:
                print(f"⚠️ Error al registrar pago inicial (no crítico): {payment_error}")
            
            # IMPORTANTE: Enviar email al admin cuando hay una primera compra
            try:
                from lib.email import send_admin_email
                import threading
                
                # Obtener información del usuario y plan
                user_info_response = supabase_client.table("profiles").select("email").eq("id", user_id).execute()
                user_email = user_info_response.data[0].get("email") if user_info_response.data else "N/A"
                
                plan_name = plan_code
                plan_price = None
                if plan_code:
                    from plans import get_plan_by_code
                    plan_info = get_plan_by_code(plan_code)
                    if plan_info:
                        plan_name = plan_info.name
                        plan_price = plan_info.price_usd
                
                # Obtener monto desde Stripe si está disponible
                amount_usd = plan_price
                if subscription_id:
                    try:
                        subscription = stripe.Subscription.retrieve(subscription_id)
                        if subscription.latest_invoice:
                            invoice_obj = stripe.Invoice.retrieve(subscription.latest_invoice)
                            if invoice_obj.amount_paid:
                                amount_usd = invoice_obj.amount_paid / 100.0
                    except Exception as e:
                        logger.warning(f"No se pudo obtener monto desde Stripe, usando precio del plan: {e}")
                
                if amount_usd is None:
                    amount_usd = plan_price or 0.0
                
                def send_admin_checkout_email():
                    try:
                        admin_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h2 style="color: white; margin: 0; font-size: 24px;">🎉 Nueva Compra - Checkout Completado</h2>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Un usuario ha completado el checkout y activado su suscripción en Codex Trader.
                                </p>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Email del usuario:</strong> 
                                            <span style="color: #333;">{user_email}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">ID de usuario:</strong> 
                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Plan adquirido:</strong> 
                                            <span style="color: #333; font-weight: bold;">{plan_name} ({plan_code})</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Tokens asignados:</strong> 
                                            <span style="color: #333;">{tokens_per_month:,} tokens</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Customer ID (Stripe):</strong> 
                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{customer_id}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Subscription ID (Stripe):</strong> 
                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{subscription_id or 'N/A'}</span>
                                        </li>
                                        <li style="margin-bottom: 0;">
                                            <strong style="color: #059669;">Monto pagado:</strong> 
                                            <span style="color: #10b981; font-weight: bold; font-size: 18px;">${amount_usd:.2f} USD</span>
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
                        send_admin_email("🎉 Nueva Compra - Checkout Completado - Codex Trader", admin_html)
                    except Exception as e:
                        print(f"⚠️ Error al enviar email al admin por checkout completado: {e}")
                
                # IMPORTANTE: También enviar email al usuario confirmando su compra
                def send_user_checkout_email():
                    try:
                        from lib.email import send_email
                        
                        # Obtener información del plan
                        plan_name = plan_code
                        plan_price = None
                        if plan_code:
                            from plans import get_plan_by_code
                            plan_info = get_plan_by_code(plan_code)
                            if plan_info:
                                plan_name = plan_info.name
                                plan_price = plan_info.price_usd
                        
                        # Obtener fecha de renovación
                        next_renewal_str = "N/A"
                        if current_period_end:
                            next_renewal = datetime.fromtimestamp(current_period_end)
                            next_renewal_str = next_renewal.strftime('%d/%m/%Y')
                        
                        # Construir URL del frontend
                        frontend_url = FRONTEND_URL or os.getenv("FRONTEND_URL", "https://www.codextrader.tech")
                        frontend_url = frontend_url.strip('"').strip("'").strip()
                        app_url = frontend_url.rstrip('/')
                        
                        user_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                            <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                <h1 style="color: white; margin: 0; font-size: 28px;">¡Pago Exitoso! 🎉</h1>
                            </div>
                            
                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    Hola <strong>{user_email}</strong>,
                                </p>
                                
                                <p style="font-size: 16px; margin-bottom: 20px;">
                                    ¡Gracias por tu compra! Tu suscripción a <strong>{plan_name}</strong> ha sido activada exitosamente.
                                </p>
                                
                                <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                    <h3 style="color: #059669; margin-top: 0;">Detalles de tu suscripción:</h3>
                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Plan:</strong> 
                                            <span style="color: #333; font-weight: bold;">{plan_name}</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Tokens recibidos:</strong> 
                                            <span style="color: #10b981; font-weight: bold; font-size: 18px;">{tokens_per_month:,} tokens</span>
                                        </li>
                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                            <strong style="color: #059669;">Monto pagado:</strong> 
                                            <span style="color: #333; font-weight: bold;">${plan_price:.2f} USD</span>
                                        </li>
                                        <li style="margin-bottom: 0;">
                                            <strong style="color: #059669;">Próxima renovación:</strong> 
                                            <span style="color: #333;">{next_renewal_str}</span>
                                        </li>
                                    </ul>
                                </div>
                                
                                <div style="text-align: center; margin: 30px 0;">
                                    <a href="{app_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                        🚀 Empezar a usar Codex Trader
                                    </a>
                                </div>
                                
                                <p style="font-size: 14px; color: #666; margin-top: 30px;">
                                    <strong>¿Qué puedes hacer ahora?</strong>
                                </p>
                                <ul style="color: #333; line-height: 1.8;">
                                    <li>Hacer consultas al asistente de IA especializado en trading</li>
                                    <li>Acceder a tu biblioteca profesional de contenido</li>
                                    <li>Ver tu uso de tokens en el panel de cuenta</li>
                                </ul>
                                
                                <p style="font-size: 12px; color: #666; margin-top: 30px; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                                    Si no reconoces este pago, contáctanos respondiendo a este correo.
                                </p>
                            </div>
                        </body>
                        </html>
                        """
                        send_email(
                            to=user_email,
                            subject=f"¡Pago exitoso! Tu plan {plan_name} está activo - Codex Trader",
                            html=user_html
                        )
                        logger.info(f"✅ Email de confirmación de compra enviado a {user_email}")
                    except Exception as e:
                        logger.error(f"❌ Error al enviar email al usuario por checkout completado: {e}")
                        print(f"⚠️ Error al enviar email al usuario por checkout completado: {e}")
                
                # Enviar emails en background (no bloquea)
                admin_thread = threading.Thread(target=send_admin_checkout_email, daemon=True)
                admin_thread.start()
                
                user_thread = threading.Thread(target=send_user_checkout_email, daemon=True)
                user_thread.start()
            except Exception as email_error:
                print(f"⚠️ Error al preparar emails por checkout completado: {email_error}")
                logger.error(f"❌ Error al preparar emails por checkout completado: {email_error}")
        else:
            print(f"⚠️ No se encontró perfil para usuario {user_id}")
            
    except Exception as e:
        print(f"❌ Error en handle_checkout_session_completed: {str(e)}")
        raise


async def handle_invoice_paid(invoice: dict):
    """
    Maneja el evento invoice.paid de Stripe (renovación mensual).
    
    Actualiza en la base de datos:
    - current_plan: Plan determinado desde el price_id de la invoice
    - tokens_restantes: Tokens del mes basados en el plan
    - current_period_end: Fecha de fin del período de facturación
    """
    try:
        # Extraer información de la invoice
        customer_id = invoice.get("customer")
        subscription_id = invoice.get("subscription")
        
        if not customer_id:
            print(f"⚠️ invoice.paid sin customer_id: {invoice.get('id')}")
            return
        
        # Buscar el usuario por stripe_customer_id
        profile_response = supabase_client.table("profiles").select("id, email, current_plan").eq("stripe_customer_id", customer_id).execute()
        
        if not profile_response.data:
            print(f"⚠️ No se encontró usuario con stripe_customer_id: {customer_id}")
            return
        
        user_id = profile_response.data[0]["id"]
        user_email = profile_response.data[0].get("email", "")
        previous_plan = profile_response.data[0].get("current_plan")
        
        # Determinar si es nueva suscripción o renovación
        is_new_subscription = previous_plan is None or previous_plan == ""
        event_type = "nueva suscripción" if is_new_subscription else "renovación"
        
        # Obtener el price_id de la invoice para determinar el plan
        line_items = invoice.get("lines", {}).get("data", [])
        if not line_items:
            print(f"⚠️ invoice.paid sin line_items: {invoice.get('id')}")
            return
        
        # El primer line_item debería tener el price del plan
        price_id = line_items[0].get("price", {}).get("id")
        if not price_id:
            print(f"⚠️ invoice.paid sin price_id en line_items: {invoice.get('id')}")
            return
        
        # Determinar el plan desde el price_id
        plan_code = get_plan_code_from_price_id(price_id) if get_plan_code_from_price_id else None
        if not plan_code:
            print(f"⚠️ No se encontró plan para price_id: {price_id}")
            return
        
        # Obtener información del plan para calcular tokens
        from plans import get_plan_by_code
        plan = get_plan_by_code(plan_code)
        if not plan:
            print(f"⚠️ No se encontró plan con código: {plan_code}")
            return
        
        tokens_per_month = plan.tokens_per_month
        
        # Obtener current_period_end desde la invoice
        period_end = None
        if line_items[0].get("period"):
            period_end_timestamp = line_items[0]["period"].get("end")
            if period_end_timestamp:
                period_end = datetime.fromtimestamp(period_end_timestamp).isoformat()
        
        # IMPORTANTE: Sumar tokens al renovar suscripción (no resetear)
        try:
            profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
            current_tokens = 0
            if profile_response.data and profile_response.data[0].get("tokens_restantes") is not None:
                current_tokens = profile_response.data[0]["tokens_restantes"]
            
            # Sumar tokens del plan a los tokens existentes
            new_tokens = current_tokens + tokens_per_month
            logger.info(f"💰 Renovación: Tokens sumados para usuario {user_id}: {current_tokens} + {tokens_per_month} = {new_tokens}")
        except Exception as e:
            logger.error(f"Error al obtener tokens actuales en renovación, usando tokens del plan: {e}")
            new_tokens = tokens_per_month
        
        update_data = {
            "current_plan": plan_code,
            "tokens_restantes": new_tokens
        }
        
        # Intentar actualizar tokens_monthly_limit solo si la columna existe
        try:
            update_data["tokens_monthly_limit"] = tokens_per_month
            update_data["fair_use_warning_shown"] = False
            update_data["fair_use_discount_eligible"] = False
            update_data["fair_use_discount_used"] = False
            update_data["fair_use_discount_eligible_at"] = None
            update_data["fair_use_email_sent"] = False
        except Exception as e:
            logger.warning(f"No se pudo actualizar campos de uso justo (columnas pueden no existir): {e}")
        
        if period_end:
            update_data["current_period_end"] = period_end
        
        # IMPORTANTE: Lógica de recompensas de referidos
        invoice_id = invoice.get("id")
        process_referral_reward = False
        referred_by_id = None
        
        if invoice_id:
            # Verificar si ya se procesó esta recompensa (idempotencia)
            reward_event_check = supabase_client.table("referral_reward_events").select("id").eq("invoice_id", invoice_id).execute()
            
            if not reward_event_check.data:
                # Esta invoice no ha sido procesada antes, verificar si es primera suscripción
                profile_check = supabase_client.table("profiles").select(
                    "referred_by_user_id, has_generated_referral_reward"
                ).eq("id", user_id).execute()
                
                if profile_check.data:
                    referred_by_id = profile_check.data[0].get("referred_by_user_id")
                    has_generated_reward = profile_check.data[0].get("has_generated_referral_reward", False)
                    
                    # Si fue referido y aún no ha generado recompensa, procesar
                    if referred_by_id and not has_generated_reward:
                        process_referral_reward = True
        
        # Si es el primer pago, marcar que ya generó recompensa
        if process_referral_reward:
            update_data["has_generated_referral_reward"] = True
        
        # Actualizar el perfil del usuario
        update_response = supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
        
        if update_response.data:
            print(f"✅ Suscripción renovada para usuario {user_id}: plan={plan_code}, tokens={tokens_per_month}")
            
            # IMPORTANTE: Registrar pago en tabla stripe_payments
            try:
                amount_total = invoice.get("amount_paid", invoice.get("amount_due", 0))
                amount_usd = amount_total / 100.0
                currency = invoice.get("currency", "usd").upper()
                
                payment_date = None
                if invoice.get("status_transitions", {}).get("paid_at"):
                    payment_date = invoice["status_transitions"]["paid_at"]
                elif invoice.get("created"):
                    payment_date = invoice["created"]
                
                if payment_date and isinstance(payment_date, (int, float)):
                    payment_date = datetime.fromtimestamp(payment_date).isoformat()
                
                payment_data = {
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "user_id": user_id,
                    "plan_code": plan_code,
                    "amount_usd": amount_usd,
                    "currency": currency,
                    "payment_date": payment_date or datetime.utcnow().isoformat()
                }
                
                try:
                    payment_response = supabase_client.table("stripe_payments").insert(payment_data).execute()
                    if payment_response.data:
                        print(f"✅ Pago registrado: ${amount_usd:.2f} USD para usuario {user_id} (plan: {plan_code})")
                except Exception as insert_error:
                    try:
                        supabase_client.table("stripe_payments").update({
                            "amount_usd": amount_usd,
                            "plan_code": plan_code,
                            "payment_date": payment_date or datetime.utcnow().isoformat()
                        }).eq("invoice_id", invoice_id).execute()
                        print(f"✅ Pago actualizado: ${amount_usd:.2f} USD para invoice {invoice_id}")
                    except Exception as update_error:
                        print(f"⚠️ No se pudo registrar/actualizar pago: {update_error}")
            except Exception as payment_error:
                print(f"⚠️ Error al registrar pago (no crítico): {payment_error}")
            
            # Procesar recompensa al que invita (si aplica)
            if process_referral_reward:
                await process_referrer_reward(user_id, referred_by_id, invoice_id)
            
            # IMPORTANTE: Enviar emails de notificación (admin y usuario)
            try:
                from lib.email import send_admin_email, send_email
                import threading
                
                plan_name = plan.name
                amount_total = invoice.get("amount_paid", invoice.get("amount_due", 0))
                amount_usd = amount_total / 100.0
                
                payment_date_str = None
                if invoice.get("status_transitions", {}).get("paid_at"):
                    payment_date_str = datetime.fromtimestamp(invoice["status_transitions"]["paid_at"]).strftime('%Y-%m-%d %H:%M:%S')
                elif invoice.get("created"):
                    payment_date_str = datetime.fromtimestamp(invoice["created"]).strftime('%Y-%m-%d %H:%M:%S')
                else:
                    payment_date_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                
                next_renewal_str = "N/A"
                if period_end:
                    try:
                        if isinstance(period_end, str):
                            if "T" in period_end:
                                dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
                            else:
                                dt = datetime.fromisoformat(period_end)
                        else:
                            dt = period_end
                        next_renewal_str = dt.strftime('%d/%m/%Y')
                    except:
                        next_renewal_str = str(period_end)
                
                def send_admin_email_background():
                    try:
                        admin_html = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                            <h2 style="color: #2563eb;">Nuevo pago en Codex Trader</h2>
                            <p>Se ha procesado un pago de suscripción en Codex Trader.</p>
                            <ul>
                                <li><strong>Email del usuario:</strong> {user_email}</li>
                                <li><strong>ID de usuario:</strong> {user_id}</li>
                                <li><strong>Plan:</strong> {plan_name} ({plan_code})</li>
                                <li><strong>Monto:</strong> ${amount_usd:.2f} USD</li>
                                <li><strong>Fecha del pago:</strong> {payment_date_str}</li>
                                <li><strong>Tipo de evento:</strong> {event_type}</li>
                                <li><strong>Invoice ID:</strong> {invoice_id}</li>
                            </ul>
                        </body>
                        </html>
                        """
                        send_admin_email("Nuevo pago en Codex Trader", admin_html)
                    except Exception as e:
                        print(f"WARNING: Error al enviar email al admin: {e}")
                
                def send_user_email_background():
                    try:
                        if user_email:
                            user_html = f"""
                            <html>
                            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                                <h2 style="color: #2563eb;">Tu plan {plan_name} en Codex Trader está activo</h2>
                                <p>Hola {user_email.split('@')[0] if '@' in user_email else 'usuario'},</p>
                                <p>Tu plan <strong>{plan_name}</strong> en Codex Trader ha sido {'activado' if is_new_subscription else 'renovado'} correctamente.</p>
                                
                                <h3 style="color: #2563eb; margin-top: 20px;">Resumen:</h3>
                                <ul>
                                    <li><strong>Plan:</strong> {plan_name}</li>
                                    <li><strong>Precio:</strong> ${amount_usd:.2f} USD</li>
                                    <li><strong>Tokens disponibles este mes:</strong> {tokens_per_month:,}</li>
                                    <li><strong>Próxima renovación:</strong> {next_renewal_str}</li>
                                </ul>
                                
                                <h3 style="color: #2563eb; margin-top: 20px;">Recuerda:</h3>
                                <ul>
                                    <li>Puedes ver tu uso de tokens en el panel de cuenta.</li>
                                    <li>Tienes acceso al modelo de IA especializado en trading y tu biblioteca profesional.</li>
                                </ul>
                                
                                <p style="margin-top: 30px; color: #666; font-size: 12px;">
                                    Si no reconoces este pago, contáctanos respondiendo a este correo.
                                </p>
                            </body>
                            </html>
                            """
                            send_email(
                                to=user_email,
                                subject=f"Tu plan {plan_name} en Codex Trader está activo",
                                html=user_html
                            )
                    except Exception as e:
                        print(f"WARNING: Error al enviar email al usuario: {e}")
                
                admin_thread = threading.Thread(target=send_admin_email_background, daemon=True)
                admin_thread.start()
                
                user_thread = threading.Thread(target=send_user_email_background, daemon=True)
                user_thread.start()
                
            except Exception as email_error:
                print(f"WARNING: Error al enviar emails de notificación (no crítico): {email_error}")
        else:
            print(f"⚠️ No se pudo actualizar perfil para usuario {user_id}")
            
    except Exception as e:
        print(f"❌ Error en handle_invoice_paid: {str(e)}")
        raise


async def process_referrer_reward(user_id: str, referrer_id: str, invoice_id: str):
    """
    Procesa la recompensa de 10,000 tokens para el usuario que invitó.
    
    IMPORTANTE: Esta función es idempotente y verifica:
    - Que el referrer no haya alcanzado el límite de 5 recompensas
    - Que esta invoice no haya sido procesada antes
    """
    try:
        # Obtener información del referrer
        referrer_response = supabase_client.table("profiles").select(
            "id, referral_rewards_count, tokens_restantes"
        ).eq("id", referrer_id).execute()
        
        if not referrer_response.data:
            print(f"⚠️ No se encontró referrer con ID: {referrer_id}")
            return
        
        referrer = referrer_response.data[0]
        rewards_count = referrer.get("referral_rewards_count", 0)
        
        # Verificar límite de 5 recompensas
        if rewards_count >= 5:
            print(f"ℹ️ Referrer {referrer_id} ya alcanzó el límite de 5 recompensas")
            return
        
        # Verificar idempotencia: esta invoice no debe haber sido procesada
        reward_event_check = supabase_client.table("referral_reward_events").select("id").eq("invoice_id", invoice_id).execute()
        if reward_event_check.data:
            print(f"ℹ️ Recompensa para invoice {invoice_id} ya fue procesada (idempotencia)")
            return
        
        # Recompensa: 10,000 tokens
        reward_amount = 10000
        
        # Sumar tokens al referrer
        current_tokens = referrer.get("tokens_restantes", 0) or 0
        new_tokens = current_tokens + reward_amount
        
        # Actualizar referrer: tokens, contador y tokens ganados
        update_response = supabase_client.table("profiles").update({
            "tokens_restantes": new_tokens,
            "referral_rewards_count": rewards_count + 1,
            "referral_tokens_earned": referrer.get("referral_tokens_earned", 0) + reward_amount
        }).eq("id", referrer_id).execute()
        
        if update_response.data:
            # Registrar evento para idempotencia
            event_response = supabase_client.table("referral_reward_events").insert({
                "invoice_id": invoice_id,
                "user_id": user_id,
                "referrer_id": referrer_id,
                "reward_type": "first_payment",
                "tokens_granted": reward_amount
            }).execute()
            
            if event_response.data:
                print(f"✅ Recompensa otorgada: {reward_amount:,} tokens a referrer {referrer_id} por invitado {user_id} (invoice: {invoice_id})")
                
                # IMPORTANTE: Enviar email al referrer notificando la recompensa
                try:
                    from lib.email import send_email
                    import threading
                    
                    # Obtener email del referrer
                    referrer_email_response = supabase_client.table("profiles").select(
                        "email"
                    ).eq("id", referrer_id).execute()
                    
                    # Obtener email del usuario que pagó (invitado)
                    invited_user_response = supabase_client.table("profiles").select(
                        "email"
                    ).eq("id", user_id).execute()
                    
                    referrer_email = referrer_email_response.data[0].get("email") if referrer_email_response.data else None
                    invited_user_email = invited_user_response.data[0].get("email") if invited_user_response.data else "un usuario"
                    
                    if referrer_email:
                        def send_referrer_reward_email():
                            try:
                                frontend_url = FRONTEND_URL or os.getenv("FRONTEND_URL", "https://www.codextrader.tech")
                                frontend_url = frontend_url.strip('"').strip("'").strip()
                                app_url = frontend_url.rstrip('/')
                                
                                referrer_html = f"""
                                <html>
                                <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                    <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                        <h1 style="color: white; margin: 0; font-size: 28px;">¡Recompensa de Referido! 🎉</h1>
                                    </div>
                                    
                                    <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            Hola <strong>{referrer_email.split('@')[0] if '@' in referrer_email else 'trader'}</strong>,
                                        </p>
                                        
                                        <p style="font-size: 16px; margin-bottom: 20px;">
                                            ¡Excelentes noticias! Uno de tus referidos ha pagado su primera suscripción y has ganado una recompensa.
                                        </p>
                                        
                                        <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                            <h3 style="color: #059669; margin-top: 0;">Detalles de tu recompensa:</h3>
                                            <ul style="list-style: none; padding: 0; margin: 0;">
                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                    <strong style="color: #059669;">Referido:</strong> 
                                                    <span style="color: #333;">{invited_user_email}</span>
                                                </li>
                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                    <strong style="color: #059669;">Tokens recibidos:</strong> 
                                                    <span style="color: #10b981; font-weight: bold; font-size: 18px;">+{reward_amount:,} tokens</span>
                                                </li>
                                                <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                    <strong style="color: #059669;">Total de bonos usados:</strong> 
                                                    <span style="color: #333;">{rewards_count + 1} / 5</span>
                                                </li>
                                                <li style="margin-bottom: 0;">
                                                    <strong style="color: #059669;">Tokens totales ganados por referidos:</strong> 
                                                    <span style="color: #333; font-weight: bold;">{referrer.get("referral_tokens_earned", 0) + reward_amount:,} tokens</span>
                                                </li>
                                            </ul>
                                        </div>
                                        
                                        <div style="text-align: center; margin: 30px 0;">
                                            <a href="{app_url}/invitar" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                                📊 Ver mis estadísticas de referidos
                                            </a>
                                        </div>
                                        
                                        <p style="font-size: 14px; color: #666; margin-top: 30px;">
                                            <strong>¿Quieres ganar más tokens?</strong> Comparte tu enlace de referido con más traders. 
                                            Puedes ganar hasta 5 bonos de 10,000 tokens cada uno.
                                        </p>
                                        
                                        <p style="font-size: 12px; color: #666; margin-top: 30px; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                                            ¡Gracias por compartir Codex Trader con otros traders!
                                        </p>
                                    </div>
                                </body>
                                </html>
                                """
                                
                                send_email(
                                    to=referrer_email,
                                    subject=f"¡Ganaste {reward_amount:,} tokens por tu referido! - Codex Trader",
                                    html=referrer_html
                                )
                                print(f"✅ Email de recompensa enviado a referrer {referrer_email}")
                            except Exception as e:
                                print(f"⚠️ Error al enviar email de recompensa al referrer: {e}")
                        
                        email_thread = threading.Thread(target=send_referrer_reward_email, daemon=True)
                        email_thread.start()
                    else:
                        print(f"⚠️ No se encontró email para referrer {referrer_id}")
                except Exception as email_error:
                    print(f"⚠️ Error al enviar email de recompensa (no crítico): {email_error}")
            else:
                print(f"⚠️ Recompensa otorgada pero no se pudo registrar evento para invoice {invoice_id}")
        else:
            print(f"⚠️ No se pudo actualizar referrer {referrer_id}")
            
    except Exception as e:
        print(f"❌ Error al procesar recompensa de referrer: {str(e)}")
        # No lanzar excepción para no romper el webhook principal

