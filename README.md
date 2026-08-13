# STEM Voice Tutor

A locally-hosted, voice-driven STEM tutor built for children in low-connectivity
areas (developed with Sub-Saharan Africa deployments in mind). A child asks a
question by voice; the system transcribes it, answers it in a fun, encouraging
way grounded in your uploaded STEM textbooks (or its own general knowledge when
nothing relevant is uploaded), and speaks the answer back — all running fully
offline on local hardware, with no cloud APIs and no per-query cost.

It started as a generic "upload documents, ask questions" RAG system and has
since been repurposed specifically for this use case. The text-based document
Q&A interface still works and is still useful on its own, but the voice pipeline
is now the primary feature.

![Status](https://img.shields.io/badge/Status-Active%20Development-yellow)
![Python](https://img.shields.io/badge/Python-3.8%2B-orange)
![License](https://img.shields.io/badge/License-MIT-green)

## Table of Contents

- [How it works](#how-it-works)
- [Features](#features)
- [Quick Start](#quick-start)
- [Voice Pipeline Setup](#voice-pipeline-setup)
- [Admin Interface](#admin-interface)
- [API Usage](#api-usage)
- [Project Structure](#project-structure)
- [What's next](#whats-next)
- [License](#license)

## How it works

```
Child speaks a question
        │
        ▼
Speech-to-text (faster-whisper, local, offline)
        │
        ▼
RAG tutor: answers using uploaded documents when relevant,
falls back to general knowledge otherwise (SimpleRAGService)
        │
        ▼
Text-to-speech (Piper, local, offline)
        │
        ▼
Spoken answer + on-screen/LCD text, with source citations
shown (not read aloud) when the answer came from a document
```

Today, this is testable end-to-end from a browser tab (using your computer's
own microphone/speakers as a stand-in). The long-term target is a physical
device — an ESP32 microcontroller with a mic, speaker, and LCD screen — that
calls the exact same API over the local network; that hardware/firmware isn't
built yet.

## Features

### Tutor behavior
- **Hybrid answering**: grounds answers in your uploaded documents when
  relevant, and answers from general knowledge in the same friendly tone when
  nothing relevant has been uploaded — it never just refuses to answer a child.
- **Kid-friendly persona**: prompts are written for a friendly, encouraging
  STEM tutor explaining science, technology, engineering, math, biology, and
  electricity with simple language and everyday examples.
- **Source citations** are shown in the on-screen answer when documents were
  used, but never read aloud in the spoken response.
- **Multi-language, extensible**: prompt templates and response strings live
  in `config/languages/*.yaml` (currently English and German). Adding a new
  language is adding one file — no code changes — and it's selectable live
  from the admin Settings page.

### Voice pipeline
- **Speech-to-text**: `faster-whisper`, fully local/offline, CPU-friendly.
- **Text-to-speech**: `piper-tts`, fully local/offline, small ONNX voice
  models with several English voices to choose from.
- **Single endpoint** (`POST /api/v1/voice/query`) takes an audio recording
  and returns transcript + answer text + spoken answer (base64 WAV) — the
  same contract the future ESP32 firmware will call.

### Document handling
- Upload PDF, DOCX, TXT, MD, or CSV files; automatic chunking and embedding
  via sentence-transformers, stored in SQLite with FAISS/numpy-based vector
  search.
- Admin document manager with configurable content filters (nothing is
  auto-flagged by default — you define your own keyword rules if you want
  any).

### Admin interface
- Model switching between installed Ollama models, with live availability
  checks.
- Language selection (see above).
- Document management: view, analyze, filter, and clean up uploaded
  documents.
- Database configuration (SQLite by default; PostgreSQL/MySQL supported).

## Quick Start

### Prerequisites
- Python 3.10+ (developed against 3.14)
- [Ollama](https://ollama.com/download), with at least one model pulled
  (e.g. `ollama pull mistral`)

### 1. Install

```bash
git clone <this-repository-url>
cd open-source-rag-system

pip install -r requirements.txt
```

### 2. Run

```bash
python simple_api.py
# → http://127.0.0.1:8001/ui     (main UI: Text Chat + Voice Chat tabs)
# → http://127.0.0.1:8001/admin  (model management, language settings)
```

### 3. Upload documents and ask questions

Open the UI, upload a few PDFs (textbooks, guides, whatever you want the
tutor grounded in), then either type a question in the **Text Chat** tab or
hold the record button in the **Voice Chat** tab and ask out loud.

## Voice Pipeline Setup

Voice support is an optional layer on top of the core system — install it
separately:

```bash
pip install -r deployment/requirements/voice_requirements.txt

# Download a text-to-speech voice (one-time; several are available, see
# https://github.com/rhasspy/piper/blob/master/VOICES.md)
python -m piper.download_voices en_US-hfc_female-medium --download-dir data/piper_voices
```

The speech-to-text model (`faster-whisper`, size configurable via the
`WHISPER_MODEL_SIZE` env var, default `base`) downloads automatically on
first use. The TTS voice is configurable via the `PIPER_VOICE` env var.

Both models are loaded once per server process and kept in memory — the
first voice request after a restart will be slower than subsequent ones
while they load.

## Admin Interface

Visit `/admin` for:
- **Model management** — switch between installed Ollama models, install new
  ones, see live availability.
- **Language settings** — pick the active response language; add new ones by
  dropping a file in `config/languages/`.

Visit `/admin/documents/management` for:
- **Content analysis** — categorize and flag documents using your own
  configurable keyword rules (`config/document_filters.yaml`).
- **Cleanup tools** — remove documents matching your filter criteria, with a
  dry-run mode.

## API Usage

```bash
# Ask a text question
curl -X POST "http://localhost:8001/api/v1/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "What is electricity?"}'

# Ask a voice question (send an audio file, get transcript + text + spoken answer back)
curl -X POST "http://localhost:8001/api/v1/voice/query" \
  -F "audio=@question.webm"

# Upload a document
curl -X POST "http://localhost:8001/api/v1/documents" \
  -F "file=@textbook.pdf"

# Health check
curl "http://localhost:8001/health"
```

Note: state-changing requests (POST/PUT/DELETE) require a CSRF token —
fetch one from `GET /api/v1/csrf-token` and send it as the `X-CSRF-Token`
header. The web UI handles this automatically.

## Project Structure

```
open-source-rag-system/
├── core/
│   ├── main.py                    # FastAPI app, security headers, router registration
│   ├── routers/
│   │   ├── query.py               # POST /api/v1/query (text)
│   │   ├── voice.py                # POST /api/v1/voice/query (STT -> RAG -> TTS)
│   │   ├── documents.py           # Upload, list, download, chunk retrieval
│   │   └── admin.py               # Model/language/database admin endpoints
│   ├── services/
│   │   ├── simple_rag_service.py  # Core tutor logic: search, prompt, answer, language
│   │   ├── voice_service.py       # faster-whisper (STT) + piper (TTS)
│   │   └── document_service.py    # Upload validation, chunking, embeddings
│   ├── ollama_client.py           # Ollama integration
│   └── templates/                 # Admin dashboard, document management HTML
├── static/
│   ├── index.html                 # Main UI (Text Chat + Voice Chat tabs)
│   └── voice_samples/             # Sample TTS clips for voice comparison
├── config/
│   ├── llm_config.yaml            # Ollama model catalog + default model
│   ├── language_config.yaml       # Active response language
│   ├── languages/                 # Prompt templates + strings, one file per language
│   └── document_filters.yaml      # Admin document-filter keyword config
├── data/
│   ├── storage/                   # Uploaded documents (gitignored)
│   ├── piper_voices/              # Downloaded TTS voice models (gitignored)
│   └── rag_database.db            # SQLite database (gitignored)
├── deployment/requirements/
│   ├── simple_requirements.txt    # Core dependencies
│   └── voice_requirements.txt     # Optional: faster-whisper, piper-tts
├── PROJECT_HANDOFF.md             # Detailed project state / handoff notes
└── simple_api.py                  # Entry point
```

## What's next

The next phase is the physical device: ESP32 firmware to record microphone
audio, POST it to `/api/v1/voice/query` over local WiFi, play the returned
audio through a speaker, and show the answer text on an LCD. Hardware
specifics (mic, speaker/amp, LCD driver) aren't finalized yet. See
[PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) for full details on the current
state, recent fixes, and known rough edges.

## License

MIT License - see [LICENSE](./LICENSE) for details.
