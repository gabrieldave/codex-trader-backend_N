-- ============================================================================
-- TABLA PARA REGISTRAR USO DE MODELOS DE IA
-- ============================================================================
-- Esta tabla registra cada llamada a modelos de IA para monitorear costos
-- y controlar márgenes.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.model_usage_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
  provider TEXT NOT NULL,  -- Ej: "deepseek", "openai", "anthropic"
  model TEXT NOT NULL,      -- Ej: "deepseek-chat", "deepseek-r1", "gpt-3.5-turbo"
  tokens_input INTEGER NOT NULL DEFAULT 0,
  tokens_output INTEGER NOT NULL DEFAULT 0,
  cost_estimated_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,  -- Costo estimado en USD
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS model_usage_events_user_id_idx ON public.model_usage_events(user_id);
CREATE INDEX IF NOT EXISTS model_usage_events_provider_idx ON public.model_usage_events(provider);
CREATE INDEX IF NOT EXISTS model_usage_events_model_idx ON public.model_usage_events(model);
CREATE INDEX IF NOT EXISTS model_usage_events_created_at_idx ON public.model_usage_events(created_at);

-- Índice compuesto para consultas de costos por usuario y fecha
CREATE INDEX IF NOT EXISTS model_usage_events_user_created_idx ON public.model_usage_events(user_id, created_at);

-- ============================================================================
-- NOTAS
-- ============================================================================
-- 1. user_id puede ser NULL si la request no está asociada a un usuario
-- 2. cost_estimated_usd se calcula usando las constantes de costo por millón
--    definidas en el archivo de configuración del backend
-- 3. Los índices permiten consultas rápidas para:
--    - Costos por usuario
--    - Costos por proveedor/modelo
--    - Análisis de uso por fecha
-- ============================================================================

