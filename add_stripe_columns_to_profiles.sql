-- ============================================================================
-- AGREGAR COLUMNAS DE STRIPE A LA TABLA PROFILES
-- ============================================================================
-- Este script agrega las columnas necesarias para manejar suscripciones de Stripe
-- en la tabla profiles.
-- ============================================================================

-- Agregar columna stripe_customer_id (ID del cliente en Stripe)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;

-- Agregar columna current_plan (código del plan actual: explorer, trader, pro, institucional)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS current_plan TEXT;

-- Agregar columna current_period_end (fecha de fin del período actual de suscripción)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMP WITH TIME ZONE;

-- Crear índice para búsquedas rápidas por stripe_customer_id
CREATE INDEX IF NOT EXISTS profiles_stripe_customer_id_idx ON public.profiles(stripe_customer_id);

-- Crear índice para búsquedas por current_plan
CREATE INDEX IF NOT EXISTS profiles_current_plan_idx ON public.profiles(current_plan);

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. stripe_customer_id: Se actualiza cuando el usuario completa el checkout
-- 2. current_plan: Se actualiza cuando se completa el checkout o se renueva la suscripción
-- 3. current_period_end: Se actualiza cuando se completa el checkout o se renueva la suscripción
-- 4. tokens_restantes: Se actualiza mensualmente cuando se paga la invoice (invoice.paid)
-- 
-- El frontend puede leer estos campos desde:
-- - /app/billing: Para mostrar información de facturación
-- - Chat: Para mostrar el plan actual y saldo de tokens
-- ============================================================================

