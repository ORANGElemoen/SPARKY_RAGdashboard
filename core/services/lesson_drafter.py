"""
Drafts a guided lesson from an uploaded sheet with the local model, for the teacher to check.

The draft is never offered to learners by itself: the teacher reviews and edits it on the
Lessons page and switches it on. Ollama's structured output (a JSON schema) keeps the reply in
the lesson format; anything missing or too long is tidied here.
"""

import json
import logging
from typing import Any, Dict, List

import requests

from ..ollama_client import KEEP_ALIVE, NUM_CTX, OllamaClient

logger = logging.getLogger(__name__)

MAX_SOURCE_CHARS = 12000  # about 3,000 tokens of sheet, well inside NUM_CTX

LEVEL_WORDING = {
    "easy": "young children in Grade R to 3 (ages 5 to 9): very short sentences and everyday words",
    "intermediate": "children in Grade 4 to 6 (ages 9 to 12): short sentences, simple science words explained",
    "advanced": "learners in Grade 7 and up (ages 12+): proper science words, still friendly and clear",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "topic": {"type": "string"},
        "hook": {"type": "string"},
        "outcomes": {"type": "array", "items": {"type": "string"}},
        "steps": {"type": "array", "items": {"type": "string"}},
        "quiz": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"}, "answer": {"type": "string"}, "why": {"type": "string"}},
            "required": ["question", "answer", "why"]}},
        "safety": {"type": "string"},
        "recap": {"type": "string"},
    },
    "required": ["title", "topic", "hook", "outcomes", "steps", "quiz", "safety", "recap"],
}

PROMPT = """You are writing a short spoken lesson for Sparky, a friendly robot that teaches children science.
Sparky will read every part OUT LOUD, so write the way you speak: no lists, symbols, numbering, headings or emojis.
Write in {language}, for {level}.

Use only the activity in the SHEET below. Fill in:
- title: a short name for the lesson, 2 to 5 words.
- topic: one or two words, for example "electricity".
- hook: one exciting sentence that makes a child curious.
- outcomes: 2 or 3 things the child will learn, each a short phrase that follows "Today you will learn",
  for example "how a lemon can make electricity".
- steps: 3 to 6 steps for doing the activity, one sentence or two each, in order.
  Include the grown-up and safety advice from the sheet in the step where it matters.
- quiz: 3 questions about the lesson with short answers (one to three words) and, in "why",
  one sentence explaining the answer.
- safety: the sheet's most important safety rule, as one sentence (start with "Remember,").
- recap: one sentence summing up what the child learned.

SHEET:
{sheet}
"""


def _clean_list(items, limit: int) -> List[str]:
    return [str(x).strip() for x in (items or []) if str(x).strip()][:limit]


def tidy(draft: Dict[str, Any]) -> Dict[str, Any]:
    """Keep the lesson format whatever the model returned."""
    quiz = []
    for q in (draft.get("quiz") or [])[:5]:
        if isinstance(q, dict) and str(q.get("question", "")).strip() and str(q.get("answer", "")).strip():
            quiz.append({k: str(q.get(k, "")).strip() for k in ("question", "answer", "why")})
    return {
        "title": str(draft.get("title") or "").strip()[:80],
        "topic": str(draft.get("topic") or "").strip()[:40],
        "content": {
            "hook": str(draft.get("hook") or "").strip(),
            "outcomes": _clean_list(draft.get("outcomes"), 3),
            "steps": _clean_list(draft.get("steps"), 8),
            "quiz": quiz,
            "safety": str(draft.get("safety") or "").strip(),
            "recap": str(draft.get("recap") or "").strip(),
        },
    }


def draft_lesson(sheet_text: str, level: str, language: str = "English", timeout: int = 240) -> Dict[str, Any]:
    """A lesson draft (title, topic, content) from a sheet's text. Raises on failure."""
    if not sheet_text.strip():
        raise ValueError("That document has no text to make a lesson from.")
    local = OllamaClient(timeout=timeout)
    prompt = PROMPT.format(language=language, level=LEVEL_WORDING.get(level, LEVEL_WORDING["intermediate"]),
                           sheet=sheet_text[:MAX_SOURCE_CHARS])
    response = requests.post(
        f"{local.base_url}/api/generate",
        json={"model": local.model, "prompt": prompt, "stream": False, "think": False, "format": SCHEMA,
              "keep_alive": KEEP_ALIVE, "options": {"num_ctx": NUM_CTX, "temperature": 0.3, "num_predict": 1500}},
        timeout=timeout,
    )
    response.raise_for_status()
    raw = response.json().get("response", "")
    try:
        draft = json.loads(raw)
    except ValueError:
        logger.error(f"Lesson draft was not valid JSON: {raw[:300]}")
        raise ValueError("The AI's draft came back incomplete. Please try again.")
    return tidy(draft)
