@echo off
REM Abre verificación de estado en una nueva ventana de terminal
start cmd /k "cd /d %~dp0 && python verificar_estado_ingesta.py && pause"
echo Verificación abierta en nueva ventana











