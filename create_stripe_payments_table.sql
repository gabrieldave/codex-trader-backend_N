-- ============================================================================
-- TABLA PARA REGISTRAR PAGOS DE STRIPE
-- ============================================================================
-- Esta tabla registra los pagos procesados de Stripe para análisis de ingresos
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.stripe_payments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id TEXT UNIQUE NOT NULL,  -- ID de la invoice de Stripe
  customer_id TEXT NOT NULL,        -- ID del cliente en Stripe
  user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
  plan_code TEXT,                   -- Código del plan (explorer, trader, pro, institucional)
  amount_usd NUMERIC(10, 2) NOT NULL,  -- Monto pagado en USD
  currency TEXT DEFAULT 'usd',
  payment_date TIMESTAMP WITH TIME ZONE NOT NULL,  -- Fecha del pago
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS stripe_payments_invoice_id_idx ON public.stripe_payments(invoice_id);
CREATE INDEX IF NOT EXISTS stripe_payments_user_id_idx ON public.stripe_payments(user_id);
CREATE INDEX IF NOT EXISTS stripe_payments_payment_date_idx ON public.stripe_payments(payment_date);
CREATE INDEX IF NOT EXISTS stripe_payments_plan_code_idx ON public.stripe_payments(plan_code);

-- Índice compuesto para consultas de ingresos por fecha
CREATE INDEX IF NOT EXISTS stripe_payments_date_amount_idx ON public.stripe_payments(payment_date, amount_usd);

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. Esta tabla se puede poblar desde los webhooks de Stripe (invoice.paid)
-- 2. También se puede consultar Stripe directamente como fuente de verdad
-- 3. Los índices permiten consultas rápidas para análisis de ingresos
-- ============================================================================

