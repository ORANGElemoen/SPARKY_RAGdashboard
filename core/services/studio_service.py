"""
Sparky Studio - faces, mood mapping and voice lines for the Sparky device.

Everything lives in data/studio/ (studio.json + voice/<id>.wav) so it survives
restarts without a database migration. Faces are 8 rows of 32 characters
('#' = LED on, '.' = off, top row first) - the same format as the 3D viewer
(docs/sparky_3d_viewer.html) and its "sparky-faces/1" download, so faces move
freely between the two.

Firmware hand-off (Stage 1): export_header() turns the faces and the mood
mapping into a C header the ESP32 sketch includes; voice lines export as
16 kHz mono WAVs sized for the ESP32's flash.
"""

import hashlib
import io
import json
import re
import uuid
import wave
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

STUDIO_DIR = Path("data/studio")
VOICE_DIR = STUDIO_DIR / "voice"
STORE = STUDIO_DIR / "studio.json"
SYNC_STORE = STUDIO_DIR / "device_sync.json"   # which pack each device reported having
FACES_FORMAT = "sparky-faces/1"

# Face states from the design report (REQ-F-09), in firmware enum order.
MOODS = ["idle", "listening", "thinking", "talking", "happy", "error", "startup"]
# When each voice line is meant to play on the device.
TRIGGERS = {
    "button_release": "When the button is let go (covers the wait for the answer)",
    "startup": "When Sparky switches on",
    "wifi_connected": "Right after Sparky joins the Wi-Fi",
    "wifi_setup": "No Wi-Fi found: Sparky opened its setup hotspot",
    "wifi_error": "When Sparky can't reach the Wi-Fi",
    "server_error": "When the tutor server doesn't answer",
    "goodbye": "Before going to sleep",
    "custom": "Your own use",
    "test_question": "Bench test: sent as the question instead of the mic (firmware test mode)",
}
DEVICE_SAMPLE_RATE = 16000          # Hz, mono 16-bit: small enough for flash, clear enough for speech
FLASH_BUDGET_BYTES = 1_000_000      # rough space for voice lines on a 4 MB ESP32 (estimate)
MAX_TEXT = 200
MAX_NAME = 40

_EYES = {
    "arch": ["...####...", "..######..", ".##....##.", ".##....##.", "##......##", "##......##"],
    "ring": ["..####..", ".######.", "##....##", "##....##", "##....##", "##....##", ".######.", "..####.."],
    "block": [".####.", "######", "######", "######", "######", ".####."],
    "caret": ["...##...", "..####..", ".##..##.", "##....##"],
    "lid": ["########", ".######."],
    "look": [".##.", "####", "####", ".##."],
    "cross": ["##....##", ".##..##.", "..####..", "...##...", "..####..", ".##..##.", "##....##"],
}


def _face(left: str, right: str, lx: int, rx: int, ltop: int, rtop: int) -> List[str]:
    grid = [["."] * 32 for _ in range(8)]
    for eye, x0, y0 in ((_EYES[left], lx, ltop), (_EYES[right], rx, rtop)):
        for r, row in enumerate(eye):
            for c, ch in enumerate(row):
                if ch == "#":
                    grid[y0 + r][x0 + c] = "#"
    return ["".join(row) for row in grid]


DEFAULT_FACES: Dict[str, List[str]] = {
    "Happy  ^ ^": _face("arch", "arch", 3, 19, 1, 1),
    "Surprised  O O": _face("ring", "ring", 4, 20, 0, 0),
    "Neutral (listening)": _face("block", "block", 5, 21, 1, 1),
    "Wink": _face("block", "caret", 5, 20, 1, 2),
    "Sleepy / idle": _face("lid", "lid", 4, 20, 4, 4),
    "Thinking (eyes up)": _face("look", "look", 8, 24, 0, 0),
    "Error  X X": _face("cross", "cross", 4, 20, 0, 0),
}
DEFAULT_MOODS = {
    "idle": "Sleepy / idle", "listening": "Neutral (listening)", "thinking": "Thinking (eyes up)",
    "talking": "Happy  ^ ^", "happy": "Happy  ^ ^", "error": "Error  X X", "startup": "Happy  ^ ^",
}

_ROW = re.compile(r"^[#.]{32}$")
_ID = re.compile(r"^[0-9a-f]{32}$")


class StudioError(ValueError):
    """Bad input from the dashboard (shown to the user as a 400)."""


# ---------------------------------------------------------------- validation
def clean_name(name: str) -> str:
    name = " ".join(str(name or "").split())
    if not name or len(name) > MAX_NAME or not name.isprintable():
        raise StudioError(f"A face name must be 1-{MAX_NAME} printable characters.")
    return name


def check_rows(rows) -> List[str]:
    if not isinstance(rows, list) or len(rows) != 8 or not all(isinstance(r, str) and _ROW.match(r) for r in rows):
        raise StudioError("A face must be 8 rows of 32 characters, '#' for on and '.' for off.")
    return list(rows)


def check_line_id(line_id: str) -> str:
    if not _ID.match(str(line_id or "")):
        raise StudioError("Unknown voice line.")
    return line_id


# ---------------------------------------------------------------- storage
def load() -> Dict:
    if STORE.exists():
        data = json.loads(STORE.read_text(encoding="utf-8"))
    else:
        data = {}
    data.setdefault("faces", dict(DEFAULT_FACES))
    data.setdefault("moods", dict(DEFAULT_MOODS))
    data.setdefault("voice_lines", [])
    for mood in MOODS:  # a mood pointing at a deleted face falls back to its default
        if data["moods"].get(mood) not in data["faces"]:
            data["moods"][mood] = DEFAULT_MOODS[mood] if DEFAULT_MOODS[mood] in data["faces"] else next(iter(data["faces"]), "")
    return data


def save(data: Dict) -> None:
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STORE)  # atomic: a crash mid-write never leaves a half-written file


def put_face(name: str, rows) -> Dict:
    data = load()
    data["faces"][clean_name(name)] = check_rows(rows)
    save(data)
    return data


def delete_face(name: str) -> Dict:
    data = load()
    name = clean_name(name)
    if name not in data["faces"]:
        raise StudioError("No face with that name.")
    if len(data["faces"]) == 1:
        raise StudioError("Sparky needs at least one face.")
    del data["faces"][name]
    save(data)
    return load()  # re-points any mood that used the deleted face


def set_moods(moods: Dict[str, str]) -> Dict:
    data = load()
    for mood, face in (moods or {}).items():
        if mood not in MOODS:
            raise StudioError(f"Unknown mood '{mood}'.")
        if face not in data["faces"]:
            raise StudioError(f"There is no face called '{face}'.")
        data["moods"][mood] = face
    save(data)
    return data


def import_faces(payload) -> Dict:
    """Merge a "sparky-faces/1" file (from the 3D viewer) into the library."""
    faces = payload.get("faces") if isinstance(payload, dict) and "faces" in payload else payload
    if not isinstance(faces, dict):
        raise StudioError("That is not a Sparky faces file.")
    data, added = load(), 0
    for name, rows in faces.items():
        try:
            data["faces"][clean_name(name)] = check_rows(rows)
            added += 1
        except StudioError:
            continue
    if not added:
        raise StudioError("No valid 32 x 8 faces were found in that file.")
    save(data)
    return {"added": added, "skipped": len(faces) - added}


def export_faces_file() -> Dict:
    return {"format": FACES_FORMAT, "faces": load()["faces"]}


# ---------------------------------------------------------------- firmware header
def _ident(name: str, used: set) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "FACE"
    if base[0].isdigit():
        base = "F_" + base
    ident, n = f"SPARKY_FACE_{base}", 2
    while ident in used:
        ident, n = f"SPARKY_FACE_{base}_{n}", n + 1
    used.add(ident)
    return ident


def row_bits(row: str) -> int:
    """'#...' -> 32-bit value with the leftmost LED as bit 31."""
    return int(row.replace("#", "1").replace(".", "0"), 2)


def export_header(data: Optional[Dict] = None) -> str:
    data = data or load()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    used, idents = set(), {}
    lines = [
        f"// sparky_faces.h - generated by Sparky Studio ({stamp}).",
        "// Don't edit by hand: change faces in the Studio and export again.",
        "//",
        "// Each face is 8 rows (top row first) of 32 LEDs. Bit 31 is the leftmost LED.",
        "// Draw one with:   sparkyDrawFace(mx, SPARKY_MOOD_FACES[SPARKY_MOOD_HAPPY]);",
        "// where mx is your MD_MAX72XX object (hardware type FC16_HW, 4 devices).",
        "#pragma once",
        "#include <stdint.h>",
        "",
        "// If a face shows up mirrored left-right, change SPARKY_FLIP_X to 0.",
        "// If it shows up upside down, change SPARKY_FLIP_Y to 1.",
        "#ifndef SPARKY_FLIP_X",
        "#define SPARKY_FLIP_X 1",
        "#endif",
        "#ifndef SPARKY_FLIP_Y",
        "#define SPARKY_FLIP_Y 0",
        "#endif",
        "",
    ]
    for name, rows in data["faces"].items():
        ident = idents[name] = _ident(name, used)
        lines.append(f"// {name}")
        lines.append(f"static const uint32_t {ident}[8] = {{")
        lines += [f"  0x{row_bits(r):08X}UL,  // {r}" for r in rows]
        lines += ["};", ""]
    lines.append("enum SparkyMood : uint8_t {")
    lines += [f"  SPARKY_MOOD_{m.upper()}," for m in MOODS]
    lines += ["  SPARKY_MOOD_COUNT", "};", ""]
    lines.append("static const uint32_t* const SPARKY_MOOD_FACES[SPARKY_MOOD_COUNT] = {")
    lines += [f"  {idents[data['moods'][m]]},  // {m}: {data['moods'][m]}" for m in MOODS]
    lines += ["};", ""]
    lines += [
        "// Works with MD_MAX72XX or anything that has setPoint(row, column, on).",
        "// Tip: wrap it in mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF / ON) to avoid flicker.",
        "template <typename Matrix>",
        "void sparkyDrawFace(Matrix &mx, const uint32_t face[8]) {",
        "  for (uint8_t r = 0; r < 8; r++) {",
        "    for (uint8_t c = 0; c < 32; c++) {",
        "      bool on = (face[r] >> (31 - c)) & 1UL;",
        "      mx.setPoint(SPARKY_FLIP_Y ? 7 - r : r, SPARKY_FLIP_X ? 31 - c : c, on);",
        "    }",
        "  }",
        "}",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- voice lines
def to_device_wav(wav_bytes: bytes) -> bytes:
    """Any mono/stereo 16-bit WAV -> 16 kHz mono 16-bit WAV.

    resample_poly low-pass filters while resampling; plain interpolation folded the
    voice's 8-11 kHz content back down as a harsh fizz on s/t sounds.
    """
    from math import gcd

    import numpy as np
    from scipy.signal import resample_poly  # scipy comes with scikit-learn (core requirement)

    with wave.open(io.BytesIO(wav_bytes)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        frames = w.readframes(w.getnframes())
    if width != 2:
        raise StudioError("Expected 16-bit audio from the voice.")
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != DEVICE_SAMPLE_RATE and len(audio):
        g = gcd(DEVICE_SAMPLE_RATE, rate)
        audio = resample_poly(audio, DEVICE_SAMPLE_RATE // g, rate // g)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(DEVICE_SAMPLE_RATE)
        w.writeframes(np.clip(audio, -32768, 32767).astype("<i2").tobytes())
    return out.getvalue()


def add_voice_line(text: str, trigger: str, mood: str, wav_bytes: bytes) -> Dict:
    text = " ".join(str(text or "").split())
    if not text or len(text) > MAX_TEXT:
        raise StudioError(f"A voice line must be 1-{MAX_TEXT} characters.")
    if trigger not in TRIGGERS:
        raise StudioError("Unknown trigger.")
    if mood not in MOODS:
        raise StudioError("Unknown mood.")
    device_wav = to_device_wav(wav_bytes)
    line_id = uuid.uuid4().hex
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    (VOICE_DIR / f"{line_id}.wav").write_bytes(device_wav)
    samples = (len(device_wav) - 44) // 2
    line = {
        "id": line_id, "text": text, "trigger": trigger, "mood": mood,
        "duration_s": round(samples / DEVICE_SAMPLE_RATE, 2), "bytes": len(device_wav),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    data = load()
    data["voice_lines"].append(line)
    save(data)
    return line


def voice_path(line_id: str) -> Path:
    path = VOICE_DIR / f"{check_line_id(line_id)}.wav"
    if not path.exists():
        raise StudioError("Unknown voice line.")
    return path


def delete_voice_line(line_id: str) -> Dict:
    check_line_id(line_id)
    data = load()
    before = len(data["voice_lines"])
    data["voice_lines"] = [v for v in data["voice_lines"] if v["id"] != line_id]
    if len(data["voice_lines"]) == before:
        raise StudioError("Unknown voice line.")
    (VOICE_DIR / f"{line_id}.wav").unlink(missing_ok=True)
    save(data)
    return data


def export_voice_zip() -> bytes:
    data = load()
    buf = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for i, line in enumerate(data["voice_lines"], 1):
            path = VOICE_DIR / f"{line['id']}.wav"
            if not path.exists():
                continue
            fname = f"{i:02d}_{line['trigger']}.wav"
            z.write(path, fname)
            manifest.append({"file": fname, **{k: line[k] for k in ("text", "trigger", "mood", "duration_s", "bytes")}})
        z.writestr("manifest.json", json.dumps({"sample_rate": DEVICE_SAMPLE_RATE, "lines": manifest}, indent=1))
        z.writestr("README.txt", (
            "Sparky voice lines - 16 kHz, 16-bit, mono WAV files.\n"
            "manifest.json says which line plays when (trigger) and which face to show (mood).\n"
            "To use them on the ESP32, upload these files to its flash file system (LittleFS)\n"
            "and play them through the MAX98357A amplifier with an I2S audio library.\n"))
    return buf.getvalue()


def summary(data: Optional[Dict] = None) -> Dict:
    data = data or load()
    used = sum(v["bytes"] for v in data["voice_lines"])
    return {
        "faces": data["faces"], "moods": data["moods"], "mood_names": MOODS,
        "voice_lines": data["voice_lines"], "triggers": TRIGGERS,
        "flash": {"used_bytes": used, "budget_bytes": FLASH_BUDGET_BYTES},
        "default_faces": list(DEFAULT_FACES),
    }


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
    _update_device(device_id, {"pack_version": pack_version, "free_bytes": int(free_bytes), "error": error,
                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def record_device_status(device_id: int, status: Dict) -> None:
    """What a Sparky reports about itself: Wi-Fi signal, and how smoothly its last answer played."""
    _update_device(device_id, {**status, "status_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def _update_device(device_id: int, fields: Dict) -> None:
    sync = device_sync()
    sync.setdefault(str(device_id), {}).update(fields)
    STUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SYNC_STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(sync, indent=1), encoding="utf-8")
    tmp.replace(SYNC_STORE)
