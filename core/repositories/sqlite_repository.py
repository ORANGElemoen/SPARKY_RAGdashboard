"""
Production SQLite Repository Implementation
Enhanced version of the existing persistent storage with repository pattern
"""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .base import QueryResult, SearchOptions
from .interfaces import IDocumentRepository
from .models import Document, DocumentStatus

logger = logging.getLogger(__name__)


class SQLiteRepository:
    """Base SQLite repository with connection management"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_local = threading.local()
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._thread_local, "connection"):
            conn = sqlite3.connect(
                str(self.db_path), check_same_thread=False, timeout=30.0
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")  # Better concurrency
            conn.execute("PRAGMA synchronous = NORMAL")  # Better performance
            self._thread_local.connection = conn
        return self._thread_local.connection

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = self._get_connection()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise

    def _run_migrations(self, conn):
        """Run database migrations for missing columns"""
        try:
            # Check current table structure
            cursor = conn.execute("PRAGMA table_info(documents)")
            columns = [row[1] for row in cursor.fetchall()]

            migrations_needed = []

            # Required columns with their types
            required_columns = {
                "file_hash": "TEXT",
                "file_path": "TEXT",
                "original_filename": "TEXT",
                "content_type": "TEXT",
                "file_size": "INTEGER",
                "upload_timestamp": "DATETIME DEFAULT CURRENT_TIMESTAMP",
                "uploader": "TEXT",
                "description": "TEXT",
                "tags": "TEXT",
                "metadata": "TEXT",
                "text_content": "TEXT",
                "chunk_count": "INTEGER DEFAULT 0",
                "embedding_count": "INTEGER DEFAULT 0",
                "processing_timestamp": "DATETIME",
                "completion_timestamp": "DATETIME",
            }

            # Check which columns are missing
            for column_name, column_type in required_columns.items():
                if column_name not in columns:
                    migrations_needed.append((column_name, column_type))

            # Apply migrations
            for column_name, column_type in migrations_needed:
                logger.info(f"Adding {column_name} column to documents table")
                conn.execute(
                    f"ALTER TABLE documents ADD COLUMN {column_name} {column_type}"
                )

            # Add indexes for new columns
            if "file_hash" in [col[0] for col in migrations_needed]:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents (file_hash)"
                )

            if migrations_needed:
                conn.commit()
                logger.info(
                    f"Database migrations completed: {len(migrations_needed)} columns added"
                )
            else:
                logger.info("No database migrations needed")

        except sqlite3.OperationalError as e:
            logger.warning(f"Migration warning: {e}")
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    def _init_database(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            # Documents table (enhanced from existing)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_path TEXT,
                    content_type TEXT,
                    file_size INTEGER,
                    status TEXT DEFAULT 'uploading',
                    upload_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processing_timestamp DATETIME,
                    completion_timestamp DATETIME,
                    uploader TEXT,
                    description TEXT,
                    tags TEXT,  -- JSON array
                    metadata TEXT,  -- JSON object
                    text_content TEXT,
                    chunk_count INTEGER DEFAULT 0,
                    embedding_count INTEGER DEFAULT 0,
                    file_hash TEXT UNIQUE,  -- For deduplication
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Chunks table (enhanced from existing)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    text_content TEXT NOT NULL,
                    character_count INTEGER,
                    word_count INTEGER,
                    start_char INTEGER,
                    end_char INTEGER,
                    quality_score REAL DEFAULT 0.0,
                    metadata TEXT,  -- JSON object
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    UNIQUE (document_id, chunk_index)
                )
            """
            )

            # Embeddings table (enhanced from existing)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chunk_id INTEGER NOT NULL,
                    document_id INTEGER NOT NULL,
                    embedding_vector BLOB NOT NULL,  -- Compressed pickle
                    embedding_model TEXT NOT NULL,
                    vector_dimension INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES chunks (id) ON DELETE CASCADE,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    UNIQUE (chunk_id, embedding_model)
                )
            """
            )

            # Run database migrations
            self._run_migrations(conn)

            # Create indexes only after ensuring all tables exist
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_uploader ON documents (uploader)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents (file_hash)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_filename ON documents (filename)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_embeddings_document ON embeddings (document_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_embeddings_chunk ON embeddings (chunk_id)"
                )
            except sqlite3.OperationalError as e:
                logger.warning(f"Some indexes could not be created: {e}")

            # Full-text search for chunks
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(text_content, content='chunks', content_rowid='id')
            """
            )

            conn.commit()
            logger.info(f"Initialized SQLite database at {self.db_path}")


class SQLiteDocumentRepository(SQLiteRepository, IDocumentRepository):
    """SQLite implementation of document repository"""

    # Virtual "documents" created from thumbs-up rated tutor answers (see
    # AnswerMemoryService) use this filename prefix so they can be kept out
    # of the normal uploaded-document list/counts without a schema change.
    TUTOR_ANSWER_FILENAME_PREFIX = "tutor_answer_"

    async def create(self, document: Document) -> Document:
        """Create a new document"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    filename, original_filename, file_path, content_type, file_size,
                    status, uploader, description, tags, metadata, file_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    document.filename,
                    document.original_filename,
                    document.file_path,
                    document.content_type,
                    document.file_size,
                    (
                        document.status.value
                        if document.status
                        else DocumentStatus.UPLOADING.value
                    ),
                    document.uploader,
                    document.description,
                    json.dumps(document.tags) if document.tags else None,
                    json.dumps(document.metadata) if document.metadata else None,
                    document.metadata.get("file_hash") if document.metadata else None,
                ),
            )

            document.id = cursor.lastrowid
            conn.commit()
            return document

    async def get_by_id(self, document_id: int) -> Optional[Document]:
        """Get document by ID"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE id = ?
            """,
                (document_id,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_document(row)

    async def update(
        self, document_id: int, updates: Dict[str, Any]
    ) -> Optional[Document]:
        """Update document"""
        # Build dynamic update query
        allowed_fields = {
            "status",
            "processing_timestamp",
            "completion_timestamp",
            "description",
            "tags",
            "metadata",
            "text_content",
            "chunk_count",
            "embedding_count",
        }

        update_fields = {k: v for k, v in updates.items() if k in allowed_fields}
        if not update_fields:
            return await self.get_by_id(document_id)

        # Handle special fields
        if "tags" in update_fields:
            update_fields["tags"] = json.dumps(update_fields["tags"])
        if "metadata" in update_fields:
            update_fields["metadata"] = json.dumps(update_fields["metadata"])
        if "status" in update_fields and hasattr(update_fields["status"], "value"):
            update_fields["status"] = update_fields["status"].value

        update_fields["updated_at"] = datetime.utcnow().isoformat()

        with self.get_connection() as conn:
            set_clause = ", ".join(f"{k} = ?" for k in update_fields.keys())
            values = list(update_fields.values()) + [document_id]

            # Safe SQL construction: set_clause built from validated allowed_fields only
            query = f"UPDATE documents SET {set_clause} WHERE id = ?"  # nosec B608
            conn.execute(query, values)

            conn.commit()
            return await self.get_by_id(document_id)

    async def delete(self, document_id: int) -> bool:
        """Delete document and all associated data"""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            conn.commit()
            return cursor.rowcount > 0

    async def get_by_filename(self, filename: str) -> Optional[Document]:
        """Get document by filename"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE filename = ? OR original_filename = ?
            """,
                (filename, filename),
            )

            row = cursor.fetchone()
            return self._row_to_document(row) if row else None

    async def get_by_hash(self, file_hash: str) -> Optional[Document]:
        """Get document by file hash"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE file_hash = ?
            """,
                (file_hash,),
            )

            row = cursor.fetchone()
            return self._row_to_document(row) if row else None

    async def list_all(
        self, options: Optional[SearchOptions] = None
    ) -> QueryResult[Document]:
        """List all documents with pagination"""
        if not options:
            options = SearchOptions()

        offset = (options.page - 1) * options.page_size

        with self.get_connection() as conn:
            # Count query (excluding virtual tutor-answer documents)
            count_cursor = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE filename NOT LIKE ?",
                (f"{self.TUTOR_ANSWER_FILENAME_PREFIX}%",),
            )
            total_count = count_cursor.fetchone()[0]

            # Data query
            cursor = conn.execute(
                """
                SELECT * FROM documents
                WHERE filename NOT LIKE ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """,
                (f"{self.TUTOR_ANSWER_FILENAME_PREFIX}%", options.page_size, offset),
            )

            documents = [self._row_to_document(row) for row in cursor.fetchall()]

            return QueryResult(
                items=documents,
                total_count=total_count,
                page=options.page,
                page_size=options.page_size,
                has_more=offset + len(documents) < total_count,
            )

    def _safe_status(self, status_value):
        """Safely convert status string to DocumentStatus enum"""
        if not status_value:
            return DocumentStatus.UPLOADING

        try:
            return DocumentStatus(status_value)
        except ValueError:
            # Handle legacy or unknown status values
            logger.warning(
                f"Unknown document status '{status_value}', defaulting to UPLOADING"
            )
            return DocumentStatus.UPLOADING

    def _row_to_document(self, row) -> Document:
        """Convert database row to Document object"""

        # Helper function to safely get row values
        def safe_get(key, default=None):
            try:
                return row[key] if key in row.keys() else default
            except (KeyError, IndexError):
                return default

        # Helper function to parse datetime safely
        def safe_datetime(value):
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None

        return Document(
            id=safe_get("id"),
            filename=safe_get("filename", ""),
            original_filename=safe_get("original_filename", safe_get("filename", "")),
            file_path=safe_get("file_path", ""),
            content_type=safe_get("content_type", ""),
            file_size=safe_get("file_size", 0) or 0,
            status=self._safe_status(safe_get("status", "uploading")),
            upload_timestamp=safe_datetime(
                safe_get("upload_timestamp") or safe_get("created_at")
            ),
            processing_timestamp=safe_datetime(safe_get("processing_timestamp")),
            completion_timestamp=safe_datetime(safe_get("completion_timestamp")),
            uploader=safe_get("uploader", "anonymous"),
            description=safe_get("description"),
            tags=json.loads(safe_get("tags")) if safe_get("tags") else [],
            metadata=json.loads(safe_get("metadata")) if safe_get("metadata") else {},
            text_content=safe_get("text_content"),
            chunk_count=safe_get("chunk_count", 0) or 0,
            embedding_count=safe_get("embedding_count", 0) or 0,
        )

    # Additional interface methods
    async def exists(self, document_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM documents WHERE id = ?", (document_id,)
            )
            return cursor.fetchone() is not None

    async def find_by_hash(self, file_hash: str) -> Optional[Document]:
        """Find document by file hash"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM documents WHERE file_hash = ?
            """,
                (file_hash,),
            )

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_document(row)

    async def update_status(self, document_id: int, status: str) -> bool:
        """Update document status"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """
                    UPDATE documents
                    SET status = ?, processing_timestamp = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (status, document_id),
                )

                conn.commit()
                return cursor.rowcount > 0
        except Exception:
            return False

    async def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE filename NOT LIKE ?",
                (f"{self.TUTOR_ANSWER_FILENAME_PREFIX}%",),
            )
            return cursor.fetchone()[0]

    async def create_chunk(
        self, document_id: int, chunk_index: int, text_content: str
    ) -> int:
        """Insert one chunk row and return its id. Mirrors DocumentService's
        upload-time chunk insertion (see document_service.py _store_chunks),
        reused here so AnswerMemoryService writes chunks the same way."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO chunks (document_id, chunk_index, text_content,
                                     character_count, word_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    chunk_index,
                    text_content,
                    len(text_content),
                    len(text_content.split()),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    async def create_embedding(
        self,
        chunk_id: int,
        document_id: int,
        embedding_vector: "list[float]",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> int:
        """Insert one embedding row (gzip+pickle, matching how existing
        embeddings are stored/read - see vector_repository.py's
        _load_existing_embeddings) and return its id."""
        import gzip
        import pickle

        compressed = gzip.compress(pickle.dumps(embedding_vector))

        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO embeddings (chunk_id, document_id, embedding_vector,
                                         embedding_model, vector_dimension)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    chunk_id,
                    document_id,
                    compressed,
                    embedding_model,
                    len(embedding_vector),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    async def get_embedding_ids_for_document(
        self, document_id: int
    ) -> "list[int]":
        """Embedding IDs for a document, needed to remove it from the live
        vector index (the index is keyed by embedding id, not document id)."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM embeddings WHERE document_id = ?", (document_id,)
            )
            return [row["id"] for row in cursor.fetchall()]

    async def get_chunk_details(
        self, chunk_ids: "list[int]"
    ) -> Dict[int, Dict[str, Any]]:
        """Resolve chunk IDs to their current text and source document name.

        Used by the interaction log admin view to show the actual snippet
        a logged answer was grounded in - the log itself only stores
        chunk/document IDs (see InteractionLogRepository), so this is
        where they're joined back to live content at display time.
        """
        if not chunk_ids:
            return {}

        with self.get_connection() as conn:
            placeholders = ",".join("?" * len(chunk_ids))
            cursor = conn.execute(
                f"""
                SELECT c.id, c.text_content, c.document_id, d.original_filename
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.id IN ({placeholders})
            """,  # nosec B608 - placeholders is just repeated '?' characters
                chunk_ids,
            )

            return {
                row["id"]: {
                    "text": row["text_content"],
                    "document_id": row["document_id"],
                    "document_name": row["original_filename"],
                }
                for row in cursor.fetchall()
            }

    async def get_statistics(self) -> Dict[str, Any]:
        """Get document statistics"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_documents,
                    SUM(file_size) as total_size,
                    AVG(chunk_count) as avg_chunks_per_doc,
                    COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_docs,
                    COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing_docs,
                    COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_docs
                FROM documents
            """
            )

            row = cursor.fetchone()
            return {
                "total_documents": row[0] or 0,
                "total_size_bytes": row[1] or 0,
                "avg_chunks_per_document": row[2] or 0,
                "completed_documents": row[3] or 0,
                "processing_documents": row[4] or 0,
                "failed_documents": row[5] or 0,
            }

    async def get_by_uploader(
        self, uploader: str, options: Optional[SearchOptions] = None
    ) -> QueryResult[Document]:
        """Get documents by uploader"""
        if not options:
            options = SearchOptions()

        offset = (options.page - 1) * options.page_size

        with self.get_connection() as conn:
            # Count query
            count_cursor = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE uploader = ?", (uploader,)
            )
            total_count = count_cursor.fetchone()[0]

            # Data query
            cursor = conn.execute(
                """
                SELECT * FROM documents
                WHERE uploader = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """,
                (uploader, options.page_size, offset),
            )

            documents = [self._row_to_document(row) for row in cursor.fetchall()]

            return QueryResult(
                items=documents,
                total_count=total_count,
                page=options.page,
                page_size=options.page_size,
                has_more=offset + len(documents) < total_count,
            )
