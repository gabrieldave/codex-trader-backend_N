"""
Módulo de utilidades para envío de emails usando SMTP.
Proporciona funciones para enviar emails genéricos y notificaciones al administrador.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dotenv import load_dotenv

# Función para limpiar caracteres nulos de las variables de entorno
def clean_env_vars():
    """Limpia caracteres nulos de las variables de entorno existentes"""
    for key in list(os.environ.keys()):
        try:
            value = os.environ[key]
            # Remover caracteres nulos
            if isinstance(value, str) and '\x00' in value:
                cleaned_value = value.replace('\x00', '')
                os.environ[key] = cleaned_value
        except (ValueError, TypeError):
            # Si hay error, intentar eliminar la variable problemática
            try:
                del os.environ[key]
            except:
                pass

# Limpiar variables de entorno antes de cargar .env
clean_env_vars()

# Cargar variables de entorno con manejo de errores
try:
    load_dotenv()
    # Limpiar nuevamente después de cargar
    clean_env_vars()
except ValueError as e:
    if "embedded null character" in str(e):
        # Limpiar y reintentar
        clean_env_vars()
        try:
            load_dotenv()
            clean_env_vars()
        except:
            pass  # Continuar sin .env si falla
except Exception:
    pass  # Continuar sin .env si hay otros errores

# Obtener variables de entorno de SMTP
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip('"').strip("'").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip('"').strip("'").strip())
SMTP_USER = os.getenv("SMTP_USER", "").strip('"').strip("'").strip()
SMTP_PASS = os.getenv("SMTP_PASS", "").strip('"').strip("'").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip('"').strip("'").strip()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip('"').strip("'").strip()

# Verificar si SMTP está configurado
SMTP_AVAILABLE = bool(SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM)

if not SMTP_AVAILABLE:
    print("WARNING: SMTP no está completamente configurado. Las funciones de email no estarán disponibles.")
    print("   Variables requeridas: SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_FROM")


def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None
) -> bool:
    """
    Envía un email usando SMTP.
    
    Esta función es robusta y no lanza excepciones para no bloquear el flujo principal.
    Si falla, solo registra el error en los logs.
    
    Args:
        to: Dirección de email del destinatario
        subject: Asunto del email
        html: Contenido HTML del email
        text: Contenido en texto plano (opcional, se genera desde HTML si no se proporciona)
        
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not SMTP_AVAILABLE:
        print(f"WARNING: No se puede enviar email: SMTP no está configurado")
        return False
    
    if not to or not subject or not html:
        print(f"WARNING: No se puede enviar email: faltan parámetros requeridos (to, subject, html)")
        return False
    
    try:
        # Crear mensaje
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = to
        msg['Subject'] = subject
        
        # Agregar contenido en texto plano si se proporciona, sino generar desde HTML
        if text:
            part_text = MIMEText(text, 'plain', 'utf-8')
            msg.attach(part_text)
        else:
            # Generar texto plano básico desde HTML (remover tags HTML simples)
            import re
            text_content = re.sub(r'<[^>]+>', '', html)
            text_content = text_content.replace('&nbsp;', ' ')
            text_content = text_content.replace('&amp;', '&')
            text_content = text_content.replace('&lt;', '<')
            text_content = text_content.replace('&gt;', '>')
            part_text = MIMEText(text_content, 'plain', 'utf-8')
            msg.attach(part_text)
        
        # Agregar contenido HTML
        part_html = MIMEText(html, 'html', 'utf-8')
        msg.attach(part_html)
        
        # Conectar al servidor SMTP y enviar
        # Agregar timeout para evitar que se quede colgado
        import socket
        socket.setdefaulttimeout(30)  # 30 segundos de timeout
        
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
                server.starttls()  # Habilitar encriptación TLS
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            
            print(f"OK: Email enviado exitosamente a {to}: {subject}")
            print(f"    Thread ID: {os.getpid()}")
            return True
        except socket.timeout:
            print(f"ERROR: Timeout al conectar a SMTP ({SMTP_HOST}:{SMTP_PORT})")
            print(f"   Railway puede tener restricciones de red. Considera usar un servicio de email con API REST (SendGrid, Resend, etc.)")
            return False
        except socket.gaierror as e:
            print(f"ERROR: No se puede resolver el hostname SMTP: {e}")
            print(f"   Verifica que SMTP_HOST sea correcto: {SMTP_HOST}")
            return False
        except OSError as e:
            if "Network is unreachable" in str(e) or e.errno == 101:
                print(f"ERROR: No se puede conectar a SMTP - Red no alcanzable: {e}")
                print(f"   Railway puede tener restricciones de firewall bloqueando conexiones SMTP salientes")
                print(f"   SOLUCIONES:")
                print(f"   1. Usar un servicio de email con API REST (SendGrid, Resend, Mailgun)")
                print(f"   2. Verificar configuración de red en Railway")
                print(f"   3. Contactar soporte de Railway sobre restricciones SMTP")
            else:
                print(f"ERROR: Error de conexión SMTP: {e}")
            return False
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"ERROR: Error de autenticación SMTP: {e}")
        print(f"   Verifica que SMTP_PASS sea una 'app password' de Gmail, no la contraseña normal")
        return False
    except smtplib.SMTPException as e:
        print(f"ERROR: Error SMTP al enviar email: {e}")
        return False
    except Exception as e:
        print(f"ERROR: Error inesperado al enviar email: {e}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return False


def send_admin_email(
    subject: str,
    html: str,
    text: Optional[str] = None
) -> bool:
    """
    Envía un email al administrador.
    
    Args:
        subject: Asunto del email
        html: Contenido HTML del email
        text: Contenido en texto plano (opcional)
        
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ADMIN_EMAIL:
        print("WARNING: ADMIN_EMAIL no está configurado, no se puede enviar email al administrador")
        return False
    
    return send_email(
        to=ADMIN_EMAIL,
        subject=subject,
        html=html,
        text=text
    )


def send_critical_error_email(
    error_type: str,
    error_message: str,
    error_details: Optional[str] = None,
    context: Optional[dict] = None
) -> bool:
    """
    Envía un email al administrador cuando ocurre un error crítico en el sistema.
    
    Args:
        error_type: Tipo de error (ej: "Database Error", "API Error", "Payment Error")
        error_message: Mensaje descriptivo del error
        error_details: Detalles adicionales del error (opcional)
        context: Diccionario con información adicional del contexto (opcional)
        
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not ADMIN_EMAIL:
        print("WARNING: ADMIN_EMAIL no está configurado, no se puede enviar email de error crítico")
        return False
    
    from datetime import datetime
    
    # Construir detalles del contexto
    context_html = ""
    if context:
        context_html = "<div style='background: #f9fafb; padding: 15px; border-radius: 8px; margin: 15px 0;'>"
        context_html += "<strong style='color: #2563eb;'>Contexto adicional:</strong><ul style='margin: 10px 0; padding-left: 20px;'>"
        for key, value in context.items():
            context_html += f"<li><strong>{key}:</strong> {value}</li>"
        context_html += "</ul></div>"
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
            <h2 style="color: white; margin: 0; font-size: 24px;">🚨 Error Crítico en el Sistema</h2>
        </div>
        
        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <p style="font-size: 16px; margin-bottom: 20px;">
                Se ha detectado un <strong>error crítico</strong> en Codex Trader que requiere atención inmediata.
            </p>
            
            <div style="background: #fee2e2; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #ef4444;">
                <ul style="list-style: none; padding: 0; margin: 0;">
                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                        <strong style="color: #991b1b;">Tipo de error:</strong> 
                        <span style="color: #333; font-weight: bold;">{error_type}</span>
                    </li>
                    <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                        <strong style="color: #991b1b;">Mensaje:</strong> 
                        <span style="color: #333;">{error_message}</span>
                    </li>
                    {f'<li style="margin-bottom: 0;"><strong style="color: #991b1b;">Detalles:</strong><pre style="background: #f3f4f6; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; color: #333;">{error_details}</pre></li>' if error_details else ''}
                </ul>
            </div>
            
            {context_html}
            
            <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
            </p>
            
            <p style="font-size: 14px; color: #666; margin-top: 20px; padding: 15px; background: #fef3c7; border-radius: 8px;">
                <strong>⚠️ Acción requerida:</strong> Por favor, revisa los logs del servidor y toma las medidas necesarias para resolver este error.
            </p>
        </div>
    </body>
    </html>
    """
    
    return send_admin_email(
        subject=f"🚨 Error Crítico: {error_type} - Codex Trader",
        html=html
    )

