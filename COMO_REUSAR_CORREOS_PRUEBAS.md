# 📧 Cómo Reusar Correos para Pruebas

## ❌ Problema

Si intentas registrar un email que ya existe en `auth.users`, Supabase te dirá que "ya tienes acceso" y no podrás crear un nuevo usuario con ese email.

## ✅ Solución

Usa el script `limpiar_usuario_especifico.py` para eliminar completamente un usuario de ambas tablas (`auth.users` y `profiles`) antes de volver a registrarlo.

### Paso 1: Ejecutar el script

Desde el directorio `backend`:

```bash
python limpiar_usuario_especifico.py dakyo31@gmail.com
```

O para eliminar sin confirmación (modo automático):

```bash
python limpiar_usuario_especifico.py dakyo31@gmail.com --auto
```

### Paso 2: Verificar que se eliminó

El script mostrará un resumen de lo que se eliminó:
- ✅ Datos de `profiles`
- ✅ Datos de `auth.users`
- ✅ Datos relacionados (chat_sessions, conversations, model_usage_events, stripe_payments, referral_reward_events)

### Paso 3: Registrar nuevamente

Ahora puedes registrar el mismo email nuevamente desde la app.

---

## ⚠️ Advertencia

- **NO puedes eliminar usuarios admin** por seguridad
- El script requiere `SUPABASE_SERVICE_ROLE_KEY` para eliminar de `auth.users`
- **Esto elimina TODOS los datos del usuario** (no es recuperable)

---

## 🔍 Si el Script No Funciona

Si el script no puede eliminar de `auth.users` (requiere permisos especiales), puedes:

1. **Eliminar manualmente desde Supabase Dashboard:**
   - Ve a **Authentication** → **Users**
   - Busca el usuario por email
   - Haz clic en los tres puntos (⋮) → **Delete**

2. **O usar emails diferentes para pruebas:**
   - Usa aliases de email: `dakyo31+test1@gmail.com`, `dakyo31+test2@gmail.com`, etc.
   - Gmail los trata como el mismo buzón pero Supabase los ve como usuarios diferentes

