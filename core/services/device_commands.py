"""
One pending command per device, delivered by long-poll ("Send to Sparky now").

In memory on purpose: a pending preview is only worth anything for a few
seconds, so losing it on a server restart is fine. The server runs a single
uvicorn worker (core/main.py), so one process sees every request.
"""

import asyncio
from typing import Dict, Optional


class CommandBoard:
    def __init__(self):
        self._pending: Dict[int, dict] = {}
        self._events: Dict[int, asyncio.Event] = {}

    def _event(self, device_id: int) -> asyncio.Event:
        return self._events.setdefault(device_id, asyncio.Event())

    def post(self, device_id: int, command: dict) -> None:
        """Queue a command, replacing any older one not yet delivered."""
        self._pending[device_id] = command
        self._event(device_id).set()

    async def wait(self, device_id: int, timeout: float) -> Optional[dict]:
        """The next command for this device, or None after `timeout` seconds."""
        event = self._event(device_id)
        if device_id not in self._pending:
            try:
                await asyncio.wait_for(event.wait(), timeout)
            except asyncio.TimeoutError:
                return None
        event.clear()
        return self._pending.pop(device_id, None)


board = CommandBoard()
