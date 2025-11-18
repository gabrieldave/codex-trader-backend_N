-- ============================================================================
-- CREAR TABLAS COMPLETAS PARA SISTEMA DE CONVERSACIONES
-- ============================================================================
-- Este script crea todas las tablas necesarias para el sistema de conversaciones
-- ============================================================================

-- 1. Crear la tabla "conversations" para guardar mensajes individuales
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_id UUID,  -- Se agregará la referencia después de crear chat_sessions
  message_role TEXT NOT NULL CHECK (message_role IN ('user', 'assistant')),
  message_content TEXT NOT NULL,
  tokens_used INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc'::text, NOW()) NOT NULL
);

-- Crear índices para búsquedas rápidas por usuario
CREATE INDEX IF NOT EXISTS conversations_user_id_idx ON conversations(user_id);
CREATE INDEX IF NOT EXISTS conversations_created_at_idx ON conversations(created_at DESC);

-- 2. Crear la tabla "chat_sessions" para agrupar conversaciones
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

-- 3. Agregar referencia de conversation_id a chat_sessions si no existe
DO $$ 
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints 
    WHERE constraint_name = 'conversations_conversation_id_fkey'
  ) THEN
    ALTER TABLE conversations 
      ADD CONSTRAINT conversations_conversation_id_fkey 
      FOREIGN KEY (conversation_id) REFERENCES chat_sessions(id) ON DELETE CASCADE;
  END IF;
END $$;

-- Crear índice para búsquedas rápidas por conversación
CREATE INDEX IF NOT EXISTS conversations_conversation_id_idx ON conversations(conversation_id);

-- 4. Habilitar RLS (Row Level Security) en conversations
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;

-- Política para SELECT: usuarios pueden ver solo sus propias conversaciones
DROP POLICY IF EXISTS "Usuarios pueden ver sus propias conversaciones" ON public.conversations;
CREATE POLICY "Usuarios pueden ver sus propias conversaciones"
  ON public.conversations FOR SELECT
  USING ( auth.uid() = user_id );

-- Política para INSERT: usuarios pueden crear solo sus propias conversaciones
DROP POLICY IF EXISTS "Usuarios pueden crear sus propias conversaciones" ON public.conversations;
CREATE POLICY "Usuarios pueden crear sus propias conversaciones"
  ON public.conversations FOR INSERT
  WITH CHECK ( auth.uid() = user_id );

-- Política para DELETE: usuarios pueden eliminar solo sus propias conversaciones
DROP POLICY IF EXISTS "Usuarios pueden eliminar sus propias conversaciones" ON public.conversations;
CREATE POLICY "Usuarios pueden eliminar sus propias conversaciones"
  ON public.conversations FOR DELETE
  USING ( auth.uid() = user_id );

-- 5. Habilitar RLS (Row Level Security) en chat_sessions
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;

-- Política para SELECT: usuarios pueden ver solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden ver sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden ver sus propias sesiones"
  ON public.chat_sessions FOR SELECT
  USING ( auth.uid() = user_id );

-- Política para INSERT: usuarios pueden crear solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden crear sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden crear sus propias sesiones"
  ON public.chat_sessions FOR INSERT
  WITH CHECK ( auth.uid() = user_id );

-- Política para UPDATE: usuarios pueden actualizar solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden actualizar sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden actualizar sus propias sesiones"
  ON public.chat_sessions FOR UPDATE
  USING ( auth.uid() = user_id )
  WITH CHECK ( auth.uid() = user_id );

-- Política para DELETE: usuarios pueden eliminar solo sus propias sesiones
DROP POLICY IF EXISTS "Usuarios pueden eliminar sus propias sesiones" ON public.chat_sessions;
CREATE POLICY "Usuarios pueden eliminar sus propias sesiones"
  ON public.chat_sessions FOR DELETE
  USING ( auth.uid() = user_id );

-- 6. Función para actualizar updated_at automáticamente en chat_sessions
CREATE OR REPLACE FUNCTION update_chat_sessions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = TIMEZONE('utc'::text, NOW());
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 7. Función para actualizar updated_at de chat_sessions cuando se inserta un mensaje
CREATE OR REPLACE FUNCTION update_chat_sessions_updated_at_via_conversations()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.conversation_id IS NOT NULL THEN
    UPDATE chat_sessions
    SET updated_at = TIMEZONE('utc'::text, NOW())
    WHERE id = NEW.conversation_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 8. Trigger para actualizar updated_at cuando se inserta un mensaje
DROP TRIGGER IF EXISTS update_chat_sessions_updated_at_trigger ON conversations;
CREATE TRIGGER update_chat_sessions_updated_at_trigger
  AFTER INSERT ON conversations
  FOR EACH ROW
  WHEN (NEW.conversation_id IS NOT NULL)
  EXECUTE FUNCTION update_chat_sessions_updated_at_via_conversations();

-- ============================================================================
-- NOTAS:
-- ============================================================================
-- 1. Cada sesión de chat (chat_sessions) agrupa múltiples mensajes (conversations)
-- 2. Los usuarios solo pueden ver/crear/actualizar/eliminar sus propias sesiones
-- 3. La columna conversation_id en conversations referencia chat_sessions.id
-- 4. El título se genera automáticamente basado en el primer mensaje (en el código)
-- 5. updated_at se actualiza automáticamente cuando se agregan mensajes
-- ============================================================================












