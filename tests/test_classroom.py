import pytest

from jarvis.actions import classroom
from jarvis.actions.classroom import ClassroomFlow, build_prompt, due_text, material_texts, pick_number
from jarvis.brain import Brain
from jarvis.tools import ToolExecutor
from tests.test_brain import FakeLLM, FakeMessenger


class _Req:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeClassroom:
    def __init__(self, courses, works):
        self._courses, self._works = courses, works
        self.asked = []

    def courses(self):
        return self

    def courseWork(self):
        return self

    def list(self, **kw):
        if "courseId" in kw:
            self.asked.append(kw["courseId"])
            return _Req({"courseWork": self._works.get(kw["courseId"], [])})
        return _Req({"courses": self._courses})


class FakeDrive:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self

    def get(self, fileId, fields):
        return _Req({"mimeType": self._files[fileId][0]})

    def export(self, fileId, mimeType):
        return _Req(self._files[fileId][1].encode())

    def get_media(self, fileId):
        return _Req(self._files[fileId][1].encode())


COURSES = [{"id": "c1", "name": "Matemática", "section": "12.º B"}, {"id": "c2", "name": "História"}]
WORKS = {"c2": [
    {"title": "Revolução Francesa", "description": "Explica as causas.", "alternateLink": "https://classroom/w1",
     "dueDate": {"day": 3, "month": 10}, "materials": [
         {"driveFile": {"driveFile": {"id": "f1", "title": "Guião"}}},
         {"link": {"title": "Fonte", "url": "https://ex.pt"}},
     ]},
    {"title": "Ficha 2"},
]}


@pytest.fixture
def flow(monkeypatch):
    monkeypatch.setattr(classroom, "configured", lambda: True)
    room = FakeClassroom(COURSES, WORKS)
    drive = FakeDrive({"f1": ("application/vnd.google-apps.document", "Faz 5 páginas.")})
    opened, sent = [], []
    f = ClassroomFlow(services_factory=lambda: (room, drive), open_url=opened.append,
                      send_to_claude=lambda p: sent.append(p) or True)
    return f, opened, sent


def test_full_flow_course_then_work_sends_everything_to_claude(flow):
    f, opened, sent = flow
    text = f.start()
    assert "1. Matemática (12.º B)" in text and "2. História" in text and f.waiting
    text = f.choose("2")
    assert "1. Revolução Francesa (entrega 03/10)" in text and "2. Ficha 2 (sem prazo)" in text
    text = f.choose("o primeiro")
    assert not f.waiting
    assert opened == ["https://classroom/w1"]
    assert "Explica as causas." in sent[0] and "Faz 5 páginas." in sent[0] and "https://ex.pt" in sent[0]
    assert "PowerPoint" in sent[0] and "Claude Design" in sent[0]
    assert "mandei tudo ao Claude" in text


def test_invalid_choice_asks_again(flow):
    f, _, _ = flow
    f.start()
    assert "de 1 a 2" in f.choose("7")
    assert f.waiting


def test_not_configured_explains_setup(monkeypatch):
    monkeypatch.setattr(classroom, "configured", lambda: False)
    assert "--classroom" in ClassroomFlow(services_factory=lambda: None).start()


@pytest.mark.parametrize("text,expected", [("3", 2), ("a segunda", 1), ("matemática", 0), ("xyz", None)])
def test_pick_number(text, expected):
    assert pick_number(text, ["Matemática", "História", "Física"]) == expected


def test_material_texts_handles_errors():
    class Broken(FakeDrive):
        def get(self, fileId, fields):
            raise RuntimeError("403")

    out = material_texts(Broken({}), {"materials": [{"driveFile": {"driveFile": {"id": "x", "title": "A"}}}]})
    assert out[0][0] == "A" and "não consegui" in out[0][1]


def test_due_text_with_time():
    assert due_text({"dueDate": {"day": 1, "month": 2}, "dueTime": {"hours": 23, "minutes": 59}}) == "entrega 01/02 às 23:59"
    assert "TÍTULO: X" in build_prompt({"name": "M"}, {"title": "X"}, [])


def test_brain_routes_classroom_without_the_model(flow):
    f, _, sent = flow
    executor = ToolExecutor(messenger=FakeMessenger())
    executor.classroom = f
    brain = Brain(llm=FakeLLM([]), executor=executor)
    assert "As tuas turmas" in brain.handle("jarvis faz um trabalho")
    assert "Trabalhos mais recentes" in brain.handle("2")
    assert "mandei tudo ao Claude" in brain.handle("1")
    assert sent


def test_brain_cancel_classroom(flow):
    f, _, _ = flow
    executor = ToolExecutor(messenger=FakeMessenger())
    executor.classroom = f
    brain = Brain(llm=FakeLLM([]), executor=executor)
    brain.handle("abre o classroom")
    assert "deixei" in brain.handle("cancela")
    assert not f.waiting
