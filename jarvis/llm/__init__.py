"""Escolha do provider de LLM (Ollama local ou Gemini)."""

from jarvis.config import Config
from jarvis.llm.base import ChatProvider, LLMError, StepResult, ToolCall, ToolResult

__all__ = ["ChatProvider", "LLMError", "StepResult", "ToolCall", "ToolResult", "create_provider"]


# Modelos locais pequenos com histórico longo começam a imitar respostas anteriores em vez de
# chamar ferramentas (qwen2.5-coder 7B: 24/24 ações executadas com 2 turnos, 9/24 com 10).
DEFAULT_MAX_TURNS = {"ollama": 2, "gemini": 10}


def create_provider(cfg: Config, system_prompt: str, tools: list[dict]) -> ChatProvider:
    common = dict(
        system_prompt=system_prompt,
        tools=tools,
        max_turns=cfg.max_turns or DEFAULT_MAX_TURNS.get(cfg.provider, 10),
    )
    if cfg.provider == "ollama":
        from jarvis.llm.ollama_provider import OllamaProvider

        return OllamaProvider(model=cfg.ollama_model, host=cfg.ollama_host, **common)
    if cfg.provider == "gemini":
        from jarvis.llm.gemini_provider import GeminiProvider

        return GeminiProvider(model=cfg.gemini_model, api_key=cfg.gemini_api_key, **common)
    raise LLMError(f"Provider desconhecido: '{cfg.provider}'. Usa 'ollama' ou 'gemini'.")
