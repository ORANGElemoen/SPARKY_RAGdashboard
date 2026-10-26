# STEM Voice Tutor — Hardware Client Protocol

This is the wire protocol for a physical device (the Sparky ESP32 unit)
talking to the server directly, as opposed to the browser UI. The firmware in
`firmware/sparky/` implements it (`ask.cpp` for the voice question,
`pack_sync.cpp` for the personality pack), and `scripts/fake_sparky.py` is a
Python reference client. This document is the single source of truth both
sides match, along with the server in `core/routers/voice.py`.

**Version: 1.** The `protocol_version` field in every response lets this
evolve without breaking already-deployed devices — bump it and add a
migration note here when the framing or metadata shape changes.

## Authentication

Every request from a device includes:

```
X-Device-Key: <api key>
```

The key is issued once per device from `POST /admin/devices` (see the
Devices admin page, `/admin/devices/view`) and is shown exactly once at
creation time — only its hash is stored server-side, so it can't be
recovered later if lost (provision a new device instead).

A request with a missing key is treated as a browser request (unauthenticated,
CSRF-protected instead). A request with a **present but invalid or revoked**
key is rejected immediately with `401`, distinct from CSRF's `403`, so
firmware can tell "I have the wrong key" apart from "I'm missing a step."

A device key request is exempt from the browser CSRF check — a per-device
key is a different, stronger trust model than a browser cookie, and a
forged/garbage key can't pass the check (it's validated against a stored
hash), so this can't be used to bypass CSRF for an actual browser request.

## Endpoint

```
POST /api/v1/voice/query
```

Same endpoint the browser uses. Request body is unchanged: `multipart/form-data`
with an `audio` file field (any ffmpeg/PyAV-readable format) and an optional
`session_id` field (see "Sessions" below).

The **response format** is chosen by the `Accept` header:

| Accept header                  | Response                                   |
|---------------------------------|---------------------------------------------|
| *(absent / anything else)*      | JSON + base64 WAV (browser default, unchanged) |
| `application/x-tutor-voice`     | Framed binary format described below       |
| `application/x-tutor-voice; version=2` | Same framing, streamed while the answer is written (see "Version 2") |

A real device should always send both `X-Device-Key` and
`Accept: application/x-tutor-voice` (Sparky's firmware sends `version=2`).

## Response framing (`application/x-tutor-voice`)

```
[4 bytes big-endian uint32]   metadata_length
[metadata_length bytes]        UTF-8 JSON metadata
repeated frame_count times:
    [4 bytes big-endian uint32]   frame_length
    [frame_length bytes]           one complete, independently-playable WAV file
```

Nothing but length-prefixed byte blocks — deliberately no dependency
beyond being able to read 4 bytes as a big-endian unsigned integer, so
it's straightforward to parse in embedded C.

The response is sent as a streamed HTTP body (chunked transfer encoding):
the metadata frame arrives first, then each sentence's audio frame as soon
as it finishes synthesizing — **the client can start playing the first
frame before later ones exist.** Frames arrive in order and should be
played in order; there is no frame index field because order is guaranteed
by the stream itself.

### Metadata JSON shape

```json
{
  "protocol_version": 1,
  "transcript": "why is the sky blue",
  "answer_text": "The sky looks blue because...",
  "confidence": 0.76,
  "used_general_knowledge": false,
  "sources": [
    {
      "id": 1,
      "document_id": 4,
      "document_name": "STEM_Child_Tutor_Guide.pdf",
      "similarity": 0.76,
      "download_url": "/api/v1/documents/4/download",
      "text": "...",
      "chunk_id": 210
    }
  ],
  "frame_count": 3
}
```

- `answer_text` is for a display (LCD/e-ink) — it may include a trailing
  source-citation footer for on-screen reading.
- The audio frames are synthesized from a citation-free version of the
  answer (citations are for display, never spoken), so don't expect the
  spoken audio and `answer_text` to be word-for-word identical.
- `sources` is empty when `used_general_knowledge` is true — display that
  distinction plainly rather than showing an empty list.

### Version 2 (streaming)

`Accept: application/x-tutor-voice; version=2`. In version 1 the metadata
can only be sent once the whole answer has been written (it carries
`answer_text` and `frame_count`). In version 2 each sentence is spoken as
soon as the AI has written it, so the child hears the answer start while
the rest is still being generated (REQ-N-01: about 3.6 s instead of 6.3 s
on the server).

```
[len][metadata JSON]        protocol_version 2, frame_count: null, no answer_text
[len][WAV]  ...             one per sentence, as each is written
[len][summary JSON]         {"protocol_version": 2, "answer_text": "...", "frame_count": N}
```

- Same length-prefixed blocks. A block after the metadata is audio if it
  starts with `RIFF`; otherwise it is the closing summary (always the last
  block).
- Use the summary's `frame_count` to check that every sentence arrived.
- The transcript-too-short and error cases still send metadata, the spoken
  retry/error prompt, then the summary.

## Sessions

`session_id` scopes conversation memory (follow-up questions like "how does
that work?") to one device's own conversation — **never shared across
devices.** Generate a UUID once per device (or per "conversation," if the
firmware wants to support an explicit "new conversation" reset) and persist
it in NVS flash; send the same value on every request until you want a
fresh conversation. See `core/services/simple_rag_service.py`'s
conversation-memory design for why this boundary matters: a global/shared
session would leak one learner's conversation into another's.

## Errors

Standard HTTP status codes:
- `400` — bad request (empty/oversized audio)
- `401` — invalid or revoked device key
- `503` — the tutor is at its concurrent-request cap
  (`MAX_CONCURRENT_VOICE_REQUESTS`, default 4) and can't take another
  request right now; back off and retry rather than queuing indefinitely
- `500` — unexpected server error

All error responses are plain JSON (`{"detail": "..."}`), regardless of
the `Accept` header — a device should always be prepared to parse a plain
JSON error body even when it requested the binary format, since an error
can occur before any audio synthesis starts.

## Personality pack (Sparky Studio content over Wi-Fi)

Additive to protocol version 1 - existing endpoints are unchanged. All of
these need `X-Device-Key`; a browser request without one gets `401`.

| Request | Response |
|---|---|
| `GET /api/v1/device/pack` (optional `If-None-Match: "<pack_version>"`) | `304` if unchanged, else `200` JSON manifest with an `ETag` |
| `GET /api/v1/device/pack/voice/<id>.wav` | the voice line: 16 kHz, 16-bit, mono WAV with a 44-byte header (`404` if unknown) |
| `POST /api/v1/device/pack/ack` `{"pack_version", "free_bytes", "error"?}` | `{"ok": true}` - shown on the Studio's "Your Sparkys" table |
| `GET /api/v1/device/commands?wait=25` (long-poll, at most 30) | `204` nothing, or `{"type": "show_face", "rows": [8 x 32 chars], "seconds": 10}` or `{"type": "sync"}` |

Manifest:

```json
{
  "pack_version": "3f9a1c07d2e4b5a6",
  "protocol_version": 1,
  "sample_rate": 16000,
  "mood_order": ["idle", "listening", "thinking", "talking", "happy", "error"],
  "faces": {"Happy  ^ ^": ["................................", "..."]},
  "moods": {"idle": "Sleepy / idle", "happy": "Happy  ^ ^"},
  "voice_lines": [{"id": "<32 hex>", "trigger": "button_release", "mood": "thinking", "bytes": 61716}]
}
```

Faces are 8 rows of 32 characters, top row first, `#` = LED on, `.` = off.

Device rules:
- Voice-line ids never change content - download only ids you don't have
  (or whose file size differs), delete files whose id is no longer listed.
- Download everything first, then replace `manifest.json`, then the stored
  version; never switch to a half-downloaded pack.
- Only sync / long-poll while idle (not listening, thinking or talking).
- On `{"type": "sync"}` sync now (the server sends it whenever Studio
  content changes); otherwise sync at boot and every 5 minutes.
- `scripts/fake_sparky.py` is the reference implementation.

## Firmware guidance (not a server concern, recorded here for later)

- **Don't request a live "thinking" acknowledgement from the server.** Play
  a locally-stored, pre-recorded sound immediately on button-release
  instead. It's instant, free, and doesn't risk sounding repetitive the
  way a small model's live ad-libbed acknowledgement would — the latency
  it's masking is exactly the time the real request is in flight anyway.
- Handle Wi-Fi reconnect and a friendly "having trouble connecting" display
  state; don't assume the server is always reachable.
- Persist `session_id` and the device's `X-Device-Key` in NVS flash, not in
  RAM only — both should survive a reboot.
