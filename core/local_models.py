"""
Stops the speech and search models asking huggingface.co for updates once they're downloaded.

Sparky has to work with no internet. Without this, every load of an already-downloaded model
first retries huggingface.co for over 20 s, which made a voice question time out at 65 s.

Must run before anything imports huggingface_hub, which reads the setting once on import. Standard
library only, for that reason. A machine still missing a model stays online so it can download it.
"""
import os
from pathlib import Path

EMBEDDING_REPO = "sentence-transformers/all-MiniLM-L6-v2"


def _cache_dir() -> Path:
    if os.getenv("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = os.getenv("HF_HOME")
    return Path(home) / "hub" if home else Path.home() / ".cache" / "huggingface" / "hub"


def _is_downloaded(repo: str) -> bool:
    snapshots = _cache_dir() / f"models--{repo.replace('/', '--')}" / "snapshots"
    return snapshots.is_dir() and any(snapshots.iterdir())


def use_downloaded_models_only() -> bool:
    """Go offline for model loading if every model is already here. Returns True if it did."""
    if "HF_HUB_OFFLINE" in os.environ:           # someone chose: respect it
        return False
    whisper_repo = f"Systran/faster-whisper-{os.getenv('WHISPER_MODEL_SIZE', 'base')}"
    if not (_is_downloaded(EMBEDDING_REPO) and _is_downloaded(whisper_repo)):
        return False
    os.environ["HF_HUB_OFFLINE"] = "1"
    return True
