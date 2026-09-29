import os
import time
import urllib.parse

import pytest

from jarvis.actions import vscode


@pytest.mark.parametrize("text,expected", [
    ("abre o vs code", True), ("Jarvis, abre o Visual Studio Code", True), ("abre o visual code studio", True),
    ("abre o TaskFlow no VS Code", False), ("abre o spotify", False),
])
def test_open_request(text, expected):
    assert bool(vscode.OPEN_REQUEST.match(text)) == expected


@pytest.mark.parametrize("text,expected", [
    ("escreve no Claude do VS Code que faça os testes", "faça os testes"),
    ("pede ao Claude no VS Code para corrigir o bug do login", "corrigir o bug do login"),
    ("no VS Code, escreve no Claude: explica este ficheiro", "explica este ficheiro"),
    ("diz ao Claudinho para continuar", None),
])
def test_claude_request(text, expected):
    assert vscode.parse_claude_request(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("instala a extensão Python no VS Code", "Python"),
    ("adiciona o plugin do prettier", "prettier"),
    ("mete a extensão Live Server", "Live Server"),
    ("abre o spotify", None),
])
def test_extension_request(text, expected):
    assert vscode.parse_extension_request(text) == expected


def test_claude_link_encodes_prompt():
    link = vscode.claude_link("faz os testes & corrige")
    assert link.startswith("vscode://anthropic.claude-code/open?prompt=")
    assert urllib.parse.parse_qs(link.split("?", 1)[1])["prompt"] == ["faz os testes & corrige"]


def test_search_extensions_sorted_by_installs():
    data = {"results": [{"extensions": [
        {"publisher": {"publisherName": "tiny", "displayName": "Tiny"}, "extensionName": "py", "displayName": "Py",
         "statistics": [{"statisticName": "install", "value": 50}]},
        {"publisher": {"publisherName": "ms-python", "displayName": "Microsoft"}, "extensionName": "python",
         "displayName": "Python", "statistics": [{"statisticName": "install", "value": 150_000_000}]},
    ]}]}
    found = vscode.search_extensions("python", post=lambda body: data)
    assert found[0]["id"] == "ms-python.python" and "150,0 M" in vscode.describe(found[0])


def test_install_extension_uses_code_cli(monkeypatch):
    monkeypatch.setattr(vscode, "code_cli", lambda: "code")
    calls = []

    class R:
        returncode, stdout, stderr = 0, "Extension 'ms-python.python' was successfully installed.", ""

    out = vscode.install_extension("ms-python.python", run=lambda cmd: calls.append(cmd) or R())
    assert calls == [["code", "--install-extension", "ms-python.python", "--force"]] and "Instalei" in out
    assert "não parece" in vscode.install_extension("rm -rf /")


def test_recent_repos_order(tmp_path, monkeypatch):
    repos = []
    for name, age in (("old", 100), ("new", 1)):
        (tmp_path / name / ".git").mkdir(parents=True)
        repos.append(tmp_path / name)
    (tmp_path / "notrepo").mkdir()
    monkeypatch.setattr(vscode.projects, "last_activity", lambda p: time.time() - (100 if p.name == "old" else 1))
    assert [p.name for p in vscode.recent_repos(repos=repos + [tmp_path / "notrepo"])] == ["new", "old"]


def _brain(monkeypatch):
    from jarvis.brain import Brain
    from jarvis.tools import ToolExecutor
    from tests.test_brain import FakeLLM, FakeMessenger

    calls = []
    executor = ToolExecutor(messenger=FakeMessenger())
    monkeypatch.setattr(executor, "run", lambda name, args, request="": calls.append((name, args)) or "feito")
    return Brain(llm=FakeLLM([]), executor=executor), calls


def test_brain_asks_which_repo(monkeypatch, tmp_path):
    monkeypatch.setattr(vscode, "recent_repos", lambda: [tmp_path / "TaskFlow", tmp_path / "Jogoportugues"])
    brain, calls = _brain(monkeypatch)
    out = brain.handle("abre o vs code")
    assert "1. TaskFlow" in out and "2. Jogoportugues" in out and calls == []
    brain.handle("2")
    assert calls == [("open_project", {"name": "Jogoportugues"})]
    brain.handle("abre o vs code")
    brain.handle("só o vs code")
    assert calls[-1] == ("open_project", {"name": "vscode"})


def test_brain_extension_asks_then_installs(monkeypatch):
    monkeypatch.setattr(vscode, "search_extensions", lambda name: [
        {"id": "esbenp.prettier-vscode", "name": "Prettier", "publisher": "Prettier", "installs": 40_000_000}])
    brain, calls = _brain(monkeypatch)
    assert "Instalo Prettier" in brain.handle("adiciona o plugin do prettier")
    assert calls == []
    brain.handle("sim")
    assert calls == [("vscode_install", {"id": "esbenp.prettier-vscode"})]


def test_brain_writes_in_claude(monkeypatch):
    brain, calls = _brain(monkeypatch)
    brain.handle("escreve no Claude do VS Code que faça os testes")
    assert calls == [("vscode_claude", {"prompt": "faça os testes"})]
