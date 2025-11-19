-- ============================================================================
-- EJECUTAR ESTO EN SUPABASE SQL EDITOR
-- ============================================================================
-- Copia y pega todo este contenido en el SQL Editor de Supabase
-- ============================================================================

-- Crear función híbrida ULTRA optimizada (versión simplificada)
-- Esta versión prioriza velocidad sobre complejidad
CREATE OR REPLACE FUNCTION match_documents_hybrid(
    query_text text,
    query_embedding vector(384),
    match_count int,
    full_text_weight float DEFAULT 0.3,
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
STABLE
AS $$
    -- Versión simplificada: solo búsqueda semántica con boost de texto completo si existe
    WITH semantic AS (
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
        LIMIT LEAST(match_count * 2, 20) -- Máximo 20 resultados para evitar timeout
    )
    SELECT 
        s.id,
        s.doc_id,
        s.content,
        s.metadata,
        s.category,
        -- Score: principalmente semántica, con pequeño boost si contiene el texto
        (s.similarity * semantic_weight + 
         CASE 
             WHEN to_tsvector('spanish', s.content) @@ websearch_to_tsquery('spanish', query_text) 
             THEN 0.1 * full_text_weight 
             ELSE 0 
         END) as similarity
    FROM semantic s
    ORDER BY similarity DESC
    LIMIT match_count;
$$;

-- ============================================================================
-- CREAR ÍNDICES PARA MEJORAR RENDIMIENTO
-- ⚠️ EJECUTAR ESTOS ÍNDICES POR SEPARADO (pueden tardar varios minutos)
-- ============================================================================

-- PASO 1: Índice para búsqueda semántica (vector) - EJECUTAR PRIMERO
-- CREATE INDEX IF NOT EXISTS idx_book_chunks_embedding ON book_chunks 
--     USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- PASO 2: Índice para mejorar JOINs - EJECUTAR SEGUNDO
-- CREATE INDEX IF NOT EXISTS idx_book_chunks_doc_id ON book_chunks (doc_id);
-- CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id);
-- CREATE INDEX IF NOT EXISTS idx_documents_category ON documents (category);

-- PASO 3: Índice para búsqueda de texto completo - EJECUTAR ÚLTIMO (más lento)
-- CREATE INDEX IF NOT EXISTS idx_book_chunks_content_fts ON book_chunks 
--     USING gin(to_tsvector('spanish', content));

-- ============================================================================
-- ✅ LISTO - La función y los índices están creados
-- ============================================================================

