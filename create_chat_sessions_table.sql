-- ============================================================================
-- TABLA DE SESIONES DE CHAT (CONVERSACIONES)
-- ============================================================================
-- Esta tabla agrupa mensajes en conversaciones/sesiones de chat
-- ============================================================================

-- 1. Crear la tabla "chat_sessions" para agrupar conversaciones
CREATE TABLE IF NOT EXISTS chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS chat_sessions_user_id_idx ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS chat_sessions_updated_at_idx ON chat_sessions(updated_at DESC);

-- 2. Agregar columna conversation_id a la tabla conversations si no existe
ALTER TABLE conversations 
  ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE;

-- Crear índice para búsquedas rápidas por conversación
CREATE INDEX IF NOT EXISTS conversations_conversation_id_idx ON conversations(conversation_id);

-- 3. Habilitar RLS (Row Level Security) en chat_sessions
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

-- 4. Política para SELECT: usuarios pueden ver solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden ver sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden ver sus propias sesiones"
  ON public.chat_sessions FOR SELECT
  USING ( auth.uid() = user_id );

-- 5. Política para INSERT: usuarios pueden crear solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden crear sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden crear sus propias sesiones"
  ON public.chat_sessions FOR INSERT
  WITH CHECK ( auth.uid() = user_id );

-- 6. Política para UPDATE: usuarios pueden actualizar solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden actualizar sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden actualizar sus propias sesiones"
  ON public.chat_sessions FOR UPDATE
  USING ( auth.uid() = user_id )
  WITH CHECK ( auth.uid() = user_id );

-- 7. Política para DELETE: usuarios pueden eliminar solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden eliminar sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden eliminar sus propias sesiones"
  ON public.chat_sessions FOR DELETE
  USING ( auth.uid() = user_id );

-- 8. Función para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION update_chat_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = TIMEZONE('utc'::text, NOW());
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 9. Función auxiliar para actualizar updated_at de chat_sessions cuando se inserta un mensaje
CREATE OR REPLACE FUNCTION update_chat_sessions_updated_at_via_conversations()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE chat_sessions
  SET updated_at = TIMEZONE('utc'::text, NOW())
  WHERE id = NEW.conversation_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 10. Trigger para actualizar updated_at cuando se inserta un mensaje
DROP TRIGGER IF EXISTS update_chat_sessions_updated_at_trigger ON conversations;
CREATE TRIGGER update_chat_sessions_updated_at_trigger
  AFTER INSERT ON conversations
  FOR EACH ROW
  WHEN (NEW.conversation_id IS NOT NULL)
  EXECUTE FUNCTION update_chat_sessions_updated_at_via_conversations();

-- 11. Función para generar título automático basado en el primer mensaje
CREATE OR REPLACE FUNCTION generate_chat_session_title()
RETURNS TRIGGER AS $$
BEGIN
  -- Si no hay título, generar uno basado en el primer mensaje del usuario
  IF NEW.title IS NULL OR NEW.title = '' THEN
    SELECT LEFT(message_content, 50)
    INTO NEW.title
    FROM conversations
    WHERE conversation_id = NEW.id
      AND message_role = 'user'
    ORDER BY created_at ASC
    LIMIT 1;
    
    -- Si aún no hay título, usar uno por defecto
    IF NEW.title IS NULL OR NEW.title = '' THEN
      NEW.title = 'Nueva conversación';
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 12. Trigger para generar título automático al crear una sesión (deshabilitado por ahora)
-- DROP TRIGGER IF EXISTS generate_chat_session_title_trigger ON chat_sessions;
-- CREATE TRIGGER generate_chat_session_title_trigger
--   BEFORE INSERT ON chat_sessions
--   FOR EACH ROW
--   EXECUTE FUNCTION generate_chat_session_title();

-- ============================================================================
-- NOTAS:
-- ============================================================================
-- 1. Cada sesión de chat agrupa múltiples mensajes (conversaciones)
-- 2. Los usuarios solo pueden ver/crear/actualizar/eliminar sus propias sesiones
-- 3. La columna conversation_id en conversations referencia chat_sessions.id
-- 4. El título se genera automáticamente basado en el primer mensaje
-- 5. updated_at se actualiza automáticamente cuando se agregan mensajes
-- ============================================================================
