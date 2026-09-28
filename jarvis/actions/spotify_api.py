"""Ligação opcional à API oficial do Spotify, para tocar músicas/artistas/playlists pelo nome.

Configuração (uma vez, ~2 minutos — ver README):
1. https://developer.spotify.com/dashboard -> Create app.
   Redirect URI: http://127.0.0.1:8888/callback  ·  API: Web API.
2. Copia o "Client ID" para o .env:  JARVIS_SPOTIFY_CLIENT_ID=...
3. No primeiro pedido de música abre-se o browser para autorizares; o Jarvis guarda o
   acesso em .jarvis/spotify_token.json (renova-se sozinho).

Usa "Authorization Code with PKCE": não há segredo guardado no PC. Controlar a reprodução
exige Spotify Premium.
"""

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse

import httpx

from jarvis.config import PROJECT_ROOT, config

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-playback-state user-modify-playback-state user-library-read"
TOKEN_FILE = PROJECT_ROOT / ".jarvis" / "spotify_token.json"
API = "https://api.spotify.com/v1"


def configured() -> bool:
    return bool(config.spotify_client_id)


# --- autenticação ------------------------------------------------------------

def _save(token: dict):
    token["expires_at"] = time.time() + token.get("expires_in", 3600) - 60
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(token), encoding="utf-8")


def _authorize() -> dict:
    """Abre o browser para o utilizador autorizar e apanha o código em 127.0.0.1:8888."""
    from jarvis.actions.system import open_url

    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if params.get("state", [""])[0] == state:
                result.update({k: v[0] for k, v in params.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            ok = "code" in result
            self.wfile.write(("<h2>Jarvis ligado ao Spotify. Podes fechar esta janela.</h2>" if ok
                              else "<h2>A autorização falhou. Tenta outra vez.</h2>").encode("utf-8"))

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8888), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    open_url("https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
        "client_id": config.spotify_client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": SCOPES,
        "state": state,
    }))
    thread.join(timeout=180)
    server.server_close()
    if "code" not in result:
        raise PermissionError("Não recebi a autorização do Spotify (tens 3 minutos para aceitar no browser).")
    response = httpx.post("https://accounts.spotify.com/api/token", data={
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": config.spotify_client_id,
        "code_verifier": verifier,
    }, timeout=15)
    response.raise_for_status()
    token = response.json()
    _save(token)
    return token


def _token() -> str:
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        token = _authorize()
    if time.time() >= token.get("expires_at", 0):
        response = httpx.post("https://accounts.spotify.com/api/token", data={
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "client_id": config.spotify_client_id,
        }, timeout=15)
        if response.status_code == 400:  # acesso revogado: pedir de novo
            token = _authorize()
        else:
            response.raise_for_status()
            new = response.json()
            new.setdefault("refresh_token", token["refresh_token"])
            _save(new)
            token = new
    return token["access_token"]


def _api(method: str, path: str, **kwargs) -> httpx.Response:
    response = httpx.request(method, API + path, headers={"Authorization": f"Bearer {_token()}"},
                             timeout=15, **kwargs)
    if response.status_code == 403 and "PREMIUM" in response.text.upper():
        raise PermissionError("Controlar a reprodução pelo Spotify precisa de Spotify Premium.")
    return response


# --- reprodução --------------------------------------------------------------

def _computer_device() -> str | None:
    """O dispositivo do PC (a app aberta). Se houver um ativo, usa esse."""
    for _ in range(10):
        devices = _api("GET", "/me/player/devices").json().get("devices", [])
        active = next((d for d in devices if d.get("is_active")), None)
        computer = next((d for d in devices if d.get("type") == "Computer"), None)
        if active or computer:
            return (active or computer)["id"]
        time.sleep(1)  # a app acabou de abrir e ainda não se registou
    return None


def choose_search_type(query: str) -> tuple[str, str]:
    """"playlist de treino" -> ("playlist", "treino"); "músicas do Plutónio" -> ("artist", "Plutónio")."""
    q = query.strip()
    for pattern, kind in (
        (r"^(?:a\s+)?playlist\s+(?:de\s+|do\s+|da\s+)?(.+)$", "playlist"),
        (r"^(?:o\s+)?[áa]lbum\s+(?:de\s+|do\s+|da\s+)?(.+)$", "album"),
        (r"^(?:m[úu]sica|m[úu]sicas|can[çc][õo]es)\s+(?:de|do|da|dos|das)\s+(.+)$", "artist"),
        (r"^(?:o\s+|a\s+)?artista\s+(.+)$", "artist"),
    ):
        import re

        m = re.match(pattern, q, re.IGNORECASE)
        if m:
            return kind, m.group(1)
    return "track", q


def play(query: str) -> str:
    """Toca `query` no PC; sem query, toca as músicas guardadas ("Músicas de que gostaste")."""
    device = _computer_device()
    if not device:
        return "O Spotify não aparece como dispositivo. Abre a app do Spotify e tenta outra vez."
    if query:
        kind, text = choose_search_type(query)
        found = _api("GET", "/search", params={"q": text, "type": kind, "limit": 1}).json()
        items = (found.get(f"{kind}s") or {}).get("items") or []
        items = [i for i in items if i]
        if not items:
            return f"Não encontrei '{query}' no Spotify."
        item = items[0]
        body = {"uris": [item["uri"]]} if kind == "track" else {"context_uri": item["uri"]}
        who = ", ".join(a["name"] for a in item.get("artists", [])[:2])
        label = f"{item['name']}" + (f" — {who}" if who else "")
    else:
        me = _api("GET", "/me").json()
        body = {"context_uri": f"spotify:user:{me['id']}:collection"}
        label = "as tuas músicas guardadas"
    response = _api("PUT", "/me/player/play", params={"device_id": device}, json=body)
    if response.status_code not in (200, 202, 204):
        return f"O Spotify recusou tocar ({response.status_code}): {response.text[:120]}"
    return f"A tocar no Spotify: {label}."
