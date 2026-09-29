"""VS Code: escolher o repositório, escrever no Claude e instalar extensões (sem clicar em nada).

- "abre o VS Code" -> lista os teus repositórios (os mais recentes primeiro) para escolheres.
- "escreve no Claude do VS Code: faz os testes" -> abre o painel do Claude Code no VS Code com o
  pedido escrito (link vscode://anthropic.claude-code/open?prompt=...).
- "instala a extensão Python no VS Code" -> procura no Marketplace, pergunta, e instala com
  `code --install-extension`.
"""

import os
import re
import shutil
import subprocess
import urllib.parse
from pathlib import Path

from jarvis.actions import projects

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def recent_repos(limit: int = 10, repos=None) -> list[Path]:
    repos = [p for p in (projects.list_projects() if repos is None else repos) if (p / ".git").exists()]
    return sorted(repos, key=projects.last_activity, reverse=True)[:limit]


def claude_link(prompt: str) -> str:
    return "vscode://anthropic.claude-code/open?" + urllib.parse.urlencode({"prompt": prompt}, quote_via=urllib.parse.quote)


def ask_claude(prompt: str, project: str = "") -> str:
    """Abre o Claude Code no VS Code com o pedido escrito (no projeto `project`, se disseres qual)."""
    prompt = prompt.strip().strip("\"'“”")
    if not prompt:
        return "O que queres que escreva no Claude?"
    if project:
        found = projects.find_project(project)
        code = projects.vscode_executable()
        if found and code:
            subprocess.Popen([str(code), str(found)])
    os.startfile(claude_link(prompt))  # type: ignore[attr-defined]
    return f"Abri o Claude no VS Code com o pedido escrito: \"{prompt}\". Carrega em Enter para o enviar."


# --- extensões -----------------------------------------------------------------

MARKETPLACE = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"


def search_extensions(query: str, post=None, limit: int = 3) -> list[dict]:
    """[{id, name, publisher, installs}] do Marketplace, as mais instaladas primeiro."""
    import httpx

    body = {"filters": [{"criteria": [{"filterType": 8, "value": "Microsoft.VisualStudio.Code"},
                                      {"filterType": 10, "value": query}],
                         "pageSize": 10, "sortBy": 0}], "flags": 0x100 | 0x200}
    post = post or (lambda b: httpx.post(MARKETPLACE, json=b, timeout=15, headers={
        "Accept": "application/json;api-version=3.0-preview.1"}).json())
    data = post(body)
    out = []
    for ext in data.get("results", [{}])[0].get("extensions", []):
        stats = {s["statisticName"]: s["value"] for s in ext.get("statistics", [])}
        out.append({
            "id": f"{ext['publisher']['publisherName']}.{ext['extensionName']}",
            "name": ext.get("displayName") or ext["extensionName"],
            "publisher": ext["publisher"].get("displayName", ext["publisher"]["publisherName"]),
            "installs": int(stats.get("install", 0)),
        })
    out.sort(key=lambda e: e["installs"], reverse=True)
    return out[:limit]


def _installs(n: int) -> str:
    return f"{n / 1e6:.1f} M".replace(".", ",") if n >= 1e6 else f"{n // 1000} mil" if n >= 1000 else str(n)


def describe(ext: dict) -> str:
    return f"{ext['name']} de {ext['publisher']} ({ext['id']}, {_installs(ext['installs'])} instalações)"


def code_cli() -> str | None:
    found = shutil.which("code")
    if found:
        return found
    exe = projects.vscode_executable()
    cmd = exe.parent / "bin" / "code.cmd" if exe else None
    return str(cmd) if cmd and cmd.exists() else None


def install_extension(ext_id: str, run=None) -> str:
    if not re.fullmatch(r"[\w-]+\.[\w.-]+", ext_id):
        return f"'{ext_id}' não parece o identificador de uma extensão."
    cli = code_cli()
    if not cli:
        return "Não encontrei o comando do VS Code (code) para instalar extensões."
    run = run or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                                             creationflags=_NO_WINDOW))
    result = run([cli, "--install-extension", ext_id, "--force"])
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or "failed" in out.lower():
        return f"Não consegui instalar {ext_id}: {out.strip()[:200]}"
    return f"Instalei a extensão {ext_id} no VS Code (se o VS Code estiver aberto, pode pedir para recarregar)."


# --- pedidos ---------------------------------------------------------------------

_VSCODE = r"(?:o\s+)?(?:vs\s*code|vscode|visual\s+(?:studio\s+)?code|visual\s+code\s+studio|code)"
OPEN_REQUEST = re.compile(
    r"^\W*(?:(?:jarvis|podes|consegues|ei|hey)\W+)*(?:abre|abrir|abra|abres)(?:-me)?\s+" + _VSCODE + r"\W*$", re.IGNORECASE)
CLAUDE_REQUEST = re.compile(
    r"(?:escreve|escrever|diz|dizer|pede|pedir|manda|mandar|pergunta|perguntar)(?:-lhe)?\s+(?:no|ao|para\s+o)\s+"
    r"claud(?:e|inho)\s+(?:no|do|dentro\s+do)\s+" + _VSCODE + r"\s*(?:que|para|a\s+dizer|:|,)?\s*(?P<prompt>.+)$"
    r"|(?:no|dentro\s+do)\s+" + _VSCODE + r"\s*,?\s*(?:escreve|diz|pede|manda|pergunta)\s+(?:no|ao)\s+claud(?:e|inho)"
    r"\s*(?:que|para|:|,)?\s*(?P<prompt2>.+)$",
    re.IGNORECASE,
)
EXTENSION_REQUEST = re.compile(
    r"(?:instala|instalar|adiciona|adicionar|p[oõ]e|mete|mete-me)\s+(?:o|a|um|uma)?\s*"
    r"(?:plugin|plug-in|pluggin|extens[aã]o|extension)\s+(?:d[oa]s?\s+|de\s+|chamad[oa]\s+)?(?P<name>.+?)"
    r"(?:\s+(?:no|ao|para\s+o)\s+" + _VSCODE + r")?\W*$",
    re.IGNORECASE,
)


def parse_claude_request(text: str) -> str | None:
    m = CLAUDE_REQUEST.search(text)
    return (m.group("prompt") or m.group("prompt2")).strip() if m else None


def parse_extension_request(text: str) -> str | None:
    m = EXTENSION_REQUEST.search(text)
    return m.group("name").strip().strip("\"'“”") if m else None
