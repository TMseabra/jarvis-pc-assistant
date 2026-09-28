import pytest

from jarvis.actions.desktop_chat import (
    ChatRouter,
    DiscordDesktop,
    WhatsAppDesktop,
    clean_discord_name,
    parse_discord_message,
    whatsapp_chat_name,
)


@pytest.mark.parametrize("raw, expected", [
    ("RafostoTag do servidor: 5-O", "Rafosto"),
    ("Sagaris, Rafosto3 membros", "Sagaris, Rafosto"),
    ("Amigos4", "Amigos"),
    ("Mensagens não lidas, Retrac", "Retrac"),
    ("soares", "soares"),
])
def test_clean_discord_name(raw, expected):
    assert clean_discord_name(raw) == expected


def test_parse_discord_message_with_header():
    texts = [("QUEIJO Tag do servidor: DEV", ""), ("", "message-timestamp-1"), ("no way", ""),
             (":thumbsup:", ""), ("Clique para reagir", "")]
    assert parse_discord_message(texts) == ("QUEIJO", "no way")


def test_parse_discord_message_continuation():
    texts = [("", "message-timestamp-2"), ("01:44", ""), ("segunda-feira, 28 de setembro de 2026 01:44", ""),
             ("bora jogar", ""), ("Modificar anexo", ""), ("Excluir", "")]
    assert parse_discord_message(texts) == ("", "bora jogar")


@pytest.mark.parametrize("raw, expected", [
    ("A Princesa Sofia 💙 01:00 olá", "A Princesa Sofia 💙"),
    ("Rafael Pedro ontem até amanhã", "Rafael Pedro"),
    ("Grupo da Turma 27/09/2026 Rui: ok", "Grupo da Turma"),
    ("Sem hora", "Sem hora"),
])
def test_whatsapp_chat_name(raw, expected):
    assert whatsapp_chat_name(raw) == expected


class FakeWeb:
    def close(self):
        pass


def test_router_uses_desktop_app_when_installed():
    router = ChatRouter(FakeWeb(), "auto", installed={WhatsAppDesktop.app_id})
    assert isinstance(router.backend("WhatsApp"), WhatsAppDesktop)
    assert isinstance(router.backend("discord"), FakeWeb)  # Discord de desktop não instalado
    assert isinstance(router.backend("telegram"), FakeWeb)  # Telegram é sempre web


def test_router_modes():
    both = {WhatsAppDesktop.app_id, DiscordDesktop.app_id}
    assert isinstance(ChatRouter(FakeWeb(), "web", installed=both).backend("whatsapp"), FakeWeb)
    assert isinstance(ChatRouter(FakeWeb(), "desktop", installed=set()).backend("discord"), DiscordDesktop)
