"""Which model answers Sparky's questions: the one chosen in the admin dashboard.

Local Ollama models are the default. An entry with `provider: gemini` in
config/llm_config.yaml answers with Google Gemini online, and its `local_model`
answers instead whenever Gemini can't (see core/gemini_client.py).
"""

import logging
from pathlib import Path

import yaml

from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)

LLM_CONFIG = Path("config/llm_config.yaml")


def active_model_entry() -> dict:
    try:
        config = yaml.safe_load(LLM_CONFIG.read_text(encoding="utf-8")) or {}
        return (config.get("models") or {}).get(config.get("default_model"), {}) or {}
    except Exception as e:
        logger.warning(f"Could not read {LLM_CONFIG}: {e}")
        return {}


def make_llm_client(timeout: int = 60):
    entry = active_model_entry()
    if entry.get("provider") == "gemini":
        from .gemini_client import GeminiClient

        # OllamaClient() picks the entry's local_model (see _load_model_from_config)
        return GeminiClient(entry["name"], timeout=timeout, fallback=OllamaClient(timeout=timeout))
    return OllamaClient(timeout=timeout)
