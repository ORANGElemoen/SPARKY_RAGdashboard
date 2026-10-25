"""Sparky Studio: face storage, mood mapping, firmware header and voice-line audio."""

import io
import json
import math
import re
import struct
import wave
import zipfile

import pytest

from core.services import studio_service as studio


@pytest.fixture(autouse=True)
def tmp_studio(tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "STUDIO_DIR", tmp_path)
    monkeypatch.setattr(studio, "VOICE_DIR", tmp_path / "voice")
    monkeypatch.setattr(studio, "STORE", tmp_path / "studio.json")
    monkeypatch.setattr(studio, "SYNC_STORE", tmp_path / "device_sync.json")


def test_default_faces_are_32_by_8():
    for name, rows in studio.DEFAULT_FACES.items():
        assert studio.check_rows(rows) == rows, name
    assert set(studio.DEFAULT_MOODS) == set(studio.MOODS)
    assert all(face in studio.DEFAULT_FACES for face in studio.DEFAULT_MOODS.values())


@pytest.mark.parametrize("rows", [None, [], ["#" * 32] * 7, ["#" * 31] * 8, ["x" * 32] * 8])
def test_bad_faces_rejected(rows):
    with pytest.raises(studio.StudioError):
        studio.check_rows(rows)


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "bad\x00name"])
def test_bad_names_rejected(name):
    with pytest.raises(studio.StudioError):
        studio.clean_name(name)


@pytest.mark.parametrize("line_id", ["../studio", "..\\x", "abc", "A" * 32])
def test_voice_ids_cannot_escape_the_folder(line_id):
    with pytest.raises(studio.StudioError):
        studio.voice_path(line_id)


def test_row_bits_leftmost_led_is_bit_31():
    assert studio.row_bits("#" + "." * 31) == 0x80000000
    assert studio.row_bits("." * 31 + "#") == 1


def test_save_delete_and_mood_fallback():
    face = ["." * 32] * 7 + ["#" * 32]
    studio.put_face("Smile", face)
    studio.set_moods({"happy": "Smile"})
    assert studio.load()["moods"]["happy"] == "Smile"
    data = studio.delete_face("Smile")
    assert "Smile" not in data["faces"]
    assert data["moods"]["happy"] == studio.DEFAULT_MOODS["happy"]  # mood fell back to a real face
    with pytest.raises(studio.StudioError):
        studio.set_moods({"happy": "Nope"})


def test_import_viewer_file_skips_invalid():
    good = ["." * 32] * 8
    res = studio.import_faces({"format": studio.FACES_FORMAT, "faces": {"Mine": good, "Broken": ["#"]}})
    assert res == {"added": 1, "skipped": 1}
    assert studio.load()["faces"]["Mine"] == good


def test_header_has_every_face_and_mood():
    studio.put_face("Big grin!", ["#" * 32] + ["." * 32] * 7)
    header = studio.export_header()
    data = studio.load()
    arrays = re.findall(r"static const uint32_t (SPARKY_FACE_\w+)\[8\] = \{\n((?:  0x[0-9A-F]{8}UL,.*\n){8})\};", header)
    assert len(arrays) == len(data["faces"])
    assert "SPARKY_FACE_BIG_GRIN" in dict(arrays)
    assert "0xFFFFFFFFUL" in dict(arrays)["SPARKY_FACE_BIG_GRIN"].splitlines()[0]
    mood_block = header.split("SPARKY_MOOD_FACES[SPARKY_MOOD_COUNT] = {")[1].split("};")[0]
    refs = re.findall(r"(SPARKY_FACE_\w+),", mood_block)
    assert len(refs) == len(studio.MOODS) and set(refs) <= dict(arrays).keys()
    for mood in studio.MOODS:
        assert f"SPARKY_MOOD_{mood.upper()}," in header


def _tone(rate=22050, seconds=1.0):
    frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate))) for i in range(int(rate * seconds)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def test_voice_line_is_16khz_mono_and_exports():
    line = studio.add_voice_line("Hmm, let me think!", "button_release", "thinking", _tone())
    with wave.open(str(studio.voice_path(line["id"]))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert abs(w.getnframes() - 16000) <= 1
    assert line["duration_s"] == pytest.approx(1.0, abs=0.01)
    with zipfile.ZipFile(io.BytesIO(studio.export_voice_zip())) as z:
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["lines"][0]["text"] == "Hmm, let me think!"
        assert manifest["lines"][0]["file"] in z.namelist()
    studio.delete_voice_line(line["id"])
    assert studio.load()["voice_lines"] == []
