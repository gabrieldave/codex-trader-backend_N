-- ============================================================================
-- AGREGAR COLUMNAS PARA FLAGS DE EMAILS CRÍTICOS
-- ============================================================================
-- Este script agrega las columnas necesarias para evitar duplicados en emails críticos
-- ============================================================================

-- Columna para email de bienvenida
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS welcome_email_sent BOOLEAN DEFAULT FALSE;

-- Columna para email de confirmación de recarga de tokens
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS tokens_reload_email_sent BOOLEAN DEFAULT FALSE;

-- Crear índices para búsquedas eficientes
CREATE INDEX IF NOT EXISTS profiles_welcome_email_sent_idx ON public.profiles(welcome_email_sent);
CREATE INDEX IF NOT EXISTS profiles_tokens_reload_email_sent_idx ON public.profiles(tokens_reload_email_sent);

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. welcome_email_sent: Se marca como TRUE cuando se envía el email de bienvenida
--    para evitar duplicados. NO se resetea (es un email único por usuario)
-- 2. tokens_reload_email_sent: Se marca como TRUE cuando se envía el email de confirmación
--    de recarga. Se resetea cuando se hace una nueva recarga exitosa
-- ============================================================================

