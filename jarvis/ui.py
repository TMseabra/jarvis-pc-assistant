"""Interface de terminal com rich."""

from contextlib import contextmanager

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from jarvis.actions.messaging import PLATFORMS
from jarvis.llm import ToolCall, ToolResult

ACCENT = "cyan"
USER = "bold magenta"
MAX_WIDTH = 92
# Degradé do logótipo, de cima para baixo.
_GRADIENT = ["#00e5ff", "#00c8ff", "#1aa3ff", "#4d7dff", "#7a5cff", "#a64dff"]

MODES = {
    "1": ("texto", "⌨  Escrever", "escreves os pedidos, respostas em texto"),
    "2": ("falar", "🎙  Falar", "Enter para falar e Enter para terminar, respostas faladas"),
    "3": ("maos-livres", "👂 Mãos-livres", "ouve sempre; começa por “Jarvis, …”"),
}
MODE_NAMES = {key: name for key, name, _ in MODES.values()}

_LOGO = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"""

_ICONS = {
    "open_app": "🚀", "open_website": "🌐", "web_search": "🔎", "play_video": "▶️ ",
    "music": "🎵", "open_project": "💻", "read_messages": "📨", "send_message": "💬",
    "ask_ai": "🎨", "open_path": "📁",
}


def tool_label(call: ToolCall) -> str:
    a = call.args
    key = str(a.get("platform", "")).lower()
    platform = PLATFORMS[key].name if key in PLATFORMS else key
    ai_site = {"image": "ChatGPT", "code": "Claude"}.get(str(a.get("kind", "")), "ChatGPT")
    if str(a.get("site", "")).lower() in ("claude", "chatgpt"):
        ai_site = "Claude" if str(a.get("site")).lower() == "claude" else "ChatGPT"
    labels = {
        "open_app": f"A abrir {a.get('name', '')}",
        "open_website": f"A abrir {a.get('url', '')}",
        "web_search": f"A pesquisar “{a.get('query', '')}”",
        "play_video": f"A procurar “{a.get('query', '')}” no "
        + ("TikTok" if str(a.get("site", "")).lower() == "tiktok" else "YouTube"),
        "music": f"Spotify: {a.get('action', '')} {a.get('query', '')}".strip(),
        "open_project": f"A abrir o projeto {a.get('name', '')} no VS Code"
        + (" e a passar o pedido ao Claude" if a.get("claude_prompt") else ""),
        "read_messages": f"A ler as mensagens de {a.get('contact', '')} no {platform}",
        "send_message": f"A abrir a conversa com {a.get('contact', '')} no {platform}",
        "ask_ai": f"A pedir ao {ai_site}: “{a.get('task', '')}”",
        "open_path": f"A abrir {a.get('name', '')}",
    }
    return labels.get(call.name, call.name)


def _logo() -> Text:
    text = Text()
    for i, line in enumerate(_LOGO.strip("\n").splitlines()):
        text.append(line + "\n", style=f"bold {_GRADIENT[i % len(_GRADIENT)]}")
    text.rstrip()
    return text


class UI:
    def __init__(self, console: Console | None = None):
        self.console = console or Console(highlight=False)
        self._status = None

    @property
    def width(self) -> int:
        return min(self.console.width, MAX_WIDTH)

    # --- ecrã inicial --------------------------------------------------------

    def banner(self, details: list[tuple[str, str]]):
        self.console.clear()
        chips = Text(justify="center")
        for i, (key, value) in enumerate(details):
            if i:
                chips.append("   ")
            chips.append(f" {key} ", style="bold black on #1aa3ff")
            chips.append(f" {value} ", style="white on grey23")
        self.console.print(Align.center(Panel(
            Group(
                Align.center(_logo()),
                Align.center(Text("assistente pessoal do PC", style="italic #7a8ba8")),
                Text(),
                Align.center(chips),
            ),
            box=box.HEAVY, border_style="#1aa3ff", padding=(1, 3), width=self.width,
        )))

    def choose_mode(self) -> str:
        table = Table.grid(padding=(0, 2))
        for key, (_, name, desc) in MODES.items():
            table.add_row(f"[bold black on #1aa3ff] {key} [/]", f"[bold]{name}[/]", f"[#7a8ba8]{desc}[/]")
        self.console.print(Align.center(Panel(
            table, title="[bold]Como queres falar comigo?[/]", title_align="left",
            box=box.ROUNDED, border_style="grey39", width=self.width, padding=(1, 2),
        )))
        choice = Prompt.ask("  [bold #1aa3ff]Modo[/]", choices=list(MODES), default="1", console=self.console)
        return MODES[choice][0]

    def help(self, mode: str):
        tips = [("sair", "terminar"), ("esquece", "conversa nova")]
        if mode == "falar":
            tips.insert(0, ("Enter", "falar / terminar"))
        elif mode == "maos-livres":
            tips = [("Jarvis, …", "fazer um pedido"), ("Jarvis, sair", "terminar")]
        line = Text("  ")
        for i, (key, desc) in enumerate(tips):
            if i:
                line.append("   ")
            line.append(f" {key} ", style="bold black on grey70")
            line.append(f" {desc}", style="#7a8ba8")
        self.console.print(line)
        self.console.print(Text(f"  modo: {MODE_NAMES.get(mode, mode)}", style="#7a8ba8"))
        self.console.rule(style="grey23")

    # --- conversa ------------------------------------------------------------

    def ask(self) -> str:
        text = self.console.input(f"\n[{USER}]  Tu ›[/] ").strip()
        if text and self.console.is_terminal:
            # Troca a linha escrita pela bolha, para a conversa ficar limpa.
            self.console.file.write("\x1b[1A\x1b[2K")
            self.console.file.flush()
            self._user_bubble(text)
        return text

    def heard(self, text: str):
        self._user_bubble(text, voice=True)

    def _user_bubble(self, text: str, voice: bool = False):
        title = "[bold magenta]Tu[/]" + (" [#7a8ba8]🎙[/]" if voice else "")
        bubble = Panel(Text(text), title=title, title_align="right", box=box.ROUNDED,
                       border_style="magenta", padding=(0, 1), expand=False)
        self.console.print(Align.right(bubble, width=self.width))

    def reply(self, text: str, seconds: float | None = None):
        subtitle = f"[#7a8ba8]{seconds:.1f}s[/]" if seconds is not None else None
        bubble = Panel(Text(text), title=f"[bold {ACCENT}]◉ Jarvis[/]", title_align="left",
                       subtitle=subtitle, subtitle_align="right", box=box.ROUNDED,
                       border_style=ACCENT, padding=(0, 1), expand=False)
        self.console.print(Align.left(bubble, width=self.width))

    def tool(self, call: ToolCall):
        icon = _ICONS.get(call.name, "⚙")
        self.console.print(Text.assemble(("  ", ""), (f"{icon} ", ""), (tool_label(call) + "…", "#9fb3c8")))

    def tool_result(self, result: ToolResult):
        mark, style = ("✖", "red") if result.is_error else ("✔", "green")
        first_line = result.content.split("\n", 1)[0]
        if first_line.startswith("<mensagens_recebidas>"):
            first_line = "mensagens lidas"
        self.console.print(Text.assemble(("     ", ""), (f"{mark} ", f"bold {style}"),
                                         (first_line[:110], "grey62" if not result.is_error else "red")))

    def verification(self, check):
        style, mark = ("green", "✔") if check.ok else ("yellow", "⚠")
        line = Text.assemble(("  ", ""), (f"{mark} ", f"bold {style}"), (check.ui_line(), style))
        for failure in check.failures:
            line.append(f"\n     ✖ {failure.content.splitlines()[0][:100]}", style="red")
        self.console.print(line)

    def info(self, text: str):
        self.console.print(f"  [yellow]ℹ {text}[/]")

    def error(self, text: str):
        self.console.print(Align.left(Panel(Text(text), title="[bold red]✖ Erro[/]", title_align="left",
                                            box=box.ROUNDED, border_style="red", expand=False), width=self.width))

    @contextmanager
    def status(self, text: str, spinner: str = "dots12"):
        previous = self._status
        self._status = self.console.status(f"[{ACCENT}]{text}[/]", spinner=spinner, spinner_style=ACCENT)
        self._status.start()
        try:
            yield
        finally:
            self._status.stop()
            self._status = previous

    def update_status(self, text: str):
        if self._status:
            self._status.update(f"[{ACCENT}]{text}[/]")

    @contextmanager
    def paused_status(self):
        """Para o spinner enquanto se pede alguma coisa ao utilizador."""
        status = self._status
        if status:
            status.stop()
        try:
            yield
        finally:
            if status:
                status.start()

    # --- confirmação de envio ------------------------------------------------

    def confirm_send(self, platform: str, contact: str, message: str) -> str | None:
        with self.paused_status():
            self.console.print(Align.left(Panel(
                Text(message, style="bold"),
                title=f"[bold yellow]💬 Enviar a {contact} ({platform})?[/]",
                title_align="left", box=box.ROUNDED, border_style="yellow", padding=(0, 1), expand=False,
            ), width=self.width))
            answer = Prompt.ask(
                "  [yellow][s][/] enviar  [yellow][e][/] editar  [yellow][n][/] cancelar",
                choices=["s", "e", "n"], default="n", show_choices=False, console=self.console,
            )
            if answer == "e":
                edited = self.console.input("  [yellow]Texto a enviar ›[/] ").strip()
                return edited or None
            if answer == "s":
                return message
            self.info("Envio cancelado.")
            return None
