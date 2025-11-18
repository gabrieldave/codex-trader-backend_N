# 🌐 Configurar URL del Backend en el Frontend

## 📋 Resumen

El backend ahora está disponible en `https://api.codextrader.tech`. Necesitas actualizar la configuración del frontend para que apunte a este nuevo dominio.

---

## 🔍 ¿Dónde se usa la URL del backend en el frontend?

El frontend necesita conocer la URL del backend para hacer llamadas a la API. Esto se configura típicamente mediante **variables de entorno**.

### Ejemplos de uso en el frontend:

1. **Llamadas a la API de autenticación/usuarios:**
   - `POST /users/notify-registration` - Para enviar email de bienvenida
   - `GET /users/profile` - Para obtener perfil del usuario
   - `POST /billing/create-checkout-session` - Para crear sesiones de checkout

2. **Llamadas a la API de chat:**
   - `POST /chat` - Para enviar mensajes
   - `GET /chat/history` - Para obtener historial

3. **Llamadas a la API de búsqueda:**
   - `POST /search` - Para búsquedas RAG

---

## ⚙️ Configuración por Tipo de Frontend

### Next.js (Recomendado)

#### 1. Variables de Entorno

Crea o actualiza el archivo `.env.local` (o `.env.production` para producción):

```env
# URL del Backend API
NEXT_PUBLIC_API_URL=https://api.codextrader.tech

# Para desarrollo local (opcional)
# NEXT_PUBLIC_API_URL=http://localhost:8000
```

**⚠️ IMPORTANTE:** En Next.js, las variables de entorno que empiezan con `NEXT_PUBLIC_` son accesibles desde el navegador. Las variables sin este prefijo solo están disponibles en el servidor.

#### 2. Crear archivo de configuración (Opcional pero recomendado)

Crea un archivo `lib/api-config.ts` o `config/api.ts`:

```typescript
// lib/api-config.ts
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const API_ENDPOINTS = {
  // Usuarios
  NOTIFY_REGISTRATION: `${API_URL}/users/notify-registration`,
  USER_PROFILE: `${API_URL}/users/profile`,
  
  // Billing
  CREATE_CHECKOUT: `${API_URL}/billing/create-checkout-session`,
  
  // Chat
  CHAT: `${API_URL}/chat`,
  CHAT_HISTORY: `${API_URL}/chat/history`,
  
  // Search
  SEARCH: `${API_URL}/search`,
} as const;
```

#### 3. Usar la configuración en tu código

```typescript
// Ejemplo: Llamar a /users/notify-registration
import { API_ENDPOINTS } from '@/lib/api-config';

async function notifyRegistration(token: string) {
  const response = await fetch(API_ENDPOINTS.NOTIFY_REGISTRATION, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });
  
  if (!response.ok) {
    throw new Error('Error al notificar registro');
  }
  
  return response.json();
}
```

---

### React / Vite

#### 1. Variables de Entorno

Crea o actualiza el archivo `.env` (o `.env.production` para producción):

```env
# URL del Backend API
VITE_API_URL=https://api.codextrader.tech

# Para desarrollo local (opcional)
# VITE_API_URL=http://localhost:8000
```

**⚠️ IMPORTANTE:** En Vite, las variables de entorno que se exponen al cliente deben empezar con `VITE_`.

#### 2. Usar la variable

```typescript
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function notifyRegistration(token: string) {
  const response = await fetch(`${API_URL}/users/notify-registration`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });
  
  return response.json();
}
```

---

### Create React App (CRA)

#### 1. Variables de Entorno

Crea o actualiza el archivo `.env` (o `.env.production` para producción):

```env
# URL del Backend API
REACT_APP_API_URL=https://api.codextrader.tech

# Para desarrollo local (opcional)
# REACT_APP_API_URL=http://localhost:8000
```

**⚠️ IMPORTANTE:** En Create React App, las variables de entorno que se exponen al cliente deben empezar con `REACT_APP_`.

#### 2. Usar la variable

```typescript
const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

async function notifyRegistration(token: string) {
  const response = await fetch(`${API_URL}/users/notify-registration`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
  });
  
  return response.json();
}
```

---

## 🔍 Verificar Configuración Actual

Para verificar qué URL está usando tu frontend actualmente, busca en tu código:

```bash
# Buscar llamadas a la API
grep -r "localhost:8000" .
grep -r "api.codextrader" .
grep -r "NEXT_PUBLIC_API_URL\|VITE_API_URL\|REACT_APP_API_URL" .
grep -r "/users/notify-registration\|/billing\|/chat" .
```

O en Windows:
```cmd
findstr /s /i "localhost:8000" *
findstr /s /i "api.codextrader" *
findstr /s /i "NEXT_PUBLIC_API_URL VITE_API_URL REACT_APP_API_URL" *
```

---

## 📝 Archivos Comunes a Revisar

Dependiendo de tu estructura, busca y actualiza estos archivos:

### Next.js:
- `.env.local` o `.env.production`
- `next.config.js` o `next.config.ts` (si hay configuración de API)
- `lib/api.ts` o `utils/api.ts` (donde se configuren las URLs)
- Componentes que hagan llamadas a la API

### React/Vite:
- `.env` o `.env.production`
- `vite.config.ts` (si hay configuración de proxy)
- `src/config/api.ts` o similar
- Componentes que hagan llamadas a la API

### Ejemplos de archivos comunes:
- `app/page.tsx` (Next.js App Router)
- `pages/_app.tsx` (Next.js Pages Router)
- `src/api/client.ts`
- `src/services/api.ts`
- `src/utils/fetch.ts`

---

## ✅ Checklist de Verificación

Después de hacer los cambios:

- [ ] Variable de entorno configurada (`NEXT_PUBLIC_API_URL`, `VITE_API_URL`, o `REACT_APP_API_URL`)
- [ ] Variable apunta a `https://api.codextrader.tech` en producción
- [ ] Variable apunta a `http://localhost:8000` en desarrollo (opcional)
- [ ] Código actualizado para usar la variable de entorno
- [ ] No hay URLs hardcodeadas del backend antiguo
- [ ] Pruebas realizadas en desarrollo
- [ ] Pruebas realizadas en producción

---

## 🧪 Probar la Configuración

### 1. Prueba en Desarrollo

1. Configura la variable de entorno para desarrollo (`http://localhost:8000`)
2. Inicia el frontend: `npm run dev`
3. Verifica que las llamadas a la API funcionen
4. Revisa la consola del navegador para ver las URLs que se están usando

### 2. Prueba en Producción

1. Configura la variable de entorno para producción (`https://api.codextrader.tech`)
2. Despliega el frontend
3. Verifica que las llamadas a la API funcionen
4. Revisa la consola del navegador (F12) para confirmar las URLs

### 3. Verificar Llamadas Específicas

#### Probar `/users/notify-registration`:
```javascript
// En la consola del navegador (después de iniciar sesión)
fetch('https://api.codextrader.tech/users/notify-registration', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}` // Reemplaza con tu token
  }
})
.then(r => r.json())
.then(console.log)
.catch(console.error);
```

#### Verificar que CORS funciona:
El backend ya está configurado para aceptar peticiones desde:
- `https://www.codextrader.tech`
- `https://codextrader.tech`
- `http://localhost:3000` (desarrollo)

Si tu frontend está en otro dominio, necesitas agregarlo en el backend (variable `FRONTEND_URL`).

---

## 🐛 Problemas Comunes

### Error: CORS bloqueado

**Síntoma:** En la consola del navegador ves:
```
Access to fetch at 'https://api.codextrader.tech/...' from origin 'https://www.codextrader.tech' has been blocked by CORS policy
```

**Solución:** Verifica que el backend tenga tu dominio en la lista de orígenes permitidos. El backend ya incluye `https://www.codextrader.tech` y `https://codextrader.tech`.

### Error: 404 Not Found

**Síntoma:** Las llamadas a la API devuelven 404

**Solución:** 
- Verifica que la URL sea correcta: `https://api.codextrader.tech`
- Verifica que no haya un `/api` extra en la URL (a menos que sea necesario)
- Revisa los logs del backend para ver qué rutas están disponibles

### Error: Variable de entorno no se lee

**Síntoma:** La variable de entorno tiene el valor `undefined` en el navegador

**Solución:**
- **Next.js:** Asegúrate de que la variable empiece con `NEXT_PUBLIC_`
- **Vite:** Asegúrate de que la variable empiece con `VITE_`
- **CRA:** Asegúrate de que la variable empiece con `REACT_APP_`
- Reinicia el servidor de desarrollo después de cambiar variables de entorno

---

## 📚 Referencias

- [Next.js Environment Variables](https://nextjs.org/docs/basic-features/environment-variables)
- [Vite Environment Variables](https://vitejs.dev/guide/env-and-mode.html)
- [Create React App Environment Variables](https://create-react-app.dev/docs/adding-custom-environment-variables/)

---

## 🎯 Resumen Rápido

**Para Next.js:**
```env
NEXT_PUBLIC_API_URL=https://api.codextrader.tech
```

**Para Vite:**
```env
VITE_API_URL=https://api.codextrader.tech
```

**Para Create React App:**
```env
REACT_APP_API_URL=https://api.codextrader.tech
```

¡Eso es todo! El backend ya está configurado para aceptar peticiones desde tu frontend. Solo necesitas actualizar la variable de entorno en el frontend. 🚀

