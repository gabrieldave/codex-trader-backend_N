#!/usr/bin/env python3
"""
Script para verificar y reparar el trigger de creación de perfiles
"""
import os
import sys
from supabase import create_client, Client
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def get_supabase_client() -> Client:
    """Crear cliente de Supabase usando URL y key"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY deben estar configurados")
    
    return create_client(supabase_url, supabase_key)

def verificar_trigger(supabase: Client):
    """Verificar si el trigger existe"""
    print("=" * 80)
    print("VERIFICANDO TRIGGER DE CREACIÓN DE PERFILES")
    print("=" * 80)
    
    query = """
    SELECT 
        tgname as trigger_name,
        tgrelid::regclass as table_name,
        tgenabled as enabled,
        pg_get_triggerdef(oid) as trigger_definition
    FROM pg_trigger
    WHERE tgname = 'on_auth_user_created';
    """
    
    try:
        result = supabase.rpc('exec_sql', {'query': query}).execute()
        if result.data:
            print("✅ Trigger 'on_auth_user_created' EXISTE")
            for row in result.data:
                print(f"   Nombre: {row.get('trigger_name')}")
                print(f"   Tabla: {row.get('table_name')}")
                print(f"   Habilitado: {row.get('enabled')}")
                return True
        else:
            print("❌ Trigger 'on_auth_user_created' NO EXISTE")
            return False
    except Exception as e:
        print(f"⚠️ Error al verificar trigger: {e}")
        # Intentar método alternativo
        try:
            result = supabase.table('pg_trigger').select('*').eq('tgname', 'on_auth_user_created').execute()
            if result.data:
                print("✅ Trigger encontrado (método alternativo)")
                return True
            else:
                print("❌ Trigger NO encontrado")
                return False
        except Exception as e2:
            print(f"⚠️ Método alternativo también falló: {e2}")
            print("   Asumiendo que el trigger no existe y procediendo a crearlo...")
            return False

def verificar_funcion(supabase: Client):
    """Verificar si la función existe"""
    print("\n" + "=" * 80)
    print("VERIFICANDO FUNCIÓN handle_new_user()")
    print("=" * 80)
    
    query = """
    SELECT 
        proname as function_name,
        prosrc as function_source
    FROM pg_proc
    WHERE proname = 'handle_new_user';
    """
    
    try:
        result = supabase.rpc('exec_sql', {'query': query}).execute()
        if result.data:
            print("✅ Función 'handle_new_user' EXISTE")
            for row in result.data:
                print(f"   Nombre: {row.get('function_name')}")
                source = row.get('function_source', '')[:200]  # Primeros 200 caracteres
                print(f"   Fuente: {source}...")
            return True
        else:
            print("❌ Función 'handle_new_user' NO EXISTE")
            return False
    except Exception as e:
        print(f"⚠️ Error al verificar función: {e}")
        return False

def crear_funcion_y_trigger(supabase: Client):
    """Crear la función y el trigger"""
    print("\n" + "=" * 80)
    print("CREANDO FUNCIÓN Y TRIGGER")
    print("=" * 80)
    
    # Primero, crear la función generate_referral_code si no existe
    funcion_referral = """
    CREATE OR REPLACE FUNCTION public.generate_referral_code(user_id UUID)
    RETURNS TEXT
    LANGUAGE plpgsql
    AS $$
    DECLARE
      code TEXT;
      exists_code BOOLEAN;
    BEGIN
      LOOP
        -- Generar código de 8 caracteres alfanuméricos
        code := UPPER(SUBSTRING(MD5(user_id::TEXT || RANDOM()::TEXT) FROM 1 FOR 8));
        
        -- Verificar si el código ya existe
        SELECT EXISTS(SELECT 1 FROM public.profiles WHERE referral_code = code) INTO exists_code;
        
        -- Si no existe, salir del loop
        IF NOT exists_code THEN
          EXIT;
        END IF;
      END LOOP;
      
      RETURN code;
    END;
    $$;
    """
    
    # Función handle_new_user actualizada
    funcion_handle_new_user = """
    CREATE OR REPLACE FUNCTION public.handle_new_user()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    SECURITY DEFINER SET search_path = public
    AS $$
    DECLARE
      ref_code TEXT;
    BEGIN
      -- Generar código de referido único
      ref_code := public.generate_referral_code(NEW.id);
      
      -- Crear el perfil con el código de referido y tokens iniciales
      INSERT INTO public.profiles (id, email, referral_code, tokens)
      VALUES (NEW.id, NEW.email, ref_code, 20000)
      ON CONFLICT (id) DO NOTHING;
      
      RETURN NEW;
    END;
    $$;
    """
    
    # Crear trigger
    crear_trigger = """
    DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
    CREATE TRIGGER on_auth_user_created
      AFTER INSERT ON auth.users
      FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
    """
    
    try:
        print("📝 Creando función generate_referral_code...")
        supabase.rpc('exec_sql', {'query': funcion_referral}).execute()
        print("   ✅ Función generate_referral_code creada")
        
        print("\n📝 Creando función handle_new_user...")
        supabase.rpc('exec_sql', {'query': funcion_handle_new_user}).execute()
        print("   ✅ Función handle_new_user creada")
        
        print("\n📝 Creando trigger on_auth_user_created...")
        supabase.rpc('exec_sql', {'query': crear_trigger}).execute()
        print("   ✅ Trigger on_auth_user_created creado")
        
        return True
    except Exception as e:
        print(f"❌ Error al crear función/trigger: {e}")
        print("\n⚠️ Intentando método alternativo usando direct SQL...")
        # Intentar método alternativo
        try:
            from supabase.client import Client as SupabaseClient
            # Usar el cliente directamente con SQL raw si está disponible
            print("   Método alternativo no disponible en este cliente")
            print("   Por favor, ejecuta el SQL manualmente en Supabase Dashboard:")
            print("\n" + "=" * 80)
            print("SQL PARA EJECUTAR EN SUPABASE DASHBOARD:")
            print("=" * 80)
            print(funcion_referral)
            print("\n" + funcion_handle_new_user)
            print("\n" + crear_trigger)
            return False
        except Exception as e2:
            print(f"   Error en método alternativo: {e2}")
            return False

def verificar_usuarios_huerfanos(supabase: Client):
    """Verificar si hay usuarios en auth.users sin perfil"""
    print("\n" + "=" * 80)
    print("VERIFICANDO USUARIOS HUÉRFANOS")
    print("=" * 80)
    
    query = """
    SELECT 
        u.id,
        u.email,
        u.created_at
    FROM auth.users u
    LEFT JOIN public.profiles p ON u.id = p.id
    WHERE p.id IS NULL
    ORDER BY u.created_at DESC
    LIMIT 10;
    """
    
    try:
        # No podemos consultar auth.users directamente, necesitamos usar una función RPC
        # Intentar método alternativo
        print("⚠️ No se puede consultar auth.users directamente")
        print("   Verificando en profiles si hay usuarios recientes sin perfil...")
        return []
    except Exception as e:
        print(f"⚠️ Error al verificar usuarios huérfanos: {e}")
        return []

def crear_perfil_para_usuario_huerfano(supabase: Client, user_id: str, email: str):
    """Crear perfil para un usuario huérfano"""
    print(f"\n📝 Creando perfil para usuario huérfano: {email} ({user_id})...")
    
    try:
        # Generar código de referido
        ref_code = f"REF{user_id[:8].upper()}"
        
        # Intentar insertar el perfil
        result = supabase.table('profiles').insert({
            'id': user_id,
            'email': email,
            'referral_code': ref_code,
            'tokens': 20000
        }).execute()
        
        print(f"   ✅ Perfil creado exitosamente")
        return True
    except Exception as e:
        print(f"   ❌ Error al crear perfil: {e}")
        return False

def main():
    """Función principal"""
    print("=" * 80)
    print("SCRIPT DE VERIFICACIÓN Y REPARACIÓN DE TRIGGER DE PERFILES")
    print("=" * 80)
    print()
    
    try:
        supabase = get_supabase_client()
        print("✅ Cliente de Supabase inicializado\n")
    except Exception as e:
        print(f"❌ Error al inicializar Supabase: {e}")
        sys.exit(1)
    
    # Verificar función
    funcion_existe = verificar_funcion(supabase)
    
    # Verificar trigger
    trigger_existe = verificar_trigger(supabase)
    
    # Si alguno no existe, crearlo
    if not funcion_existe or not trigger_existe:
        print("\n" + "=" * 80)
        print("REPARACIÓN NECESARIA")
        print("=" * 80)
        respuesta = input("\n¿Deseas crear/reparar la función y el trigger? (s/n): ").strip().lower()
        if respuesta == 's':
            if crear_funcion_y_trigger(supabase):
                print("\n✅ Función y trigger creados/reparados exitosamente")
            else:
                print("\n⚠️ No se pudo crear automáticamente. Por favor, ejecuta el SQL manualmente en Supabase Dashboard.")
        else:
            print("\n⚠️ Reparación cancelada. El trigger debe estar configurado para que los registros funcionen correctamente.")
    else:
        print("\n✅ La función y el trigger están configurados correctamente")
        print("\n⚠️ Si sigues teniendo problemas, el usuario podría estar en auth.users sin perfil.")
        print("   En ese caso, ejecuta el script 'crear_perfiles_usuarios_huerfanos.py'")
    
    print("\n" + "=" * 80)
    print("VERIFICACIÓN COMPLETADA")
    print("=" * 80)

if __name__ == "__main__":
    main()

