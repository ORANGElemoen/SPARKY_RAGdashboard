"""Device-facing pack endpoints, tested on a minimal app with a fake device key."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.repositories.device_repository import Device
from core.routers import device_auth, device_pack
from core.services import device_commands
from core.services import studio_service as studio


@pytest.fixture(autouse=True)
def tmp_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO_DIR", tmp_path)
    monkeypatch.setattr(studio, "VOICE_DIR", tmp_path / "voice")
    monkeypatch.setattr(studio, "STORE", tmp_path / "studio.json")
    monkeypatch.setattr(studio, "SYNC_STORE", tmp_path / "device_sync.json")


def _client(device):
    app = FastAPI()
    app.include_router(device_pack.router)
    app.dependency_overrides[device_auth.get_device_from_key] = lambda: device
    return TestClient(app)


SPARKY = Device(id=7, name="Test Sparky", created_at="2026-10-20", last_seen_at=None, revoked_at=None)


def test_browser_without_key_is_refused():
    assert _client(None).get("/api/v1/device/pack").status_code == 401


def test_pack_then_304_when_unchanged():
    c = _client(SPARKY)
    first = c.get("/api/v1/device/pack")
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert etag == f'"{first.json()["pack_version"]}"'
    again = c.get("/api/v1/device/pack", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""


def test_unknown_voice_file_is_404_not_500():
    c = _client(SPARKY)
    assert c.get("/api/v1/device/pack/voice/" + "0" * 32 + ".wav").status_code == 404
    assert c.get("/api/v1/device/pack/voice/..%2Fstudio.wav").status_code == 404


def test_ack_is_recorded_per_device():
    c = _client(SPARKY)
    r = c.post("/api/v1/device/pack/ack", json={"pack_version": "abcd1234abcd1234", "free_bytes": 800000})
    assert r.status_code == 200
    assert studio.device_sync()["7"]["pack_version"] == "abcd1234abcd1234"
    bad = c.post("/api/v1/device/pack/ack", json={"pack_version": "x" * 65, "free_bytes": 1})
    assert bad.status_code == 422


def test_commands_204_then_face(monkeypatch):
    monkeypatch.setattr(device_commands, "board", device_commands.CommandBoard())
    c = _client(SPARKY)
    assert c.get("/api/v1/device/commands?wait=0").status_code == 204
    face = ["#" * 32] * 8
    device_commands.board.post(7, {"type": "show_face", "rows": face, "seconds": 10})
    r = c.get("/api/v1/device/commands?wait=0")
    assert r.status_code == 200 and r.json()["rows"] == face


def test_status_report_is_kept_alongside_sync():
    c = _client(SPARKY)
    r = c.post("/api/v1/device/status", json={"rssi": -67, "answer_audio_s": 25.4, "answer_stalls": 2,
                                               "answer_stall_ms": 900, "answer_latency_ms": 3100,
                                               "answer_complete": True, "uptime_s": 420})
    assert r.status_code == 200
    c.post("/api/v1/device/pack/ack", json={"pack_version": "abcd1234abcd1234", "free_bytes": 1})
    rec = studio.device_sync()["7"]
    assert rec["rssi"] == -67 and rec["answer_stalls"] == 2 and rec["pack_version"] == "abcd1234abcd1234"
    assert rec["answer_latency_ms"] == 3100 and rec["answer_complete"] is True and rec["uptime_s"] == 420
    assert c.post("/api/v1/device/status", json={"rssi": 5}).status_code == 422   # not a real signal level
