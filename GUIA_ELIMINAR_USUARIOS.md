# Guía para Eliminar o Desactivar Usuarios

Esta guía explica cómo eliminar o desactivar usuarios de tu proyecto Codex Trader.

## 📋 Opciones Disponibles

### 1. **Eliminar Usuario Completamente** (Irreversible)
Elimina el usuario de `auth.users` y todos sus datos relacionados (perfil, conversaciones, etc.)

### 2. **Desactivar Usuario** (Reversible)
Establece los tokens del usuario a 0, bloqueando su acceso sin eliminar sus datos

---

## 🚀 Configuración Inicial

### Paso 1: Crear función SQL en Supabase

Ejecuta el script `delete_user_function.sql` en tu base de datos Supabase:

1. Ve a tu proyecto en Supabase Dashboard
2. Abre el **SQL Editor**
3. Copia y pega el contenido de `delete_user_function.sql`
4. Ejecuta el script

Esto creará la función `delete_user_by_id` que permite eliminar usuarios de forma segura.

### Paso 2: Verificar que eres administrador

Asegúrate de que tu usuario tenga permisos de administrador:

- Opción A: Agregar tu email a `ADMIN_EMAILS` en variables de entorno
- Opción B: Marcar tu perfil con `is_admin = true` en la tabla `profiles`

---

## 📡 Métodos para Eliminar/Desactivar Usuarios

### Método 1: Usando el Endpoint de Admin (Recomendado)

#### Eliminar Usuario Completamente

```bash
DELETE /admin/users/{user_id}
Authorization: Bearer {admin_token}
```

**Ejemplo con curl:**
```bash
curl -X DELETE "https://api.codextrader.tech/admin/users/123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer TU_TOKEN_DE_ADMIN"
```

#### Desactivar Usuario

```bash
POST /admin/users/{user_id}/deactivate
Authorization: Bearer {admin_token}
```

**Ejemplo con curl:**
```bash
curl -X POST "https://api.codextrader.tech/admin/users/123e4567-e89b-12d3-a456-426614174000/deactivate" \
  -H "Authorization: Bearer TU_TOKEN_DE_ADMIN"
```

### Método 2: Usando el Script Python

```bash
# Eliminar usuario completamente
python eliminar_usuario_ejemplo.py 123e4567-e89b-12d3-a456-426614174000

# Solo desactivar usuario
python eliminar_usuario_ejemplo.py 123e4567-e89b-12d3-a456-426614174000 --deactivate
```

**Nota:** Necesitas configurar `ADMIN_TOKEN` en tu `.env` o variables de entorno.

### Método 3: Directamente desde Supabase Dashboard

1. Ve a **Authentication > Users** en Supabase Dashboard
2. Busca el usuario por email o ID
3. Haz clic en los tres puntos (⋯) junto al usuario
4. Selecciona **Delete user**

⚠️ **Advertencia:** Esto eliminará el usuario pero no ejecutará la función SQL personalizada.

---

## 🔍 Cómo Obtener el User ID

### Opción 1: Desde Supabase Dashboard
1. Ve a **Authentication > Users**
2. Busca el usuario por email
3. Copia el **User UID**

### Opción 2: Desde la Base de Datos
```sql
SELECT id, email FROM profiles WHERE email = 'usuario@ejemplo.com';
```

### Opción 3: Desde el Backend (si tienes acceso)
```python
# Buscar usuario por email
profile = supabase_client.table("profiles").select("id").eq("email", "usuario@ejemplo.com").execute()
user_id = profile.data[0]["id"] if profile.data else None
```

---

## ⚠️ Advertencias Importantes

### Eliminar Usuario
- ✅ Elimina el usuario de `auth.users`
- ✅ Elimina automáticamente el perfil (por CASCADE)
- ✅ Elimina todas las conversaciones y datos relacionados
- ❌ **Esta acción es IRREVERSIBLE**
- ❌ No se puede deshacer

### Desactivar Usuario
- ✅ Establece tokens a 0 (bloquea acceso)
- ✅ Mantiene todos los datos
- ✅ Puede reactivarse después
- ⚠️ El usuario aún puede intentar iniciar sesión (pero no tendrá tokens)

---

## 🛡️ Seguridad

1. **Solo administradores** pueden usar estos endpoints
2. Se requiere autenticación con token de admin
3. Los logs registran todas las eliminaciones
4. Se recomienda usar `deactivate` en lugar de `delete` cuando sea posible

---

## 📝 Ejemplo Completo

```python
import requests

# Configuración
BACKEND_URL = "https://api.codextrader.tech"
ADMIN_TOKEN = "tu_token_de_admin"
USER_ID = "123e4567-e89b-12d3-a456-426614174000"

# Eliminar usuario
response = requests.delete(
    f"{BACKEND_URL}/admin/users/{USER_ID}",
    headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
)

if response.status_code == 200:
    print("✅ Usuario eliminado exitosamente")
    print(response.json())
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)
```

---

## 🆘 Solución de Problemas

### Error: "Función delete_user_by_id no existe"
**Solución:** Ejecuta `delete_user_function.sql` en Supabase SQL Editor

### Error: "Acceso denegado: se requieren permisos de administrador"
**Solución:** Verifica que tu usuario tenga `is_admin = true` o esté en `ADMIN_EMAILS`

### Error: "Usuario no encontrado"
**Solución:** Verifica que el `user_id` sea correcto y que el usuario exista

### Error: "requests no está instalado"
**Solución:** Instala requests: `pip install requests`

---

## 📚 Archivos Relacionados

- `admin_router.py` - Endpoints de administración
- `delete_user_function.sql` - Función SQL para eliminar usuarios
- `eliminar_usuario_ejemplo.py` - Script de ejemplo

---

## ✅ Checklist

Antes de eliminar un usuario:

- [ ] ¿Estás seguro de que quieres eliminar permanentemente?
- [ ] ¿Has considerado desactivar en lugar de eliminar?
- [ ] ¿Has verificado que tienes permisos de admin?
- [ ] ¿Has ejecutado `delete_user_function.sql` en Supabase?
- [ ] ¿Has respaldado los datos importantes del usuario?

---

**Última actualización:** 2025-01-19

