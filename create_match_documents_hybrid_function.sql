-- ============================================================================
-- CREAR FUNCIÓN RPC match_documents_hybrid (Búsqueda Híbrida: Keyword + Vector)
-- ============================================================================
-- Esta función combina búsqueda de texto completo (full-text search) con
-- búsqueda semántica (vector similarity) para mejorar la precisión de los resultados.
-- ============================================================================

-- Habilitar extensión para búsqueda de texto completo si no existe
-- Nota: PostgreSQL tiene búsqueda de texto completo nativa, no necesitamos pgroonga
-- pero si prefieres usarlo, descomenta la siguiente línea:
-- CREATE EXTENSION IF NOT EXISTS pgroonga;

-- Crear función híbrida
CREATE OR REPLACE FUNCTION match_documents_hybrid(
    query_text text,
    query_embedding vector(384),
    match_count int,
    full_text_weight float DEFAULT 1.0,
    semantic_weight float DEFAULT 1.0,
    category_filter text DEFAULT NULL
)
RETURNS TABLE (
    id bigint,
    doc_id text,
    content text,
    metadata jsonb,
    category text,
    similarity float
)
LANGUAGE sql
AS $$
WITH full_text AS (
    SELECT 
        bc.id,
        bc.doc_id,
        bc.content,
        bc.metadata,
        d.category,
        ts_rank(to_tsvector('spanish', bc.content), websearch_to_tsquery('spanish', query_text)) as rank
    FROM book_chunks bc
    JOIN documents d ON bc.doc_id = d.doc_id
    WHERE 
        to_tsvector('spanish', bc.content) @@ websearch_to_tsquery('spanish', query_text)
        AND (category_filter IS NULL OR d.category = category_filter)
    ORDER BY rank DESC
    LIMIT match_count * 3
),
semantic AS (
    SELECT 
        bc.id,
        bc.doc_id,
        bc.content,
        bc.metadata,
        d.category,
        (1 - (bc.embedding <=> query_embedding)) as similarity
    FROM book_chunks bc
    JOIN documents d ON bc.doc_id = d.doc_id
    WHERE 
        (category_filter IS NULL OR d.category = category_filter)
    ORDER BY bc.embedding <=> query_embedding
    LIMIT match_count * 3
)
SELECT 
    COALESCE(ft.id, s.id) as id,
    COALESCE(ft.doc_id, s.doc_id) as doc_id,
    COALESCE(ft.content, s.content) as content,
    COALESCE(ft.metadata, s.metadata) as metadata,
    COALESCE(ft.category, s.category) as category,
    COALESCE(
        1.0 / (1.0 + exp(-((COALESCE(s.similarity, 0) * semantic_weight) + (COALESCE(ft.rank, 0) * full_text_weight)))),
        0.0
    ) as similarity
FROM full_text ft
FULL OUTER JOIN semantic s ON ft.id = s.id
ORDER BY similarity DESC
LIMIT match_count;
$$;

-- ============================================================================
-- NOTAS:
-- ============================================================================
-- 1. La función combina dos tipos de búsqueda:
--    - full_text: Búsqueda de texto completo usando PostgreSQL nativo (to_tsvector)
--    - semantic: Búsqueda semántica usando embeddings vectoriales
--
-- 2. Parámetros:
--    - query_text: Texto de la consulta del usuario (para búsqueda de texto completo)
--    - query_embedding: Vector embedding de 384 dimensiones (para búsqueda semántica)
--    - match_count: Número de resultados a retornar
--    - full_text_weight: Peso para la búsqueda de texto completo (default: 1.0)
--    - semantic_weight: Peso para la búsqueda semántica (default: 1.0)
--    - category_filter: Filtro opcional por categoría
--
-- 3. La función usa FULL OUTER JOIN para combinar resultados de ambas búsquedas
--    y calcula un score combinado usando una función sigmoide
--
-- 4. Para mejorar el rendimiento, considera crear índices:
--    CREATE INDEX IF NOT EXISTS idx_book_chunks_embedding ON book_chunks 
--        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
--    CREATE INDEX IF NOT EXISTS idx_book_chunks_content_fts ON book_chunks 
--        USING gin(to_tsvector('spanish', content));
-- ============================================================================

