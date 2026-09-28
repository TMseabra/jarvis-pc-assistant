"""Divide um pedido com várias ações em pedidos simples.

"abre o Spotify e a Steam" -> ["abre o Spotify", "abre a Steam"]
"abre o Discord e manda ao Rafosto a dizer anda jogar"
    -> ["abre o Discord", "manda ao Rafosto a dizer anda jogar no Discord"]

Modelos pequenos fazem bem uma ação de cada vez, mas com várias na mesma frase às vezes
só fazem a primeira.
"""

import re

_VERBS = (
    r"abr[ea]|abrir|pesquis[ae]|pesquisar|procur[ae]|procurar|l[êe]|ler|leia|"
    r"envi[ae]|enviar|mand[ae]|mandar|diz|diga|respond[ae]|responder|escrev[ae]|escrever|"
    r"p[õo]e|p[ôo]r|mete|meter|toca|tocar|pausa|reproduz"
)
# Separadores seguidos de um verbo de ação: ", abre", " e manda", " e depois pesquisa"...
_SPLIT = re.compile(
    rf"\s*(?:,|;|\s)\s*(?:e\s+)?(?:depois\s+|também\s+|a\s+seguir\s+)?(?=(?:{_VERBS})\b)",
    re.IGNORECASE,
)
_OPEN = re.compile(r"^(?P<verb>abr[ea]|abrir)\s+(?P<objects>.+)$", re.IGNORECASE)
_SEND = re.compile(r"^(?:envi[ae]|enviar|mand[ae]|mandar|diz|diga|respond[ae]|responder|escrev[ae]|escrever)\b", re.I)
_PLATFORM = re.compile(r"\b(whatsapp|telegram|discord)\b", re.IGNORECASE)
# "abre no VS Code o projeto X", "abre o site..." : não dividir a lista de objetos.
_NO_LIST_SPLIT = re.compile(r"vs ?code|projeto|reposit[óo]rio|https?://|\.com\b|\.pt\b", re.IGNORECASE)
_QUOTED = re.compile(r"[\"“«].*?[\"”»]")
_TO_CLAUDE = re.compile(
    r"(?:diz|diga|mand[ae]|escrev[ae]|pede)\s+(?:ao|a|para\s+o)\s+claud(?:e|inho)\b", re.IGNORECASE
)


def _split_actions(text: str) -> list[str]:
    # Não divide dentro de texto entre aspas nem depois de um "que" (o resto é a mensagem ditada).
    protected = [(m.start(), m.end()) for m in _QUOTED.finditer(text)]
    dictation = re.search(r"\b(?:que|a\s+dizer|dizendo)\s", text, re.IGNORECASE)
    parts, start = [], 0
    for m in _SPLIT.finditer(text):
        if m.start() == 0 or any(a <= m.start() < b for a, b in protected):
            continue
        if dictation and m.start() > dictation.start() and _SEND.match(text[start:]):
            continue
        if _TO_CLAUDE.match(text[m.end():]):  # "...TaskFlow e diz ao Claude para continuar"
            continue
        parts.append(text[start:m.start()])
        start = m.end()
    parts.append(text[start:])
    return [p.strip(" ,.;") for p in parts if p.strip(" ,.;")]


def _split_open_list(part: str) -> list[str]:
    """"abre o Spotify, a Steam e o WhatsApp" -> um "abre" por objeto (se forem nomes curtos)."""
    m = _OPEN.match(part)
    if not m or _NO_LIST_SPLIT.search(part):
        return [part]
    items = [i.strip() for i in re.split(r",\s*|\s+e\s+", m.group("objects")) if i.strip()]
    if len(items) < 2 or any(len(i.split()) > 4 for i in items):
        return [part]
    return [f"{m.group('verb')} {item}" for item in items]


def split_commands(text: str) -> list[str]:
    text = text.strip()
    commands = [c for part in _split_actions(text) for c in _split_open_list(part)]
    # Uma mensagem sem app herda a que foi falada antes ("abre o Discord e manda ao Rafosto...").
    platform = None
    for i, command in enumerate(commands):
        found = _PLATFORM.search(command)
        if found:
            platform = found.group(1)
        elif platform and _SEND.match(command):
            commands[i] = f"{command} no {platform.capitalize() if platform != 'whatsapp' else 'WhatsApp'}"
    return commands or [text]
