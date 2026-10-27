@echo off
title Lumina ERP - Demonstracao
cd /d "%~dp0"

echo ========================================================
echo       INICIANDO DEMONSTRACAO - LUMINA ERP
echo ========================================================
echo.

set PYTHON="C:\Users\wgfer\Downloads\Projeto-fabrica-main\venv\Scripts\python.exe"

echo Iniciando servidor Django na porta 8000...
start "Servidor Lumina ERP Demo" %PYTHON% manage.py runserver 127.0.0.1:8000

timeout /t 2 /nobreak >nul
echo Abrindo o navegador...
start http://127.0.0.1:8000/login/

echo.
echo ========================================================
echo   ACESSO DE DEMONSTRACAO:
echo   URL:      http://127.0.0.1:8000
echo   Usuario:  admin
echo   Senha:    admin
echo ========================================================
echo.
pause
