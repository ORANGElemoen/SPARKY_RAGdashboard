# Contributing

This is a university course project (BEng Computer Electronic, NWU) built by a
single student, so there's no formal external-contribution process - but if
you're reading this because you forked it, found a bug, or want to build on
it, here's what's useful to know.

## Project shape

- `core/` is the actual running FastAPI backend - read
  [CLAUDE.md](CLAUDE.md) first, it documents the current architecture,
  conventions, and known gotchas (CSRF, security headers, device auth).
- `docs/` holds project documentation and the Sparky hardware materials
  (shopping list, wiring diagram, build sequence, demo scripts).
- `scripts/` holds one-off generator/helper scripts (PDF generators, CAD
  inspection tools, firmware helpers) - not part of the running app, run
  manually when their output needs regenerating.

## Setup

See the [README](README.md) Quick Start section. In short:
`pip install -r requirements.txt`, have Ollama running with a model pulled,
then `python simple_api.py`.

## Before submitting a change

- Restart the server after editing anything under `core/` -
  `uvicorn.run(..., reload=False)` is deliberate (see CLAUDE.md), so changes
  don't hot-reload.
- Frontend files (`static/*.html`, `core/templates/*.html`) are read fresh on
  every request - just refresh the browser, no restart needed.
- If you add a new state-changing frontend request (POST/PUT/DELETE), it must
  fetch a CSRF token first (`GET /api/v1/csrf-token`) and send it as
  `X-CSRF-Token`, or it will 403.
- Multi-language strings belong in `config/languages/*.yaml`, never hardcoded
  in Python - see `load_language_strings()` in `simple_rag_service.py`.
- Run the test suite (`pytest`) before committing, if you have Ollama and the
  optional voice dependencies installed.

## Reporting issues

Open a GitHub issue on this repo, or see [SECURITY.md](SECURITY.md) for
anything security-sensitive.
