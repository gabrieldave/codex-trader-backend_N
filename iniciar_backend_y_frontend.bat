@echo off
REM Inicia backend y frontend en ventanas separadas
echo ========================================
echo Iniciando Backend y Frontend
echo ========================================
echo.

echo [1/2] Iniciando Backend con DeepSeek...
start "Backend - DeepSeek" cmd /k "cd /d %~dp0 && python main.py"
timeout /t 3 /nobreak >nul

echo [2/2] Iniciando Frontend (Next.js)...
start "Frontend - Next.js" cmd /k "cd /d %~dp0\..\frontend && npm run dev"
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo ✅ Backend y Frontend iniciados
echo ========================================
echo.
echo 📡 Backend: http://localhost:8000
echo 🌐 Frontend: http://localhost:3000 (o el puerto que Next.js asigne)
echo.
echo 💡 Verifica las ventanas de terminal para ver los logs
echo.
pause

