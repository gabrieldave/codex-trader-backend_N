-- ============================================================================
-- AGREGAR COLUMNAS DE USO JUSTO (FAIR USE) A LA TABLA PROFILES
-- ============================================================================
-- Este script agrega las columnas necesarias para el sistema de uso justo
-- y elegibilidad para descuento del 20% en la tabla profiles.
-- ============================================================================

-- Agregar columna tokens_monthly_limit (límite mensual según el plan)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS tokens_monthly_limit BIGINT;

-- Agregar columna fair_use_warning_shown (si se mostró aviso suave al 80%)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS fair_use_warning_shown BOOLEAN DEFAULT FALSE;

-- Agregar columna fair_use_discount_eligible (si es elegible para descuento al 90%)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS fair_use_discount_eligible BOOLEAN DEFAULT FALSE;

-- Agregar columna fair_use_discount_used (si ya usó el descuento en este ciclo)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS fair_use_discount_used BOOLEAN DEFAULT FALSE;

-- Agregar columna fair_use_discount_eligible_at (fecha cuando se volvió elegible)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS fair_use_discount_eligible_at TIMESTAMP WITH TIME ZONE;

-- Crear índice para búsquedas por fair_use_discount_eligible
CREATE INDEX IF NOT EXISTS profiles_fair_use_discount_eligible_idx ON public.profiles(fair_use_discount_eligible);

-- ============================================================================
-- ACTUALIZAR USUARIOS EXISTENTES
-- ============================================================================
-- Para usuarios existentes sin plan, establecer tokens_monthly_limit basado en tokens_restantes
-- o un valor por defecto. Esto se actualizará cuando se renueve o cambie el plan.
-- ============================================================================

-- Establecer tokens_monthly_limit para usuarios existentes sin límite
-- Si tienen tokens_restantes > 0, usar ese valor como límite temporal
UPDATE public.profiles
SET tokens_monthly_limit = tokens_restantes
WHERE tokens_monthly_limit IS NULL AND tokens_restantes > 0;

-- Para usuarios sin tokens o sin límite, usar un valor por defecto (20,000)
UPDATE public.profiles
SET tokens_monthly_limit = 20000
WHERE tokens_monthly_limit IS NULL;

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. tokens_monthly_limit: Se actualiza cuando se renueva o cambia el plan
--    (en el webhook invoice.paid) con el valor de tokensPerMonth del plan
-- 2. fair_use_warning_shown: Se marca como TRUE cuando el usuario alcanza 80% de uso
-- 3. fair_use_discount_eligible: Se marca como TRUE cuando el usuario alcanza 90% de uso
-- 4. fair_use_discount_used: Se marca como TRUE cuando el usuario usa el descuento
-- 5. Todos estos campos se resetean cuando se renueva la suscripción (invoice.paid)
-- 
-- El frontend puede leer estos valores desde GET /me/usage para mostrar
-- el estado de uso justo en el chat y en la página de billing.
-- ============================================================================

