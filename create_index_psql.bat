@echo off
REM Script para crear índice vectorial usando psql directamente (Windows)
REM Esto evita timeouts del SQL Editor de Supabase

echo ============================================================
echo CREACION DE INDICE VECTORIAL CON psql
echo ============================================================
echo.

REM Cargar variables de entorno desde .env si existe
if exist .env (
    for /f "tokens=1,* delims==" %%a in (.env) do (
        set "%%a=%%b"
    )
)

REM Obtener SUPABASE_DB_URL
if "%SUPABASE_DB_URL%"=="" (
    echo [ERROR] SUPABASE_DB_URL no esta configurada
    echo Configura SUPABASE_DB_URL en tu archivo .env
    exit /b 1
)

echo [*] Conectando a la base de datos...
echo.

REM Crear archivo SQL temporal
set SQL_FILE=%TEMP%\create_index_%RANDOM%.sql

(
    echo -- Configurar timeout ilimitado
    echo SET statement_timeout = '0';
    echo.
    echo -- Crear indice HNSW CONCURRENTLY
    echo CREATE INDEX CONCURRENTLY IF NOT EXISTS knowledge_vec_idx_hnsw_m32_ef64 
    echo ON vecs.knowledge 
    echo USING hnsw ^(vec vector_cosine_ops^) 
    echo WITH ^(m = 32, ef_construction = 64^);
    echo.
    echo -- Verificar que el indice se creo
    echo SELECT 
    echo     indexname, 
    echo     indexdef 
    echo FROM pg_indexes 
    echo WHERE schemaname = 'vecs' 
    echo   AND tablename = 'knowledge'
    echo   AND indexname LIKE '%%hnsw%%'
    echo ORDER BY indexname;
) > "%SQL_FILE%"

echo [*] Ejecutando comandos SQL...
echo.

REM Ejecutar con psql
psql "%SUPABASE_DB_URL%" -f "%SQL_FILE%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Proceso completado!
    echo.
    echo [IMPORTANTE]
    echo    - El indice se esta creando en segundo plano (CONCURRENTLY^)
    echo    - Puede tardar varios minutos dependiendo del tamano de la tabla
    echo    - Las busquedas mejoraran gradualmente mientras se construye
) else (
    echo.
    echo [ERROR] Hubo un error al crear el indice
    exit /b 1
)

REM Limpiar archivo temporal
del "%SQL_FILE%" 2>nul












