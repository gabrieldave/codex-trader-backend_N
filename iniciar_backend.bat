@echo off
echo ========================================
echo Iniciando CODEX TRADER Backend
echo ========================================
echo.

cd /d "%~dp0"

echo Verificando variables de entorno...
if not exist .env (
    echo ADVERTENCIA: No se encontro archivo .env
    echo Asegurate de tener configuradas las variables de entorno
    echo.
)

echo Iniciando servidor FastAPI...
echo.
python main.py

pause
