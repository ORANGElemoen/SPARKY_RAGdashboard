"""
Binary framing for the hardware (ESP32) voice response format.

See docs/PROTOCOL.md for the full spec. Framing:

    [4 bytes big-endian uint32: metadata_length]
    [metadata_length bytes: UTF-8 JSON metadata]
    repeated frame_count times:
        [4 bytes big-endian uint32: frame_length]
        [frame_length bytes: one self-contained WAV file]

Kept deliberately simple (fixed-width length prefixes, no dependencies
beyond stdlib json/struct) so it's easy to parse in embedded C - an ESP32
just needs to read 4 bytes, know how many more bytes follow, repeat.
"""

import json
import struct
from typing import Any, Dict


WAV_FORMAT_MULAW = 7


def to_mulaw_wav(wav_bytes: bytes) -> bytes:
    """A sentence's WAV -> 16 kHz G.711 mu-law WAV with a plain 44-byte header: 16 KB/s, not 44.

    For a board on the internet route, whose connection tops out near 22 KB/s (docs/PROTOCOL.md).
    """
    import numpy as np

    from .studio_service import DEVICE_SAMPLE_RATE, to_device_wav  # needs scipy, so only when used

    samples = np.frombuffer(to_device_wav(wav_bytes)[44:], dtype="<i2").astype(np.int32)
    negative = samples < 0
    magnitude = np.minimum(np.abs(samples), 32635) + 0x84
    exponent = np.floor(np.log2(magnitude)).astype(np.int32) - 7
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    data = (~((negative.astype(np.int32) << 7) | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8).tobytes()
    header = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, WAV_FORMAT_MULAW, 1,
              DEVICE_SAMPLE_RATE, DEVICE_SAMPLE_RATE, 1, 8) + b"data" + struct.pack("<I", len(data)))
    return header + data


def pack_frame(data: bytes) -> bytes:
    """One length-prefixed frame: 4-byte big-endian length + payload."""
    return struct.pack(">I", len(data)) + data


def pack_metadata(metadata: Dict[str, Any]) -> bytes:
    """The metadata frame's payload (not length-prefixed itself - callers
    combine this with pack_frame or write the length separately)."""
    return json.dumps(metadata, ensure_ascii=False).encode("utf-8")
