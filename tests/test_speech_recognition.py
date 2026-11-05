"""The recogniser's hint words are only safe with the silence filter, so the two must stay together."""
from types import SimpleNamespace

from core.services import voice_service


def test_transcribe_uses_the_silence_filter_with_the_hint_words(monkeypatch):
    seen = {}

    class FakeWhisper:
        def transcribe(self, audio, **kwargs):
            seen.update(kwargs)
            return [SimpleNamespace(text=" Why is grass green? ")], None

    monkeypatch.setattr(voice_service, "_get_whisper_model", lambda: FakeWhisper())
    assert voice_service.VoiceService().transcribe(b"audio") == "Why is grass green?"
    assert seen["vad_filter"] is True
    assert "Sparky" in seen["hotwords"]
