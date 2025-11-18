@echo off
REM Inicia el frontend Next.js en una nueva ventana de terminal visible
echo ========================================
echo Iniciando Frontend (Next.js)
echo ========================================
echo.
start "Frontend - Next.js" cmd /k "cd /d %~dp0\..\frontend && npm run dev"
echo.
echo Frontend iniciado en nueva ventana
echo URL: http://localhost:3000 (o el puerto que Next.js asigne)
echo.
pause

