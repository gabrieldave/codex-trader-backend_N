# 🔧 Solucionar Error de Chat - URLs Incorrectas

## ❌ Errores Detectados

Según los logs y errores del navegador:

1. **Error: "Failed to parse URL from api.codextrader.tech/chat"**
   - Problema: Falta el protocolo `https://` en la URL
   - Debe ser: `https://api.codextrader.tech/chat`

2. **Error: ERR_CONNECTION_REFUSED en localhost:8000**
   - Problema: El frontend todavía intenta conectarse a `localhost:8000`
   - Solución: Actualizar todas las referencias a usar `https://api.codextrader.tech`

3. **Error: 500 en `/api/tokens`, `/api/chat-sessions`, `/api/chat-simple`**
   - Problema: El frontend está agregando `/api` al inicio de las rutas
   - El backend NO usa el prefijo `/api`
   - Debe ser: `/tokens`, `/chat-sessions`, `/chat-simple` (sin `/api`)

---

## 🔍 Diagnosticar el Problema en el Frontend

### 1. Buscar URLs Hardcodeadas

Busca en tu código del frontend:

```bash
# Buscar referencias a localhost:8000
grep -r "localhost:8000" .

# Buscar referencias sin protocolo
grep -r "api.codextrader.tech" .

# Buscar rutas con /api incorrecto
grep -r "/api/chat\|/api/tokens\|/api/chat-sessions" .
```

O en Windows:
```cmd
findstr /s /i "localhost:8000" *
findstr /s /i "api.codextrader.tech" *
findstr /s /i "/api/chat /api/tokens /api/chat-sessions" *
```

---

## ✅ Correcciones Necesarias

### Problema 1: URL sin Protocolo

**❌ Incorrecto:**
```typescript
const url = 'api.codextrader.tech/chat';  // Falta https://
fetch(url);
```

**✅ Correcto:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const url = `${API_URL}/chat`;  // Con https://
fetch(url);
```

### Problema 2: Agregando Prefijo /api Incorrecto

**❌ Incorrecto:**
```typescript
fetch('/api/chat', {...});  // ❌ El backend NO tiene /api
fetch('/api/tokens', {...});  // ❌ El backend NO tiene /api
fetch('/api/chat-sessions', {...});  // ❌ El backend NO tiene /api
```

**✅ Correcto:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

fetch(`${API_URL}/chat`, {...});  // ✅ Sin /api
fetch(`${API_URL}/tokens`, {...});  // ✅ Sin /api
fetch(`${API_URL}/chat-sessions`, {...});  // ✅ Sin /api
```

### Problema 3: URLs Hardcodeadas

**❌ Incorrecto:**
```typescript
fetch('http://localhost:8000/chat', {...});  // ❌ Hardcodeado
```

**✅ Correcto:**
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
fetch(`${API_URL}/chat`, {...});  // ✅ Usando variable
```

---

## 📝 Rutas Correctas del Backend

El backend tiene estas rutas (sin `/api`):

### Chat
- `POST /chat` - Enviar mensaje al chat
- `POST /chat-simple` - Alias de `/chat`

### Sesiones de Chat
- `GET /chat-sessions` - Listar sesiones
- `POST /chat-sessions` - Crear nueva sesión
- `GET /chat-sessions/{id}/messages` - Obtener mensajes de una sesión
- `PATCH /chat-sessions/{id}` - Actualizar sesión
- `DELETE /chat-sessions/{id}` - Eliminar sesión

### Tokens
- `GET /tokens` - Obtener tokens disponibles
- `POST /tokens/reload` - Recargar tokens
- `POST /tokens/reset` - Resetear tokens

---

## 🛠️ Solución Paso a Paso

### Paso 1: Crear o Actualizar Archivo de Configuración

Crea `lib/api-config.ts` (o `config/api.ts`):

```typescript
// lib/api-config.ts
export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Asegurar que la URL termine sin barra
const cleanApiUrl = API_URL.replace(/\/$/, '');

export const API_ENDPOINTS = {
  // Chat
  CHAT: `${cleanApiUrl}/chat`,
  CHAT_SIMPLE: `${cleanApiUrl}/chat-simple`,
  
  // Chat Sessions
  CHAT_SESSIONS: `${cleanApiUrl}/chat-sessions`,
  CHAT_SESSION_MESSAGES: (id: string) => `${cleanApiUrl}/chat-sessions/${id}/messages`,
  CHAT_SESSION_UPDATE: (id: string) => `${cleanApiUrl}/chat-sessions/${id}`,
  CHAT_SESSION_DELETE: (id: string) => `${cleanApiUrl}/chat-sessions/${id}`,
  
  // Tokens
  TOKENS: `${cleanApiUrl}/tokens`,
  TOKENS_RELOAD: `${cleanApiUrl}/tokens/reload`,
  TOKENS_RESET: `${cleanApiUrl}/tokens/reset`,
  
  // Usuarios
  NOTIFY_REGISTRATION: `${cleanApiUrl}/users/notify-registration`,
  USER_PROFILE: `${cleanApiUrl}/users/profile`,
  
  // Billing
  CREATE_CHECKOUT: `${cleanApiUrl}/billing/create-checkout-session`,
} as const;
```

### Paso 2: Actualizar Todas las Llamadas a la API

Reemplaza todas las llamadas hardcodeadas:

**Antes:**
```typescript
// ❌ Incorrecto
const response = await fetch('/api/chat', {
  method: 'POST',
  body: JSON.stringify({ query: 'test' })
});
```

**Después:**
```typescript
// ✅ Correcto
import { API_ENDPOINTS } from '@/lib/api-config';

const response = await fetch(API_ENDPOINTS.CHAT, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  },
  body: JSON.stringify({ query: 'test' })
});
```

### Paso 3: Verificar Variable de Entorno en Vercel

1. Ve a **Vercel Dashboard** → Tu Proyecto → **Settings** → **Environment Variables**
2. Verifica que exista:
   - **Nombre:** `NEXT_PUBLIC_API_URL`
   - **Valor:** `https://api.codextrader.tech`
   - **Entornos:** Production, Preview, Development (o al menos Production)

3. Si no existe, créala y haz redeploy

### Paso 4: Verificar que la URL no Tenga Barra Final

**❌ Incorrecto:**
```env
NEXT_PUBLIC_API_URL=https://api.codextrader.tech/
```

**✅ Correcto:**
```env
NEXT_PUBLIC_API_URL=https://api.codextrader.tech
```

### Paso 5: Función Helper para Fetch (Opcional)

Crea una función helper para asegurar que todas las llamadas usen la URL correcta:

```typescript
// lib/api-client.ts
import { API_ENDPOINTS } from './api-config';

export async function apiFetch(
  endpoint: string,
  options: RequestInit = {}
): Promise<Response> {
  // Asegurar que endpoint empiece con /
  const url = endpoint.startsWith('http') 
    ? endpoint  // Ya es una URL completa
    : endpoint.startsWith('/')
    ? `${API_ENDPOINTS.CHAT.replace('/chat', '')}${endpoint}`  // Agregar base URL
    : `${API_ENDPOINTS.CHAT.replace('/chat', '')}/${endpoint}`;  // Agregar base URL y /

  // Asegurar que no tenga /api
  const cleanUrl = url.replace(/\/api\//, '/');

  return fetch(cleanUrl, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
}

// Uso:
const response = await apiFetch('/chat', {
  method: 'POST',
  body: JSON.stringify({ query: 'test' })
});
```

---

## 🔍 Buscar y Reemplazar en el Código

### Buscar Patrones Problemáticos

```typescript
// Buscar estos patrones y reemplazarlos:

// 1. Referencias a localhost:8000
"localhost:8000"
'localhost:8000'
`localhost:8000`

// 2. URLs sin protocolo
"api.codextrader.tech"
'api.codextrader.tech'

// 3. Rutas con /api incorrecto
"/api/chat"
"/api/tokens"
"/api/chat-sessions"
"/api/chat-simple"

// 4. Funciones fetch con URLs incorrectas
fetch('/api/
fetch('api.codextrader.tech
fetch('localhost:8000
```

---

## ✅ Checklist de Verificación

Después de hacer los cambios:

- [ ] Variable `NEXT_PUBLIC_API_URL` configurada en Vercel como `https://api.codextrader.tech`
- [ ] Variable no tiene barra final (`/`)
- [ ] Todas las URLs usan la variable de entorno (no hardcodeadas)
- [ ] No hay prefijo `/api` en las rutas
- [ ] Todas las URLs incluyen el protocolo `https://`
- [ ] Código actualizado para usar `API_ENDPOINTS` o similar
- [ ] No hay referencias a `localhost:8000` en producción
- [ ] Pruebas realizadas y funcionando

---

## 🧪 Probar los Cambios

### 1. Verificar en la Consola del Navegador

Después de desplegar, abre la consola (F12) y verifica:

1. **No debe haber errores de parseo de URL**
2. **Las llamadas deben ser a `https://api.codextrader.tech/...`**
3. **No debe haber intentos de conexión a `localhost:8000`**
4. **Las rutas NO deben empezar con `/api`**

### 2. Probar Endpoint de Chat

```javascript
// En la consola del navegador (después de iniciar sesión)
const token = 'TU_TOKEN_AQUI';  // Reemplaza con tu token real

fetch('https://api.codextrader.tech/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    query: 'Hola, prueba',
    conversation_id: null
  })
})
.then(r => r.json())
.then(console.log)
.catch(console.error);
```

### 3. Verificar Headers de las Peticiones

En las DevTools → Network:
- Las peticiones deben ir a `https://api.codextrader.tech`
- No deben ir a `localhost:8000`
- No deben tener `/api` en la ruta

---

## 🐛 Problemas Comunes

### Error: "Failed to parse URL"

**Causa:** URL sin protocolo (`https://`)

**Solución:** Asegúrate de que `API_URL` incluya el protocolo:
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
// Debe ser: 'https://api.codextrader.tech' o 'http://localhost:8000'
```

### Error: 404 en /api/chat

**Causa:** Prefijo `/api` incorrecto

**Solución:** Elimina el prefijo `/api`:
```typescript
// ❌ Incorrecto
fetch('/api/chat')

// ✅ Correcto
fetch(`${API_URL}/chat`)
```

### Error: ERR_CONNECTION_REFUSED

**Causa:** Intentando conectar a `localhost:8000` en producción

**Solución:** Verifica que la variable de entorno esté configurada en Vercel

---

## 📚 Ejemplo Completo

```typescript
// lib/api-client.ts
import { API_ENDPOINTS } from './api-config';

interface ChatRequest {
  query: string;
  conversation_id?: string | null;
}

export async function sendChatMessage(
  query: string,
  conversationId: string | null = null,
  token: string
): Promise<any> {
  const response = await fetch(API_ENDPOINTS.CHAT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      query,
      conversation_id: conversationId,
    } as ChatRequest),
  });

  if (!response.ok) {
    throw new Error(`Error ${response.status}: ${response.statusText}`);
  }

  return response.json();
}

// Uso en un componente:
import { sendChatMessage } from '@/lib/api-client';

async function handleSendMessage() {
  try {
    const result = await sendChatMessage(
      'Hola, prueba',
      null,
      userToken
    );
    console.log('Respuesta:', result);
  } catch (error) {
    console.error('Error:', error);
  }
}
```

---

## 🎯 Resumen Rápido

**Los problemas principales son:**

1. ❌ URL sin `https://` → ✅ Agregar protocolo
2. ❌ Prefijo `/api` incorrecto → ✅ Eliminar `/api`
3. ❌ URLs hardcodeadas → ✅ Usar variable de entorno

**La solución:**
1. Configurar `NEXT_PUBLIC_API_URL=https://api.codextrader.tech` en Vercel
2. Usar la variable en todo el código
3. Eliminar cualquier referencia a `/api` en las rutas
4. Verificar que todas las URLs incluyan el protocolo

¡Con estos cambios, el chat debería funcionar correctamente! 🚀

