-- ============================================================================
-- TABLA DE HISTORIAL DE CONVERSACIONES
-- ============================================================================
-- Esta tabla guarda el historial de conversaciones de cada usuario
-- ============================================================================

-- 1. Crear la tabla "conversations" para guardar el historial
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  message_role TEXT NOT NULL CHECK (message_role IN ('user', 'assistant')),
  message_content TEXT NOT NULL,
  tokens_used INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índice para búsquedas rápidas por usuario
CREATE INDEX IF NOT EXISTS conversations_user_id_idx ON conversations(user_id);
CREATE INDEX IF NOT EXISTS conversations_created_at_idx ON conversations(created_at DESC);

-- 2. Habilitar RLS (Row Level Security)
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

-- 3. Política para SELECT: usuarios pueden ver solo sus propias conversaciones
DROP POLICY IF EXISTS "Usuarios pueden ver sus propias conversaciones" ON public.conversations;
CREATE POLICY "Usuarios pueden ver sus propias conversaciones"
  ON public.conversations FOR SELECT
  USING ( auth.uid() = user_id );

-- 4. Política para INSERT: usuarios pueden crear solo sus propias conversaciones
DROP POLICY IF EXISTS "Usuarios pueden crear sus propias conversaciones" ON public.conversations;
CREATE POLICY "Usuarios pueden crear sus propias conversaciones"
  ON public.conversations FOR INSERT
  WITH CHECK ( auth.uid() = user_id );

-- 5. Política para DELETE: usuarios pueden eliminar solo sus propias conversaciones
DROP POLICY IF EXISTS "Usuarios pueden eliminar sus propias conversaciones" ON public.conversations;
CREATE POLICY "Usuarios pueden eliminar sus propias conversaciones"
  ON public.conversations FOR DELETE
  USING ( auth.uid() = user_id );

-- ============================================================================
-- NOTAS:
-- ============================================================================
-- 1. Cada mensaje (usuario o asistente) se guarda como una fila separada
-- 2. Los usuarios solo pueden ver/crear/eliminar sus propias conversaciones
-- 3. Se guarda la cantidad de tokens usados para cada respuesta del asistente
-- 4. Los índices permiten búsquedas rápidas por usuario y fecha
-- ============================================================================



