# Configurar STRIPE_WEBHOOK_SECRET en Railway

## ✅ Webhook Configurado en Stripe

Veo que ya tienes el webhook configurado en Stripe:
- **URL:** `https://api.codextrader.tech/billing/stripe-webhook`
- **Estado:** Activo ✅
- **Secreto de firma:** `whsec_bUt4cLHUyCBPtzotNohq2YzntaHehRAZ`

## ⚠️ Falta Configurar en Railway

El secreto de firma debe estar en Railway para que el backend pueda verificar los webhooks.

---

## Pasos para Configurar en Railway

### 1. Ve a Railway Dashboard
- Abre: https://railway.app
- Selecciona tu proyecto del backend

### 2. Ve a Variables de Entorno
- Haz clic en tu servicio (el que corre el backend)
- Ve a la pestaña **"Variables"** o **"Environment Variables"**

### 3. Agrega STRIPE_WEBHOOK_SECRET
- Haz clic en **"+ New Variable"** o **"+ Add Variable"**
- **Nombre:** `STRIPE_WEBHOOK_SECRET`
- **Valor:** `whsec_bUt4cLHUyCBPtzotNohq2YzntaHehRAZ`
- Haz clic en **"Add"** o **"Save"**

### 4. Verifica RESEND_API_KEY
- Busca la variable `RESEND_API_KEY`
- Si no existe, agrégala con tu API key de Resend
- Verifica que `EMAIL_FROM` sea: `Codex Trader <noreply@mail.codextrader.tech>`

### 5. Redeploy (si es necesario)
- Railway debería reiniciar automáticamente
- Si no, haz clic en **"Redeploy"**

---

## Verificación

Después de configurar, cuando hagas una compra:

1. **En Stripe Dashboard → Webhooks:**
   - Ve al webhook
   - Deberías ver eventos en "Entregas de eventos"
   - Deberían aparecer como "Completados correctamente" (verde)

2. **En Railway Logs:**
   - Deberías ver: `🔔 Webhook endpoint llamado`
   - Deberías ver: `✅ Webhook recibido y verificado: checkout.session.completed`
   - Deberías ver: `💰 Tokens sumados para usuario ...`

3. **Emails:**
   - Deberían llegar emails al admin y al usuario

---

## Variables Necesarias en Railway

✅ `STRIPE_SECRET_KEY` - Ya configurada
❌ `STRIPE_WEBHOOK_SECRET` - **AGREGAR:** `whsec_bUt4cLHUyCBPtzotNohq2YzntaHehRAZ`
❌ `RESEND_API_KEY` - **VERIFICAR/AGREGAR**
✅ `EMAIL_FROM` - Ya configurada (verificar que sea correcta)

---

## Nota Importante

El webhook muestra "Total 0" eventos porque:
- O no se ha procesado ninguna compra después de configurarlo
- O el secreto no está configurado en Railway y los webhooks están fallando

Una vez que agregues `STRIPE_WEBHOOK_SECRET` en Railway, los webhooks deberían funcionar correctamente.

