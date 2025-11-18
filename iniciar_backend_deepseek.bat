@echo off
REM Inicia el backend con DeepSeek en una nueva ventana de terminal visible
echo ========================================
echo Iniciando Backend con DeepSeek
echo ========================================
echo.
start "Backend - DeepSeek" cmd /k "cd /d %~dp0 && python main.py"
echo.
echo Backend iniciado en nueva ventana
echo URL: http://localhost:8000
echo.
pause

