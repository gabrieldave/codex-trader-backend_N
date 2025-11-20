-- ============================================================================
-- VERIFICAR TRIGGER DE CREACIÓN DE PERFILES
-- ============================================================================
-- Este script verifica si el trigger que crea perfiles automáticamente
-- cuando un usuario se registra está funcionando correctamente
-- ============================================================================

-- 1. Verificar si el trigger existe
SELECT 
    tgname as trigger_name,
    tgrelid::regclass as table_name,
    tgenabled as enabled,
    pg_get_triggerdef(oid) as trigger_definition
FROM pg_trigger
WHERE tgname = 'on_auth_user_created';

-- 2. Verificar si la función existe
SELECT 
    proname as function_name,
    prosrc as function_source
FROM pg_proc
WHERE proname = 'handle_new_user';

-- 3. Verificar si la tabla profiles existe y tiene la estructura correcta
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public' 
  AND table_name = 'profiles'
ORDER BY ordinal_position;

-- 4. Verificar políticas RLS en profiles
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE tablename = 'profiles';

-- 5. Verificar si RLS está habilitado
SELECT 
    tablename,
    rowsecurity as rls_enabled
FROM pg_tables
WHERE schemaname = 'public' 
  AND tablename = 'profiles';

