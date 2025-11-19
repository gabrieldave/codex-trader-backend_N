-- ============================================================================
-- TRIGGER: Notificar Backend cuando se Confirma un Email
-- ============================================================================
-- Este trigger detecta cuando un usuario confirma su email y llama
-- automáticamente al endpoint del backend para enviar el email de bienvenida
-- ============================================================================

-- Función que se ejecuta cuando se confirma un email
CREATE OR REPLACE FUNCTION notify_backend_on_email_confirmation()
RETURNS TRIGGER AS $$
DECLARE
  backend_url TEXT := 'https://api.codextrader.tech/users/notify-registration';
  service_key TEXT;
  request_id BIGINT;
BEGIN
  -- Solo ejecutar si el email acaba de ser confirmado (antes era NULL, ahora tiene valor)
  IF OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL THEN
    
    -- Obtener el service key desde las variables de entorno de Supabase
    -- El service key debe estar configurado en Supabase Dashboard > Project Settings > API
    -- Para este trigger, usamos el service_role key que tiene permisos para llamar al endpoint
    service_key := current_setting('app.settings.service_role_key', true);
    
    -- Si no está en variables, intentar obtenerlo de otra forma
    -- Nota: En producción, esto debe estar configurado correctamente
    IF service_key IS NULL OR service_key = '' THEN
      -- Intentar obtener desde vault o usar un valor por defecto
      -- IMPORTANTE: Reemplazar con el service_role key real de Supabase
      service_key := 'REPLACE_WITH_SERVICE_ROLE_KEY';
    END IF;
    
    -- Llamar al endpoint usando pg_net (requiere extensión habilitada)
    -- Enviar el user_id y email para que el backend pueda identificar al usuario
    SELECT net.http_post(
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
    ) INTO request_id;
    
    -- Log para debugging (visible en Supabase logs)
    RAISE NOTICE 'Trigger ejecutado: Email confirmado para usuario % (ID: %). Request ID: %', 
      NEW.email, NEW.id, request_id;
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
-- 1. La extensión pg_net ya está habilitada (versión 0.19.5)
--
-- 2. El service_role key debe configurarse:
--    - Ir a Supabase Dashboard > Project Settings > API
--    - Copiar el "service_role" key (secret)
--    - Reemplazar 'REPLACE_WITH_SERVICE_ROLE_KEY' en la función
--    - O configurarlo como variable de entorno en Supabase
--
-- 3. El endpoint del backend acepta:
--    - Authorization header con Bearer token (service_role key)
--    - Body con user_id y email
--
-- 4. Verificar que el trigger funciona:
--    - Confirmar un email de prueba
--    - Verificar logs en Supabase Dashboard > Logs > Postgres Logs
--    - Verificar que el email de bienvenida se envía
-- ============================================================================

