"""`Jarvis.bat --telegram`: liga o Jarvis ao teu bot do Telegram, passo a passo."""

import re
import subprocess
import time

from rich.console import Console
from rich.prompt import Confirm, Prompt

from jarvis.config import PROJECT_ROOT
from jarvis.telegram_bot import TelegramAPI

ENV_FILE = PROJECT_ROOT / ".env"


def write_env(key: str, value: str, path=ENV_FILE):
    """Atualiza (ou acrescenta) KEY=value no .env, sem mexer no resto."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pattern = re.compile(rf"^\s*#?\s*{re.escape(key)}\s*=")
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def wait_for_first_message(api, timeout: float = 180) -> dict | None:
    """Espera pela 1.ª mensagem enviada ao bot e devolve o remetente."""
    offset = 0
    # Ignora mensagens antigas que já estejam na fila.
    old = api.call("getUpdates", timeout=0)
    if old:
        offset = old[-1]["update_id"] + 1
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for update in api.call("getUpdates", offset=offset, timeout=20):
            offset = update["update_id"] + 1
            sender = (update.get("message") or {}).get("from")
            if sender:
                api.call("getUpdates", offset=offset, timeout=0)  # marca como lida
                return sender
    return None


def run() -> int:
    console = Console(highlight=False)
    console.print("\n[bold cyan]Ligar o Jarvis ao Telegram[/]\n")
    console.print(
        "1. No Telegram, abre uma conversa com [bold]@BotFather[/] e envia [bold]/newbot[/].\n"
        "2. Escolhe um nome (ex.: [italic]Jarvis do Tiago[/]) e um utilizador acabado em "
        "[italic]bot[/] (ex.: [italic]jarvis_tiago_bot[/]).\n"
        "3. O BotFather responde com um [bold]token[/] (tipo 123456789:ABC-...). Cola-o aqui.\n"
    )
    token = Prompt.ask("Token do bot", password=True, console=console).strip()
    api = TelegramAPI(token)
    try:
        me = api.call("getMe")
    except Exception as exc:
        console.print(f"[red]Esse token não funcionou: {exc}[/]")
        return 1
    console.print(f"\n[green]✔ Bot encontrado: @{me['username']}[/]")
    console.print(
        f"\nAgora, no Telegram (na conta com que vais mandar ordens), abre [bold]@{me['username']}[/] "
        "e envia [bold]/start[/]. Fico à espera 3 minutos…"
    )
    sender = wait_for_first_message(api)
    if not sender:
        console.print("[red]Não recebi nenhuma mensagem. Corre outra vez quando estiveres pronto.[/]")
        return 1
    name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")]))
    username = f" (@{sender['username']})" if sender.get("username") else ""
    if not Confirm.ask(f"Recebi uma mensagem de [bold]{name}{username}[/], ID {sender['id']}. És tu?",
                       console=console):
        console.print("Não guardei nada.")
        return 1
    write_env("JARVIS_TELEGRAM_TOKEN", token)
    write_env("JARVIS_TELEGRAM_ALLOWED_IDS", str(sender["id"]))
    api.call("sendMessage", chat_id=sender["id"],
             text="✅ Ligado! Sou o Jarvis. Manda-me pedidos como farias no PC: \"abre o Spotify\", "
                  "\"põe um vídeo sobre...\", \"continua o trabalho no meu GitHub\".")
    console.print("\n[green]✔ Guardado no .env. Só aceito mensagens tuas; as outras são ignoradas.[/]")

    if Confirm.ask("\nQueres que o Jarvis do Telegram arranque sozinho com o Windows (em segundo plano, sem janela)?",
                   console=console, default=True):
        script = PROJECT_ROOT / "scripts" / "telegram_startup.ps1"
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=False)
        console.print("[green]✔ Vai arrancar com o Windows. Para o ligar já, abre o Jarvis ou reinicia o PC.[/]")
    return 0
