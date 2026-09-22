# API Documentation

API reference for the STEM Voice Tutor backend (see [CLAUDE.md](../CLAUDE.md) and
[PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) for the fuller project context).

## Base URL

```
http://127.0.0.1:8001
```

When a physical device (ESP32) is involved, use the host machine's LAN IP instead
of `127.0.0.1` so the device can actually reach it over WiFi.

## Authentication

Two different trust models, depending on the caller:

- **Browser clients** (the web UI): no API key. State-changing requests
  (POST/PUT/DELETE to `/api/v1/*` or `/admin/*`) require a CSRF token instead -
  fetch one from `GET /api/v1/csrf-token` and send it back as an `X-CSRF-Token`
  header. The web UI does this automatically.
- **Physical devices**: register a device in `/admin/devices` to get a one-time
  API key (shown once, never recoverable after). Send it as an `X-Device-Key`
  header on every request. A valid device key bypasses the CSRF check (a device
  can't do a browser session handshake); an invalid one is rejected with `401`.
  Only a SHA-256 hash of the key is ever stored server-side.

## Content Types

JSON for most endpoints; `multipart/form-data` for file/audio uploads.

## Error Handling

Standard HTTP status codes:

- `200` - Success
- `400` - Bad Request (validation error)
- `401` - Invalid or missing device key (device-authenticated endpoints)
- `403` - Missing/invalid CSRF token (browser-authenticated state changes)
- `404` - Not Found
- `422` - Unprocessable Entity (Pydantic validation error)
- `500` - Internal Server Error

Error response format:
```json
{
  "detail": "Error description"
}
```

## Core Endpoints

### `POST /api/v1/query` - Ask a text question

```json
{
  "query": "What is gravity?",
  "session_id": "optional-session-id-for-conversation-memory"
}
```

Response:
```json
{
  "answer": "Gravity is the force that pulls objects toward each other...",
  "sources": [
    {"document": "Physics_Grade8.pdf", "chunk_text": "...", "similarity": 0.87}
  ],
  "confidence": 0.87,
  "used_general_knowledge": false,
  "timestamp": "2026-09-23T10:00:00",
  "query": "What is gravity?"
}
```

`used_general_knowledge` is `true` when no relevant document chunk was found and
the tutor fell back to its own knowledge instead of refusing to answer - this is
a deliberate design choice for a kids' tutor, not a bug.

### `POST /api/v1/voice/query` - Ask a spoken question

Multipart form fields: `audio` (file, required), `session_id` (optional).

Default response (browser clients):
```json
{
  "transcript": "what is gravity",
  "answer_text": "Gravity is the force that...",
  "audio_base64": "<base64-encoded WAV>",
  "sources": [...],
  "used_general_knowledge": false
}
```

Send `Accept: application/x-tutor-voice` to instead receive a compact
length-prefixed binary framing intended for embedded/hardware clients - see
[PROTOCOL.md](PROTOCOL.md) for the full wire format.

### `POST /api/v1/documents` - Upload a document

Multipart form field: `file` (PDF, DOCX, TXT, MD, or CSV).

### `GET /api/v1/documents/{id}/chunks` - Paginated chunk viewer

Query params: `page`, `page_size`.

### `POST /api/v1/translate` - Translate an answer

```json
{
  "text": "Gravity is the force that pulls objects together.",
  "target_language": "fr"
}
```

For spot-checking answer quality in a reviewer's own language - does not change
the tutor's actual response language.

### `GET /health` - Health check

Returns `200` with basic service status; used both for manual checks and by
device firmware to confirm connectivity before/after WiFi onboarding.

## Admin Endpoints

All under `/admin`, browser-authenticated (CSRF token required for
state-changing calls). See `core/routers/admin.py` for the full set; notable
ones:

- `GET/POST /admin/settings/language` - active response language
- `GET/POST /admin/models`, `POST /admin/models/switch` - Ollama model management
- `GET/POST /admin/devices` - list/register physical devices
- `DELETE /admin/devices/{id}` - revoke a device (disables its key)
- `DELETE /admin/devices/{id}/purge` - permanently delete an already-revoked device
- `GET /admin/devices/{id}/summary` - stats + AI-generated activity summary for one device's learner
- `GET /admin/documents/management` (page) - content analysis/cleanup tools

## Notes

- No enforced rate limiting is currently implemented - don't rely on any
  specific requests-per-minute figure.
- Responses may be served from a short-lived cache; failed/errored answers are
  explicitly never cached (a real bug once caused a failure to be served
  repeatedly for up to 24 hours - fixed).
