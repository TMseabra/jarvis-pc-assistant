# Jarvis PC Assistant

**Assistente pessoal para o PC.** Controla o computador por voz ou texto — abre aplicações e sites, e entra em conversas no WhatsApp, Telegram e Discord pelo browser para ler e responder a mensagens.

## Stack

- Python
- Anthropic Claude API (interpretação de comandos em linguagem natural)
- Playwright (automação do browser para WhatsApp Web / Telegram Web / Discord)
- SpeechRecognition + pyttsx3 (voz)

## Features

- Abrir aplicações do PC por nome ("abre o Spotify")
- Abrir sites no browser ("abre o YouTube")
- Pesquisar na web
- Entrar numa conversa (WhatsApp, Telegram ou Discord) e ler as últimas mensagens
- Responder a uma pessoa específica numa conversa
- Comandos por voz ou por texto

## What this project demonstrates

Integração com LLM para interpretar linguagem natural, automação de browser (Playwright) e automação do sistema operativo

## Development roadmap

1. Idea
2. Planning
3. Definir esquema de comandos (NLU) e ações suportadas
4. Automação de apps/sites
5. Automação de browser (WhatsApp / Telegram / Discord)
6. Voz (input e output)
7. Git / Branches
8. Testing
9. README
10. Screenshots
11. Demo

## Running locally

Prerequisites: Python 3.11+, `ANTHROPIC_API_KEY` definido, e `playwright install chromium` corrido uma vez.

```bash
pip install -r requirements.txt
python -m jarvis.main
```
