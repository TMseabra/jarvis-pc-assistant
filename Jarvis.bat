@echo off
rem Duplo clique para abrir o Jarvis.
chcp 65001 >nul
title Jarvis
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo O Jarvis ainda nao esta instalado. A correr o instalador...
    call "%~dp0install.bat" || (pause & exit /b 1)
)

".venv\Scripts\python.exe" -m jarvis.main %*
if errorlevel 1 pause
