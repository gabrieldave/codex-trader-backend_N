@echo off
REM Inicia el frontend en una nueva ventana de terminal visible
echo Iniciando frontend...
start cmd /k "cd /d %~dp0\..\frontend && npm run dev"
echo Frontend iniciado en nueva ventana













