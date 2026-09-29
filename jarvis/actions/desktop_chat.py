"""WhatsApp e Discord através das apps de desktop (UI Automation do Windows).

As duas apps são páginas web dentro de uma janela (WebView2 / Electron) e expõem a
interface ao Windows: dá para encontrar a caixa de pesquisa, a lista de conversas e a
caixa de escrever sem depender de coordenadas. Tal como na versão web, antes de enviar
confirmamos que a conversa aberta é a da pessoa pedida; se não der para confirmar,
não enviamos.
"""

import contextlib
import os
import re
import time

from jarvis.actions.messaging import (
    ChatMessage,
    MessagingError,
    format_messages,
    name_matches,
    normalize_name,
    pick_result,
)

WAIT_WINDOW_S = 25
WAIT_UI_S = 8


def _wait(predicate, timeout: float, interval: float = 0.25):
    end = time.monotonic() + timeout
    while True:
        try:
            value = predicate()
        except Exception:
            value = None
        if value or time.monotonic() > end:
            return value
        time.sleep(interval)


@contextlib.contextmanager
def keep_user_context():
    """Guarda a janela à frente (ex.: o jogo) e a posição do rato, e repõe-nas no fim:
    o Jarvis escreve a mensagem e devolve-te o jogo sem te roubar o rato."""
    try:
        import win32api
        import win32gui

        previous = win32gui.GetForegroundWindow()
        cursor = win32api.GetCursorPos()
    except Exception:
        previous = cursor = None
    try:
        yield
    finally:
        if cursor is not None:
            try:
                win32api.SetCursorPos(cursor)
                if previous and win32gui.IsWindow(previous) and win32gui.GetForegroundWindow() != previous:
                    from jarvis.actions.windows import bring_to_front

                    bring_to_front(previous, maximize=False)
            except Exception:
                pass


def _composer_text(composer) -> str | None:
    """Texto na caixa de escrever (só leitura), ou None se a app não o deixar ler."""
    try:
        return composer.iface_value.CurrentValue or ""
    except Exception:
        return None


def _type_and_send(window, find_composer, message: str, app: str):
    """Põe a janela à frente, cola o texto, confirma que ficou na caixa e só então carrega em Enter.
    Se outra janela (um jogo) roubar o foco, tenta outra vez; se não der, não envia."""
    import win32gui
    from pywinauto.keyboard import send_keys

    probe = " ".join(message.split())[:20]
    for attempt in range(3):
        composer = _wait(find_composer, WAIT_UI_S)
        if not composer:
            raise MessagingError(f"Não encontrei a caixa de escrever do {app}. Não enviei nada.")
        window.set_focus()
        composer.set_focus()
        if win32gui.GetForegroundWindow() != window.handle:
            time.sleep(0.3)
            continue
        before = _composer_text(composer)
        if before is None or probe not in " ".join(before.split()):
            _paste(message)
            time.sleep(0.2)
        typed = _composer_text(find_composer() or composer)
        written = typed is None or probe in " ".join(typed.split())  # sem leitura: confia no colar
        if written and win32gui.GetForegroundWindow() == window.handle:
            send_keys("{ENTER}")
            return
        time.sleep(0.4)
    raise MessagingError(f"Não consegui escrever no {app} (outra janela, talvez o jogo, estava sempre à frente). "
                         "Não enviei nada.")


def _paste(text: str):
    """Escreve `text` com colar (Ctrl+V): acentos, emojis e quebras de linha saem certos.
    Repõe o que estava na área de transferência."""
    import win32clipboard
    from pywinauto.keyboard import send_keys

    previous = None
    win32clipboard.OpenClipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            previous = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    send_keys("^v")
    time.sleep(0.3)
    if previous is not None:
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, previous)
        finally:
            win32clipboard.CloseClipboard()


class DesktopChat:
    """Base: encontra/abre a janela da app e põe-na à frente."""

    name = ""
    app_id = ""  # para os.startfile("shell:AppsFolder\\<app_id>")

    def _find_window(self):
        raise NotImplementedError

    def _ready(self, window) -> bool:
        raise NotImplementedError

    def window(self):
        from pywinauto import Desktop  # noqa: F401 (garante que o pywinauto existe)

        window = self._find_window()
        if window is None:
            os.startfile(f"shell:AppsFolder\\{self.app_id}")  # type: ignore[attr-defined]
            window = _wait(self._find_window, WAIT_WINDOW_S)
            if window is None:
                raise MessagingError(f"Não consegui abrir o {self.name}.")
        if window.is_minimized():
            window.restore()
        window.set_focus()
        if not _wait(lambda: self._ready(window), WAIT_WINDOW_S):
            raise MessagingError(f"O {self.name} abriu mas não ficou pronto (tens a sessão iniciada?).")
        return window

    def close(self):
        pass  # as apps continuam abertas


# --- Discord ---------------------------------------------------------------

_DISCORD_TAG = re.compile(r"(?:Tag do servidor|Server Tag).*$", re.I)
_DISCORD_NOISE = re.compile(
    r"^(?:\d{1,2}:\d{2}|\d{2}/\d{2}/\d{4}.*|(?:segunda|terça|quarta|quinta|sexta)-feira.*|sábado.*|domingo.*|"
    r"hoje.*|ontem.*|:\w+:|\d+|Clique para reagir|Modificar anexo|Excluir|Responder|\(editado\)|editado)$",
    re.I,
)


def clean_discord_name(name: str) -> str:
    """'RafostoTag do servidor: 5-O' -> 'Rafosto'; 'Sagaris, Rafosto3 membros' -> 'Sagaris, Rafosto'."""
    name = re.sub(r"^Mensagens não lidas,\s*", "", name)
    name = _DISCORD_TAG.sub("", name)
    name = re.sub(r"\d+\s*membros?$", "", name)
    return re.sub(r"\d+$", "", name).strip(" ,")


def parse_discord_message(texts: list[tuple[str, str]]) -> tuple[str, str]:
    """[(texto, automation_id), ...] de um item da lista de mensagens -> (autor, conteúdo).
    O autor aparece antes do elemento message-timestamp-*; mensagens seguidas não o repetem."""
    ts = next((i for i, (_, aid) in enumerate(texts) if aid.startswith("message-timestamp")), None)
    before = texts[:ts] if ts is not None else []
    after = texts[ts + 1:] if ts is not None else texts
    author = clean_discord_name(" ".join(t for t, _ in before if t.strip()))
    content = " ".join(t.strip() for t, _ in after if t.strip() and not _DISCORD_NOISE.match(t.strip()))
    return author, content


class DiscordDesktop(DesktopChat):
    name = "Discord"
    app_id = "com.squirrel.Discord.Discord"
    opened_by_jarvis = False

    def _find_window(self):
        from pywinauto import Desktop

        for w in Desktop(backend="uia").windows(class_name="Chrome_WidgetWin_1"):
            title = w.window_text()
            if title == "Discord" or title.endswith(" - Discord"):
                return w
        return None

    def _ready(self, window) -> bool:
        return bool(window.descendants(control_type="Edit") or self._dm_list(window))

    @staticmethod
    def _dm_list(window):
        return next(
            (l for l in window.descendants(control_type="List")
             if (l.element_info.name or "") in ("Mensagens diretas", "Direct Messages")),
            None,
        )

    def _current_chat(self, window) -> str:
        """Nome da conversa aberta: título da janela ou nome da caixa de escrever."""
        title = window.window_text()
        if title.endswith(" - Discord"):
            return title[: -len(" - Discord")].lstrip("@#").strip()
        composer = self._composer(window)
        if composer:
            m = re.match(r"^(?:Conversar|Mensagem|Message)\s+(?:em|com|para)?\s*[@#]?(.+)$", composer.element_info.name or "")
            if m:
                return m.group(1).strip()
        return ""

    @staticmethod
    def _composer(window):
        return next(
            (e for e in window.descendants(control_type="Edit")
             if re.match(r"^(?:Conversar|Mensagem|Message)\b", e.element_info.name or "")),
            None,
        )

    def _open_chat(self, window, contact: str) -> str:
        from pywinauto.keyboard import send_keys

        if name_matches(self._current_chat(window), contact):
            return self._current_chat(window)
        # 1) Conversas diretas na barra lateral.
        dm_list = self._dm_list(window)
        items = dm_list.children(control_type="ListItem") if dm_list else []
        titles = [clean_discord_name(i.element_info.name or "") for i in items]
        index = pick_result(titles, contact, fuzzy=True)
        if index is not None:
            contact = titles[index]  # o nome escolhido (pode ter sido "parecido")
            link = items[index].descendants(control_type="Hyperlink")
            if link:
                link[0].invoke()  # sem mexer no rato
            else:
                items[index].click_input()
        else:
            # 2) Pesquisa rápida (Ctrl+K), como farias à mão.
            window.set_focus()
            send_keys("^k")
            time.sleep(0.6)
            _paste(contact)
            time.sleep(1.2)
            send_keys("{ENTER}")
        opened = _wait(lambda: name_matches(self._current_chat(window), contact) and self._current_chat(window), WAIT_UI_S)
        if not opened:
            current = self._current_chat(window) or "outra conversa"
            raise MessagingError(
                f"Não encontrei a conversa '{contact}' no Discord (ficou aberta: '{current}'). Não enviei nada."
            )
        return opened

    def read_messages(self, platform: str, contact: str, count: int = 10) -> str:
        window = self.window()
        title = self._open_chat(window, contact)
        messages_list = _wait(lambda: next(
            (l for l in window.descendants(control_type="List")
             if re.match(r"^(?:Mensagens em|Messages in)\b", l.element_info.name or "")), None), WAIT_UI_S)
        out, last_author = [], ""
        for item in (messages_list.children(control_type="ListItem") if messages_list else [])[-count:]:
            texts = [((t.element_info.name or ""), (t.element_info.automation_id or ""))
                     for t in item.descendants(control_type="Text")]
            author, content = parse_discord_message(texts)
            author = author or last_author
            last_author = author
            if content:
                out.append(ChatMessage(author=author, text=content))
        return f"Conversa: {title} (Discord)\n" + format_messages(out)

    def send_message(self, platform: str, contact: str, message: str, confirm=None) -> str | None:
        from pywinauto.keyboard import send_keys

        window = self.window()
        title = self._open_chat(window, contact)
        if confirm is not None:
            message = confirm(title)
            if not message:
                return None
        composer = _wait(lambda: self._composer(window), WAIT_UI_S)
        if not composer:
            raise MessagingError("Não encontrei a caixa de escrever do Discord. Não enviei nada.")
        _type_and_send(window, lambda: self._composer(window), message, "Discord")
        return f"Mensagem enviada para {title} no Discord."

    def unread_summary(self, limit: int = 5) -> str:
        """Mensagens por ler, separadas em amigos, grupos e servidores (sem abrir conversas)."""
        window = self._find_window()
        if window is None:
            window = self.window()  # abre o Discord se estiver fechado
            self.opened_by_jarvis = True
        home, servers, seen_servers = [], [], False
        tree = next(iter(window.descendants(control_type="Tree")), None)
        for group in tree.children() if tree else []:
            items = [t.element_info.name or "" for t in group.descendants(control_type="TreeItem")]
            if (group.element_info.name or "") in ("Servidores", "Servers"):
                servers, seen_servers = items, True
            elif not seen_servers:  # antes dos servidores: "Mensagens diretas" e as conversas por ler
                home += items
        dm_list = self._dm_list(window)
        dm_names = [i.element_info.name or "" for i in dm_list.descendants(control_type="ListItem")] if dm_list else []
        return format_discord_sections(discord_sections(home, servers, dm_names), limit)

    def close_if_opened(self) -> bool:
        """Fecha o Discord se foi o Jarvis que o abriu para ver as mensagens."""
        if not getattr(self, "opened_by_jarvis", False):
            return False
        self.opened_by_jarvis = False
        window = self._find_window()
        if window is not None:
            window.close()
        return True


_MENTIONS = re.compile(r"(\d[\d.]*)\s+men[çc](?:ão|ões|ao|oes|tions?)(?:\s+não\s+lidas?)?", re.IGNORECASE)
_HOME_NAMES = {"mensagens diretas", "direct messages"}


def _mentions(name: str) -> int:
    m = _MENTIONS.search(name)
    return int(m.group(1).replace(".", "")) if m else 0


def _strip_unread(name: str) -> str:
    name = re.sub(r"(?:Mensagens não lidas|Unread messages?)\s*,?\s*", "", name, flags=re.I)
    name = _MENTIONS.sub("", name)
    return clean_discord_name(name.strip(" ,"))


def discord_sections(home: list[str], servers: list[str], dm_names: list[str]) -> dict:
    """Barra lateral do Discord -> {"friends": [(nome, n)], "groups": [...], "servers": [...], "requests": n}.
    Mensagens diretas por ler aparecem como avatares junto de "Mensagens diretas"; os grupos têm
    "N membros" na lista de conversas; as pastas de servidores ("..., pasta") são ignoradas (os
    servidores lá dentro aparecem à parte)."""
    group_names = {clean_discord_name(n) for n in dm_names if re.search(r"\d+\s*membros?$", n)}
    friends, groups = [], []
    for name in home:
        if name.strip().lower() in _HOME_NAMES:
            continue
        who = _strip_unread(name)
        if not who:
            continue
        (groups if who in group_names or "," in who else friends).append((who, _mentions(name)))
    unread_servers = [
        (_strip_unread(n), _mentions(n)) for n in servers
        if "pasta" not in n and _DISCORD_UNREAD.search(n)
    ]
    requests = next((int(m.group(1)) for n in dm_names
                     if (m := re.match(r"(?:Solicitações de mensagens|Message Requests)\s*(\d+)", n))), 0)
    return {"friends": friends, "groups": groups, "servers": unread_servers, "requests": requests}


def format_discord_sections(sections: dict, limit: int = 5) -> str:
    def names(items):
        return ", ".join(f"{n} ({c})" if c else n for n, c in items[:limit])

    lines = ["Discord:"]
    lines.append(f"- 👤 Amigos: {names(sections['friends'])}" if sections["friends"]
                 else "- 👤 Nenhum amigo te mandou mensagem.")
    if sections["groups"]:
        lines.append(f"- 👥 Grupos: {names(sections['groups'])}")
    if sections["requests"]:
        lines.append(f"- ✉️ {sections['requests']} pedido(s) de mensagem de quem não é teu amigo.")
    servers = sections["servers"]
    if servers:
        top = sorted(servers, key=lambda s: s[1], reverse=True)
        lines.append(f"- 🌐 Comunidades: {len(servers)} servidores com mensagens por ler"
                     + (f" (mais menções: {names([s for s in top if s[1]])})" if top[0][1] else "") + ".")
    return "\n".join(lines)


# --- WhatsApp ----------------------------------------------------------------

_WA_TIME = re.compile(
    r"\s(?:\d{1,2}:\d{2}|ontem|hoje|segunda|terça|quarta|quinta|sexta|sábado|domingo|\d{2}/\d{2}/\d{4})\b", re.I
)


_WA_UNREAD = re.compile(r"\b\d+\s+(?:mensage(?:m|ns)\s+não\s+lidas?|unread\s+messages?)\s*", re.IGNORECASE)


def whatsapp_chat_name(item_name: str) -> str:
    """'A Princesa Sofia 💙 01:00 última mensagem' -> 'A Princesa Sofia 💙'."""
    item_name = _WA_UNREAD.sub("", item_name)
    m = _WA_TIME.search(item_name)
    return (item_name[: m.start()] if m else item_name).strip()


def whatsapp_preview(item_name: str) -> tuple[str, str, str]:
    """'Rafa 11:24 bora jogar?' -> ('Rafa', '11:24', 'bora jogar?')."""
    item_name = _WA_UNREAD.sub("", item_name)
    m = _WA_TIME.search(item_name)
    if not m:
        return item_name.strip(), "", ""
    for noise in ("Conversa afixada", "Conversa com estrela", "Conversa sem som"):
        item_name = item_name.replace(noise, "")
    return item_name[: m.start()].strip(), m.group(0).strip(), " ".join(item_name[m.end():].split())


_DISCORD_UNREAD = re.compile(r"mensage(?:m|ns) não lida|\d+\s+men[çc][ãõa]o|men[çc][õo]es", re.IGNORECASE)


def discord_unread(names: list[str]) -> list[str]:
    """Da barra lateral do Discord, os sítios com mensagens por ler (já com o nome limpo)."""
    out = []
    for name in names:
        if not _DISCORD_UNREAD.search(name):
            continue
        count = re.search(r"(\d+)\s+men[çc]", name)
        place = re.sub(r"^(?:Mensagens não lidas,\s*|\d+\s+men[çc][ãõa]o(?:es)?,?\s*)", "", name).strip()
        place = clean_discord_name(place) or name
        out.append(f"{place} ({count.group(1)} menções)" if count else place)
    return out


class WhatsAppDesktop(DesktopChat):
    name = "WhatsApp"
    app_id = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"

    def _find_window(self):
        from pywinauto import Desktop

        for w in Desktop(backend="uia").windows(class_name="WinUIDesktopWin32WindowClass"):
            if w.window_text().endswith("WhatsApp"):
                return w
        return None

    @staticmethod
    def _document(window, timeout: float = WAIT_UI_S):
        """A página do WhatsApp dentro da janela (espera que tenha conteúdo)."""
        def find():
            docs = window.descendants(control_type="Document")
            return docs[0] if docs and len(docs[0].children()) else None

        return _wait(find, timeout)

    def _ready(self, window) -> bool:
        doc = self._document(window, 0.3)
        return bool(doc and self._search_box(doc))

    @staticmethod
    def _search_box(doc):
        return next((e for e in doc.descendants(control_type="Edit")
                     if re.search(r"procurar|pesquisar|search", e.element_info.name or "", re.I)), None)

    @staticmethod
    def _composer(doc):
        return next((e for e in doc.descendants(control_type="Edit")
                     if re.search(r"mensagem|message", e.element_info.name or "", re.I)
                     and not re.search(r"procurar|pesquisar|search", e.element_info.name or "", re.I)), None)

    @staticmethod
    def _chat_list(doc):
        return next((g for g in doc.descendants(control_type="DataGrid")), None)

    def _header_names(self, doc) -> list[str]:
        """Textos no topo do painel da conversa (à direita da lista), onde está o nome."""
        chat_list = self._chat_list(doc)
        composer = self._composer(doc)
        if not composer:
            return []
        left = chat_list.rectangle().right if chat_list else 0
        top = doc.rectangle().top
        names = []
        for e in doc.descendants():
            r = e.rectangle()
            if r.left >= left and r.top < top + 110 and e.element_info.name:
                names.append(e.element_info.name)
        return names

    def _current_chat(self, doc, contact: str) -> str:
        return next((n for n in self._header_names(doc) if name_matches(n, contact)), "")

    def _open_chat(self, window, contact: str) -> str:
        from pywinauto.keyboard import send_keys

        doc = self._document(window)
        current = self._current_chat(doc, contact)
        if current:
            return current
        search = self._search_box(doc)
        # Nome completo; se o reconhecimento de voz o ouviu mal e não aparece nada,
        # tenta só a primeira palavra e depois as primeiras letras.
        first = contact.split()[0] if contact.split() else contact
        index, items, titles = None, [], []
        for term in dict.fromkeys([contact, first, first[:4]]):
            if len(term) < 3:
                continue
            search.set_focus()
            send_keys("^a{BACKSPACE}")
            _paste(term)
            time.sleep(1.5)
            chat_list = self._chat_list(doc)
            items = chat_list.children(control_type="DataItem") if chat_list else []
            titles = [whatsapp_chat_name(i.element_info.name or "") for i in items]
            index = pick_result(titles, contact, fuzzy=True)
            if index is not None:
                break
        if index is None:
            found = ", ".join(t for t in titles[:5] if t)
            send_keys("{ESC}")
            raise MessagingError(
                f"Não encontrei a conversa '{contact}' no WhatsApp." + (f" Encontrei: {found}." if found else "")
            )
        contact = titles[index]  # o nome escolhido (pode ter sido "parecido")
        items[index].click_input()
        opened = _wait(lambda: self._current_chat(self._document(window, 0.5), contact), WAIT_UI_S)
        if not opened:
            raise MessagingError(
                f"Não consegui confirmar que a conversa aberta no WhatsApp é a de '{contact}'. Não enviei nada."
            )
        return whatsapp_chat_name(opened)

    def _messages_in_open_chat(self, window, count: int) -> list[ChatMessage]:
        """As linhas do painel da conversa, entre o cabeçalho e a caixa de escrever."""
        doc = self._document(window)
        composer = self._composer(doc)
        chat_list = self._chat_list(doc)
        left = chat_list.rectangle().right if chat_list else 0
        top, bottom = doc.rectangle().top + 110, composer.rectangle().top if composer else doc.rectangle().bottom
        rows = [
            e for e in doc.descendants(control_type="DataItem") + doc.descendants(control_type="ListItem")
            if e.rectangle().left >= left and top <= e.rectangle().top < bottom and e.element_info.name
        ]
        seen, messages = set(), []
        for row in rows:
            text = " ".join((row.element_info.name or "").split())
            if text and text not in seen:
                seen.add(text)
                messages.append(ChatMessage(author="", text=text))
        return messages[-count:]

    def read_messages(self, platform: str, contact: str, count: int = 10) -> str:
        window = self.window()
        title = self._open_chat(window, contact)
        return f"Conversa: {title} (WhatsApp)\n" + format_messages(self._messages_in_open_chat(window, count))

    def _set_filter(self, doc, which: str) -> bool:
        """Carrega num filtro da lista de conversas: 'all-filter' (Tudo) ou 'label_item_1' (Não lidas)."""
        names = {"all-filter": "Tudo", "label_item_1": "Não lidas"}
        tab = next((t for t in doc.descendants(control_type="TabItem")
                    if t.element_info.automation_id == which or t.element_info.name == names.get(which)), None)
        if tab is None:
            return False
        try:
            tab.select()
        except Exception:
            tab.click_input()
        time.sleep(1.0)
        return True

    def open_latest_unread(self, window) -> tuple[str, bool]:
        """Abre a conversa não lida mais recente (filtro "Não lidas"). Sem não lidas, abre a
        conversa mais recente da lista. Devolve (nome, era_não_lida)."""
        doc = self._document(window)
        unread = self._set_filter(doc, "label_item_1")
        try:
            items = self._chat_list(doc).children(control_type="DataItem") if self._chat_list(doc) else []
            was_unread = bool(unread and items)
            if not was_unread:
                if unread:
                    self._set_filter(doc, "all-filter")
                items = self._chat_list(doc).children(control_type="DataItem") if self._chat_list(doc) else []
            if not items:
                raise MessagingError("Não encontrei conversas no WhatsApp.")
            title = whatsapp_chat_name(items[0].element_info.name or "")
            items[0].click_input()
            if not _wait(lambda: self._current_chat(self._document(window, 0.5), title), WAIT_UI_S):
                raise MessagingError("Não consegui confirmar que conversa abri no WhatsApp. Não enviei nada.")
            return title, was_unread
        finally:
            if unread:
                self._set_filter(self._document(window), "all-filter")  # deixa a lista como estava

    def unread_summary(self, limit: int = 5) -> str:
        """As conversas por ler (filtro "Não lidas"), sem as abrir: nome, hora e início da mensagem."""
        window = self.window()
        doc = self._document(window)
        if not self._set_filter(doc, "label_item_1"):
            return "WhatsApp: não encontrei o filtro 'Não lidas'."
        try:
            chat_list = self._chat_list(doc)
            items = chat_list.children(control_type="DataItem") if chat_list else []
            previews = [whatsapp_preview(i.element_info.name or "") for i in items[:limit]]
        finally:
            self._set_filter(self._document(window), "all-filter")
        if not previews:
            return "WhatsApp: não tens mensagens por ler."
        lines = [f"WhatsApp ({len(previews)} por ler):"]
        lines += [f"- {name} ({time_}): {text[:80]}" if text else f"- {name} ({time_})" for name, time_, text in previews]
        return "\n".join(lines)

    def reply_latest(self, message: str = "", compose=None, confirm=None) -> str | None:
        """Responde na conversa não lida mais recente. Sem `message`, `compose(nome, mensagens)`
        escreve a resposta; `confirm(plataforma, nome, texto)` pode mostrá-la antes de enviar."""
        from pywinauto.keyboard import send_keys

        window = self.window()
        title, was_unread = self.open_latest_unread(window)
        messages = self._messages_in_open_chat(window, 12)
        if not messages:
            raise MessagingError(f"Abri a conversa com {title} mas não consegui ler as mensagens. Não enviei nada.")
        if not message:
            if compose is None:
                raise MessagingError("Não sei o que responder: diz-me o texto.")
            message = compose(title, format_messages(messages))
        if confirm is not None:
            message = confirm("WhatsApp", title, message)
            if not message:
                return None
        _type_and_send(window, lambda: self._composer(self._document(window, 0.5)), message, "WhatsApp")
        where = "(tinha mensagens por ler)" if was_unread else "(não havia conversas por ler: respondi na mais recente)"
        return f"Respondi a {title} no WhatsApp {where}. Texto enviado: \"{message}\""

    def send_message(self, platform: str, contact: str, message: str, confirm=None) -> str | None:
        from pywinauto.keyboard import send_keys

        window = self.window()
        title = self._open_chat(window, contact)
        if confirm is not None:
            message = confirm(title)
            if not message:
                return None
        _type_and_send(window, lambda: self._composer(self._document(window, 0.5)), message, "WhatsApp")
        return f"Mensagem enviada para {title} no WhatsApp."


class ChatRouter:
    """Escolhe, por plataforma, a app de desktop (se estiver instalada) ou a versão web."""

    DESKTOP = {"whatsapp": WhatsAppDesktop, "discord": DiscordDesktop}

    def __init__(self, web, mode: str = "auto", installed=None):
        self.web = web
        self.mode = mode
        self._installed = installed  # para testes: set de app_ids instalados
        self._desktop: dict[str, DesktopChat] = {}

    def _desktop_installed(self, cls) -> bool:
        if self._installed is not None:
            return cls.app_id in self._installed
        from jarvis.actions.system import list_start_apps

        return any(app_id == cls.app_id for _, app_id in list_start_apps())

    def backend(self, platform: str):
        key = platform.strip().lower()
        cls = self.DESKTOP.get(key)
        if cls and self.mode != "web" and (self.mode == "desktop" or self._desktop_installed(cls)):
            return self._desktop.setdefault(key, cls())
        return self.web

    def read_messages(self, platform: str, contact: str, count: int = 10) -> str:
        return self.backend(platform).read_messages(platform, contact, count)

    def send_message(self, platform: str, contact: str, message: str, confirm=None) -> str | None:
        backend = self.backend(platform)
        if backend is self.web:
            return backend.send_message(platform, contact, message, confirm=confirm)
        with keep_user_context():  # no fim, o jogo volta à frente e o rato fica onde estava
            return backend.send_message(platform, contact, message, confirm=confirm)

    def check_messages(self, limit: int = 5) -> str:
        """Mensagens por ler no WhatsApp e no Discord (apps de desktop): quem, o quê e onde."""
        parts = []
        wa = self.backend("whatsapp")
        if isinstance(wa, WhatsAppDesktop):
            try:
                parts.append(wa.unread_summary(limit))
            except Exception as exc:
                parts.append(f"WhatsApp: não consegui ver ({exc}).")
        dc = self.backend("discord")
        if isinstance(dc, DiscordDesktop):
            try:
                parts.append(dc.unread_summary(limit))
            except Exception as exc:
                parts.append(f"Discord: não consegui ver ({exc}).")
            try:
                if dc.close_if_opened():
                    parts.append("(fechei o Discord outra vez)")
            except Exception:
                pass
        if not parts:
            return "Não encontrei o WhatsApp nem o Discord de desktop instalados."
        return "\n".join(parts)

    def reply_latest(self, platform: str, message: str = "", compose=None, confirm=None) -> str | None:
        backend = self.backend(platform)
        if not hasattr(backend, "reply_latest"):
            raise MessagingError(f"Responder à última mensagem ainda só funciona no WhatsApp de desktop.")
        with keep_user_context():
            return backend.reply_latest(message, compose=compose, confirm=confirm)

    def close(self):
        self.web.close()
