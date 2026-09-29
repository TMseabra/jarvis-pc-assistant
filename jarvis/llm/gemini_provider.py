"""Provider na cloud com a API do Gemini (chave grátis em https://aistudio.google.com)."""

from google import genai
from google.genai import errors, types

from jarvis.llm.base import ChatProvider, LLMError, StepResult, ToolCall, ToolResult


class GeminiProvider(ChatProvider):
    def __init__(self, model: str, api_key: str | None = None, client=None, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        if client is None:
            try:
                # Sem api_key, o SDK lê GEMINI_API_KEY / GOOGLE_API_KEY do ambiente.
                client = genai.Client(api_key=api_key)
            except ValueError as exc:
                raise LLMError("Define GEMINI_API_KEY para usar o Gemini.") from exc
        self.client = client
        self._config = types.GenerateContentConfig(
            # Sem temperature: nos Gemini 3 a Google recomenda manter a predefinição.
            system_instruction=self.system_prompt,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t["name"], description=t["description"], parameters_json_schema=t["parameters"]
                        )
                        for t in self.tools
                    ]
                )
            ],
            # Somos nós que executamos as ferramentas (e pedimos confirmação).
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def complete(self, system: str, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=prompt, config=types.GenerateContentConfig(system_instruction=system)
            )
        except errors.APIError as exc:
            raise LLMError(f"Erro do Gemini ({exc.code}): {exc.message}") from exc
        return (response.text or "").strip()

    def _user_message(self, text: str):
        return types.Content(role="user", parts=[types.Part.from_text(text=text)])

    def step(self) -> StepResult:
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=self.history(), config=self._config
            )
        except errors.ClientError as exc:
            if exc.code in (401, 403):
                raise LLMError("A chave do Gemini é inválida ou não tem acesso a este modelo.") from exc
            if exc.code == 429:
                raise LLMError("Limite de pedidos do Gemini atingido. Tenta daqui a pouco.") from exc
            raise LLMError(f"Erro do Gemini ({exc.code}): {exc.message}") from exc
        except errors.APIError as exc:
            raise LLMError(f"Erro do Gemini ({exc.code}): {exc.message}") from exc

        if not response.candidates or response.candidates[0].content is None:
            raise LLMError("O Gemini bloqueou ou não respondeu a este pedido.")

        content = response.candidates[0].content
        self._append(content)
        parts = content.parts or []
        text = "".join(p.text for p in parts if p.text and not p.thought).strip()
        calls = [
            ToolCall(name=p.function_call.name, args=dict(p.function_call.args or {}), id=p.function_call.id)
            for p in parts
            if p.function_call
        ]
        return StepResult(text=text, tool_calls=calls)

    def add_tool_results(self, results: list[ToolResult]):
        parts = []
        for result in results:
            part = types.Part.from_function_response(
                name=result.call.name,
                response={"error": result.content} if result.is_error else {"result": result.content},
            )
            if result.call.id:
                part.function_response.id = result.call.id
            parts.append(part)
        self._append(types.Content(role="user", parts=parts))
