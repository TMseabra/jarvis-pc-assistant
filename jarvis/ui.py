"""Interface de terminal com rich."""

from contextlib import contextmanager

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from jarvis.actions.messaging import PLATFORMS
from jarvis.llm import ToolCall

ACCENT = "cyan"
USER = "bold magenta"

MODES = {
    "1": ("texto", "Escrever", "escreves os pedidos, respostas em texto"),
    "2": ("falar", "Falar", "Enter para falar (ou escreve), respostas faladas"),
    "3": ("maos-livres", "Mãos-livres", "ouve sempre, respostas faladas"),
}

_LOGO = r"""
     ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
     ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
     ██║███████║██████╔╝██║   ██║██║███████╗
██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
 ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝"""


def tool_label(call: ToolCall) -> str:
    a = call.args
    key = str(a.get("platform", "")).lower()
    platform = PLATFORMS[key].name if key in PLATFORMS else key
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
    }
    return labels.get(call.name, call.name)


class UI:
    def __init__(self, console: Console | None = None):
        self.console = console or Console(highlight=False)
        self._status = None

    # --- ecrã inicial --------------------------------------------------------

    def banner(self, details: list[tuple[str, str]]):
        self.console.clear()
        logo = Text(_LOGO.strip("\n"), style=f"bold {ACCENT}")
        subtitle = Text("assistente pessoal do PC", style="dim italic")
        info = Table.grid(padding=(0, 2))
        info.add_column(style="dim", justify="right")
        info.add_column()
        for key, value in details:
            info.add_row(key, value)
        self.console.print(
            Panel(
                Group(Align.center(logo), Align.center(subtitle), Text(), Align.center(info)),
                border_style=ACCENT,
                padding=(1, 4),
            )
        )

    def choose_mode(self) -> str:
        table = Table.grid(padding=(0, 2))
        for key, (_, name, desc) in MODES.items():
            table.add_row(f"[bold {ACCENT}]{key}[/]", f"[bold]{name}[/]", f"[dim]{desc}[/]")
        self.console.print(Panel(table, title="Como queres falar comigo?", title_align="left", border_style="dim"))
        choice = Prompt.ask("Modo", choices=list(MODES), default="1", console=self.console)
        return MODES[choice][0]

    def help(self, mode: str):
        tips = ["[bold]sair[/] para terminar", "[bold]esquece[/] para começar uma conversa nova"]
        if mode == "falar":
            tips.insert(0, "[bold]Enter[/] vazio para falar")
        elif mode == "maos-livres":
            tips.insert(0, "começa cada pedido por [bold]“Jarvis, …”[/]")
            tips[-2] = "[bold]“Jarvis, sair”[/] para terminar"
        self.console.print("  " + "  ·  ".join(tips), style="dim")
        self.console.rule(style="dim")

    # --- conversa ------------------------------------------------------------

    def ask(self) -> str:
        return self.console.input(f"\n[{USER}]Tu ›[/] ").strip()

    def heard(self, text: str):
        self.console.print(f"\n[{USER}]Tu ›[/] {text}  [dim](voz)[/]")

    def reply(self, text: str):
        self.console.print(
            Panel(text, title=f"[bold {ACCENT}]Jarvis[/]", title_align="left", border_style=ACCENT, padding=(0, 1))
        )

    def tool(self, call: ToolCall):
        self.console.print(f"  [dim]⚙ {tool_label(call)}…[/]")

    def info(self, text: str):
        self.console.print(f"  [yellow]ℹ {text}[/]")

    def error(self, text: str):
        self.console.print(Panel(text, title="[bold red]Erro[/]", title_align="left", border_style="red"))

    @contextmanager
    def status(self, text: str, spinner: str = "dots"):
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
            self.console.print(
                Panel(
                    Text(message, style="bold"),
                    title=f"[bold yellow]Enviar a {contact} ({platform})?[/]",
                    title_align="left",
                    border_style="yellow",
                    padding=(0, 1),
                )
            )
            answer = Prompt.ask(
                "[yellow][s][/] enviar  [yellow][e][/] editar  [yellow][n][/] cancelar",
                choices=["s", "e", "n"],
                default="n",
                show_choices=False,
                console=self.console,
            )
            if answer == "e":
                edited = self.console.input("[yellow]Texto a enviar ›[/] ").strip()
                return edited or None
            if answer == "s":
                return message
            self.info("Envio cancelado.")
            return None
