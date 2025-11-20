# 🔍 Resumen: Problema de Registro de Usuarios

## ❌ Problema Detectado

**Usuario:** `dakyo31@gmail.com`  
**Estado:** NO se registró correctamente

### Hallazgos:
- ❌ NO existe en tabla `profiles`
- ❌ NO existe en `auth.users` (no se puede verificar sin permisos admin)
- ❌ No hay usuarios creados en las últimas 24 horas
- ✅ Solo existe 1 usuario en la base de datos (el admin)

## 🔍 Posibles Causas

### 1. **El trigger de creación de perfiles NO funciona**
   - El trigger `on_auth_user_created` debería crear automáticamente un perfil cuando se crea un usuario en `auth.users`
   - Si el trigger no existe o está deshabilitado, el usuario se crea en `auth.users` pero NO en `profiles`

### 2. **Error en el proceso de registro del frontend**
   - El frontend llama a `supabase.auth.signUp()` pero falla silenciosamente
   - Hay un error de red o de configuración que impide el registro

### 3. **Configuración de Supabase incorrecta**
   - La confirmación de email está habilitada y el usuario no confirma
   - Hay restricciones que impiden el registro

### 4. **El script de limpieza eliminó algo importante**
   - Aunque es poco probable, el script podría haber eliminado el trigger o alguna función necesaria

## ✅ Acciones Inmediatas

### 1. Verificar el Trigger en Supabase

Ejecuta en Supabase SQL Editor:

```sql
-- Verificar si el trigger existe
SELECT 
    tgname as trigger_name,
    tgrelid::regclass as table_name,
    tgenabled as enabled,
    pg_get_triggerdef(oid) as trigger_definition
FROM pg_trigger
WHERE tgname = 'on_auth_user_created';

-- Verificar si la función existe
SELECT 
    proname as function_name,
    prosrc as function_source
FROM pg_proc
WHERE proname = 'handle_new_user';
```

**Si el trigger NO existe**, ejecuta el script `create_profiles_table.sql` para recrearlo.

### 2. Verificar Logs del Backend

Busca en los logs del backend cuando intentas registrar:
- ¿Aparece alguna llamada a `/users/notify-registration`?
- ¿Hay errores relacionados con Supabase?
- ¿Se registró el router de usuarios correctamente?

### 3. Verificar Consola del Navegador

Abre la consola del navegador (F12) cuando intentas registrar:
- ¿Hay errores de red?
- ¿Hay errores de JavaScript?
- ¿Se llama correctamente a `supabase.auth.signUp()`?

### 4. Verificar Configuración de Supabase

En Supabase Dashboard:
- **Authentication → Providers → Email**
  - Verifica que "Enable email confirmations" esté configurado correctamente
  - Si está habilitado, el usuario debe confirmar su email antes de poder usar la app

- **Database → Functions**
  - Verifica que la función `handle_new_user` existe

- **Database → Triggers**
  - Verifica que el trigger `on_auth_user_created` existe y está habilitado

## 🛠️ Solución Temporal

Si el trigger no existe, puedes crear el perfil manualmente después del registro:

```sql
-- Crear perfil manualmente para un usuario existente
INSERT INTO public.profiles (id, email, tokens_restantes, current_plan)
SELECT 
    id,
    email,
    20000,
    'free'
FROM auth.users
WHERE email = 'dakyo31@gmail.com'
  AND id NOT IN (SELECT id FROM public.profiles);
```

## 📋 Checklist de Verificación

- [ ] Verificar que el trigger `on_auth_user_created` existe
- [ ] Verificar que la función `handle_new_user` existe
- [ ] Verificar logs del backend durante el registro
- [ ] Verificar consola del navegador durante el registro
- [ ] Verificar configuración de Supabase Authentication
- [ ] Intentar registrar un usuario de prueba y observar todo el flujo

