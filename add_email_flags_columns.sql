-- ============================================================================
-- AGREGAR COLUMNAS PARA FLAGS DE EMAILS EN LA TABLA PROFILES
-- ============================================================================
-- Este script agrega las columnas necesarias para evitar duplicados en los emails
-- ============================================================================

-- Columna para email de tokens agotados
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS tokens_exhausted_email_sent BOOLEAN DEFAULT FALSE;

-- Columna para recordatorio de renovación
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS renewal_reminder_sent BOOLEAN DEFAULT FALSE;

-- Columna para email de recuperación de usuarios inactivos
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS inactive_recovery_email_sent BOOLEAN DEFAULT FALSE;

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. tokens_exhausted_email_sent: Se marca como TRUE cuando se envía el email
--    de tokens agotados para evitar duplicados
-- 2. renewal_reminder_sent: Se marca como TRUE cuando se envía el recordatorio
--    de renovación (se resetea cuando se renueva la suscripción)
-- 3. inactive_recovery_email_sent: Se marca como TRUE cuando se envía el email
--    de recuperación para evitar duplicados
-- ============================================================================

