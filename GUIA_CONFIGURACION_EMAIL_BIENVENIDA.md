# 📧 Guía Completa: Configuración de Email de Bienvenida

## 🔍 Problema
No recibes el email de bienvenida después de confirmar tu correo electrónico.

---

## ✅ Checklist de Configuración

### 1. Configuración en Supabase Dashboard

#### ✅ 1.1. Authentication → URL Configuration

**Ve a:** Supabase Dashboard → Authentication → URL Configuration

**Configurar:**

1. **Site URL:**
   ```
   https://www.codextrader.tech
   ```

2. **Redirect URLs** (agregar TODAS estas URLs):
   ```
   http://localhost:3000/auth/callback
   https://www.codextrader.tech/auth/callback
   https://codextrader.tech/auth/callback
   ```

**⚠️ IMPORTANTE:** Sin estas URLs configuradas, el flujo de confirmación no funcionará correctamente.

---

#### ✅ 1.2. Authentication → Email Templates

**Ve a:** Supabase Dashboard → Authentication → Email Templates

**Verificar que estos templates existan:**

- [ ] **Confirm signup** - Template para confirmación de registro
- [ ] **Magic Link** - Template para magic links
- [ ] **Change Email Address** - Template para cambio de email
- [ ] **Reset Password** - Template para reset de contraseña

**Nota:** Puedes personalizar estos templates, pero asegúrate de que existan.

---

#### ✅ 1.3. Authentication → Providers

**Ve a:** Supabase Dashboard → Authentication → Providers

**Verificar:**

- [ ] **Email** - Debe estar habilitado
- [ ] **Confirm email** - Debe estar habilitado (requiere confirmación de email)

**Configuración recomendada:**
- ✅ **Enable email confirmations** - Activado
- ✅ **Secure email change** - Activado (recomendado)

---

### 2. Variables de Entorno en Railway (Backend)

**Ve a:** Railway Dashboard → Tu Proyecto → Variables

**Verificar que estas variables estén configuradas:**

```env
# SMTP Configuration (CRÍTICO para email de bienvenida)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=todossomostr4ders@gmail.com
SMTP_PASS=kjhf biie tgrk wncz
EMAIL_FROM=Codex Trader <todossomostr4ders@gmail.com>
ADMIN_EMAIL=todossomostr4ders@gmail.com

# Frontend URL (para enlaces en el email)
FRONTEND_URL=https://www.codextrader.tech
```

**⚠️ IMPORTANTE sobre SMTP_PASS:**
- Debe ser una **"App Password"** de Gmail, NO tu contraseña normal
- **Cómo obtener una App Password:**
  1. Ve a [myaccount.google.com](https://myaccount.google.com)
  2. **Seguridad** → **Verificación en 2 pasos** (debe estar activada)
  3. **Contraseñas de aplicaciones** → **Generar nueva contraseña**
  4. Copia la contraseña generada (16 caracteres sin espacios)
  5. Úsala como `SMTP_PASS` en Railway

---

### 3. Flujo de Confirmación de Email

#### 📋 Paso a Paso del Flujo

1. **Usuario se registra** en el frontend
   - Frontend llama a `supabase.auth.signUp()`
   - Supabase envía email de confirmación automáticamente

2. **Usuario hace clic en el enlace de confirmación**
   - Supabase redirige a `/auth/callback?code=...` o `/auth/callback?token=...`
   - El callback procesa la confirmación

3. **Frontend detecta confirmación**
   - El código en `app/page.tsx` detecta `confirmed=true` o `email_confirmed=true`
   - Llama a `/users/notify-registration` con el token de autenticación

4. **Backend envía email de bienvenida**
   - El endpoint `/users/notify-registration` recibe la solicitud
   - Verifica configuración SMTP
   - Envía email de bienvenida al usuario

---

### 4. Verificación del Flujo

#### ✅ 4.1. Verificar que el Frontend Llama al Endpoint

**Revisa los logs del navegador (Console) después de confirmar email:**

Deberías ver:
```
✅ Usuario confirmado detectado en onAuthStateChange, notificando al backend para enviar email de bienvenida
   Llamando a https://api.codextrader.tech/users/notify-registration...
   Response status: 200
✅ Email de bienvenida solicitado correctamente desde onAuthStateChange
```

**Si NO ves estos logs:**
- El frontend no está detectando la confirmación correctamente
- Verifica que el callback `/auth/callback` esté funcionando

---

#### ✅ 4.2. Verificar Logs del Backend (Railway)

**Después de confirmar email, revisa los logs de Railway:**

Deberías ver:
```
[EMAIL] ========================================
[EMAIL] INICIANDO ENVIO DE EMAIL DE BIENVENIDA
[EMAIL] ========================================
[EMAIL] SMTP_AVAILABLE: True
[EMAIL] SMTP_HOST: smtp.gmail.com
[EMAIL] SMTP_USER: todossomostr4ders@gmail.com
[EMAIL] EMAIL_FROM: Codex Trader <todossomostr4ders@gmail.com>
[EMAIL] Destinatario: [email del usuario]
[EMAIL] Enviando email de bienvenida a [email]...
[OK] Email de bienvenida enviado correctamente a [email]
```

**Si ves `SMTP_AVAILABLE: False`:**
- Las variables SMTP no están configuradas en Railway
- Verifica que todas las variables estén presentes

**Si ves errores de autenticación SMTP:**
- `SMTP_PASS` es incorrecta o no es una App Password válida
- Genera una nueva App Password y actualiza `SMTP_PASS`

---

### 5. Problemas Comunes y Soluciones

#### ❌ Problema 1: No se llama al endpoint `/users/notify-registration`

**Síntomas:**
- No hay logs del endpoint en Railway
- No hay logs en la consola del navegador

**Soluciones:**
1. Verifica que el callback `/auth/callback` esté funcionando
2. Verifica que las Redirect URLs estén configuradas en Supabase
3. Verifica que el frontend detecte `confirmed=true` o `email_confirmed=true`

---

#### ❌ Problema 2: SMTP_AVAILABLE es False

**Síntomas:**
- En los logs: `[EMAIL] SMTP_AVAILABLE: False`
- Error: "SMTP no está configurado"

**Soluciones:**
1. Verifica que todas las variables SMTP estén en Railway:
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USER`
   - `SMTP_PASS`
   - `EMAIL_FROM`
2. Reinicia el servicio en Railway después de agregar variables
3. Verifica que no haya espacios extra en las variables

---

#### ❌ Problema 3: Error de autenticación SMTP

**Síntomas:**
- En los logs: Error de autenticación SMTP
- `SMTP_AVAILABLE: True` pero el email no se envía

**Soluciones:**
1. Verifica que `SMTP_PASS` sea una App Password válida (no tu contraseña normal)
2. Genera una nueva App Password en Gmail
3. Actualiza `SMTP_PASS` en Railway
4. Reinicia el servicio

---

#### ❌ Problema 4: Email llega a Spam

**Síntomas:**
- El email se envía pero llega a la carpeta de spam

**Soluciones:**
1. Verifica que `EMAIL_FROM` tenga el formato correcto: `Nombre <email@ejemplo.com>`
2. Considera usar un servicio de email profesional (SendGrid, Mailgun, etc.)
3. Configura SPF y DKIM en tu dominio (avanzado)

---

#### ❌ Problema 5: Redirect a localhost después de confirmar

**Síntomas:**
- Después de confirmar email, te redirige a `localhost:3000`

**Soluciones:**
1. Verifica que las Redirect URLs en Supabase incluyan tu dominio de producción
2. Verifica que `Site URL` esté configurado como `https://www.codextrader.tech`
3. El código del frontend ya está actualizado para usar `window.location.origin` en producción

---

### 6. Prueba Completa del Flujo

#### ✅ Paso 1: Crear Cuenta Nueva

1. Ve a `https://www.codextrader.tech`
2. Crea una cuenta nueva con un email de prueba
3. Verifica que recibas el email de confirmación de Supabase

#### ✅ Paso 2: Confirmar Email

1. Haz clic en el enlace de confirmación en el email
2. Deberías ser redirigido a `https://www.codextrader.tech` (no localhost)
3. Deberías ver un mensaje de éxito

#### ✅ Paso 3: Verificar Logs

1. Revisa los logs de Railway
2. Deberías ver los logs de `[EMAIL] INICIANDO ENVIO DE EMAIL DE BIENVENIDA`
3. Deberías ver `[OK] Email de bienvenida enviado correctamente`

#### ✅ Paso 4: Verificar Email de Bienvenida

1. Revisa tu bandeja de entrada (y spam)
2. Deberías recibir el email de bienvenida de Codex Trader

---

### 7. Configuración Adicional Recomendada

#### ✅ 7.1. Configurar SMTP en Supabase (Opcional)

Si prefieres que Supabase envíe los emails directamente:

1. Ve a **Settings** → **Auth** → **SMTP Settings**
2. Configura tu SMTP personalizado
3. Esto reemplazará el SMTP por defecto de Supabase

**Nota:** El backend también puede enviar emails usando SMTP configurado en Railway (recomendado para emails personalizados).

---

### 8. Verificación Final

Después de configurar todo, verifica:

- [ ] Redirect URLs configuradas en Supabase
- [ ] Site URL configurado en Supabase
- [ ] Variables SMTP configuradas en Railway
- [ ] `SMTP_PASS` es una App Password válida
- [ ] `FRONTEND_URL` configurada en Railway
- [ ] Logs muestran `SMTP_AVAILABLE: True`
- [ ] El frontend llama a `/users/notify-registration` después de confirmar
- [ ] El email de bienvenida se envía correctamente

---

## 📝 Resumen Rápido

**Para que el email de bienvenida funcione necesitas:**

1. ✅ **Supabase:** Redirect URLs y Site URL configurados
2. ✅ **Railway:** Variables SMTP configuradas (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`)
3. ✅ **Railway:** `FRONTEND_URL` configurada
4. ✅ **Gmail:** App Password generada y usada como `SMTP_PASS`
5. ✅ **Frontend:** Llama a `/users/notify-registration` después de confirmar email
6. ✅ **Backend:** Recibe la solicitud y envía el email usando SMTP

---

## 🆘 Si el Problema Persiste

1. **Comparte los logs de Railway** después de confirmar email
2. **Comparte los logs de la consola del navegador** después de confirmar email
3. **Verifica que todas las variables estén configuradas** en Railway
4. **Verifica que las Redirect URLs estén configuradas** en Supabase

---

## 🔗 Archivos Relacionados

- `backend/main.py` - Endpoint `/users/notify-registration` (línea ~3373)
- `backend/lib/email.py` - Funciones de envío de email
- `frontend/app/auth/callback/route.ts` - Callback de confirmación
- `frontend/app/page.tsx` - Detección de confirmación y llamada al endpoint




