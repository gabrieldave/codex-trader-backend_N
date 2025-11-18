# 🔗 Configurar Webhook de Stripe

## 📍 URL del Webhook

Si tienes el subdominio `api.codextrader.tech` configurado (recomendado):

```
https://api.codextrader.tech/billing/stripe-webhook
```

Si NO tienes el subdominio configurado, usa la URL de Railway directamente:

```
https://web-production-3ab35.up.railway.app/billing/stripe-webhook
```

## ✅ ¿Cuál usar?

**Recomendado: `api.codextrader.tech`** porque:
- ✅ Es más profesional
- ✅ No cambia si Railway actualiza la URL
- ✅ Es más fácil de recordar
- ✅ Es consistente con tu dominio

**Alternativa: URL de Railway** si:
- ⚠️ Aún no configuraste el subdominio
- ⚠️ El subdominio no está funcionando

## 🎯 Pasos para Configurar en Stripe

### 1. Ve a Stripe Dashboard
1. Abre: https://dashboard.stripe.com
2. Ve a **Developers** → **Webhooks**
3. Haz clic en **"+ Add endpoint"**

### 2. Configura el Webhook

**Endpoint URL:**
```
https://api.codextrader.tech/billing/stripe-webhook
```

O si no tienes el subdominio:
```
https://web-production-3ab35.up.railway.app/billing/stripe-webhook
```

**Eventos a seleccionar:**
- ✅ `checkout.session.completed` - Cuando un usuario completa el checkout
- ✅ `invoice.paid` - Cuando se paga una factura (renovación mensual)

### 3. Copia el Signing Secret

Después de crear el webhook:
1. Haz clic en el webhook que acabas de crear
2. En la sección **"Signing secret"**, haz clic en **"Reveal"** o **"Click to reveal"**
3. Copia el valor (empieza con `whsec_...`)

### 4. Agrega el Secret en Railway

1. Ve a Railway Dashboard → Tu Proyecto → **Variables**
2. Agrega una nueva variable:
   - **Nombre:** `STRIPE_WEBHOOK_SECRET`
   - **Valor:** `whsec_...` (el valor que copiaste)
3. **Guarda** - Railway reiniciará automáticamente

## ✅ Verificación

Después de configurar:

1. **Prueba el webhook:**
   - En Stripe Dashboard → Webhooks → Tu webhook
   - Haz clic en **"Send test webhook"**
   - Selecciona el evento `checkout.session.completed`
   - Debería aparecer como "Succeeded" (verde)

2. **Verifica los logs en Railway:**
   - Deberías ver mensajes como "✅ Webhook recibido correctamente"
   - No deberían aparecer errores de firma

3. **Prueba una compra real:**
   - Haz una compra de prueba desde el frontend
   - Verifica que el webhook se ejecute correctamente
   - Revisa que el plan del usuario se actualice en la base de datos

## 🔍 Endpoint en el Código

El endpoint está definido en `main.py`:

```python
@app.post("/billing/stripe-webhook")
async def stripe_webhook(request: Request):
    # Procesa webhooks de Stripe
```

## ⚠️ Notas Importantes

- El webhook **NO requiere autenticación** normal (Stripe lo firma con el secret)
- El endpoint debe ser **público** (no protegido con autenticación)
- Stripe enviará eventos **HTTPS** a tu endpoint
- Si el webhook falla, Stripe lo reintentará automáticamente

## 🐛 Solución de Problemas

### Error: "Firma de webhook inválida"
- Verifica que `STRIPE_WEBHOOK_SECRET` esté correctamente configurado en Railway
- Asegúrate de copiar el secret completo (empieza con `whsec_`)

### Error: "Webhook no recibido"
- Verifica que la URL sea correcta y accesible
- Prueba acceder a la URL desde tu navegador (debería dar error 405, pero significa que el endpoint existe)
- Revisa los logs de Railway para ver si hay errores

### El webhook no se ejecuta
- Verifica que los eventos estén seleccionados en Stripe
- Revisa que el endpoint esté respondiendo con código 200
- Verifica los logs de Railway

