-- ============================================================================
-- Script para crear índice vectorial en Supabase
-- Optimiza las búsquedas RAG y reduce reconexiones
-- ============================================================================

-- PASO 1: Verificar qué columnas tiene realmente la tabla vecs.knowledge
SELECT 
    column_name, 
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_schema = 'vecs' 
  AND table_name = 'knowledge'
ORDER BY ordinal_position;

-- PASO 2: Buscar columnas de tipo vector (pueden tener nombres diferentes)
SELECT 
    column_name,
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_schema = 'vecs' 
  AND table_name = 'knowledge'
  AND (data_type = 'USER-DEFINED' OR udt_name LIKE '%vector%');

-- PASO 3: Verificar si ya existe algún índice vectorial
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE schemaname = 'vecs' 
  AND tablename = 'knowledge';

-- PASO 4: Crear el índice vectorial (la columna se llama "vec")
-- IMPORTANTE: 
-- - Si falla por memoria: reduce el número de "lists" (25, 10)
-- - Si falla por timeout: usa menos "lists" O usa HNSW en lugar de IVFFlat

-- OPCIÓN A: IVFFlat con menos lists (más rápido de crear)
-- Prueba primero con lists = 10 (más rápido, menos memoria):
CREATE INDEX IF NOT EXISTS knowledge_vec_idx 
ON vecs.knowledge 
USING ivfflat (vec vector_cosine_ops) 
WITH (lists = 10);

-- OPCIÓN B: Si IVFFlat sigue dando timeout, usa HNSW (más rápido de crear)
-- HNSW es más rápido de crear pero usa más espacio:
-- CREATE INDEX IF NOT EXISTS knowledge_vec_idx_hnsw 
-- ON vecs.knowledge 
-- USING hnsw (vec vector_cosine_ops) 
-- WITH (m = 16, ef_construction = 64);

-- NOTA: HNSW es mejor para búsquedas pero IVFFlat es mejor para tablas grandes con pocas búsquedas

-- PASO 5: Verificar que el índice se creó correctamente
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE schemaname = 'vecs' 
  AND tablename = 'knowledge'
  AND indexdef LIKE '%ivfflat%';

