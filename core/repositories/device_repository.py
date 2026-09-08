"""
Device Repository

Identity for physical clients (ESP32 tutor units) talking to the API
directly, as opposed to a browser tab. A device presents an API key via the
X-Device-Key header; only its SHA-256 hash is ever stored, matching how a
GitHub personal access token works - the plaintext key is shown once, at
creation time, and cannot be recovered afterward.

Kept in the same rag_database.db file as documents/interaction_log, per this
project's "reuse the existing DB and repository pattern" convention.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .sqlite_repository import SQLiteRepository

logger = logging.getLogger(__name__)


@dataclass
class Device:
    id: int
    name: str
    created_at: str
    last_seen_at: Optional[str]
    revoked_at: Optional[str]


class DeviceRepository(SQLiteRepository):
    """Registered hardware devices and their API keys."""

    def _init_database(self):
        with self.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at DATETIME,
                    revoked_at DATETIME
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_devices_api_key_hash "
                "ON devices (api_key_hash)"
            )
            conn.commit()
            logger.info(f"Initialized devices table at {self.db_path}")

    @staticmethod
    def _hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    async def create_device(self, name: str) -> tuple[Device, str]:
        """Create a device and return it along with its plaintext API key.

        The plaintext key is only ever available here, at creation time.
        """
        api_key = secrets.token_urlsafe(32)
        key_hash = self._hash_key(api_key)

        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO devices (name, api_key_hash) VALUES (?, ?)",
                (name, key_hash),
            )
            conn.commit()
            device_id = cursor.lastrowid

        device = await self.get_by_id(device_id)
        return device, api_key

    async def get_by_id(self, device_id: int) -> Optional[Device]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE id = ?", (device_id,)
            ).fetchone()
            return self._row_to_device(row) if row else None

    async def get_by_api_key(self, api_key: str) -> Optional[Device]:
        """Look up an active (non-revoked) device by its plaintext API key."""
        key_hash = self._hash_key(api_key)
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE api_key_hash = ? AND revoked_at IS NULL",
                (key_hash,),
            ).fetchone()
            return self._row_to_device(row) if row else None

    async def touch_last_seen(self, device_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE devices SET last_seen_at = CURRENT_TIMESTAMP WHERE id = ?",
                (device_id,),
            )
            conn.commit()

    async def list_devices(self) -> List[Device]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM devices ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_device(row) for row in rows]

    async def revoke_device(self, device_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "UPDATE devices SET revoked_at = CURRENT_TIMESTAMP "
                "WHERE id = ? AND revoked_at IS NULL",
                (device_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def count_devices(self) -> Dict[str, int]:
        with self.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM devices WHERE revoked_at IS NULL"
            ).fetchone()[0]
            return {"total": total, "active": active, "revoked": total - active}

    def _row_to_device(self, row) -> Device:
        return Device(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            last_seen_at=row["last_seen_at"],
            revoked_at=row["revoked_at"],
        )
