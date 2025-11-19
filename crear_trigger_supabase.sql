-- ============================================================================
-- OPCIÓN 1: TRIGGER EN SUPABASE (RECOMENDADO)
-- ============================================================================
-- Este trigger detecta cuando un usuario confirma su email y llama
-- automáticamente al endpoint del backend
-- ============================================================================

-- Primero, verificar si la extensión pg_net está habilitada
-- Si no está, habilitarla desde Supabase Dashboard > Database > Extensions

-- Función que se ejecuta cuando se confirma un email
CREATE OR REPLACE FUNCTION notify_backend_on_email_confirmation()
RETURNS TRIGGER AS $$
DECLARE
  backend_url TEXT := 'https://api.codextrader.tech/users/notify-registration';
  service_key TEXT;
BEGIN
  -- Solo ejecutar si el email acaba de ser confirmado (antes era NULL, ahora tiene valor)
  IF OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL THEN
    
    -- Obtener el service key desde las variables de entorno de Supabase
    -- Nota: En producción, esto debe estar en las variables de entorno
    service_key := current_setting('app.settings.service_role_key', true);
    
    -- Si no hay service key, intentar usar una variable de entorno
    IF service_key IS NULL OR service_key = '' THEN
      -- Usar el service key directamente (debe configurarse en Supabase)
      service_key := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0.EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU';
    END IF;
    
    -- Llamar al endpoint usando pg_net (requiere extensión habilitada)
    -- Alternativa: usar http extension si pg_net no está disponible
    PERFORM net.http_post(
      url := backend_url,
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || service_key
      ),
      body := jsonb_build_object(
        'user_id', NEW.id::text,
        'email', NEW.email,
        'triggered_by', 'database_trigger'
      )
    );
    
    RAISE NOTICE 'Trigger ejecutado: Email confirmado para usuario %', NEW.email;
  END IF;
  
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Crear el trigger
DROP TRIGGER IF EXISTS on_email_confirmation_trigger ON auth.users;
CREATE TRIGGER on_email_confirmation_trigger
  AFTER UPDATE OF email_confirmed_at ON auth.users
  FOR EACH ROW
  WHEN (OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL)
  EXECUTE FUNCTION notify_backend_on_email_confirmation();

-- ============================================================================
-- NOTAS IMPORTANTES:
-- ============================================================================
-- 1. Requiere la extensión pg_net habilitada en Supabase
--    Dashboard > Database > Extensions > Buscar "pg_net" > Enable
--
-- 2. El service key debe configurarse en Supabase
--    Dashboard > Project Settings > API > service_role key
--
-- 3. Si pg_net no está disponible, usar http extension:
--    CREATE EXTENSION IF NOT EXISTS http;
--    Y cambiar net.http_post por http_post
--
-- 4. Verificar que el trigger funciona:
--    UPDATE auth.users SET email_confirmed_at = NOW() WHERE email = 'test@example.com';
-- ============================================================================

