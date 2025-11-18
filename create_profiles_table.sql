-- ============================================================================
-- SISTEMA DE PERFILES CON TOKENS PARA SAAS BOT
-- ============================================================================
-- Este script crea:
-- 1. Tabla 'profiles' vinculada a auth.users
-- 2. Función automática para crear perfiles al registrarse
-- 3. Trigger que ejecuta la función
-- 4. RLS (Row Level Security) habilitado
-- 5. Políticas de seguridad para que usuarios solo vean/editen su propio perfil
-- ============================================================================

-- 1. Crear la tabla "profiles" para guardar datos públicos (y los tokens)
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT,
  tokens_restantes BIGINT DEFAULT 20000,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índice para búsquedas por email (opcional pero recomendado)
CREATE INDEX IF NOT EXISTS profiles_email_idx ON profiles(email);

-- 2. Función para crear un "profile" automáticamente cuando un usuario nuevo se registra
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email)
  VALUES (NEW.id, NEW.email);
  RETURN NEW;
END;
$$;

-- 3. "Trigger" (Disparador) que ejecuta la función de arriba
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
  
-- 4. Habilitar RLS (Row Level Security) para proteger la tabla
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- 5. Crear políticas para que los usuarios SOLO puedan ver/editar SU PROPIO profile

-- Política para SELECT: usuarios pueden ver su propio profile
DROP POLICY IF EXISTS "Usuarios pueden ver su propio profile." ON public.profiles;
CREATE POLICY "Usuarios pueden ver su propio profile."
  ON public.profiles FOR SELECT
  USING ( auth.uid() = id );
  
-- Política para UPDATE: usuarios pueden actualizar su propio profile
DROP POLICY IF EXISTS "Usuarios pueden actualizar su propio profile." ON public.profiles;
CREATE POLICY "Usuarios pueden actualizar su propio profile."
  ON public.profiles FOR UPDATE
  USING ( auth.uid() = id );

-- ============================================================================
-- VERIFICACIÓN (opcional - puedes ejecutar estas consultas después)
-- ============================================================================
-- Verificar que la tabla existe:
-- SELECT * FROM information_schema.tables WHERE table_name = 'profiles';

-- Verificar que RLS está habilitado:
-- SELECT tablename, rowsecurity FROM pg_tables WHERE tablename = 'profiles';

-- Verificar las políticas creadas:
-- SELECT * FROM pg_policies WHERE tablename = 'profiles';

-- ============================================================================
-- NOTAS IMPORTANTES:
-- ============================================================================
-- 1. Cada usuario nuevo recibirá automáticamente 20,000 tokens al registrarse
-- 2. Los usuarios solo pueden ver y editar su propio perfil
-- 3. Si un usuario se elimina de auth.users, su perfil se elimina automáticamente (CASCADE)
-- 4. La función handle_new_user() se ejecuta con privilegios de seguridad (SECURITY DEFINER)
-- ============================================================================

