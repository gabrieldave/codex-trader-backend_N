-- ============================================================================
-- AGREGAR COLUMNAS DE REFERIDOS A LA TABLA PROFILES
-- ============================================================================
-- Este script agrega las columnas necesarias para el sistema de referidos
-- en la tabla profiles.
-- ============================================================================

-- Agregar columna referral_code (código único de referido, ej: "TST-7G3KZ")
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS referral_code TEXT UNIQUE;

-- Agregar columna referred_by_user_id (ID del usuario que invitó, si aplica)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS referred_by_user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL;

-- Agregar columna referral_rewards_count (cuántos referidos han generado recompensa)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS referral_rewards_count INTEGER DEFAULT 0;

-- Agregar columna referral_tokens_earned (tokens totales obtenidos por referidos)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS referral_tokens_earned BIGINT DEFAULT 0;

-- Crear índice para búsquedas rápidas por referral_code
CREATE INDEX IF NOT EXISTS profiles_referral_code_idx ON public.profiles(referral_code);

-- Crear índice para búsquedas por referred_by_user_id
CREATE INDEX IF NOT EXISTS profiles_referred_by_user_id_idx ON public.profiles(referred_by_user_id);

-- ============================================================================
-- FUNCIÓN PARA GENERAR CÓDIGO DE REFERIDO ÚNICO
-- ============================================================================
-- Esta función genera un código de referido único en formato: 3-4 letras + 4-6 caracteres
-- Ejemplo: "TST-7G3KZ"
-- ============================================================================

CREATE OR REPLACE FUNCTION public.generate_referral_code(user_id UUID)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  prefix TEXT;
  suffix TEXT;
  code TEXT;
  exists_check INTEGER;
  max_attempts INTEGER := 10;
  attempts INTEGER := 0;
BEGIN
  -- Prefijo: primeras 3 letras del email o "TST" por defecto
  -- Tomamos las primeras 3 letras del ID del usuario convertidas a mayúsculas
  prefix := UPPER(SUBSTRING(user_id::TEXT FROM 1 FOR 3));
  
  -- Si el prefijo no tiene suficientes letras, usar "TST"
  IF LENGTH(REGEXP_REPLACE(prefix, '[^A-Z]', '', 'g')) < 2 THEN
    prefix := 'TST';
  ELSE
    -- Tomar solo las primeras 3 letras válidas
    prefix := UPPER(REGEXP_REPLACE(SUBSTRING(user_id::TEXT FROM 1 FOR 10), '[^A-Z]', '', 'g'));
    IF LENGTH(prefix) < 2 THEN
      prefix := 'TST';
    ELSE
      prefix := SUBSTRING(prefix FROM 1 FOR 3);
    END IF;
  END IF;
  
  -- Generar código hasta encontrar uno único
  LOOP
    -- Sufijo: 4-6 caracteres alfanuméricos aleatorios
    suffix := UPPER(
      SUBSTRING(
        MD5(RANDOM()::TEXT || user_id::TEXT || NOW()::TEXT) 
        FROM 1 FOR 5
      )
    );
    
    -- Formato: PREFIJO-SUFIJO (ej: TST-7G3KZ)
    code := prefix || '-' || suffix;
    
    -- Verificar si el código ya existe
    SELECT COUNT(*) INTO exists_check
    FROM public.profiles
    WHERE referral_code = code;
    
    -- Si no existe, salir del loop
    EXIT WHEN exists_check = 0;
    
    -- Incrementar intentos
    attempts := attempts + 1;
    
    -- Si se exceden los intentos, usar un código basado en timestamp
    IF attempts >= max_attempts THEN
      code := prefix || '-' || UPPER(SUBSTRING(MD5(user_id::TEXT || NOW()::TEXT) FROM 1 FOR 5));
      -- Verificar una vez más
      SELECT COUNT(*) INTO exists_check
      FROM public.profiles
      WHERE referral_code = code;
      
      IF exists_check = 0 THEN
        EXIT;
      END IF;
      
      -- Último recurso: usar timestamp
      code := prefix || '-' || UPPER(SUBSTRING(MD5(user_id::TEXT || EXTRACT(EPOCH FROM NOW())::TEXT) FROM 1 FOR 5));
      EXIT;
    END IF;
  END LOOP;
  
  RETURN code;
END;
$$;

-- ============================================================================
-- ACTUALIZAR FUNCIÓN handle_new_user() PARA GENERAR CÓDIGO DE REFERIDO
-- ============================================================================
-- Modificamos la función existente para que genere automáticamente un código
-- de referido al crear un nuevo usuario.
-- ============================================================================

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
  
  -- Crear el perfil con el código de referido
  INSERT INTO public.profiles (id, email, referral_code)
  VALUES (NEW.id, NEW.email, ref_code);
  
  RETURN NEW;
END;
$$;

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. referral_code: Se genera automáticamente al crear un usuario
-- 2. referred_by_user_id: Se establece cuando un usuario se registra con un código de referido
-- 3. referral_rewards_count: Se incrementa cuando un referido genera una recompensa
-- 4. referral_tokens_earned: Se incrementa con los tokens ganados por referidos
-- 
-- Para usar un código de referido al registrarse:
-- - El frontend debe pasar el parámetro ?ref=XXXX en la URL de registro
-- - Después del registro, llamar al endpoint POST /referrals/process con el código
-- ============================================================================

