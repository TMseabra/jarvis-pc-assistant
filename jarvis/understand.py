"""Perceber melhor o que dizes e escreves, antes de o pedido chegar ao resto do Jarvis.

- Limpa a fala: gaguejar ("isto, isto, isto"), hesitações ("epá", "hã", "né").
- Corrige nomes mal ouvidos ou mal escritos: "Lavaloranti" -> Valorant, "Cláudio" -> Claudinho,
  "espotifai" -> Spotify, e nomes parecidos com apps, jogos, contactos e projetos teus.
- Corrige gralhas no verbo do pedido: "abrre o spotify" -> "abre o spotify".

Tudo isto é determinístico (não usa o modelo) e idempotente: aplicar duas vezes dá o mesmo.
"""

import difflib
import re
import time
import unicodedata

# --- normalização -----------------------------------------------------------

_WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


def norm(text: str) -> str:
    """'Põe Música!' -> 'poe musica' (sem acentos, minúsculas, só letras/números e espaços)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), norm(m.group())) for m in _WORD.finditer(text)]


# --- limpar a fala ------------------------------------------------------------

_FILLERS = re.compile(r"(?<!\w)(?:ep[áa]|pá|hã|hum+|hmm+|ahn+|uh+|eh+|né)(?!\w)[,.]?\s*", re.IGNORECASE)
_TIPO = re.compile(r"(^|[,.!?]\s*)tipo\b,?\s+", re.IGNORECASE)
_STUTTER = re.compile(r"(?<!\w)([^\W\d_]{2,})(?:[\s,]+\1(?!\w)){1,3}", re.IGNORECASE)
_NOT_STUTTER = {"nao", "sim", "muito", "mais", "bem", "bom", "boa", "sempre", "nunca"}


def clean_speech(text: str) -> str:
    def stutter(m):
        return m.group(0) if norm(m.group(1)) in _NOT_STUTTER else m.group(1)

    text = _FILLERS.sub("", text)
    text = _TIPO.sub(r"\1", text)
    text = _STUTTER.sub(stutter, text)
    return " ".join(text.split()).strip(" ,")


# --- nomes: apelidos e erros conhecidos ---------------------------------------------

# nome certo -> como o Whisper (ou os dedos) costumam escrevê-lo mal
ALIASES = {
    "Claudinho": ["claudio", "claudinio", "cloudinho", "claudinha", "cloudinio", "claudino"],
    "Valorant": ["valorante", "valoranti", "lavaloranti", "valorent", "valoran", "valorat", "valoarant"],
    "Spotify": ["spotifai", "espotify", "espotifai", "spotifi", "spotfy", "spotfy", "spotifay", "spotifi"],
    "WhatsApp": ["whatsap", "whatsaap", "uatsapp", "whatzap", "zapzap", "watsapp", "wpp", "zap"],
    "Discord": ["diskord", "discorde", "discordi", "discor", "discodr"],
    "Roblox": ["robloxe", "roblocks", "robloques", "robolox", "roblocx", "roblox"],
    "TikTok": ["tik tok", "tique toque", "tik toque", "ticktock", "tiktoc"],
    "YouTube": ["you tube", "iutube", "iu tube", "yutube", "yotube", "youtub"],
    "Instagram": ["insta gram", "instagran", "instagrama", "intagram"],
    "LinkedIn": ["linked in", "linquedin", "linkedim", "linkdin"],
    "Standvirtual": ["stand virtual", "standvirtuel", "standvirtal"],
    "OLX": ["o l x", "olixe", "olex"],
    "Fortnite": ["forte night", "fortnaite", "fortenaite", "fortnait", "fortnight"],
    "Minecraft": ["maine craft", "mainecraft", "maincraft", "minecrafte"],
    "Overwatch": ["overwash", "overuatch", "overwatche", "overwach"],
    "Steam": ["estim", "esteam", "stime"],
    "Telegram": ["telegrama", "telegran", "telagram"],
    "ChatGPT": ["chat gpt", "chatjipiti", "chat gepeté", "chat gpt"],
    "Opera": ["opera gx"],
    "Palworld": ["pal world", "paulworld"],
}
_ALIAS_MAP = {norm(alias): canon for canon, aliases in ALIASES.items() for alias in aliases if norm(alias) != norm(canon)}
_MAX_ALIAS_WORDS = max(len(k.split()) for k in _ALIAS_MAP)

# "abre o cloud" -> "abre o Claudinho" (só depois de verbos, para não mexer em "cloud" de nuvem)
_CLOUD = re.compile(
    r"\b((?:abre|abrir|abra|abres|diz|dizer|pede|pedir|fala|falar|manda|mandar|pergunta|perguntar)(?:-me|-lhe)?"
    r"\s+(?:ao|o|no|com\s+o|para\s+o|pro)\s+)(?:cloud|clod|clode|cloudi|clodinho)\b",
    re.IGNORECASE,
)


def _contact_words() -> set[str]:
    try:
        from jarvis.contacts import known_names

        return {norm(n) for n in known_names()}
    except Exception:
        return set()


def fix_aliases(text: str) -> str:
    toks = _tokens(text)
    protected = _contact_words()
    out, pos, i = [], 0, 0
    while i < len(toks):
        replaced = False
        for n in range(min(_MAX_ALIAS_WORDS, len(toks) - i), 0, -1):
            phrase = " ".join(t[2] for t in toks[i:i + n])
            canon = _ALIAS_MAP.get(phrase)
            if canon and phrase not in protected:
                start, end = toks[i][0], toks[i + n - 1][1]
                out.append(text[pos:start])
                out.append(canon)
                pos, i, replaced = end, i + n, True
                break
        if not replaced:
            i += 1
    out.append(text[pos:])
    return _CLOUD.sub(lambda m: m.group(1) + "Claudinho", "".join(out))


# --- gralhas no verbo ------------------------------------------------------------------

VERBS = {
    "abre": "abre", "abrir": "abrir", "abra": "abra", "fecha": "fecha", "fechar": "fechar", "toca": "toca",
    "tocar": "tocar", "pesquisa": "pesquisa", "pesquisar": "pesquisar", "procura": "procura",
    "procurar": "procurar", "manda": "manda", "mandar": "mandar", "envia": "envia", "enviar": "enviar",
    "diz": "diz", "dizer": "dizer", "responde": "responde", "responder": "responder", "desliga": "desliga",
    "desligar": "desligar", "reinicia": "reinicia", "reiniciar": "reiniciar", "bloqueia": "bloqueia",
    "bloquear": "bloquear", "mostra": "mostra", "mostrar": "mostrar", "instala": "instala",
    "instalar": "instalar", "escreve": "escreve", "escrever": "escrever", "poe": "põe", "mete": "mete",
    "meter": "meter", "salta": "salta", "pausa": "pausa", "continua": "continua", "faz": "faz",
}
_LEAD = re.compile(
    r"^(\W*(?:(?:jarvis|podes|consegues|por favor|se faz favor|ei|hey|ok|entao|agora|e|pf)\W+)*)([^\W\d_]+)",
    re.IGNORECASE,
)


def fix_verb(text: str) -> str:
    m = _LEAD.match(text)
    if not m:
        return text
    word = m.group(2)
    key = norm(word).split(" ")[0]
    if key in VERBS or len(key) < 4 or "-" in word:  # "fecha-me" fica como está
        return text
    close = difflib.get_close_matches(key, VERBS, n=1, cutoff=0.84)
    return text[:m.start(2)] + VERBS[close[0]] + text[m.end(2):] if close else text


# --- nomes parecidos com apps, jogos, contactos e projetos teus -------------------------------

_STATIC_VOCAB = [
    "Spotify", "Steam", "Valorant", "Roblox", "WhatsApp", "Discord", "Telegram", "Instagram", "TikTok",
    "LinkedIn", "YouTube", "Claudinho", "Opera", "ChatGPT", "Overwatch", "Fortnite", "Minecraft", "Palworld",
    "Classroom", "Standvirtual", "Chrome", "Firefox", "Calculadora", "Netflix",
]
_dynamic: list[str] = []
_dynamic_at = 0.0


def load_dynamic() -> list[str]:
    """Nomes das tuas apps, jogos e projetos (chamar uma vez em segundo plano; pode demorar)."""
    global _dynamic, _dynamic_at
    names: list[str] = []
    try:
        from jarvis.actions import system

        names += [n for n, _ in system.list_start_apps()]
    except Exception:
        pass
    try:
        from jarvis.actions import games

        names += [g.name for g in games.list_games()]
    except Exception:
        pass
    try:
        from jarvis.actions import projects

        names += [p.name for p in projects.list_projects()]
    except Exception:
        pass
    _dynamic = [n for n in dict.fromkeys(names) if 4 <= len(norm(n)) <= 30]
    _dynamic_at = time.monotonic()
    return _dynamic


def vocabulary() -> list[str]:
    try:
        from jarvis.contacts import known_names

        contacts = [n for n in known_names() if len(norm(n)) >= 4]
    except Exception:
        contacts = []
    return list(dict.fromkeys(_STATIC_VOCAB + contacts + _dynamic))


_TRIGGERS = {
    "abre", "abrir", "abra", "abres", "fecha", "fechar", "inicia", "iniciar", "arranca", "toca", "entra",
    "entrar", "joga", "jogar", "lanca", "corre", "abre-me", "poe", "mete",
}
_SKIP = {"o", "a", "os", "as", "no", "na", "nos", "nas", "ao", "a", "meu", "minha", "um", "uma", "me", "aplicacao", "app"}
_STOP = {"e", "ou", "no", "na", "nos", "nas", "que", "para", "pra", "com", "do", "da", "de", "por", "se", "depois",
         "ao", "em", "pelo", "pela", "para"}


_OPEN_TRIGGERS = {"abre", "abrir", "abra", "abres", "fecha", "fechar", "inicia", "iniciar", "arranca", "entra",
                  "entrar", "lanca", "joga", "jogar", "corre"}


def _closest(candidate: str, vocab: list[str], cutoff: float = 0.82) -> str | None:
    key = candidate.replace(" ", "")
    if len(key) < 4:
        return None
    best, best_ratio = None, 0.0
    for name in vocab:
        target = norm(name).replace(" ", "")
        if target == key:
            return None  # já está certo
        ratio = difflib.SequenceMatcher(None, key, target).ratio()
        if ratio > best_ratio:
            best, best_ratio = name, ratio
    return best if best_ratio >= cutoff else None


def fix_entities(text: str, vocab: list[str] | None = None) -> str:
    vocab = vocabulary() if vocab is None else vocab
    toks = _tokens(text)
    out, pos, i = [], 0, 0
    while i < len(toks):
        first = toks[i][2].split(" ")[0]
        if first not in _TRIGGERS:
            i += 1
            continue
        j = i + 1
        skipped = 0
        while j < len(toks) and toks[j][2] in _SKIP and skipped < 3:
            j, skipped = j + 1, skipped + 1
        cand = []
        while j + len(cand) < len(toks) and len(cand) < 3:
            k = j + len(cand)
            if toks[k][2] in _STOP or (cand and re.search(r"[,.!?;:]", text[toks[k - 1][1]:toks[k][0]])):
                break
            cand.append(toks[k])
        replaced = False
        for n in range(len(cand), 0, -1):
            phrase = " ".join(t[2] for t in cand[:n])
            if len(phrase.replace(" ", "")) < 4:
                continue
            match = _closest(phrase, vocab, 0.78 if first in _OPEN_TRIGGERS else 0.86)
            if match:
                out.append(text[pos:cand[0][0]])
                out.append(match)
                pos = cand[n - 1][1]
                i = j + n
                replaced = True
                break
        if not replaced:
            i = max(j, i + 1)
    out.append(text[pos:])
    return "".join(out)


# --- tudo junto -----------------------------------------------------------------------------------

def correct(text: str, vocab: list[str] | None = None) -> str:
    """O pedido, já com a fala limpa e os nomes/verbos corrigidos."""
    fixed = clean_speech(text)
    fixed = fix_aliases(fixed)
    fixed = fix_verb(fixed)
    fixed = fix_entities(fixed, vocab)
    return fixed if fixed.strip() else text
