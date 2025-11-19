# 📚 Sistema RAG de Ingesta de Libros

## 1. Introducción General

### ¿Qué es este proyecto?

Este proyecto implementa un sistema completo de **RAG (Retrieval-Augmented Generation)** para procesar, indexar y consultar documentos (principalmente libros en formato PDF, EPUB, TXT, DOCX, MD) usando embeddings vectoriales y búsqueda semántica.

### ¿Qué problema resuelve?

El sistema resuelve el problema de **indexar grandes colecciones de libros/documentos** y permitir consultas semánticas sobre su contenido:

- **Ingesta masiva**: Procesa cientos o miles de archivos de forma eficiente y paralela
- **Búsqueda semántica**: Permite hacer preguntas en lenguaje natural sobre el contenido indexado
- **Anti-duplicados**: Evita indexar el mismo contenido dos veces
- **Control de límites**: Respeta los límites de la API de OpenAI (Tier 3) sin excederlos
- **Monitoreo en tiempo real**: Muestra progreso, velocidad y métricas durante la ingesta
- **Reporte detallado**: Genera un reporte final con estadísticas completas

### Tecnologías Principales

- **Python 3.x** - Lenguaje principal
- **LlamaIndex** - Framework para RAG y procesamiento de documentos
- **SentenceTransformer** - Embeddings locales con modelo `all-MiniLM-L6-v2` (384 dimensiones)
- **Supabase** - Base de datos PostgreSQL con extensión pgvector para almacenamiento vectorial
- **FastAPI** - API REST para consultas RAG
- **LiteLLM** - Abstracción para usar múltiples modelos de IA (OpenAI, Deepseek, Claude, Gemini, etc.)

---

## 2. Arquitectura General del Sistema

### Flujo End-to-End

El sistema funciona en dos fases principales:

#### **Fase 1: Ingesta de Documentos**

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE INGESTIÓN                         │
└─────────────────────────────────────────────────────────────────┘

1️⃣ LEER ARCHIVOS
   ↓
   SimpleDirectoryReader(input_files=[file_path])
   • Soporta: PDF, EPUB, TXT, DOCX, MD
   • Lee desde ./data/
   • Convierte automáticamente a texto

2️⃣ VERIFICAR DUPLICADOS
   ↓
   calculate_doc_id(file_path)  # Hash SHA256
   • Consulta tabla documents en Supabase
   • Si existe → SKIP o REINDEX (según configuración)
   • Si no existe → PROCESS

3️⃣ EXTRAER TEXTO
   ↓
   reader.load_data()
   • LlamaIndex extrae texto automáticamente
   • Crea objetos Document con metadata

4️⃣ DIVIDIR EN CHUNKS
   ↓
   SentenceSplitter(chunk_size=1024, chunk_overlap=200)
   • Divide en chunks de 1024 caracteres
   • Overlap de 200 caracteres entre chunks
   • Mantiene contexto entre chunks adyacentes

5️⃣ GENERAR EMBEDDINGS
   ↓
   SentenceTransformer('all-MiniLM-L6-v2')
   • Ejecución local en el servidor
   • Genera embeddings de 384 dimensiones
   • Sin costo por token (procesamiento local)

6️⃣ GUARDAR EN SUPABASE
   ↓
   SupabaseVectorStore + pgvector
   • Almacena vectores en PostgreSQL
   • Guarda metadata (file_name, chunk_id, doc_id, etc.)
   • Tabla: vecs.knowledge (configurable)
```

#### **Fase 2: Consulta RAG**

```
┌─────────────────────────────────────────────────────────────────┐
│                    PIPELINE DE CONSULTA                          │
└─────────────────────────────────────────────────────────────────┘

1️⃣ RECIBIR PREGUNTA
   ↓
   POST /chat { "query": "¿Qué dice el libro sobre X?" }

2️⃣ GENERAR EMBEDDING DE LA PREGUNTA
   ↓
   SentenceTransformer('all-MiniLM-L6-v2')
   • Ejecución local en el servidor
   • 384 dimensiones

3️⃣ BÚSQUEDA SEMÁNTICA
   ↓
   match_documents_384(query_embedding, match_count)
   • Función RPC en Supabase
   • Busca los chunks más similares usando distancia coseno
   • Tabla: book_chunks

4️⃣ CONSTRUIR CONTEXTO
   ↓
   Concatenar chunks recuperados
   • Crea contexto para el LLM

5️⃣ GENERAR RESPUESTA
   ↓
   LiteLLM (OpenAI/Deepseek/Claude/Gemini)
   • Envía contexto + pregunta al LLM
   • Genera respuesta basada en el contexto

6️⃣ DEVOLVER RESPUESTA
   ↓
   { "response": "...", "tokens_usados": 150, "tokens_restantes": 19850 }
```

### Diagrama de Alto Nivel

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Libros/PDFs │ ──→ │   Ingesta    │ ──→ │   Chunks     │
│   ./data/    │     │  (Paralelo)  │     │  (1024 chars)│
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ↓
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Consulta   │ ←── │   Supabase   │ ←── │  Embeddings  │
│   RAG API    │     │  (pgvector)  │     │  (384 dims)  │
│              │     │              │     │  (Local)     │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## 3. Detalle de la Ingesta de Documentos

### 3.1. Lectura de Archivos

El sistema usa **LlamaIndex SimpleDirectoryReader** para leer archivos:

```python
reader = SimpleDirectoryReader(input_files=[file_path])
documents = reader.load_data()
```

**Formatos soportados**:
- PDF (`.pdf`)
- EPUB (`.epub`)
- Texto plano (`.txt`)
- Word (`.docx`)
- Markdown (`.md`)

**Ubicación**: Los archivos se leen desde `./data/` (configurable en `config.py`)

### 3.2. Extracción de Texto

LlamaIndex extrae el texto automáticamente según el formato:
- **PDF**: Extrae texto de todas las páginas
- **EPUB**: Extrae texto de todos los capítulos
- **TXT/MD**: Lee el contenido directamente
- **DOCX**: Extrae texto del documento Word

Cada archivo se convierte en uno o más objetos `Document` de LlamaIndex.

### 3.3. Configuración de Chunks

El sistema usa **chunking fijo** (no configurable sin solicitud explícita):

- **Chunk size**: **1024 caracteres** (no tokens)
- **Chunk overlap**: **200 caracteres** (~20% de overlap)
- **Splitter**: `SentenceSplitter` de LlamaIndex

**¿Por qué 1024 caracteres?**
- Equivale a aproximadamente **256 tokens** (1 token ≈ 4 caracteres)
- Balance entre contexto y precisión
- Compatible con el modelo de embeddings

**¿Por qué 200 caracteres de overlap?**
- Mantiene contexto entre chunks adyacentes
- Evita cortar frases a la mitad
- Mejora la recuperación de información

**Código**:
```python
text_splitter = SentenceSplitter(
    chunk_size=1024,      # caracteres
    chunk_overlap=200     # caracteres
)
```

### 3.4. Modelo de Embeddings

**Modelo**: `all-MiniLM-L6-v2` de SentenceTransformer (ejecución local)

**Características**:
- **Dimensiones**: 384
- **Costo**: Sin costo (procesamiento local en el servidor)
- **Calidad**: Excelente para búsqueda semántica
- **Velocidad**: Muy rápido (sin latencia de red)
- **Ejecución**: Local en el servidor (no requiere API externa)

**¿Por qué este modelo?**
- Sin costo por token (procesamiento local)
- Excelente calidad para búsqueda semántica
- Compatible con pgvector en Supabase
- No depende de límites de API externa
- Mayor control y privacidad

**Código**:
```python
from sentence_transformers import SentenceTransformer

local_embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")
# O sin GPU:
local_embedder = SentenceTransformer("all-MiniLM-L6-v2")
```

### 3.5. Generación de Embeddings

**Procesamiento**: Local en el servidor (sin API externa)

**Características**:
- **Sin límites de API**: No hay límites de RPM/TPM para embeddings
- **Procesamiento en batch**: Los chunks se procesan en lotes para eficiencia
- **Sin costo**: No hay costo por token o request
- **Velocidad**: Depende del hardware del servidor (CPU/GPU)

**Ventajas**:
- No requiere API key de OpenAI para embeddings
- Sin preocupaciones por rate limits
- Mayor privacidad (datos no salen del servidor)
- Control total sobre el procesamiento

**Código**:
```python
from sentence_transformers import SentenceTransformer

# Inicializar embedder local
local_embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")

# Generar embeddings
embeddings = local_embedder.encode(chunks, show_progress_bar=False)
```

### 3.6. Workers y Procesamiento Paralelo

**Número de workers por defecto**: **15**

**Configuración**:
- Configurable mediante variable de entorno: `MAX_WORKERS=15`
- Usa `ThreadPoolExecutor` para concurrencia
- Cada worker procesa un archivo a la vez

**¿Por qué 15 workers?**
- Balance entre velocidad y uso de recursos del servidor
- Optimizado para procesamiento local de embeddings
- No hay límites de API que respetar (procesamiento local)

**Código**:
```python
MAX_WORKERS = 15  # configurable
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
```

---

## 4. Rendimiento y Procesamiento Local

### 4.1. Procesamiento Local de Embeddings

El sistema usa **embeddings locales** con SentenceTransformer, lo que significa:

- **Sin límites de API**: No hay límites de RPM/TPM para embeddings
- **Sin costo por token**: El procesamiento es completamente local
- **Mayor velocidad**: Sin latencia de red para generar embeddings
- **Mayor privacidad**: Los datos no salen del servidor

### 4.2. Rendimiento

**Factores que afectan el rendimiento**:
- **Hardware del servidor**: CPU/GPU disponible
- **Número de workers**: Paralelización del procesamiento
- **Tamaño de los chunks**: Más chunks = más embeddings a generar
- **Carga del servidor**: Otros procesos ejecutándose

**Optimizaciones**:
- Uso de GPU cuando está disponible (`device="cuda"`)
- Procesamiento en batch para eficiencia
- Paralelización con múltiples workers

### 4.3. Distribución del Trabajo

El sistema distribuye el trabajo de la siguiente manera:

1. **Múltiples workers** procesan archivos en paralelo
2. **Cada worker** procesa un archivo completo
3. **Cada archivo** se divide en chunks
4. **Cada batch** de chunks se procesa localmente con SentenceTransformer
5. **Los embeddings** se guardan directamente en Supabase

**Ejemplo**:
- 15 workers procesando en paralelo
- Cada worker procesa archivos según capacidad del servidor
- Embeddings generados localmente sin límites de API
- Sin preocupaciones por rate limits o costos de API

---

## 5. Lógica Anti-Duplicados

### 5.1. Detección de Duplicados a Nivel de Documento

El sistema usa **hash SHA256 del archivo** para detectar duplicados:

**Cálculo de `doc_id`**:
```python
doc_id = calculate_doc_id(file_path)  # SHA256 de los bytes del archivo
```

**Ventajas**:
- Detecta duplicados incluso si el archivo tiene diferente nombre
- Detecta contenido idéntico en archivos diferentes
- Determinístico: siempre genera el mismo hash para el mismo archivo

**Alternativa disponible**:
```python
doc_id = calculate_doc_id(file_path, use_content_hash=True, content=texto)
```
- Usa hash del contenido normalizado (útil para detectar contenido duplicado con formato diferente)

### 5.2. Tabla `documents` en Supabase

**Estructura**:
```sql
CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT,
    title TEXT,
    hash_method TEXT DEFAULT 'sha256',
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
)
```

**Índices**:
- `idx_documents_filename` en `filename`
- `idx_documents_created_at` en `created_at`

**Propósito**:
- Tracking de documentos indexados
- Verificación rápida de duplicados
- Auditoría de ingesta

### 5.3. Decisión de Procesamiento

Antes de procesar un archivo, el sistema toma una decisión:

```python
action, existing_doc = decide_document_action(doc_id, force_reindex=FORCE_REINDEX)

if action == "skip":
    # Duplicado detectado, saltar
    monitor.on_file_duplicated(file_name, doc_id)
elif action == "reindex":
    # Eliminar chunks anteriores y reindexar
    delete_document_chunks(doc_id, collection_name)
    # Procesar archivo normalmente
elif action == "process":
    # Nuevo documento, procesar normalmente
```

**Configuración**:
- **Variable de entorno**: `FORCE_REINDEX=false` (por defecto)
- Si `FORCE_REINDEX=true`: Fuerza reindexación incluso si el documento existe

### 5.4. Detección de Duplicados a Nivel de Chunk

**Cálculo de `chunk_id`**:
```python
chunk_id = calculate_chunk_id(doc_id, chunk_index, chunk_content)
# Hash de: doc_id + ":" + chunk_index + ":" + contenido_normalizado
```

**Verificación**:
Antes de procesar cada batch, se verifica si el chunk ya existe:

```python
if check_chunk_exists(chunk_id, collection_name):
    # Chunk duplicado, saltar
    continue
```

**Ventajas**:
- Evita duplicar chunks individuales
- Útil cuando se reindexa un documento parcialmente
- Determínistico: siempre genera el mismo `chunk_id` para el mismo contenido

### 5.5. Flujo Completo Anti-Duplicados

```
1. Calcular doc_id (hash del archivo)
   ↓
2. Verificar en tabla documents
   ↓
3a. Si existe y FORCE_REINDEX=False → SKIP (duplicado)
3b. Si existe y FORCE_REINDEX=True → REINDEX (eliminar chunks y procesar)
3c. Si no existe → PROCESS (nuevo)
   ↓
4. Procesar archivo (si no es skip)
   ↓
5. Para cada chunk:
   - Calcular chunk_id determinístico
   - Verificar si chunk existe
   - Si existe → saltar chunk
   - Si no existe → procesar
   ↓
6. Registrar documento en tabla documents
```

---

## 6. Estructura de la Base de Datos en Supabase

### 6.1. Tabla `documents`

**Propósito**: Tracking de documentos indexados

**Columnas**:
- `doc_id` (TEXT, PRIMARY KEY): Hash SHA256 del archivo
- `filename` (TEXT, NOT NULL): Nombre del archivo
- `file_path` (TEXT): Ruta completa del archivo
- `title` (TEXT): Título del documento (opcional)
- `hash_method` (TEXT, DEFAULT 'sha256'): Método de hash usado
- `total_chunks` (INTEGER, DEFAULT 0): Número total de chunks
- `created_at` (TIMESTAMP, DEFAULT NOW()): Fecha de creación
- `updated_at` (TIMESTAMP, DEFAULT NOW()): Fecha de última actualización

**Índices**:
- `idx_documents_filename`: Búsqueda rápida por nombre de archivo
- `idx_documents_created_at`: Ordenamiento por fecha

### 6.2. Tabla `book_chunks` (Almacenamiento de Vectores)

**Propósito**: Almacenamiento de embeddings y chunks

**Estructura** (pgvector):
- `id` (UUID, PRIMARY KEY): ID único del chunk
- `embedding` (vector(384)): Embedding vectorial (384 dimensiones)
- `content` (TEXT): Contenido del chunk
- `metadata` (JSONB): Metadatos del chunk

**Función RPC de búsqueda**: `match_documents_384`
- Recibe: `query_embedding` (vector de 384 dimensiones) y `match_count`
- Retorna: Los chunks más similares usando distancia coseno
- Filtros opcionales: `category_filter` para filtrar por categoría

**Metadatos guardados**:
```json
{
  "file_name": "libro.pdf",
  "chunk_id": "abc123...",
  "doc_id": "def456...",
  "chunk_index": 0,
  "total_chunks": 100,
  "char_range": "0-1024",
  "book_title": "Título del Libro"
}
```

**Relaciones**:
- `metadata->>'doc_id'` → `documents.doc_id` (relación lógica)

**Nota**: El sistema usa la función RPC `match_documents_384` para búsqueda semántica en lugar de índices de LlamaIndex. Esta función está optimizada para embeddings de 384 dimensiones.

### 6.3. Tabla `profiles` (Usuarios)

**Propósito**: Gestión de usuarios y tokens

**Columnas** (relevantes):
- `id` (UUID, PRIMARY KEY): ID del usuario (de Supabase Auth)
- `tokens_restantes` (INTEGER): Tokens disponibles para el usuario
- `email` (TEXT): Email del usuario

### 6.4. Tabla `conversations` (Historial)

**Propósito**: Historial de conversaciones

**Columnas**:
- `id` (UUID, PRIMARY KEY): ID único de la conversación
- `user_id` (UUID, FOREIGN KEY): ID del usuario
- `message_role` (TEXT): 'user' o 'assistant'
- `message_content` (TEXT): Contenido del mensaje
- `tokens_used` (INTEGER): Tokens usados en esta respuesta
- `created_at` (TIMESTAMP, DEFAULT NOW()): Fecha de creación

### 6.5. Esquema Completo

```
documents (doc_id, filename, file_path, title, total_chunks, ...)
    ↓
book_chunks (id, embedding[384], content, metadata)
    └─ metadata->>'doc_id' referencia documents.doc_id
    └─ Búsqueda mediante match_documents_384 RPC

profiles (id, tokens_restantes, email, ...)
    ↓
conversations (id, user_id, message_role, message_content, ...)
    └─ user_id referencia profiles.id
```

---

## 7. Monitor de Ingesta y Reporte Final

### 7.1. Monitor en Tiempo Real

El sistema incluye un **monitor en tiempo real** que muestra:

**Métricas principales**:
- **Progreso**: Archivos procesados / total
- **Velocidad**: Archivos/minuto, chunks/minuto
- **ETA**: Tiempo estimado restante
- **RPM/TPM**: Requests y tokens por minuto (estimados)
- **Errores**: Contador de errores por tipo

**Actualizaciones**:
- Cada 5 segundos (configurable)
- Visualización con `rich` si está disponible
- Salida simple si `rich` no está disponible

**Thread-safe**:
- Usa locks para acceso concurrente
- Seguro para múltiples workers

### 7.2. Métricas Registradas

**Contadores globales**:
- `total_files`: Total de archivos a procesar
- `files_processed`: Archivos procesados exitosamente
- `files_failed`: Archivos con error total
- `files_suspicious`: Archivos con < 5 chunks
- `files_duplicated`: Archivos duplicados saltados
- `files_reindexed`: Archivos reindexados
- `total_chunks`: Chunks generados
- `rate_limit_retries`: Reintentos por error 429
- `network_errors`: Errores de red
- `other_errors`: Otros errores

**Métricas de velocidad**:
- `files_per_minute`: Archivos procesados por minuto
- `chunks_per_minute`: Chunks generados por minuto
- `estimated_rpm`: RPM estimado
- `estimated_tpm`: TPM estimado

**Calidad de datos**:
- `min_chunks_per_file`: Mínimo de chunks por archivo
- `max_chunks_per_file`: Máximo de chunks por archivo
- `avg_chunks_per_file`: Promedio de chunks por archivo
- `suspicious_files`: Lista de archivos sospechosos

### 7.3. Hooks del Monitor

El monitor proporciona hooks para registrar eventos:

```python
monitor.on_file_started(file_name, file_path)
monitor.on_file_completed(file_name, chunks_generated, is_suspicious=False)
monitor.on_file_error(file_name, error_message, error_type="other")
monitor.on_file_duplicated(file_name, doc_id)
monitor.on_file_reindexed(file_name, doc_id, deleted_chunks)
monitor.on_chunk_batch_processed(chunks_count, estimated_tokens)
```

### 7.4. Reporte Final

Al finalizar la ingesta, se genera un **reporte en formato Markdown** con:

**Información de ejecución**:
- Fecha y hora de inicio
- Fecha y hora de finalización
- Tiempo total de ejecución

**Resumen general**:
- Archivos totales
- Archivos procesados correctamente
- Archivos con errores
- Archivos sospechosos (< 5 chunks)
- Archivos duplicados saltados
- Archivos reindexados
- Chunks totales generados
- Promedio, mínimo y máximo de chunks por archivo

**Advertencias y problemas**:
- Lista de archivos duplicados saltados
- Lista de archivos reindexados
- Lista de archivos sospechosos
- Lista de archivos con error total

**Métricas de rendimiento**:
- Velocidad promedio (archivos/minuto, chunks/minuto)
- RPM estimado promedio
- TPM estimado promedio

**Distribución de chunks**:
- Tabla con distribución por rangos (0-5, 5-20, 20-50, etc.)

**Resumen de errores**:
- Reintentos por rate limit (429)
- Errores de red
- Otros errores

**Ubicación del reporte**:
- Por defecto: `ingestion_report_YYYYMMDD_HHMMSS.md`
- Configurable mediante variable de entorno: `REPORT_FILE_PATH`

---

## 8. Metadatos y Filtros de Búsqueda

### 8.1. Metadatos Guardados

Cada chunk guarda los siguientes metadatos en Supabase:

```json
{
  "file_name": "libro.pdf",
  "chunk_id": "abc123...",
  "doc_id": "def456...",
  "chunk_index": 0,
  "total_chunks": 100,
  "char_range": "0-1024",
  "book_title": "Título del Libro"
}
```

**Campos**:
- `file_name`: Nombre del archivo
- `chunk_id`: ID único del chunk (hash determinístico)
- `doc_id`: ID del documento (hash del archivo)
- `chunk_index`: Índice del chunk en el documento (0-based)
- `total_chunks`: Número total de chunks del documento
- `char_range`: Rango de caracteres del chunk (start-end)
- `book_title`: Título del libro/documento (opcional)

### 8.2. Filtros de Búsqueda (Plan Futuro)

**Estado actual**: Los filtros por idioma, categoría, autor, año **no están implementados** en el código actual. Esto es una **mejora planificada para el futuro**.

**Metadatos que se podrían agregar**:
- `language`: Idioma del documento (es, en, fr, etc.)
- `category`: Categoría/tema (trading, finanzas, tecnología, etc.)
- `author`: Autor del documento
- `year`: Año de publicación
- `publisher`: Editorial

**Funcionalidad planificada**:
```python
def search_with_filters(
    query: str,
    language: Optional[str] = None,
    category: Optional[str] = None,
    author: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None
):
    # Filtrar chunks por metadatos antes de la búsqueda
    # Usar metadata->>'language', metadata->>'category', etc.
    pass
```

**Implementación sugerida**:
1. Extraer metadatos del documento (título, autor, año, etc.)
2. Guardar metadatos en la tabla `documents`
3. Agregar metadatos a cada chunk
4. Modificar el retriever para filtrar por metadatos
5. Actualizar la API para aceptar filtros

---

## 9. Guía Rápida para Ejecutar el Sistema

### 9.1. Configurar Variables de Entorno

Crear archivo `.env` en la raíz del proyecto:

```env
# Supabase
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_SERVICE_KEY=tu-service-key
SUPABASE_DB_URL=postgresql://postgres.tu-proyecto:password@aws-0-us-west-1.pooler.supabase.com:5432/postgres
SUPABASE_DB_PASSWORD=tu-password

# OpenAI
OPENAI_API_KEY=tu-openai-api-key

# Opcional: Otros modelos de IA
DEEPSEEK_API_KEY=tu-deepseek-api-key
ANTHROPIC_API_KEY=tu-anthropic-api-key
GOOGLE_API_KEY=tu-google-api-key
COHERE_API_KEY=tu-cohere-api-key

# Opcional: URLs del frontend y backend
FRONTEND_URL=https://www.codextrader.tech
BACKEND_URL=https://api.codextrader.tech

# Opcional: Configuración de ingesta
MAX_WORKERS=15
EMBEDDING_BATCH_SIZE=30
FORCE_REINDEX=false
LOG_LEVEL=INFO
```

### 9.2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

**Dependencias principales**:
- `fastapi`: API REST
- `uvicorn`: Servidor ASGI
- `supabase`: Cliente de Supabase
- `litellm`: Abstracción para modelos de IA
- `llama-index`: Framework RAG
- `sentence-transformers`: Embeddings locales (all-MiniLM-L6-v2)
- `python-dotenv`: Variables de entorno
- `pypdf`: Lectura de PDFs
- `python-docx`: Lectura de documentos Word
- `ebooklib`: Lectura de EPUBs

### 9.3. Configurar Base de Datos

**Crear tablas en Supabase**:

1. **Tabla `documents`** (se crea automáticamente al ejecutar `ingest_optimized_rag.py`)
2. **Colección de vectores** (se crea automáticamente al ejecutar la ingesta)
3. **Tabla `profiles`** (para usuarios y tokens)
4. **Tabla `conversations`** (para historial de conversaciones)

**Scripts SQL** (si necesitas crearlos manualmente):
- Ver `create_profiles_table.sql`
- Ver `create_conversations_table.sql`
- Ver `create_match_documents_384_function.sql` (función RPC para búsqueda)

### 9.4. Preparar Archivos

Colocar archivos en la carpeta `./data/`:

```bash
mkdir data
# Copiar archivos PDF, EPUB, TXT, DOCX, MD a ./data/
```

### 9.5. Ejecutar Ingesta

**Opción 1: Ingesta mejorada (simple)**:
```bash
python ingest_improved.py
```

**Opción 2: Ingesta optimizada (con monitor y anti-duplicados)**:
```bash
python ingest_optimized_rag.py
```

**Opción 3: Forzar reindexación**:
```bash
FORCE_REINDEX=true python ingest_optimized_rag.py
```

### 9.6. Ver Progreso

El monitor muestra el progreso en tiempo real:
- Progreso: Archivos procesados / total
- Velocidad: Archivos/minuto, chunks/minuto
- ETA: Tiempo estimado restante
- RPM/TPM: Requests y tokens por minuto

### 9.7. Revisar Reporte Final

Al finalizar, se genera un reporte en `ingestion_report_YYYYMMDD_HHMMSS.md` con:
- Resumen general
- Archivos procesados
- Archivos con errores
- Archivos sospechosos
- Métricas de rendimiento

### 9.8. Iniciar API de Consulta

```bash
python main.py
```

La API estará disponible en `http://localhost:8000`

**Endpoints**:
- `GET /`: Información de la API
- `GET /health`: Salud de la API
- `POST /chat`: Consulta RAG (requiere autenticación)
- `GET /tokens`: Tokens restantes del usuario
- `POST /tokens/reload`: Recargar tokens
- `GET /conversations`: Historial de conversaciones

**Documentación**: `http://localhost:8000/docs`

### 9.9. Comandos Típicos

```bash
# Verificar archivos nuevos
python check_new_files.py

# Verificar estado de la ingesta
python check_status.py

# Verificar datos en Supabase
python view_data.py

# Verificar duplicados
python check_duplicates.py

# Verificar límites de OpenAI
python verificar_limites_openai.py
```

---

## 10. Glosario de Conceptos Básicos

### RAG (Retrieval-Augmented Generation)

**Definición**: Técnica que combina búsqueda de información (retrieval) con generación de texto (generation) para crear respuestas basadas en un corpus de documentos.

**Cómo funciona**:
1. El usuario hace una pregunta
2. El sistema busca los documentos más relevantes
3. El sistema usa esos documentos como contexto
4. El LLM genera una respuesta basada en el contexto

**Ventajas**:
- Respuestas más precisas y contextualizadas
- Puede citar fuentes específicas
- Reduce alucinaciones del LLM

### Documento vs. Chunk

**Documento**: Archivo completo (ej: un PDF de 500 páginas)

**Chunk**: Fragmento del documento (ej: 1024 caracteres del PDF)

**¿Por qué dividir en chunks?**
- Los modelos de embeddings tienen límites de tamaño
- Permite búsqueda más precisa
- Mejora la recuperación de información específica

### Embedding

**Definición**: Representación vectorial de un texto que captura su significado semántico.

**Características**:
- Es un vector de números (ej: 384 dimensiones con all-MiniLM-L6-v2)
- Textos similares tienen embeddings similares
- Se usa para búsqueda semántica
- En este sistema: Generado localmente con SentenceTransformer

**Ejemplo**:
- "gato" y "felino" tienen embeddings similares
- "gato" y "perro" tienen embeddings más similares que "gato" y "coche"

### Vector Store

**Definición**: Base de datos especializada en almacenar y buscar vectores (embeddings).

**Características**:
- Almacena embeddings y metadatos
- Permite búsqueda por similitud (distancia coseno)
- Optimizado para búsqueda semántica

**En este proyecto**: Supabase con pgvector (PostgreSQL)
- Tabla: `book_chunks`
- Función de búsqueda: `match_documents_384`
- Dimensiones: 384 (all-MiniLM-L6-v2)

### doc_id

**Definición**: Identificador único de un documento basado en hash SHA256 del archivo.

**Características**:
- Determinístico: siempre genera el mismo hash para el mismo archivo
- Único: archivos diferentes tienen hashes diferentes
- Usado para detectar duplicados

### chunk_id

**Definición**: Identificador único de un chunk basado en hash del contenido.

**Características**:
- Determinístico: siempre genera el mismo hash para el mismo contenido
- Único: chunks diferentes tienen hashes diferentes
- Usado para evitar duplicar chunks

### match_documents_384

**Definición**: Función RPC en Supabase que realiza búsqueda semántica usando embeddings de 384 dimensiones.

**Parámetros**:
- `query_embedding`: Vector de 384 dimensiones de la consulta
- `match_count`: Número de chunks a retornar (por defecto: 5)
- `category_filter` (opcional): Filtrar por categoría

**Retorna**: Lista de chunks ordenados por similitud (distancia coseno)

**Ventajas**:
- Optimizado para embeddings de 384 dimensiones
- Búsqueda eficiente usando pgvector
- Soporte para filtros por categoría

---

## 11. Ideas de Mejora Futura

### 11.1. Filtros de Búsqueda Avanzados

**Estado**: Plan futuro

**Mejoras**:
- Filtros por idioma (es, en, fr, etc.)
- Filtros por categoría/tema (trading, finanzas, tecnología, etc.)
- Filtros por autor
- Filtros por rango de años
- Filtros combinados (múltiples criterios)

### 11.2. Extracción de Metadatos Automática

**Estado**: Plan futuro

**Mejoras**:
- Extraer título, autor, año, editorial automáticamente del PDF
- Clasificación automática por categoría/tema
- Detección automática de idioma
- Extracción de resumen/abstract

### 11.3. Rerankers

**Estado**: Plan futuro

**Mejoras**:
- Usar rerankers para mejorar la precisión de la búsqueda
- Reordenar resultados por relevancia
- Mejorar la calidad de las respuestas

### 11.4. Evaluación de Calidad

**Estado**: Plan futuro

**Mejoras**:
- Evaluar la calidad de las respuestas con preguntas de test
- Métricas de precisión, recall, F1
- Comparar diferentes configuraciones

### 11.5. UI para Explorar la Biblioteca

**Estado**: Plan futuro

**Mejoras**:
- Interfaz web para explorar documentos indexados
- Búsqueda visual
- Visualización de chunks
- Estadísticas de la biblioteca

### 11.6. Mejoras de Rendimiento

**Estado**: Plan futuro

**Mejoras**:
- Cache de embeddings
- Procesamiento incremental (solo archivos nuevos)
- Optimización de queries en pgvector
- Compresión de embeddings

### 11.7. Mejoras de Seguridad

**Estado**: Plan futuro

**Mejoras**:
- Encriptación de documentos sensibles
- Control de acceso por usuario
- Auditoría de consultas
- Logs de seguridad

---

## 12. Archivos Principales del Proyecto

### 12.1. Ingesta

- **`ingest_improved.py`**: Ingesta simple y directa
- **`ingest_optimized_rag.py`**: Ingesta optimizada con monitor y anti-duplicados
- **`config_ingesta.py`**: Configuración centralizada de ingesta
- **`anti_duplicates.py`**: Sistema anti-duplicados
- **`ingestion_monitor.py`**: Monitor de ingesta en tiempo real

### 12.2. API y Consulta

- **`main.py`**: API FastAPI para consultas RAG
- **`config.py`**: Configuración general del proyecto

### 12.3. Utilidades

- **`check_new_files.py`**: Verificar archivos nuevos
- **`check_status.py`**: Verificar estado de la ingesta
- **`view_data.py`**: Ver datos en Supabase
- **`check_duplicates.py`**: Verificar duplicados
- **`verificar_limites_openai.py`**: Verificar límites de OpenAI

### 12.4. Documentación

- **`README.md`**: Este archivo
- **`PIPELINE_TECNICO.md`**: Documentación técnica del pipeline
- **`RESUMEN_ANTI_DUPLICADOS.md`**: Resumen del sistema anti-duplicados
- **`RESUMEN_MONITOR_REPORTE.md`**: Resumen del monitor y reporte

---

## 13. Conclusión

Este sistema RAG de ingesta de libros es una solución completa y robusta para indexar y consultar grandes colecciones de documentos. Incluye:

- ✅ **Ingesta masiva y paralela**
- ✅ **Embeddings locales sin costo** (SentenceTransformer)
- ✅ **Sistema anti-duplicados robusto**
- ✅ **Monitor en tiempo real**
- ✅ **Reporte detallado**
- ✅ **API REST para consultas**
- ✅ **Soporte para múltiples modelos de IA**
- ✅ **Búsqueda semántica optimizada** (match_documents_384)

**Próximos pasos**:
1. Implementar filtros de búsqueda avanzados
2. Mejorar extracción de metadatos
3. Agregar rerankers
4. Crear UI para explorar la biblioteca

---

## 14. Contacto y Soporte

Para preguntas o problemas, consulta la documentación técnica en los archivos `.md` del proyecto o revisa el código fuente directamente.

**Archivos de referencia**:
- `PIPELINE_TECNICO.md`: Pipeline técnico completo
- `RESUMEN_ANTI_DUPLICADOS.md`: Sistema anti-duplicados
- `RESUMEN_MONITOR_REPORTE.md`: Monitor y reporte
- `GUIA_MONITOR_REPORTE.md`: Guía de uso del monitor

---

## 15. Cambios recientes

### 2025-11-19: Migración a Embeddings Locales

- **Migración completa a SentenceTransformer**: El sistema ahora usa `all-MiniLM-L6-v2` (384 dimensiones) en lugar de OpenAI embeddings
- **Sin costo por embeddings**: El procesamiento es completamente local, sin límites de API
- **Función RPC optimizada**: Uso de `match_documents_384` para búsqueda semántica en Supabase
- **Tabla actualizada**: Los embeddings se almacenan en `book_chunks` con 384 dimensiones

### 2025-11-16: Mejoras de Rendimiento

- Escalado de Supabase al plan XL (4 cores, 16 GB RAM) para mayor concurrencia.
- Instalación de `tenacity` en `venv_ingesta` para reintentos automáticos.
- Reemplazo completo de `ingest_masiva_local.py` por versión "anti-fracaso":
  - Reintentos robustos con `RemoteProtocolError`, `ConnectError`, `httpx.ReadError` y `httpcore.ReadError`.
  - `upsert(..., on_conflict="doc_id")` en tabla `documents` para evitar `23505 duplicate key`.
  - Limpieza de texto eliminando `\u0000` para evitar error `22P05` en Postgres.
  - Parámetros de alto rendimiento para XL: `MAX_WORKERS_LECTURA=20`, `DB_INSERT_BATCH_SIZE=250`, `EMBEDDING_BATCH_SIZE=256`, `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=200`.
  - Corrección de import: `langchain_text_splitters.RecursiveCharacterTextSplitter`.
- Ejecución reciente completada en ~23.42 minutos, con reintentos aplicados y progreso continuo ante fallos de red puntuales.

---

**Última actualización**: 2025-11-19
