#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Webhook endpoint para recibir notificaciones de Supabase cuando se crea un nuevo usuario.
Esta es una solución alternativa más robusta que depender del frontend.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Este archivo será importado en main.py para agregar el endpoint de webhook

def create_webhook_endpoint(app, supabase_client):
    """
    Crea un endpoint de webhook para recibir notificaciones de Supabase.
    Este endpoint se puede configurar en Supabase Dashboard > Database > Webhooks.
    """
    from fastapi import Request, HTTPException
    from lib.email import send_email, send_admin_email
    from datetime import datetime
    
    @app.post("/webhooks/new-user")
    async def webhook_new_user(request: Request):
        """
        Webhook para recibir notificaciones cuando se crea un nuevo usuario.
        
        Configura esto en Supabase Dashboard:
        Database > Webhooks > New Webhook
        - Table: auth.users
        - Events: INSERT
        - HTTP Request URL: https://tu-backend.com/webhooks/new-user
        - HTTP Request Method: POST
        """
        try:
            # Obtener datos del webhook
            data = await request.json()
            
            # Supabase envía los datos en formato específico
            # Verificar si es un evento de inserción
            if data.get("type") == "INSERT":
                record = data.get("record", {})
                user_id = record.get("id")
                user_email = record.get("email")
                
                if not user_id or not user_email:
                    raise HTTPException(status_code=400, detail="Datos incompletos en webhook")
                
                print(f"[WEBHOOK] Nuevo usuario detectado: {user_email} (ID: {user_id})")
                
                # Obtener información del perfil
                try:
                    profile_response = supabase_client.table("profiles").select(
                        "current_plan, created_at, tokens_restantes"
                    ).eq("id", user_id).execute()
                    
                    if profile_response.data:
                        profile_data = profile_response.data[0]
                        initial_tokens = profile_data.get("tokens_restantes", 0)
                    else:
                        initial_tokens = 0
                except Exception as e:
                    print(f"[WEBHOOK] Error al obtener perfil: {e}")
                    initial_tokens = 0
                
                # Enviar email al admin
                admin_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <h2 style="color: #2563eb;">Nuevo registro en Codex Trader</h2>
                    <p>Se ha registrado un nuevo usuario en Codex Trader.</p>
                    <ul>
                        <li><strong>Email:</strong> {user_email}</li>
                        <li><strong>ID de usuario:</strong> {user_id}</li>
                        <li><strong>Fecha de registro:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}</li>
                        <li><strong>Tokens iniciales:</strong> {initial_tokens:,}</li>
                    </ul>
                </body>
                </html>
                """
                
                print(f"[WEBHOOK] Enviando email al admin...")
                send_admin_email("Nuevo registro en Codex Trader", admin_html)
                
                # Enviar email de bienvenida al usuario
                user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
                app_url = f"{FRONTEND_URL}/app"
                
                welcome_html = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                        <h1 style="color: white; margin: 0; font-size: 28px;">Bienvenido a Codex Trader</h1>
                    </div>
                    
                    <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                        <p style="font-size: 16px; margin-bottom: 20px;">
                            Hola <strong>{user_name}</strong>, bienvenido a Codex Trader.
                        </p>
                        
                        <p style="font-size: 16px; margin-bottom: 20px; color: #555;">
                            Codex Trader es tu asistente de IA especializado en trading, entrenado con contenido profesional para ayudarte a analizar el mercado, gestionar riesgo y diseñar estrategias.
                        </p>
                        
                        <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #2563eb;">
                            <h3 style="color: #2563eb; margin-top: 0;">¿Qué puedes hacer?</h3>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li style="margin-bottom: 10px;">Tienes <strong>{initial_tokens:,} tokens iniciales</strong> para probar el asistente.</li>
                                <li style="margin-bottom: 10px;">Puedes hacer preguntas sobre gestión de riesgo, psicología del trader, análisis técnico y más.</li>
                            </ul>
                        </div>
                        
                        <div style="text-align: center; margin: 30px 0;">
                            <a href="{app_url}" style="display: inline-block; background: #2563eb; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                Empieza aquí
                            </a>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                print(f"[WEBHOOK] Enviando email de bienvenida a {user_email}...")
                send_email(
                    to=user_email,
                    subject="Bienvenido a Codex Trader",
                    html=welcome_html
                )
                
                print(f"[WEBHOOK] Emails enviados correctamente para {user_email}")
                
                return {"success": True, "message": "Emails enviados correctamente"}
            else:
                return {"success": False, "message": "Tipo de evento no soportado"}
                
        except Exception as e:
            print(f"[WEBHOOK] ERROR: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

