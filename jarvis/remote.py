"""Pedidos vindos do Telegram: executa-os no PC e responde no chat com o resultado."""

import os
import sys
import threading

from jarvis import guard
from jarvis.actions.desktop_chat import ChatRouter
from jarvis.actions.screen import attachments
from jarvis.actions.messaging import Messenger
from jarvis.brain import Brain
from jarvis.commands import split_commands
from jarvis.config import PROJECT_ROOT, config
from jarvis.llm import LLMError, ToolCall, ToolResult
from jarvis.log import log
from jarvis.telegram_bot import TelegramAPI, TelegramBot, is_sensitive, parse_allowed_ids
from jarvis.tools import ToolExecutor
from jarvis.ui import tool_label
from jarvis.verify import verify

LOCK_FILE = PROJECT_ROOT / ".jarvis" / "telegram.lock"


def telegram_configured() -> bool:
    return bool(config.telegram_token and parse_allowed_ids(config.telegram_allowed_ids))


def format_reply(answers: list[str], results: list[ToolResult]) -> str:
    lines = [" ".join(answers).strip() or "Feito."]
    check = verify(results)
    if check:
        lines.append("")
        for r in results:
            mark = "❌" if r in check.failures else "✅"
            lines.append(f"{mark} {r.content.splitlines()[0][:150]}")
        lines.append("")
        lines.append(("✔️ " if check.ok else "⚠️ ") + check.ui_line())
    return "\n".join(lines)


class TelegramController:
    def __init__(self, api=None, ui=None):
        self.ui = ui
        self.results: list[ToolResult] = []
        self._chat: int | None = None
        api = api or TelegramAPI(config.telegram_token)
        self.bot = TelegramBot(api, parse_allowed_ids(config.telegram_allowed_ids), self.handle)
        executor = ToolExecutor(
            messenger=ChatRouter(Messenger(config.browser_profile, notify=log.info), config.messaging),
            confirm=None,
        )
        self.brain = Brain(executor=executor, on_tool=self._on_tool, on_tool_result=self._on_result,
                           approve=self._approve)
        if config.confirm_ai_replies:
            executor.confirm_ai = self._confirm_reply
        self.guard_chat: int | None = None  # onde avisar se o code red bloquear o PC
        guard.instance.listeners.append(self._on_code_red)

    def _on_tool(self, call: ToolCall):
        if self.ui:
            self.ui.tool(call)

    def _on_result(self, result: ToolResult):
        self.results.append(result)
        if self.ui:
            self.ui.tool_result(result)

    def _approve(self, call: ToolCall) -> bool:
        if not is_sensitive(call.name, call.args) or self._chat is None:
            return True
        return self.bot.confirm(self._chat, f"Confirmas? {tool_label(call)}")

    def _confirm_reply(self, platform: str, contact: str, message: str) -> str | None:
        if self._chat is None:
            return None
        ok = self.bot.confirm(self._chat, "\n".join([f"Responder a {contact} ({platform}) com:", f"«{message}»"]))
        return message if ok else None

    def _on_code_red(self):
        if self.guard_chat is not None:
            try:
                self.bot.send(self.guard_chat, "🚨 Code red: alguém mexeu no teclado ou no rato. Bloqueei o PC.")
            except Exception as exc:
                log.warning("Telegram: não avisei do code red: %s", exc)

    def handle(self, text: str, chat: int) -> str:
        log.info("telegram: %r", text)
        if guard.parse(text) == "arm":
            self.guard_chat = chat
        if self.ui:
            self.ui.info(f"📱 Pedido pelo Telegram: {text}")
        self._chat = chat
        self.results.clear()
        answers = []
        for part in split_commands(text):
            try:
                answers.append(self.brain.handle(part))
            except LLMError as exc:
                answers.append(f"Erro do modelo: {exc}")
                break
        reply = format_reply(answers, self.results)
        log.info("telegram resposta: %r", reply)
        # Ficheiros criados pelas ferramentas (prints do ecrã, ...) vão para o chat.
        for result in self.results:
            for path in attachments(result.content):
                try:
                    self.bot.api.send_file(chat, path, caption=path.name)
                except Exception as exc:
                    log.warning("Telegram: não enviei %s: %s", path, exc)
                    reply += f"\n⚠️ Não consegui enviar {path.name}: {exc}"
        return reply

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.bot.run, daemon=True, name="telegram")
        thread.start()
        return thread


# --- um só leitor do bot de cada vez (o Telegram não deixa dois) ------------------

def _process_alive(pid: int) -> bool:
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import win32api
    import win32con
    import win32process

    try:
        handle = win32api.OpenProcess(win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except Exception:
        return False
    try:
        return win32process.GetExitCodeProcess(handle) == 259  # STILL_ACTIVE
    finally:
        win32api.CloseHandle(handle)


def claim_bot() -> bool:
    """True se este processo pode ler o bot (nenhum outro Jarvis o está a fazer)."""
    try:
        pid = int(LOCK_FILE.read_text().strip())
        if pid != os.getpid() and _process_alive(pid):
            return False
    except (OSError, ValueError):
        pass
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def run_service() -> int:
    """`--servico`: só o bot do Telegram, sem janela nem voz (para correr sempre em segundo plano)."""
    if not telegram_configured():
        log.error("Telegram não configurado: corre Jarvis.bat --telegram")
        return 1
    if not claim_bot():
        log.info("Já há outro Jarvis a ler o Telegram: este serviço não arranca.")
        return 0
    log.info("=== serviço do Telegram a correr (pid %s)", os.getpid())
    controller = TelegramController()
    controller.bot.run()
    return 0
