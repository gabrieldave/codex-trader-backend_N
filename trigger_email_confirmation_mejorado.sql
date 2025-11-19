-- ============================================================================
-- TRIGGER MEJORADO: Notificar Backend cuando se Confirma un Email
-- ============================================================================
-- Este trigger detecta cuando un usuario confirma su email y llama
-- automáticamente al endpoint del backend para enviar el email de bienvenida.
-- 
-- MEJORA: También verifica si el email de bienvenida no se ha enviado,
-- incluso si el email ya estaba confirmado antes.
-- ============================================================================

-- Función que se ejecuta cuando se confirma un email
CREATE OR REPLACE FUNCTION notify_backend_on_email_confirmation()
RETURNS TRIGGER AS $$
DECLARE
  backend_url TEXT := 'https://api.codextrader.tech/users/notify-registration';
  service_key TEXT;
  request_id BIGINT;
  welcome_email_sent BOOLEAN;
BEGIN
  -- Solo ejecutar si el email acaba de ser confirmado (antes era NULL, ahora tiene valor)
  IF OLD.email_confirmed_at IS NULL AND NEW.email_confirmed_at IS NOT NULL THEN
    
    -- Verificar si el email de bienvenida ya se envió
    -- Esto evita llamadas innecesarias si ya se envió
    SELECT COALESCE(p.welcome_email_sent, false) INTO welcome_email_sent
    FROM public.profiles p
    WHERE p.id = NEW.id;
    
    -- Si ya se envió, no hacer nada (evitar spam)
    IF welcome_email_sent THEN
      RAISE NOTICE '[TRIGGER] Email de bienvenida ya enviado para usuario % (ID: %). Saltando.', 
        NEW.email, NEW.id;
      RETURN NEW;
    END IF;
    
    -- Obtener el service_role key
    BEGIN
      service_key := current_setting('app.settings.service_role_key', true);
    EXCEPTION WHEN OTHERS THEN
      service_key := NULL;
    END;
    
    -- Si no está en variables, usar el valor hardcodeado
    -- IMPORTANTE: Reemplazar con tu service_role key real
    IF service_key IS NULL OR service_key = '' THEN
      service_key := 'TU_SERVICE_ROLE_KEY_AQUI';
    END IF;
    
    -- Si aún no hay service key, usar un método alternativo
    -- Llamar al endpoint sin autenticación (el endpoint debe aceptar user_id en el body)
    IF service_key = 'TU_SERVICE_ROLE_KEY_AQUI' OR service_key IS NULL THEN
      -- Método alternativo: llamar sin Authorization header
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
-- FUNCIÓN ADICIONAL: Verificar y enviar email de bienvenida pendiente
-- ============================================================================
-- Esta función puede ejecutarse manualmente para verificar usuarios confirmados
-- que no han recibido el email de bienvenida
-- ============================================================================

CREATE OR REPLACE FUNCTION check_and_send_pending_welcome_emails()
RETURNS TABLE(
  user_id UUID,
  user_email TEXT,
  email_confirmed BOOLEAN,
  welcome_email_sent BOOLEAN,
  action_taken TEXT
) AS $$
DECLARE
  backend_url TEXT := 'https://api.codextrader.tech/users/notify-registration';
  service_key TEXT;
  request_id BIGINT;
  user_record RECORD;
BEGIN
  -- Obtener service key
  BEGIN
    service_key := current_setting('app.settings.service_role_key', true);
  EXCEPTION WHEN OTHERS THEN
    service_key := NULL;
  END;
  
  IF service_key IS NULL OR service_key = '' THEN
    service_key := 'TU_SERVICE_ROLE_KEY_AQUI';
  END IF;
  
  -- Buscar usuarios confirmados que no han recibido email de bienvenida
  FOR user_record IN
    SELECT 
      u.id,
      u.email,
      u.email_confirmed_at IS NOT NULL as email_confirmed,
      COALESCE(p.welcome_email_sent, false) as welcome_email_sent
    FROM auth.users u
    LEFT JOIN public.profiles p ON p.id = u.id
    WHERE u.email_confirmed_at IS NOT NULL
      AND COALESCE(p.welcome_email_sent, false) = false
    LIMIT 10  -- Limitar a 10 para evitar sobrecarga
  LOOP
    -- Llamar al endpoint para enviar email de bienvenida
    IF service_key = 'TU_SERVICE_ROLE_KEY_AQUI' OR service_key IS NULL THEN
      SELECT net.http_post(
        url := backend_url,
        headers := jsonb_build_object('Content-Type', 'application/json'),
        body := jsonb_build_object(
          'user_id', user_record.id::text,
          'email', user_record.email,
          'triggered_by', 'manual_check_function'
        )
      ) INTO request_id;
    ELSE
      SELECT net.http_post(
        url := backend_url,
        headers := jsonb_build_object(
          'Content-Type', 'application/json',
          'Authorization', 'Bearer ' || service_key
        ),
        body := jsonb_build_object(
          'user_id', user_record.id::text,
          'email', user_record.email,
          'triggered_by', 'manual_check_function'
        )
      ) INTO request_id;
    END IF;
    
    -- Retornar información
    RETURN QUERY SELECT
      user_record.id,
      user_record.email,
      user_record.email_confirmed,
      user_record.welcome_email_sent,
      'Email de bienvenida solicitado (Request ID: ' || request_id::text || ')'::TEXT;
  END LOOP;
  
  RETURN;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================================================
-- INSTRUCCIONES:
-- ============================================================================
-- 1. Reemplazar 'TU_SERVICE_ROLE_KEY_AQUI' con tu service_role key real
-- 2. Ejecutar este script en Supabase SQL Editor
-- 3. Para verificar usuarios pendientes, ejecutar:
--    SELECT * FROM check_and_send_pending_welcome_emails();
-- ============================================================================

