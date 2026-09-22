# Security Policy

## Reporting a vulnerability

This is a university course project, not a production service with a
dedicated security team - but if you find a real vulnerability, please open
it as a private [GitHub Security Advisory](../../security/advisories/new) on
this repo rather than a public issue, so it can be looked at before details
are public.

## Scope and design context

- **Fully local/offline by design**: the LLM (Ollama), speech-to-text
  (faster-whisper), text-to-speech (Piper), and all storage (SQLite) run on
  the same machine. No user question or answer is sent to a third-party
  cloud API.
- **Browser clients** are protected by CSRF tokens on every state-changing
  request (`X-CSRF-Token`, see `csrf_middleware` in `core/main.py`) and by the
  security headers set in `core/main.py` (CSP, Permissions-Policy, etc.).
- **Physical devices** (ESP32 hardware) authenticate with a per-device API
  key instead of a CSRF token, since they can't do a browser session
  handshake. Only a SHA-256 hash of each key is ever stored; the plaintext is
  shown once at registration and can't be recovered afterward. A device can
  be individually revoked (disables its key) or, once revoked, permanently
  deleted.
- **Uploaded documents** go through a configurable content filter
  (`config/document_filters.yaml`) that flags likely prompt-injection
  attempts, corrupted encoding, and other red flags for admin review - it
  does not silently execute or trust document content.

## Known limitations

- There is no user-facing authentication on the admin dashboard itself - it's
  designed for a single trusted operator on a local/trusted network, not
  multi-tenant or internet-facing deployment. Don't expose `/admin` directly
  to the public internet without adding your own auth layer in front of it.
- Rate limiting is not currently enforced on any endpoint.

If you're deploying this beyond a local trusted network, review both points
above first.
