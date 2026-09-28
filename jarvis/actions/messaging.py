"""Automação de WhatsApp Web, Telegram Web e Discord com Playwright.

Usa um perfil de browser persistente: na primeira vez é preciso fazer login
manualmente (QR code / credenciais) na janela que o Jarvis abre; as sessões
ficam guardadas para as vezes seguintes.

Os seletores CSS dependem do HTML de cada site e podem deixar de funcionar
quando estes mudam — estão todos concentrados em PLATFORMS para serem fáceis
de atualizar.
"""

import difflib
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Platform:
    name: str
    url: str
    # Elemento que só existe depois do login (serve para esperar pelo login).
    ready: str
    # Como abrir uma conversa: "search" usa a caixa de pesquisa, "quick_switcher" usa Ctrl+K.
    open_mode: str
    search_box: str
    # Resultados da pesquisa (cada um tem o nome da conversa no texto).
    results: str
    # Nome da conversa aberta (cabeçalho), para confirmar que é a pessoa certa.
    chat_title: str
    message: str
    message_text: str
    composer: str
    login_hint: str


PLATFORMS: dict[str, Platform] = {
    "whatsapp": Platform(
        name="WhatsApp",
        url="https://web.whatsapp.com/",
        ready="#side",
        open_mode="search",
        search_box='#side div[contenteditable="true"]',
        results='#pane-side div[role="listitem"], #pane-side div[role="row"]',
        chat_title='#main header span[dir="auto"]',
        message="div.message-in, div.message-out",
        message_text="span.selectable-text",
        composer='footer div[contenteditable="true"]',
        login_hint="Faz scan do QR code com o telemóvel (WhatsApp > Dispositivos ligados).",
    ),
    "telegram": Platform(
        name="Telegram",
        url="https://web.telegram.org/k/",
        ready="input.input-search-input",
        open_mode="search",
        search_box="input.input-search-input",
        results=".search-group a.chatlist-chat, .search-group .chatlist-chat",
        chat_title=".chat-info .peer-title",
        message=".bubbles .bubble",
        message_text=".message",
        composer='div.input-message-input[contenteditable="true"]',
        login_hint="Faz login no Telegram Web (QR code ou número de telefone).",
    ),
    "discord": Platform(
        name="Discord",
        url="https://discord.com/channels/@me",
        ready='nav[aria-label], [class*="guilds"]',
        open_mode="quick_switcher",
        search_box='input[aria-label="Quick switcher"], [class*="quickswitcher"] input',
        results="",
        chat_title='section[class*="title"] h1, [class*="titleWrapper"] h1, h1[class*="title"]',
        message='li[id^="chat-messages-"]',
        message_text='div[id^="message-content-"]',
        composer='div[role="textbox"][data-slate-editor="true"]',
        login_hint="Faz login no Discord (QR code ou email/password).",
    ),
}

LOGIN_TIMEOUT_MS = 180_000
ACTION_TIMEOUT_MS = 15_000


class MessagingError(Exception):
    pass


@dataclass
class ChatMessage:
    author: str
    text: str
    time: str = ""
    outgoing: bool = False


def get_platform(platform: str) -> Platform:
    key = platform.strip().lower()
    if key not in PLATFORMS:
        raise MessagingError(
            f"Plataforma desconhecida: '{platform}'. Usa: {', '.join(PLATFORMS)}."
        )
    return PLATFORMS[key]


def normalize_name(name: str) -> str:
    """Minúsculas, sem acentos nem emojis/pontuação: 'Ána Sofia 🌸' -> 'ana sofia'."""
    decomposed = unicodedata.normalize("NFKD", name.casefold())
    kept = "".join(ch for ch in decomposed if ch.isalnum() or ch.isspace())
    return " ".join(kept.split())


def name_matches(title: str, contact: str) -> bool:
    """O nome pedido corresponde ao título da conversa? Todas as palavras pedidas têm de lá estar
    ("Ana" corresponde a "Ana Silva", mas não a "Anabela"; "Ana Silva" não corresponde a "Ana Costa")."""
    title_words = set(normalize_name(title).split())
    wanted = normalize_name(contact).split()
    return bool(wanted) and all(w in title_words for w in wanted)


def pick_result(titles: list[str], contact: str, fuzzy: bool = False) -> int | None:
    """Índice do resultado que melhor corresponde ao contacto (exato > parcial > parecido).

    fuzzy=True aceita nomes parecidos ("Rafosta" -> "Rafosto"), para quando o reconhecimento
    de voz ouve mal. Quem usa isto deve depois confirmar com o nome escolhido (titles[i]).
    """
    target = normalize_name(contact)
    matches = [i for i, t in enumerate(titles) if name_matches(t, contact)]
    for i in matches:
        if normalize_name(titles[i]) == target:
            return i
    if matches:
        return matches[0]
    if fuzzy and target:
        scores = [(difflib.SequenceMatcher(None, target, normalize_name(t)).ratio(), i) for i, t in enumerate(titles)]
        best = max(scores, default=(0, None))
        if best[0] >= 0.75:
            return best[1]
    return None


def parse_whatsapp_meta(pre: str) -> tuple[str, str]:
    """'[12:34, 01/01/2026] Ana Silva: ' -> ('Ana Silva', '12:34')."""
    if not pre.startswith("["):
        return "", ""
    stamp, _, rest = pre[1:].partition("] ")
    return rest.rstrip().rstrip(":").strip(), stamp.split(",")[0].strip()


def format_messages(messages: list[ChatMessage]) -> str:
    if not messages:
        return "Não encontrei mensagens nesta conversa."
    lines = []
    for m in messages:
        who = "Tu (enviada)" if m.outgoing else (m.author or "Outra pessoa")
        when = f"[{m.time}] " if m.time else ""
        lines.append(f"{when}{who}: {m.text}")
    return "\n".join(lines)


class Messenger:
    """Mantém um browser aberto (perfil persistente) com um separador por plataforma."""

    def __init__(self, profile_dir: Path, notify=print, headless: bool = False):
        self.profile_dir = profile_dir
        self.notify = notify
        self.headless = headless
        self._playwright = None
        self._context = None
        self._pages: dict[str, object] = {}

    # --- ciclo de vida -------------------------------------------------------

    def _ensure_context(self):
        if self._context is not None:
            return self._context
        from playwright.sync_api import sync_playwright

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            viewport=None,
            args=["--start-maximized"],
        )
        return self._context

    def close(self):
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._pages.clear()

    def _page(self, p: Platform):
        context = self._ensure_context()
        page = self._pages.get(p.name)
        if page is None or page.is_closed():
            page = context.pages[0] if not self._pages and context.pages else context.new_page()
            page.goto(p.url)
            self._pages[p.name] = page
        page.bring_to_front()
        try:
            page.wait_for_selector(p.ready, timeout=ACTION_TIMEOUT_MS)
        except Exception:
            self.notify(f"[{p.name}] À espera de login. {p.login_hint}")
            page.wait_for_selector(p.ready, timeout=LOGIN_TIMEOUT_MS)
        return page

    # --- ações ---------------------------------------------------------------

    def _chat_title(self, page, p: Platform) -> str:
        el = page.query_selector(p.chat_title)
        return el.inner_text().strip() if el else ""

    def _open_chat(self, page, p: Platform, contact: str) -> str:
        """Abre a conversa e devolve o nome que aparece no cabeçalho."""
        if normalize_name(self._chat_title(page, p)) == normalize_name(contact):
            return self._chat_title(page, p)  # já está aberta

        if p.open_mode == "quick_switcher":
            page.keyboard.press("Control+K")
            box = page.wait_for_selector(p.search_box, timeout=ACTION_TIMEOUT_MS)
            box.fill(contact)
            page.wait_for_timeout(1200)
            page.keyboard.press("Enter")
        else:
            box = page.wait_for_selector(p.search_box, timeout=ACTION_TIMEOUT_MS)
            box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(contact, delay=30)
            page.wait_for_timeout(1500)
            results = page.query_selector_all(p.results)
            titles = [(r.inner_text().strip().split("\n") or [""])[0] for r in results]
            index = pick_result(titles, contact)
            if index is None:
                found = ", ".join(t for t in titles[:5] if t)
                hint = f" Encontrei: {found}." if found else ""
                raise MessagingError(f"Não encontrei a conversa '{contact}' no {p.name}.{hint}")
            results[index].click()
        try:
            page.wait_for_selector(p.composer, timeout=ACTION_TIMEOUT_MS)
        except Exception as exc:
            raise MessagingError(f"Não consegui abrir a conversa '{contact}' no {p.name}.") from exc
        page.wait_for_timeout(800)
        # Pode vir vazio se o seletor do cabeçalho deixar de funcionar: quem chama decide.
        return self._chat_title(page, p)

    def _extract_messages(self, page, p: Platform, limit: int) -> list[ChatMessage]:
        out: list[ChatMessage] = []
        for item in page.query_selector_all(p.message)[-limit:]:
            text_el = item.query_selector(p.message_text)
            text = (text_el.inner_text() if text_el else item.inner_text()).strip()
            if not text:
                continue
            classes = item.get_attribute("class") or ""
            msg = ChatMessage(author="", text=text)
            if p.name == "WhatsApp":
                msg.outgoing = "message-out" in classes
                meta = item.query_selector("[data-pre-plain-text]")
                if meta:
                    msg.author, msg.time = parse_whatsapp_meta(meta.get_attribute("data-pre-plain-text") or "")
            elif p.name == "Telegram":
                msg.outgoing = "is-out" in classes
            elif p.name == "Discord":
                author = item.query_selector('[id^="message-username-"]')
                msg.author = author.inner_text().strip() if author else ""
            out.append(msg)
        return out

    def read_messages(self, platform: str, contact: str, count: int = 10) -> str:
        p = get_platform(platform)
        page = self._page(p)
        title = self._open_chat(page, p, contact)
        messages = self._extract_messages(page, p, max(1, min(count, 50)))
        if not title:
            header = f"Conversa: {contact}? ({p.name}) — atenção: não consegui confirmar o nome da conversa aberta"
        elif not name_matches(title, contact):
            header = f"Conversa: {title} ({p.name}) — atenção: pediste '{contact}', mas a conversa aberta é '{title}'"
        else:
            header = f"Conversa: {title} ({p.name})"
        return header + "\n" + format_messages(messages)

    def send_message(self, platform: str, contact: str, message: str, confirm=None) -> str | None:
        """Envia `message`. Se `confirm` for dado, é chamado com o nome da conversa já aberta e
        verificada, e devolve o texto final a enviar (ou None para cancelar -> devolve None)."""
        p = get_platform(platform)
        page = self._page(p)
        title = self._open_chat(page, p, contact)
        if not title:
            raise MessagingError(
                f"Não consegui confirmar que a conversa aberta no {p.name} é a de '{contact}'. "
                "Por segurança não enviei nada."
            )
        if not name_matches(title, contact):
            raise MessagingError(
                f"A conversa aberta é '{title}', não '{contact}'. Por segurança não enviei nada."
            )
        if confirm is not None:
            message = confirm(title)
            if not message:
                return None
        composer = page.wait_for_selector(p.composer, timeout=ACTION_TIMEOUT_MS)
        composer.click()
        for i, line in enumerate(message.split("\n")):
            if i:
                page.keyboard.press("Shift+Enter")
            page.keyboard.type(line, delay=10)
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)
        return f"Mensagem enviada para {title} no {p.name}."
