"""Personality pack: what a Sparky downloads over Wi-Fi, and the sync record it reports back."""

import io
import math
import struct
import wave

import pytest

from core.services import studio_service as studio


@pytest.fixture(autouse=True)
def tmp_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO_DIR", tmp_path)
    monkeypatch.setattr(studio, "VOICE_DIR", tmp_path / "voice")
    monkeypatch.setattr(studio, "STORE", tmp_path / "studio.json")
    monkeypatch.setattr(studio, "SYNC_STORE", tmp_path / "device_sync.json")


def _tone(rate=22050, seconds=0.5):
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(rate * seconds)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def test_pack_has_everything_a_device_needs():
    line = studio.add_voice_line("Hello!", "startup", "happy", _tone())
    pack = studio.build_pack()
    assert pack["protocol_version"] == 1 and pack["sample_rate"] == 16000
    assert pack["mood_order"] == studio.MOODS
    assert set(pack["moods"]) == set(studio.MOODS)
    assert all(pack["moods"][m] in pack["faces"] for m in studio.MOODS)
    assert pack["voice_lines"] == [{"id": line["id"], "trigger": "startup", "mood": "happy", "bytes": line["bytes"]}]
    assert len(pack["pack_version"]) == 16


def test_version_is_stable_and_changes_with_content():
    first = studio.build_pack()["pack_version"]
    assert studio.build_pack()["pack_version"] == first
    studio.put_face("New face", ["#" * 32] + ["." * 32] * 7)
    second = studio.build_pack()["pack_version"]
    assert second != first
    studio.set_moods({"happy": "New face"})
    assert studio.build_pack()["pack_version"] != second


def test_missing_voice_file_is_left_out_of_the_pack():
    line = studio.add_voice_line("Bye!", "goodbye", "idle", _tone())
    (studio.VOICE_DIR / f"{line['id']}.wav").unlink()
    assert studio.build_pack()["voice_lines"] == []


def test_device_sync_record():
    studio.record_device_sync(7, "abcd1234abcd1234", 900000)
    studio.record_device_sync(8, "ffff0000ffff0000", 1000, error="not enough space")
    sync = studio.device_sync()
    assert sync["7"]["pack_version"] == "abcd1234abcd1234" and sync["7"]["error"] is None
    assert sync["8"]["error"] == "not enough space"
    assert "at" in sync["7"]
