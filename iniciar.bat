@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Airline Manager 4 Bot

set "RESULTADO=1"
pushd "%~dp0"
if errorlevel 1 (
    >&2 echo [AM4] ERRO: Nao foi possivel abrir a pasta do bot.
    goto :erro
)

if not exist "src\main.py" (
    >&2 echo [AM4] ERRO: src\main.py ausente. Extraia o projeto completo.
    goto :fim
)
if not exist ".venv\Scripts\python.exe" (
    >&2 echo [AM4] ERRO: Ambiente .venv ausente ou incompleto. Execute instalar.bat primeiro.
    goto :fim
)

".venv\Scripts\python.exe" "src\main.py" %*
set "RESULTADO=%errorlevel%"
if not "%RESULTADO%"=="0" (
    >&2 echo [AM4] ERRO: O bot encerrou com o codigo %RESULTADO%. Veja a mensagem acima.
)

:fim
popd
if "%RESULTADO%"=="0" exit /b 0

:erro
pause
exit /b %RESULTADO%
