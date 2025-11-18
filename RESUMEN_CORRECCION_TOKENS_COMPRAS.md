# 🔧 Corrección: Tokens No Se Suman en Compras

## 🔍 Problema Identificado

Los tokens no se estaban sumando correctamente cuando un usuario completaba una compra. Después de la auditoría, se identificaron varios problemas críticos:

### Problemas Encontrados:

1. **Si `plan_code` no está en metadata del checkout:**
   - `tokens_per_month` nunca se obtiene
   - Los tokens NO se suman
   - No hay logging que indique el problema

2. **Si el plan no se encuentra en `plans.py`:**
   - `tokens_per_month` es `None`
   - Los tokens NO se suman
   - Solo hay un error silencioso

3. **Falta de validación post-actualización:**
   - No se verifica que los tokens se actualizaron correctamente
   - Si `update_response.data` está vacío, no hay confirmación

---

## ✅ Correcciones Implementadas

### 1. Logging Detallado Agregado

**Ubicación:** `handle_checkout_session_completed` (líneas ~3113-3183)

**Cambios:**
- ✅ Log cuando `plan_code` no está en metadata
- ✅ Log cuando el plan no se encuentra
- ✅ Log cuando `tokens_per_month` es `None`
- ✅ Log del valor de `update_data` antes de actualizar
- ✅ Log del resultado de la actualización
- ✅ Verificación que los tokens se actualizaron correctamente

**Ejemplo de logs agregados:**
```python
logger.error(f"❌ ERROR CRÍTICO: plan_code no está en metadata del checkout session")
logger.error(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado en plans.py")
logger.info(f"💰 Tokens sumados para usuario {user_id}: {current_tokens:,} + {tokens_per_month:,} = {new_tokens:,}")
```

### 2. Validaciones Mejoradas

**Cambios:**
- ✅ Verificación explícita cuando `plan_code` falta
- ✅ Verificación explícita cuando el plan no se encuentra
- ✅ Mensajes de error claros indicando por qué los tokens no se suman
- ✅ Verificación post-actualización que los tokens coinciden

**Código agregado:**
```python
if not plan_code:
    logger.error(f"❌ ERROR CRÍTICO: plan_code no está en metadata")
    print(f"❌ ERROR CRÍTICO: plan_code no está en metadata. Session ID: {session.get('id')}")
    print(f"   Metadata disponible: {metadata}")

if not plan:
    logger.error(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado en plans.py")
    print(f"❌ ERROR CRÍTICO: Plan '{plan_code}' no encontrado. Los tokens NO se sumarán.")

if not tokens_per_month:
    logger.error(f"❌ ERROR CRÍTICO: tokens_per_month es None")
    print(f"❌ ERROR CRÍTICO: tokens_per_month es None. Los tokens NO se actualizarán.")
```

### 3. Verificación Post-Actualización

**Cambios:**
- ✅ Verificación que `update_response.data` no está vacío
- ✅ Verificación que los tokens actualizados coinciden con los esperados
- ✅ Logging detallado del resultado

**Código agregado:**
```python
if update_response.data:
    updated_profile = update_response.data[0]
    updated_tokens = updated_profile.get("tokens_restantes")
    
    if "tokens_restantes" in update_data:
        expected_tokens = update_data["tokens_restantes"]
        if updated_tokens == expected_tokens:
            logger.info(f"✅ Perfil actualizado correctamente: tokens={updated_tokens:,}")
        else:
            logger.error(f"❌ ERROR: Tokens no coinciden. Esperado: {expected_tokens:,}, Actual: {updated_tokens}")
```

---

## 📋 Cómo Verificar que Funciona

### 1. Revisar los Logs del Webhook

Después de una compra, revisa los logs de Railway. Deberías ver:

**Si todo funciona correctamente:**
```
✅ Plan encontrado: explorer -> 150,000 tokens/mes
💰 Tokens sumados para usuario abc123: 0 + 150,000 = 150,000
📝 Actualizando perfil con: plan=explorer, tokens_restantes=sumados
✅ Perfil actualizado: plan=explorer, tokens=150,000
```

**Si hay problemas:**
```
❌ ERROR CRÍTICO: plan_code no está en metadata del checkout session
   Metadata disponible: {'user_id': 'abc123'}
```

O:
```
❌ ERROR CRÍTICO: Plan 'invalid_plan' no encontrado en plans.py
❌ ERROR CRÍTICO: tokens_per_month es None. Los tokens NO se actualizarán.
```

### 2. Verificar en la Base de Datos

Después de una compra, verifica en Supabase:

```sql
SELECT 
    id, 
    email, 
    current_plan, 
    tokens_restantes, 
    stripe_customer_id,
    created_at
FROM profiles
WHERE stripe_customer_id IS NOT NULL
ORDER BY created_at DESC
LIMIT 10;
```

Verifica que:
- `current_plan` tiene el código del plan correcto
- `tokens_restantes` tiene el valor esperado (tokens del plan)
- `stripe_customer_id` está configurado

### 3. Verificar en Stripe Dashboard

1. Ve a Stripe Dashboard → Customers
2. Busca el customer que hizo la compra
3. Ve a "Events" y busca `checkout.session.completed`
4. Verifica que el metadata incluye `plan_code` y `user_id`

---

## 🐛 Posibles Causas del Problema Original

### Causa 1: Metadata Faltante en Checkout

**Síntoma:** `plan_code` no está en metadata

**Solución:** Verificar que al crear el checkout session, se incluye el metadata:

```python
metadata={
    "user_id": user_id,
    "plan_code": plan_code  # ← Debe estar aquí
}
```

**Ubicación:** `create_checkout_session` en `main.py`

### Causa 2: Plan No Existe en plans.py

**Síntoma:** El plan_code no coincide con ningún plan en `plans.py`

**Solución:** Verificar que el `plan_code` usado en el checkout coincide con los códigos en `plans.py`:
- `explorer`
- `trader`
- `pro`
- `institucional`

### Causa 3: Error en la Actualización

**Síntoma:** `update_response.data` está vacío

**Solución:** Verificar que:
- El usuario existe en la tabla `profiles`
- El `user_id` es correcto
- No hay problemas de permisos en Supabase

---

## 🔧 Próximos Pasos Recomendados

1. **Monitorear los logs** después de cada compra para detectar problemas
2. **Agregar alertas** si los tokens no se suman (email al admin)
3. **Crear dashboard** para monitorear compras vs tokens asignados
4. **Agregar tests** para el flujo completo de checkout

---

## 📝 Archivos Modificados

- `main.py` - Función `handle_checkout_session_completed` (líneas ~3113-3228)
- `auditoria_tokens_compras.py` - Script de auditoría (nuevo)
- `RESUMEN_CORRECCION_TOKENS_COMPRAS.md` - Este documento

---

## ✅ Estado

**Correcciones implementadas:** ✅ Completado
**Logging agregado:** ✅ Completado
**Validaciones agregadas:** ✅ Completado
**Verificación post-actualización:** ✅ Completado

**Próximo paso:** Desplegar y monitorear los logs en producción

---

## 🆘 Si el Problema Persiste

1. **Revisa los logs de Railway** después de una compra
2. **Verifica el metadata** en Stripe Dashboard
3. **Verifica que el plan existe** en `plans.py`
4. **Verifica en la base de datos** que los tokens se actualizaron
5. **Comparte los logs** para diagnóstico adicional

