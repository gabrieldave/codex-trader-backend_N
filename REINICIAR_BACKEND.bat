@echo off
echo ========================================
echo Reiniciando CODEX TRADER Backend
echo ========================================
echo.

cd /d "%~dp0"

echo Deteniendo procesos de Python existentes...
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Iniciando servidor FastAPI...
echo.
echo El backend se abrira en una nueva ventana.
echo Cierra esta ventana cuando termines.
echo.

start "CODEX TRADER Backend" cmd /k "cd /d %~dp0 && python main.py"

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo Backend reiniciado!
echo ========================================
echo.
echo Verifica la ventana del backend para confirmar que inicio correctamente.
echo.
pause
