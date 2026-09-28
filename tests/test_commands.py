import pytest

from jarvis.commands import split_commands


@pytest.mark.parametrize("text, expected", [
    ("abre o Spotify e a Steam", ["abre o Spotify", "abre a Steam"]),
    ("abre o Spotify, a Steam e o WhatsApp", ["abre o Spotify", "abre a Steam", "abre o WhatsApp"]),
    ("abre o youtube e pesquisa gatos", ["abre o youtube", "pesquisa gatos"]),
    (
        "abre o Discord e manda uma mensagem ao Rafosto a dizer anda jogar",
        ["abre o Discord", "manda uma mensagem ao Rafosto a dizer anda jogar no Discord"],
    ),
    (
        "abre o Valorant, depois pesquisa o patch notes e lê as mensagens da Ana no whatsapp",
        ["abre o Valorant", "pesquisa o patch notes", "lê as mensagens da Ana no whatsapp"],
    ),
    # A mensagem ditada não é dividida, mesmo com "e" + verbo lá dentro.
    ("diz à Ana que eu e o Rui vamos jantar", ["diz à Ana que eu e o Rui vamos jantar"]),
    ("diz ao Rui que já vou e manda beijinhos", ["diz ao Rui que já vou e manda beijinhos"]),
    ('envia ao Rui "abre a porta e pesquisa isso"', ['envia ao Rui "abre a porta e pesquisa isso"']),
    # Projetos e sites não são listas de apps.
    (
        "abre no VS Code o repositório TaskFlow e diz ao Claude para continuar",
        ["abre no VS Code o repositório TaskFlow e diz ao Claude para continuar"],
    ),
    ("qual é a capital de França?", ["qual é a capital de França?"]),
    ("abre o Rock and Roll Racing", ["abre o Rock and Roll Racing"]),
])
def test_split_commands(text, expected):
    assert split_commands(text) == expected
