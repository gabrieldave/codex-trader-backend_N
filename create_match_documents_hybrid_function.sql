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
--    y calcula un score combinado simplificado (más rápido que sigmoide)
-- 4. Optimizaciones aplicadas:
--    - Reducción de resultados iniciales (match_count + 10 en lugar de match_count * 3)
--    - Uso de plpgsql para mejor control de límites
--    - Score combinado simplificado (suma ponderada en lugar de sigmoide)
--    - DISTINCT ON para evitar duplicados
--
-- 5. Crear índices para mejorar el rendimiento (EJECUTAR DESPUÉS DE CREAR LA FUNCIÓN)
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

