"""Abrir pastas, ficheiros e páginas das Definições do Windows pelo nome."""

import os
import unicodedata
from pathlib import Path


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if ch.isalnum())


# Pastas conhecidas -> nome "shell:" do Windows (funciona mesmo com o OneDrive a mudar os caminhos).
KNOWN_FOLDERS = {
    "transferencias": ("Transferências", "shell:Downloads"),
    "downloads": ("Transferências", "shell:Downloads"),
    "documentos": ("Documentos", "shell:Personal"),
    "documents": ("Documentos", "shell:Personal"),
    "ambientedetrabalho": ("Ambiente de Trabalho", "shell:Desktop"),
    "desktop": ("Ambiente de Trabalho", "shell:Desktop"),
    "imagens": ("Imagens", "shell:My Pictures"),
    "fotos": ("Imagens", "shell:My Pictures"),
    "fotografias": ("Imagens", "shell:My Pictures"),
    "videos": ("Vídeos", "shell:My Video"),
    "musica": ("Música", "shell:My Music"),
    "musicas": ("Música", "shell:My Music"),
    "estepc": ("Este PC", "shell:MyComputerFolder"),
    "computador": ("Este PC", "shell:MyComputerFolder"),
    "reciclagem": ("Reciclagem", "shell:RecycleBinFolder"),
    "lixo": ("Reciclagem", "shell:RecycleBinFolder"),
    "capturasdeecra": ("Capturas de ecrã", "shell:Screenshots"),
    "screenshots": ("Capturas de ecrã", "shell:Screenshots"),
}

# Definições do Windows (ms-settings:).
SETTINGS = {
    "bluetooth": ("Bluetooth", "ms-settings:bluetooth"),
    "wifi": ("Wi-Fi", "ms-settings:network-wifi"),
    "rede": ("Rede e Internet", "ms-settings:network"),
    "internet": ("Rede e Internet", "ms-settings:network"),
    "som": ("Som", "ms-settings:sound"),
    "audio": ("Som", "ms-settings:sound"),
    "ecra": ("Ecrã", "ms-settings:display"),
    "monitor": ("Ecrã", "ms-settings:display"),
    "display": ("Ecrã", "ms-settings:display"),
    "atualizacoes": ("Windows Update", "ms-settings:windowsupdate"),
    "windowsupdate": ("Windows Update", "ms-settings:windowsupdate"),
    "aplicacoes": ("Aplicações", "ms-settings:appsfeatures"),
    "apps": ("Aplicações", "ms-settings:appsfeatures"),
    "bateria": ("Energia e bateria", "ms-settings:batterysaver"),
    "energia": ("Energia e bateria", "ms-settings:powersleep"),
    "fundo": ("Fundo do ambiente de trabalho", "ms-settings:personalization-background"),
    "personalizacao": ("Personalização", "ms-settings:personalization"),
    "ratos": ("Rato", "ms-settings:mousetouchpad"),
    "rato": ("Rato", "ms-settings:mousetouchpad"),
    "teclado": ("Teclado", "ms-settings:typing"),
    "impressoras": ("Impressoras", "ms-settings:printers"),
    "armazenamento": ("Armazenamento", "ms-settings:storagesense"),
    "privacidade": ("Privacidade", "ms-settings:privacy"),
    "notificacoes": ("Notificações", "ms-settings:notifications"),
    "hora": ("Data e hora", "ms-settings:dateandtime"),
    "idioma": ("Idioma", "ms-settings:regionlanguage"),
    "jogos": ("Jogos", "ms-settings:gaming-gamebar"),
    "definicoes": ("Definições", "ms-settings:"),
}

_SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__", "appdata", "$recycle.bin", ".cache"}


def search_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / "Desktop", home / "OneDrive" / "Ambiente de Trabalho", home / "OneDrive" / "Desktop",
        home / "Downloads",
        home / "Documents", home / "OneDrive" / "Documentos", home / "OneDrive" / "Documents",
        home / "Pictures", home / "OneDrive" / "Imagens", home / "Videos", home / "Music",
    ]
    return list(dict.fromkeys(r for r in roots if r.is_dir()))


def find_path(name: str, roots: list[Path] | None = None, max_depth: int = 4, limit: int = 20000) -> Path | None:
    """Procura um ficheiro ou pasta pelo nome (sem extensão, sem acentos).
    Exato > começa por > contém; nas pastas mais à superfície primeiro."""
    target = _fold(name)
    if len(target) < 2:
        return None
    exact_only = len(target) < 3  # "CV": só o nome exato, senão apanhava tudo
    best: dict[int, tuple[int, Path]] = {}  # rank -> (profundidade, caminho)
    seen = 0
    for root in roots if roots is not None else search_roots():
        stack = [(root, 0)]
        while stack:
            folder, depth = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                seen += 1
                if seen > limit:
                    break
                stem = _fold(Path(entry.name).stem if entry.is_file() else entry.name)
                rank = 0 if stem == target else None if exact_only else \
                    1 if stem.startswith(target) else 2 if target in stem else None
                if rank is not None and (rank not in best or depth < best[rank][0]):
                    best[rank] = (depth, Path(entry.path))
                if entry.is_dir(follow_symlinks=False) and depth < max_depth \
                        and entry.name.lower() not in _SKIP_DIRS and not entry.name.startswith("."):
                    stack.append((Path(entry.path), depth + 1))
            if 0 in best and best[0][0] == 0:
                break
    for rank in (0, 1, 2):
        if rank in best:
            return best[rank][1]
    return None


def open_path(name: str) -> str:
    """Abre uma pasta conhecida, uma página das Definições ou um ficheiro/pasta pelo nome."""
    key = _fold(name.replace("definições de", "").replace("definicoes de", ""))
    if key in KNOWN_FOLDERS:
        label, target = KNOWN_FOLDERS[key]
        os.startfile(target)  # type: ignore[attr-defined]
        return f"Abri a pasta {label}."
    if key in SETTINGS:
        label, target = SETTINGS[key]
        os.startfile(target)  # type: ignore[attr-defined]
        return f"Abri as Definições: {label}."
    found = find_path(name)
    if not found:
        return f"Não encontrei nenhum ficheiro ou pasta chamado '{name}'."
    os.startfile(str(found))  # type: ignore[attr-defined]
    kind = "a pasta" if found.is_dir() else "o ficheiro"
    return f"Abri {kind} {found.name} ({found.parent})."
