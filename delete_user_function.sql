-- ============================================================================
-- FUNCIÓN PARA ELIMINAR USUARIOS DEL SISTEMA
-- ============================================================================
-- Esta función elimina un usuario de auth.users y todos sus datos relacionados
-- Se ejecuta con permisos de administrador (SECURITY DEFINER)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.delete_user_by_id(user_id_to_delete UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public, auth
AS $$
BEGIN
  -- Verificar que el usuario existe
  IF NOT EXISTS (SELECT 1 FROM auth.users WHERE id = user_id_to_delete) THEN
    RAISE EXCEPTION 'Usuario con ID % no encontrado', user_id_to_delete;
  END IF;
  
  -- Eliminar el usuario de auth.users
  -- Esto automáticamente eliminará el perfil por CASCADE
  DELETE FROM auth.users WHERE id = user_id_to_delete;
  
  RETURN TRUE;
END;
$$;

-- ============================================================================
-- NOTAS:
-- ============================================================================
-- 1. Esta función requiere permisos de SECURITY DEFINER para poder eliminar de auth.users
-- 2. Al eliminar de auth.users, el perfil se elimina automáticamente por ON DELETE CASCADE
-- 3. Todos los datos relacionados también se eliminarán según las políticas de CASCADE
-- 4. ⚠️ ADVERTENCIA: Esta acción es irreversible
-- ============================================================================

-- Para usar esta función desde el backend:
-- supabase_admin_client.rpc('delete_user_by_id', {'user_id_to_delete': 'uuid-del-usuario'}).execute()

