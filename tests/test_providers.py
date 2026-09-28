"""Testa a conversão de/para o formato de cada SDK, sem rede."""

import ollama
import pytest
from google.genai import types

from jarvis.llm import LLMError, ToolResult
from jarvis.llm.gemini_provider import GeminiProvider
from jarvis.llm.ollama_provider import OllamaProvider, parse_text_tool_calls
from jarvis.tools import TOOL_SPECS

PARAMS = {t["name"]: list(t["parameters"]["properties"]) for t in TOOL_SPECS}


class FakeOllamaClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ollama_response(content="", tool_calls=None):
    return ollama.ChatResponse(
        model="m",
        message=ollama.Message(role="assistant", content=content, tool_calls=tool_calls),
    )


def test_ollama_tool_call_roundtrip():
    tc = ollama.Message.ToolCall(function=ollama.Message.ToolCall.Function(name="open_app", arguments={"name": "Spotify"}))
    client = FakeOllamaClient([ollama_response(tool_calls=[tc]), ollama_response("Abri o Spotify.")])
    llm = OllamaProvider(model="m", client=client, system_prompt="SYS", tools=TOOL_SPECS)

    llm.begin_turn("abre o spotify")
    step = llm.step()
    assert step.tool_calls[0].name == "open_app"
    assert step.tool_calls[0].args == {"name": "Spotify"}

    llm.add_tool_results([ToolResult(step.tool_calls[0], "Abri Spotify.")])
    assert llm.step().text == "Abri o Spotify."

    sent = client.calls[1]["messages"]
    assert sent[0] == {"role": "system", "content": "SYS"}
    assert sent[-1] == {"role": "tool", "content": "Abri Spotify.", "tool_name": "open_app"}
    assert client.calls[0]["tools"][0]["function"]["name"] == "open_app"


def test_ollama_tool_call_written_as_text_is_parsed():
    client = FakeOllamaClient([
        ollama_response('```json\n{"name": "web_search", "arguments": {"query": "tempo"}}\n```'),
        ollama_response("Pesquisei."),
    ])
    llm = OllamaProvider(model="m", client=client, system_prompt="", tools=TOOL_SPECS)
    llm.begin_turn("pesquisa o tempo")
    step = llm.step()
    assert step.text == ""
    assert [(c.name, c.args) for c in step.tool_calls] == [("web_search", {"query": "tempo"})]
    assert llm.turns[-1][-1]["tool_calls"][0]["function"]["name"] == "web_search"


@pytest.mark.parametrize("text", [
    'Claro! {"name": "open_app", "arguments": {"name": "x"}}',  # texto + JSON: não mexer
    '{"name": "rm_rf", "arguments": {}}',                       # ferramenta desconhecida
    '{"a": 1}',
    "olá",
])
def test_parse_text_tool_calls_ignores_non_calls(text):
    assert parse_text_tool_calls(text, PARAMS) == []


@pytest.mark.parametrize("text, expected", [
    ('web_search("capital de França")', ("web_search", {"query": "capital de França"})),
    ("open_app(name='Spotify')", ("open_app", {"name": "Spotify"})),
    (
        '```\nread_messages("whatsapp", "Ana", count=5)\n```',
        ("read_messages", {"platform": "whatsapp", "contact": "Ana", "count": 5}),
    ),
])
def test_parse_python_style_calls(text, expected):
    [call] = parse_text_tool_calls(text, PARAMS)
    assert (call.name, call.args) == expected


@pytest.mark.parametrize("text", [
    "open_app(__import__('os').system('calc'))",  # só literais: nada é executado
    "rm_rf('/')",
    'web_search("a", "b")',  # argumentos a mais
])
def test_parse_python_style_rejects_unsafe_or_unknown(text):
    assert parse_text_tool_calls(text, PARAMS) == []


def test_ollama_missing_model_is_explained():
    client = FakeOllamaClient([ollama.ResponseError("model not found", 404)])
    llm = OllamaProvider(model="xpto", client=client, system_prompt="", tools=TOOL_SPECS)
    llm.begin_turn("olá")
    with pytest.raises(LLMError, match="ollama pull xpto"):
        llm.step()


def test_ollama_connection_error():
    client = FakeOllamaClient([ConnectionError("recusado")])
    llm = OllamaProvider(model="m", client=client, system_prompt="", tools=TOOL_SPECS)
    llm.begin_turn("olá")
    with pytest.raises(LLMError, match="ollama serve"):
        llm.step()


class FakeGeminiClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append({**kwargs, "contents": list(kwargs["contents"])})
        return self.responses.pop(0)


def gemini_response(*parts):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))]
    )


def test_gemini_tool_call_roundtrip():
    fc = types.Part(function_call=types.FunctionCall(id="c1", name="web_search", args={"query": "tempo"}))
    client = FakeGeminiClient([gemini_response(fc), gemini_response(types.Part.from_text(text="Pesquisei."))])
    llm = GeminiProvider(model="g", client=client, system_prompt="SYS", tools=TOOL_SPECS)

    llm.begin_turn("pesquisa o tempo")
    step = llm.step()
    assert (step.tool_calls[0].name, step.tool_calls[0].args, step.tool_calls[0].id) == ("web_search", {"query": "tempo"}, "c1")

    llm.add_tool_results([ToolResult(step.tool_calls[0], "falhou", is_error=True)])
    assert llm.step().text == "Pesquisei."

    last = client.calls[1]["contents"][-1]
    assert last.role == "user"
    assert last.parts[0].function_response.response == {"error": "falhou"}
    assert last.parts[0].function_response.id == "c1"
    config = client.calls[0]["config"]
    assert config.system_instruction == "SYS"
    assert config.automatic_function_calling.disable is True


def test_gemini_blocked_response():
    client = FakeGeminiClient([types.GenerateContentResponse(candidates=[])])
    llm = GeminiProvider(model="g", client=client, system_prompt="", tools=TOOL_SPECS)
    llm.begin_turn("x")
    with pytest.raises(LLMError, match="bloqueou"):
        llm.step()
