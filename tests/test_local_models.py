"""With its models downloaded, the server must not depend on reaching huggingface.co."""
import os

import pytest

from core import local_models


def download(cache, repo):
    (cache / f"models--{repo.replace('/', '--')}" / "snapshots" / "abc123").mkdir(parents=True)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    monkeypatch.delenv("WHISPER_MODEL_SIZE", raising=False)
    # setenv first so monkeypatch restores the real value when the code under test sets it
    monkeypatch.setenv("HF_HUB_OFFLINE", "placeholder")
    monkeypatch.delenv("HF_HUB_OFFLINE")
    return tmp_path


def test_goes_offline_once_every_model_is_downloaded(cache):
    download(cache, local_models.EMBEDDING_REPO)
    download(cache, "Systran/faster-whisper-base")
    assert local_models.use_downloaded_models_only() is True
    assert os.environ["HF_HUB_OFFLINE"] == "1"


@pytest.mark.parametrize("present", [[], [local_models.EMBEDDING_REPO], ["Systran/faster-whisper-base"]])
def test_stays_online_while_a_model_is_missing(cache, present):
    for repo in present:
        download(cache, repo)
    assert local_models.use_downloaded_models_only() is False
    assert "HF_HUB_OFFLINE" not in os.environ


def test_checks_the_whisper_size_in_use(cache, monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "small")
    download(cache, local_models.EMBEDDING_REPO)
    download(cache, "Systran/faster-whisper-base")
    assert local_models.use_downloaded_models_only() is False


def test_respects_an_explicit_setting(cache, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    download(cache, local_models.EMBEDDING_REPO)
    download(cache, "Systran/faster-whisper-base")
    assert local_models.use_downloaded_models_only() is False
    assert os.environ["HF_HUB_OFFLINE"] == "0"
