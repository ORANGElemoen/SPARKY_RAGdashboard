"""
Interaction Log Repository

Persistent record of every question/answer exchange, kept separate from
the RAG content library (documents/chunks/embeddings) so it survives
independently of document/index changes and can be reviewed in full later.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from .sqlite_repository import SQLiteRepository

logger = logging.getLogger(__name__)


class InteractionLogRepository(SQLiteRepository):
    """Logs every question/answer exchange for later manual review."""

    def _init_database(self):
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    query_type TEXT NOT NULL,
                    question_text TEXT NOT NULL,
                    answer_text TEXT NOT NULL,
                    used_general_knowledge BOOLEAN NOT NULL DEFAULT 0,
                    confidence REAL,
                    chunk_ids TEXT,
                    document_ids TEXT,
                    session_id TEXT,
                    rating TEXT,
                    promoted_document_id INTEGER,
                    device_id INTEGER
                )
                """
            )

            # Migrate tables created before these columns existed
            cursor = conn.execute("PRAGMA table_info(interaction_log)")
            columns = [row[1] for row in cursor.fetchall()]
            if "session_id" not in columns:
                conn.execute("ALTER TABLE interaction_log ADD COLUMN session_id TEXT")
                logger.info("Added session_id column to interaction_log")
            if "rating" not in columns:
                conn.execute("ALTER TABLE interaction_log ADD COLUMN rating TEXT")
                logger.info("Added rating column to interaction_log")
            if "promoted_document_id" not in columns:
                conn.execute(
                    "ALTER TABLE interaction_log ADD COLUMN promoted_document_id INTEGER"
                )
                logger.info("Added promoted_document_id column to interaction_log")
            if "device_id" not in columns:
                conn.execute("ALTER TABLE interaction_log ADD COLUMN device_id INTEGER")
                logger.info("Added device_id column to interaction_log")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_log_timestamp "
                "ON interaction_log (timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_log_session "
                "ON interaction_log (session_id)"
            )
            conn.commit()
            logger.info(f"Initialized interaction_log table at {self.db_path}")

    async def log_interaction(
        self,
        query_type: str,
        question_text: str,
        answer_text: str,
        used_general_knowledge: bool,
        confidence: float,
        sources: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        device_id: Optional[int] = None,
    ) -> None:
        """Persist one question/answer exchange.

        Never raises - a logging failure must never affect the response
        already sent to the user (see callers, which fire this off via
        asyncio.create_task rather than awaiting it inline).
        """
        try:
            sources = sources or []
            chunk_ids = [
                s["chunk_id"] for s in sources if s.get("chunk_id") is not None
            ]
            document_ids = sorted(
                {s["document_id"] for s in sources if s.get("document_id") is not None}
            )

            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO interaction_log (
                        query_type, question_text, answer_text,
                        used_general_knowledge, confidence, chunk_ids, document_ids,
                        session_id, device_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        query_type,
                        question_text,
                        answer_text,
                        used_general_knowledge,
                        confidence,
                        json.dumps(chunk_ids),
                        json.dumps(document_ids),
                        session_id,
                        device_id,
                    ),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Interaction logging failed (non-fatal): {e}")

    async def get_recent_turns(
        self, session_id: str, limit: int = 4
    ) -> List[Dict[str, str]]:
        """Most recent turns for a session, oldest first (for prompt context).

        Only question_text/answer_text are returned - this is conversation
        memory, not a review export, so it stays minimal.
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT question_text, answer_text
                    FROM interaction_log
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                )
                turns = [dict(row) for row in cursor.fetchall()]
                turns.reverse()
                return turns
        except Exception as e:
            logger.error(f"Failed to load conversation turns for session: {e}")
            return []

    async def get_interaction(self, interaction_id: int) -> Optional[Dict[str, Any]]:
        """Fetch one logged interaction by id, or None."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, query_type, question_text, answer_text,
                           used_general_knowledge, confidence, chunk_ids, document_ids,
                           session_id, rating, promoted_document_id
                    FROM interaction_log
                    WHERE id = ?
                    """,
                    (interaction_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                entry = dict(row)
                entry["chunk_ids"] = (
                    json.loads(entry["chunk_ids"]) if entry["chunk_ids"] else []
                )
                entry["document_ids"] = (
                    json.loads(entry["document_ids"]) if entry["document_ids"] else []
                )
                entry["used_general_knowledge"] = bool(entry["used_general_knowledge"])
                return entry
        except Exception as e:
            logger.error(f"Failed to load interaction {interaction_id}: {e}")
            return None

    async def set_rating(
        self,
        interaction_id: int,
        rating: Optional[str],
        promoted_document_id: Optional[int],
    ) -> None:
        """Set (or clear) an interaction's rating and its promoted-document
        link, if a thumbs-up added it to the global answer-memory pool."""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE interaction_log
                SET rating = ?, promoted_document_id = ?
                WHERE id = ?
                """,
                (rating, promoted_document_id, interaction_id),
            )
            conn.commit()

    async def get_interactions(
        self,
        limit: int = 100,
        offset: int = 0,
        session_id: Optional[str] = None,
        device_id: Optional[int] = None,
        sort_by: str = "timestamp",
    ) -> List[Dict[str, Any]]:
        """Return logged interactions, most recent first.

        sort_by="session" groups rows by session_id (nulls last), most
        recent turn first within each session - useful for reviewing one
        learner's conversation as a unit rather than an interleaved feed.

        device_id scopes to one physical device across all of its sessions -
        a device can be reused by different learners/sessions over time, so
        this is the "everything this unit has ever been asked" view, wider
        than a single session_id.
        """
        try:
            order_clause = (
                "session_id IS NULL, session_id, timestamp DESC"
                if sort_by == "session"
                else "timestamp DESC"
            )
            conditions = []
            params: List[Any] = []
            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)
            if device_id is not None:
                conditions.append("device_id = ?")
                params.append(device_id)
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params += [limit, offset]

            with self.get_connection() as conn:
                cursor = conn.execute(
                    f"""
                    SELECT id, timestamp, query_type, question_text, answer_text,
                           used_general_knowledge, confidence, chunk_ids, document_ids,
                           session_id, device_id, rating, promoted_document_id
                    FROM interaction_log
                    {where_clause}
                    ORDER BY {order_clause}
                    LIMIT ? OFFSET ?
                    """,  # nosec B608 - where_clause/order_clause are fixed strings, not user input
                    params,
                )
                results = []
                for row in cursor.fetchall():
                    entry = dict(row)
                    entry["chunk_ids"] = (
                        json.loads(entry["chunk_ids"]) if entry["chunk_ids"] else []
                    )
                    entry["document_ids"] = (
                        json.loads(entry["document_ids"])
                        if entry["document_ids"]
                        else []
                    )
                    entry["used_general_knowledge"] = bool(
                        entry["used_general_knowledge"]
                    )
                    results.append(entry)
                return results
        except Exception as e:
            logger.error(f"Failed to load interaction log: {e}")
            return []

    async def count_interactions(
        self, session_id: Optional[str] = None, device_id: Optional[int] = None
    ) -> int:
        """Total number of logged interactions, optionally scoped to a session and/or device."""
        try:
            conditions = []
            params: List[Any] = []
            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)
            if device_id is not None:
                conditions.append("device_id = ?")
                params.append(device_id)
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            with self.get_connection() as conn:
                cursor = conn.execute(
                    f"SELECT COUNT(*) FROM interaction_log {where_clause}",  # nosec B608
                    params,
                )
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to count interaction log: {e}")
            return 0
