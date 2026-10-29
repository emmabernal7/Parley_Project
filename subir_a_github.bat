@echo off
chcp 65001 >nul
title Subir SportsQuant a GitHub (Parley_Project)
color 0B

echo ========================================================
echo        SUBIR PROYECTO PARLEY (SPORTSQUANT v2) A GITHUB
echo ========================================================
echo Repositorio destino: https://github.com/emmabernal7/Parley_Project.git
echo.

:: 1. Detectar directorio del proyecto
cd /d "%~dp0"
if exist "sports-quant-ai-v2\run.py" (
    cd /d "%~dp0sports-quant-ai-v2"
)

echo [INFO] Carpeta de trabajo: %CD%
echo.

:: 2. Verificar que Git este instalado
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encontro Git instalado o no esta en el PATH de Windows.
    echo Por favor descarga e instala Git desde: https://git-scm.com/
    echo.
    pause
    exit /b 1
)

:: 3. Inicializar repositorio Git si no existe
if not exist ".git" (
    echo [INFO] Inicializando repositorio Git local...
    git init
    if errorlevel 1 (
        echo [ERROR] No se pudo inicializar git.
        pause
        exit /b 1
    )
)

:: 4. Configurar rama principal (main) y repositorio remoto
git branch -M main
git remote remove origin >nul 2>&1
git remote add origin https://github.com/emmabernal7/Parley_Project.git
echo [OK] Remoto configurado: https://github.com/emmabernal7/Parley_Project.git
echo.

:: 5. Mostrar archivos modificados y nuevos
echo ========================================================
echo [ESTADO DE ARCHIVOS]
echo ========================================================
git status --short
echo.

:: 6. Solicitar mensaje de commit
set "DEFAULT_MSG=SportsQuant v2: Plataforma Cuantitativa y Sportsbook (+EV, Dixon-Coles, FastAPI, UI Bilingue)"
echo Presiona ENTER para usar el mensaje por defecto:
echo "%DEFAULT_MSG%"
echo.
set /p "USER_MSG=O escribe un mensaje personalizado: "

if "%USER_MSG%"=="" (
    set "COMMIT_MSG=%DEFAULT_MSG%"
) else (
    set "COMMIT_MSG=%USER_MSG%"
)

echo.
echo [INFO] Preparando archivos para commit...
git add .

git commit -m "%COMMIT_MSG%"
echo.

:: 7. Subir a GitHub
echo ========================================================
echo [SUBIENDO A GITHUB]
echo ========================================================
echo Si es tu primera vez conectandote a GitHub en esta maquina,
echo se abrira una ventana emergente para autenticarte con tu cuenta de GitHub.
echo.

git push -u origin main
if errorlevel 1 (
    echo.
    echo [AVISO] El comando push directo fallo. Es posible que el repositorio
    echo en GitHub ya contenga archivos (como README o LICENSE).
    echo Intentando sincronizar y combinar con rebase...
    echo.
    git pull origin main --rebase
    if not errorlevel 1 (
        git push -u origin main
    )
)

if errorlevel 1 (
    echo.
    echo ========================================================
    echo [ERROR AL SUBIR]
    echo No se pudo completar la subida a GitHub.
    echo.
    echo Posibles causas y soluciones:
    echo 1. Autenticacion: Si te pide contrasena, usa un "Personal Access Token" de GitHub.
    echo 2. El repositorio https://github.com/emmabernal7/Parley_Project no existe
    echo    o tu usuario no tiene permisos de escritura.
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo [EXITO] Proyecto subido correctamente a GitHub!
    echo Puedes verlo en: https://github.com/emmabernal7/Parley_Project
    echo ========================================================
)

echo.
pause
