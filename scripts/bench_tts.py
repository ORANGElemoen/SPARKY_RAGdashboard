"""Benchmark Piper vs KittenTTS 2 on Sparky-style tutor answers.

Run from the repo root inside the isolated venv (has kittenml; sees the
main install's piper/torch via --system-site-packages):

    PYTHONUTF8=1 .venv-kitten/Scripts/python scripts/bench_tts.py
    PYTHONUTF8=1 .venv-kitten/Scripts/python scripts/bench_tts.py --reference my_voice.wav

PYTHONUTF8=1 is needed on Windows: kittenml opens its voices JSON without
an encoding, so it crashes under the default cp1252 codepage.

Writes WAVs to data/tts_bench/ so you can listen. RTF = synth time / audio
length; under 1.0 means faster than real time. Ollama's default model is
loaded first so the numbers reflect a real Sparky machine under load.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np
import psutil
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.services.voice_service import _get_piper_voice  # noqa: E402

OUT = Path("data/tts_bench")
SENTENCES = [
    "Great question!",
    "Plants make their own food using sunlight, water, and air, and this is called photosynthesis.",
    "Imagine the leaf is a tiny kitchen, and sunlight is the stove that cooks the food.",
    "You are doing really well, so keep asking questions like that!",
]
# Kitten-only extra: shows off expression tags (Piper would read them aloud)
EXPRESSIVE = "[joyful] Wow, you got it right! <laugh> That was (((really))) clever thinking."

proc = psutil.Process()


def rss_mb():
    return proc.memory_info().rss / 2**20


def warm_ollama():
    model = yaml.safe_load(open("config/llm_config.yaml", encoding="utf-8")).get("default_model")
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({"model": model, "prompt": "hi", "keep_alive": "15m", "stream": False}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=300).read()
        print(f"Ollama model '{model}' loaded (kept warm 15 min)")
    except Exception as e:
        print(f"WARNING: could not load Ollama model '{model}' ({e}) - results are without LLM load")


def save_wav(path, audio, rate):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def report(name, load_s, load_mb, rows):
    first, total_t, total_a = rows[0][0], sum(r[0] for r in rows), sum(r[1] for r in rows)
    print(f"\n== {name}")
    print(f"   load: {load_s:.1f}s, +{load_mb:.0f} MB RAM")
    for i, (t, a) in enumerate(rows, 1):
        print(f"   sentence {i}: {t:.2f}s synth for {a:.2f}s audio (RTF {t / a:.2f})")
    print(f"   first-sentence latency {first:.2f}s | overall RTF {total_t / total_a:.2f}")


def bench_piper():
    m0, t0 = rss_mb(), time.perf_counter()
    voice = _get_piper_voice()
    load_s, load_mb = time.perf_counter() - t0, rss_mb() - m0
    list(voice.synthesize("Warm up."))
    rows = []
    for i, s in enumerate(SENTENCES, 1):
        t0 = time.perf_counter()
        chunks = list(voice.synthesize(s))
        t = time.perf_counter() - t0
        audio = np.concatenate([c.audio_float_array for c in chunks])
        rate = chunks[0].sample_rate
        save_wav(OUT / f"piper_{i}.wav", audio, rate)
        rows.append((t, len(audio) / rate))
    report(f"Piper ({os.getenv('PIPER_VOICE', 'en_US-hfc_female-medium')})", load_s, load_mb, rows)


def bench_kitten(weights, voices, reference, reference_text):
    from kittenml import KittenTTS

    m0, t0 = rss_mb(), time.perf_counter()
    kw = {"weights": weights} if weights else {}
    m = KittenTTS("KittenML/kitten-tts-2", **kw)
    load_s, load_mb = time.perf_counter() - t0, rss_mb() - m0
    m.generate("Warm up.", voice=voices[0])

    runs = [(v, {"voice": v}) for v in voices]
    if reference:
        ref = {"reference": reference}
        if reference_text:
            ref["reference_text"] = reference_text
        runs.append(("clone", ref))

    for label, kwargs in runs:
        rows = []
        for i, s in enumerate(SENTENCES, 1):
            t0 = time.perf_counter()
            audio = np.asarray(m.generate(s, **kwargs), dtype=np.float32).squeeze()
            t = time.perf_counter() - t0
            save_wav(OUT / f"kitten_{label}_{i}.wav", audio, m.sample_rate)
            rows.append((t, len(audio) / m.sample_rate))
        report(f"KittenTTS 2 [{weights or 'default'}] voice={label}", load_s, load_mb, rows)
        audio = np.asarray(m.generate(EXPRESSIVE, **kwargs), dtype=np.float32).squeeze()
        save_wav(OUT / f"kitten_{label}_expressive.wav", audio, m.sample_rate)
        load_s = load_mb = 0  # only the first run pays the load cost
    print(f"\nPeak process RAM: {rss_mb():.0f} MB (Piper + Kitten + Python)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--weights", default="emb4", help="'emb4' (506 MiB) or '' for full (947 MiB)")
    p.add_argument("--voices", default="Luna,Bruno", help="comma-separated built-in voices")
    p.add_argument("--reference", help="WAV of one speaker, 5-30s, for voice cloning")
    p.add_argument("--reference-text", help="exact words spoken in the reference clip")
    p.add_argument("--skip-ollama", action="store_true")
    a = p.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if not a.skip_ollama:
        warm_ollama()
    print(f"CPU: {psutil.cpu_count(logical=False)} cores, RAM total {psutil.virtual_memory().total / 2**30:.1f} GB, "
          f"free {psutil.virtual_memory().available / 2**30:.1f} GB")
    bench_piper()
    bench_kitten(a.weights, a.voices.split(","), a.reference, a.reference_text)
    print(f"\nListen to the WAVs in {OUT.resolve()}")
