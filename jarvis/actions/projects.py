"""Projetos de código: abrir no VS Code e pedir ao Claude Code para continuar o trabalho."""

import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from jarvis.config import config


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


def project_dirs() -> list[Path]:
    """Pastas onde procurar projetos (JARVIS_PROJECT_DIRS, separadas por ';')."""
    if config.project_dirs:
        return [Path(p).expanduser() for p in config.project_dirs.split(os.pathsep) if p.strip()]
    home = Path.home()
    return [
        home / "OneDrive" / "Documentos" / "GitHub",
        home / "OneDrive" / "Documents" / "GitHub",
        home / "Documents" / "GitHub",
        home / "Documentos" / "GitHub",
        home / "source" / "repos",
        home / "Projects",
        home / "projetos",
    ]


def list_projects(dirs: list[Path] | None = None) -> list[Path]:
    projects = []
    for base in dirs if dirs is not None else project_dirs():
        if base.is_dir():
            projects += [p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")]
    return projects


def find_project(name: str, projects: list[Path] | None = None) -> Path | None:
    """"task flow" encontra "TaskFlow"; exato > começa por > contém."""
    projects = list_projects() if projects is None else projects
    target = _fold(name)
    if not target:
        return None
    words = [_fold(w) for w in name.split() if _fold(w)]
    for rank in (
        lambda f: f == target,
        lambda f: f.startswith(target),
        lambda f: target in f,
        lambda f: all(w in f for w in words),  # "sales dashboard" -> sales-analytics-dashboard
    ):
        matches = [p for p in projects if rank(_fold(p.name))]
        if matches:
            return min(matches, key=lambda p: len(p.name))
    return None


def vscode_executable() -> Path | None:
    code_cmd = shutil.which("code")
    if code_cmd:  # ...\Microsoft VS Code\bin\code.cmd -> ...\Microsoft VS Code\Code.exe
        exe = Path(code_cmd).resolve().parent.parent / "Code.exe"
        if exe.exists():
            return exe
    default = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "Code.exe"
    return default if default.exists() else None


def claude_executable() -> Path | None:
    """O comando `claude`, ou o que vem com a extensão Claude Code do VS Code."""
    found = shutil.which("claude")
    if found:
        return Path(found)
    extensions = Path.home() / ".vscode" / "extensions"
    candidates = sorted(
        extensions.glob("anthropic.claude-code-*/resources/native-binary/claude.exe"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def has_claude_session(project: Path) -> bool:
    """O Claude Code guarda as conversas em ~/.claude/projects/<caminho com '-'>."""
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(project)).lower()
    sessions = Path.home() / ".claude" / "projects"
    return sessions.is_dir() and any(d.name.lower() == encoded for d in sessions.iterdir())


def _git(project: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=project, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def last_activity(project: Path) -> float:
    """Quando mexeste por último no repositório: último commit ou última alteração no índice/ficheiros."""
    # Não usamos .git/index: o próprio "git status" atualiza-o, o que baralhava a ordem.
    times = []
    last_commit = _git(project, "log", "-1", "--format=%ct")
    if last_commit.isdigit():
        times.append(float(last_commit))
    for changed in _git(project, "--no-optional-locks", "status", "--porcelain").splitlines()[:30]:
        path = project / changed[3:].strip().strip('"')
        if path.exists():
            times.append(path.stat().st_mtime)
    return max(times, default=0.0)


def last_worked_project(projects: list[Path] | None = None) -> Path | None:
    repos = [p for p in (list_projects() if projects is None else projects) if (p / ".git").exists()]
    return max(repos, key=last_activity, default=None)


def work_context(project: Path) -> str:
    """Resumo do estado do repositório para o Claude Code saber onde ficaste."""
    branch = _git(project, "branch", "--show-current") or "?"
    status = _git(project, "--no-optional-locks", "status", "--short")
    commits = _git(project, "log", "-5", "--format=%h %ar %s")
    parts = [f"Branch: {branch}."]
    if commits:
        parts.append("Últimos commits:\n" + commits)
    parts.append("Alterações por guardar:\n" + status if status else "Sem alterações por guardar.")
    return "\n".join(parts)


def continue_work(name: str = "") -> str:
    """Abre o último repositório em que trabalhaste (ou o `name`) e pede ao Claude Code para continuar."""
    project = find_project(name) if name.strip() else last_worked_project()
    if not project:
        names = ", ".join(p.name for p in list_projects()[:15])
        return f"Não encontrei em que repositório estavas a trabalhar. Diz-me qual: {names or 'nenhum encontrado'}."
    prompt = (
        "Continua o trabalho onde fiquei neste repositório. Vê o git log, o git status e os ficheiros "
        "alterados recentemente para perceber o que estava a fazer, diz-me em poucas linhas o que vais "
        "fazer e continua.\n\nEstado atual:\n" + work_context(project)
    )
    return open_project(str(project.name), prompt, project=project)


def open_project(name: str, claude_prompt: str = "", project: Path | None = None) -> str:
    project = project or find_project(name)
    if not project and _fold(name) in {"vscode", "visualstudiocode", "code", "vs", ""}:
        # "abre o VS Code" sem projeto: abre só o editor.
        code = vscode_executable()
        if not code:
            return "Não encontrei o VS Code instalado."
        subprocess.Popen([str(code)])
        return "Abri o VS Code."
    if not project:
        names = ", ".join(p.name for p in list_projects()[:15])
        return f"Não encontrei o projeto '{name}'. Projetos que encontrei: {names or 'nenhum'}."

    code = vscode_executable()
    if not code:
        return "Não encontrei o VS Code instalado."
    subprocess.Popen([str(code), str(project)])
    result = f"Abri {project.name} no VS Code."

    if claude_prompt.strip():
        claude = claude_executable()
        if not claude:
            return result + " Não encontrei o Claude Code para lhe passar o pedido."
        args = [str(claude)]
        if has_claude_session(project):
            args.append("--continue")  # retoma a última conversa deste projeto
        args.append(claude_prompt.strip())
        # Numa janela de terminal nova, na pasta do projeto: vês o Claude a trabalhar e
        # aprovas as permissões como sempre.
        subprocess.Popen(args, cwd=project, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        how = "a continuar a última conversa" if "--continue" in args else "numa conversa nova"
        result += f" Pedi ao Claude Code ({how}): \"{claude_prompt.strip()}\"."
    return result
