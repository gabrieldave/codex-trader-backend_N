@echo off
REM Script para verificar el tamaño del repositorio en Windows

echo ========================================
echo Verificando tamano del repositorio...
echo ========================================
echo.

REM Tamaño del .git
if exist ".git" (
    echo [1/3] Verificando tamano de .git...
    for /f "tokens=*" %%i in ('powershell -Command "(Get-ChildItem -Path .git -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1GB"') do set git_size=%%i
    echo    Tamano de .git: %git_size% GB
    echo.
    echo    [INFO] Si el tamano es mayor a 0.1 GB (100MB), revisa el repositorio.
) else (
    echo    No se encontro .git
    echo.
)

REM Verificar archivos grandes en staging
echo [2/3] Verificando archivos en staging area...
git diff --cached --name-only >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%f in ('git diff --cached --name-only') do (
        if exist "%%f" (
            for %%s in ("%%f") do (
                set /a size_mb=%%~zs/1048576
                if %%~zs GTR 10485760 (
                    echo    [ERROR] Archivo grande en staging: %%f ^(%%~zs bytes^)
                )
            )
        )
    )
) else (
    echo    No hay archivos en staging
)
echo.

REM Verificar archivos rastreados que deberían estar ignorados
echo [3/3] Verificando archivos rastreados prohibidos...
git ls-files | findstr /i "venv_ingesta data\.pdf \.epub \.pkl \.bin node_modules \.next" >nul 2>&1
if %errorlevel% equ 0 (
    echo    [ERROR] Archivos no deseados encontrados en el repositorio:
    git ls-files | findstr /i "venv_ingesta data\.pdf \.epub \.pkl \.bin node_modules \.next"
    echo.
    echo    Ejecuta: git rm --cached -r ^<archivo^>
) else (
    echo    [OK] No se encontraron archivos prohibidos
)
echo.

echo ========================================
echo Verificacion completada
echo ========================================
pause
