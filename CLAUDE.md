# CLAUDE.md - STEM Voice Tutor Project Settings

## 🎯 Project Overview

**STEM Voice Tutor** - A locally-hosted, voice-driven STEM tutor for children,
built with low-connectivity deployments in mind (developed with Sub-Saharan
Africa in mind). A child asks a question by voice; the system transcribes it,
answers it in a friendly, encouraging way grounded in uploaded STEM
textbooks (falling back to general knowledge when nothing relevant is
uploaded), and speaks the answer back. Everything runs fully offline/locally
— no cloud LLM, STT, or TTS APIs.

This project started as a generic "upload documents, ask questions" RAG
system and has been substantially repurposed. The original document-QA
interface still works (Text Chat tab), but the voice pipeline (Voice Chat
tab, `/api/v1/voice/query`) is now the primary feature.

**For the full current state, recent bug fixes and why they mattered, and
known rough edges, read [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) first.**
This file (CLAUDE.md) is the shorter, ongoing-guidance version.

**Next phase (not started)**: ESP32 firmware (mic + speaker + LCD) that
calls the same voice API over local WiFi. Hardware specifics aren't decided.

## 🏗️ Project Structure

```
open-source-rag-system/
├── core/
│   ├── main.py                    # FastAPI app: security headers, CSRF, router registration
│   ├── ollama_client.py           # Ollama LLM client
│   ├── routers/
│   │   ├── query.py               # POST /api/v1/query (text) + get_rag_service DI
│   │   ├── voice.py               # POST /api/v1/voice/query (STT -> RAG -> TTS)
│   │   ├── documents.py           # Upload, list, download, chunk retrieval
│   │   ├── admin.py               # Model/language/database admin endpoints
│   │   └── document_manager.py    # Document content analysis/cleanup
│   ├── services/
│   │   ├── simple_rag_service.py  # Core tutor logic - READ THIS FIRST for RAG behavior
│   │   ├── voice_service.py       # faster-whisper (STT) + piper (TTS), lazy singletons
│   │   ├── document_service.py    # Upload validation, chunking, embeddings
│   │   └── query_service.py       # Trimmed to just get_document_chunks() - see note below
│   ├── repositories/              # Data access layer (SQLite-backed)
│   ├── di/                        # Dependency injection container/service config
│   └── templates/                 # Admin dashboard, document management HTML
├── static/
│   ├── index.html                 # Main UI: Text Chat + Voice Chat tabs, single page
│   └── voice_samples/             # Sample TTS clips for comparing voices
├── config/
│   ├── llm_config.yaml            # Ollama model catalog + default_model
│   ├── language_config.yaml       # current_language (en/de)
│   ├── languages/*.yaml           # Prompt templates + response strings, one file per language
│   └── document_filters.yaml      # Admin document-filter keywords (empty by default)
├── data/                          # gitignored: storage/, piper_voices/, *.db
├── deployment/requirements/
│   ├── simple_requirements.txt    # Core deps
│   └── voice_requirements.txt     # Optional: faster-whisper, piper-tts
├── PROJECT_HANDOFF.md             # Detailed state/handoff doc - read for full context
└── simple_api.py                  # Entry point (imports core.main.main())
```

## 🧠 AI Assistant Guidelines

### Core Principles
1. **Reliability first**: every error handled gracefully, no crashes under normal use.
2. **The tutor never just refuses to answer**: this is a deliberate change from
   the original "zero-hallucination, documents-only" design. It grounds
   answers in uploaded documents when relevant, and falls back to the LLM's
   general knowledge in the same friendly tone otherwise. Don't reintroduce a
   hard refusal path without discussing it — it's the wrong shape for a kids'
   tutor.
3. **Fully local/offline**: no cloud LLM/STT/TTS APIs. This is a deliberate
   constraint (deployment target has limited/costly internet), not an
   oversight — don't suggest cloud alternatives as the default.
4. **Multi-language is data, not code**: language-specific strings and
   prompts live in `config/languages/*.yaml`. Never hardcode English or
   German text into Python for anything user-facing — add/edit a language
   file instead. See `load_language_strings()` in `simple_rag_service.py`.
5. **Be suspicious of leftover behavior from this project's previous life**
   as a Swiss municipal bio-waste assistant. Several serious bugs this
   session came from exactly that: hardcoded German content, hardcoded
   off-topic keyword filters, hardcoded "zero-hallucination" refusal
   messages. If you find German text, waste-disposal references, or
   "Quelle"/"Zitiere"/zero-hallucination language in code you're touching,
   it's probably leftover cruft, not intentional — check before assuming
   it's load-bearing. `core/services/query_service.py` had ~700 lines of
   exactly this kind of unreachable leftover code (including a second,
   independent hardcoded-German answer-generation path) trimmed down to the
   one method that's actually used (`get_document_chunks`) - if you're
   tempted to "restore" something from git history in that file, check
   first whether it was ever actually called by a router.

### Error Handling Philosophy
- Never crash: catch and handle every exception gracefully.
- Cleanup on failure: remove partial files, reset state on errors.
- Fallback mechanisms: e.g. voice deps are optional - `core/routers/voice.py`
  imports `faster_whisper`/`piper` lazily at request time, not at module
  level, so the server still starts fine without them installed; hitting the
  endpoint without them returns a clean 503 with the install command instead
  of crashing.

### Before changing `core/main.py` security headers
This has bitten us twice: the `Permissions-Policy` header blocked
`getUserMedia` (microphone) outright until explicitly set to
`microphone=(self)`, and the `Content-Security-Policy` header had no
`media-src` directive (falling back to `default-src 'self'`), which
silently blocked both `data:` and `blob:` audio URLs in the browser with no
thrown JS exception - it just looked like "audio won't play, 0:00
duration" with nothing in the console except a CSP violation. If you add
new browser capabilities (camera, geolocation, new resource types), check
these headers.

### CSRF pattern
Any POST/PUT/DELETE to `/api/v1/*` or `/admin/*` requires an `X-CSRF-Token`
header (see `csrf_middleware` in `core/main.py`). Every piece of frontend
JS that makes a state-changing request needs to call
`GET /api/v1/csrf-token` first and send the token back - there's a
`getCsrfToken()` helper duplicated in `static/index.html`,
`admin_dashboard.html`, and `document_management.html`. If you add a new
POST call anywhere in the frontend, it needs this or it will silently
403/500.

### Technology Stack
- **Backend**: FastAPI (`core/main.py`), dependency injection (`core/di/`)
- **LLM**: Ollama via `core/ollama_client.py` (default model: `mistral`,
  configured in `config/llm_config.yaml`)
- **RAG**: `SimpleRAGService` (`core/services/simple_rag_service.py`) -
  hybrid grounded/general-knowledge answering, language-aware prompts
- **STT**: `faster-whisper` (local, CPU, model size configurable)
- **TTS**: `piper-tts` (local, ONNX voice models in `data/piper_voices/`)
- **Vector search**: sentence-transformers + numpy-based similarity search
- **Storage**: SQLite (`data/rag_database.db`), audit log
  (`data/audit.db`)
- **Frontend**: single-page vanilla JS/HTML (`static/index.html`), two tabs

## 🔧 Common Development Tasks

### Running the system
```bash
python simple_api.py
# → http://127.0.0.1:8001/ui       (Text Chat + Voice Chat)
# → http://127.0.0.1:8001/admin    (models, language settings)
# → http://127.0.0.1:8001/admin/documents/management
```
Requires Ollama running with at least one model pulled. Voice features
require `pip install -r deployment/requirements/voice_requirements.txt`
plus a downloaded Piper voice model (see README).

Frontend changes (`static/*.html`, `core/templates/*.html`) take effect on
browser refresh - these are read fresh from disk on every request, no
server restart needed. Backend Python changes require a restart
(`reload=False` in `core/main.py`'s `uvicorn.run`, deliberately, per the
original project's "avoid import issues" comment).

### Key API Endpoints
- `POST /api/v1/query` - text question -> answer with sources
- `POST /api/v1/voice/query` - audio file -> `{transcript, answer_text, audio_base64}`
- `POST /api/v1/documents` - upload a document
- `GET /api/v1/documents/{id}/chunks` - paginated chunk viewer (uses the
  trimmed `QueryProcessingService`)
- `GET/POST /admin/settings/language` - active response language
- `GET/POST /admin/models`, `POST /admin/models/switch` - Ollama model management

### Common Issues & Solutions
- **numpy install fails on newer Python**: `numpy<2.0.0` has no wheels for
  very new Python versions and will try to build from source (needs a C
  compiler). Requirements are pinned `numpy<3.0.0` for this reason - don't
  tighten that pin without checking wheel availability first.
- **Ollama not available / no models**: `ollama pull <model>` and check
  `config/llm_config.yaml`'s `default_model` actually matches an installed
  model (`ollama list`) - a mismatch here silently degrades every query.
- **Voice audio won't play in browser**: check the CSP `media-src`
  directive first (see above) before assuming it's a JS bug.
- **Answers cut off mid-sentence**: check `max_tokens` isn't being clamped
  somewhere in `ollama_client.py`'s request options - this happened once
  already (see PROJECT_HANDOFF.md, bug #8).
- **Document upload fails silently / 500s**: check the `chunks` and
  `embeddings` table column names in `core/repositories/sqlite_repository.py`
  actually match what `document_service.py` and `vector_repository.py`
  insert/select - these have drifted before.

---

**See [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) for the detailed list of
bugs fixed this session (with root causes), known rough edges, and what to
hand off to a fresh Claude session.**
