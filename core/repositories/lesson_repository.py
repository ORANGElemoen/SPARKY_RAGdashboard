"""
Guided lessons: the teacher's lessons, and each learner's progress through one.

Stored in the main SQLite database next to the interaction log, so the backup script and the
Docker image include them without extra steps.

A lesson's content is JSON: {"hook", "outcomes": [...], "steps": [...],
"quiz": [{"question", "answer", "why"}], "safety", "recap"}. `levels` is a comma-separated
subset of LEVELS: who the lesson is for. Only lessons the teacher marked `available` are
offered to learners.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .sqlite_repository import SQLiteRepository

logger = logging.getLogger(__name__)

LEVELS = ("easy", "intermediate", "advanced")


def level_for_grade(grade: str) -> str:
    """Grade R-3 easy, 4-6 intermediate, 7 and up advanced; "" if no grade is set."""
    grade = (grade or "").strip().upper()
    if grade == "R":
        return "easy"
    if not grade.isdigit():
        return ""
    n = int(grade)
    return "easy" if n <= 3 else "intermediate" if n <= 6 else "advanced"


class LessonRepository(SQLiteRepository):
    def _init_database(self):
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lessons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    topic TEXT,
                    levels TEXT NOT NULL DEFAULT 'easy,intermediate,advanced',
                    available BOOLEAN NOT NULL DEFAULT 0,
                    source_document_id INTEGER,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lesson_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    device_id INTEGER,
                    lesson_id INTEGER,
                    lesson_title TEXT,
                    level TEXT,
                    stage TEXT NOT NULL,
                    step_index INTEGER NOT NULL DEFAULT 0,
                    quiz_index INTEGER NOT NULL DEFAULT 0,
                    score INTEGER NOT NULL DEFAULT 0,
                    quiz_total INTEGER NOT NULL DEFAULT 0,
                    offered TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME,
                    outcome TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_lesson_progress_session ON lesson_progress(session_id, finished_at)"
            )
            conn.commit()

    # ------------------------------------------------------------------ lessons
    @staticmethod
    def _lesson(row) -> Dict[str, Any]:
        lesson = dict(row)
        try:
            lesson["content"] = json.loads(lesson.get("content") or "{}")
        except ValueError:
            lesson["content"] = {}
        lesson["levels"] = [x for x in (lesson.get("levels") or "").split(",") if x]
        lesson["available"] = bool(lesson.get("available"))
        return lesson

    async def list_lessons(self, available_only: bool = False, level: str = "") -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM lessons" + (" WHERE available = 1" if available_only else "") + " ORDER BY title"
            ).fetchall()
        lessons = [self._lesson(r) for r in rows]
        if level:
            lessons = [x for x in lessons if level in x["levels"]]
        return lessons

    async def get_lesson(self, lesson_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        return self._lesson(row) if row else None

    async def save_lesson(self, lesson: Dict[str, Any]) -> int:
        """Insert (no id) or update a lesson. Returns its id."""
        levels = ",".join(x for x in LEVELS if x in (lesson.get("levels") or LEVELS))
        values = (
            lesson["title"].strip(), (lesson.get("topic") or "").strip(), levels,
            1 if lesson.get("available") else 0, lesson.get("source_document_id"),
            json.dumps(lesson.get("content") or {}, ensure_ascii=False),
        )
        with self.get_connection() as conn:
            if lesson.get("id"):
                conn.execute(
                    """UPDATE lessons SET title = ?, topic = ?, levels = ?, available = ?,
                       source_document_id = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                    (*values, lesson["id"]),
                )
                lesson_id = int(lesson["id"])
            else:
                cursor = conn.execute(
                    """INSERT INTO lessons (title, topic, levels, available, source_document_id, content)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    values,
                )
                lesson_id = cursor.lastrowid
            conn.commit()
        return lesson_id

    async def set_available(self, lesson_id: int, available: bool) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE lessons SET available = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (1 if available else 0, lesson_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    async def delete_lesson(self, lesson_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
            conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------ source sheets (for drafting)
    async def list_documents(self) -> List[Dict[str, Any]]:
        """Uploaded documents a lesson can be drafted from."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, COALESCE(original_filename, filename) AS name FROM documents ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]

    async def document_text(self, document_id: int) -> str:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT text_content FROM chunks WHERE document_id = ? ORDER BY chunk_index", (document_id,)
            ).fetchall()
        return "\n".join(r[0] or "" for r in rows)

    # ------------------------------------------------------------------ progress
    async def active_progress(self, session_id: str, max_idle_minutes: int = 60) -> Optional[Dict[str, Any]]:
        """This learner's unfinished lesson, unless it was left alone longer than max_idle_minutes."""
        with self.get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM lesson_progress
                   WHERE session_id = ? AND finished_at IS NULL
                     AND updated_at >= datetime('now', ?)
                   ORDER BY id DESC LIMIT 1""",
                (session_id, f"-{int(max_idle_minutes)} minutes"),
            ).fetchone()
        if not row:
            return None
        progress = dict(row)
        progress["offered"] = json.loads(progress["offered"]) if progress.get("offered") else []
        return progress

    async def start_progress(self, session_id: str, device_id: Optional[int], stage: str, **fields) -> int:
        # A new lesson (or menu) replaces any unfinished one
        await self.finish_open(session_id, "replaced")
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO lesson_progress (session_id, device_id, stage) VALUES (?, ?, ?)",
                (session_id, device_id, stage),
            )
            conn.commit()
            progress_id = cursor.lastrowid
        if fields:
            await self.update_progress(progress_id, **fields)
        return progress_id

    async def update_progress(self, progress_id: int, **fields) -> None:
        allowed = {"lesson_id", "lesson_title", "level", "stage", "step_index", "quiz_index", "score",
                   "quiz_total", "offered"}
        fields = {k: (json.dumps(v) if k == "offered" else v) for k, v in fields.items() if k in allowed}
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.get_connection() as conn:
            conn.execute(
                f"UPDATE lesson_progress SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*fields.values(), progress_id),
            )
            conn.commit()

    async def finish_progress(self, progress_id: int, outcome: str) -> None:
        """outcome: "completed", "stopped" or "replaced"."""
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE lesson_progress SET finished_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP, outcome = ? WHERE id = ?""",
                (outcome, progress_id),
            )
            conn.commit()

    async def finish_open(self, session_id: str, outcome: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE lesson_progress SET finished_at = CURRENT_TIMESTAMP, outcome = ?
                   WHERE session_id = ? AND finished_at IS NULL""",
                (outcome, session_id),
            )
            conn.commit()

    async def list_results(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Lessons learners actually began (not menus), newest first, for the teacher."""
        with self.get_connection() as conn:
            has_devices = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'devices'").fetchone()
            name = "d.name" if has_devices else "NULL"
            join = "LEFT JOIN devices d ON d.id = p.device_id" if has_devices else ""
            rows = conn.execute(
                f"""SELECT p.*, {name} AS device_name FROM lesson_progress p {join}
                    WHERE p.lesson_id IS NOT NULL ORDER BY p.id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
