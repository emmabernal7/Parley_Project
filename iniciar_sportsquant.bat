@echo off
chcp 65001 >nul
title SportsQuant v2 - Plataforma Cuantitativa y Sportsbook
color 0A

echo ========================================================
echo        SPORTSQUANT v2 - PLATAFORMA CUANTITATIVA
echo ========================================================
echo.

:: Detectar directorio de trabajo
cd /d "%~dp0"
if exist "sports-quant-ai-v2\run.py" (
    cd /d "%~dp0sports-quant-ai-v2"
)

:: Detectar interprete de Python funcional con dependencias instaladas
set "PYTHON_CMD="
for %%P in (
    "%~dp0.venv\Scripts\python.exe"
    "%~dp0venv\Scripts\python.exe"
    ".venv\Scripts\python.exe"
    "venv\Scripts\python.exe"
    "%USERPROFILE%\Miniconda3\python.exe"
    "%USERPROFILE%\anaconda3\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Miniconda3\python.exe"
    "python"
) do (
    if not defined PYTHON_CMD (
        if exist "%%~P" (
            "%%~P" -c "import fastapi, uvicorn, yaml" >nul 2>&1
            if not errorlevel 1 set "PYTHON_CMD=%%~P"
        ) else if "%%~P"=="python" (
            python -c "import fastapi, uvicorn, yaml" >nul 2>&1
            if not errorlevel 1 set "PYTHON_CMD=python"
        )
    )
)

:: Si no se encontro ningun Python con paquetes, probar comando generico
if not defined PYTHON_CMD (
    python --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] No se encontro un interprete de Python instalado en el sistema.
    echo Instala Python o Miniconda y agrega la ruta al PATH.
    echo.
    pause
    exit /b 1
)

echo [OK] Interprete detectado: %PYTHON_CMD%
echo [OK] Iniciando servidor web cuantitativo...
echo [INFO] URL: http://127.0.0.1:8000
echo [INFO] Tu navegador se abrira automaticamente en cuanto el servidor este listo.
echo [INFO] Para detener el servidor presiona Ctrl + C en esta ventana.
echo.

:: Lanzador de respaldo en segundo plano via PowerShell (espera a que el puerto 8000 responda 200 OK)
start "" powershell -NoProfile -WindowStyle Hidden -Command "$u='http://127.0.0.1:8000'; for($i=0;$i -lt 30;$i++){ try { $r = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 1; if($r.StatusCode -eq 200){ Start-Process $u; break } } catch {}; Start-Sleep -Milliseconds 400 }"

:: Ejecutar aplicacion
"%PYTHON_CMD%" run.py

if errorlevel 1 (
    echo.
    echo ========================================================
    echo [AVISO] El servidor se ha detenido con error.
    echo Revisa el mensaje anterior para corregir el inconveniente.
    echo ========================================================
    echo.
    pause
)
