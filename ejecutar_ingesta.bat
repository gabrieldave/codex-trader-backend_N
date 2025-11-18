@echo off
REM Ejecuta la ingesta en una nueva ventana de terminal visible
start cmd /k "cd /d %~dp0 && python ingest_optimized_rag.py"
echo Ingesta iniciada en nueva ventana











