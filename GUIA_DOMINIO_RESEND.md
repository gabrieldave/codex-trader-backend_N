# 🌐 Guía: Configurar Dominio en Resend

## 🤔 ¿Para qué es "Add Domain"?

Agregar un dominio en Resend te permite:
- ✅ Enviar emails desde tu dominio personalizado (ej: `noreply@codextrader.tech`)
- ✅ Mejor deliverability (menos probabilidad de ir a spam)
- ✅ Emails más profesionales
- ✅ Verificación de dominio (SPF, DKIM, DMARC)

---

## 🎯 Opciones Disponibles

### Opción 1: Saltarse este paso (RECOMENDADO para empezar)

**Puedes saltarte agregar un dominio inicialmente:**
- ✅ Resend te da un dominio de prueba: `onboarding@resend.dev`
- ✅ Funciona inmediatamente sin configuración
- ✅ Puedes empezar a enviar emails ahora mismo
- ⚠️ Los emails vendrán de `onboarding@resend.dev` (no es tu dominio)

**Para usar el dominio de prueba:**
- No necesitas agregar dominio
- Solo configura `RESEND_API_KEY` en Railway
- Usa `EMAIL_FROM=Codex Trader <onboarding@resend.dev>` en Railway

---

### Opción 2: Agregar tu dominio (Opcional, más profesional)

**Si quieres usar tu dominio personalizado:**

#### Campo "Name":
```
codextrader.tech
```
O si quieres un subdominio específico:
```
mail.codextrader.tech
```
O:
```
noreply.codextrader.tech
```

#### Campo "Region":
- **North Virginia (us-east-1)** ← Recomendado (más rápido para usuarios en América)
- O la región más cercana a tus usuarios

---

## 📋 Pasos si Agregas tu Dominio

### 1. Agregar Dominio en Resend
- Name: `codextrader.tech` (o el subdominio que prefieras)
- Region: `North Virginia (us-east-1)` (recomendado)

### 2. Configurar Registros DNS
Resend te dará registros DNS que debes agregar en tu proveedor de dominio:

**Ejemplo de registros que Resend te dará:**
```
Tipo: TXT
Nombre: @
Valor: v=spf1 include:resend.com ~all

Tipo: CNAME
Nombre: resend._domainkey
Valor: resend.com

Tipo: TXT
Nombre: _dmarc
Valor: v=DMARC1; p=none;
```

### 3. Verificar Dominio
- Resend verificará automáticamente los registros DNS
- Puede tardar unos minutos a horas
- Una vez verificado, podrás usar tu dominio

### 4. Actualizar EMAIL_FROM en Railway
Cambiar de:
```
EMAIL_FROM=Codex Trader <onboarding@resend.dev>
```

A:
```
EMAIL_FROM=Codex Trader <noreply@codextrader.tech>
```
O:
```
EMAIL_FROM=Codex Trader <mail@codextrader.tech>
```

---

## 🎯 Recomendación

### Para Empezar Rápido:
1. ✅ **Saltarse agregar dominio** por ahora
2. ✅ Usar `onboarding@resend.dev` (dominio de prueba)
3. ✅ Configurar solo `RESEND_API_KEY` en Railway
4. ✅ Empezar a enviar emails inmediatamente

### Para Más Profesionalismo (Después):
1. ⏳ Agregar dominio `codextrader.tech` en Resend
2. ⏳ Configurar registros DNS en tu proveedor de dominio
3. ⏳ Esperar verificación
4. ⏳ Actualizar `EMAIL_FROM` en Railway

---

## 📝 Resumen

**¿Qué poner en "Add Domain"?**

**Si quieres saltarte este paso (recomendado para empezar):**
- ❌ No agregues nada, cierra esta ventana
- ✅ Ve directamente a "API Keys" para obtener tu API key

**Si quieres agregar tu dominio:**
- **Name:** `codextrader.tech` (o `mail.codextrader.tech`)
- **Region:** `North Virginia (us-east-1)`
- Luego configura los registros DNS que Resend te dé

---

## 🚀 Próximo Paso

**Para empezar rápido:**
1. Cierra la ventana de "Add Domain"
2. Ve a **API Keys** en el menú de Resend
3. Crea una nueva API key
4. Copia la key y configúrala en Railway como `RESEND_API_KEY`

¡Listo! Los emails funcionarán con el dominio de prueba de Resend.

