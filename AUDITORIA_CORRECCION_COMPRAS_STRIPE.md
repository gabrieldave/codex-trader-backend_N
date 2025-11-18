# Auditoría y Corrección: Compras con Stripe

## Problemas Identificados

### 1. ❌ No se enviaba email al usuario después de compra
**Problema:** Solo se enviaba email al admin, pero el usuario no recibía confirmación de su compra ni información sobre los tokens recibidos.

**Solución:** Agregado email de confirmación al usuario con:
- Detalles del plan adquirido
- Cantidad de tokens recibidos
- Monto pagado
- Fecha de próxima renovación
- Botón para empezar a usar Codex Trader

**Archivo:** `main.py` líneas 3355-3458

---

### 2. ❌ 4 Notificaciones Duplicadas en Frontend
**Problema:** El `useEffect` se ejecutaba múltiples veces cuando `checkout=success` estaba en la URL, mostrando la notificación 4 veces.

**Solución:** 
- Agregado `useRef` para rastrear si ya se mostró la notificación
- La notificación solo se muestra una vez
- Se resetea la bandera después de limpiar la URL

**Archivo:** `app/page.tsx` líneas 42, 338-358

---

### 3. ⚠️ Tokens No Se Recargan
**Estado:** El código de suma de tokens está correcto, pero puede fallar si:
- `plan_code` no está en metadata del checkout session
- El plan no existe en `plans.py`
- `tokens_per_month` es `None`

**Verificación Necesaria:**
1. Verificar que `plan_code` se esté pasando en metadata al crear el checkout session
2. Verificar que el plan existe en `plans.py`
3. Revisar logs del backend cuando se procesa el webhook

**Archivo:** `main.py` líneas 3113-3183

---

## Correcciones Aplicadas

### Backend (`main.py`)
1. ✅ Agregado email al usuario con detalles de compra y tokens recibidos
2. ✅ Mejorado manejo de `amount_usd` para emails (obtiene desde Stripe o usa precio del plan)
3. ✅ Mejorado logging para debugging de tokens
4. ✅ Verificación post-actualización de tokens para asegurar que se sumaron correctamente

### Frontend (`app/page.tsx`)
1. ✅ Agregado `useRef` para evitar notificaciones duplicadas
2. ✅ Mejorado timing de limpieza de URL para evitar re-ejecuciones

---

## Flujo Correcto de Compra

1. **Usuario completa checkout en Stripe**
2. **Stripe envía webhook `checkout.session.completed`** → `/billing/stripe-webhook`
3. **Backend procesa el webhook:**
   - Extrae `user_id` y `plan_code` de metadata
   - Obtiene `tokens_per_month` del plan
   - Suma tokens: `current_tokens + tokens_per_month = new_tokens`
   - Actualiza perfil en Supabase
   - Verifica que tokens se actualizaron correctamente
   - Registra pago en `stripe_payments`
   - **Envía email al admin** (nueva compra)
   - **Envía email al usuario** (confirmación con tokens recibidos)
4. **Frontend detecta `checkout=success` en URL:**
   - Muestra notificación UNA VEZ
   - Recarga tokens y conversaciones
   - Limpia parámetros de URL

---

## Verificaciones Pendientes

### 1. Verificar Metadata del Checkout Session
Asegurar que al crear el checkout session se incluya:
```python
metadata={
    "user_id": user_id,
    "plan_code": plan_code
}
```

### 2. Verificar Logs del Backend
Cuando se procesa un webhook, revisar logs para:
- `✅ Plan encontrado: {plan_code} -> {tokens_per_month:,} tokens/mes`
- `💰 Tokens sumados para usuario {user_id}: {current_tokens:,} + {tokens_per_month:,} = {new_tokens:,}`
- `✅ Perfil actualizado: plan={plan_code}, tokens={updated_tokens:,}`

### 3. Verificar Emails
- Email al admin debe llegar con detalles de la compra
- Email al usuario debe llegar con confirmación y tokens recibidos

---

## Posibles Problemas Restantes

### Si los tokens NO se suman:
1. Verificar que `plan_code` esté en metadata del checkout session
2. Verificar que el plan existe en `plans.py` y tiene `tokens_per_month` definido
3. Revisar logs del backend para ver errores específicos

### Si los emails NO llegan:
1. Verificar configuración de Resend (`RESEND_API_KEY` y `EMAIL_FROM`)
2. Revisar logs del backend para errores de envío
3. Verificar que `user_email` se obtiene correctamente

### Si las notificaciones siguen duplicadas:
1. Verificar que `checkoutNotificationSent.current` se está usando correctamente
2. Verificar que la URL se limpia correctamente

---

## Archivos Modificados

- `main.py`: Agregado email al usuario, mejorado manejo de amount_usd
- `app/page.tsx`: Agregado useRef para evitar notificaciones duplicadas

---

## Próximos Pasos

1. Probar con una compra real
2. Verificar que:
   - Los tokens se suman correctamente
   - Llegan ambos emails (admin y usuario)
   - Solo se muestra UNA notificación
3. Revisar logs del backend si hay problemas

