#!/bin/bash
# Script para crear índice vectorial usando psql directamente
# Esto evita timeouts del SQL Editor de Supabase

echo "============================================================"
echo "CREACION DE INDICE VECTORIAL CON psql"
echo "============================================================"
echo ""

# Cargar variables de entorno
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Obtener SUPABASE_DB_URL
DB_URL="${SUPABASE_DB_URL}"

if [ -z "$DB_URL" ]; then
    echo "[ERROR] SUPABASE_DB_URL no está configurada"
    echo "Configura SUPABASE_DB_URL en tu archivo .env"
    exit 1
fi

echo "[*] Conectando a la base de datos..."
echo ""

# Crear archivo SQL temporal con los comandos
SQL_FILE=$(mktemp)
cat > "$SQL_FILE" << 'EOF'
-- Configurar timeout ilimitado
SET statement_timeout = '0';

-- Crear índice HNSW CONCURRENTLY
CREATE INDEX CONCURRENTLY IF NOT EXISTS knowledge_vec_idx_hnsw_m32_ef64 
ON vecs.knowledge 
USING hnsw (vec vector_cosine_ops) 
WITH (m = 32, ef_construction = 64);

-- Verificar que el índice se creó
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE schemaname = 'vecs' 
  AND tablename = 'knowledge'
  AND indexname LIKE '%hnsw%'
ORDER BY indexname;
EOF

echo "[*] Ejecutando comandos SQL..."
echo ""

# Ejecutar con psql
psql "$DB_URL" -f "$SQL_FILE"

EXIT_CODE=$?

# Limpiar archivo temporal
rm -f "$SQL_FILE"

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "[OK] Proceso completado!"
    echo ""
    echo "[IMPORTANTE]"
    echo "   - El índice se está creando en segundo plano (CONCURRENTLY)"
    echo "   - Puede tardar varios minutos dependiendo del tamaño de la tabla"
    echo "   - Las búsquedas mejorarán gradualmente mientras se construye"
else
    echo ""
    echo "[ERROR] Hubo un error al crear el índice"
    exit 1
fi















