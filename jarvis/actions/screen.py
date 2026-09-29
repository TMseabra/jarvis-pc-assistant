"""Prints do ecrã (guardados em .jarvis/prints; o Telegram envia-os para o chat)."""

from datetime import datetime
from pathlib import Path


ATTACHMENT = "📎 "  # prefixo no resultado da ferramenta: o Telegram envia o ficheiro a seguir


def screenshot(monitor: int = 0, folder: Path | None = None) -> str:
    """Print de todos os ecrãs (monitor=0) ou de um (1, 2, ...)."""
    import mss
    import mss.tools

    from jarvis import outputs

    folder = outputs.prepare(folder or outputs.folder("Prints"))
    path = folder / f"print_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
    with mss.mss() as sct:
        monitors = sct.monitors  # [0] = todos juntos, [1..] = cada ecrã
        index = monitor if 0 <= monitor < len(monitors) else 0
        image = sct.grab(monitors[index])
        mss.tools.to_png(image.rgb, image.size, output=str(path))
    which = "de todos os ecrãs" if index == 0 else f"do ecrã {index}"
    return f"Tirei um print {which}.\n{ATTACHMENT}{path}"


def attachments(text: str) -> list[Path]:
    """Ficheiros anexados num resultado de ferramenta (linhas "📎 caminho")."""
    return [Path(line[len(ATTACHMENT):].strip()) for line in text.splitlines() if line.startswith(ATTACHMENT)]
