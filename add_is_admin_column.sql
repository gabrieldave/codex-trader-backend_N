-- ============================================================================
-- AGREGAR COLUMNA is_admin A LA TABLA PROFILES
-- ============================================================================
-- Este script agrega la columna is_admin para marcar usuarios como administradores
-- ============================================================================

-- Agregar columna is_admin (BOOLEAN, por defecto FALSE)
ALTER TABLE public.profiles 
ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

-- Crear índice para búsquedas rápidas por is_admin
CREATE INDEX IF NOT EXISTS profiles_is_admin_idx ON public.profiles(is_admin);

-- ============================================================================
-- MARCAR USUARIO COMO ADMINISTRADOR
-- ============================================================================
-- Para marcar un usuario como admin, ejecuta:
-- UPDATE public.profiles SET is_admin = TRUE WHERE email = 'tu-email@example.com';
-- ============================================================================

-- Ejemplo: Marcar usuario específico como admin (descomenta y cambia el email)
-- UPDATE public.profiles SET is_admin = TRUE WHERE email = 'david.del.rio.colin@gmail.com';

-- ============================================================================
-- VERIFICAR USUARIOS ADMIN
-- ============================================================================
-- Para ver todos los usuarios admin:
-- SELECT id, email, is_admin FROM public.profiles WHERE is_admin = TRUE;
-- ============================================================================

