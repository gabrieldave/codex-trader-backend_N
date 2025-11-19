-- ============================================================================
-- TRIGGER: Notificar Backend cuando se Confirma un Email
-- ============================================================================
-- Este trigger detecta cuando un usuario confirma su email y llama
-- automáticamente al endpoint del backend para enviar el email de bienvenida
-- ============================================================================

-- IMPORTANTE: Antes de ejecutar este script, necesitas:
-- 1. Obtener el SERVICE_ROLE_KEY de Supabase Dashboard > Project Settings > API
-- 2. Reemplazar 'TU_SERVICE_ROLE_KEY_AQUI' con el valor real

-- Función que se ejecuta cuando se confirma un email
CREATE OR REPLACE FUNCTION notify_backend_on_email_confirmation()
RETURNS TRIGGER AS $$
DECLARE
  backend_url TEXT := 'https://api.codextrader.tech/users/notify-registration';
  service_key TEXT;
  request_id BIGINT;
  response_status INT;
BEGIN
  -- Solo ejecutar si el email acaba de ser confirmado (antes era NULL, ahora tiene valor)
  IF OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL THEN
    
    -- Obtener el service_role key
    -- Opción 1: Desde variable de entorno (si está configurada en Supabase)
    BEGIN
      service_key := current_setting('app.settings.service_role_key', true);
    EXCEPTION WHEN OTHERS THEN
      service_key := NULL;
    END;
    
    -- Opción 2: Si no está en variables, usar el valor hardcodeado
    -- IMPORTANTE: Reemplazar con tu service_role key real
    IF service_key IS NULL OR service_key = '' THEN
      service_key := 'TU_SERVICE_ROLE_KEY_AQUI';
    END IF;
    
    -- Si aún no hay service key, usar un método alternativo
    -- Llamar al endpoint sin autenticación (el endpoint debe aceptar user_id en el body)
    IF service_key = 'TU_SERVICE_ROLE_KEY_AQUI' OR service_key IS NULL THEN
      -- Método alternativo: llamar sin Authorization header
      -- El endpoint debe aceptar user_id directamente
      SELECT net.http_post(
        url := backend_url,
        headers := jsonb_build_object(
          'Content-Type', 'application/json'
        ),
        body := jsonb_build_object(
          'user_id', NEW.id::text,
          'email', NEW.email,
          'triggered_by', 'database_trigger'
        )
      ) INTO request_id;
    ELSE
      -- Método preferido: llamar con Authorization header
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
    END IF;
    
    -- Log para debugging (visible en Supabase logs)
    RAISE NOTICE '[TRIGGER] Email confirmado para usuario % (ID: %). Request ID: %', 
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
-- INSTRUCCIONES:
-- ============================================================================
-- 1. Obtener el SERVICE_ROLE_KEY:
--    - Ir a Supabase Dashboard > Project Settings > API
--    - Copiar el "service_role" key (secret, no el anon key)
--    - Reemplazar 'TU_SERVICE_ROLE_KEY_AQUI' en la función
--
-- 2. Ejecutar este script en Supabase:
--    - Ir a Supabase Dashboard > SQL Editor
--    - Pegar este script completo
--    - Reemplazar 'TU_SERVICE_ROLE_KEY_AQUI' con tu service_role key
--    - Ejecutar (Run)
--
-- 3. Verificar que funciona:
--    - Confirmar un email de prueba
--    - Verificar logs en Supabase Dashboard > Logs > Postgres Logs
--    - Verificar que el email de bienvenida se envía
--
-- 4. NOTA: El endpoint del backend debe aceptar:
--    - Authorization header con Bearer token (service_role key), O
--    - Body con user_id y email (sin autenticación)
-- ============================================================================

