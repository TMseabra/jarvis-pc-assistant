"""Configuração lida de variáveis de ambiente (e de um ficheiro .env, se existir)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # python-dotenv é opcional
    pass


def _env(name: str, default: str) -> str:
    return os.getenv(name) or default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # "ollama" (local, grátis) ou "gemini" (cloud, precisa de GEMINI_API_KEY).
    provider: str = field(default_factory=lambda: _env("JARVIS_PROVIDER", "ollama").lower())
    ollama_model: str = field(default_factory=lambda: _env("JARVIS_OLLAMA_MODEL", "qwen2.5:7b"))
    ollama_host: str | None = field(default_factory=lambda: os.getenv("OLLAMA_HOST"))
    gemini_model: str = field(default_factory=lambda: _env("JARVIS_GEMINI_MODEL", "gemini-3.8-flash"))
    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    # Nº de pedidos que o modelo recorda (incluindo o atual). None = predefinição do provider.
    max_turns: int | None = field(default_factory=lambda: _int_env("JARVIS_MAX_TURNS", 0) or None)
    language: str = field(default_factory=lambda: _env("JARVIS_LANGUAGE", "pt-PT"))
    # Voz. JARVIS_MIC: parte do nome do microfone (ex. "HyperX"); vazio = primeiro não virtual.
    mic: str | None = field(default_factory=lambda: os.getenv("JARVIS_MIC") or None)
    whisper_model: str = field(default_factory=lambda: _env("JARVIS_WHISPER_MODEL", "large-v3-turbo"))
    whisper_device: str = field(default_factory=lambda: _env("JARVIS_WHISPER_DEVICE", "auto"))
    # Segundos de silêncio que terminam a gravação: no mãos-livres, e no modo Falar
    # (onde também podes carregar em Enter para terminar logo).
    end_silence: float = field(default_factory=lambda: _float_env("JARVIS_END_SILENCE", 3.0))
    manual_silence: float = field(default_factory=lambda: _float_env("JARVIS_MANUAL_SILENCE", 15.0))
    # Mãos-livres: sensibilidade do "Hey Jarvis" (openWakeWord), 0-1; 0 desliga.
    wake_threshold: float = field(default_factory=lambda: _float_env("JARVIS_WAKE_THRESHOLD", 0.3))
    # "edge" = voz neural portuguesa (online); "sapi" = vozes do Windows (offline).
    tts_engine: str = field(default_factory=lambda: _env("JARVIS_TTS", "edge"))
    tts_voice: str = field(default_factory=lambda: _env("JARVIS_TTS_VOICE", "pt-PT-DuarteNeural"))
    # "jarvis" = voz mais grave e com efeito digital subtil; "normal" = voz neural sem efeitos.
    voice_style: str = field(default_factory=lambda: _env("JARVIS_VOICE_STYLE", "normal").lower())
    # Browser para sites e pesquisas: "opera", "chrome", "firefox", "brave", "edge", um caminho
    # para o .exe, ou "default" (o browser predefinido do Windows).
    browser: str = field(default_factory=lambda: _env("JARVIS_BROWSER", "default"))
    # WhatsApp/Discord: "auto" usa a app de desktop se estiver instalada, senão a versão web;
    # "desktop" ou "web" forçam uma delas. (O Telegram usa sempre a versão web.)
    messaging: str = field(default_factory=lambda: _env("JARVIS_MESSAGING", "auto").lower())
    # Telegram: token do bot (@BotFather) e IDs de utilizador autorizados (separados por vírgulas).
    telegram_token: str = field(default_factory=lambda: os.getenv("JARVIS_TELEGRAM_TOKEN", ""))
    telegram_allowed_ids: str = field(default_factory=lambda: os.getenv("JARVIS_TELEGRAM_ALLOWED_IDS", ""))
    # Opcional: Client ID de uma app em developer.spotify.com, para tocar música pelo nome.
    spotify_client_id: str = field(default_factory=lambda: os.getenv("JARVIS_SPOTIFY_CLIENT_ID", ""))
    # Pastas com projetos de código, separadas por ";" (vazio = pastas habituais do GitHub).
    project_dirs: str = field(default_factory=lambda: os.getenv("JARVIS_PROJECT_DIRS", ""))
    # Perfil do browser da versão web (sessões): sempre dentro do projeto.
    browser_profile: Path = field(
        default_factory=lambda: PROJECT_ROOT / _env("JARVIS_BROWSER_PROFILE", ".jarvis/browser-profile")
    )
    # Pedir confirmação antes de enviar mensagens em nome do utilizador.
    confirm_send: bool = field(default_factory=lambda: os.getenv("JARVIS_CONFIRM_SEND", "1") != "0")
    # Mostrar as respostas escritas pelo Jarvis ("responde à última mensagem") antes de enviar.
    confirm_ai_replies: bool = field(default_factory=lambda: os.getenv("JARVIS_CONFIRM_AI_REPLIES", "1") != "0")


config = Config()
