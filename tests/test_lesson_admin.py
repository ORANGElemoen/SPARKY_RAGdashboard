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


def test_a_result_in_detail_and_re_marking(tmp_path, monkeypatch):
    """A whole lesson through Sparky, then the teacher's view: quiz marks, sources and re-marking."""
    import asyncio

    from core.repositories.interaction_log_repository import InteractionLogRepository
    from core.services import simple_rag_service as rag
    from core.services.lesson_service import LessonService

    db = str(tmp_path / "all.db")
    repo, log = LessonRepository(db), InteractionLogRepository(db)
    with repo.get_connection() as conn:
        conn.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, filename TEXT, original_filename TEXT)")
        conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, document_id INTEGER, chunk_index INTEGER, text_content TEXT)")
        conn.execute("INSERT INTO documents VALUES (7, 'f.pdf', 'Lemon Battery.pdf')")
        conn.execute("INSERT INTO chunks VALUES (41, 7, 0, 'Zinc gives away electrons to the copper.')")
        conn.commit()
    two_steps = {**LESSON["content"], "steps": ["Roll the lemons.", "Push in a coin and a nail."]}
    asyncio.run(repo.save_lesson({**LESSON, "content": two_steps, "available": True, "source_document_id": 7}))

    class OneSheet:
        async def search_similar_text(self, query, limit, threshold):
            class Item:
                id, document_id, text_content = 41, 7, "Zinc gives away electrons to the copper."
                metadata = {"similarity_score": 0.62, "document_name": "Lemon Battery.pdf"}

            class Result:
                items = [Item()]
            return Result()

    class Model:
        model = "fake"

        def generate_answer(self, query, **kwargs):
            if "Reply YES if the child" in query:
                return "NO"
            return "QUESTION" if "Decide what kind" in query else "Zinc gives electrons away. Can you guess why?"

        def generate_stream(self, prompt, **kwargs):
            yield "Zinc gives electrons away. Can you guess why?"

    lessons = LessonService(repo, Model(), grade_loader=lambda: "")
    service = rag.SimpleRAGService(OneSheet(), Model(), log, lessons=lessons)

    async def conversation():
        for text in ["lesson", "yes", "next", "Why does zinc matter for the battery here?", "next", "next", "brass"]:
            await service.answer_query(text, query_type="text", session_id="s")
            await asyncio.sleep(0.05)   # the log is written in the background
    asyncio.run(conversation())

    monkeypatch.setattr(lessons_router, "_repo", lambda: repo)
    monkeypatch.setattr(lessons_router, "_interaction_log", lambda: log)
    app = FastAPI()
    app.include_router(lessons_router.router)
    api = TestClient(app)

    progress_id = api.get("/admin/lessons/results").json()["results"][0]["id"]
    detail = api.get(f"/admin/lessons/results/{progress_id}").json()
    assert detail["progress"]["score"] == 0 and detail["lesson_source"] == "Lemon Battery.pdf"
    [answer] = detail["answers"]
    assert answer["given"] == "brass" and answer["expected"] == "Copper" and answer["marked_by"] == "ai"
    assert answer["correct"] is False

    turns = detail["turns"]
    assert [t["question_text"] for t in turns][:2] == ["lesson", "yes"] and turns[0]["from_lesson"]
    asked = next(t for t in turns if t["question_text"].startswith("Why does zinc"))
    assert not asked["from_lesson"] and asked["sources"][0]["document_name"] == "Lemon Battery.pdf"
    assert asked["sources"][0]["similarity"] == 0.62 and "electrons" in asked["sources"][0]["text"]

    remarked = api.post(f"/admin/lessons/results/{progress_id}/answers/{answer['id']}", json={"correct": True}).json()
    assert remarked["score"] == 1
    answer = api.get(f"/admin/lessons/results/{progress_id}").json()["answers"][0]
    assert answer["correct"] is True and answer["marked_by"] == "teacher" and answer["sparky_correct"] is False
