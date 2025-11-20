-- ============================================================================
-- REPARAR TRIGGER DE CREACIÓN DE PERFILES
-- ============================================================================
-- Este script verifica y repara el trigger que crea perfiles automáticamente
-- cuando un usuario se registra en auth.users
-- ============================================================================

-- 1. Crear función generate_referral_code si no existe
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

-- 2. Crear/actualizar función handle_new_user
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
  -- Usar ON CONFLICT para evitar errores si el perfil ya existe
  INSERT INTO public.profiles (id, email, referral_code, tokens)
  VALUES (NEW.id, NEW.email, ref_code, 20000)
  ON CONFLICT (id) DO NOTHING;
  
  RETURN NEW;
END;
$$;

-- 3. Eliminar trigger existente si existe y recrearlo
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW 
  EXECUTE FUNCTION public.handle_new_user();

-- 4. Verificar que el trigger se creó correctamente
SELECT 
    tgname as trigger_name,
    tgrelid::regclass as table_name,
    tgenabled as enabled,
    pg_get_triggerdef(oid) as trigger_definition
FROM pg_trigger
WHERE tgname = 'on_auth_user_created';

-- 5. Verificar que la función existe
SELECT 
    proname as function_name,
    prosrc as function_source
FROM pg_proc
WHERE proname = 'handle_new_user';

-- ============================================================================
-- NOTA: Si hay usuarios huérfanos (en auth.users pero no en profiles),
-- ejecuta este SQL para crearles perfiles:
-- ============================================================================
-- INSERT INTO public.profiles (id, email, referral_code, tokens)
-- SELECT 
--     u.id,
--     u.email,
--     'REF-' || UPPER(SUBSTRING(u.id::TEXT FROM 1 FOR 8)),
--     20000
-- FROM auth.users u
-- WHERE u.id NOT IN (SELECT id FROM public.profiles)
-- ON CONFLICT (id) DO NOTHING;
-- ============================================================================

