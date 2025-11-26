# 🚀 GUÍA COMPLETA PARA REPLICAR SAAS RAG CON IA

## Descripción del Proyecto Base
Este es un SaaS de consultoría con IA que permite a usuarios hacer preguntas sobre una base de conocimiento (libros/documentos). Incluye:
- Chat con IA usando RAG (Retrieval Augmented Generation)
- Análisis de imágenes con Gemini
- Sistema de tokens y planes de suscripción
- Autenticación con Supabase
- Pagos con Stripe

## Repositorios de Referencia (Codex Trader)
- **Backend**: https://github.com/gabrieldave/codex-trader-backend_N
- **Frontend**: https://github.com/gabrieldave/codex-trader-frontend

---

# 📋 CHECKLIST DE REPLICACIÓN

## FASE 1: PREPARACIÓN (30 min)

### 1.1 Definir información del nuevo SaaS
```
NOMBRE_SAAS: [ej: Codex Legal]
DOMINIO: [ej: codexlegal.tech]
TEMA: [ej: Derecho y leyes mexicanas]
ROL_EXPERTO: [ej: abogado experto en derecho mexicano]
COLOR_PRIMARIO: [ej: #1e40af (azul)]
COLOR_SECUNDARIO: [ej: #3b82f6]
```

### 1.2 Preparar cuentas necesarias
- [ ] Cuenta en Supabase (https://supabase.com)
- [ ] Cuenta en Stripe (https://stripe.com)
- [ ] Cuenta en Railway (https://railway.app)
- [ ] Cuenta en Vercel (https://vercel.com)
- [ ] Dominio comprado
- [ ] API Key de DeepSeek (https://platform.deepseek.com)
- [ ] API Key de Google/Gemini (https://makersuite.google.com/app/apikey)
- [ ] Cuenta en Resend para emails (https://resend.com)

### 1.3 Preparar contenido
- [ ] Libros/documentos en formato PDF para indexar
- [ ] Logo del nuevo SaaS
- [ ] Textos de marketing (descripciones, beneficios)

---

## FASE 2: CLONAR Y CONFIGURAR REPOSITORIOS (20 min)

### 2.1 Clonar repositorios
```bash
# Crear carpeta del proyecto
mkdir MI_NUEVO_SAAS
cd MI_NUEVO_SAAS

# Clonar backend
git clone https://github.com/gabrieldave/codex-trader-backend_N.git backend
cd backend
rm -rf .git
git init

# Clonar frontend
cd ..
git clone https://github.com/gabrieldave/codex-trader-frontend.git frontend
cd frontend
rm -rf .git
git init
```

### 2.2 Crear nuevos repositorios en GitHub
- Crear repo: `[tu-usuario]/[nombre-saas]-backend`
- Crear repo: `[tu-usuario]/[nombre-saas]-frontend`

```bash
# En carpeta backend
git remote add origin https://github.com/[tu-usuario]/[nombre-saas]-backend.git

# En carpeta frontend
git remote add origin https://github.com/[tu-usuario]/[nombre-saas]-frontend.git
```

---

## FASE 3: CONFIGURAR SUPABASE (45 min)

### 3.1 Crear nuevo proyecto en Supabase
1. Ir a https://supabase.com/dashboard
2. Click "New Project"
3. Elegir organización
4. Nombre: [nombre-saas]-db
5. Región: us-west-1 (o la más cercana)
6. Guardar la contraseña de la base de datos

### 3.2 Obtener credenciales
En Settings > API, copiar:
- `SUPABASE_URL`: URL del proyecto
- `SUPABASE_ANON_KEY`: anon/public key
- `SUPABASE_SERVICE_ROLE_KEY`: service_role key (secreto)

### 3.3 Ejecutar SQL para crear tablas
En SQL Editor, ejecutar estos scripts en orden:

```sql
-- 1. Habilitar extensión pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Crear tabla de documentos
CREATE TABLE IF NOT EXISTS documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    doc_id TEXT UNIQUE NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT,
    chunk_count INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Crear tabla de chunks con embeddings 384d
CREATE TABLE IF NOT EXISTS book_chunks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    doc_id TEXT NOT NULL,
    chunk_id TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);

-- 4. Crear índice para búsqueda vectorial
CREATE INDEX IF NOT EXISTS book_chunks_embedding_idx 
ON book_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 5. Crear función de búsqueda semántica
CREATE OR REPLACE FUNCTION match_documents_384(
    query_embedding vector(384),
    match_count int DEFAULT 5,
    category_filter text DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    doc_id TEXT,
    chunk_id TEXT,
    content TEXT,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        bc.id,
        bc.doc_id,
        bc.chunk_id,
        bc.content,
        bc.metadata,
        1 - (bc.embedding <=> query_embedding) AS similarity
    FROM book_chunks bc
    WHERE (category_filter IS NULL OR bc.metadata->>'category' = category_filter)
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 6. Crear tabla de perfiles de usuario
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT,
    name TEXT,
    tokens_restantes INTEGER DEFAULT 20000,
    tokens_monthly_limit INTEGER DEFAULT 20000,
    current_plan TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_status TEXT DEFAULT 'inactive',
    welcome_email_sent BOOLEAN DEFAULT FALSE,
    tokens_exhausted_email_sent BOOLEAN DEFAULT FALSE,
    fair_use_warning_shown BOOLEAN DEFAULT FALSE,
    fair_use_email_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Crear tabla de sesiones de chat
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. Crear tabla de conversaciones/mensajes
CREATE TABLE IF NOT EXISTS conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    conversation_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    message_role TEXT NOT NULL,
    message_content TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. Crear tabla de uso de modelos
CREATE TABLE IF NOT EXISTS model_usage_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_input INTEGER DEFAULT 0,
    tokens_output INTEGER DEFAULT 0,
    cost_estimated_usd DECIMAL(10, 6) DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 10. Crear trigger para crear perfil automáticamente
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, email, tokens_restantes, tokens_monthly_limit, current_plan)
    VALUES (NEW.id, NEW.email, 20000, 20000, 'free');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 11. Habilitar RLS
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- 12. Crear políticas RLS
CREATE POLICY "Users can view own profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can view own sessions" ON chat_sessions FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own sessions" ON chat_sessions FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can view own conversations" ON conversations FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own conversations" ON conversations FOR INSERT WITH CHECK (auth.uid() = user_id);
```

### 3.4 Configurar autenticación
En Authentication > Providers:
- Habilitar Email/Password
- Configurar Site URL: https://[tu-dominio].com
- Configurar Redirect URLs: https://[tu-dominio].com/*

---

## FASE 4: CONFIGURAR STRIPE (30 min)

### 4.1 Crear productos y precios en Stripe
En Stripe Dashboard > Products, crear:

| Producto | Precio | Price ID |
|----------|--------|----------|
| Explorer | $9.99/mes | price_xxx |
| Trader | $19.99/mes | price_xxx |
| Pro | $39.99/mes | price_xxx |
| Institucional | $99.99/mes | price_xxx |

### 4.2 Configurar Webhook
En Developers > Webhooks:
1. Add endpoint: `https://api.[tu-dominio].com/billing/stripe-webhook`
2. Eventos a escuchar:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
3. Guardar `STRIPE_WEBHOOK_SECRET`

### 4.3 Obtener API Keys
En Developers > API Keys:
- `STRIPE_SECRET_KEY`: sk_live_xxx (o sk_test_xxx para pruebas)
- `STRIPE_PUBLISHABLE_KEY`: pk_live_xxx

---

## FASE 5: PERSONALIZAR BACKEND (1 hora)

### 5.1 Archivos a modificar

#### `backend/config.py`
Cambiar:
```python
# Nombre del proyecto
PROJECT_NAME = "[NOMBRE_SAAS]"

# Tokens iniciales (ajustar si es necesario)
INITIAL_TOKENS = 20000
```

#### `backend/plans.py`
Cambiar nombres y descripciones de planes según el tema.

#### `backend/lib/llm_service.py`
Modificar el prompt del sistema (línea ~240):
```python
# ANTES (trading)
system_prompt = """Eres CODEX TRADER, un experto en trading..."""

# DESPUÉS (tu tema)
system_prompt = """Eres [NOMBRE_SAAS], un experto en [TEMA]..."""
```

Buscar y reemplazar todas las referencias a "trading", "trader", "mercados" por términos de tu tema.

#### `backend/lib/vision_service.py`
Modificar el prompt de análisis de imágenes (línea ~93):
```python
# ANTES
system_prompt = """Actúa como un experto analista técnico de trading..."""

# DESPUÉS
system_prompt = """Actúa como un experto en [TEMA]. Analiza esta imagen..."""
```

#### `backend/lib/email.py`
Cambiar:
- Nombre del producto en emails
- URLs
- Textos de marketing

#### `backend/main.py`
Cambiar título y descripción de la API:
```python
app = FastAPI(
    title="[NOMBRE_SAAS] API",
    description="API para [descripción]",
    version="1.0.0"
)
```

### 5.2 Crear archivo .env
```env
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=eyJxxx
SUPABASE_SERVICE_ROLE_KEY=eyJxxx

# APIs de IA
DEEPSEEK_API_KEY=sk-xxx
GOOGLE_API_KEY=AIzaxxx

# Stripe
STRIPE_SECRET_KEY=sk_live_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
STRIPE_PRICE_EXPLORER=price_xxx
STRIPE_PRICE_TRADER=price_xxx
STRIPE_PRICE_PRO=price_xxx
STRIPE_PRICE_INSTITUCIONAL=price_xxx

# URLs
FRONTEND_URL=https://www.[tu-dominio].com
BACKEND_URL=https://api.[tu-dominio].com

# Email (Resend)
RESEND_API_KEY=re_xxx
EMAIL_FROM=noreply@mail.[tu-dominio].com
ADMIN_EMAIL=[tu-email]
```

---

## FASE 6: PERSONALIZAR FRONTEND (1 hora)

### 6.1 Archivos a modificar

#### `frontend/.env.local`
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJxxx
NEXT_PUBLIC_BACKEND_URL=https://api.[tu-dominio].com
```

#### `frontend/lib/plans.ts`
Cambiar nombres y descripciones de planes.

#### `frontend/app/page.tsx`
- Cambiar nombre del producto
- Cambiar textos de bienvenida
- Cambiar colores del tema
- Cambiar placeholder del chat

#### `frontend/app/layout.tsx`
```tsx
export const metadata: Metadata = {
  title: "[NOMBRE_SAAS]",
  description: "[Descripción]",
};
```

#### `frontend/app/globals.css`
Cambiar variables de colores:
```css
:root {
  --primary: [tu-color-primario];
  --secondary: [tu-color-secundario];
}
```

#### `frontend/public/`
- Reemplazar logo
- Reemplazar favicon
- Reemplazar imágenes de marketing

### 6.2 Buscar y reemplazar global
En todo el frontend, buscar y reemplazar:
- "Codex Trader" → "[NOMBRE_SAAS]"
- "codextrader" → "[nombre-saas]"
- "trading" → "[tu-tema]"
- "trader" → "[tu-usuario-tipo]"

---

## FASE 7: INGESTAR DOCUMENTOS (Variable)

### 7.1 Preparar documentos
1. Crear carpeta `backend/data/`
2. Copiar todos los PDFs/documentos ahí
3. Organizar en subcarpetas por categoría si es necesario

### 7.2 Ejecutar ingesta
```bash
cd backend

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o: venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar ingesta
python ingest_optimized_rag.py
```

### 7.3 Verificar ingesta
```bash
python check_status.py
python view_data.py
```

---

## FASE 8: DEPLOY (30 min)

### 8.1 Deploy Backend en Railway
1. Ir a https://railway.app
2. New Project > Deploy from GitHub repo
3. Seleccionar repo del backend
4. Agregar todas las variables de entorno
5. Configurar dominio personalizado: api.[tu-dominio].com

### 8.2 Deploy Frontend en Vercel
1. Ir a https://vercel.com
2. Import Git Repository
3. Seleccionar repo del frontend
4. Agregar variables de entorno
5. Configurar dominio: www.[tu-dominio].com

### 8.3 Configurar DNS
En tu proveedor de dominio:
- `api.[dominio]` → CNAME a Railway
- `www.[dominio]` → CNAME a Vercel
- `[dominio]` → Redirect a www.[dominio]

---

## FASE 9: VERIFICACIÓN FINAL

### Checklist de pruebas:
- [ ] Registro de usuario funciona
- [ ] Login funciona
- [ ] Email de bienvenida llega
- [ ] Chat responde correctamente
- [ ] RAG encuentra información de los documentos
- [ ] Análisis de imágenes funciona
- [ ] Tokens se descuentan correctamente
- [ ] Multiplicadores funcionan (1.5x profundo, 2x imagen)
- [ ] Checkout de Stripe funciona
- [ ] Webhook de Stripe actualiza el plan
- [ ] Historial de chat se guarda

---

## 📁 ESTRUCTURA DE ARCHIVOS CLAVE

```
backend/
├── main.py                 # API principal
├── config.py               # Configuración (MODIFICAR)
├── plans.py                # Planes de suscripción (MODIFICAR)
├── Dockerfile              # Docker config
├── requirements.txt        # Dependencias
├── data/                   # Documentos para RAG
├── lib/
│   ├── llm_service.py      # Prompts del sistema (MODIFICAR)
│   ├── vision_service.py   # Análisis de imágenes (MODIFICAR)
│   ├── rag_service.py      # Búsqueda RAG
│   ├── token_service.py    # Gestión de tokens
│   └── email.py            # Emails (MODIFICAR)
└── routers/
    ├── chat.py             # Endpoints de chat
    ├── billing.py          # Stripe/pagos
    └── users.py            # Usuarios

frontend/
├── app/
│   ├── page.tsx            # Página principal (MODIFICAR)
│   ├── layout.tsx          # Layout (MODIFICAR)
│   └── globals.css         # Estilos (MODIFICAR)
├── lib/
│   └── plans.ts            # Planes (MODIFICAR)
└── public/                 # Assets (REEMPLAZAR)
```

---

## 🔑 VARIABLES DE ENTORNO COMPLETAS

### Backend (Railway)
```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DEEPSEEK_API_KEY=
GOOGLE_API_KEY=
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_EXPLORER=
STRIPE_PRICE_TRADER=
STRIPE_PRICE_PRO=
STRIPE_PRICE_INSTITUCIONAL=
FRONTEND_URL=
BACKEND_URL=
RESEND_API_KEY=
EMAIL_FROM=
ADMIN_EMAIL=
PORT=8080
```

### Frontend (Vercel)
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_BACKEND_URL=
```

---

## ⏱️ TIEMPO ESTIMADO TOTAL: 4-6 horas

| Fase | Tiempo |
|------|--------|
| Preparación | 30 min |
| Clonar repos | 20 min |
| Supabase | 45 min |
| Stripe | 30 min |
| Backend | 1 hora |
| Frontend | 1 hora |
| Ingesta | Variable (depende de docs) |
| Deploy | 30 min |
| Verificación | 30 min |

---

## 🆘 TROUBLESHOOTING COMÚN

### Error: "No se encontraron chunks"
- Verificar que la ingesta se completó
- Verificar que `match_documents_384` existe en Supabase

### Error: "CORS"
- Agregar dominio del frontend a CORS en `main.py`

### Error: "Webhook signature"
- Verificar `STRIPE_WEBHOOK_SECRET`
- Usar el secret del endpoint específico, no el global

### Error: "Token inválido"
- Verificar `SUPABASE_ANON_KEY` en frontend
- Verificar que el usuario existe en `profiles`

---

**Última actualización**: Noviembre 2024
**Proyecto base**: Codex Trader

