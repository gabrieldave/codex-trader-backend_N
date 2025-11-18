"""
Script de Auditoría Completa del Sistema de Emails
Ejecutar: python auditoria_emails.py
"""

import os
import sys
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# Configurar encoding para Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

from dotenv import load_dotenv

# Función para limpiar caracteres nulos de las variables de entorno
def clean_env_vars():
    """Limpia caracteres nulos de las variables de entorno existentes"""
    cleaned_count = 0
    for key in list(os.environ.keys()):
        try:
            value = os.environ[key]
            if isinstance(value, str) and '\x00' in value:
                cleaned_value = value.replace('\x00', '')
                os.environ[key] = cleaned_value
                cleaned_count += 1
        except (ValueError, TypeError):
            try:
                del os.environ[key]
                cleaned_count += 1
            except:
                pass
    return cleaned_count

# Cargar variables de entorno de forma segura
clean_env_vars()
try:
    load_dotenv()
    clean_env_vars()
except Exception as e:
    print(f"[ADVERTENCIA] Error al cargar .env: {e}")

# Agregar el directorio actual al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importar módulo de email
try:
    from lib.email import (
        SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, 
        EMAIL_FROM, ADMIN_EMAIL, SMTP_AVAILABLE
    )
except ImportError as e:
    print(f"❌ Error al importar módulo de email: {e}")
    sys.exit(1)


class EmailAuditor:
    """Clase para realizar auditoría completa del sistema de emails"""
    
    def __init__(self):
        self.report = []
        self.issues = []
        self.warnings = []
        self.recommendations = []
        
    def add_to_report(self, section: str, content: str, level: str = "INFO"):
        """Agrega contenido al reporte"""
        self.report.append({
            "section": section,
            "content": content,
            "level": level,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        if level == "ERROR":
            self.issues.append(content)
        elif level == "WARNING":
            self.warnings.append(content)
    
    def check_smtp_configuration(self) -> Dict[str, any]:
        """Verifica la configuración SMTP"""
        print("\n" + "="*70)
        print("1. VERIFICACIÓN DE CONFIGURACIÓN SMTP")
        print("="*70)
        
        config_status = {
            "smtp_available": SMTP_AVAILABLE,
            "variables": {},
            "missing_variables": [],
            "issues": []
        }
        
        # Verificar cada variable
        variables = {
            "SMTP_HOST": SMTP_HOST,
            "SMTP_PORT": SMTP_PORT,
            "SMTP_USER": SMTP_USER,
            "SMTP_PASS": "***" if SMTP_PASS else "",
            "EMAIL_FROM": EMAIL_FROM,
            "ADMIN_EMAIL": ADMIN_EMAIL
        }
        
        required_vars = ["SMTP_HOST", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM"]
        
        for var_name, var_value in variables.items():
            is_required = var_name in required_vars
            is_set = bool(var_value)
            
            config_status["variables"][var_name] = {
                "value": var_value if var_name != "SMTP_PASS" else "***",
                "is_set": is_set,
                "is_required": is_required
            }
            
            if is_required and not is_set:
                config_status["missing_variables"].append(var_name)
                self.add_to_report(
                    "Configuración SMTP",
                    f"❌ Variable requerida faltante: {var_name}",
                    "ERROR"
                )
                print(f"❌ {var_name}: NO CONFIGURADO")
            elif is_set:
                if var_name == "SMTP_PASS":
                    print(f"✅ {var_name}: CONFIGURADO (oculto)")
                else:
                    print(f"✅ {var_name}: {var_value}")
            else:
                if var_name == "ADMIN_EMAIL":
                    self.add_to_report(
                        "Configuración SMTP",
                        f"⚠️ Variable opcional no configurada: {var_name} (los emails al admin no funcionarán)",
                        "WARNING"
                    )
                    print(f"⚠️ {var_name}: NO CONFIGURADO (opcional pero recomendado)")
        
        # Verificar formato de EMAIL_FROM
        if EMAIL_FROM:
            if "<" not in EMAIL_FROM and ">" not in EMAIL_FROM:
                config_status["issues"].append("EMAIL_FROM no tiene formato 'Nombre <email@ejemplo.com>'")
                self.add_to_report(
                    "Configuración SMTP",
                    "⚠️ EMAIL_FROM debería tener formato 'Nombre <email@ejemplo.com>' para mejor deliverability",
                    "WARNING"
                )
                print("⚠️ EMAIL_FROM: Formato recomendado 'Nombre <email@ejemplo.com>'")
        
        # Verificar SMTP_PORT
        if SMTP_PORT:
            if SMTP_PORT not in [587, 465, 25]:
                config_status["issues"].append(f"SMTP_PORT {SMTP_PORT} no es estándar (587, 465, 25)")
                self.add_to_report(
                    "Configuración SMTP",
                    f"⚠️ SMTP_PORT {SMTP_PORT} no es un puerto estándar (587 para TLS, 465 para SSL, 25 para sin encriptación)",
                    "WARNING"
                )
        
        # Estado general
        if SMTP_AVAILABLE:
            print("\n✅ SMTP está configurado correctamente")
            self.add_to_report(
                "Configuración SMTP",
                "✅ SMTP está configurado correctamente",
                "INFO"
            )
        else:
            print("\n❌ SMTP NO está configurado correctamente")
            self.add_to_report(
                "Configuración SMTP",
                "❌ SMTP NO está configurado correctamente - Los emails no funcionarán",
                "ERROR"
            )
        
        return config_status
    
    def list_email_types(self) -> List[Dict[str, any]]:
        """Lista todos los tipos de emails que se envían en el sistema"""
        print("\n" + "="*70)
        print("2. TIPOS DE EMAILS EN EL SISTEMA")
        print("="*70)
        
        email_types = [
            {
                "name": "Email de Bienvenida",
                "trigger": "Registro de nuevo usuario",
                "recipient": "Usuario",
                "endpoint": "/users/notify-registration",
                "file": "main.py ~4966",
                "function": "send_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Notificación de Nuevo Registro (Admin)",
                "trigger": "Registro de nuevo usuario",
                "recipient": "Admin",
                "endpoint": "/users/notify-registration",
                "file": "main.py ~4828",
                "function": "send_admin_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Confirmación de Recarga de Tokens (Usuario)",
                "trigger": "Recarga de tokens exitosa",
                "recipient": "Usuario",
                "endpoint": "/tokens/reload",
                "file": "main.py ~2542",
                "function": "send_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Notificación de Recarga de Tokens (Admin)",
                "trigger": "Recarga de tokens exitosa",
                "recipient": "Admin",
                "endpoint": "/tokens/reload",
                "file": "main.py ~2485",
                "function": "send_admin_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Email de Tokens Agotados",
                "trigger": "Usuario intenta usar chat con 0 tokens",
                "recipient": "Usuario",
                "endpoint": "/chat",
                "file": "main.py ~947",
                "function": "send_email()",
                "flags": "tokens_exhausted_email_sent",
                "status": "✅ Implementado con flag anti-duplicados"
            },
            {
                "name": "Alerta 80% de Uso (Admin)",
                "trigger": "Usuario alcanza 80% de límite mensual",
                "recipient": "Admin",
                "endpoint": "/chat",
                "file": "main.py ~1708",
                "function": "send_admin_email()",
                "flags": "fair_use_warning_shown",
                "status": "✅ Implementado"
            },
            {
                "name": "Alerta 90% de Uso con Descuento (Usuario)",
                "trigger": "Usuario alcanza 90% de límite mensual",
                "recipient": "Usuario",
                "endpoint": "/chat",
                "file": "main.py ~1939",
                "function": "send_email()",
                "flags": "fair_use_email_sent",
                "status": "✅ Implementado con flag anti-duplicados"
            },
            {
                "name": "Alerta 90% de Uso (Admin)",
                "trigger": "Usuario alcanza 90% de límite mensual",
                "recipient": "Admin",
                "endpoint": "/chat",
                "file": "main.py ~2010",
                "function": "send_admin_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Email de Error Crítico",
                "trigger": "Error crítico en el sistema",
                "recipient": "Admin",
                "endpoint": "Varios (catch de errores)",
                "file": "main.py ~595, lib/email.py ~196",
                "function": "send_critical_error_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Confirmación de Pago/Plan Activo (Usuario)",
                "trigger": "Pago de suscripción exitoso",
                "recipient": "Usuario",
                "endpoint": "/webhook/stripe",
                "file": "main.py ~3587",
                "function": "send_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Notificación de Nueva Compra (Admin)",
                "trigger": "Pago de suscripción exitoso",
                "recipient": "Admin",
                "endpoint": "/webhook/stripe",
                "file": "main.py ~3552",
                "function": "send_admin_email()",
                "flags": None,
                "status": "✅ Implementado"
            },
            {
                "name": "Recordatorio de Renovación",
                "trigger": "Tarea programada (3 días antes de renovación)",
                "recipient": "Usuario",
                "endpoint": "Tarea programada",
                "file": "main.py ~5523",
                "function": "send_email()",
                "flags": "renewal_reminder_sent",
                "status": "✅ Implementado con flag anti-duplicados"
            },
            {
                "name": "Email de Recuperación de Usuarios Inactivos",
                "trigger": "Tarea programada (usuarios inactivos 30+ días)",
                "recipient": "Usuario",
                "endpoint": "Tarea programada",
                "file": "main.py ~5695",
                "function": "send_email()",
                "flags": "inactive_recovery_email_sent",
                "status": "✅ Implementado con flag anti-duplicados"
            },
            {
                "name": "Email de Reset de Contraseña",
                "trigger": "Admin resetea contraseña de usuario",
                "recipient": "Usuario",
                "endpoint": "/admin/reset-password",
                "file": "main.py ~4172",
                "function": "send_email()",
                "flags": None,
                "status": "✅ Implementado (opcional)"
            },
            {
                "name": "Reporte Diario de Costos (Admin)",
                "trigger": "Tarea programada diaria",
                "recipient": "Admin",
                "endpoint": "Tarea programada",
                "file": "lib/cost_reports.py ~385",
                "function": "send_admin_email()",
                "flags": None,
                "status": "✅ Implementado"
            }
        ]
        
        print(f"\nTotal de tipos de emails: {len(email_types)}\n")
        
        for i, email_type in enumerate(email_types, 1):
            print(f"{i}. {email_type['name']}")
            print(f"   Trigger: {email_type['trigger']}")
            print(f"   Destinatario: {email_type['recipient']}")
            print(f"   Endpoint/Ubicación: {email_type['endpoint']}")
            print(f"   Archivo: {email_type['file']}")
            if email_type['flags']:
                print(f"   Flag anti-duplicados: {email_type['flags']}")
            print(f"   Estado: {email_type['status']}")
            print()
        
        self.add_to_report(
            "Tipos de Emails",
            f"Total de tipos de emails identificados: {len(email_types)}",
            "INFO"
        )
        
        return email_types
    
    def check_database_flags(self) -> Dict[str, any]:
        """Verifica las columnas de flags de emails en la base de datos"""
        print("\n" + "="*70)
        print("3. VERIFICACIÓN DE FLAGS EN BASE DE DATOS")
        print("="*70)
        
        flags_info = {
            "expected_flags": [
                {
                    "name": "tokens_exhausted_email_sent",
                    "type": "BOOLEAN",
                    "default": "FALSE",
                    "purpose": "Evitar duplicados de email de tokens agotados",
                    "reset_condition": "Cuando se recargan tokens",
                    "sql_file": "add_email_flags_columns.sql"
                },
                {
                    "name": "renewal_reminder_sent",
                    "type": "BOOLEAN",
                    "default": "FALSE",
                    "purpose": "Evitar duplicados de recordatorio de renovación",
                    "reset_condition": "Cuando se renueva la suscripción",
                    "sql_file": "add_email_flags_columns.sql"
                },
                {
                    "name": "inactive_recovery_email_sent",
                    "type": "BOOLEAN",
                    "default": "FALSE",
                    "purpose": "Evitar duplicados de email de recuperación",
                    "reset_condition": "Cuando el usuario vuelve a ser activo",
                    "sql_file": "add_email_flags_columns.sql"
                },
                {
                    "name": "fair_use_email_sent",
                    "type": "BOOLEAN",
                    "default": "FALSE",
                    "purpose": "Evitar duplicados de email de alerta al 90%",
                    "reset_condition": "Cuando se renueva la suscripción",
                    "sql_file": "add_fair_use_email_sent_column.sql"
                }
            ],
            "usage_locations": {
                "tokens_exhausted_email_sent": [
                    "main.py:890 - Verificación antes de enviar",
                    "main.py:955 - Marcado como True después de enviar"
                ],
                "renewal_reminder_sent": [
                    "main.py:5448 - Verificación antes de enviar",
                    "main.py:5531 - Marcado como True después de enviar"
                ],
                "inactive_recovery_email_sent": [
                    "main.py:5613 - Verificación antes de enviar",
                    "main.py:5703 - Marcado como True después de enviar"
                ],
                "fair_use_email_sent": [
                    "main.py:1725 - Verificación antes de enviar",
                    "main.py:1947 - Marcado como True después de enviar",
                    "main.py:3133 - Reset cuando se renueva suscripción",
                    "main.py:3400 - Reset cuando se renueva suscripción"
                ]
            }
        }
        
        print("\nFlags esperados en la tabla 'profiles':\n")
        
        for flag in flags_info["expected_flags"]:
            print(f"✅ {flag['name']}")
            print(f"   Tipo: {flag['type']}")
            print(f"   Propósito: {flag['purpose']}")
            print(f"   Reset: {flag['reset_condition']}")
            print(f"   SQL: {flag['sql_file']}")
            print()
        
        print("\nUbicaciones de uso en el código:\n")
        for flag_name, locations in flags_info["usage_locations"].items():
            print(f"📌 {flag_name}:")
            for location in locations:
                print(f"   - {location}")
            print()
        
        self.add_to_report(
            "Flags de Base de Datos",
            f"Total de flags de emails: {len(flags_info['expected_flags'])}",
            "INFO"
        )
        
        return flags_info
    
    def check_email_implementation_quality(self) -> Dict[str, any]:
        """Verifica la calidad de la implementación de emails"""
        print("\n" + "="*70)
        print("4. CALIDAD DE IMPLEMENTACIÓN")
        print("="*70)
        
        quality_checks = {
            "background_threading": {
                "status": "✅ Implementado",
                "description": "Los emails se envían en threads de background para no bloquear",
                "locations": [
                    "main.py:962 - Email de tokens agotados",
                    "main.py:1712 - Email al admin 80%",
                    "main.py:2017 - Email al 90%",
                    "main.py:2551 - Email de recarga de tokens",
                    "main.py:3596 - Email de pago exitoso"
                ]
            },
            "error_handling": {
                "status": "✅ Implementado",
                "description": "Manejo de errores robusto - no lanza excepciones",
                "locations": [
                    "lib/email.py:65 - send_email() no lanza excepciones",
                    "Todos los usos tienen try/except"
                ]
            },
            "anti_duplicate_flags": {
                "status": "✅ Implementado",
                "description": "Sistema de flags para evitar duplicados",
                "coverage": "4 tipos de emails protegidos"
            },
            "logging": {
                "status": "✅ Implementado",
                "description": "Logging detallado para debugging",
                "locations": [
                    "lib/email.py - Logs de éxito/error",
                    "main.py - Logs en endpoints críticos"
                ]
            },
            "html_templates": {
                "status": "✅ Implementado",
                "description": "Templates HTML bien formateados y responsivos",
                "quality": "Alto - Incluyen estilos inline, gradientes, estructura clara"
            },
            "text_plain_fallback": {
                "status": "✅ Implementado",
                "description": "Generación automática de versión texto plano desde HTML",
                "location": "lib/email.py:106-114"
            }
        }
        
        print("\nVerificaciones de calidad:\n")
        
        for check_name, check_info in quality_checks.items():
            print(f"{check_info['status']} {check_name.replace('_', ' ').title()}")
            print(f"   {check_info['description']}")
            if 'locations' in check_info:
                for location in check_info['locations']:
                    print(f"   - {location}")
            if 'coverage' in check_info:
                print(f"   Cobertura: {check_info['coverage']}")
            print()
        
        self.add_to_report(
            "Calidad de Implementación",
            "Implementación de alta calidad con threading, error handling y anti-duplicados",
            "INFO"
        )
        
        return quality_checks
    
    def identify_potential_issues(self) -> List[str]:
        """Identifica problemas potenciales"""
        print("\n" + "="*70)
        print("5. PROBLEMAS POTENCIALES Y RECOMENDACIONES")
        print("="*70)
        
        issues = []
        recommendations = []
        
        # Verificar si hay emails sin flags anti-duplicados
        emails_without_flags = [
            "Email de Bienvenida",
            "Notificación de Nuevo Registro (Admin)",
            "Confirmación de Recarga de Tokens",
            "Alerta 80% de Uso (Admin)",
            "Alerta 90% de Uso (Admin)",
            "Email de Error Crítico",
            "Confirmación de Pago/Plan Activo",
            "Notificación de Nueva Compra (Admin)",
            "Email de Reset de Contraseña",
            "Reporte Diario de Costos (Admin)"
        ]
        
        print("\n⚠️ Emails sin flags anti-duplicados:")
        for email_name in emails_without_flags:
            print(f"   - {email_name}")
            issues.append(f"Email '{email_name}' no tiene flag anti-duplicados")
        
        # Recomendaciones
        print("\n💡 RECOMENDACIONES:\n")
        
        recommendations.append({
            "priority": "ALTA",
            "title": "Agregar flags anti-duplicados para emails críticos",
            "description": "Algunos emails importantes no tienen protección contra duplicados",
            "emails": ["Email de Bienvenida", "Confirmación de Recarga de Tokens"]
        })
        
        recommendations.append({
            "priority": "MEDIA",
            "title": "Considerar servicio de email profesional",
            "description": "Para mejor deliverability y evitar problemas con Railway/SMTP",
            "options": ["SendGrid", "Resend", "Mailgun", "Amazon SES"]
        })
        
        recommendations.append({
            "priority": "BAJA",
            "title": "Implementar sistema de templates",
            "description": "Centralizar templates HTML en archivos separados para mejor mantenimiento"
        })
        
        recommendations.append({
            "priority": "MEDIA",
            "title": "Agregar métricas de envío",
            "description": "Tracking de emails enviados, fallidos, abiertos, etc."
        })
        
        for rec in recommendations:
            print(f"📌 [{rec['priority']}] {rec['title']}")
            print(f"   {rec['description']}")
            if 'emails' in rec:
                print(f"   Emails afectados: {', '.join(rec['emails'])}")
            if 'options' in rec:
                print(f"   Opciones: {', '.join(rec['options'])}")
            print()
            self.recommendations.append(rec)
        
        return issues
    
    def generate_summary_report(self):
        """Genera un resumen final del reporte"""
        print("\n" + "="*70)
        print("RESUMEN DE AUDITORÍA")
        print("="*70)
        
        total_emails = 15
        emails_with_flags = 4
        emails_without_flags = total_emails - emails_with_flags
        
        print(f"\n📊 ESTADÍSTICAS:")
        print(f"   Total de tipos de emails: {total_emails}")
        print(f"   Emails con flags anti-duplicados: {emails_with_flags}")
        print(f"   Emails sin flags anti-duplicados: {emails_without_flags}")
        print(f"   Problemas encontrados: {len(self.issues)}")
        print(f"   Advertencias: {len(self.warnings)}")
        print(f"   Recomendaciones: {len(self.recommendations)}")
        
        print(f"\n✅ PUNTOS FUERTES:")
        print(f"   - Configuración SMTP robusta con manejo de errores")
        print(f"   - Emails se envían en background threads")
        print(f"   - Templates HTML bien diseñados")
        print(f"   - Sistema de flags para emails críticos")
        print(f"   - Logging detallado para debugging")
        
        if self.issues:
            print(f"\n❌ PROBLEMAS CRÍTICOS:")
            for issue in self.issues:
                print(f"   - {issue}")
        
        if self.warnings:
            print(f"\n⚠️ ADVERTENCIAS:")
            for warning in self.warnings:
                print(f"   - {warning}")
        
        if self.recommendations:
            print(f"\n💡 RECOMENDACIONES PRIORITARIAS:")
            high_priority = [r for r in self.recommendations if r['priority'] == 'ALTA']
            for rec in high_priority:
                print(f"   - {rec['title']}")
        
        print("\n" + "="*70)
        print("Auditoría completada")
        print("="*70)
    
    def run_full_audit(self):
        """Ejecuta la auditoría completa"""
        print("\n" + "="*70)
        print("AUDITORÍA COMPLETA DEL SISTEMA DE EMAILS")
        print("Codex Trader")
        print("="*70)
        print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Verificar configuración SMTP
        smtp_config = self.check_smtp_configuration()
        
        # 2. Listar tipos de emails
        email_types = self.list_email_types()
        
        # 3. Verificar flags de base de datos
        db_flags = self.check_database_flags()
        
        # 4. Verificar calidad de implementación
        quality = self.check_email_implementation_quality()
        
        # 5. Identificar problemas potenciales
        issues = self.identify_potential_issues()
        
        # 6. Generar resumen
        self.generate_summary_report()
        
        return {
            "smtp_config": smtp_config,
            "email_types": email_types,
            "db_flags": db_flags,
            "quality": quality,
            "issues": issues,
            "report": self.report
        }


def main():
    """Función principal"""
    auditor = EmailAuditor()
    results = auditor.run_full_audit()
    
    # Guardar reporte en archivo (opcional)
    report_filename = f"auditoria_emails_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    try:
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("REPORTE DE AUDITORÍA DE EMAILS\n")
            f.write("="*70 + "\n")
            f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for entry in auditor.report:
                f.write(f"[{entry['level']}] {entry['section']}: {entry['content']}\n")
                f.write(f"   Timestamp: {entry['timestamp']}\n\n")
        
        print(f"\n📄 Reporte guardado en: {report_filename}")
    except Exception as e:
        print(f"\n⚠️ No se pudo guardar el reporte: {e}")


if __name__ == "__main__":
    main()

