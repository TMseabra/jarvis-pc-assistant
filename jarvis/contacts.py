"""Contactos: os nomes das pessoas com quem falas e as formas como os dizes.

Ficheiro contactos.txt (na pasta do Jarvis, fica fora do git), uma pessoa por linha:

    Rafosto = rafa, rafael, rafostinho
    Rafael Pedro = pedro, rafa pedro

À esquerda o nome como aparece no Discord/WhatsApp; à direita como o costumas dizer.
Serve para duas coisas: o Whisper passa a reconhecer estes nomes quando falas, e o Jarvis
traduz o que disseste para o nome certo antes de procurar a conversa.
"""

import difflib
import unicodedata

from jarvis.config import PROJECT_ROOT

CONTACTS_FILE = PROJECT_ROOT / "contactos.txt"

_TEMPLATE = """\
# Contactos do Jarvis: uma pessoa por linha.
# À esquerda o nome como aparece no Discord/WhatsApp; à direita (separadas por vírgulas)
# as formas como o dizes. As linhas começadas por # são ignoradas.
#
# Rafosto = rafa, rafael, rafostinho
# Rafael Pedro = pedro, rafa pedro
"""


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in decomposed if ch.isalnum() or ch.isspace()).split())


def load(path=None) -> list[tuple[str, list[str]]]:
    path = path or CONTACTS_FILE
    if not path.exists():
        try:
            path.write_text(_TEMPLATE, encoding="utf-8")  # cria o modelo para o utilizador preencher
        except OSError:
            pass
        return []
    contacts = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        real, _, aliases = line.partition("=")
        real = real.strip()
        if real:
            contacts.append((real, [a.strip() for a in aliases.split(",") if a.strip()]))
    return contacts


def resolve(spoken: str, contacts: list[tuple[str, list[str]]] | None = None) -> str:
    """Nome dito -> nome real. Exato (nome ou alcunha) primeiro; depois o mais parecido
    (o Whisper às vezes ouve "Rafosta" em vez de "Rafosto"). Se não souber, devolve o que foi dito."""
    contacts = load() if contacts is None else contacts
    target = _fold(spoken)
    if not target:
        return spoken
    for real, aliases in contacts:
        if target in {_fold(real), *(_fold(a) for a in aliases)}:
            return real
    best, best_score = None, 0.0
    for real, aliases in contacts:
        for form in (real, *aliases):
            score = difflib.SequenceMatcher(None, target, _fold(form)).ratio()
            if score > best_score:
                best, best_score = real, score
    return best if best and best_score >= 0.8 else spoken


def known_names(contacts: list[tuple[str, list[str]]] | None = None) -> list[str]:
    contacts = load() if contacts is None else contacts
    names = []
    for real, aliases in contacts:
        names += [real, *aliases]
    return list(dict.fromkeys(names))
