"""
Módulo de utilidades para envío de emails usando Resend (API REST) o SMTP como fallback.
Proporciona funciones para enviar emails genéricos y notificaciones al administrador.
"""
import os
import smtplib
import time
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dotenv import load_dotenv

# Intentar importar Resend
try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    print("WARNING: Resend no está instalado. Instala con: pip install resend")

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

# Obtener variables de entorno de Resend
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip('"').strip("'").strip()

# Obtener variables de entorno de SMTP (fallback)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip('"').strip("'").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip('"').strip("'").strip())
SMTP_USER = os.getenv("SMTP_USER", "").strip('"').strip("'").strip()
SMTP_PASS = os.getenv("SMTP_PASS", "").strip('"').strip("'").strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip('"').strip("'").strip()
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip('"').strip("'").strip()

# Verificar si Resend está configurado
RESEND_AVAILABLE_AND_CONFIGURED = RESEND_AVAILABLE and bool(RESEND_API_KEY)

# Verificar si SMTP está configurado (fallback)
SMTP_AVAILABLE = bool(SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM)

# Instancia global de Resend (se inicializa si está configurado)
resend_client = None

# Rate limiting para Resend: máximo 2 requests por segundo
# Usamos un lock y timestamp para controlar el rate
_resend_rate_lock = threading.Lock()
_last_resend_request_time = 0
_min_request_interval = 0.5  # 500ms entre requests (permite 2 por segundo)

# Configurar Resend si está disponible
if RESEND_AVAILABLE_AND_CONFIGURED:
    try:
        # Intentar diferentes formas de inicializar Resend según la versión de la librería
        # Opción 1: Crear instancia con Resend(api_key=...)
        try:
            resend_client = resend.Resend(api_key=RESEND_API_KEY)
            print("✅ Resend configurado correctamente (usando instancia)")
        except (AttributeError, TypeError):
            # Opción 2: Configurar API key directamente
            try:
                resend.api_key = RESEND_API_KEY
                resend_client = resend  # Usar el módulo directamente
                print("✅ Resend configurado correctamente (usando api_key directo)")
            except Exception as e2:
                print(f"WARNING: Error al configurar Resend: {e2}")
                resend_client = None
                RESEND_AVAILABLE_AND_CONFIGURED = False
    except Exception as e:
        print(f"WARNING: Error al inicializar Resend: {e}")
        resend_client = None
        RESEND_AVAILABLE_AND_CONFIGURED = False
elif RESEND_AVAILABLE and not RESEND_API_KEY:
    print("WARNING: Resend está instalado pero RESEND_API_KEY no está configurado.")
    print("   Configura RESEND_API_KEY en Railway para usar Resend (recomendado).")
    print("   O usa SMTP como fallback.")

if not RESEND_AVAILABLE_AND_CONFIGURED and not SMTP_AVAILABLE:
    print("WARNING: Ni Resend ni SMTP están configurados. Las funciones de email no estarán disponibles.")
    print("   Configura RESEND_API_KEY (recomendado) o SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_FROM")


def send_email(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None
) -> bool:
    """
    Envía un email usando Resend (API REST) como método principal, o SMTP como fallback.
    
    Esta función es robusta y no lanza excepciones para no bloquear el flujo principal.
    Si falla, solo registra el error en los logs.
    
    Prioridad:
    1. Resend (si está configurado) - Recomendado para Railway
    2. SMTP (si Resend no está disponible) - Fallback
    
    Args:
        to: Dirección de email del destinatario
        subject: Asunto del email
        html: Contenido HTML del email
        text: Contenido en texto plano (opcional, se genera desde HTML si no se proporciona)
        
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not to or not subject or not html:
        print(f"WARNING: No se puede enviar email: faltan parámetros requeridos (to, subject, html)")
        return False
    
    # Intentar primero con Resend (método recomendado)
    if RESEND_AVAILABLE_AND_CONFIGURED:
        return _send_email_resend(to, subject, html, text)
    
    # Fallback a SMTP si Resend no está disponible
    if SMTP_AVAILABLE:
        return _send_email_smtp(to, subject, html, text)
    
    print(f"WARNING: No se puede enviar email: Ni Resend ni SMTP están configurados")
    return False


def _wait_for_rate_limit():
    """
    Espera el tiempo necesario para respetar el rate limit de Resend (2 requests/segundo).
    Usa un lock para asegurar que solo un thread a la vez controle el rate limiting.
    """
    global _last_resend_request_time
    
    with _resend_rate_lock:
        current_time = time.time()
        time_since_last_request = current_time - _last_resend_request_time
        
        if time_since_last_request < _min_request_interval:
            wait_time = _min_request_interval - time_since_last_request
            time.sleep(wait_time)
        
        _last_resend_request_time = time.time()


def _send_email_resend(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None
) -> bool:
    """
    Envía un email usando Resend API (método principal, funciona en Railway).
    Implementa rate limiting (2 requests/segundo) y retry con backoff exponencial.
    
    Args:
        to: Dirección de email del destinatario
        subject: Asunto del email
        html: Contenido HTML del email
        text: Contenido en texto plano (opcional)
        
    Returns:
        True si el email se envió correctamente, False en caso contrario
    """
    if not resend_client:
        print("ERROR: Cliente de Resend no está inicializado")
        return False
    
    try:
        # Generar texto plano desde HTML si no se proporciona
        if not text:
            import re
            text = re.sub(r'<[^>]+>', '', html)
            text = text.replace('&nbsp;', ' ')
            text = text.replace('&amp;', '&')
            text = text.replace('&lt;', '<')
            text = text.replace('&gt;', '>')
        
        # Extraer el email del formato "Nombre <email@example.com>" si es necesario
        from_email = EMAIL_FROM
        if '<' in EMAIL_FROM and '>' in EMAIL_FROM:
            # Ya está en formato correcto
            pass
        else:
            # Formato simple, usar como está
            pass
        
        # Parámetros para Resend
        params = {
            "from": from_email,
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text
        }
        
        # Retry con backoff exponencial para manejar rate limiting
        max_retries = 3
        base_delay = 1.0  # 1 segundo base
        
        for attempt in range(max_retries):
            try:
                # Esperar para respetar rate limit antes de cada intento
                _wait_for_rate_limit()
                
                # Enviar email usando Resend
                # Intentar diferentes formas según la versión de la librería
                email = None
                last_error = None
                
                # Opción 1: resend_client.emails.send() (instancia)
                if hasattr(resend_client, 'emails') and hasattr(resend_client.emails, 'send'):
                    try:
                        email = resend_client.emails.send(params)
                    except AttributeError as e:
                        last_error = e
                # Opción 2: resend_client.Emails.send() (instancia con mayúscula)
                elif hasattr(resend_client, 'Emails') and hasattr(resend_client.Emails, 'send'):
                    try:
                        email = resend_client.Emails.send(params)
                    except AttributeError as e:
                        last_error = e
                # Opción 3: resend.emails.send() (módulo directo)
                elif hasattr(resend, 'emails') and hasattr(resend.emails, 'send'):
                    try:
                        email = resend.emails.send(params)
                    except AttributeError as e:
                        last_error = e
                # Opción 4: resend.Emails.send() (módulo directo con mayúscula)
                elif hasattr(resend, 'Emails') and hasattr(resend.Emails, 'send'):
                    try:
                        email = resend.Emails.send(params)
                    except AttributeError as e:
                        last_error = e
                else:
                    raise Exception(f"No se pudo encontrar el método correcto para enviar email. Cliente: {type(resend_client)}")
                
                if email is None and last_error:
                    raise last_error
                
                # Resend devuelve un objeto con 'id' si es exitoso
                if email and hasattr(email, 'id'):
                    print(f"OK: Email enviado exitosamente a {to} usando Resend: {subject}")
                    print(f"    Email ID: {email.id}")
                    return True
                elif email and isinstance(email, dict) and 'id' in email:
                    print(f"OK: Email enviado exitosamente a {to} usando Resend: {subject}")
                    print(f"    Email ID: {email['id']}")
                    return True
                else:
                    print(f"ERROR: Resend no devolvió un ID de email válido. Respuesta: {email}")
                    return False
                    
            except Exception as e:
                error_str = str(e)
                
                # Si es error de rate limiting, intentar retry con backoff
                if "Too many requests" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        # Calcular delay exponencial: 1s, 2s, 4s
                        delay = base_delay * (2 ** attempt)
                        print(f"WARNING: Rate limit alcanzado. Esperando {delay:.1f}s antes de reintentar (intento {attempt + 1}/{max_retries})...")
                        time.sleep(delay)
                        continue
                    else:
                        print(f"ERROR: Rate limit alcanzado después de {max_retries} intentos")
                        raise
                else:
                    # Otro tipo de error, no reintentar
                    raise
        
        # Si llegamos aquí, todos los reintentos fallaron
        return False
            
    except Exception as e:
        print(f"ERROR: Error al enviar email con Resend: {e}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        # Intentar fallback a SMTP si Resend falla
        if SMTP_AVAILABLE:
            print(f"   Intentando fallback a SMTP...")
            return _send_email_smtp(to, subject, html, text)
        return False


def _send_email_smtp(
    to: str,
    subject: str,
    html: str,
    text: Optional[str] = None
) -> bool:
    """
    Envía un email usando SMTP (método fallback, puede no funcionar en Railway).
    
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
            
            print(f"OK: Email enviado exitosamente a {to} usando SMTP: {subject}")
            print(f"    Thread ID: {os.getpid()}")
            return True
        except socket.timeout:
            print(f"ERROR: Timeout al conectar a SMTP ({SMTP_HOST}:{SMTP_PORT})")
            print(f"   Railway bloquea SMTP. Configura RESEND_API_KEY para usar Resend (recomendado).")
            return False
        except socket.gaierror as e:
            print(f"ERROR: No se puede resolver el hostname SMTP: {e}")
            print(f"   Verifica que SMTP_HOST sea correcto: {SMTP_HOST}")
            return False
        except OSError as e:
            if "Network is unreachable" in str(e) or e.errno == 101:
                print(f"ERROR: No se puede conectar a SMTP - Red no alcanzable: {e}")
                print(f"   Railway bloquea conexiones SMTP salientes.")
                print(f"   SOLUCION: Configura RESEND_API_KEY en Railway para usar Resend (recomendado).")
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
        print(f"ERROR: Error inesperado al enviar email con SMTP: {e}")
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

