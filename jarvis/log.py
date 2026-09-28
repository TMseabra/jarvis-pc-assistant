"""Registo em .jarvis/jarvis.log: o que foi ouvido, pedido, que ferramentas correram e o resultado.

Serve para perceber porque é que algo falhou. Fica só no teu PC (a pasta .jarvis está fora do git).
"""

import logging
from logging.handlers import RotatingFileHandler

from jarvis.config import PROJECT_ROOT

LOG_FILE = PROJECT_ROOT / ".jarvis" / "jarvis.log"

log = logging.getLogger("jarvis")


def setup():
    if log.handlers:
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
