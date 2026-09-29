"""Perguntas com pesquisa na internet: o Gemini (grátis) com a Pesquisa Google, com fontes.

O modelo local (Ollama) não tem internet. Com JARVIS_GEMINI_API_KEY / GEMINI_API_KEY no .env, o
Jarvis pergunta ao Gemini, que pesquisa no Google e responde com as fontes. Sem chave, abre a
pesquisa no browser.
"""

from jarvis.actions.system import open_url, search_url
from jarvis.config import config

ANSWER_STYLE = (
    "Responde em português de Portugal, de forma curta (3 a 5 frases), com base na pesquisa, com "
    "datas e números concretos quando existirem. Não inventes: se não encontrares, diz."
)


def answer(question: str, client=None) -> str:
    if not config.gemini_api_key and client is None:
        open_url(search_url(question))
        return (
            f"Abri a pesquisa de \"{question}\" no browser. Para eu responder aqui com os resultados, "
            "falta a chave grátis do Gemini (GEMINI_API_KEY no .env, ver README)."
        )
    from google import genai
    from google.genai import errors, types

    client = client or genai.Client(api_key=config.gemini_api_key)
    try:
        response = client.models.generate_content(
            model=config.gemini_model,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=ANSWER_STYLE,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )
    except errors.APIError as exc:
        return f"Não consegui pesquisar: erro do Gemini ({exc.code}): {exc.message}"
    text = (response.text or "").strip()
    if not text:
        return "Pesquisei mas não obtive resposta."
    sources = []
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks or []
        for chunk in chunks[:3]:
            if chunk.web and chunk.web.title:
                sources.append(chunk.web.title)
    except (AttributeError, IndexError, TypeError):
        pass
    return text + (f"\nFontes: {', '.join(dict.fromkeys(sources))}" if sources else "")
