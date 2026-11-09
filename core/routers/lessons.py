"""Admin: the teacher's guided lessons (see core/services/lesson_service.py for the spoken side).

Under /admin, so every change needs the CSRF token (core/main.py) and, over the internet, the
dashboard login (ngrok policy).
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ..repositories.lesson_repository import LEVELS, LessonRepository, level_for_grade

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/lessons", tags=["lessons"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _repo() -> LessonRepository:
    from ..repositories.factory import RepositoryFactory

    return RepositoryFactory.create_production_repository().lessons


class QuizItem(BaseModel):
    question: str = Field(min_length=1, max_length=300)
    answer: str = Field(min_length=1, max_length=120)
    why: str = Field(default="", max_length=400)


class LessonContent(BaseModel):
    hook: str = Field(default="", max_length=400)
    outcomes: List[str] = Field(default_factory=list, max_length=5)
    steps: List[str] = Field(default_factory=list, max_length=12)
    quiz: List[QuizItem] = Field(default_factory=list, max_length=5)
    safety: str = Field(default="", max_length=400)
    recap: str = Field(default="", max_length=400)


class LessonBody(BaseModel):
    id: Optional[int] = None
    title: str = Field(min_length=1, max_length=80)
    topic: str = Field(default="", max_length=40)
    levels: List[str] = Field(default_factory=lambda: list(LEVELS))
    available: bool = False
    source_document_id: Optional[int] = None
    content: LessonContent


class AvailableBody(BaseModel):
    available: bool


class DraftBody(BaseModel):
    document_id: int
    level: str = "intermediate"


@router.get("/view", response_class=HTMLResponse)
async def lessons_page(request: Request):
    return templates.TemplateResponse("lessons.html", {"request": request})


@router.get("")
async def list_lessons():
    from ..services.simple_rag_service import load_learner_grade

    repo = _repo()
    grade = load_learner_grade()
    return {
        "lessons": await repo.list_lessons(),
        "documents": await repo.list_documents(),
        "grade": grade,
        "level": level_for_grade(grade),
        "levels": list(LEVELS),
    }


@router.post("")
async def save_lesson(body: LessonBody):
    lesson = body.model_dump()
    lesson["levels"] = [x for x in LEVELS if x in body.levels] or list(LEVELS)
    lesson["content"]["steps"] = [s.strip() for s in lesson["content"]["steps"] if s.strip()]
    lesson["content"]["outcomes"] = [s.strip() for s in lesson["content"]["outcomes"] if s.strip()]
    if not lesson["content"]["steps"]:
        raise HTTPException(status_code=400, detail="A lesson needs at least one step.")
    repo = _repo()
    if body.id and not await repo.get_lesson(body.id):
        raise HTTPException(status_code=404, detail="That lesson no longer exists.")
    lesson_id = await repo.save_lesson(lesson)
    return {"id": lesson_id, "lesson": await repo.get_lesson(lesson_id)}


@router.post("/draft")
async def draft(body: DraftBody):
    """The AI's draft of a lesson from an uploaded sheet. Not saved: the teacher checks it first."""
    from ..services.lesson_drafter import draft_lesson
    from ..services.simple_rag_service import load_language_strings

    repo = _repo()
    text = await repo.document_text(body.document_id)
    if not text.strip():
        raise HTTPException(status_code=404, detail="That document has no text to make a lesson from.")
    level = body.level if body.level in LEVELS else "intermediate"
    try:
        result = await asyncio.to_thread(draft_lesson, text, level, load_language_strings().get("name", "English"))
    except Exception as e:
        logger.error(f"Lesson draft failed: {e}")
        raise HTTPException(status_code=503, detail=f"The draft didn't work: {e}")
    return {**result, "levels": [level], "source_document_id": body.document_id}


@router.post("/{lesson_id}/available")
async def set_available(lesson_id: int, body: AvailableBody):
    if not await _repo().set_available(lesson_id, body.available):
        raise HTTPException(status_code=404, detail="Lesson not found")
    return {"id": lesson_id, "available": body.available}


@router.delete("/{lesson_id}")
async def delete_lesson(lesson_id: int):
    if not await _repo().delete_lesson(lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    return {"deleted": lesson_id}


@router.get("/results")
async def results():
    return {"results": await _repo().list_results()}
