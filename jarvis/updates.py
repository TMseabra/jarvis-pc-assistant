"""Deteta quando o código do Jarvis mudou depois de ele arrancar (uma versão nova), para avisar
e, pelo Telegram, reiniciar com /reiniciar. Um programa só lê o código quando arranca: sem isto,
um Jarvis aberto há horas continua com o comportamento antigo sem ninguém perceber."""

import os
import subprocess
import sys
import time

from jarvis.config import PROJECT_ROOT

STARTED = time.time()
CODE_DIR = PROJECT_ROOT / "jarvis"


def newer_code_available(since: float = STARTED) -> bool:
    return any(p.stat().st_mtime > since + 1 for p in CODE_DIR.rglob("*.py"))


NOTICE = "🔄 Há uma versão nova do Jarvis. Manda /reiniciar (ou fecha e abre o Jarvis) para a usar."


def restart(extra_args: list[str] | None = None):
    """Abre um Jarvis novo (numa janela nova, em modo texto) e fecha este."""
    from jarvis.remote import LOCK_FILE

    LOCK_FILE.unlink(missing_ok=True)  # o novo Jarvis passa a ler o Telegram
    args = extra_args if extra_args is not None else ["--modo", "texto"]
    if "--servico" in sys.argv:
        args = ["--servico"]
        python = PROJECT_ROOT / ".venv" / "Scripts" / "pythonw.exe"
        subprocess.Popen([str(python), "-m", "jarvis.main", *args], cwd=PROJECT_ROOT)
    else:
        subprocess.Popen(["cmd", "/c", "start", "", str(PROJECT_ROOT / "Jarvis.bat"), *args], cwd=PROJECT_ROOT)
    os._exit(0)
