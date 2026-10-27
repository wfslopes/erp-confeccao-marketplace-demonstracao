@echo off
title Parar Lumina ERP Demo
cd /d "%~dp0"

echo Encerrando servidor na porta 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    taskkill /f /pid %%a 2>nul
)

echo Servidor encerrado.
timeout /t 2 >nul
exit
