"""`Jarvis.bat --classroom`: liga o Jarvis ao teu Google Classroom (só leitura), passo a passo."""

import shutil
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm

from jarvis.actions import classroom

STEPS = """[bold]1.[/] Abre https://console.cloud.google.com e cria um projeto (ex.: "Jarvis").
[bold]2.[/] Em "APIs e serviços" > "Biblioteca", ativa a [cyan]Google Classroom API[/] e a [cyan]Google Drive API[/].
[bold]3.[/] Em "Ecrã de consentimento OAuth" (Google Auth Platform): tipo [cyan]Externo[/], nome "Jarvis",
   o teu email; em "Público-alvo" adiciona o teu email da escola como [cyan]utilizador de teste[/].
[bold]4.[/] Em "Credenciais" > "Criar credenciais" > [cyan]ID de cliente OAuth[/] > tipo [cyan]App para computador[/].
[bold]5.[/] Carrega em [cyan]Transferir JSON[/] (fica nas Transferências como client_secret_....json).
[dim]Se a tua escola bloquear apps de terceiros, a Google mostra "acesso bloqueado" no passo final:
aí só o administrador da escola pode autorizar.[/]"""


def find_client_secret(folder: Path | None = None) -> Path | None:
    """O client_secret*.json mais recente nas Transferências."""
    folder = folder or Path.home() / "Downloads"
    found = sorted(folder.glob("client_secret*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return found[0] if found else None


def run() -> int:
    console = Console()
    console.rule("[bold cyan]Jarvis + Google Classroom")
    if not classroom.configured():
        console.print(STEPS)
        if Confirm.ask("Abrir a Google Cloud Console agora?", default=True):
            webbrowser.open("https://console.cloud.google.com/apis/library/classroom.googleapis.com")
        while True:
            secret = find_client_secret()
            if secret:
                break
            if not Confirm.ask("Não encontrei o client_secret....json nas Transferências. Já o transferiste?",
                               default=True):
                return 1
        classroom.CREDENTIALS.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(secret, classroom.CREDENTIALS)
        console.print(f"✅ Copiei [cyan]{secret.name}[/] para .jarvis/google_credentials.json")
    console.print("Agora vai abrir o browser: entra com a conta da escola e aceita (só leitura).")
    try:
        room, _ = classroom.services()
        courses = classroom.list_courses(room)
    except Exception as exc:
        console.print(f"[red]Não deu: {exc}[/]")
        return 1
    console.print(f"✅ Ligado! Encontrei {len(courses)} turma(s):")
    for i, c in enumerate(courses, 1):
        console.print(f"  {i}. {c['name']}")
    console.print('Diz ao Jarvis [cyan]"faz um trabalho"[/] para começar.')
    return 0
