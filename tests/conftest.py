"""Os testes não usam a configuração pessoal (.env) nem fazem ações reais no PC."""

import os

import pytest

# Antes de importar o jarvis: o load_dotenv não substitui variáveis que já existem.
os.environ["JARVIS_BROWSER"] = "default"
os.environ["JARVIS_PROVIDER"] = "ollama"
os.environ["JARVIS_MESSAGING"] = "web"


def _blocked(what):
    def fail(*args, **kwargs):
        raise AssertionError(f"Um teste tentou {what} a sério: {args!r}. Usa monkeypatch.")
    return fail


@pytest.fixture(autouse=True)
def no_real_side_effects(monkeypatch):
    """Abrir apps, pastas, Definições ou sites a partir de um teste é sempre um erro.
    Os testes que precisam substituem estas funções por versões falsas (e isso prevalece)."""
    import webbrowser

    from jarvis.actions import ai_web, media, system

    monkeypatch.setattr(os, "startfile", _blocked("abrir (os.startfile)"), raising=False)
    monkeypatch.setattr(webbrowser, "open", _blocked("abrir o browser"))
    for module in (system, ai_web, media):
        monkeypatch.setattr(module, "open_url", _blocked("abrir um site"))
