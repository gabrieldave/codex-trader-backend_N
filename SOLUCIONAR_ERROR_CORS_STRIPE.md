# 🔧 Solucionar Error CORS en Stripe Checkout

## ❌ Error Detectado

```
Access to fetch at 'https://api.codextrader.tech/billing/create-checkout-session' 
from origin 'https://www.codextrader.tech' has been blocked by CORS policy: 
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

## 🔍 Causa

El backend no está enviando el header `Access-Control-Allow-Origin` correctamente, lo que bloquea las peticiones desde el frontend.

## ✅ Solución

### Paso 1: Verificar que el Backend Esté Actualizado

El código ya incluye `https://www.codextrader.tech` en la lista de orígenes permitidos. Asegúrate de que:

1. **El código actualizado esté en Railway:**
   - Ve a Railway Dashboard → Tu Proyecto
   - Verifica que el último commit esté desplegado
   - Si no, haz **"Redeploy"** o **"Deploy Latest Commit"**

2. **Verificar los logs del backend:**
   - En Railway → Logs
   - Busca el mensaje: `🌐 CORS configurado - Orígenes permitidos:`
   - Verifica que incluya `https://www.codextrader.tech`

### Paso 2: Verificar Variable FRONTEND_URL en Railway

1. Ve a Railway Dashboard → Tu Proyecto → **Variables**
2. Verifica que exista la variable:
   - **Nombre:** `FRONTEND_URL`
   - **Valor:** `https://www.codextrader.tech` (sin `/app`, sin `/` al final)
3. Si no existe o está incorrecta, créala/corrígela y haz **Redeploy**

### Paso 3: Limpiar Cache y Redeploy

1. En Railway Dashboard → Tu Proyecto → **Settings** → **Build**
2. Haz clic en **"Clear Build Cache"**
3. Haz clic en **"Redeploy"** o **"Deploy Latest Commit"**
4. Espera a que termine el deploy

### Paso 4: Verificar que Funciona

1. Después del redeploy, verifica los logs:
   - Busca: `🌐 CORS configurado - Orígenes permitidos:`
   - Debe incluir: `https://www.codextrader.tech`

2. Prueba desde el frontend:
   - Haz clic en el botón de compra
   - Debe redirigir a Stripe sin errores de CORS

## 🐛 Si el Problema Persiste

### Opción 1: Usar `allow_origins=["*"]` Temporalmente (NO Recomendado para Producción)

**⚠️ SOLO PARA TESTING** - Esto permite cualquier origen:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Solo para testing
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)
```

**NO usar en producción** por razones de seguridad.

### Opción 2: Verificar Headers del Response

Asegúrate de que el endpoint `/billing/create-checkout-session` no esté sobrescribiendo los headers de CORS.

### Opción 3: Verificar el Origen Exacto

En la consola del navegador, verifica el origen exacto desde donde se está haciendo la petición:
- Debe ser exactamente: `https://www.codextrader.tech`
- No debe incluir subdirectorios como `/app`

## 🔍 Debugging

### Verificar en los Logs de Railway

Después de hacer un redeploy, busca en los logs:

```
🌐 CORS configurado - Orígenes permitidos: ['https://www.codextrader.tech', 'https://codextrader.tech', ...]
```

### Probar desde la Consola del Navegador

```javascript
// En la consola del navegador (F12)
fetch('https://api.codextrader.tech/billing/create-checkout-session', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer TU_TOKEN_AQUI'
  },
  body: JSON.stringify({
    planCode: 'pro'
  })
})
.then(r => {
  console.log('Status:', r.status);
  console.log('Headers:', [...r.headers.entries()]);
  return r.json();
})
.then(console.log)
.catch(console.error);
```

Deberías ver en los headers:
```
access-control-allow-origin: https://www.codextrader.tech
```

## ✅ Checklist

- [ ] Código actualizado en Railway (último commit desplegado)
- [ ] Variable `FRONTEND_URL` configurada en Railway como `https://www.codextrader.tech`
- [ ] Build cache limpiado
- [ ] Redeploy realizado
- [ ] Logs verificados - CORS incluye `https://www.codextrader.tech`
- [ ] Prueba desde el frontend - funciona sin errores de CORS

## 📝 Nota

El código ya está configurado correctamente. El problema probablemente es que Railway necesita un redeploy para aplicar los cambios o la variable `FRONTEND_URL` no está configurada correctamente.

¡Con estos pasos debería funcionar! 🚀

