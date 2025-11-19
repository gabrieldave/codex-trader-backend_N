-- ============================================================================
-- EJECUTAR ESTO EN SUPABASE SQL EDITOR
-- ============================================================================
-- Copia y pega todo este contenido en el SQL Editor de Supabase
-- ============================================================================

-- Crear función híbrida optimizada (prioriza búsqueda semántica)
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
LANGUAGE plpgsql
AS $$
DECLARE
    semantic_limit int;
    full_text_limit int;
BEGIN
    -- Limitar resultados para mejorar rendimiento
    semantic_limit := match_count * 2; -- Búsqueda semántica (principal)
    full_text_limit := match_count; -- Búsqueda de texto (complementaria, más pequeña)
    
    RETURN QUERY
    WITH semantic AS (
        -- Búsqueda semántica (principal, más rápida con índices)
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
        LIMIT semantic_limit
    ),
    full_text AS (
        -- Búsqueda de texto completo (complementaria, limitada)
        SELECT 
            bc.id,
            bc.doc_id,
            bc.content,
            bc.metadata,
            d.category,
            ts_rank_cd(to_tsvector('spanish', bc.content), websearch_to_tsquery('spanish', query_text)) as rank
        FROM book_chunks bc
        JOIN documents d ON bc.doc_id = d.doc_id
        WHERE 
            to_tsvector('spanish', bc.content) @@ websearch_to_tsquery('spanish', query_text)
            AND (category_filter IS NULL OR d.category = category_filter)
        ORDER BY rank DESC
        LIMIT full_text_limit
    ),
    combined AS (
        -- Combinar resultados: priorizar semántica, agregar texto completo si no está duplicado
        SELECT 
            s.id,
            s.doc_id,
            s.content,
            s.metadata,
            s.category,
            -- Score: semántica (principal) + texto completo (boost si existe)
            (s.similarity * semantic_weight + COALESCE(ft.rank, 0) * full_text_weight) as combined_score
        FROM semantic s
        LEFT JOIN full_text ft ON s.id = ft.id
        
        UNION ALL
        
        -- Agregar resultados de texto completo que no están en semántica
        SELECT 
            ft.id,
            ft.doc_id,
            ft.content,
            ft.metadata,
            ft.category,
            (COALESCE(ft.rank, 0) * full_text_weight) as combined_score
        FROM full_text ft
        WHERE NOT EXISTS (SELECT 1 FROM semantic s WHERE s.id = ft.id)
    ),
    ranked AS (
        SELECT DISTINCT ON (id)
            id,
            doc_id,
            content,
            metadata,
            category,
            combined_score
        FROM combined
        ORDER BY id, combined_score DESC
    )
    SELECT 
        id,
        doc_id,
        content,
        metadata,
        category,
        combined_score as similarity
    FROM ranked
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- CREAR ÍNDICES PARA MEJORAR RENDIMIENTO (EJECUTAR DESPUÉS DE LA FUNCIÓN)
-- ============================================================================

-- Índice para búsqueda semántica (vector)
CREATE INDEX IF NOT EXISTS idx_book_chunks_embedding ON book_chunks 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Índice para búsqueda de texto completo
CREATE INDEX IF NOT EXISTS idx_book_chunks_content_fts ON book_chunks 
    USING gin(to_tsvector('spanish', content));

-- Índice para mejorar JOINs con documents
CREATE INDEX IF NOT EXISTS idx_book_chunks_doc_id ON book_chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents (doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents (category);

-- ============================================================================
-- ✅ LISTO - La función y los índices están creados
-- ============================================================================

