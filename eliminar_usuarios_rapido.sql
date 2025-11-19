-- ============================================================================
-- SCRIPT SQL PARA ELIMINAR TODOS LOS USUARIOS EXCEPTO EL ADMIN
-- ============================================================================
-- ⚠️ ADVERTENCIA: Este script eliminará TODOS los usuarios excepto el admin
-- Esta acción es IRREVERSIBLE
-- ============================================================================

-- IMPORTANTE: Reemplaza 'david.del.rio.colin@gmail.com' con el email de tu admin
-- o ajusta la condición WHERE según necesites

-- Opción 1: Eliminar usuarios directamente (requiere función delete_user_by_id)
-- Descomenta y ejecuta si ya tienes la función creada:

/*
DO $$
DECLARE
    admin_email TEXT := 'david.del.rio.colin@gmail.com';
    admin_id UUID;
    user_record RECORD;
    deleted_count INT := 0;
BEGIN
    -- Obtener ID del admin
    SELECT id INTO admin_id
    FROM auth.users
    WHERE email = admin_email;
    
    IF admin_id IS NULL THEN
        RAISE EXCEPTION 'Admin con email % no encontrado', admin_email;
    END IF;
    
    RAISE NOTICE 'Admin encontrado: % (ID: %)', admin_email, admin_id;
    
    -- Eliminar todos los usuarios excepto el admin
    FOR user_record IN 
        SELECT id, email 
        FROM auth.users 
        WHERE id != admin_id
    LOOP
        BEGIN
            -- Usar la función delete_user_by_id si existe
            PERFORM public.delete_user_by_id(user_record.id);
            deleted_count := deleted_count + 1;
            RAISE NOTICE 'Usuario eliminado: % (ID: %)', user_record.email, user_record.id;
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Error al eliminar usuario %: %', user_record.email, SQLERRM;
        END;
    END LOOP;
    
    RAISE NOTICE 'Total de usuarios eliminados: %', deleted_count;
END $$;
*/

-- ============================================================================
-- Opción 2: Eliminar usuarios manualmente (más seguro, paso a paso)
-- ============================================================================

-- Paso 1: Ver usuarios que se eliminarán (EJECUTA PRIMERO PARA VERIFICAR)
SELECT 
    id,
    email,
    created_at
FROM auth.users
WHERE email != 'david.del.rio.colin@gmail.com'
ORDER BY created_at;

-- Paso 2: Si estás seguro, elimina usuario por usuario:
-- DELETE FROM auth.users WHERE id = 'uuid-del-usuario-aqui';

-- ============================================================================
-- Opción 3: Eliminar usando función RPC desde el backend
-- ============================================================================
-- Usa el script Python: eliminar_todos_usuarios_excepto_admin.py
-- Es más seguro porque tiene confirmaciones y muestra el progreso

-- ============================================================================
-- NOTAS IMPORTANTES:
-- ============================================================================
-- 1. Al eliminar de auth.users, el perfil se elimina automáticamente (CASCADE)
-- 2. Todas las conversaciones y datos relacionados también se eliminarán
-- 3. Esta acción es IRREVERSIBLE
-- 4. Se recomienda hacer un backup antes de ejecutar
-- ============================================================================

