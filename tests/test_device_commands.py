"""The one-command-per-device board behind "Send to Sparky now"."""

import asyncio

from core.services.device_commands import CommandBoard


def test_waiting_device_gets_a_command_posted_later():
    async def scenario():
        board = CommandBoard()
        waiter = asyncio.create_task(board.wait(7, timeout=2))
        await asyncio.sleep(0.05)
        board.post(7, {"type": "show_face"})
        return await waiter
    assert asyncio.run(scenario()) == {"type": "show_face"}


def test_command_posted_before_waiting_is_not_lost():
    async def scenario():
        board = CommandBoard()
        board.post(7, {"type": "show_face", "n": 1})
        board.post(7, {"type": "show_face", "n": 2})   # newer replaces older
        return await board.wait(7, timeout=0.1)
    assert asyncio.run(scenario()) == {"type": "show_face", "n": 2}


def test_timeout_returns_none_and_devices_are_separate():
    async def scenario():
        board = CommandBoard()
        board.post(8, {"type": "show_face"})
        return await board.wait(7, timeout=0.05)
    assert asyncio.run(scenario()) is None
