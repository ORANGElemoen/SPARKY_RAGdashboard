"""The teacher's Lessons page API: save, edit, offer, delete, draft and results."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.repositories.lesson_repository import LessonRepository
from core.routers import lessons as lessons_router
from core.services import lesson_drafter

LESSON = {
    "title": "Lemon Battery", "topic": "electricity", "levels": ["intermediate"], "available": False,
    "content": {"hook": "Can fruit make electricity?", "outcomes": ["how a lemon makes electricity"],
                "steps": ["Roll the lemons.", "  ", "Push in a coin and a nail."],
                "quiz": [{"question": "What metal is the coin?", "answer": "Copper", "why": ""}],
                "safety": "Remember, never use a wall socket.", "recap": "Fruit and metals can make electricity."},
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = LessonRepository(str(tmp_path / "lessons.db"))
    with repo.get_connection() as conn:   # a minimal documents/chunks pair to draft from
        conn.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, filename TEXT, original_filename TEXT)")
        conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, document_id INTEGER, chunk_index INTEGER, text_content TEXT)")
        conn.execute("INSERT INTO documents VALUES (7, 'f.pdf', 'Lemon Battery.pdf')")
        conn.execute("INSERT INTO chunks VALUES (1, 7, 0, 'Roll three lemons. Push in coins and nails.')")
        conn.commit()
    monkeypatch.setattr(lessons_router, "_repo", lambda: repo)
    app = FastAPI()
    app.include_router(lessons_router.router)
    return TestClient(app)


def test_save_edit_offer_and_delete(client):
    saved = client.post("/admin/lessons", json=LESSON).json()
    assert saved["lesson"]["content"]["steps"] == ["Roll the lemons.", "Push in a coin and a nail."]  # blank line dropped
    assert saved["lesson"]["available"] is False

    lesson_id = saved["id"]
    edited = client.post("/admin/lessons", json={**LESSON, "id": lesson_id, "title": "Lemon Power"}).json()
    assert edited["id"] == lesson_id and edited["lesson"]["title"] == "Lemon Power"

    assert client.post(f"/admin/lessons/{lesson_id}/available", json={"available": True}).status_code == 200
    listing = client.get("/admin/lessons").json()
    assert listing["lessons"][0]["available"] is True
    assert listing["documents"] == [{"id": 7, "name": "Lemon Battery.pdf"}]

    assert client.delete(f"/admin/lessons/{lesson_id}").status_code == 200
    assert client.get("/admin/lessons").json()["lessons"] == []
    assert client.delete(f"/admin/lessons/{lesson_id}").status_code == 404


def test_a_lesson_needs_a_title_and_a_step(client):
    assert client.post("/admin/lessons", json={**LESSON, "title": ""}).status_code == 422
    no_steps = {**LESSON, "content": {**LESSON["content"], "steps": ["  "]}}
    assert client.post("/admin/lessons", json=no_steps).status_code == 400


def test_draft_from_a_sheet(client, monkeypatch):
    seen = {}

    def fake_draft(text, level, language):
        seen.update(text=text, level=level)
        return lesson_drafter.tidy({"title": "Lemon Light", "topic": "electricity", "hook": "Wow!",
                                    "outcomes": ["a", "b"], "steps": ["one", "two"],
                                    "quiz": [{"question": "Q?", "answer": "A", "why": "W"}],
                                    "safety": "Remember.", "recap": "Done."})
    monkeypatch.setattr(lesson_drafter, "draft_lesson", fake_draft)
    draft = client.post("/admin/lessons/draft", json={"document_id": 7, "level": "easy"}).json()
    assert seen == {"text": "Roll three lemons. Push in coins and nails.", "level": "easy"}
    assert draft["title"] == "Lemon Light" and draft["levels"] == ["easy"] and draft["source_document_id"] == 7
    assert client.get("/admin/lessons").json()["lessons"] == []      # a draft isn't saved
    assert client.post("/admin/lessons/draft", json={"document_id": 99}).status_code == 404


def test_tidy_keeps_the_lesson_format():
    tidy = lesson_drafter.tidy({"title": "x" * 200, "outcomes": ["a", "", "b", "c", "d"],
                                "quiz": [{"question": "Q", "answer": ""}, {"question": "Q2", "answer": "A2"}]})
    assert len(tidy["title"]) == 80 and tidy["content"]["outcomes"] == ["a", "b", "c"]
    assert tidy["content"]["quiz"] == [{"question": "Q2", "answer": "A2", "why": ""}]
