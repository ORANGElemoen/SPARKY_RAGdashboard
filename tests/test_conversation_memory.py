"""Conversation memory lasts while questions keep coming: a board keeps one session for life,
so a long pause starts a new conversation."""
import asyncio
import inspect
import sqlite3

from core.repositories.interaction_log_repository import InteractionLogRepository

GAP = 60


def make_log(tmp_path, minutes_ago):
    """One turn per entry, asked that many minutes ago, oldest first."""
    path = tmp_path / "log.db"
    repo = InteractionLogRepository(str(path))
    if inspect.iscoroutinefunction(getattr(repo, "initialize", None)):
        asyncio.run(repo.initialize())
    for i, ago in enumerate(minutes_ago):
        asyncio.run(repo.log_interaction(query_type="voice", question_text=f"q{i}", answer_text="answer",
                                         used_general_knowledge=True, confidence=0.0, session_id="board"))
        with sqlite3.connect(path) as db:
            db.execute("UPDATE interaction_log SET timestamp = datetime('now', ?) WHERE question_text = ?",
                       (f"-{ago} minutes", f"q{i}"))
    return repo


def questions(repo, session="board", limit=10, gap=GAP):
    return [t["question_text"] for t in asyncio.run(repo.get_recent_turns(session, limit=limit, max_gap_minutes=gap))]


def test_a_steady_conversation_is_remembered_beyond_an_hour(tmp_path):
    # Two and a half hours of questions, never more than 40 minutes apart
    repo = make_log(tmp_path, [150, 110, 70, 30, 5])
    assert questions(repo) == ["q0", "q1", "q2", "q3", "q4"]


def test_a_long_pause_starts_a_new_conversation(tmp_path):
    repo = make_log(tmp_path, [200, 190, 20, 10])  # 170-minute pause before q2
    assert questions(repo) == ["q2", "q3"]


def test_nothing_is_remembered_after_a_long_silence(tmp_path):
    repo = make_log(tmp_path, [120, 90])  # the latest turn was 90 minutes ago
    assert questions(repo) == []


def test_the_turn_limit_still_applies(tmp_path):
    repo = make_log(tmp_path, [50, 40, 30, 20, 10])
    assert questions(repo, limit=3) == ["q2", "q3", "q4"]


def test_without_a_gap_every_turn_counts(tmp_path):
    repo = make_log(tmp_path, [300, 5])
    assert questions(repo, gap=None) == ["q0", "q1"]


def test_other_sessions_stay_private(tmp_path):
    repo = make_log(tmp_path, [10])
    assert questions(repo, session="another board") == []
