# Jarvis PC Assistant

**Personal assistant for your PC.** Control your computer by voice or text — open apps and websites, and step into WhatsApp, Telegram and Discord conversations through the browser to read and reply to messages.

## Stack

- Python
- LLM with tool calling to interpret natural language: **Ollama** (local, free) or **Gemini** (API)
- Playwright (browser automation for WhatsApp Web / Telegram Web / Discord)
- faster-whisper (local speech recognition) + edge-tts (Portuguese neural voice)
- rich (terminal UI)

## Features

- Open PC applications by name (`"abre o Spotify"` — "open Spotify")
- Open websites in the browser (`"abre o YouTube"` — "open YouTube")
- Search the web
- Enter a conversation (WhatsApp, Telegram or Discord) and read the latest messages
- Reply to a specific person in a conversation
- Voice or text commands

> **Note:** Jarvis is designed for European Portuguese (pt-PT). Voice commands and spoken replies are in Portuguese; example commands below are shown in Portuguese with an English translation.

## What this project demonstrates

Integration with LLMs (local and cloud) through a common interface to interpret natural language, browser automation (Playwright) and operating system automation.

## Development roadmap

1. Idea
2. Planning
3. Define the command schema (NLU) and supported actions
4. App/website automation
5. Browser automation (WhatsApp / Telegram / Discord)
6. Voice (input and output)
7. Git / Branches
8. Testing
9. README
10. Screenshots
11. Demo

## Running locally

Prerequisites: Python 3.11+ and **one** of these:

- **Ollama** (default): install from https://ollama.com and run `ollama pull qwen2.5:7b` (≈4.7 GB). In tests it picked the right tool in 24/24 requests, in ~1 s each, and speaks European Portuguese. `qwen2.5-coder` also works, but replies in Brazilian Portuguese (set `JARVIS_OLLAMA_MODEL=qwen2.5-coder`).
- **Gemini**: create a free key at https://aistudio.google.com/apikey and set `JARVIS_PROVIDER=gemini` and `GEMINI_API_KEY=...` (in a `.env` file, see `.env.example`).

### Ollama or Gemini?

| | Ollama (local) | Gemini (free tier) |
|---|---|---|
| Quality (choosing actions, European Portuguese, summaries) | Decent with 7B models | Much better |
| Privacy | Everything stays on your PC | Messages you read are sent to Google, and on the free tier Google may use them to improve its products |
| Cost and limits | Free, no limits | Free, but with a daily request limit |
| Internet | Not required | Required |
| Requirements | A good PC (≈5 GB of RAM/VRAM for a 7B model) | None |

### Install and launch (Windows)

1. Double-click **`install.bat`**. It creates the Python environment, installs everything, downloads the browser and the Ollama model, and puts a **Jarvis** shortcut on your desktop.
2. Launch Jarvis from the shortcut, or double-click **`Jarvis.bat`**.
3. Choose a mode:
   - **Type**: you type your requests.
   - **Speak**: press Enter, talk for as long as you like (pauses are fine) and press Enter again to finish. If you forget, it stops on its own after 15 s of silence. Jarvis answers out loud.
   - **Hands-free**: always listening, but only reacts to phrases starting with **"Jarvis, …"**. Recording only ends after 3 s of silence. For 8 s after answering you can keep talking without repeating the name. "Jarvis, sair" (quit) exits.

From the command line: `.venv\Scripts\python -m jarvis.main --modo texto|falar|maos-livres` (text | speak | hands-free).

### Music, videos and contacts

- **YouTube:** `"põe um vídeo sobre…"` / `"mete no YouTube…"` ("play a video about…") searches YouTube and immediately opens the first video (in the chosen browser).
- **Spotify:** `"põe a minha música"` (play my music), `"pausa"` (pause), `"próxima"` (next), `"anterior"` (previous) work without any setup (media keys). Jarvis checks the Spotify window title to confirm the music really started.
- **Spotify by name** (`"toca Bohemian Rhapsody"`, `"põe a playlist de treino"` — "play my workout playlist"): requires the Spotify API (Premium). One-time setup: at https://developer.spotify.com/dashboard create an app with the Redirect URI `http://127.0.0.1:8888/callback` (Web API), copy the **Client ID** into `.env` as `JARVIS_SPOTIFY_CLIENT_ID=...` and authorize in the browser on your first request. Without this, Jarvis opens the Spotify search and says it couldn't start playback.
- **Contacts:** in `contactos.txt` (created automatically, git-ignored) write one person per line, `Name as it appears = ways you say it` (e.g. `Rafosto = rafa, rafael`). Whisper will then recognize those names and Jarvis maps what you said to the right name. Similar names ("Rafosta") are also matched, and the confirmation always shows the real name before sending.
- **Claudinho:** `"abre o Claudinho"` opens Claude on the web; `"diz ao Claudinho para continuar no TaskFlow"` ("tell Claudinho to continue on TaskFlow") opens the project and passes the request to Claude Code.
- **Log:** `.jarvis/jarvis.log` records what was heard, the actions and the errors (only on your PC), so you can work out what went wrong.

### Voice

- **Recording:** voice activity detection (Silero VAD), not volume. Background noise (fans, games) doesn't count as speech and pauses don't cut off your sentence.
- **Recognition:** Whisper `large-v3-turbo`, running locally. On an NVIDIA GPU it takes ~0.5 s per sentence; without a GPU it automatically falls back to `small` on the CPU. The model (~1.6 GB) is downloaded on first use.
- **Microphone:** automatically picks the first non-virtual one (ignores Voicemod and the "Sound Mapper", which alter or don't capture your voice). To pick another, set `JARVIS_MIC=HyperX` (any part of the name).
- **Spoken replies:** Portuguese neural voice (Duarte or Raquel) via `edge-tts`. Requires internet, and the reply text goes through Microsoft's service. Without internet it uses the Windows voices. To stay always offline set `JARVIS_TTS=sapi`.

Example commands:

- `"abre o Spotify e a Steam"` — "open Spotify and Steam" (several requests in one sentence are handled one by one)
- `"abre o Valorant"` / `"abre o Overwatch"` / `"abre o Palworld"` — opens the game directly (Riot, Battle.net, Steam and Epic)
- `"abre no VS Code o repositório TaskFlow e diz ao Claude para continuar"` — "open the TaskFlow repository in VS Code and tell Claude to continue"
- `"abre a calculadora"` / `"abre o WhatsApp"` — "open the calculator" / "open WhatsApp" (any Start Menu app, including Microsoft Store apps, by its Portuguese name)
- `"abre o YouTube"` — "open YouTube"
- `"pesquisa o tempo em Lisboa"` — "search the weather in Lisbon"
- `"lê as últimas mensagens da Ana no WhatsApp"` — "read Ana's latest messages on WhatsApp"
- `"responde ao Rui no Discord a dizer que chego às 8"` — "reply to Rui on Discord saying I'll arrive at 8"

**WhatsApp and Discord** use the desktop apps if installed: Jarvis opens the app, looks up the person and confirms by name that the open conversation is the right one before sending (if it can't confirm, it doesn't send). **Telegram** (or WhatsApp/Discord without the app installed, or with `JARVIS_MESSAGING=web`) uses the web version: the first time, a Chromium window opens for you to log in (QR code), and the session is saved in `.jarvis/browser-profile`. Before sending any message Jarvis asks for confirmation (turn off with `JARVIS_CONFIRM_SEND=0`). Say `"esquece"` (forget) to start a new conversation and `"sair"` (quit) to exit.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `JARVIS_PROVIDER` | `ollama` | `ollama` or `gemini` |
| `JARVIS_OLLAMA_MODEL` | `qwen2.5:7b` | Ollama model (must support tools) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server |
| `GEMINI_API_KEY` | — | Gemini API key |
| `JARVIS_GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model (has a free tier) |
| `JARVIS_MAX_TURNS` | 2 (Ollama) / 10 (Gemini) | Number of requests the model remembers. Small local models get worse at calling tools with a long history |
| `JARVIS_LANGUAGE` | `pt-PT` | Recognition and voice language |
| `JARVIS_MIC` | automatic | Part of the name of the microphone to use |
| `JARVIS_WHISPER_MODEL` | `large-v3-turbo` | Whisper model (`small`, `medium`, ...) |
| `JARVIS_WHISPER_DEVICE` | `auto` | `cuda`, `cpu` or `auto` |
| `JARVIS_TTS` | `edge` | `edge` (neural voice, online) or `sapi` (Windows, offline) |
| `JARVIS_TTS_VOICE` | `pt-PT-DuarteNeural` | Or `pt-PT-RaquelNeural` |
| `JARVIS_END_SILENCE` | `3` | Hands-free: seconds of silence that end the recording |
| `JARVIS_MANUAL_SILENCE` | `15` | Speak mode: seconds of silence that end the recording (or press Enter) |
| `JARVIS_BROWSER` | `default` | Browser for websites: `opera`, `chrome`, `firefox`, `brave`, `edge` or path to the .exe |
| `JARVIS_MESSAGING` | `auto` | WhatsApp/Discord: `auto` (desktop app if present), `desktop` or `web` |
| `JARVIS_PROJECT_DIRS` | GitHub folders | Where to look for projects for VS Code (separated by `;`) |
| `JARVIS_BROWSER_PROFILE` | `.jarvis/browser-profile` | Persistent browser profile |
| `JARVIS_CONFIRM_SEND` | `1` | Ask for confirmation before sending messages |

## Security

- When you dictate the message (`"diz à Ana que já vou"` — "tell Ana I'm on my way", `"responde-lhe que sim"` — "reply yes to them", `envia ao Rui "bom jogo"` — "send Rui 'good game'"), the text sent is taken from your words and not from what the model writes, since it tends to rephrase and add sentences.
- Before sending, Jarvis opens the conversation and confirms it is the requested person ("Ana" opens "Ana Silva", but never "Anabela"). If not, it doesn't send.
- It then shows the real conversation name and the exact text and asks for confirmation: `s` (sim) to send, `e` (editar) to edit the text, any other key to cancel. In hands-free mode confirmation is by voice.
- Messages that are read are passed to the model marked as third-party content, so it doesn't follow instructions written in them.
- `open_app` only accepts application names (no paths or shell characters) and doesn't go through the shell; `open_website` only accepts http/https.

## Reliability with local models

7B models sometimes answer "I opened Spotify" without calling the tool, especially when the same request is already in the history. Jarvis detects action requests (`"abre…"`, `"pesquisa…"`, `"lê…"`, `"diz à Ana que…"`) with no tool called and retries with only the current request. If nothing gets done anyway, it says it couldn't, instead of showing the false answer. With `qwen2.5:7b`: 72/72 correct actions across three runs (before: 13–17/24 when requests repeated).

Ollama's context is set to 8192 tokens (the default, 4096, filled up with read messages and cut off the instructions) and the model stays loaded for 30 min between requests.

## Project structure

```
jarvis/
  main.py              # text/voice loop
  brain.py             # loop: the model picks tools, Jarvis runs them
  tools.py             # tool definitions + execution (and send confirmation)
  llm/
    base.py            # common interface for providers
    ollama_provider.py # Ollama (includes a parser for models that write tool calls as text)
    gemini_provider.py # Gemini (google-genai)
  voice.py             # microphone + Whisper (input), edge-tts (output)
  ui.py                # terminal UI (rich)
  commands.py          # splits "open X and Y and send..." into simple requests
  config.py            # environment variables
  actions/
    system.py          # open apps, websites and searches
    messaging.py       # Playwright: WhatsApp Web, Telegram Web, Discord (web version)
    desktop_chat.py    # desktop WhatsApp and Discord (UI Automation)
    games.py           # games from Steam, Epic, Riot and Battle.net
    projects.py        # projects in VS Code + Claude Code
Jarvis.bat             # double-click to launch
install.bat            # installation + desktop shortcut
scripts/create_shortcut.ps1
assets/jarvis.ico
tests/                 # pytest; test_messaging_browser.py uses a local page that mimics WhatsApp
```

## Testing

```bash
pytest
```

> The CSS selectors for WhatsApp/Telegram/Discord are all in `PLATFORMS` (`jarvis/actions/messaging.py`). These sites change their HTML frequently; if reading or sending stops working, that's where to update them.

## License

This project is licensed under the [MIT License](LICENSE).
