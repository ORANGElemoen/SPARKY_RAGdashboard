"""
Google Gemini (online) as an optional alternative to the local Ollama model.

For comparison testing only: Sparky is designed to run fully offline (see CLAUDE.md), so the
local model stays the default. Switch to the "gemini" entry in the admin dashboard to try it.

Only text is sent to Google: the prompt, which holds the child's transcribed question, the
conversation so far and any matching sheet. Speech recognition and the voice stay on this
computer. The API key is read from GEMINI_API_KEY (environment or the gitignored .env file).

GeminiClient has the same methods SimpleRAGService uses on OllamaClient (generate_answer,
generate_stream, model), so Sparky's prompts, memory and safety rules apply unchanged. If
Gemini can't answer (no internet, bad key, quota), the local model answers instead.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Iterator, Optional

import requests

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
# Gemini's thinking counts towards the output limit, so a 4-token limit (the message type
# check) could leave no room for the answer. Limits below this are raised to it; the answer
# itself is still as short as the prompt asks, so this costs nothing extra.
MIN_OUTPUT_TOKENS = 1024
# Sparky's quick checks (message type, follow-up) ask for a word or two. The local model
# answers those in about 0.2 s; over the internet each would add a second or more.
QUICK_CHECK_TOKENS = 16
# How long to wait for Google before the local model answers instead. Busy Gemini models
# took up to 28 s just to say "high demand" (2026-11-10).
TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT", "8"))
ENV_FILE = Path(".env")


def gemini_api_key() -> str:
    """The key from the environment, or else from .env (read each time, so no restart is needed)."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key and ENV_FILE.exists():
        try:
            from dotenv import dotenv_values

            key = dotenv_values(ENV_FILE).get("GEMINI_API_KEY") or ""
        except Exception as e:
            logger.warning(f"Could not read {ENV_FILE}: {e}")
    return key.strip()


class GeminiError(Exception):
    pass


class GeminiClient:
    # Models that rejected their thinking setting, so it isn't sent to them again
    _no_thinking: set = set()

    def __init__(self, model: str, timeout: float = TIMEOUT_S, fallback=None, thinking: Optional[dict] = None):
        self.model = model
        self.timeout = timeout
        self.fallback = fallback  # an OllamaClient: answers whenever Gemini can't, and the quick checks
        # Gemini 3 models take {"thinkingLevel": "low"}; 2.5 models {"thinkingBudget": 0} (off)
        self.thinking = thinking

    # ------------------------------------------------------------------ helpers
    def is_available(self) -> bool:
        return bool(gemini_api_key())

    def _body(self, prompt: str, max_tokens: int, temperature: float) -> dict:
        generation = {"temperature": temperature, "maxOutputTokens": max(max_tokens, MIN_OUTPUT_TOKENS)}
        if self.thinking and self.model not in GeminiClient._no_thinking:
            generation["thinkingConfig"] = dict(self.thinking)
        return {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": generation}

    def _post(self, method: str, prompt: str, max_tokens: int, temperature: float, stream: bool = False):
        key = gemini_api_key()
        if not key:
            raise GeminiError("No GEMINI_API_KEY set (add it to .env)")
        url = API_URL.format(model=self.model, method=method) + ("?alt=sse" if stream else "")
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        for attempt in range(2):
            response = requests.post(url, headers=headers, json=self._body(prompt, max_tokens, temperature),
                                     stream=stream, timeout=(10, self.timeout))
            if response.status_code == 400 and attempt == 0 and self.thinking \
                    and self.model not in GeminiClient._no_thinking and "thinking" in response.text.lower():
                logger.info(f"{self.model} rejected the thinking setting; sending requests without it")
                GeminiClient._no_thinking.add(self.model)
                continue
            if response.status_code != 200:
                detail = response.text[:300].replace(key, "***")
                response.close()
                raise GeminiError(f"Gemini said {response.status_code}: {detail}")
            return response
        raise GeminiError("Gemini rejected the request")

    @staticmethod
    def _text(data: dict) -> str:
        """The answer text in one response chunk, without any thinking parts."""
        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            if block:
                logger.warning(f"Gemini blocked the prompt: {block}")
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    @staticmethod
    def _log_usage(data: dict, started: float) -> None:
        usage = data.get("usageMetadata") or {}
        if usage:
            logger.info(
                f"Gemini answered in {time.time() - started:.1f}s: {usage.get('promptTokenCount', '?')} prompt "
                f"tokens, {usage.get('candidatesTokenCount', '?')} answer tokens, "
                f"{usage.get('thoughtsTokenCount', 0)} thinking tokens"
            )

    # ------------------------------------------------------------------ the interface Sparky uses
    def generate_answer(
        self,
        query: str,
        context: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        max_retries: int = 1,
        is_complete_prompt: bool = False,
    ) -> Optional[str]:
        if max_tokens <= QUICK_CHECK_TOKENS and self.fallback is not None:
            return self.fallback.generate_answer(query=query, context=context, max_tokens=max_tokens,
                                                 temperature=temperature, max_retries=max_retries,
                                                 is_complete_prompt=is_complete_prompt)
        prompt = query if is_complete_prompt else f"{context}\n\n{query}".strip()
        started = time.time()
        try:
            response = self._post("generateContent", prompt, max_tokens, temperature)
            data = response.json()
            self._log_usage(data, started)
            text = self._text(data).strip()
            if text:
                return text
            logger.warning("Gemini returned no text")
        except Exception as e:
            logger.warning(f"Gemini failed ({e}); the local model answers instead")
        if self.fallback is not None:
            return self.fallback.generate_answer(query=query, context=context, max_tokens=max_tokens,
                                                 temperature=temperature, max_retries=max_retries,
                                                 is_complete_prompt=is_complete_prompt)
        return None

    def generate_stream(self, prompt: str, max_tokens: int = 600, temperature: float = 0.4, stop=None) -> Iterator[str]:
        """The answer piece by piece. `stop` (a threading.Event) ends it early."""
        started, said_anything = time.time(), False
        try:
            with self._post("streamGenerateContent", prompt, max_tokens, temperature, stream=True) as response:
                last = {}
                for line in response.iter_lines(decode_unicode=True):
                    if stop is not None and stop.is_set():
                        return
                    if not line or not line.startswith("data:"):
                        continue
                    last = json.loads(line[5:].strip())
                    text = self._text(last)
                    if text:
                        said_anything = True
                        yield text
                self._log_usage(last, started)
        except Exception as e:
            if said_anything or self.fallback is None:
                raise
            logger.warning(f"Gemini failed ({e}); the local model answers instead")
        if not said_anything and self.fallback is not None:
            if stop is None or not stop.is_set():
                yield from self.fallback.generate_stream(prompt, max_tokens=max_tokens,
                                                         temperature=temperature, stop=stop)

    def list_models(self) -> list:
        """The model ids this key can use for answers (to check the configured name)."""
        key = gemini_api_key()
        if not key:
            return []
        response = requests.get(API_URL.split("/{model}")[0], headers={"x-goog-api-key": key},
                                params={"pageSize": 1000}, timeout=15)
        response.raise_for_status()
        return [m["name"].split("/", 1)[-1] for m in response.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]
