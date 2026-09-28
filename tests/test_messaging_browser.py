"""Corre o código real do Playwright contra uma página local que imita o WhatsApp Web."""

import dataclasses
from pathlib import Path

import pytest

from jarvis.actions import messaging
from jarvis.actions.messaging import Messenger, MessagingError

FIXTURE = Path(__file__).parent / "fixtures" / "fake_whatsapp.html"


@pytest.fixture
def messenger(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    fake = dataclasses.replace(messaging.PLATFORMS["whatsapp"], url=FIXTURE.as_uri())
    monkeypatch.setitem(messaging.PLATFORMS, "whatsapp", fake)
    m = Messenger(tmp_path / "profile", headless=True)
    try:
        m._ensure_context()
    except Exception as exc:  # Chromium não instalado (playwright install chromium)
        pytest.skip(f"Chromium indisponível: {exc}")
    yield m
    m.close()


def sent(m):
    return m._pages["WhatsApp"].evaluate("window.sent")


def test_read_picks_right_chat_and_parses_authors(messenger):
    out = messenger.read_messages("whatsapp", "ana silva", 10)
    assert out.splitlines() == [
        "Conversa: Ana Silva 🌸 (WhatsApp)",
        "[19:01] Ana Silva: Olá! Amanhã jantamos?",
        "[19:05] Tu (enviada): Pode ser",
        "[19:06] Ana Silva: Às 20h no sítio do costume?",
    ]


def test_ana_does_not_open_anabela(messenger):
    # "Ana" aparece em "Anabela" e em "Ana Silva": tem de escolher a Ana, não a Anabela.
    assert "Conversa: Ana Silva" in messenger.read_messages("whatsapp", "Ana", 1)


def test_send_types_exact_text(messenger):
    result = messenger.send_message("whatsapp", "Rui", "Vi!\nFoi incrível")
    assert result == "Mensagem enviada para Rui no WhatsApp."
    assert sent(messenger) == [["Rui", "Vi!\nFoi incrível"]]


def test_unknown_contact_fails_before_asking_confirmation(messenger):
    asked = []
    with pytest.raises(MessagingError, match="Não encontrei a conversa 'Zé'"):
        messenger.send_message("whatsapp", "Zé", "olá", confirm=asked.append)
    assert asked == []
    assert sent(messenger) == []


def test_refuses_to_send_when_chat_title_cannot_be_read(messenger, monkeypatch):
    # Simula o WhatsApp a mudar o HTML do cabeçalho: o seletor deixa de encontrar o nome.
    broken = dataclasses.replace(messaging.PLATFORMS["whatsapp"], chat_title="#nao-existe")
    monkeypatch.setitem(messaging.PLATFORMS, "whatsapp", broken)
    with pytest.raises(MessagingError, match="Não consegui confirmar"):
        messenger.send_message("whatsapp", "Rui", "olá", confirm=lambda t: "olá")
    assert sent(messenger) == []
    assert "não consegui confirmar" in messenger.read_messages("whatsapp", "Rui", 1)


def test_confirmation_gets_real_chat_title_and_can_cancel_or_edit(messenger):
    titles = []
    assert messenger.send_message("whatsapp", "Ana", "olá", confirm=lambda t: titles.append(t)) is None
    assert sent(messenger) == []
    messenger.send_message("whatsapp", "Ana", "olá", confirm=lambda t: "olá, corrigido")
    assert titles == ["Ana Silva 🌸"]
    assert sent(messenger) == [["Ana Silva 🌸", "olá, corrigido"]]
