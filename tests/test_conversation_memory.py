"""Conversation memory ends after a while: a board keeps one session for life."""
import asyncio
import inspect
import sqlite3

from core.repositories.interaction_log_repository import InteractionLogRepository


def make_log(tmp_path):
    path = tmp_path / "log.db"
    repo = InteractionLogRepository(str(path))
    if inspect.iscoroutinefunction(getattr(repo, "initialize", None)):
        asyncio.run(repo.initialize())
    for question in ("old question", "recent question"):
        asyncio.run(repo.log_interaction(query_type="voice", question_text=question, answer_text="answer", used_general_knowledge=True, confidence=0.0,
                                         session_id="board"))
    with sqlite3.connect(path) as db:
        db.execute("UPDATE interaction_log SET timestamp = datetime('now', '-2 hours') "
                   "WHERE question_text = 'old question'")
    return repo


def questions(turns):
    return [t["question_text"] for t in turns]


def test_old_turns_are_left_out(tmp_path):
    repo = make_log(tmp_path)
    turns = asyncio.run(repo.get_recent_turns("board", limit=3, max_age_minutes=30))
    assert questions(turns) == ["recent question"]


def test_without_a_limit_every_turn_counts(tmp_path):
    repo = make_log(tmp_path)
    turns = asyncio.run(repo.get_recent_turns("board", limit=3))
    assert questions(turns) == ["old question", "recent question"]


def test_other_sessions_stay_private(tmp_path):
    repo = make_log(tmp_path)
    assert asyncio.run(repo.get_recent_turns("another board", limit=3, max_age_minutes=30)) == []
