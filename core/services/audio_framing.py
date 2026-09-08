"""
Binary framing for the hardware (ESP32) voice response format.

See PROTOCOL.md at the repo root for the full spec. Framing:

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


def pack_frame(data: bytes) -> bytes:
    """One length-prefixed frame: 4-byte big-endian length + payload."""
    return struct.pack(">I", len(data)) + data


def pack_metadata(metadata: Dict[str, Any]) -> bytes:
    """The metadata frame's payload (not length-prefixed itself - callers
    combine this with pack_frame or write the length separately)."""
    return json.dumps(metadata, ensure_ascii=False).encode("utf-8")
