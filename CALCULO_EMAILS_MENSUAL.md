# 📊 Cálculo de Emails Mensuales por Cliente

## 📧 Tipos de Emails en el Sistema

### Emails al Usuario (Cliente):
1. **Email de Bienvenida** - 1 vez (al registrarse)
2. **Confirmación de Recarga de Tokens** - Cada recarga
3. **Email de Tokens Agotados** - 1 vez (cuando se agotan, con flag)
4. **Alerta 90% de Uso con Descuento** - 1 vez (cuando alcanza 90%, con flag)
5. **Confirmación de Activación/Renovación de Plan** - Cada compra/renovación
6. **Recordatorio de Renovación** - Varios antes de renovar (con flag)
7. **Recuperación de Usuarios Inactivos** - Varios si está inactivo (con flag)
8. **Contraseña Temporal** - Solo si se solicita (raro)

### Emails al Admin:
1. **Notificación de Nuevo Registro** - 1 vez por usuario nuevo
2. **Notificación de Recarga de Tokens** - Cada recarga de cualquier usuario
3. **Alerta 80% de Uso** - 1 vez por usuario que alcanza 80% (sin flag, puede repetirse)
4. **Alerta 90% de Uso** - 1 vez por usuario que alcanza 90% (sin flag)
5. **Notificación de Compra** - Cada compra de cualquier usuario
6. **Email de Error Crítico** - Solo si hay errores (raro)

---

## 🧮 Cálculo: 1 Cliente Activo en 1 Mes

### Escenario: Cliente Activo Típico

**Hipótesis:**
- Cliente se registra este mes
- Usa tokens activamente
- Hace 1 recarga de tokens
- Alcanza 80% y 90% de uso
- Tiene plan mensual (1 renovación)

### Emails al Cliente (Usuario):

| Tipo de Email | Cantidad | Frecuencia |
|---------------|----------|------------|
| Email de Bienvenida | **1** | Una vez al registrarse |
| Confirmación de Recarga | **1** | Por cada recarga |
| Tokens Agotados | **0** | Solo si se agotan (hipótesis: no se agotan) |
| Alerta 90% con Descuento | **1** | Una vez cuando alcanza 90% |
| Confirmación de Activación | **1** | Al comprar/activar plan |
| Recordatorio de Renovación | **2** | 7 días antes y 1 día antes |
| Recuperación Inactivos | **0** | Solo si está inactivo (hipótesis: activo) |
| **TOTAL CLIENTE** | **6 emails** | |

### Emails al Admin (por este cliente):

| Tipo de Email | Cantidad | Frecuencia |
|---------------|----------|------------|
| Notificación de Nuevo Registro | **1** | Una vez al registrarse |
| Notificación de Recarga | **1** | Por cada recarga del cliente |
| Alerta 80% de Uso | **1** | Una vez cuando alcanza 80% |
| Alerta 90% de Uso | **1** | Una vez cuando alcanza 90% |
| Notificación de Compra | **1** | Por cada compra del cliente |
| **TOTAL ADMIN** | **5 emails** | |

---

## 📊 Total por Cliente Activo

**Total emails por cliente activo en 1 mes:**
- Emails al cliente: **6 emails**
- Emails al admin: **5 emails**
- **TOTAL: 11 emails por cliente activo**

---

## 🎯 Cálculo para Diferentes Escenarios

### Escenario 1: Cliente Nuevo Activo (Primer Mes)
- Registro + uso activo + 1 recarga + alcanza 80%/90%
- **Total: 11 emails**

### Escenario 2: Cliente Activo Recurrente (Meses Siguientes)
- Sin registro (ya registrado)
- Uso activo + 1 recarga + alcanza 80%/90% + renovación
- **Total: ~8 emails** (sin email de bienvenida ni notificación de registro)

### Escenario 3: Cliente Poco Activo
- Sin recargas, sin alcanzar límites
- Solo renovación si tiene plan
- **Total: ~2-3 emails** (renovación + recordatorios)

### Escenario 4: Cliente Muy Activo
- Múltiples recargas (3-4/mes)
- Alcanza límites varias veces
- **Total: ~15-20 emails**

---

## 📈 Proyección Mensual

### Con 1 Cliente Activo:
- **11 emails/mes** (escenario típico)

### Con 10 Clientes Activos:
- **110 emails/mes** (10 × 11)

### Con 50 Clientes Activos:
- **550 emails/mes** (50 × 11)

### Con 100 Clientes Activos:
- **1,100 emails/mes** (100 × 11)

### Con 200 Clientes Activos:
- **2,200 emails/mes** (200 × 11)

### Con 300 Clientes Activos:
- **3,300 emails/mes** (300 × 11) ⚠️ **SOBREPASA 3,000**

---

## 🎯 Conclusión

### Límite de Resend Gratis: **3,000 emails/mes**

**Con el plan gratuito de Resend puedes tener:**
- ✅ **~270 clientes activos** (270 × 11 = 2,970 emails)
- ⚠️ **~300 clientes activos** (300 × 11 = 3,300 emails) - **SOBREPASA el límite**

### Recomendaciones:

1. **Para empezar (0-200 clientes):**
   - ✅ Plan gratuito de Resend (3,000/mes) es suficiente
   - ✅ No necesitas pagar nada

2. **Cuando crezcas (200-500 clientes):**
   - ⚠️ Necesitarás el plan de pago de Resend ($20/mes por 50,000 emails)
   - 💰 Costo: $20/mes (muy razonable)

3. **Optimizaciones:**
   - Algunos emails al admin podrían consolidarse
   - Algunos emails podrían ser opcionales
   - Podrías reducir recordatorios de renovación

---

## 💡 Recomendación Final

**Para empezar:**
- ✅ **Resend gratuito (3,000/mes) es perfecto**
- ✅ Te alcanza para ~270 clientes activos
- ✅ Cuando crezcas, $20/mes por 50,000 emails es muy barato

**No te preocupes por sobrepasar el límite al inicio.** Cuando tengas 200+ clientes activos, ya estarás generando ingresos suficientes para pagar $20/mes por emails.

