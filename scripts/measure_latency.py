#!/usr/bin/env python3
"""
M-14 / REQ-N-01: time the server pipeline (speech-to-text -> answer -> speech) without the device.

Speaks ten child-style questions with the Sparky voice at 16 kHz (what the ESP32 mic sends), posts
each to /api/v1/voice/query exactly like the firmware (Accept: application/x-tutor-voice) and times:
  heard   - metadata frame received (speech-to-text + retrieval + LLM done)
  speaks  - first answer sentence fully received (+ text-to-speech of sentence 1) = REQ-N-01 point
  done    - whole answer received
REQ-N-01: end of utterance -> start of spoken response <= 5.0 s under normal load.

Uses a temporary device key (created and removed). The server must be running.
    python scripts/measure_latency.py [--base-url http://127.0.0.1:8001] [--repeat 1] [--protocol 2]
Protocol 2 streams the answer while the AI writes it; 1 is the original whole-answer format.
"""
import argparse
import json
import statistics
import struct
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUESTIONS = [
    "Why is the sky blue?",
    "How do plants make their own food?",
    "What is gravity?",
    "Why does the moon change shape?",
    "How many legs does a spider have?",
    "What is three times seven?",
    "Why do we need to drink water?",
    "How does a rainbow form?",
    "What makes thunder?",
    "Can you tell me a fun fact about elephants?",
]


def ask(http, key, wav, protocol=2):
    t0 = time.perf_counter()
    heard = speaks = None
    buf = b""
    meta = None
    frames = 0
    with http.stream("POST", "/api/v1/voice/query",
                     headers={"X-Device-Key": key, "Accept": "application/x-tutor-voice"
                              + ("; version=2" if protocol == 2 else "")},
                     data={"session_id": uuid.uuid4().hex},
                     files={"audio": ("question.wav", wav, "audio/wav")}, timeout=120) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            buf += chunk
            while len(buf) >= 4:                       # parse [u32 length][block] as it arrives
                (n,) = struct.unpack(">I", buf[:4])
                if len(buf) < 4 + n:
                    break
                block, buf = buf[4:4 + n], buf[4 + n:]
                if meta is None:
                    meta, heard = json.loads(block), time.perf_counter() - t0
                elif block[:4] == b"RIFF":
                    frames += 1
                    if speaks is None:
                        speaks = time.perf_counter() - t0
                else:                                   # v2 closing summary: full text + sentence count
                    meta.update(json.loads(block))
    return meta, frames, heard, speaks, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8001")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--protocol", type=int, choices=(1, 2), default=2)
    args = ap.parse_args()

    from core.services import studio_service
    from core.services.voice_service import VoiceService

    voice = VoiceService()
    wavs = [(q, studio_service.to_device_wav(voice.synthesize(q))) for q in QUESTIONS]

    admin = httpx.Client(base_url=args.base_url, timeout=30)
    csrf = lambda: {"X-CSRF-Token": admin.get("/api/v1/csrf-token").json()["csrf_token"]}  # noqa: E731
    dev = admin.post("/admin/devices", json={"name": "Latency test (temporary)"}, headers=csrf()).json()
    http = httpx.Client(base_url=args.base_url)
    rows = []
    try:
        ask(http, dev["api_key"], wavs[0][1], args.protocol)   # warm-up, not counted
        for _ in range(args.repeat):
            for q, wav in wavs:
                meta, frames, heard, speaks, done = ask(http, dev["api_key"], wav, args.protocol)
                ok = frames == meta["frame_count"]
                rows.append((q, meta["transcript"], heard, speaks, done, frames, ok))
                print(f"{speaks:5.1f} s to first sentence | heard {heard:4.1f} s | all {done:5.1f} s | "
                      f"{frames}/{meta['frame_count']} sentences | {q!r} -> {meta['transcript']!r}", flush=True)
    finally:
        admin.delete(f"/admin/devices/{dev['id']}", headers=csrf())
        admin.delete(f"/admin/devices/{dev['id']}/purge", headers=csrf())

    speaks = [r[3] for r in rows]
    print(f"\nprotocol {args.protocol} | {len(rows)} questions | first sentence: median {statistics.median(speaks):.1f} s, "
          f"max {max(speaks):.1f} s | REQ-N-01 (<= 5.0 s): {sum(s <= 5.0 for s in speaks)}/{len(rows)} pass | "
          f"complete answers: {sum(r[6] for r in rows)}/{len(rows)}")


if __name__ == "__main__":
    main()
