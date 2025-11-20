"""
Script para limpiar completamente la base de datos, dejando solo al administrador.
Este script elimina todos los datos de prueba: usuarios, chats, métricas, pagos, referidos, etc.

ADVERTENCIA: Este script es IRREVERSIBLE y eliminará TODOS los datos excepto el admin.

Uso:
    python limpiar_base_datos_para_produccion.py
"""
import os
import sys
from dotenv import load_dotenv

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

load_dotenv()

# Obtener variables de entorno con limpieza
def get_env(key, default=""):
    """Obtiene variable de entorno y limpia comillas y formato."""
    value = os.getenv(key, default)
    if not value:
        return ""
    value = value.strip('"').strip("'").strip()
    if "=" in value and not value.startswith(("http://", "https://", "postgresql://", "postgres://")):
        if value.startswith("http="):
            value = value.replace("http=", "https://", 1)
        elif not value.startswith(("http://", "https://", "postgresql://", "postgres://")):
            # Si tiene formato KEY=VALUE, extraer solo el valor
            parts = value.split("=", 1)
            if len(parts) > 1:
                value = parts[1].strip()
    # Si empieza con //, agregar postgresql://
    if value.startswith("//"):
        value = "postgresql://" + value[2:]
    return value

def _derive_rest_url_from_db(db_url: str) -> str:
    """Deriva la URL REST de Supabase desde una URL de conexión a la base de datos."""
    from urllib.parse import urlparse
    
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

# Obtener variables de entorno (usando misma lógica que verificar_admin_usuario.py)
SUPABASE_URL = get_env("SUPABASE_URL") or get_env("SUPABASE_REST_URL")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY") or get_env("SUPABASE_SERVICE_ROLE_KEY")

# Si SUPABASE_URL es una URL de DB, derivar la REST URL
if SUPABASE_URL:
    if SUPABASE_URL.startswith("postgresql://") or SUPABASE_URL.startswith("postgres://"):
        from urllib.parse import urlparse
        try:
            parsed = urlparse(SUPABASE_URL)
            host = parsed.hostname or ""
            username = parsed.username or ""
            
            # Caso 1: URL de pooler (ej: aws-0-us-west-1.pooler.supabase.com)
            if "pooler.supabase.com" in host or "pooler.supabase.co" in host:
                if username and username.startswith("postgres."):
                    project_ref = username.replace("postgres.", "")
                    if project_ref:
                        SUPABASE_URL = f"https://{project_ref}.supabase.co"
            
            # Caso 2: Conexión directa (ej: db.xxx.supabase.co o host.supabase.co)
            elif "db." in host and ".supabase.co" in host:
                project_ref = host.replace("db.", "").replace(".supabase.co", "")
                if project_ref:
                    SUPABASE_URL = f"https://{project_ref}.supabase.co"
            elif ".supabase.co" in host and not host.startswith("db."):
                # Ya es el host correcto, solo agregar https://
                if not SUPABASE_URL.startswith("https://"):
                    SUPABASE_URL = f"https://{host}"
        except Exception as e:
            print(f"[DEBUG] WARNING: Error al derivar URL REST: {e}")
            # Si falla, intentar usar directamente la URL si ya empieza con https://
            if not SUPABASE_URL.startswith("https://"):
                print(f"[DEBUG] URL no pudo ser derivada, usando como está: {SUPABASE_URL[:50]}...")

# Usar SUPABASE_URL como SUPABASE_REST_URL
SUPABASE_REST_URL = SUPABASE_URL

# Asegurarse de que la URL es válida (debe empezar con https://)
if SUPABASE_REST_URL and not SUPABASE_REST_URL.startswith("https://"):
    print(f"[DEBUG] ERROR: URL inválida (debe empezar con https://): {SUPABASE_REST_URL[:50]}...")
    SUPABASE_REST_URL = None

# Variable global para ADMIN_EMAILS
ADMIN_EMAILS = []

if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
    print("❌ ERROR: Faltan variables de entorno SUPABASE_URL y SUPABASE_SERVICE_KEY")
    print(f"   SUPABASE_REST_URL: {SUPABASE_REST_URL or 'No configurada'}")
    print(f"   SUPABASE_SERVICE_KEY: {'Configurada' if SUPABASE_SERVICE_KEY else 'No configurada'}")
    sys.exit(1)

print(f"[DEBUG] Conectando a Supabase: {SUPABASE_REST_URL[:50]}...")

def get_admin_user_id():
    """Obtiene el ID del usuario administrador."""
    global ADMIN_EMAILS
    try:
        from supabase import create_client
        
        if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
            print("[ERROR] SUPABASE_REST_URL y SUPABASE_SERVICE_KEY deben estar configurados")
            sys.exit(1)
        
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        # Obtener ADMIN_EMAILS para uso global
        admin_emails_env = os.getenv("ADMIN_EMAILS", "").strip('"').strip("'").strip()
        if admin_emails_env:
            ADMIN_EMAILS = [email.strip().lower() for email in admin_emails_env.split(",") if email.strip()]
        
        # Verificar por email en ADMIN_EMAILS
        admin_emails = admin_emails_env
        if admin_emails:
            admin_list = [email.strip().lower() for email in admin_emails.split(",")]
            
            # Buscar admin por email
            for admin_email in admin_list:
                profile_response = supabase.table("profiles").select("id, email, is_admin").eq("email", admin_email).execute()
                if profile_response.data:
                    admin_user = profile_response.data[0]
                    print(f"[OK] Admin encontrado por email: {admin_user['email']} (ID: {admin_user['id']})")
                    return admin_user['id']
        
        # Verificar por is_admin = true
        profile_response = supabase.table("profiles").select("id, email, is_admin").eq("is_admin", True).execute()
        if profile_response.data:
            admin_user = profile_response.data[0]
            print(f"[OK] Admin encontrado por is_admin: {admin_user['email']} (ID: {admin_user['id']})")
            return admin_user['id']
        
        print("[ERROR] No se encontró ningún usuario administrador")
        print("   Verifica que ADMIN_EMAILS esté configurado o que exista un usuario con is_admin=true")
        sys.exit(1)
        
    except Exception as e:
        print(f"[ERROR] Error al obtener admin: {e}")
        sys.exit(1)

def limpiar_base_datos(admin_user_id: str):
    """Limpia la base de datos, manteniendo solo al admin."""
    try:
        from supabase import create_client
        
        if not SUPABASE_REST_URL or not SUPABASE_SERVICE_KEY:
            print("[ERROR] SUPABASE_REST_URL y SUPABASE_SERVICE_KEY deben estar configurados")
            sys.exit(1)
        
        supabase = create_client(SUPABASE_REST_URL, SUPABASE_SERVICE_KEY)
        
        print("\n" + "="*60)
        print("INICIANDO LIMPIEZA DE BASE DE DATOS")
        print("="*60)
        print(f"Admin protegido (ID): {admin_user_id}\n")
        
        # 1. Eliminar eventos de referidos (excepto admin)
        print("[1/9] Limpiando eventos de referidos...")
        try:
            # Primero obtener todos los eventos
            ref_events = supabase.table("referral_reward_events").select("id").execute()
            if ref_events.data:
                # Eliminar todos (no hay relación directa con usuario, así que eliminamos todos)
                deleted = 0
                for event in ref_events.data:
                    try:
                        supabase.table("referral_reward_events").delete().eq("id", event["id"]).execute()
                        deleted += 1
                    except:
                        pass
                print(f"   ✅ {deleted} eventos de referidos eliminados")
            else:
                print("   ℹ️  No hay eventos de referidos")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar referral_reward_events: {e}")
            # Continuar aunque falle
        
        # 2. Eliminar pagos de Stripe (excepto del admin si es necesario)
        print("[2/9] Limpiando pagos de Stripe de prueba...")
        try:
            # Obtener todos los pagos que NO son del admin
            payments = supabase.table("stripe_payments").select("id, user_id").neq("user_id", admin_user_id).execute()
            if payments.data:
                deleted = 0
                for payment in payments.data:
                    try:
                        supabase.table("stripe_payments").delete().eq("id", payment["id"]).execute()
                        deleted += 1
                    except:
                        pass
                print(f"   ✅ {deleted} pagos de Stripe eliminados")
            else:
                print("   ℹ️  No hay pagos de Stripe para eliminar")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar stripe_payments: {e}")
        
        # 3. Eliminar eventos de uso de modelos (excepto del admin)
        print("[3/9] Limpiando eventos de uso de modelos...")
        try:
            # Obtener todos los eventos que NO son del admin
            usage_events = supabase.table("model_usage_events").select("id, user_id").neq("user_id", admin_user_id).execute()
            if usage_events.data:
                deleted = 0
                for event in usage_events.data:
                    try:
                        supabase.table("model_usage_events").delete().eq("id", event["id"]).execute()
                        deleted += 1
                    except:
                        pass
                print(f"   ✅ {deleted} eventos de uso de modelos eliminados")
            else:
                print("   ℹ️  No hay eventos de uso de modelos para eliminar")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar model_usage_events: {e}")
        
        # 4. Eliminar sesiones de chat (excepto del admin)
        print("[4/9] Limpiando sesiones de chat...")
        try:
            # Obtener todas las sesiones que NO son del admin
            chat_sessions = supabase.table("chat_sessions").select("id, user_id").neq("user_id", admin_user_id).execute()
            if chat_sessions.data:
                deleted = 0
                for session in chat_sessions.data:
                    try:
                        supabase.table("chat_sessions").delete().eq("id", session["id"]).execute()
                        deleted += 1
                    except:
                        pass
                print(f"   ✅ {deleted} sesiones de chat eliminadas")
            else:
                print("   ℹ️  No hay sesiones de chat para eliminar")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar chat_sessions: {e}")
        
        # 5. Eliminar conversaciones/mensajes (excepto del admin)
        print("[5/9] Limpiando conversaciones y mensajes...")
        try:
            # Obtener todas las conversaciones que NO son del admin
            conversations = supabase.table("conversations").select("id, user_id").neq("user_id", admin_user_id).execute()
            if conversations.data:
                deleted = 0
                for conv in conversations.data:
                    try:
                        supabase.table("conversations").delete().eq("id", conv["id"]).execute()
                        deleted += 1
                    except:
                        pass
                print(f"   ✅ {deleted} conversaciones/mensajes eliminados")
            else:
                print("   ℹ️  No hay conversaciones para eliminar")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar conversations: {e}")
        
        # 6. Limpiar referencias de referidos en profiles (excepto admin)
        print("[6/9] Limpiando referencias de referidos...")
        try:
            # Actualizar todos los perfiles (excepto admin) para limpiar referencias
            profiles = supabase.table("profiles").select("id").neq("id", admin_user_id).execute()
            if profiles.data:
                updated = 0
                for profile in profiles.data:
                    try:
                        supabase.table("profiles").update({
                            "referred_by_user_id": None,
                            "has_generated_referral_reward": False
                        }).eq("id", profile["id"]).execute()
                        updated += 1
                    except:
                        pass
                print(f"   ✅ {updated} perfiles actualizados (referencias limpiadas)")
            else:
                print("   ℹ️  No hay perfiles para actualizar")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar referencias: {e}")
        
        # 7. Obtener lista de usuarios a eliminar (excepto admin)
        print("[7/9] Obteniendo lista de usuarios a eliminar...")
        try:
            users_response = supabase.table("profiles").select("id, email").neq("id", admin_user_id).execute()
            users_to_delete = users_response.data if users_response.data else []
            print(f"   ℹ️  {len(users_to_delete)} usuarios encontrados para eliminar")
        except Exception as e:
            print(f"   ⚠️  Error al obtener usuarios: {e}")
            users_to_delete = []
        
        # 8. Eliminar usuarios (excepto admin)
        print("[8/9] Eliminando usuarios...")
        if users_to_delete:
            deleted_count = 0
            failed_count = 0
            
            for i, user in enumerate(users_to_delete, 1):
                user_id = user.get("id")
                user_email = user.get("email", "Sin email")
                
                print(f"   [{i}/{len(users_to_delete)}] Eliminando {user_email}...", end=" ")
                
                try:
                    # Intentar eliminar usando función RPC si existe
                    try:
                        supabase.rpc('delete_user_by_id', {'user_id_to_delete': user_id}).execute()
                        print("✅")
                        deleted_count += 1
                    except:
                        # Si RPC no existe, intentar eliminar desde Admin API
                        try:
                            import requests
                            admin_api_url = f"{SUPABASE_REST_URL}/auth/v1/admin/users/{user_id}"
                            headers = {
                                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                "apikey": SUPABASE_SERVICE_KEY,
                                "Content-Type": "application/json"
                            }
                            response = requests.delete(admin_api_url, headers=headers, timeout=10)
                            if response.status_code in [200, 204]:
                                print("✅")
                                deleted_count += 1
                            else:
                                print(f"❌ Error {response.status_code}")
                                failed_count += 1
                        except Exception as api_error:
                            print(f"❌ Error: {api_error}")
                            failed_count += 1
                except Exception as e:
                    print(f"❌ Error: {e}")
                    failed_count += 1
            
            print(f"\n   ✅ Usuarios eliminados: {deleted_count}")
            if failed_count > 0:
                print(f"   ❌ Usuarios con error: {failed_count}")
        else:
            print("   ℹ️  No hay usuarios para eliminar")
        
        # 9. IMPORTANTE: Eliminar usuarios huérfanos (existen en auth.users pero NO en profiles)
        print("[9/9] Eliminando usuarios huérfanos de auth.users...")
        try:
            import requests
            
            # Obtener todos los usuarios de auth.users
            try:
                auth_users_response = supabase.auth.admin.list_users()
                if auth_users_response and hasattr(auth_users_response, 'users'):
                    auth_users = auth_users_response.users
                    
                    # Obtener IDs de perfiles que existen
                    existing_profiles = supabase.table("profiles").select("id").execute()
                    existing_profile_ids = {p['id'] for p in (existing_profiles.data or [])}
                    
                    # Identificar usuarios huérfanos (no tienen perfil y no son admin)
                    orphaned_users = []
                    for auth_user in auth_users:
                        user_id = auth_user.id
                        user_email = (auth_user.email or "").lower()
                        
                        # Verificar si es admin
                        is_admin = False
                        if ADMIN_EMAILS:
                            is_admin = user_email in ADMIN_EMAILS
                        
                        # Verificar si tiene is_admin en profiles (por si acaso)
                        if not is_admin:
                            try:
                                profile_check = supabase.table("profiles").select("is_admin").eq("id", user_id).execute()
                                if profile_check.data:
                                    is_admin = profile_check.data[0].get("is_admin", False)
                            except:
                                pass
                        
                        # Si no es admin y no tiene perfil, es huérfano
                        if not is_admin and user_id not in existing_profile_ids:
                            orphaned_users.append({
                                'id': user_id,
                                'email': auth_user.email or "Sin email"
                            })
                    
                    if orphaned_users:
                        print(f"   ⚠️  Encontrados {len(orphaned_users)} usuario(s) huérfano(s) para eliminar")
                        deleted_orphans = 0
                        failed_orphans = 0
                        
                        for i, orphan in enumerate(orphaned_users, 1):
                            user_id = orphan['id']
                            user_email = orphan['email']
                            
                            print(f"   [{i}/{len(orphaned_users)}] Eliminando huérfano {user_email}...", end=" ")
                            
                            try:
                                admin_api_url = f"{SUPABASE_REST_URL}/auth/v1/admin/users/{user_id}"
                                headers = {
                                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                                    "apikey": SUPABASE_SERVICE_KEY,
                                    "Content-Type": "application/json"
                                }
                                response = requests.delete(admin_api_url, headers=headers, timeout=10)
                                if response.status_code in [200, 204]:
                                    print("✅")
                                    deleted_orphans += 1
                                else:
                                    print(f"❌ Error {response.status_code}")
                                    if response.text:
                                        print(f"      {response.text[:100]}")
                                    failed_orphans += 1
                            except Exception as e:
                                print(f"❌ Error: {str(e)[:50]}")
                                failed_orphans += 1
                        
                        print(f"\n   ✅ Usuarios huérfanos eliminados: {deleted_orphans}")
                        if failed_orphans > 0:
                            print(f"   ❌ Usuarios huérfanos con error: {failed_orphans}")
                    else:
                        print("   ✅ No hay usuarios huérfanos")
                else:
                    print("   ⚠️  No se pudieron obtener usuarios de auth.users (requiere permisos admin)")
            except Exception as e:
                print(f"   ⚠️  Error al obtener usuarios de auth.users: {e}")
                print("   ℹ️  Esto es normal si no tienes permisos de admin")
        except Exception as e:
            print(f"   ⚠️  Error al limpiar usuarios huérfanos: {e}")
        
        # Verificar resultado final
        print("\n" + "="*60)
        print("VERIFICACIÓN FINAL")
        print("="*60)
        
        # Verificar usuarios restantes
        try:
            remaining_users = supabase.table("profiles").select("id, email").execute()
            if remaining_users.data:
                print(f"✅ Usuarios restantes: {len(remaining_users.data)}")
                for user in remaining_users.data:
                    print(f"   - {user.get('email', 'Sin email')} (ID: {user.get('id')})")
            else:
                print("ℹ️  No quedan usuarios (solo admin debería quedar)")
        except Exception as e:
            print(f"⚠️  Error al verificar usuarios restantes: {e}")
        
        # Verificar datos restantes del admin
        try:
            admin_chats = supabase.table("chat_sessions").select("id").eq("user_id", admin_user_id).execute()
            admin_events = supabase.table("model_usage_events").select("id").eq("user_id", admin_user_id).execute()
            print(f"\n✅ Datos del admin preservados:")
            print(f"   - Sesiones de chat: {len(admin_chats.data) if admin_chats.data else 0}")
            print(f"   - Eventos de uso: {len(admin_events.data) if admin_events.data else 0}")
        except:
            pass
        
        # 10. IMPORTANTE: Verificar que el trigger sigue funcionando después de la limpieza
        print("[10/10] Verificando que el trigger de creación de perfiles sigue funcionando...")
        try:
            # Verificar si el trigger existe
            trigger_check = supabase.rpc('exec_sql', {
                'query': """
                SELECT tgname as trigger_name, tgenabled as enabled
                FROM pg_trigger
                WHERE tgname = 'on_auth_user_created';
                """
            }).execute()
            
            if trigger_check.data:
                print("   ✅ Trigger 'on_auth_user_created' está configurado correctamente")
            else:
                print("   ⚠️  ADVERTENCIA: Trigger 'on_auth_user_created' NO existe")
                print("   ⚠️  Los nuevos registros NO crearán perfiles automáticamente")
                print("   ⚠️  Ejecuta el script 'reparar_trigger_perfiles.sql' para corregirlo")
        except Exception as e:
            print(f"   ⚠️  No se pudo verificar el trigger: {e}")
            print("   ℹ️  Verifica manualmente que el trigger existe en Supabase Dashboard")
        
        print("\n" + "="*60)
        print("✅ LIMPIEZA COMPLETADA")
        print("="*60)
        print("La base de datos está lista para pruebas finales con amigos.")
        print("Solo queda el usuario administrador y sus datos.")
        print()
        
    except Exception as e:
        print(f"\n[ERROR] Error durante la limpieza: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    print("="*60)
    print("LIMPIEZA COMPLETA DE BASE DE DATOS")
    print("="*60)
    print()
    print("⚠️  ADVERTENCIA: Este script es IRREVERSIBLE")
    print("   - Eliminará TODOS los usuarios excepto el admin")
    print("   - Eliminará usuarios de auth.users Y profiles")
    print("   - Eliminará TODOS los chats, mensajes y conversaciones")
    print("   - Eliminará TODOS los eventos de uso de modelos")
    print("   - Eliminará TODOS los pagos de Stripe de prueba")
    print("   - Eliminará TODOS los eventos de referidos")
    print("   - Limpiará todas las referencias de referidos")
    print("   - Eliminará usuarios huérfanos (en auth.users pero no en profiles)")
    print()
    print("   Solo se mantendrá el usuario administrador y sus datos.")
    print()
    
    # Verificar modo automático
    skip_confirmations = "--auto" in sys.argv or "--yes" in sys.argv
    
    if not skip_confirmations:
        try:
            confirm = input("¿Estás SEGURO? Escribe 'LIMPIAR TODO' para confirmar: ")
            if confirm != "LIMPIAR TODO":
                print("\n❌ Operación cancelada.")
                sys.exit(0)
        except EOFError:
            print("\n⚠️  No se puede leer input. Usa --auto para modo automático.")
            sys.exit(1)
    
    print()
    print("Obteniendo información del admin...")
    admin_user_id = get_admin_user_id()
    
    print()
    print("⚠️  ÚLTIMA ADVERTENCIA:")
    print(f"   Se eliminará TODO excepto el admin: {admin_user_id}")
    
    if not skip_confirmations:
        try:
            final_confirm = input("\n¿Proceder? (s/n): ")
            if final_confirm.lower() != 's':
                print("\n❌ Operación cancelada.")
                sys.exit(0)
        except EOFError:
            print("\n⚠️  No se puede leer input. Cancelando...")
            sys.exit(1)
    
    # Ejecutar limpieza
    limpiar_base_datos(admin_user_id)
    
    print("\n✅ Proceso completado exitosamente!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Operación cancelada por el usuario.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

