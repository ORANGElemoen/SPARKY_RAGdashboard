"""The sync decision the fake Sparky (and the ESP32) make."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("fake_sparky", Path(__file__).parent.parent / "scripts" / "fake_sparky.py")
fake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fake)


def manifest(*lines):
    return {"voice_lines": [{"id": i, "bytes": b, "trigger": "custom", "mood": "idle"} for i, b in lines]}


def test_downloads_only_missing_or_wrong_size_and_deletes_leftovers():
    m = manifest(("a" * 32, 100), ("b" * 32, 200), ("c" * 32, 300))
    have = {"a" * 32: 100, "b" * 32: 150, "z" * 32: 999}     # b is truncated, z is no longer used
    download, delete = fake.plan_sync(m, have)
    assert [v["id"] for v in download] == ["b" * 32, "c" * 32]
    assert delete == ["z" * 32]


def test_face_art():
    art = fake.face_art(["#" + "." * 31] * 8).splitlines()
    assert len(art) == 8 and art[0].startswith("@") and art[0][1] == " "
