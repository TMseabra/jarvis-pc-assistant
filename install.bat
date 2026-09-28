@echo off
rem Instala o Jarvis: ambiente Python, dependencias, browser e atalho no ambiente de trabalho.
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul || (
    echo Python nao encontrado. Instala o Python 3.11+ em https://www.python.org e volta a correr.
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] A criar o ambiente Python...
    python -m venv .venv || exit /b 1
)

echo [2/4] A instalar dependencias (pode demorar)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || exit /b 1

echo [3/4] A instalar o browser para WhatsApp / Telegram / Discord...
".venv\Scripts\python.exe" -m playwright install chromium || exit /b 1

echo [4/4] A criar o atalho no ambiente de trabalho...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcut.ps1"

where ollama >nul 2>nul && (
    echo A descarregar o modelo do Ollama, se ainda nao existir...
    ollama pull qwen2.5:7b
) || (
    echo Nota: o Ollama nao esta instalado. Instala em https://ollama.com ou usa o Gemini ^(ver README^).
)

echo.
echo Pronto! Abre o Jarvis pelo atalho no ambiente de trabalho.
exit /b 0
