-- ============================================================================
-- ELIMINAR FUNCIÓN HÍBRIDA DE SUPABASE
-- ============================================================================
-- Ejecuta esto en Supabase SQL Editor para eliminar la función match_documents_hybrid
-- ============================================================================

DROP FUNCTION IF EXISTS match_documents_hybrid(
    text,
    vector(384),
    int,
    float,
    float,
    text
);

-- ============================================================================
-- ✅ LISTO - La función híbrida ha sido eliminada
-- ============================================================================


