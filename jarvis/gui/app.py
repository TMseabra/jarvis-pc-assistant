"""Janela do Jarvis com o HUD (círculo animado, conversa, botão Parar).

A página (index.html) corre num WebView2 (pywebview). `GuiUI` tem os mesmos métodos que a
`UI` do terminal, por isso o resto do Jarvis (main.py) funciona igual nos dois.
"""

import itertools
import json
import queue
import threading
from contextlib import contextmanager
from pathlib import Path

from jarvis.llm import ToolCall, ToolResult
from jarvis.log import log
from jarvis.ui import _ICONS, tool_label

PAGE = Path(__file__).with_name("index.html")


def state_for(text: str) -> str:
    """Texto de estado do main.py -> estado do HUD."""
    low = text.lower()
    if "a gravar" in low:
        return "recording"
    if "escuta" in low or "🎤" in text or "fala quando" in low:
        return "listening"
    if "a falar" in low:
        return "speaking"
    return "thinking"


class _Console:
    """O main.py usa ui.console.print() ao sair; na janela não há consola."""

    is_terminal = False

    def print(self, *args, **kwargs):
        pass


class GuiUI:
    def __init__(self):
        self.window = None
        self.console = _Console()
        self.commands: queue.Queue = queue.Queue()
        self.mic_on = True
        self.cancel = threading.Event()  # botão Parar / Esc
        self.closed = threading.Event()
        self._ready = threading.Event()
        self._pending: list[dict] = []
        self._answers: dict[str, queue.Queue] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._states: list[tuple[str, str]] = []

    # --- ligação à página -------------------------------------------------------

    def emit(self, **event):
        with self._lock:
            if not self._ready.is_set() or self.window is None:
                self._pending.append(event)
                return
        try:
            self.window.evaluate_js(f"window.J && J.event({json.dumps(event, ensure_ascii=False)})")
        except Exception as exc:  # janela a fechar
            log.debug("gui: %s", exc)

    def page_ready(self):
        with self._lock:
            self._ready.set()
            pending, self._pending = self._pending, []
        for event in pending:
            self.emit(**event)

    # --- entrada ---------------------------------------------------------------

    def submit(self, text: str, voice: bool = False):
        self.commands.put((text, voice))

    def next_command(self, timeout: float = 0.5) -> tuple[str, bool] | None:
        try:
            return self.commands.get(timeout=timeout)
        except queue.Empty:
            return None

    def set_mic(self, on: bool):
        self.mic_on = on
        self.emit(type="mic", on=on)
        self.emit(type="state", state="listening" if on else "idle", detail="" if on else "microfone desligado")

    # --- a mesma interface da UI do terminal --------------------------------------

    def banner(self, details: list[tuple[str, str]]):
        self.emit(type="chips", items=[[k, v] for k, v in details])
        self.emit(type="sys", text="sistemas online")

    def choose_mode(self) -> str:
        return "janela"

    def help(self, mode: str):
        pass

    def ask(self) -> str:
        item = None
        while item is None and not self.closed.is_set():
            item = self.next_command()
        return item[0] if item else "sair"

    def heard(self, text: str):
        self.emit(type="user", text=text, voice=True)

    def typed(self, text: str):
        self.emit(type="user", text=text, voice=False)

    def reply(self, text: str, seconds: float | None = None):
        self.emit(type="reply", text=text, seconds=seconds)

    def tool(self, call: ToolCall):
        self.emit(type="action", icon=_ICONS.get(call.name, "⚙").strip(), label=tool_label(call))

    def tool_result(self, result: ToolResult):
        first = result.content.split("\n", 1)[0]
        if first.startswith("<mensagens_recebidas>"):
            first = "mensagens lidas"
        self.emit(type="result", ok=not result.is_error, text=first[:160])

    def verification(self, check):
        failures = [f.content.splitlines()[0][:120] for f in check.failures]
        self.emit(type="check", ok=check.ok, text=check.ui_line(), failures=failures)

    def info(self, text: str):
        self.emit(type="note", text=text)

    def error(self, text: str):
        self.emit(type="note", text="✖ " + text, error=True)

    @contextmanager
    def status(self, text: str, spinner: str = ""):
        self._states.append((state_for(text), text))
        self.emit(type="state", state=state_for(text), detail=_clean(text))
        try:
            yield
        finally:
            self._states.pop()
            state, detail = self._states[-1] if self._states else ("idle", "")
            self.emit(type="state", state=state if self._states else self._rest_state(), detail=_clean(detail))

    def _rest_state(self) -> str:
        return "listening" if self.mic_on and getattr(self, "voice_enabled", False) else "idle"

    def update_status(self, text: str):
        self.emit(type="state", state=state_for(text), detail=_clean(text))

    @contextmanager
    def paused_status(self):
        yield

    def confirm_send(self, platform: str, contact: str, message: str) -> str | None:
        key = str(next(self._ids))
        answer: queue.Queue = queue.Queue()
        self._answers[key] = answer
        self.emit(type="confirm", id=key, question=f"💬 Enviar a {contact} ({platform})?", message=message)
        try:
            text = answer.get(timeout=300)
        except queue.Empty:
            text = ""
        finally:
            self._answers.pop(key, None)
        if not text:
            self.info("Envio cancelado.")
        return text or None

    def answer(self, key: str, text: str):
        if key in self._answers:
            self._answers[key].put(text)


def _clean(text: str) -> str:
    return text.replace("🎤", "").strip()


class Api:
    """Funções que a página chama (window.pywebview.api.*)."""

    def __init__(self, ui: GuiUI):
        self._ui = ui

    def ready(self):
        self._ui.page_ready()

    def send(self, text: str):
        self._ui.submit(text)

    def stop(self):
        from jarvis.voice import stop_speaking

        self._ui.cancel.set()
        stop_speaking()
        self._ui.emit(type="note", text="■ Parado. Diz ou escreve o próximo pedido.")

    def toggle_mic(self):
        self._ui.set_mic(not self._ui.mic_on)

    def answer(self, key: str, text: str):
        self._ui.answer(key, text)

    def open_link(self, url: str):
        from jarvis.actions.system import open_url

        open_url(url)


def run_gui(session) -> int:
    """Abre a janela e corre `session(ui)` (o ciclo do Jarvis) numa thread à parte."""
    import webview

    ui = GuiUI()
    api = Api(ui)
    ui.window = webview.create_window(
        "J.A.R.V.I.S.", str(PAGE), js_api=api, width=1280, height=800, min_size=(900, 600),
        background_color="#02070d", text_select=True,
    )
    result = {"code": 0}

    def worker():
        try:
            result["code"] = session(ui) or 0
        except Exception:
            log.exception("gui: o Jarvis parou com um erro")
            ui.error("O Jarvis parou com um erro (vê .jarvis/jarvis.log).")
            result["code"] = 1

    def on_closed():
        ui.closed.set()
        ui.submit("sair")

    ui.window.events.closed += on_closed
    webview.start(worker, private_mode=False)
    return result["code"]
