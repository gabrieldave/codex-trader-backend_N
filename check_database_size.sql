-- ============================================================================
-- Script para verificar el tamaño de la base de datos y buscar datos a limpiar
-- ============================================================================

-- 1. Ver el tamaño total de la tabla vecs.knowledge (versión mejorada)
SELECT 
    pg_size_pretty(pg_total_relation_size(format('%I.%I','vecs','knowledge')::regclass)) AS total_size,
    pg_size_pretty(pg_relation_size(format('%I.%I','vecs','knowledge')::regclass)) AS table_size,
    pg_size_pretty(pg_indexes_size(format('%I.%I','vecs','knowledge')::regclass)) AS indexes_size;

-- 2. Contar cuántos registros hay
-- Opción A: Conteo exacto (más lento pero preciso)
SELECT COUNT(*) AS total_records FROM vecs.knowledge;

-- Opción B: Estimación rápida (más rápido para tablas grandes)
SELECT reltuples::bigint AS estimated_records 
FROM pg_class 
WHERE oid = 'vecs.knowledge'::regclass;

-- 3. Ver el tamaño de las tablas más grandes (versión mejorada con LATERAL JOIN)
SELECT 
    t.schemaname,
    t.tablename,
    pg_size_pretty(sz.total) AS size
FROM pg_tables t
CROSS JOIN LATERAL (
    SELECT pg_total_relation_size(format('%I.%I', t.schemaname, t.tablename)::regclass) AS total
) sz
WHERE t.schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY sz.total DESC
LIMIT 10;

-- 4. Ver archivos indexados para identificar posibles duplicados (filtra NULLs)
SELECT 
    metadata->>'file_name' AS file_name,
    COUNT(*) AS chunk_count
FROM vecs.knowledge
WHERE metadata ? 'file_name'  -- Solo filas que tienen file_name
GROUP BY metadata->>'file_name'
ORDER BY chunk_count DESC
LIMIT 20;

-- 5. Opcional: Crear índice para mejorar búsquedas por file_name
-- (Descomentar si necesitas buscar por nombre de archivo frecuentemente)
-- CREATE INDEX IF NOT EXISTS idx_knowledge_file_name 
-- ON vecs.knowledge ((metadata->>'file_name'));

