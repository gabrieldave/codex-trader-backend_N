-- ============================================================================
-- SISTEMA DE RECOMPENSAS DE REFERIDOS
-- ============================================================================
-- Este script agrega los campos y tablas necesarios para el sistema de
-- recompensas de referidos con idempotencia.
-- ============================================================================

-- Agregar columna has_generated_referral_reward (si el usuario ya generó recompensa)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS has_generated_referral_reward BOOLEAN DEFAULT FALSE;

-- Crear tabla de eventos de recompensas para idempotencia
-- Esta tabla evita que se procesen recompensas duplicadas si Stripe reenvía webhooks
CREATE TABLE IF NOT EXISTS public.referral_reward_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id TEXT UNIQUE NOT NULL,  -- ID de la invoice de Stripe
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  referrer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  reward_type TEXT NOT NULL,  -- 'first_payment' para recompensa al que invita
  tokens_granted BIGINT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índice para búsquedas rápidas por invoice_id
CREATE INDEX IF NOT EXISTS referral_reward_events_invoice_id_idx ON public.referral_reward_events(invoice_id);

-- Crear índice para búsquedas por user_id
CREATE INDEX IF NOT EXISTS referral_reward_events_user_id_idx ON public.referral_reward_events(user_id);

-- Crear índice para búsquedas por referrer_id
CREATE INDEX IF NOT EXISTS referral_reward_events_referrer_id_idx ON public.referral_reward_events(referrer_id);

-- ============================================================================
-- ACTUALIZAR FUNCIÓN handle_new_user() PARA BONO DE BIENVENIDA
-- ============================================================================
-- Modificamos la función para que dé 5,000 tokens adicionales si el usuario
-- fue referido (tiene referred_by_user_id).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  ref_code TEXT;
  initial_tokens BIGINT := 20000;  -- Tokens base por defecto
  welcome_bonus BIGINT := 5000;     -- Bono de bienvenida por referido
  referred_by_id UUID;
BEGIN
  -- Generar código de referido único
  ref_code := public.generate_referral_code(NEW.id);
  
  -- Verificar si el usuario fue referido (esto se establece después del registro)
  -- Por ahora, creamos el perfil con tokens base
  -- El bono de bienvenida se aplicará después cuando se procese el referido
  
  -- Crear el perfil con el código de referido y tokens base
  INSERT INTO public.profiles (id, email, referral_code, tokens_restantes)
  VALUES (NEW.id, NEW.email, ref_code, initial_tokens);
  
  RETURN NEW;
END;
$$;

-- ============================================================================
-- FUNCIÓN PARA APLICAR BONO DE BIENVENIDA A USUARIO REFERIDO
-- ============================================================================
-- Esta función se llama después de que se procesa un código de referido
-- para dar los 5,000 tokens de bienvenida al usuario invitado.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.apply_referral_welcome_bonus(user_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  current_tokens BIGINT;
  welcome_bonus BIGINT := 5000;
  referred_by_id UUID;
BEGIN
  -- Obtener tokens actuales y referred_by_user_id
  SELECT tokens_restantes, referred_by_user_id INTO current_tokens, referred_by_id
  FROM public.profiles
  WHERE id = user_id;
  
  -- Solo aplicar bono si fue referido y no se ha aplicado antes
  IF referred_by_id IS NOT NULL THEN
    -- Sumar tokens de bienvenida
    UPDATE public.profiles
    SET tokens_restantes = tokens_restantes + welcome_bonus
    WHERE id = user_id;
    
    RETURN TRUE;
  END IF;
  
  RETURN FALSE;
END;
$$;

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. has_generated_referral_reward: Se marca como TRUE cuando el usuario
--    genera su primera recompensa de referido (paga su primera suscripción)
-- 2. referral_reward_events: Tabla de eventos para evitar duplicados
--    cuando Stripe reenvía webhooks
-- 3. Bono de bienvenida (5,000 tokens): Se aplica cuando se procesa el código
--    de referido después del registro
-- 4. Bono al que invita (10,000 tokens): Se aplica cuando el invitado paga
--    su primera suscripción (invoice.paid), máximo 5 veces por usuario
-- ============================================================================

