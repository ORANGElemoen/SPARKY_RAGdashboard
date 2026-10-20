"""Sparky speaks in his own voice unless told otherwise."""

from core.services import voice_service as vs


def test_sparky_voice_used_when_present(tmp_path, monkeypatch):
    monkeypatch.delenv("PIPER_VOICE", raising=False)
    assert vs._voice_name(tmp_path) == vs.FALLBACK_VOICE          # fresh checkout: no Sparky model
    (tmp_path / f"{vs.SPARKY_VOICE}.onnx").write_bytes(b"")
    assert vs._voice_name(tmp_path) == vs.SPARKY_VOICE
    monkeypatch.setenv("PIPER_VOICE", "en_US-ryan-medium")         # explicit choice still wins
    assert vs._voice_name(tmp_path) == "en_US-ryan-medium"
