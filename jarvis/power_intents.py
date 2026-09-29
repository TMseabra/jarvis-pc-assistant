"""Bloquear / desligar / reiniciar / suspender o PC, sempre com uma pergunta antes:

"fecha o PC" -> "Bloqueio o PC (Windows + L)?" -> "sim" -> bloqueia.
"desliga o PC" -> "Desligo o PC?" -> "sim" -> desliga (com 15 s para cancelar).
"""

import re

_LEAD = r"^\W*(?:(?:jarvis|podes|consegues|por\s+favor|quero)\W+)*"
_PC = r"(?:o\s+)?(?:pc|computador|port[aá]til|windows)"

INTENTS = [
    ("cancel", re.compile(r"cancela(?:r)?\s+(?:o\s+)?(?:desligar|encerrar|reiniciar|shutdown)|n[aã]o\s+desligues", re.I),
     None),
    ("lock", re.compile(_LEAD + r"(?:(?:fecha|fechar|bloqueia|bloquear|tranca|trancar)\s+" + _PC + r"|"
                        r"(?:windows|win)\s*(?:\+|mais)?\s*l|lock(?:[\s_-]*pc)?)\W*$", re.I),
     "Bloqueio o PC (Windows + L)?"),
    ("shutdown", re.compile(_LEAD + r"(?:desliga|desligar|encerra|encerrar|apaga|apagar)\s+" + _PC + r"\W*$|"
                            r"^\W*shutdown\W*$", re.I),
     "Desligo o PC? (Fica 15 segundos para cancelares.)"),
    ("restart", re.compile(_LEAD + r"(?:reinicia|reiniciar|restart)\s+" + _PC + r"\W*$", re.I),
     "Reinicio o PC? (Fica 15 segundos para cancelares.)"),
    ("sleep", re.compile(_LEAD + r"(?:suspende|suspender|p[oõ]e\s+" + _PC + r"\s+(?:a\s+dormir|em\s+suspens[aã]o)|"
                         r"(?:mete|p[oõ]e)\s+" + _PC + r"\s+a\s+dormir)(?:\s+" + _PC + r")?\W*$", re.I),
     "Ponho o PC em suspensão?"),
]


def parse_power(text: str) -> tuple[str, str | None] | None:
    """-> (ação, pergunta de confirmação) ou None. "cancel" não precisa de pergunta."""
    for action, pattern, question in INTENTS:
        if pattern.search(text):
            return action, question
    return None
