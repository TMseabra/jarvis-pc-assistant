import pytest

from jarvis.llm import ToolCall
from jarvis.ui import tool_label
from jarvis.voice import is_hallucination, pick_microphone, speakable, strip_wake_word

DEVICES = [
    (0, "Mapeador de sons da Microsoft - Input"),
    (1, "Microfone (Voicemod)"),
    (2, "Microfone (HyperX Quadcast)"),
    (3, "Conjunto de microfones (Realtek"),
]


def test_pick_microphone_skips_virtual_devices():
    assert pick_microphone(DEVICES) == 2


def test_pick_microphone_by_name():
    assert pick_microphone(DEVICES, "realtek") == 3
    assert pick_microphone(DEVICES, "voicemod") == 1  # se o utilizador quiser mesmo
    assert pick_microphone(DEVICES, "não existe") == 2


def test_pick_microphone_only_virtual():
    assert pick_microphone([(1, "Microfone (Voicemod)")]) is None


def test_hallucinations_are_filtered_but_short_answers_kept():
    assert is_hallucination("Obrigado.")
    assert is_hallucination("Legendas pela comunidade Amara.org")
    assert is_hallucination("  ...  ")
    assert not is_hallucination("Sim.")
    assert not is_hallucination("Não")
    assert not is_hallucination("abre o Spotify")


def test_prompt_echo_is_hallucination():
    assert is_hallucination("Jarvis, abre o Spotify, o WhatsApp, o Telegram, o Discord e o YouTube.")
    assert not is_hallucination("Jarvis, abre o Spotify")


@pytest.mark.parametrize("text, expected", [
    ("Jarvis, abre o Spotify.", "abre o Spotify."),
    ("Ok Jarvis abre o YouTube", "abre o YouTube"),
    ("Jervis, que horas são?", "que horas são?"),
    ("Jarvis.", ""),
    ("abre o Spotify", None),
    ("o Jarvis é fixe", None),   # "Jarvis" a meio não conta
])
def test_strip_wake_word(text, expected):
    assert strip_wake_word(text) == expected


def test_speakable():
    assert speakable("**Abri** o `YouTube` 🎬 em https://www.youtube.com/watch?v=x") == "Abri o YouTube em o link"


def test_tool_labels():
    assert tool_label(ToolCall("open_app", {"name": "Spotify"})) == "A abrir Spotify"
    assert tool_label(ToolCall("read_messages", {"platform": "whatsapp", "contact": "Ana"})) == (
        "A ler as mensagens de Ana no WhatsApp"
    )
