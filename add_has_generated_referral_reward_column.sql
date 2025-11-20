-- ============================================================================
-- AGREGAR COLUMNA has_generated_referral_reward A LA TABLA PROFILES
-- ============================================================================
-- Esta columna se usa para rastrear si un usuario ya generó una recompensa
-- de referido (cuando paga su primera suscripción)
-- ============================================================================

-- Agregar columna has_generated_referral_reward
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS has_generated_referral_reward BOOLEAN DEFAULT FALSE;

-- Crear índice para búsquedas rápidas
CREATE INDEX IF NOT EXISTS profiles_has_generated_referral_reward_idx 
ON public.profiles(has_generated_referral_reward) 
WHERE has_generated_referral_reward = TRUE;

-- ============================================================================
-- NOTAS
-- ============================================================================
-- Esta columna se marca como TRUE cuando un usuario referido paga su primera
-- suscripción, activando la recompensa para el usuario que lo invitó.
-- ============================================================================










