@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Instalar Airline Manager 4 Bot

echo [AM4] Instalar Airline Manager 4 Bot
echo [AM4] Requisitos manuais: Python 3.10 ou superior e Google Chrome ou Chromium compativel.
echo.

pushd "%~dp0"
if errorlevel 1 (
    >&2 echo [AM4] ERRO: Nao foi possivel abrir a pasta do instalador.
    pause
    exit /b 1
)

call :instalar
set "RESULTADO=%errorlevel%"
popd
echo.
pause
exit /b %RESULTADO%

:instalar
for %%A in (requirements.txt src\main.py config\defaults.ini iniciar.bat) do (
    if not exist "%%A" (
        >&2 echo [AM4] ERRO: Arquivo ausente: %%A. Extraia o projeto completo e tente novamente.
        exit /b 1
    )
)

if exist ".venv" (
    echo [AM4] Reutilizando o ambiente .venv...
) else (
    call :criar_venv
    if errorlevel 1 exit /b 1
)

if not exist ".venv\Scripts\python.exe" goto :venv_invalido
".venv\Scripts\python.exe" -I -c "import sys; sys.exit(not (sys.prefix != sys.base_prefix and sys.version_info >= (3, 10)))"
if errorlevel 1 goto :venv_invalido

".venv\Scripts\python.exe" -I -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [AM4] Preparando o pip no ambiente .venv...
    ".venv\Scripts\python.exe" -I -m ensurepip
    if errorlevel 1 (
        >&2 echo [AM4] ERRO: Nao foi possivel preparar o pip no ambiente .venv.
        exit /b 1
    )
)

echo [AM4] Instalando as dependencias de requirements.txt...
".venv\Scripts\python.exe" -I -m pip install -r "requirements.txt"
if errorlevel 1 (
    >&2 echo [AM4] ERRO: O pip falhou ao instalar as dependencias.
    exit /b 1
)

echo.
echo [AM4] Instalacao concluida. No primeiro uso, abra "iniciar.bat" para configurar o login no desktop.
echo [AM4] Painel web opcional depois da configuracao: "scripts\web.bat".
exit /b 0

:criar_venv
rem Impede instalacao automatica de Python pelos launchers do Windows.
set "PYTHON_MANAGER_AUTOMATIC_INSTALL=false"
set "PYLAUNCHER_ALLOW_INSTALL="

set "PYTHON=py.exe -3"
py.exe -3 -I -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    set "PYTHON=python.exe"
    python.exe -I -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
    if errorlevel 1 (
        >&2 echo [AM4] ERRO: Python 3.10 ou superior nao encontrado.
        >&2 echo [AM4] Instale o Python, adicione-o ao PATH e execute instalar.bat novamente.
        exit /b 1
    )
)

echo [AM4] Criando o ambiente .venv...
%PYTHON% -I -m venv ".venv"
if errorlevel 1 (
    >&2 echo [AM4] ERRO: Nao foi possivel criar o ambiente .venv.
    exit /b 1
)
exit /b 0

:venv_invalido
>&2 echo [AM4] ERRO: O ambiente .venv esta incompleto ou nao usa Python 3.10 ou superior.
>&2 echo [AM4] Renomeie a pasta .venv e execute instalar.bat novamente para recria-la.
exit /b 1
