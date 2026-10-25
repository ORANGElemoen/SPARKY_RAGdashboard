# Sparky Wi-Fi "Personality Pack" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faces, mood mapping and voice lines designed in Sparky Studio reach the ESP32 over Wi-Fi - no Arduino IDE, no USB cable - plus a "Send to Sparky now" live preview.

**Architecture:** The server bundles the Studio content into a versioned *personality pack* (a small JSON manifest plus voice-line WAV files). Each Sparky checks in with its existing device key while idle, downloads only what changed into its flash file system (LittleFS), switches over safely, and reports which version it has. A long-poll "command" channel lets the dashboard show a face on a connected Sparky within about a second.

**Tech Stack:** Server - FastAPI, existing `studio_service` and device-key auth, pytest. Device - ESP32 (Arduino core via PlatformIO), LittleFS, HTTPClient, ArduinoJson 7, MD_MAX72XX, legacy I2S driver, FreeRTOS task. Test client - Python + httpx.

**Spec:** Part A of this document (written for the project owner to approve).

## Global Constraints

- Fully local: the ESP32 only talks to the school's own server on the local network - no cloud services (project rule, CLAUDE.md).
- Device endpoints authenticate with the existing `X-Device-Key` header (docs/PROTOCOL.md, core/routers/device_auth.py); a request with a valid key is already exempt from CSRF (core/main.py `csrf_middleware`).
- Admin endpoints stay under `/admin/` so the existing CSRF check covers them; the page sends `X-CSRF-Token` via `getCsrfToken()`.
- Face format is `sparky-faces/1`: 8 rows x 32 characters, `#` = LED on, `.` = off, top row first (core/services/studio_service.py).
- Voice lines are 16 kHz, 16-bit, mono WAV; voice-line ids are 32 lowercase hex characters and never change content (a new line always gets a new id).
- Pins (report Table "ESP32 pin map"): amplifier BCLK 27, LRC 26, DIN 22, SD/mute 21; LED matrix CLK 18, DIN 23, CS 5; button 14.
- Sparky never syncs or previews while it is listening, thinking or talking - only when idle.
- `docs/PROTOCOL.md` stays the single source of truth for the device wire format; its `protocol_version` stays 1 (the pack is a purely additive set of new endpoints).

---

# Part A - How it works (plain English)

## The short answer

Yes. After the Sparky program has been put on the ESP32 **once**, everything you make in Sparky Studio can reach Sparky over Wi-Fi:

- new or changed **faces**,
- which face goes with which **mood**,
- new **voice lines** in Sparky's voice.

You press **Save** in the Studio, and within a few minutes every Sparky in the classroom has it - no cable, no Arduino IDE. There is also a **"Send to Sparky now"** button that shows a face on a Sparky straight away, so you can see your drawing on the real LEDs while you design it.

(The program itself still has to get onto the ESP32 the first time. Part B, decision 4, covers doing even that from a web browser instead of the Arduino IDE.)

## The idea: a "personality pack"

Think of it like a phone downloading new stickers for a chat app. The app (Sparky's program) stays the same; only the stickers (faces and voice lines) change.

1. **You design** faces and voice lines in Sparky Studio, exactly as you do now.
2. **The server packs them up** into a "personality pack" with a version code - a short fingerprint like `3f9a1c07...`. Change anything and the fingerprint changes.
3. **Sparky checks in** when it switches on, and every few minutes while nobody is talking to it: *"I have pack 3f9a1c07 - anything new?"*
   - Nothing new: the server answers "no" in a tiny reply. This costs almost nothing.
   - Something new: Sparky gets the list of faces, moods and voice lines.
4. **Sparky downloads only what it doesn't have yet.** Faces are tiny (a few bytes each). Voice lines are small sound files, stored in the ESP32's own flash memory.
5. **Safe swap.** Sparky downloads everything first and only switches to the new pack once it is complete. If the power is cut halfway, it keeps using its old pack and simply tries again later. If something ever goes really wrong, it falls back to the faces built into its program.
6. **Sparky reports back** *"I now have pack 3f9a1c07"*, so the Studio can show a list of your Sparkys with **"Up to date"** or **"Waiting to update"** next to each one.

## "Send to Sparky now" (live preview)

While Sparky is idle it keeps a "listening line" open to the server: it asks *"anything for me?"* and the server holds that question open for up to 25 seconds. When you press **Send to Sparky now** in the Studio, the server answers immediately with your face, and Sparky shows it for 10 seconds, then goes back to normal. Because the line is already open, it appears in about a second.

## What changes for you

| Today (Stage 1) | After this plan |
|---|---|
| Design in the Studio | Design in the Studio |
| Download `sparky_faces.h` | - |
| Open the Arduino IDE, copy the file in, upload over USB | - |
| Repeat for every Sparky | Every Sparky updates itself over Wi-Fi |
| Can't preview on the real LEDs without uploading | "Send to Sparky now" shows it in about a second |

The firmware download (`sparky_faces.h`) stays available as a backup.

## Limits to know about

- **Storage:** the ESP32 has about 1.3 MB of space for voice lines - roughly **40 seconds of speech** in total, or 20-30 short lines. The Studio's space meter already tracks this. Faces use almost no space.
- **Timing:** updates arrive within a few minutes, never in the middle of a conversation. Sparky only updates when idle.
- **Network:** Sparky must be switched on and connected to the same Wi-Fi as the server - which it already needs to answer questions.
- **Safety:** only Sparkys registered on the Devices page (with their own key) can download packs or receive previews. Revoking a device on the Devices page stops it immediately. Packs contain only faces and voice lines - never anything a child said.

## How we will test it before the hardware is ready

A small program on the PC, `scripts/fake_sparky.py`, pretends to be a Sparky: it checks in, downloads the pack into a folder, reports back, and prints any "Send to Sparky now" face in the terminal as LED art. That proves the whole Wi-Fi side works before the real ESP32 code is written - and it is also the reference the ESP32 code copies.

---

# Part B - Decisions for you

1. **How often Sparky checks for a new pack while idle.** Recommended: every **5 minutes** (plus at switch-on and right after any "Send to Sparky now"). Shorter is snappier but chattier on the Wi-Fi.
2. **Live preview ("Send to Sparky now").** Recommended: **yes**. It costs one open connection per idle Sparky.
3. **Storage split on the ESP32.** Recommended: the **standard split** (about 1.3 MB for voice lines), which also keeps room for updating Sparky's *program* over Wi-Fi later. The alternative gives about 2 MB for voice lines but rules out program updates over Wi-Fi.
4. **Installing the program without the Arduino IDE** (not in this plan's tasks - a small follow-up). Recommended: **yes, later**. A "Install Sparky" button on the Studio page uses Chrome's built-in USB support (the free ESP Web Tools project) to put the program on a brand-new ESP32 from the browser. After that, program updates can also come over Wi-Fi.

---

# Part C - Implementation plan

## File structure

| File | Responsibility |
|---|---|
| `core/services/studio_service.py` (modify) | `build_pack()` - the manifest + version; `record_device_sync()` / `device_sync()` - which pack each device has |
| `core/services/device_commands.py` (create) | In-memory "one pending command per device" board for the live-preview long-poll |
| `core/routers/device_pack.py` (create) | Device-facing endpoints: pack, voice file, ack, commands (device key required) |
| `core/routers/studio.py` (modify) | Admin endpoints: list devices with sync status; send a preview face |
| `core/main.py` (modify) | Register the new router |
| `core/templates/studio.html` (modify) | "Your Sparkys" section + "Send to Sparky now" |
| `scripts/fake_sparky.py` (create) | Reference device in Python: sync + preview, used for end-to-end testing |
| `docs/PROTOCOL.md` (modify) | Document the pack endpoints for firmware |
| `tests/test_pack.py`, `tests/test_device_pack_api.py`, `tests/test_fake_sparky.py` (create) | Tests |
| `firmware/sparky/platformio.ini` + `src/*.cpp/.h` (create) | ESP32 program: Wi-Fi settings, pack sync to LittleFS, faces from the pack, voice playback, live preview |

**Note on existing firmware:** the Wi-Fi bring-up sketch lives outside the repo at `C:\Users\user\OneDrive\Documents\Arduino\libraries\Sparky_Wifi_Setup.ino\Sparky_Wifi_Setup\Sparky_Wifi_Setup.ino` (WiFiManager portal with Sparky styling, "Sparky Setup" / `sparky123` hotspot, optional class code, `/health` and test voice-query calls with a hard-coded server and device key). Task 7 ports its portal into `settings.cpp` and changes two things: it stops calling `wm.resetSettings()` on every boot, and the server address and device key move from the code into the setup page. The device key in that sketch must not be copied into this public repo. The sketch's `testVoiceQuery()` (multipart upload to `/api/v1/voice/query`) is the starting point for the later voice-question firmware task, which is not part of this plan.

---

### Task 1: Build the personality pack (server)

**Files:**
- Modify: `core/services/studio_service.py`
- Test: `tests/test_pack.py`

**Interfaces:**
- Produces: `studio.build_pack(data: Optional[Dict] = None) -> Dict` with keys `pack_version` (16 hex chars), `protocol_version` (1), `sample_rate` (16000), `mood_order` (list of mood names), `faces` (name -> 8 rows), `moods` (mood -> face name), `voice_lines` (list of `{id, trigger, mood, bytes}`).
- Produces: `studio.SYNC_STORE: Path`, `studio.record_device_sync(device_id: int, pack_version: str, free_bytes: int, error: Optional[str] = None) -> None`, `studio.device_sync() -> Dict[str, Dict]` keyed by `str(device_id)` with `{pack_version, free_bytes, error, at}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pack.py
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_pack.py -v -p no:warnings`
Expected: FAIL - `AttributeError: module 'core.services.studio_service' has no attribute 'SYNC_STORE'`

- [ ] **Step 3: Implement**

In `core/services/studio_service.py`:

1. Add `import hashlib` to the imports (with the other standard-library imports).
2. Under `STORE = STUDIO_DIR / "studio.json"`, add:

```python
SYNC_STORE = STUDIO_DIR / "device_sync.json"   # which pack each device reported having
```

3. Add at the end of the file:

```python
# ---------------------------------------------------------------- Wi-Fi personality pack
def build_pack(data: Optional[Dict] = None) -> Dict:
    """What a Sparky downloads over Wi-Fi: faces, mood mapping and voice-line list.

    pack_version is a fingerprint of the content, so a device can ask
    "is pack X still current?" and get a tiny "yes" (HTTP 304). Voice-line
    ids never change content, so the device only fetches ids it lacks.
    """
    data = data or load()
    lines = [{"id": v["id"], "trigger": v["trigger"], "mood": v["mood"], "bytes": v["bytes"]}
             for v in data["voice_lines"] if (VOICE_DIR / f"{v['id']}.wav").exists()]
    body = {"faces": data["faces"], "moods": {m: data["moods"][m] for m in MOODS}, "voice_lines": lines}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    version = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return {"pack_version": version, "protocol_version": 1, "sample_rate": DEVICE_SAMPLE_RATE,
            "mood_order": MOODS, **body}


def device_sync() -> Dict[str, Dict]:
    if SYNC_STORE.exists():
        return json.loads(SYNC_STORE.read_text(encoding="utf-8"))
    return {}


def record_device_sync(device_id: int, pack_version: str, free_bytes: int, error: Optional[str] = None) -> None:
    sync = device_sync()
    sync[str(device_id)] = {"pack_version": pack_version, "free_bytes": int(free_bytes), "error": error,
                            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SYNC_STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sync, indent=1), encoding="utf-8")
    tmp.replace(SYNC_STORE)
```

4. In `tests/test_studio.py`, add the new path to the existing `tmp_studio` fixture so those tests never touch the real file:

```python
    monkeypatch.setattr(studio, "SYNC_STORE", tmp_path / "device_sync.json")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_pack.py tests/test_studio.py -v -p no:warnings`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add core/services/studio_service.py tests/test_pack.py tests/test_studio.py
git commit -m "Studio: build a versioned personality pack and record device sync state"
```

---

### Task 2: Device endpoints - download the pack, its voice files, and report back

**Files:**
- Create: `core/routers/device_pack.py`
- Modify: `core/main.py` (router import list and `app.include_router(...)` block)
- Test: `tests/test_device_pack_api.py`

**Interfaces:**
- Consumes: `studio.build_pack()`, `studio.voice_path(line_id)`, `studio.record_device_sync(...)` (Task 1); `get_device_from_key` from `core/routers/device_auth.py`; `Device(id, name, created_at, last_seen_at, revoked_at)` from `core/repositories/device_repository.py`.
- Produces: `device_pack.router` (prefix `/api/v1/device`), `device_pack.require_device` dependency, endpoints `GET /pack` (ETag / 304), `GET /pack/voice/{line_id}.wav`, `POST /pack/ack` (body `{pack_version, free_bytes, error?}`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_device_pack_api.py
"""Device-facing pack endpoints, tested on a minimal app with a fake device key."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.repositories.device_repository import Device
from core.routers import device_auth, device_pack
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_device_pack_api.py -v -p no:warnings`
Expected: FAIL - `ImportError: cannot import name 'device_pack'`

- [ ] **Step 3: Implement the router**

```python
# core/routers/device_pack.py
"""
Device-facing endpoints for the Wi-Fi "personality pack" (Sparky Studio content).

A Sparky authenticates with its X-Device-Key (core/routers/device_auth.py),
fetches the pack manifest (ETag/304 when unchanged), downloads voice-line
files it doesn't have, and reports which pack version it now holds.
Wire format documented in docs/PROTOCOL.md ("Personality pack").
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from ..repositories.device_repository import Device
from ..services import studio_service as studio
from .device_auth import get_device_from_key

router = APIRouter(prefix="/api/v1/device", tags=["device"])


async def require_device(device: Optional[Device] = Depends(get_device_from_key)) -> Device:
    """Like get_device_from_key, but these endpoints are for devices only."""
    if device is None:
        raise HTTPException(status_code=401, detail="Sparky devices only: send your X-Device-Key")
    return device


class PackAck(BaseModel):
    pack_version: str = Field(..., min_length=1, max_length=64)
    free_bytes: int = Field(0, ge=0)
    error: Optional[str] = Field(None, max_length=200)


@router.get("/pack")
async def get_pack(request: Request, device: Device = Depends(require_device)):
    pack = studio.build_pack()
    etag = f'"{pack["pack_version"]}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return JSONResponse(pack, headers={"ETag": etag})


@router.get("/pack/voice/{line_id}.wav")
async def get_pack_voice(line_id: str, device: Device = Depends(require_device)):
    try:
        path = studio.voice_path(line_id)
    except studio.StudioError:
        raise HTTPException(status_code=404, detail="Unknown voice line")
    return FileResponse(path, media_type="audio/wav")


@router.post("/pack/ack")
async def ack_pack(body: PackAck, device: Device = Depends(require_device)):
    studio.record_device_sync(device.id, body.pack_version, body.free_bytes, body.error)
    return {"ok": True}
```

- [ ] **Step 4: Register it in `core/main.py`**

Add `device_pack,` to the `from .routers import (...)` list (alphabetical, after `admin,`), and after `app.include_router(studio.router)` add:

```python
app.include_router(device_pack.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_device_pack_api.py tests/test_pack.py -v -p no:warnings`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add core/routers/device_pack.py core/main.py tests/test_device_pack_api.py
git commit -m "Add device pack endpoints: manifest with ETag, voice files, sync ack"
```

---

### Task 3: Live preview - "Send to Sparky now"

**Files:**
- Create: `core/services/device_commands.py`
- Modify: `core/routers/device_pack.py` (add `GET /commands`)
- Modify: `core/routers/studio.py` (add `GET /admin/studio/devices`, `POST /admin/studio/devices/{device_id}/preview`)
- Test: `tests/test_device_commands.py`, plus new cases in `tests/test_device_pack_api.py`

**Interfaces:**
- Consumes: `require_device` (Task 2); `studio.check_rows`, `studio.build_pack`, `studio.device_sync` (Task 1); `RepositoryFactory.create_production_repository().devices` with `list_devices()` and `get_by_id(id)`.
- Produces: `device_commands.board: CommandBoard` with `post(device_id: int, command: dict) -> None` and `async wait(device_id: int, timeout: float) -> Optional[dict]`; device endpoint `GET /api/v1/device/commands?wait=25` returning 204 or `{"type": "show_face", "rows": [...], "seconds": 10}`; admin `GET /admin/studio/devices` returning `{"pack_version": str, "devices": [{id, name, last_seen_at, revoked, pack_version, up_to_date, free_bytes, error, synced_at}]}`; admin `POST /admin/studio/devices/{id}/preview` with body `{"rows": [...]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_device_commands.py
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
```

Append to `tests/test_device_pack_api.py`:

```python
from core.services import device_commands


def test_commands_204_then_face(monkeypatch):
    monkeypatch.setattr(device_commands, "board", device_commands.CommandBoard())
    c = _client(SPARKY)
    assert c.get("/api/v1/device/commands?wait=0").status_code == 204
    face = ["#" * 32] * 8
    device_commands.board.post(7, {"type": "show_face", "rows": face, "seconds": 10})
    r = c.get("/api/v1/device/commands?wait=0")
    assert r.status_code == 200 and r.json()["rows"] == face
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_device_commands.py tests/test_device_pack_api.py -v -p no:warnings`
Expected: FAIL - `ModuleNotFoundError: No module named 'core.services.device_commands'`

- [ ] **Step 3: Implement the command board**

```python
# core/services/device_commands.py
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
```

- [ ] **Step 4: Add the device endpoint** - in `core/routers/device_pack.py` add the import `from ..services import device_commands` and:

```python
@router.get("/commands")
async def get_commands(wait: float = 25, device: Device = Depends(require_device)):
    """Long-poll: held open up to `wait` seconds; 204 = nothing to do."""
    command = await device_commands.board.wait(device.id, timeout=max(0.0, min(wait, 30.0)))
    if command is None:
        return Response(status_code=204)
    return command
```

- [ ] **Step 5: Add the admin endpoints** - in `core/routers/studio.py` add imports `from ..repositories.factory import RepositoryFactory` and `from ..services import device_commands`, then:

```python
def _devices():
    return RepositoryFactory.create_production_repository().devices


class PreviewBody(BaseModel):
    rows: List[str]
    seconds: int = 10


@router.get("/devices")
async def list_studio_devices():
    current = studio.build_pack()["pack_version"]
    sync = studio.device_sync()
    out = []
    for d in await _devices().list_devices():
        s = sync.get(str(d.id), {})
        out.append({"id": d.id, "name": d.name, "last_seen_at": d.last_seen_at, "revoked": d.revoked_at is not None,
                    "pack_version": s.get("pack_version"), "up_to_date": s.get("pack_version") == current,
                    "free_bytes": s.get("free_bytes"), "error": s.get("error"), "synced_at": s.get("at")})
    return {"pack_version": current, "devices": out}


@router.post("/devices/{device_id}/preview")
async def preview_on_device(device_id: int, body: PreviewBody):
    rows = _run(studio.check_rows, body.rows)
    device = await _devices().get_by_id(device_id)
    if device is None or device.revoked_at is not None:
        raise HTTPException(status_code=404, detail="No active Sparky with that id")
    device_commands.board.post(device_id, {"type": "show_face", "rows": rows, "seconds": max(1, min(body.seconds, 60))})
    return {"ok": True}
```

Also send devices a "check for a new pack now" nudge whenever content changes, so updates feel instant instead of waiting up to 5 minutes. In `core/routers/studio.py` add this helper and call `await _nudge_all()` at the end of `put_face`, `delete_face`, `put_moods`, `import_faces`, `add_voice_line` and `delete_voice_line` (before their `return`):

```python
async def _nudge_all():
    """Tell idle Sparkys a new pack exists (they still fetch it themselves)."""
    try:
        for d in await _devices().list_devices():
            if d.revoked_at is None:
                device_commands.board.post(d.id, {"type": "sync"})
    except Exception as e:  # a nudge is a nicety - never fail the save over it
        logger.warning(f"Could not nudge devices: {e}")
```

(A pending `show_face` is replaced by a later `sync` nudge only if the device hasn't collected it yet - acceptable: the device syncs, then the next preview press shows the face.)

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_device_commands.py tests/test_device_pack_api.py tests/test_pack.py tests/test_studio.py -v -p no:warnings`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add core/services/device_commands.py core/routers/device_pack.py core/routers/studio.py tests/test_device_commands.py tests/test_device_pack_api.py
git commit -m "Add live preview long-poll, device sync list and update nudges"
```

---

### Task 4: Studio page - "Your Sparkys" and "Send to Sparky now"

**Files:**
- Modify: `core/templates/studio.html`

**Interfaces:**
- Consumes: `GET /admin/studio/devices`, `POST /admin/studio/devices/{id}/preview` (Task 3); existing page helpers `h()`, `api()`, `say()`, `$()`, and the global `rows` (current drawing).

- [ ] **Step 1: Add the "Send to Sparky" control** under the face buttons (after the `<div class="row">` that holds Clear / Invert / Copy / Delete):

```html
<div class="row">
    <select id="previewDevice" class="input" style="max-width:260px"></select>
    <button id="previewBtn" class="btn btn-secondary">Send to Sparky now</button>
</div>
```

- [ ] **Step 2: Add a new section** before the "4. Send it to Sparky" section, and renumber that one to "5":

```html
<section class="studio-section">
    <h2>4. Your Sparkys</h2>
    <p class="hint">Sparkys update themselves over Wi-Fi when nobody is talking to them. "Up to date" means a Sparky already has everything on this page.</p>
    <table>
        <thead><tr><th>Sparky</th><th>Status</th><th>Last seen</th><th>Space left</th></tr></thead>
        <tbody id="devices"></tbody>
    </table>
</section>
```

- [ ] **Step 3: Add the script** (inside the existing `<script>`, before the final `(async () => {...})()` loader):

```javascript
async function loadDevices() {
    let data;
    try { data = await api('GET', '/admin/studio/devices'); } catch (e) { return; }
    const active = data.devices.filter(d => !d.revoked);
    $('previewDevice').replaceChildren(...(active.length ? active.map(d => h('option', {value: d.id}, d.name))
                                                          : [h('option', {value: ''}, 'No Sparkys registered yet')]));
    const body = $('devices'); body.replaceChildren();
    if (!active.length) body.append(h('tr', {}, h('td', {colSpan: 4, class: 'muted'}, 'Register a Sparky on the Devices page first.')));
    for (const d of active) {
        const status = d.error ? `Problem: ${d.error}` : !d.pack_version ? 'Never updated yet'
                     : d.up_to_date ? 'Up to date' : 'Waiting to update';
        const space = d.free_bytes == null ? '-' : `${Math.round(d.free_bytes / 1024)} KB`;
        body.append(h('tr', {}, h('td', {}, d.name), h('td', {}, status), h('td', {class: 'muted'}, d.last_seen_at || 'never'), h('td', {}, space)));
    }
}
$('previewBtn').onclick = async () => {
    const id = $('previewDevice').value;
    if (!id) return say('faceMsg', 'Register a Sparky on the Devices page first.', 'bad');
    try { await api('POST', `/admin/studio/devices/${id}/preview`, {rows}); say('faceMsg', 'Sent - it should appear on Sparky in a second or two.', 'ok'); }
    catch (e) { say('faceMsg', e.message, 'bad'); }
};
setInterval(loadDevices, 15000);
```

and add `loadDevices();` inside the final loader after `renderAll();`.

- [ ] **Step 4: Check it in a browser**

Run the server (`python simple_api.py`), open `http://127.0.0.1:8001/admin/studio/view`. Expected: the "Your Sparkys" table lists registered devices with "Never updated yet"; with none registered it says to register one; "Send to Sparky now" with no device shows the message instead of an error. (The live path is tested in Task 5.)

- [ ] **Step 5: Commit**

```bash
git add core/templates/studio.html
git commit -m "Studio: show each Sparky's update status and add Send to Sparky now"
```

---

### Task 5: Fake Sparky - the reference device, for testing without hardware

**Files:**
- Create: `scripts/fake_sparky.py`
- Test: `tests/test_fake_sparky.py`

**Interfaces:**
- Consumes: the device endpoints from Tasks 2-3.
- Produces: `plan_sync(manifest: dict, have: Dict[str, int]) -> Tuple[List[dict], List[str]]` (voice lines to download, ids to delete) - the exact algorithm the ESP32 copies in Task 9; `face_art(rows) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fake_sparky.py
"""The sync decision the fake Sparky (and the ESP32) make."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("fake_sparky", Path("scripts/fake_sparky.py"))
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_fake_sparky.py -v -p no:warnings`
Expected: FAIL - `FileNotFoundError` for `scripts/fake_sparky.py`

- [ ] **Step 3: Implement**

```python
#!/usr/bin/env python3
"""
A pretend Sparky for testing the Wi-Fi personality pack without hardware.

Does exactly what the ESP32 firmware does (firmware/sparky/src/pack_sync.cpp
copies plan_sync): fetch the pack with If-None-Match, download only missing
voice lines into a folder, switch the manifest over last, report back with
an ack, and long-poll for "Send to Sparky now" faces (printed as LED art).

Usage:
    python scripts/fake_sparky.py --key <device API key from the Devices page>
    python scripts/fake_sparky.py --key ... --once      # one sync, then exit
"""
import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Dict, List, Tuple

import httpx


def plan_sync(manifest: dict, have: Dict[str, int]) -> Tuple[List[dict], List[str]]:
    """Voice lines to download (missing or wrong size) and ids to delete (no longer in the pack)."""
    wanted = {v["id"]: v for v in manifest.get("voice_lines", [])}
    download = [v for i, v in wanted.items() if have.get(i) != v["bytes"]]
    delete = sorted(i for i in have if i not in wanted)
    return download, delete


def face_art(rows: List[str]) -> str:
    return "\n".join(" ".join("@" if ch == "#" else "." for ch in row) for row in rows)


class FakeSparky:
    def __init__(self, base_url: str, key: str, folder: Path):
        self.http = httpx.Client(base_url=base_url, headers={"X-Device-Key": key}, timeout=35)
        self.folder = folder
        self.voice = folder / "voice"
        self.voice.mkdir(parents=True, exist_ok=True)

    def version(self) -> str:
        f = self.folder / "version.txt"
        return f.read_text().strip() if f.exists() else ""

    def sync(self) -> None:
        headers = {"If-None-Match": f'"{self.version()}"'} if self.version() else {}
        r = self.http.get("/api/v1/device/pack", headers=headers)
        if r.status_code == 304:
            print("pack up to date:", self.version())
            return
        r.raise_for_status()
        manifest = r.json()
        have = {p.stem: p.stat().st_size for p in self.voice.glob("*.wav")}
        download, delete = plan_sync(manifest, have)
        for line in download:                              # 1. download new files (old pack still valid)
            tmp = self.voice / f"{line['id']}.tmp"
            with self.http.stream("GET", f"/api/v1/device/pack/voice/{line['id']}.wav") as resp:
                resp.raise_for_status()
                with tmp.open("wb") as out:
                    for chunk in resp.iter_bytes():
                        out.write(chunk)
            if tmp.stat().st_size != line["bytes"]:
                tmp.unlink()
                raise RuntimeError(f"voice line {line['id']} arrived incomplete")
            shutil.move(tmp, self.voice / f"{line['id']}.wav")
        tmp_manifest = self.folder / "manifest.tmp"          # 2. switch over: manifest, then version
        tmp_manifest.write_text(json.dumps(manifest))
        shutil.move(tmp_manifest, self.folder / "manifest.json")
        (self.folder / "version.txt").write_text(manifest["pack_version"])
        for line_id in delete:                             # 3. tidy up leftovers
            (self.voice / f"{line_id}.wav").unlink(missing_ok=True)
        used = sum(p.stat().st_size for p in self.voice.glob("*.wav"))
        self.http.post("/api/v1/device/pack/ack", json={"pack_version": manifest["pack_version"],
                                                        "free_bytes": max(0, 1_300_000 - used)})
        print(f"updated to pack {manifest['pack_version']}: {len(manifest['faces'])} faces, "
              f"{len(download)} downloaded, {len(delete)} deleted")

    def listen(self) -> None:
        r = self.http.get("/api/v1/device/commands", params={"wait": 25})
        if r.status_code == 204:
            return
        command = r.json()
        if command.get("type") == "sync":
            self.sync()
        elif command.get("type") == "show_face":
            print(f"\nShowing face for {command.get('seconds', 10)} s:\n{face_art(command['rows'])}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--key", required=True, help="device API key from the Devices page")
    ap.add_argument("--folder", default="data/fake_sparky")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    sparky = FakeSparky(args.base_url, args.key, Path(args.folder))
    sparky.sync()
    if args.once:
        return
    last = time.time()
    while True:
        sparky.listen()
        if time.time() - last > 300:   # same 5-minute check as the real Sparky
            sparky.sync()
            last = time.time()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_fake_sparky.py -v -p no:warnings`
Expected: PASS

- [ ] **Step 5: End-to-end check against the real server**

1. `python simple_api.py`
2. Register a device on `http://127.0.0.1:8001/admin/devices/view`, copy its key.
3. `python scripts/fake_sparky.py --key <key>` - Expected: `updated to pack ...` with the number of faces.
4. In the Studio, save a face change. Expected within ~1 s (the nudge): the fake Sparky prints `updated to pack <new version>`; the "Your Sparkys" table shows "Up to date".
5. Press "Send to Sparky now". Expected: the face appears in the terminal as `@ . @` art.
6. Make a voice line. Expected: it downloads into `data/fake_sparky/voice/`; delete it in the Studio - it disappears from the folder on the next sync.
7. Revoke the device on the Devices page. Expected: the fake Sparky's next request fails with 401.

- [ ] **Step 6: Commit** (add `data/fake_sparky/` to `.gitignore` first)

```bash
printf 'data/fake_sparky/\n' >> .gitignore
git add scripts/fake_sparky.py tests/test_fake_sparky.py .gitignore
git commit -m "Add fake Sparky: reference device for testing the Wi-Fi pack without hardware"
```

---

### Task 6: Document the pack in the device protocol

**Files:**
- Modify: `docs/PROTOCOL.md` (new section before "## Firmware guidance")

- [ ] **Step 1: Add the section**

````markdown
## Personality pack (Sparky Studio content over Wi-Fi)

Additive to protocol version 1 - existing endpoints are unchanged. All of
these need `X-Device-Key`; a browser request without one gets `401`.

| Request | Response |
|---|---|
| `GET /api/v1/device/pack` (optional `If-None-Match: "<pack_version>"`) | `304` if unchanged, else `200` JSON manifest with an `ETag` |
| `GET /api/v1/device/pack/voice/<id>.wav` | the voice line: 16 kHz, 16-bit, mono WAV (`404` if unknown) |
| `POST /api/v1/device/pack/ack` `{"pack_version", "free_bytes", "error"?}` | `{"ok": true}` - shown on the Studio's "Your Sparkys" table |
| `GET /api/v1/device/commands?wait=25` (long-poll, at most 30) | `204` nothing, or `{"type": "show_face", "rows": [8 x 32 chars], "seconds": 10}` or `{"type": "sync"}` |

Manifest:

```json
{
  "pack_version": "3f9a1c07d2e4b5a6",
  "protocol_version": 1,
  "sample_rate": 16000,
  "mood_order": ["idle", "listening", "thinking", "talking", "happy", "error"],
  "faces": {"Happy  ^ ^": ["......####......", "..."]},
  "moods": {"idle": "Sleepy / idle", "happy": "Happy  ^ ^"},
  "voice_lines": [{"id": "<32 hex>", "trigger": "button_release", "mood": "thinking", "bytes": 61716}]
}
```

Device rules:
- Voice-line ids never change content - download only ids you don't have
  (or whose file size differs), delete files whose id is no longer listed.
- Download everything first, then replace `manifest.json`, then the stored
  version; never switch to a half-downloaded pack.
- Only sync / long-poll while idle (not listening, thinking or talking).
- On `{"type": "sync"}` sync now; otherwise sync at boot and every 5 minutes.
````

- [ ] **Step 2: Commit**

```bash
git add docs/PROTOCOL.md
git commit -m "Document the personality pack endpoints in the device protocol"
```

---

### Task 7: ESP32 project, Wi-Fi settings and LittleFS

> **As built (2026-10-20):** PlatformIO was not installed, but the Arduino IDE's bundled `arduino-cli` and the ESP32 core 3.3.11 were, so `firmware/sparky/` is an Arduino sketch folder (`sparky.ino` + `.cpp/.h` side by side, no `src/`, no `platformio.ini`), compiled and uploaded with `arduino-cli` - see `firmware/sparky/README.md`. The temporary per-task `main.cpp` files were skipped in favour of the final `sparky.ino` plus the README's hardware checklist. Core 3.x renames the I2S DMA fields (`dma_desc_num`, `dma_frame_num`).

**Files:**
- Create: `firmware/sparky/platformio.ini`, `firmware/sparky/src/config.h`, `firmware/sparky/src/settings.h`, `firmware/sparky/src/settings.cpp`, `firmware/sparky/README.md`

**Interfaces:**
- Produces: `settingsBegin()` (connects Wi-Fi via the captive portal, loads server URL + device key), `String settingsServerUrl()`, `String settingsDeviceKey()`; all pin and timing constants in `config.h`.

- [ ] **Step 1: Create the project files**

```ini
; firmware/sparky/platformio.ini
[env:esp32dev]
platform = espressif32
board = esp32dev
framework = arduino
board_build.filesystem = littlefs
board_build.partitions = default.csv     ; ~1.3 MB LittleFS + two app slots (keeps Wi-Fi program updates possible)
monitor_speed = 115200
lib_deps =
    bblanchon/ArduinoJson@^7.0.0
    majicdesigns/MD_MAX72XX@^3.5.1
    tzapu/WiFiManager@^2.0.17
```

```cpp
// firmware/sparky/src/config.h - pins from the report's ESP32 pin map, and timings.
#pragma once
#include <Arduino.h>

constexpr int PIN_AMP_BCLK = 27, PIN_AMP_LRC = 26, PIN_AMP_DIN = 22, PIN_AMP_SD = 21;
constexpr int PIN_MATRIX_CS = 5;              // CLK 18 / DIN 23 are the default VSPI pins
constexpr int PIN_BUTTON = 14;
constexpr int MATRIX_DEVICES = 4;             // 4 x 8x8 = 32 x 8
constexpr uint32_t SYNC_EVERY_MS = 5UL * 60UL * 1000UL;
constexpr int LONG_POLL_SECONDS = 25;
constexpr size_t FLASH_MARGIN_BYTES = 32 * 1024;   // never fill LittleFS completely
#ifndef SPARKY_FLIP_X
#define SPARKY_FLIP_X 1                       // flip if faces show up mirrored
#endif
#ifndef SPARKY_FLIP_Y
#define SPARKY_FLIP_Y 0
#endif
```

```cpp
// firmware/sparky/src/settings.h
#pragma once
#include <Arduino.h>
void settingsBegin();            // Wi-Fi (captive portal on first boot) + server URL + device key
String settingsServerUrl();      // e.g. "http://192.168.1.20:8001"
String settingsDeviceKey();
```

```cpp
// firmware/sparky/src/settings.cpp
// Ported from the bring-up sketch Sparky_Wifi_Setup.ino (OneDrive/Documents/Arduino):
// same Sparky-styled WiFiManager portal, hotspot name/password and class-code field.
// Changes from the sketch:
//   - no wm.resetSettings() on every boot: the portal only opens when Sparky has no
//     Wi-Fi/server/key yet, or when the button is held while switching on;
//   - server address and device key are typed into the portal and saved in flash
//     (Preferences) instead of being written into the code.
#include "settings.h"
#include "config.h"
#include <Preferences.h>
#include <WiFiManager.h>

static const char* SPARKY_CSS = R"rawliteral(
<style>
  body { background-color: #EAF6FD; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1A1A1A; }
  .wrap { background-color: #FFFFFF; max-width: 340px; margin: 30px auto; padding: 24px; border-radius: 16px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.12); text-align: left; }
  h1, h2, h3 { color: #3AA0D8; text-align: center; }
  button { background-color: #F5821F; color: #FFFFFF; border: 0; border-radius: 10px; line-height: 2.4rem;
           font-size: 1.1rem; width: 100%; margin-top: 8px; cursor: pointer; }
  button:hover { background-color: #D96F16; }
  input, select { border-radius: 8px; border: 1px solid #CFE6F3; padding: 8px; font-size: 1rem; width: 92%; }
  a { color: #3AA0D8; }
  .msg { border-radius: 10px; padding: 10px; }
</style>
)rawliteral";

static Preferences prefs;
static String serverUrl, deviceKey, classCode;

void settingsBegin() {
  prefs.begin("sparky", false);
  serverUrl = prefs.getString("server", "");
  deviceKey = prefs.getString("key", "");
  classCode = prefs.getString("class", "");

  WiFiManager wm;
  wm.setCustomHeadElement(SPARKY_CSS);
  wm.setTitle("Sparky Setup");
  WiFiManagerParameter pServer("server", "Server address (e.g. http://192.168.1.20:8001)", serverUrl.c_str(), 80);
  WiFiManagerParameter pKey("key", "Device key (from the Devices admin page)", deviceKey.c_str(), 80);
  WiFiManagerParameter pClass("classcode", "Class Code (optional)", classCode.c_str(), 20);
  wm.addParameter(&pServer);
  wm.addParameter(&pKey);
  wm.addParameter(&pClass);
  wm.setConfigPortalTimeout(300);

  bool forceSetup = digitalRead(PIN_BUTTON) == LOW;          // hold the button while switching on = set up again
  if (forceSetup || serverUrl.isEmpty() || deviceKey.isEmpty()) wm.startConfigPortal(SETUP_AP_NAME, SETUP_AP_PASSWORD);
  else wm.autoConnect(SETUP_AP_NAME, SETUP_AP_PASSWORD);

  serverUrl = pServer.getValue();  serverUrl.trim();
  if (serverUrl.endsWith("/")) serverUrl.remove(serverUrl.length() - 1);
  deviceKey = pKey.getValue();     deviceKey.trim();
  classCode = pClass.getValue();   classCode.trim();
  prefs.putString("server", serverUrl);
  prefs.putString("key", deviceKey);
  prefs.putString("class", classCode);
}

String settingsServerUrl() { return serverUrl; }
String settingsDeviceKey() { return deviceKey; }
```

Add to `config.h` (same hotspot as the bring-up sketch, so nothing changes for whoever sets Sparky up):

```cpp
constexpr const char* SETUP_AP_NAME = "Sparky Setup";
constexpr const char* SETUP_AP_PASSWORD = "sparky123";   // WPA2 needs 8+ characters
```

`firmware/sparky/README.md`:

```markdown
# Sparky firmware

Build and upload with PlatformIO (VS Code extension or `pio run -t upload`).
First boot opens the "Sparky Setup" Wi-Fi hotspot (password `sparky123`) -
connect with a phone, choose the school Wi-Fi, and enter the server address
and the device key from the Devices admin page. Hold Sparky's button while
switching on to open the setup page again (e.g. new Wi-Fi or new key).
Faces and voice lines then arrive over Wi-Fi from Sparky Studio
(docs/PROTOCOL.md, "Personality pack").

The device key is a password: type it into the setup page, never into the
code (this repository is public).
```

- [ ] **Step 2: Add a temporary `main.cpp` that only proves Wi-Fi + LittleFS**

```cpp
// firmware/sparky/src/main.cpp (temporary - replaced in Task 11)
#include <Arduino.h>
#include <LittleFS.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include "config.h"
#include "settings.h"

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  if (!LittleFS.begin(true)) Serial.println("LittleFS failed");
  settingsBegin();
  Serial.printf("Wi-Fi %s, IP %s, server %s, flash free %u bytes\n",
                WiFi.isConnected() ? "OK" : "FAILED", WiFi.localIP().toString().c_str(),
                settingsServerUrl().c_str(), LittleFS.totalBytes() - LittleFS.usedBytes());
  HTTPClient http;                                   // same /health check as the bring-up sketch
  http.begin(settingsServerUrl() + "/health");
  Serial.printf("Server /health: %d\n", http.GET());
  http.end();
}
void loop() {}
```

- [ ] **Step 3: Build and test on the ESP32**

Run: `cd firmware/sparky && pio run -t upload && pio device monitor`
Expected:
1. First boot: the "Sparky Setup" hotspot appears with the same blue/orange page as the bring-up sketch, now with server address and device key fields. After filling it in from a phone, the monitor prints `Wi-Fi OK, IP ..., server http://..., flash free ~1300000 bytes` and `Server /health: 200`.
2. Press reset: it reconnects **without** opening the hotspot (the bring-up sketch reopened it every boot).
3. Hold the button and press reset: the hotspot opens again with the saved values filled in.

- [ ] **Step 4: Commit**

```bash
git add firmware/sparky
git commit -m "Firmware: PlatformIO project with Wi-Fi setup portal and LittleFS"
```

---

### Task 8: ESP32 faces from the pack

**Files:**
- Create: `firmware/sparky/src/faces.h`, `firmware/sparky/src/faces.cpp`

**Interfaces:**
- Produces: `facesBegin()` (starts the matrix, loads `/pack/manifest.json` or the built-in fallback), `bool facesLoad()`, `void facesShowMood(uint8_t mood)`, `void facesShowRows(const char* const rows[8])`, mood indices `MOOD_IDLE=0 ... MOOD_ERROR=5` in `mood_order` order.

- [ ] **Step 1: Write the code**

```cpp
// firmware/sparky/src/faces.h
#pragma once
#include <Arduino.h>
enum : uint8_t { MOOD_IDLE, MOOD_LISTENING, MOOD_THINKING, MOOD_TALKING, MOOD_HAPPY, MOOD_ERROR, MOOD_COUNT };
void facesBegin();
bool facesLoad();                                   // re-read /pack/manifest.json; false = using built-ins
void facesShowMood(uint8_t mood);
void facesShowRows(const char* const rows[8]);      // 8 strings of 32 '#'/'.'
```

```cpp
// firmware/sparky/src/faces.cpp
#include "faces.h"
#include "config.h"
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <MD_MAX72xx.h>

static MD_MAX72XX mx(MD_MAX72XX::FC16_HW, PIN_MATRIX_CS, MATRIX_DEVICES);
static uint32_t moodFaces[MOOD_COUNT][8];
static const char* const MOOD_NAMES[MOOD_COUNT] = {"idle", "listening", "thinking", "talking", "happy", "error"};

// Built-in faces so Sparky has a face before its first sync (happy ^ ^ for everything, X X for error).
static const uint32_t FALLBACK_HAPPY[8] = {0x00000000, 0x03C003C0, 0x07E007E0, 0x0C300C30,
                                           0x0C300C30, 0x18181818, 0x18181818, 0x00000000};
static const uint32_t FALLBACK_ERROR[8] = {0x0C300C30, 0x06600660, 0x03C003C0, 0x01800180,
                                           0x03C003C0, 0x06600660, 0x0C300C30, 0x00000000};

static uint32_t rowBits(const char* row) {
  uint32_t v = 0;
  for (int c = 0; c < 32; c++) v = (v << 1) | (row[c] == '#' ? 1u : 0u);
  return v;
}

static void drawBits(const uint32_t face[8]) {
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF);
  for (uint8_t r = 0; r < 8; r++)
    for (uint8_t c = 0; c < 32; c++)
      mx.setPoint(SPARKY_FLIP_Y ? 7 - r : r, SPARKY_FLIP_X ? 31 - c : c, (face[r] >> (31 - c)) & 1u);
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::ON);
}

static void useFallback() {
  for (uint8_t m = 0; m < MOOD_COUNT; m++) memcpy(moodFaces[m], m == MOOD_ERROR ? FALLBACK_ERROR : FALLBACK_HAPPY, sizeof(moodFaces[m]));
}

bool facesLoad() {
  File f = LittleFS.open("/pack/manifest.json", "r");
  if (!f) { useFallback(); return false; }
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, f);
  f.close();
  if (err) { useFallback(); return false; }
  for (uint8_t m = 0; m < MOOD_COUNT; m++) {
    const char* faceName = doc["moods"][MOOD_NAMES[m]] | "";
    JsonArray rows = doc["faces"][faceName];
    if (rows.size() != 8) { useFallback(); return false; }
    for (uint8_t r = 0; r < 8; r++) {
      const char* row = rows[r] | "";
      if (strlen(row) != 32) { useFallback(); return false; }
      moodFaces[m][r] = rowBits(row);
    }
  }
  return true;
}

void facesBegin() {
  mx.begin();
  mx.control(MD_MAX72XX::INTENSITY, 3);      // low brightness keeps current (and USB brownouts) down
  facesLoad();
  facesShowMood(MOOD_IDLE);
}

void facesShowMood(uint8_t mood) { if (mood < MOOD_COUNT) drawBits(moodFaces[mood]); }

void facesShowRows(const char* const rows[8]) {
  uint32_t face[8];
  for (uint8_t r = 0; r < 8; r++) face[r] = strlen(rows[r]) == 32 ? rowBits(rows[r]) : 0;
  drawBits(face);
}
```

- [ ] **Step 2: Hardware check** - temporarily call `facesBegin();` at the end of `setup()` in `main.cpp`.
Expected: with no pack yet, the matrix shows the built-in happy `^ ^` face. If it is mirrored, set `SPARKY_FLIP_X` to 0 in `config.h` and re-upload - **write down which value is right** (it also fixes `sparky_faces.h` exports).

- [ ] **Step 3: Commit**

```bash
git add firmware/sparky/src/faces.h firmware/sparky/src/faces.cpp firmware/sparky/src/main.cpp
git commit -m "Firmware: faces and mood mapping loaded from the personality pack"
```

---

### Task 9: ESP32 pack sync over Wi-Fi

**Files:**
- Create: `firmware/sparky/src/pack_sync.h`, `firmware/sparky/src/pack_sync.cpp`

**Interfaces:**
- Consumes: `settingsServerUrl()`, `settingsDeviceKey()` (Task 7).
- Produces: `bool packSync()` - returns true if a new pack was installed (caller then runs `facesLoad()`); files `/pack/manifest.json`, `/pack/version.txt`, `/pack/v/<id>.wav`. Same algorithm as `plan_sync` + `FakeSparky.sync` (Task 5).

- [ ] **Step 1: Write the code**

```cpp
// firmware/sparky/src/pack_sync.h
#pragma once
#include <Arduino.h>
bool packSync();   // true = a new pack was installed
```

```cpp
// firmware/sparky/src/pack_sync.cpp
// Mirrors scripts/fake_sparky.py: If-None-Match -> 304, download missing voice
// lines first, then switch manifest + version, then delete leftovers, then ack.
#include "pack_sync.h"
#include "config.h"
#include "settings.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>

static String readVersion() {
  File f = LittleFS.open("/pack/version.txt", "r");
  String v = f ? f.readString() : "";
  if (f) f.close();
  v.trim();
  return v;
}

static void begin(HTTPClient& http, const String& path) {
  http.begin(settingsServerUrl() + path);
  http.addHeader("X-Device-Key", settingsDeviceKey());
  http.setTimeout(30000);
}

static void ack(const String& version, const char* error) {
  HTTPClient http;
  begin(http, "/api/v1/device/pack/ack");
  http.addHeader("Content-Type", "application/json");
  JsonDocument doc;
  doc["pack_version"] = version.length() ? version : String("none");
  doc["free_bytes"] = LittleFS.totalBytes() - LittleFS.usedBytes();
  if (error) doc["error"] = error;
  String body;
  serializeJson(doc, body);
  http.POST(body);
  http.end();
}

static bool download(const String& id, size_t expected) {
  String tmp = "/pack/v/" + id + ".tmp", final = "/pack/v/" + id + ".wav";
  HTTPClient http;
  begin(http, "/api/v1/device/pack/voice/" + id + ".wav");
  if (http.GET() != 200) { http.end(); return false; }
  File out = LittleFS.open(tmp, "w");
  int written = out ? http.writeToStream(&out) : -1;
  if (out) out.close();
  http.end();
  if (written < 0 || (size_t)written != expected) { LittleFS.remove(tmp); return false; }
  LittleFS.remove(final);
  return LittleFS.rename(tmp, final);
}

bool packSync() {
  LittleFS.mkdir("/pack");
  LittleFS.mkdir("/pack/v");
  String current = readVersion();

  HTTPClient http;
  begin(http, "/api/v1/device/pack");
  const char* keep[] = {"ETag"};
  http.collectHeaders(keep, 1);
  if (current.length()) http.addHeader("If-None-Match", "\"" + current + "\"");
  int code = http.GET();
  if (code == 304) { http.end(); return false; }
  if (code != 200) { http.end(); return false; }      // server down or 401 (revoked) - try later
  String manifestText = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, manifestText)) { ack(current, "bad manifest"); return false; }
  String version = doc["pack_version"] | "";

  // 1. what to download (missing or wrong size) - same as plan_sync()
  size_t needed = 0;
  for (JsonObject v : doc["voice_lines"].as<JsonArray>()) {
    String path = "/pack/v/" + String((const char*)v["id"]) + ".wav";
    File f = LittleFS.open(path, "r");
    size_t have = f ? f.size() : 0;
    if (f) f.close();
    if (have != v["bytes"].as<size_t>()) needed += v["bytes"].as<size_t>();
  }
  size_t free = LittleFS.totalBytes() - LittleFS.usedBytes();
  if (needed + FLASH_MARGIN_BYTES > free) { ack(current, "not enough space"); return false; }
  for (JsonObject v : doc["voice_lines"].as<JsonArray>()) {
    String id = v["id"];
    String path = "/pack/v/" + id + ".wav";
    File f = LittleFS.open(path, "r");
    size_t have = f ? f.size() : 0;
    if (f) f.close();
    if (have != v["bytes"].as<size_t>() && !download(id, v["bytes"].as<size_t>())) { ack(current, "download failed"); return false; }
  }

  // 2. switch over: manifest first, version last
  File m = LittleFS.open("/pack/manifest.tmp", "w");
  if (!m) { ack(current, "cannot write manifest"); return false; }
  m.print(manifestText);
  m.close();
  LittleFS.remove("/pack/manifest.json");
  LittleFS.rename("/pack/manifest.tmp", "/pack/manifest.json");
  File ver = LittleFS.open("/pack/version.txt", "w");
  ver.print(version);
  ver.close();

  // 3. delete voice lines no longer in the pack
  File dir = LittleFS.open("/pack/v");
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    String name = f.name();                        // "<id>.wav"
    f.close();
    String id = name.substring(0, name.indexOf('.'));
    bool wanted = false;
    for (JsonObject v : doc["voice_lines"].as<JsonArray>()) if (id == (const char*)v["id"]) { wanted = true; break; }
    if (!wanted) LittleFS.remove("/pack/v/" + name);
  }

  ack(version, nullptr);
  return true;
}
```

- [ ] **Step 2: Hardware check** - in temporary `main.cpp` `setup()` after `facesBegin();` add `if (packSync()) facesLoad(); facesShowMood(MOOD_HAPPY);`.
Expected: the serial monitor shows no errors; the Studio's "Your Sparkys" table shows the ESP32 as "Up to date"; the matrix shows the face you mapped to "happy". Change the happy face in the Studio, reset the ESP32 - the new face appears. Pull the power during a voice-line download, power up again - Sparky still shows its previous faces, and the next sync completes.

- [ ] **Step 3: Commit**

```bash
git add firmware/sparky/src/pack_sync.h firmware/sparky/src/pack_sync.cpp firmware/sparky/src/main.cpp
git commit -m "Firmware: download the personality pack over Wi-Fi with a safe switch-over"
```

---

### Task 10: ESP32 voice lines from flash

**Files:**
- Create: `firmware/sparky/src/voice.h`, `firmware/sparky/src/voice.cpp`

**Interfaces:**
- Produces: `voiceBegin()`, `bool voicePlay(const char* trigger, uint8_t* moodOut)` - plays a random voice line with that trigger (`button_release`, `startup`, `wifi_error`, `server_error`, `goodbye`, `custom`) and reports which mood face to show; false if none.

- [ ] **Step 1: Write the code**

```cpp
// firmware/sparky/src/voice.h
#pragma once
#include <Arduino.h>
void voiceBegin();
bool voicePlay(const char* trigger, uint8_t* moodOut);   // blocks until the clip finishes
```

```cpp
// firmware/sparky/src/voice.cpp
// Plays 16 kHz 16-bit mono WAVs from LittleFS through the MAX98357A on I2S port 1
// (port 0 stays free for the INMP441 microphone). Driving SD high (3.3 V) selects
// the left channel on the MAX98357A, which is where ONLY_LEFT puts the samples.
#include "voice.h"
#include "config.h"
#include "faces.h"
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <driver/i2s.h>

static const char* const MOOD_NAMES[MOOD_COUNT] = {"idle", "listening", "thinking", "talking", "happy", "error"};

void voiceBegin() {
  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW);                 // amplifier muted until a clip plays
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate = 16000;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = 256;
  cfg.tx_desc_auto_clear = true;
  i2s_pin_config_t pins = {};
  pins.bck_io_num = PIN_AMP_BCLK;
  pins.ws_io_num = PIN_AMP_LRC;
  pins.data_out_num = PIN_AMP_DIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_driver_install(I2S_NUM_1, &cfg, 0, nullptr);
  i2s_set_pin(I2S_NUM_1, &pins);
}

bool voicePlay(const char* trigger, uint8_t* moodOut) {
  File mf = LittleFS.open("/pack/manifest.json", "r");
  if (!mf) return false;
  JsonDocument doc;
  bool bad = deserializeJson(doc, mf);
  mf.close();
  if (bad) return false;

  JsonObject pick;
  int seen = 0;
  for (JsonObject v : doc["voice_lines"].as<JsonArray>())          // random pick among matching lines
    if (strcmp(v["trigger"] | "", trigger) == 0 && random(++seen) == 0) pick = v;
  if (pick.isNull()) return false;

  if (moodOut) {
    *moodOut = MOOD_IDLE;
    for (uint8_t m = 0; m < MOOD_COUNT; m++) if (strcmp(pick["mood"] | "", MOOD_NAMES[m]) == 0) *moodOut = m;
  }
  File f = LittleFS.open("/pack/v/" + String((const char*)pick["id"]) + ".wav", "r");
  if (!f) return false;
  f.seek(44);                                    // skip the standard 44-byte WAV header
  uint8_t buf[1024];
  size_t n, written;
  digitalWrite(PIN_AMP_SD, HIGH);
  while ((n = f.read(buf, sizeof(buf))) > 0) i2s_write(I2S_NUM_1, buf, n, &written, portMAX_DELAY);
  i2s_zero_dma_buffer(I2S_NUM_1);
  digitalWrite(PIN_AMP_SD, LOW);
  f.close();
  return true;
}
```

- [ ] **Step 2: Hardware check** - in temporary `main.cpp` add `voiceBegin();` and after the sync `uint8_t mood; if (voicePlay("startup", &mood)) facesShowMood(mood);`. Make a "startup" voice line in the Studio first.
Expected: Sparky says the line through the speaker, clearly and at normal speed (a chipmunk or slow voice means the sample rate is wrong). No hiss while silent (amplifier muted).

- [ ] **Step 3: Commit**

```bash
git add firmware/sparky/src/voice.h firmware/sparky/src/voice.cpp firmware/sparky/src/main.cpp
git commit -m "Firmware: play Studio voice lines from flash through the MAX98357A"
```

---

### Task 11: ESP32 background network task, live preview and the real main loop

**Files:**
- Create: `firmware/sparky/src/network_task.h`, `firmware/sparky/src/network_task.cpp`
- Modify: `firmware/sparky/src/main.cpp` (replace the temporary version)

**Interfaces:**
- Consumes: `packSync()` (Task 9), `settingsServerUrl()`, `settingsDeviceKey()` (Task 7).
- Produces: `networkBegin()`; shared flags `volatile bool sparkyIdle` (set by the main loop), `volatile bool packChanged` (set by the network task); `bool networkTakePreview(char rows[8][33], uint16_t* seconds)`.

- [ ] **Step 1: Write the network task**

```cpp
// firmware/sparky/src/network_task.h
#pragma once
#include <Arduino.h>
extern volatile bool sparkyIdle;      // main loop: true only when not listening/thinking/talking
extern volatile bool packChanged;     // network task: a new pack was installed -> reload faces
void networkBegin();
bool networkTakePreview(char rows[8][33], uint16_t* seconds);
```

```cpp
// firmware/sparky/src/network_task.cpp
// Runs on core 0 so a 25-second long-poll never blocks the button on core 1.
#include "network_task.h"
#include "config.h"
#include "pack_sync.h"
#include "settings.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

volatile bool sparkyIdle = true;
volatile bool packChanged = false;
static char previewRows[8][33];
static uint16_t previewSeconds = 0;
static volatile bool previewReady = false;
static portMUX_TYPE previewLock = portMUX_INITIALIZER_UNLOCKED;

bool networkTakePreview(char rows[8][33], uint16_t* seconds) {
  if (!previewReady) return false;
  portENTER_CRITICAL(&previewLock);
  memcpy(rows, previewRows, sizeof(previewRows));
  *seconds = previewSeconds;
  previewReady = false;
  portEXIT_CRITICAL(&previewLock);
  return true;
}

static void pollCommands() {
  HTTPClient http;
  http.begin(settingsServerUrl() + "/api/v1/device/commands?wait=" + String(LONG_POLL_SECONDS));
  http.addHeader("X-Device-Key", settingsDeviceKey());
  http.setTimeout((LONG_POLL_SECONDS + 5) * 1000);
  int code = http.GET();
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, http.getString())) {
      const char* type = doc["type"] | "";
      if (strcmp(type, "sync") == 0) {
        if (packSync()) packChanged = true;
      } else if (strcmp(type, "show_face") == 0 && doc["rows"].size() == 8) {
        portENTER_CRITICAL(&previewLock);
        for (int r = 0; r < 8; r++) strlcpy(previewRows[r], doc["rows"][r] | "", 33);
        previewSeconds = doc["seconds"] | 10;
        previewReady = true;
        portEXIT_CRITICAL(&previewLock);
      }
    }
  }
  http.end();
  if (code < 0) vTaskDelay(pdMS_TO_TICKS(5000));   // server unreachable - back off
}

static void networkTask(void*) {
  uint32_t lastSync = 0;
  bool firstSync = true;
  for (;;) {
    if (WiFi.isConnected() && sparkyIdle) {
      if (firstSync || millis() - lastSync > SYNC_EVERY_MS) {
        if (packSync()) packChanged = true;
        lastSync = millis();
        firstSync = false;
      }
      pollCommands();
    } else {
      vTaskDelay(pdMS_TO_TICKS(1000));
    }
  }
}

void networkBegin() { xTaskCreatePinnedToCore(networkTask, "network", 12288, nullptr, 1, nullptr, 0); }
```

- [ ] **Step 2: Replace `main.cpp`** with the real loop (the voice-question part - recording, sending to `/api/v1/voice/query`, playing the answer - plugs into the marked state when that firmware task is written; it is not part of this plan):

```cpp
// firmware/sparky/src/main.cpp
#include <Arduino.h>
#include <LittleFS.h>
#include "config.h"
#include "faces.h"
#include "network_task.h"
#include "settings.h"
#include "voice.h"

static uint32_t previewUntil = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  LittleFS.begin(true);
  facesBegin();
  voiceBegin();
  settingsBegin();
  uint8_t mood;
  if (voicePlay("startup", &mood)) facesShowMood(mood);
  facesShowMood(MOOD_IDLE);
  networkBegin();
}

void loop() {
  bool pressed = digitalRead(PIN_BUTTON) == LOW;
  sparkyIdle = !pressed;                                    // the voice-question flow also clears this while thinking/talking

  if (pressed) {
    facesShowMood(MOOD_LISTENING);
    while (digitalRead(PIN_BUTTON) == LOW) delay(10);        // (recording happens here in the voice-question task)
    uint8_t mood = MOOD_THINKING;
    voicePlay("button_release", &mood);                      // instant "Hmm, let me think!" while the answer is fetched
    facesShowMood(MOOD_THINKING);
    // (send the recording, play the answer with MOOD_TALKING, then fall through to idle)
    facesShowMood(MOOD_IDLE);
    sparkyIdle = true;
    return;
  }

  if (packChanged) {                                         // new faces arrived - load them while idle
    packChanged = false;
    facesLoad();
    facesShowMood(MOOD_IDLE);
  }

  char rows[8][33];
  uint16_t seconds;
  if (networkTakePreview(rows, &seconds)) {                  // "Send to Sparky now"
    const char* ptrs[8];
    for (int r = 0; r < 8; r++) ptrs[r] = rows[r];
    facesShowRows(ptrs);
    previewUntil = millis() + seconds * 1000UL;
  }
  if (previewUntil && millis() > previewUntil) {
    previewUntil = 0;
    facesShowMood(MOOD_IDLE);
  }
  delay(20);
}
```

- [ ] **Step 3: Hardware check (the whole feature)**

Upload, open the Studio:
1. Draw a face, press **Send to Sparky now** - Expected: it appears on the real LEDs within ~1-2 s and returns to the idle face after 10 s.
2. Save a face change - Expected: Sparky shows the new idle face within a few seconds (nudge) and the table says "Up to date".
3. Hold the button while a sync is due - Expected: no sync starts while held; the button responds instantly even during a long-poll.
4. Make a `button_release` voice line - Expected: it plays as soon as the button is released.
5. Unplug the server for a minute - Expected: Sparky keeps working with its stored pack and resyncs when the server is back.

- [ ] **Step 4: Commit**

```bash
git add firmware/sparky/src/network_task.h firmware/sparky/src/network_task.cpp firmware/sparky/src/main.cpp
git commit -m "Firmware: background sync and live preview without blocking the button"
```

---

## After this plan (separate follow-ups, need your go-ahead)

- **Install from the browser** (decision 4): add ESP Web Tools to the Studio page so a brand-new ESP32 can be set up from Chrome over USB - no Arduino IDE or PlatformIO needed by the person installing it.
- **Program updates over Wi-Fi (OTA):** the server offers a new firmware file the same way it offers packs; Sparky installs it into its second program slot (kept free by the standard storage split) and switches over on restart.
- **Emotion per answer:** add an `emotion` field to the voice-answer metadata so the server picks the face (Stage 3 of the Studio idea).

## Effort and order

| Phase | Tasks | Rough effort | Needs hardware? |
|---|---|---|---|
| Server + fake Sparky | 1-6 | about a day | No - testable now |
| Firmware | 7-11 | 1-2 days including testing | Yes |

Tasks 1-6 can be built and fully tested before the parts arrive; tasks 7-11 wait for the ESP32 with the matrix and amplifier wired up.
