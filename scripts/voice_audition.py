"""Render the same Sparky lines with every Piper voice in data/piper_voices/.

    python scripts/voice_audition.py

Writes one WAV per voice (per speaker, for multi-speaker voices) to
data/voice_audition/ so voices can be compared by ear. To try a voice in the
app afterwards: set PIPER_VOICE=<name> before starting simple_api.py.
"""

import json
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig

VOICES = Path("data/piper_voices")
OUT = Path("data/voice_audition")
TEXT = [
    "Hi there, I'm Sparky! What would you like to learn about today?",
    "Great question! Plants make their own food using sunlight, water, and air.",
    "Imagine the leaf is a tiny kitchen, and sunlight is the stove that cooks the food.",
    "Wow, you got it right! You are doing really well, so keep asking questions like that!",
]
MAX_SPEAKERS = 6  # libritts has ~900 speakers; sample a spread instead of all


def render(voice, path, speaker_id=None):
    cfg = SynthesisConfig(speaker_id=speaker_id)
    rate = voice.config.sample_rate
    pause = b"\x00\x00" * int(rate * 0.6)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        for line in TEXT:
            for chunk in voice.synthesize(line, cfg):
                w.writeframes(chunk.audio_int16_bytes)
            w.writeframes(pause)


OUT.mkdir(parents=True, exist_ok=True)
for model in sorted(VOICES.glob("*.onnx")):
    name = model.stem
    if not Path(f"{model}.json").exists():
        print(f"{name}: skipped (download incomplete - no .onnx.json)")
        continue
    voice = PiperVoice.load(str(model))
    n = json.loads(Path(f"{model}.json").read_text(encoding="utf-8")).get("num_speakers", 1)
    if n <= 1:
        render(voice, OUT / f"{name}.wav")
        print(name)
        continue
    step = max(1, n // MAX_SPEAKERS)
    for sid in range(0, n, step)[:MAX_SPEAKERS]:
        render(voice, OUT / f"{name}__speaker{sid}.wav", sid)
    print(f"{name} ({n} speakers, sampled {min(n, MAX_SPEAKERS)})")
print(f"\nDone - listen in {OUT.resolve()}")
