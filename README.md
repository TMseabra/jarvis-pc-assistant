# Jarvis PC Assistant

**Assistente pessoal para o PC.** Controla o computador por voz ou texto — abre aplicações e sites, e entra em conversas no WhatsApp, Telegram e Discord pelo browser para ler e responder a mensagens.

## Stack

- Python
- LLM com tool calling para interpretar linguagem natural: **Ollama** (local, grátis) ou **Gemini** (API)
- Playwright (automação do browser para WhatsApp Web / Telegram Web / Discord)
- faster-whisper (reconhecimento de voz local) + edge-tts (voz neural portuguesa)
- rich (interface de terminal)

## Features

- Abrir aplicações do PC por nome ("abre o Spotify")
- Abrir sites no browser ("abre o YouTube")
- Pesquisar na web
- Entrar numa conversa (WhatsApp, Telegram ou Discord) e ler as últimas mensagens
- Responder a uma pessoa específica numa conversa
- Comandos por voz ou por texto

## What this project demonstrates

Integração com LLMs (locais e na cloud) através de uma interface comum para interpretar linguagem natural, automação de browser (Playwright) e automação do sistema operativo

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

Prerequisites: Python 3.11+ e **um** destes:

- **Ollama** (predefinição): instala em https://ollama.com e corre `ollama pull qwen2.5:7b` (≈4.7 GB). Nos testes escolheu a ferramenta certa em 24/24 pedidos, em ~1 s cada, e fala português de Portugal. O `qwen2.5-coder` também funciona, mas responde em português do Brasil (define `JARVIS_OLLAMA_MODEL=qwen2.5-coder`).
- **Gemini**: cria uma chave grátis em https://aistudio.google.com/apikey e define `JARVIS_PROVIDER=gemini` e `GEMINI_API_KEY=...` (num ficheiro `.env`, ver `.env.example`).

### Ollama ou Gemini?

| | Ollama (local) | Gemini (plano gratuito) |
|---|---|---|
| Qualidade (escolher ações, português de Portugal, resumos) | Razoável com modelos de 7B | Bastante melhor |
| Privacidade | Tudo fica no PC | As mensagens lidas vão para a Google, e no plano gratuito a Google pode usá-las para melhorar os produtos |
| Custo e limites | Grátis, sem limites | Grátis, mas com limite de pedidos por dia |
| Internet | Não precisa | Precisa |
| Requisitos | Bom PC (≈5 GB de RAM/VRAM para um modelo de 7B) | Nenhum |

### Instalar e abrir (Windows)

1. Faz duplo clique em **`install.bat`**. Cria o ambiente Python, instala tudo, descarrega o browser e o modelo do Ollama, e põe um atalho **Jarvis** no ambiente de trabalho.
2. Abre o Jarvis pelo atalho, ou com duplo clique em **`Jarvis.bat`**.
3. Escolhe o modo:
   - **Escrever**: escreves os pedidos.
   - **Falar**: carregas em Enter, falas o tempo que quiseres (com pausas) e carregas em Enter outra vez para terminar. Se te esqueceres, para sozinho após 15 s de silêncio. O Jarvis responde em voz alta.
   - **Mãos-livres**: está sempre a ouvir, mas só reage a frases começadas por **“Jarvis, …”**. A gravação só acaba com 3 s de silêncio. Durante 8 s depois de responder podes continuar sem repetir o nome. “Jarvis, sair” termina.

Pela linha de comandos: `.venv\Scripts\python -m jarvis.main --modo texto|falar|maos-livres`.

### Música, vídeos e contactos

- **YouTube:** "põe um vídeo sobre…" / "mete no YouTube…" pesquisa no YouTube e abre logo o primeiro vídeo (no browser escolhido).
- **Spotify:** "põe a minha música", "pausa", "próxima", "anterior" funcionam sem configuração (teclas multimédia). O Jarvis confirma pelo título da janela do Spotify que a música começou mesmo.
- **Spotify pelo nome** ("toca Bohemian Rhapsody", "põe a playlist de treino"): precisa da API do Spotify (Premium). Uma vez: em https://developer.spotify.com/dashboard cria uma app com o Redirect URI `http://127.0.0.1:8888/callback` (Web API), copia o **Client ID** para o `.env` como `JARVIS_SPOTIFY_CLIENT_ID=...` e, no primeiro pedido, autoriza no browser. Sem isto, o Jarvis abre a pesquisa no Spotify e diz que não conseguiu pôr a tocar.
- **Contactos:** em `contactos.txt` (criado automaticamente, fora do git) escreve uma pessoa por linha, `Nome como aparece = formas como o dizes` (ex.: `Rafosto = rafa, rafael`). O Whisper passa a reconhecer esses nomes e o Jarvis traduz o que disseste para o nome certo. Nomes parecidos ("Rafosta") também são encontrados, e a confirmação mostra sempre o nome real antes de enviar.
- **Claudinho:** "abre o Claudinho" abre o Claude na web; "diz ao Claudinho para continuar no TaskFlow" abre o projeto e passa o pedido ao Claude Code.
- **Imagens, código e textos com IA:** "faz-me uma imagem de…" abre o ChatGPT com o pedido (e envia-o); "faz-me um script que…" abre o Claude com o pedido e carrega em Enter quando a janela estiver à frente; "escreve-me um email…" vai ao ChatGPT. Usa a tua sessão no browser escolhido.
- **Abrir qualquer coisa:** pastas ("abre as transferências", "as minhas fotos"), ficheiros pelo nome ("abre o meu CV") e Definições do Windows ("o bluetooth não funciona", "abre o som").
- **Pedidos vagos:** o Jarvis escolhe a interpretação mais provável e faz logo ("põe música", "quero rir um bocado"); só pergunta quando não há nenhuma interpretação segura.
- **Verificação final:** no fim de cada pedido o Jarvis confere o resultado de todas as ações e diz "Terminei, correu tudo bem" ou o que falhou.
- **Voz estilo JARVIS:** `JARVIS_VOICE_STYLE=jarvis` deixa a voz mais grave, um pouco mais rápida e com um efeito digital subtil.
- **Responder a quem tens por responder:** "responde à última mensagem que recebi no WhatsApp" usa o filtro **Não lidas** do WhatsApp de desktop, abre a conversa mais recente, lê as mensagens e escreve uma resposta como tu escreverias. Por segurança, as respostas escritas pelo Jarvis são mostradas antes de enviar (✅/❌ no Telegram, s/n no PC); desliga com `JARVIS_CONFIRM_AI_REPLIES=0`. Se ditares o texto ("…a dizer que já vou"), envia logo.
- **O último vídeo que viste:** "abre o meu último vídeo do YouTube" (ou "o penúltimo") vem do histórico do browser, não de uma pesquisa.
- **Última conversa do Claude/ChatGPT:** "abre o Claude na minha última conversa e diz para continuar" abre a conversa mais recente (do histórico do browser) e escreve lá o pedido.
- **Steam:** "qual é o jogo com mais horas nos meus favoritos?" lê as horas e a coleção de favoritos dos ficheiros da Steam no PC (sem login).
- **Fechar apps:** "fecha o WhatsApp".
- **Registo:** `.jarvis/jarvis.log` guarda o que foi ouvido, as ações e os erros (só no teu PC), para perceber o que falhou.

### "Hey Jarvis" e Telegram

- **Palavra de ativação (mãos-livres):** o Jarvis ouve "**Hey Jarvis**" localmente com o openWakeWord, que funciona mesmo com música a tocar. O modelo foi treinado com pronúncia inglesa ("Djárvis"); com o "J" português também funciona, porque frases começadas por "Jarvis" são apanhadas pelo Whisper. Para veres como dizer para ativar sempre: `Jarvis.bat --testar-jarvis` (barra ao vivo). Sensibilidade: `JARVIS_WAKE_THRESHOLD` (0.3 por omissão; 0 desliga).
- **Telegram:** `Jarvis.bat --telegram` guia a configuração. Crias um bot no **@BotFather**, colas o token, envias `/start` ao bot e o Jarvis guarda o teu ID. A partir daí mandas pedidos pelo Telegram ("abre o Spotify", "continua o trabalho no meu GitHub") e ele responde com o resultado e a verificação.
  - Só aceita mensagens dos IDs em `JARVIS_TELEGRAM_ALLOWED_IDS`; as outras são ignoradas sem resposta.
  - Ações sensíveis (lançar o Claude Code a mexer em código; no futuro apagar ficheiros, `git push`, comandos) pedem confirmação com botões ✅/❌. Sem resposta em 2 minutos, não faz.
  - Sempre ligado: o assistente oferece-se para arrancar com o Windows em segundo plano (`--servico`, sem janela). Só um Jarvis lê o bot de cada vez.

### Voz

- **Gravação:** deteção de voz (Silero VAD), não o volume. O ruído de fundo (ventoinhas, jogo) não conta como fala e as pausas não cortam a frase.
- **Reconhecimento:** Whisper `large-v3-turbo`, a correr localmente. Na GPU NVIDIA demora ~0.5 s por frase; sem GPU passa sozinho para o `small` no CPU. Na primeira vez descarrega o modelo (~1.6 GB).
- **Microfone:** escolhe automaticamente o primeiro que não seja virtual (ignora o Voicemod e o "Mapeador de sons", que alteram ou não captam a voz). Para escolher outro, define `JARVIS_MIC=HyperX` (qualquer parte do nome).
- **Resposta falada:** voz neural portuguesa (Duarte ou Raquel) através do `edge-tts`. Precisa de internet, e o texto das respostas passa pelo serviço da Microsoft. Sem internet usa as vozes do Windows. Para ficar sempre offline define `JARVIS_TTS=sapi`.

Exemplos de comandos:

- "abre o Spotify e a Steam" (vários pedidos na mesma frase são feitos um a um)
- "abre o Valorant" / "abre o Overwatch" / "abre o Palworld" (abre o jogo diretamente: Riot, Battle.net, Steam e Epic)
- "abre no VS Code o repositório TaskFlow e diz ao Claude para continuar"
- "abre a calculadora" / "abre o WhatsApp" (qualquer app do Menu Iniciar, incluindo as da Microsoft Store, pelo nome em português)
- "abre o YouTube"
- "pesquisa o tempo em Lisboa"
- "lê as últimas mensagens da Ana no WhatsApp"
- "responde ao Rui no Discord a dizer que chego às 8"

**WhatsApp e Discord** usam as apps de desktop se estiverem instaladas: o Jarvis abre a app, procura a pessoa e confirma pelo nome que a conversa aberta é a certa antes de enviar (se não conseguir confirmar, não envia). O **Telegram** (ou WhatsApp/Discord sem app instalada, ou com `JARVIS_MESSAGING=web`) usa a versão web: na primeira vez abre-se uma janela do Chromium para fazeres login (QR code), e a sessão fica guardada em `.jarvis/browser-profile`. Antes de enviar qualquer mensagem o Jarvis pede confirmação (desliga com `JARVIS_CONFIRM_SEND=0`). Escreve "esquece" para começar uma conversa nova e "sair" para terminar.

## Configuração

| Variável | Predefinição | Descrição |
|---|---|---|
| `JARVIS_PROVIDER` | `ollama` | `ollama` ou `gemini` |
| `JARVIS_OLLAMA_MODEL` | `qwen2.5:7b` | Modelo do Ollama (tem de suportar tools) |
| `OLLAMA_HOST` | `http://localhost:11434` | Servidor do Ollama |
| `GEMINI_API_KEY` | — | Chave da API do Gemini |
| `JARVIS_GEMINI_MODEL` | `gemini-3.8-flash` | Modelo do Gemini (tem plano gratuito) |
| `JARVIS_MAX_TURNS` | 2 (Ollama) / 10 (Gemini) | Pedidos que o modelo recorda. Modelos locais pequenos ficam piores a chamar ferramentas com histórico longo |
| `JARVIS_LANGUAGE` | `pt-PT` | Língua do reconhecimento e da voz |
| `JARVIS_MIC` | automático | Parte do nome do microfone a usar |
| `JARVIS_WHISPER_MODEL` | `large-v3-turbo` | Modelo do Whisper (`small`, `medium`, ...) |
| `JARVIS_WHISPER_DEVICE` | `auto` | `cuda`, `cpu` ou `auto` |
| `JARVIS_TTS` | `edge` | `edge` (voz neural, online) ou `sapi` (Windows, offline) |
| `JARVIS_TTS_VOICE` | `pt-PT-DuarteNeural` | Ou `pt-PT-RaquelNeural` |
| `JARVIS_END_SILENCE` | `3` | Mãos-livres: segundos de silêncio que terminam a gravação |
| `JARVIS_MANUAL_SILENCE` | `15` | Modo Falar: segundos de silêncio que terminam a gravação (ou carrega em Enter) |
| `JARVIS_BROWSER` | `default` | Browser para sites: `opera`, `chrome`, `firefox`, `brave`, `edge` ou caminho do .exe |
| `JARVIS_MESSAGING` | `auto` | WhatsApp/Discord: `auto` (app de desktop se existir), `desktop` ou `web` |
| `JARVIS_PROJECT_DIRS` | pastas GitHub | Onde procurar projetos para o VS Code (separadas por `;`) |
| `JARVIS_BROWSER_PROFILE` | `.jarvis/browser-profile` | Perfil persistente do browser |
| `JARVIS_CONFIRM_SEND` | `1` | Pedir confirmação antes de enviar mensagens |

## Segurança

- Quando ditas a mensagem ("diz à Ana que já vou", "responde-lhe que sim", `envia ao Rui "bom jogo"`), o texto enviado é tirado das tuas palavras e não do que o modelo escreve, que tende a reescrever e acrescentar frases.
- Antes de enviar, o Jarvis abre a conversa e confirma que é a pessoa pedida ("Ana" abre "Ana Silva", mas nunca "Anabela"). Se não for, não envia.
- Depois mostra o nome real da conversa e o texto exato e pede confirmação: `s` para enviar, `e` para corrigir o texto, qualquer outra tecla para cancelar. No modo mãos-livres a confirmação é por voz.
- As mensagens lidas vão para o modelo marcadas como conteúdo de terceiros, para ele não seguir instruções escritas nelas.
- `open_app` só aceita nomes de aplicações (sem caminhos nem caracteres de shell) e não passa pela shell; `open_website` só aceita http/https.

## Fiabilidade com modelos locais

Modelos de 7B às vezes respondem "abri o Spotify" sem chamar a ferramenta, sobretudo quando o mesmo pedido já está no histórico. O Jarvis deteta pedidos de ação ("abre…", "pesquisa…", "lê…", "diz à Ana que…") sem nenhuma ferramenta chamada e tenta outra vez só com o pedido atual. Se mesmo assim nada for feito, diz que não conseguiu, em vez de mostrar a resposta falsa. Com o `qwen2.5:7b`: 72/72 ações certas em três execuções (antes: 13–17/24 quando os pedidos se repetiam).

O contexto do Ollama está a 8192 tokens (o predefinido, 4096, enchia com mensagens lidas e cortava as instruções) e o modelo fica carregado 30 min entre pedidos.

## Estrutura

```
jarvis/
  main.py              # loop de texto/voz
  brain.py             # loop: o modelo escolhe ferramentas, o Jarvis executa-as
  tools.py             # definição das ferramentas + execução (e confirmação de envio)
  llm/
    base.py            # interface comum aos providers
    ollama_provider.py # Ollama (inclui parser para modelos que escrevem tool calls como texto)
    gemini_provider.py # Gemini (google-genai)
  voice.py             # microfone + Whisper (entrada), edge-tts (saída)
  ui.py                # interface de terminal (rich)
  commands.py          # divide "abre X e Y e manda..." em pedidos simples
  config.py            # variáveis de ambiente
  actions/
    system.py          # abrir apps, sites e pesquisas
    messaging.py       # Playwright: WhatsApp Web, Telegram Web, Discord (versão web)
    desktop_chat.py    # WhatsApp e Discord de desktop (UI Automation)
    games.py           # jogos da Steam, Epic, Riot e Battle.net
    projects.py        # projetos no VS Code + Claude Code
Jarvis.bat             # duplo clique para abrir
install.bat            # instalação + atalho no ambiente de trabalho
scripts/create_shortcut.ps1
assets/jarvis.ico
tests/                 # pytest; test_messaging_browser.py usa uma página local que imita o WhatsApp
```

## Testing

```bash
pytest
```

> Os seletores CSS do WhatsApp/Telegram/Discord estão todos em `PLATFORMS` (`jarvis/actions/messaging.py`). Estes sites mudam o HTML com frequência; se a leitura ou o envio deixarem de funcionar, é aí que se atualizam.
