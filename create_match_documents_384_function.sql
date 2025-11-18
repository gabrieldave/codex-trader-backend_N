-- ============================================================================
-- CREAR FUNCIÓN RPC match_documents_384 Y ÍNDICES PARA book_chunks
-- ============================================================================
-- Este script crea la función RPC que usa el sistema RAG para buscar
-- en la tabla book_chunks con embeddings de 384 dimensiones (all-MiniLM-L6-v2)
-- ============================================================================

-- PASO 1: Verificar estructura de book_chunks
-- Ejecuta esto primero para ver qué columnas tiene:
SELECT 
    column_name, 
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_schema = 'public' 
  AND table_name = 'book_chunks'
ORDER BY ordinal_position;

-- PASO 2: Verificar si existe columna de tipo vector
-- Busca la columna que contiene los embeddings (puede llamarse 'embedding' o 'vec')
SELECT 
    column_name,
    data_type,
    udt_name
FROM information_schema.columns 
WHERE table_schema = 'public' 
  AND table_name = 'book_chunks'
  AND (data_type = 'USER-DEFINED' OR udt_name LIKE '%vector%');

-- PASO 3: Crear función RPC match_documents_384
-- IMPORTANTE: Ajusta el nombre de la columna vector según lo que encontraste en el PASO 2
-- Si la columna se llama 'embedding', usa 'embedding'
-- Si la columna se llama 'vec', usa 'vec'

CREATE OR REPLACE FUNCTION match_documents_384(
  query_embedding vector(384),
  match_count int DEFAULT 5,
  filter jsonb DEFAULT '{}'::jsonb
)
RETURNS TABLE (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    book_chunks.id,
    book_chunks.content,
    book_chunks.metadata,
    1 - (book_chunks.embedding <=> query_embedding) AS similarity
  FROM book_chunks
  WHERE (filter->>'doc_id' IS NULL OR book_chunks.metadata->>'doc_id' = filter->>'doc_id')
  ORDER BY book_chunks.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- NOTA: Si tu columna vector se llama 'vec' en lugar de 'embedding', 
-- reemplaza 'book_chunks.embedding' por 'book_chunks.vec' en la función anterior

-- PASO 4: Crear índice vectorial en book_chunks para optimizar búsquedas
-- IMPORTANTE: Ajusta el nombre de la columna según el PASO 2

-- OPCIÓN A: IVFFlat (más rápido de crear, mejor para tablas grandes)
CREATE INDEX IF NOT EXISTS book_chunks_embedding_idx_ivfflat 
ON book_chunks 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- OPCIÓN B: HNSW (mejor para búsquedas frecuentes, más espacio)
-- Descomenta esta línea si prefieres HNSW sobre IVFFlat:
-- CREATE INDEX IF NOT EXISTS book_chunks_embedding_idx_hnsw 
-- ON book_chunks 
-- USING hnsw (embedding vector_cosine_ops) 
-- WITH (m = 16, ef_construction = 64);

-- NOTA: Si tu columna vector se llama 'vec', reemplaza 'embedding' por 'vec' en los índices

-- PASO 5: Verificar que la función y el índice se crearon correctamente
SELECT 
    routine_name, 
    routine_type
FROM information_schema.routines 
WHERE routine_schema = 'public' 
  AND routine_name = 'match_documents_384';

SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE schemaname = 'public' 
  AND tablename = 'book_chunks'
  AND indexname LIKE '%embedding%' OR indexname LIKE '%vec%';

-- ============================================================================
-- NOTAS IMPORTANTES:
-- ============================================================================
-- 1. La función match_documents_384 busca en book_chunks usando distancia coseno
-- 2. Los embeddings son de 384 dimensiones (all-MiniLM-L6-v2)
-- 3. El índice vectorial acelera las búsquedas significativamente
-- 4. IVFFlat es mejor para tablas grandes (>100K registros)
-- 5. HNSW es mejor para búsquedas muy frecuentes
-- 6. Asegúrate de que la columna vector tenga exactamente 384 dimensiones
-- ============================================================================

