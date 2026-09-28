"""Provider local com Ollama (https://ollama.com)."""

import ast
import json
import re

import httpx
import ollama

from jarvis.llm.base import ChatProvider, LLMError, StepResult, ToolCall, ToolResult

NUM_CTX = 8192
# Mantém o modelo carregado entre pedidos (o primeiro pedido depois de descarregar demora segundos).
KEEP_ALIVE = "30m"

_WRAPPERS = re.compile(r"^```(?:json)?|```$|</?tool_call>", re.IGNORECASE)


def _parse_python_call(text: str, tools: dict[str, list[str]]) -> list[ToolCall]:
    """`web_search("tempo")` ou `open_app(name="Spotify")` -> ToolCall (só literais, sem executar nada)."""
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return []
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in tools):
        return []
    params = tools[node.func.id]
    if len(node.args) > len(params):
        return []
    try:
        args = {params[i]: ast.literal_eval(a) for i, a in enumerate(node.args)}
        args.update({k.arg: ast.literal_eval(k.value) for k in node.keywords if k.arg})
    except (ValueError, SyntaxError):
        return []
    return [ToolCall(name=node.func.id, args=args)]


def parse_text_tool_calls(content: str, tools: dict[str, list[str]]) -> list[ToolCall]:
    """Alguns modelos locais escrevem a chamada à ferramenta como texto em vez de usarem
    tool_calls: em JSON (qwen2.5-coder) ou como chamada Python (qwen2.5). Se a resposta for
    *só* isso, converte-a. `tools` mapeia cada ferramenta aos nomes dos seus parâmetros."""
    text = _WRAPPERS.sub("", content.strip()).strip()
    if re.fullmatch(r"\w+\(.*\)", text, re.DOTALL):
        return _parse_python_call(text, tools)
    if not text.startswith(("{", "[")):
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else [data]
    calls = []
    for item in items:
        if not isinstance(item, dict) or item.get("name") not in tools:
            return []
        args = item.get("arguments", item.get("parameters", {}))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return []
        if not isinstance(args, dict):
            return []
        calls.append(ToolCall(name=item["name"], args=args))
    return calls


class OllamaProvider(ChatProvider):
    def __init__(self, model: str, host: str | None = None, client=None, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.client = client or ollama.Client(host=host)
        self._params = {t["name"]: list(t["parameters"]["properties"]) for t in self.tools}
        self._tools = [
            {
                "type": "function",
                "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
            }
            for t in self.tools
        ]

    def _user_message(self, text: str):
        return {"role": "user", "content": text}

    def warmup(self):
        """Carrega o modelo na memória já, para o primeiro pedido não demorar."""
        try:
            self.client.chat(model=self.model, messages=[], options={"num_ctx": NUM_CTX}, keep_alive=KEEP_ALIVE)
        except Exception:
            pass  # o erro real aparece (com explicação) no primeiro pedido

    def step(self) -> StepResult:
        messages = [{"role": "system", "content": self.system_prompt}, *self.history()]
        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                tools=self._tools,
                # O contexto predefinido do Ollama (4096) enche com mensagens lidas e aí
                # corta o início — onde estão as instruções.
                options={"temperature": 0.2, "num_ctx": NUM_CTX},
                keep_alive=KEEP_ALIVE,
            )
        except ollama.ResponseError as exc:
            if exc.status_code == 404:
                raise LLMError(f"O modelo '{self.model}' não está instalado. Corre: ollama pull {self.model}") from exc
            raise LLMError(f"Erro do Ollama: {exc.error}") from exc
        except (ConnectionError, httpx.HTTPError) as exc:
            raise LLMError("Não consegui ligar ao Ollama. Confirma que está a correr (ollama serve).") from exc

        message = response.message
        content = message.content or ""
        calls = [ToolCall(name=c.function.name, args=dict(c.function.arguments or {})) for c in message.tool_calls or []]
        if not calls:
            calls = parse_text_tool_calls(content, self._params)
            if calls:
                content = ""  # era só a chamada escrita como texto

        entry = {"role": "assistant", "content": content}
        if calls:
            entry["tool_calls"] = [{"function": {"name": c.name, "arguments": c.args}} for c in calls]
        self._append(entry)
        return StepResult(text=content.strip(), tool_calls=calls)

    def add_tool_results(self, results: list[ToolResult]):
        for result in results:
            content = f"Erro: {result.content}" if result.is_error else result.content
            self._append({"role": "tool", "content": content, "tool_name": result.call.name})
