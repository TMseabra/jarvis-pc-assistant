"""Onde ficam as coisas que o Jarvis cria (fotos, prints, gráficos): Ambiente de Trabalho\\Jarvis\\<tipo>.

Assim sabes sempre onde está tudo. Ficheiros com mais de JARVIS_KEEP_DAYS dias (7 por omissão;
0 = nunca apagar) são apagados sozinhos quando o Jarvis guarda um novo.
"""

import os
import time
from pathlib import Path

from jarvis.config import config


def desktop_dir() -> Path:
    try:
        from win32com.shell import shell, shellcon

        return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
    except Exception:
        return Path.home() / "Desktop"


def base_dir() -> Path:
    custom = os.getenv("JARVIS_OUTPUT_DIR")
    return Path(custom) if custom else desktop_dir() / "Jarvis"


def folder(kind: str) -> Path:
    """kind: "Fotos", "Prints", "Gráficos"."""
    return base_dir() / kind


def clean_old(path: Path, days: float | None = None, now: float | None = None) -> int:
    """Apaga os ficheiros de `path` com mais de `days` dias. Devolve quantos apagou."""
    days = config.keep_days if days is None else days
    if days <= 0 or not path.exists():
        return 0
    limit = (now or time.time()) - days * 86400
    removed = 0
    for file in path.iterdir():
        try:
            if file.is_file() and file.stat().st_mtime < limit:
                file.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def prepare(path: Path) -> Path:
    """Cria a pasta e limpa os ficheiros antigos (chamar antes de guardar um ficheiro novo)."""
    path.mkdir(parents=True, exist_ok=True)
    clean_old(path)
    return path
