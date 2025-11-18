-- ============================================================================
-- AGREGAR COLUMNA fair_use_email_sent A LA TABLA PROFILES
-- ============================================================================
-- Esta columna marca si ya se envió el email de alerta al 90% de uso
-- para evitar enviar múltiples emails al mismo usuario
-- ============================================================================

-- Agregar columna fair_use_email_sent
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS fair_use_email_sent BOOLEAN DEFAULT FALSE;

-- Crear índice para búsquedas por fair_use_email_sent
CREATE INDEX IF NOT EXISTS profiles_fair_use_email_sent_idx ON public.profiles(fair_use_email_sent);

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. fair_use_email_sent: Se marca como TRUE cuando se envía el email de alerta al 90%
-- 2. Esta columna se resetea cuando se renueva la suscripción (invoice.paid)
-- 3. El email solo se envía una vez por ciclo de suscripción
-- ============================================================================

