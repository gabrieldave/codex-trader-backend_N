# Solución: Webhook de Stripe No Funciona

## Problemas Identificados

### 1. ❌ STRIPE_WEBHOOK_SECRET No Configurado
**Síntoma:** El webhook no se procesa, los tokens no se suman, no llegan emails.

**Solución:** Configurar el webhook en Stripe Dashboard y agregar el secret en Railway.

---

## Pasos para Configurar el Webhook

### Paso 1: Configurar Webhook en Stripe Dashboard

1. **Ve a Stripe Dashboard:**
   - Abre: https://dashboard.stripe.com/webhooks
   - Haz clic en **"+ Add endpoint"** o **"Add webhook endpoint"**

2. **Configura el Endpoint:**
   - **Endpoint URL:** `https://api.codextrader.tech/billing/stripe-webhook`
   - **Description:** "Webhook para procesar compras y renovaciones"

3. **Selecciona los Eventos:**
   - ✅ `checkout.session.completed` - Cuando un usuario completa el checkout
   - ✅ `invoice.paid` - Cuando se paga una factura (renovación mensual)

4. **Crea el Webhook:**
   - Haz clic en **"Add endpoint"**

5. **Copia el Signing Secret:**
   - Después de crear el webhook, haz clic en él
   - En la sección **"Signing secret"**, haz clic en **"Reveal"** o **"Click to reveal"**
   - Copia el valor completo (empieza con `whsec_...`)
   - **IMPORTANTE:** Guárdalo, lo necesitarás en el siguiente paso

---

### Paso 2: Configurar STRIPE_WEBHOOK_SECRET en Railway

1. **Ve a Railway Dashboard:**
   - Abre tu proyecto en Railway
   - Ve a **Variables** (o **Environment Variables**)

2. **Agrega la Variable:**
   - **Nombre:** `STRIPE_WEBHOOK_SECRET`
   - **Valor:** `whsec_...` (el valor que copiaste de Stripe)
   - Haz clic en **"Add"** o **"Save"**

3. **Redeploy:**
   - Railway debería reiniciar automáticamente
   - Si no, haz clic en **"Redeploy"**

---

### Paso 3: Verificar RESEND_API_KEY

1. **En Railway Dashboard → Variables:**
   - Verifica que exista `RESEND_API_KEY`
   - Si no existe, agrégalo con el valor de tu API key de Resend

2. **Verificar EMAIL_FROM:**
   - Debe ser: `Codex Trader <noreply@mail.codextrader.tech>`
   - O el formato que configuraste en Resend

---

### Paso 4: Probar el Webhook

1. **En Stripe Dashboard:**
   - Ve al webhook que acabas de crear
   - Haz clic en **"Send test webhook"**
   - Selecciona el evento `checkout.session.completed`
   - Haz clic en **"Send test webhook"**
   - Debería aparecer como **"Succeeded"** (verde)

2. **Verificar Logs en Railway:**
   - Deberías ver: `🔔 Webhook endpoint llamado`
   - Deberías ver: `✅ Webhook recibido y verificado: checkout.session.completed`
   - Deberías ver: `🛒 Procesando checkout.session.completed para sesión: ...`

---

## Verificación Post-Configuración

Después de configurar todo, cuando hagas una compra:

1. **Logs del Backend deben mostrar:**
   ```
   🔔 Webhook endpoint llamado
   ✅ Webhook recibido y verificado: checkout.session.completed
   🛒 Procesando checkout.session.completed para sesión: cs_...
   💰 Tokens sumados para usuario ...: X + Y = Z
   ✅ Perfil actualizado: plan=explorer, tokens=Z
   ```

2. **Emails deben llegar:**
   - Email al admin: "Nueva Compra - Checkout Completado"
   - Email al usuario: "¡Pago exitoso! Tu plan Explorer está activo"

3. **Tokens deben actualizarse:**
   - El usuario debe recibir los tokens del plan
   - Se suman a los tokens existentes

---

## Si el Problema Persiste

### Verificar que el Webhook Está Llegando

1. **En Stripe Dashboard → Webhooks:**
   - Ve al webhook que creaste
   - Revisa la sección **"Recent events"**
   - Deberías ver eventos con estado **"Succeeded"** (verde)
   - Si ves **"Failed"** (rojo), haz clic para ver el error

2. **Verificar Logs en Railway:**
   - Busca cualquier error relacionado con webhook
   - Verifica que el endpoint esté accesible

### Verificar que el Endpoint Está Accesible

Prueba acceder a la URL desde tu navegador:
```
https://api.codextrader.tech/billing/stripe-webhook
```

Debería dar un error 405 (Method Not Allowed) porque es un endpoint POST, pero esto confirma que el endpoint existe y está accesible.

---

## Resumen de Variables Necesarias en Railway

- ✅ `STRIPE_SECRET_KEY` - Ya configurada
- ❌ `STRIPE_WEBHOOK_SECRET` - **FALTA CONFIGURAR** (crítico)
- ❌ `RESEND_API_KEY` - **FALTA CONFIGURAR** (para emails)
- ✅ `EMAIL_FROM` - Ya configurada

---

## Nota sobre Resend

Si ya configuraste `RESEND_API_KEY` pero el script dice que no está:
- Verifica que esté en Railway (no solo en .env local)
- Verifica que el nombre sea exactamente `RESEND_API_KEY`
- Haz redeploy después de agregar la variable

