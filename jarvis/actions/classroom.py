"""Google Classroom (só leitura): turmas -> trabalhos recentes -> enunciado e anexos -> Claude.

Configuração (uma vez): `Jarvis.bat --classroom` explica os passos no Google Cloud e faz a
autorização. As chaves ficam em .jarvis/ (fora do git). Permissões pedidas: ler as turmas,
os trabalhos e os materiais, e ler (descarregar) os ficheiros do Drive anexados aos trabalhos.
"""

import io
import re
from datetime import datetime

from jarvis.config import PROJECT_ROOT

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]
CREDENTIALS = PROJECT_ROOT / ".jarvis" / "google_credentials.json"
TOKEN = PROJECT_ROOT / ".jarvis" / "google_token.json"
MAX_ATTACHMENT_CHARS = 15_000  # por anexo, para o pedido ao Claude não ficar gigante


def configured() -> bool:
    return CREDENTIALS.exists()


def credentials(interactive: bool = True):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None
    if not creds or not creds.valid:
        if not interactive:
            raise PermissionError("Falta autorizar o Jarvis no Google: corre Jarvis.bat --classroom.")
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True,
                                      success_message="Jarvis ligado ao Google Classroom. Podes fechar esta janela.")
    TOKEN.parent.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def services():
    from googleapiclient.discovery import build

    creds = credentials()
    return (build("classroom", "v1", credentials=creds, cache_discovery=False),
            build("drive", "v3", credentials=creds, cache_discovery=False))


# --- leitura ---------------------------------------------------------------

def list_courses(classroom) -> list[dict]:
    courses = classroom.courses().list(courseStates=["ACTIVE"], pageSize=50).execute().get("courses", [])
    return [{"id": c["id"], "name": c.get("name", "?"), "section": c.get("section", ""),
             "link": c.get("alternateLink", "")} for c in courses]


def recent_work(classroom, course_id: str, limit: int = 10) -> list[dict]:
    items = classroom.courses().courseWork().list(
        courseId=course_id, orderBy="updateTime desc", pageSize=limit).execute().get("courseWork", [])
    return items[:limit]


def due_text(work: dict) -> str:
    due = work.get("dueDate")
    if not due:
        return "sem prazo"
    time = work.get("dueTime", {})
    hour = f" às {time.get('hours', 0):02d}:{time.get('minutes', 0):02d}" if time else ""
    return f"entrega {due.get('day', 0):02d}/{due.get('month', 0):02d}{hour}"


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


_EXPORTS = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}


def material_texts(drive, work: dict) -> list[tuple[str, str]]:
    """[(título, conteúdo)] dos anexos: texto de PDFs e Google Docs/Slides/Sheets; links e vídeos."""
    out = []
    for material in work.get("materials", []):
        if "driveFile" in material:
            file = material["driveFile"].get("driveFile", {})
            title, file_id = file.get("title", "ficheiro"), file.get("id")
            try:
                meta = drive.files().get(fileId=file_id, fields="mimeType,name").execute()
                mime = meta.get("mimeType", "")
                if mime in _EXPORTS:
                    text = drive.files().export(fileId=file_id, mimeType=_EXPORTS[mime]).execute()
                    text = text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text)
                elif mime == "application/pdf":
                    text = _pdf_text(drive.files().get_media(fileId=file_id).execute())
                elif mime.startswith("text/"):
                    text = drive.files().get_media(fileId=file_id).execute().decode("utf-8", "replace")
                else:
                    text = f"(ficheiro {mime}: abre no Classroom: {file.get('alternateLink', '')})"
            except Exception as exc:
                text = f"(não consegui ler este anexo: {exc})"
            out.append((title, text[:MAX_ATTACHMENT_CHARS]))
        elif "link" in material:
            link = material["link"]
            out.append((link.get("title") or "link", link.get("url", "")))
        elif "youtubeVideo" in material:
            video = material["youtubeVideo"]
            out.append((f"vídeo: {video.get('title', '')}", video.get("alternateLink", "")))
        elif "form" in material:
            form = material["form"]
            out.append((f"formulário: {form.get('title', '')}", form.get("formUrl", "")))
    return out


def build_prompt(course: dict, work: dict, materials: list[tuple[str, str]]) -> str:
    parts = [
        f"Tenho este trabalho da disciplina \"{course['name']}\" no Google Classroom "
        f"({due_text(work)}). Ajuda-me a fazê-lo, em português de Portugal.",
        "",
        f"TÍTULO: {work.get('title', '')}",
        f"ENUNCIADO:\n{work.get('description', '(sem descrição)')}",
    ]
    for title, text in materials:
        parts += ["", f"--- ANEXO: {title} ---", text]
    parts += [
        "",
        "O que preciso:",
        "1. Faz o trabalho completo, a seguir o enunciado e os anexos.",
        "2. Faz também uma apresentação PowerPoint (.pptx) sobre o trabalho, com 8 a 12 diapositivos.",
        "3. No fim, escreve um prompt pronto a colar no Claude Design para gerar essa apresentação "
        "com um design bonito (cores, estrutura de cada diapositivo, imagens sugeridas).",
    ]
    return "\n".join(parts)


# --- conversa em passos: turma -> trabalho -> Claude ---------------------------------

_NUMBER = re.compile(r"\d+")
_ORDINALS = {"primeira": 1, "primeiro": 1, "segunda": 2, "segundo": 2, "terceira": 3, "terceiro": 3,
             "quarta": 4, "quarto": 4, "quinta": 5, "quinto": 5, "sexta": 6, "sexto": 6}


def pick_number(text: str, options: list[str]) -> int | None:
    """"3", "a terceira", "a de matemática" -> índice (0-based) na lista."""
    t = text.strip().lower()
    m = _NUMBER.search(t)
    if m and 1 <= int(m.group()) <= len(options):
        return int(m.group()) - 1
    for word, n in _ORDINALS.items():
        if re.search(rf"\b{word}\b", t) and n <= len(options):
            return n - 1
    words = [w for w in re.findall(r"\w+", t) if len(w) > 3]
    for i, option in enumerate(options):
        if words and all(w in option.lower() for w in words):
            return i
    return None


class ClassroomFlow:
    """Guarda em que passo estamos: à espera da turma, do trabalho, ou nada."""

    def __init__(self, services_factory=services, open_url=None, send_to_claude=None):
        self.services_factory = services_factory
        self.open_url = open_url
        self.send_to_claude = send_to_claude
        self.step: str | None = None
        self.courses: list[dict] = []
        self.course: dict | None = None
        self.works: list[dict] = []

    @property
    def waiting(self) -> bool:
        return self.step is not None

    def cancel(self):
        self.step, self.courses, self.course, self.works = None, [], None, []

    def start(self) -> str:
        if not configured():
            return ("Para eu entrar no teu Classroom falta autorizar o Jarvis na Google (é só uma vez). "
                    "Corre Jarvis.bat --classroom e segue os passos.")
        classroom, _ = self.services_factory()
        self.courses = list_courses(classroom)
        if not self.courses:
            return "Não encontrei turmas ativas no teu Classroom."
        self.step = "course"
        lines = ["As tuas turmas:"] + [
            f"{i}. {c['name']}" + (f" ({c['section']})" if c["section"] else "") for i, c in enumerate(self.courses, 1)
        ]
        return "\n".join(lines + ["Qual? Diz o número."])

    def choose(self, text: str) -> str:
        if self.step == "course":
            index = pick_number(text, [c["name"] for c in self.courses])
            if index is None:
                return f"Não percebi a turma. Diz um número de 1 a {len(self.courses)} (ou \"cancela\")."
            self.course = self.courses[index]
            classroom, _ = self.services_factory()
            self.works = recent_work(classroom, self.course["id"])
            if not self.works:
                self.cancel()
                return "Essa turma não tem trabalhos."
            self.step = "work"
            lines = [f"Trabalhos mais recentes de {self.course['name']}:"] + [
                f"{i}. {w.get('title', '?')} ({due_text(w)})" for i, w in enumerate(self.works, 1)
            ]
            return "\n".join(lines + ["Qual queres fazer? Diz o número."])
        if self.step == "work":
            index = pick_number(text, [w.get("title", "") for w in self.works])
            if index is None:
                return f"Não percebi o trabalho. Diz um número de 1 a {len(self.works)} (ou \"cancela\")."
            work, course = self.works[index], self.course
            self.cancel()
            return self._do(course, work)
        return "Não estava à espera de nenhuma escolha."

    def _do(self, course: dict, work: dict) -> str:
        _, drive = self.services_factory()
        materials = material_texts(drive, work)
        if self.open_url and work.get("alternateLink"):
            self.open_url(work["alternateLink"])  # para veres o trabalho no Classroom
        prompt = build_prompt(course, work, materials)
        sent = self.send_to_claude(prompt) if self.send_to_claude else False
        attached = f" com {len(materials)} anexo(s)" if materials else ""
        where = "mandei tudo ao Claude" if sent else "abri o Claude, mas não consegui colar o pedido (cola tu: está na área de transferência)"
        return (f"Abri o trabalho \"{work.get('title', '')}\" ({due_text(work)}) e {where}{attached}: "
                "pedi o trabalho feito, um PowerPoint e um prompt para o Claude Design.")
