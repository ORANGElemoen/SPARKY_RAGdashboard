# Project Handoff: STEM Voice Tutor for Children in Sub-Saharan Africa

**Purpose of this document**: give a new Claude session (or any new contributor) full context
on what this project actually is *now*, what's built, what's fixed, what's fragile, and
what's next — without having to rediscover everything from scratch.

## What this project actually is

This started as a generic, open-source "upload documents, ask questions" RAG (Retrieval-
Augmented Generation) system. It has since been repurposed and heavily modified into a
**voice-driven STEM tutor for children in Sub-Saharan Africa**.

**End goal (not yet built)**: a physical device — ESP32 microcontroller + microphone +
speaker + LCD screen — that a child can speak a question into. The ESP32 sends the audio
over local WiFi to this server, which transcribes it, answers it in a fun/encouraging way
grounded in uploaded STEM textbooks (falling back to general knowledge when nothing
relevant is uploaded), speaks the answer back, and the ESP32 plays it through a speaker
and shows the text on an LCD.

**What exists today**: the full server-side pipeline (speech-to-text → RAG tutor →
text-to-speech) is built, tested, and working end-to-end, testable right now from a
browser tab using this computer's own mic/speakers as a stand-in for the ESP32. The ESP32
hardware and firmware do not exist yet — that's the next phase.

Key constraints that shaped every decision below:
- **Fully local/offline** — no cloud APIs for LLM, STT, or TTS. This matches
  low-connectivity deployment (rural/low-bandwidth areas) and the original project's
  "no external API calls" design philosophy.
- **ESP32 will talk to this server over the local network** (not the internet).
- Everything runs on a Windows dev machine right now (Python 3.14, no GPU).

## Architecture

```
Browser mic (test today) ----\
                               \
ESP32 mic (future hardware) ----> POST /api/v1/voice/query (audio file)
                                        |
                                        v
                              1. Speech-to-Text (faster-whisper, local, CPU)
                                        |
                                        v
                              2. SimpleRAGService.answer_query(text)
                                        |
                                        v
                              3. Text-to-Speech (Piper, local, CPU)
                                        |
                                        v
                              JSON { transcript, answer_text, audio_base64 }
```

The text-only path (`POST /api/v1/query`, and the "Text Chat" tab in the web UI) still
works exactly as before and shares the same `SimpleRAGService` — voice is a thin wrapper
around it, not a separate answer-generation path.

## Core RAG behavior (the important part)

`core/services/simple_rag_service.py` is the heart of the system. Current behavior:

1. Search uploaded documents for relevant chunks (`_search_documents`).
2. **If relevant documents are found**: answer using them as grounding, in a friendly
   "STEM tutor for children" persona, and if the documents don't fully cover the
   question, the model is explicitly told to fill gaps with its own knowledge in the
   same style. Source citations are appended to the answer text.
3. **If nothing relevant is found**: falls back to a general-knowledge answer using the
   same tutor persona (`_generate_general_answer`) — it does **not** refuse to answer
   anymore. This was a deliberate product decision for a children's tutor (a strict
   "zero-hallucination, documents-only" bot is the wrong shape for open-ended kid
   questions).
4. Both paths return `text` (full answer, with source citations if any) and
   `spoken_text` (same answer, **without** citations — this is what gets sent to TTS,
   so citations are never read aloud, only shown on screen/LCD).

**Language system**: fully externalized and extensible, not hardcoded.
- `config/language_config.yaml` — one key, `current_language` (currently `en`).
- `config/languages/en.yaml`, `config/languages/de.yaml` — each holds the prompt
  templates (`prompt_template`, `general_prompt_template`) and every user-facing string
  for that language. **Adding a new language = adding one new YAML file** — it shows up
  automatically in the admin Settings page dropdown (`GET/POST /admin/settings/language`
  in `core/routers/admin.py`).
- `load_language_strings()` in `simple_rag_service.py` reads the active language fresh
  on every call (no caching), falls back to English defaults baked into
  `DEFAULT_LANGUAGE_STRINGS` if the config/files are missing or broken.
- `core/services/voice_service.py` reads `config/language_config.yaml` too and passes
  the current language as a hint to Whisper for better transcription accuracy.

## Voice pipeline specifics

- **STT**: `faster-whisper`, model size `base` (env var `WHISPER_MODEL_SIZE`), CPU,
  `int8` compute type. Model auto-downloads from HuggingFace on first use and is cached
  at `~/.cache/huggingface`.
- **TTS**: `piper-tts`, voice `en_US-hfc_female-medium` (env var `PIPER_VOICE`, default
  set in `core/services/voice_service.py`). Voice models live in
  `data/piper_voices/*.onnx` + `.onnx.json`, downloaded via
  `python -m piper.download_voices <voice_name> --download-dir data/piper_voices`.
  Several other voices were downloaded for comparison and are still on disk if you want
  to switch: `en_US-lessac-medium` (old default), `en_US-amy-medium`, `en_US-joe-medium`,
  `en_US-ryan-medium`. Sample clips of each (all speaking the same test line) are in
  `static/voice_samples/`.
- **Endpoint**: `POST /api/v1/voice/query` in `core/routers/voice.py`. Accepts
  `UploadFile` field `audio` (any ffmpeg/PyAV-decodable format — the browser records
  `audio/webm`, works fine directly, no client-side transcoding). Returns JSON:
  `{transcript, answer_text, audio_base64}` (WAV, base64-encoded). Deliberately **not**
  raw binary + headers — JSON+base64 is simpler for both the browser and future ESP32
  firmware (no multipart parsing needed on the embedded side, no header-encoding issues
  with non-ASCII answer text).
- Both STT and TTS models are lazily loaded **once per process** as module-level
  singletons in `voice_service.py` (loading them is slow — a few seconds). The very
  first `/api/v1/voice/query` call after a server restart will be slower than
  subsequent ones for this reason.
- If a transcript comes back empty/too short (<3 chars), the endpoint returns a
  friendly "I didn't quite catch that, try again?" (language-aware,
  `voice_retry_prompt` in the language files) instead of erroring — still spoken via
  TTS.
- Voice deps are **optional**: `core/routers/voice.py` only imports `faster_whisper`/
  `piper` lazily inside the request-time dependency function, so the router always
  registers successfully; if the deps aren't installed, hitting the endpoint returns a
  clean `503` with the install command, rather than crashing the server.

## Web UI

Everything lives in one page now: `static/index.html`, served at `/ui`. Two tabs:
- **Text Chat** — the original upload/search UI, unchanged.
- **Voice Chat** — record button (`getUserMedia` + `MediaRecorder`), shows transcript +
  answer text (simulating the LCD), auto-plays the spoken response (simulating the
  speaker). This *was* a separate `static/voice_test.html` page but was merged into the
  main UI as a tab per request — that standalone file no longer exists.

There's also `core/templates/admin_dashboard.html` (`/admin`) with a "🌐 Language
Settings" section (dropdown, auto-populated from `config/languages/*.yaml`), and
`core/templates/document_management.html` (`/admin/documents/management`) for the
document filter/cleanup admin tools.

## Bugs fixed this session (context so they don't get reintroduced)

These are worth knowing about because several were subtle and could easily resurface if
similar code is touched again:

1. **numpy/Python 3.14 install failure**: `deployment/requirements/simple_requirements.txt`
   had `numpy<2.0.0`, which has no prebuilt wheels for Python 3.14 (only this machine's
   installed interpreter), forcing a from-source build that failed with no C compiler
   installed. Fixed by relaxing to `numpy<3.0.0`.
2. **`simple_api.py` was broken**: it called `from core.main import main`, but
   `core/main.py` never defined a `main()` function — only the FastAPI `app` object and
   a bare `if __name__ == "__main__": uvicorn.run(...)` block. Added a proper `main()`
   wrapper in `core/main.py`.
3. **CSRF tokens missing everywhere in the frontend**: `core/main.py`'s
   `csrf_middleware` requires an `X-CSRF-Token` header on all POST/PUT/DELETE to
   `/api/v1/*` (and `/admin/*`), but none of the JS in `static/index.html`,
   `admin_dashboard.html`, or `document_management.html` was sending it. Also, the
   middleware itself was `raise HTTPException(...)` from inside `@app.middleware("http")`
   (a `BaseHTTPMiddleware`), which Starlette turns into an ugly unhandled 500 instead of
   a clean 403 — changed to return a `JSONResponse` directly. All the affected JS now
   fetches a token from `/api/v1/csrf-token` first via a shared `getCsrfToken()` helper.
4. **Document upload literally didn't work**: `DocumentResponse` Pydantic model was
   missing an `obfuscated_id` field that the router tried to set on it (crashed every
   upload). Separately, `document_service.py` was inserting into the `chunks` and
   `embeddings` SQLite tables using column names (`text`, `embedding_data`,
   `dimensions`) that didn't match the actual schema (`text_content`,
   `embedding_vector`, `vector_dimension`) — and the `embeddings` insert was missing
   `document_id` entirely (a `NOT NULL` column). All fixed; the corresponding `SELECT`
   queries in `core/repositories/vector_repository.py` had the same column-name
   mismatches and were fixed too.
5. **The RAG system was answering from hardcoded fake content, always**:
   `simple_rag_service.py`'s `_generate_answer` had a "TEMPORARY FIX" block that
   completely discarded the real retrieved document context and substituted a
   hardcoded German paragraph about bio-waste disposal (leftover from this project's
   previous life as a Swiss municipal waste-sorting assistant) into every single prompt,
   regardless of what was uploaded or asked. This was the single biggest correctness bug
   in the project — removed entirely, replaced with the actual retrieved context.
6. **Double-templating producing mixed-language garbage answers**:
   `core/ollama_client.py`'s `generate_answer` tried to detect "is this already a
   complete prompt" by string-sniffing for German phrases like `"Frage:"`. Since
   `simple_rag_service.py`'s prompts are in English, this check always failed, so the
   client wrapped the already-complete English prompt in a *second*, German-language
   template. Replaced the sniffing with an explicit `is_complete_prompt: bool` parameter.
7. **Hardcoded municipal-domain content filters were silently dropping search results**:
   `_search_documents` in `simple_rag_service.py` excluded any chunk containing words
   like `"javascript"`, `"console.log"`, or the German phrase `"zusätzliche
   richtlinien"`, plus a hardcoded `document_id == 60` check — all leftover from the old
   use case, running on every query regardless of the admin-configurable filters.
   Removed. (Separately, `core/routers/document_manager.py`'s admin "problematic
   document" analyzer had its own default keyword list including bare words like
   `"function"` and `"software"` that flagged completely normal documents — fixed by
   adding `config/document_filters.yaml` with neutral/empty defaults.)
8. **Answers were getting cut off mid-sentence**: `ollama_client.py` had a hardcoded
   `min(max_tokens, 256)` and `min(temperature, 0.1)` baked into the Ollama request
   options (comment: "Ultra-aggressive... for speed"), silently overriding whatever the
   caller actually asked for. Removed the clamps; raised the actual budget in
   `simple_rag_service.py` to 600 tokens. Also added `_trim_to_complete_sentence()` as a
   defensive backstop in case a response is ever still truncated (trims back to the last
   full sentence, but only if that keeps at least half the answer).
9. **Default LLM model wasn't installed**: `config/llm_config.yaml` had
   `default_model: tinyllama`, but only `mistral` and `llama3.2:1b` were actually pulled
   in Ollama, meaning every query was silently running with no usable model. Changed
   default to `mistral` (confirmed installed).
10. **Voice audio wouldn't play in the browser — two separate CSP/header issues**:
    (a) `core/main.py`'s `Permissions-Policy` header explicitly set `microphone=()`,
    which blocks `getUserMedia` outright regardless of frontend code — changed to
    `microphone=(self)`. (b) The `Content-Security-Policy` header had no `media-src`
    directive, so it fell back to `default-src 'self'`, which blocks both `data:` and
    `blob:` URLs for `<audio>` — this caused a **silent** failure (no thrown JS
    exception, just "0:00 duration, won't play") until checking the browser console
    revealed the actual CSP violation. Added `media-src 'self' data: blob:;`.
11. **Admin dashboard checked model availability 17× per page load**: the `/admin`
    dashboard and `/admin/models` endpoints created a fresh `OllamaClient` (with its own
    noisy logging) and made a separate network round-trip **per model in
    `llm_config.yaml`** (17 models) just to render the page. Fixed to fetch the
    installed-models list once and compare locally.

## Known rough edges / things worth revisiting

- **Spoken answers can be long** (a 60+ second answer isn't unusual for a full,
  friendly explanation) — fine for testing, but worth tuning down for a real kid's
  attention span on embedded hardware. Would mean a separate (smaller) `max_tokens` for
  the voice path specifically.
- **First voice request after a server restart is slow** (Whisper + Piper model
  loading, a few seconds) — acceptable for now, but worth pre-warming on startup if
  latency matters for the real device.
- All the work in this session is **uncommitted** — `git status` shows a long list of
  modified/new files, nothing has been committed yet.
- The old `SIMPLE_RAG_README.md`, `README.md`, and `CLAUDE.md` at the repo root still
  describe the *original* generic document-QA project (zero-hallucination, "AI answers
  only", etc.) and haven't been updated to reflect the STEM-tutor pivot or the voice
  pipeline. Worth updating if this project is going to be shared/open-sourced as-is.
- `core/services/query_service.py` appears to be dead/legacy code (a different, more
  complex answer-generation path with German zero-hallucination prompts, not wired to
  any active router — `core/routers/query.py` uses `SimpleRAGService` exclusively).
  Untouched so far; worth confirming it's actually unused before deleting.

## How to run everything

```bash
# Start the server (Ollama must already be running with `mistral` pulled)
python simple_api.py
# → http://127.0.0.1:8001/ui        (main UI: Text Chat + Voice Chat tabs)
# → http://127.0.0.1:8001/admin     (model management, language settings)
# → http://127.0.0.1:8001/admin/documents/management  (document filters/cleanup)
```

Voice dependencies are optional and separate from the core install:
```bash
pip install -r deployment/requirements/voice_requirements.txt
python -m piper.download_voices en_US-hfc_female-medium --download-dir data/piper_voices
```

Currently uploaded documents (for context — these are what the tutor can currently
ground answers in): science experiment books, a math history book, math games for kids,
an engineering/technology/science Wikipedia-derived set, and a "STEM Child Tutor Guide"
PDF — 9 documents total, all under `data/storage/`.

## What to upload/paste to a new Claude session

If you're starting a fresh Claude conversation (not Claude Code with repo access):

1. **This file** (`PROJECT_HANDOFF.md`) — gives full context without needing anything else read first.
2. If you want it to actually write code, it needs repo access (Claude Code CLI/IDE
   extension pointed at this folder), not just this file — this doc explains *what
   exists and why*, but Claude will still need to read the actual current file contents
   before editing them.
3. If you're stuck using a chat interface without file system access and need to discuss
   a specific piece, the most relevant individual files to paste alongside this doc are
   usually: `core/services/simple_rag_service.py` (the RAG/tutor logic),
   `core/routers/voice.py` + `core/services/voice_service.py` (voice pipeline), and
   `static/index.html` (the frontend) — depending on what you're working on next.
4. Mention explicitly that the next phase is **ESP32 firmware** (recording mic audio,
   POSTing it to `/api/v1/voice/query` over local WiFi, playing back the returned
   base64 WAV through a speaker, showing `answer_text` on an LCD) since that's not
   started yet and needs a fresh planning conversation of its own — hardware specifics
   (mic model, speaker/amp, LCD driver) aren't decided yet either.
