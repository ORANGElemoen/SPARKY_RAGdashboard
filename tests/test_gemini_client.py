"""The optional online Gemini model: same interface as the local one, and the local model
answers whenever Gemini can't."""
import json
import threading

import pytest
import yaml

from core import gemini_client as gc


class FakeResponse:
    def __init__(self, status=200, data=None, lines=None, text=""):
        self.status_code, self._data, self._lines, self.text = status, data, lines or [], text

    def json(self):
        return self._data

    def iter_lines(self, decode_unicode=False):
        yield from self._lines

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def chunk(text, thought=False):
    part = {"text": text, **({"thought": True} if thought else {})}
    return "data: " + json.dumps({"candidates": [{"content": {"parts": [part]}}]})


class LocalModel:
    model = "qwen3.5:4b"

    def generate_answer(self, **kwargs):
        return "local answer"

    def generate_stream(self, prompt, max_tokens=600, temperature=0.4, stop=None):
        yield "local "
        yield "stream"


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gc.GeminiClient, "_send_thinking", True)


def test_an_answer_comes_back_without_the_thinking(key, monkeypatch):
    sent = {}

    def post(url, headers, json, stream, timeout):
        sent.update(url=url, headers=headers, body=json)
        return FakeResponse(data={"candidates": [{"content": {"parts": [
            {"text": "I should be friendly.", "thought": True}, {"text": "The sky is blue!"}]}}]})
    monkeypatch.setattr(gc.requests, "post", post)
    answer = gc.GeminiClient("gemini-3.8-flash").generate_answer("Why?", "", max_tokens=4, is_complete_prompt=True)
    assert answer == "The sky is blue!"
    assert "gemini-3.8-flash:generateContent" in sent["url"]
    assert sent["headers"]["x-goog-api-key"] == "test-key" and "test-key" not in sent["url"]
    assert sent["body"]["generationConfig"]["maxOutputTokens"] >= gc.MIN_OUTPUT_TOKENS


def test_a_stream_yields_text_pieces(key, monkeypatch):
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: FakeResponse(
        lines=[chunk("hmm", thought=True), "", chunk("The sky "), chunk("is blue.")]))
    assert list(gc.GeminiClient("g").generate_stream("Why?")) == ["The sky ", "is blue."]


def test_a_stream_stops_when_told(key, monkeypatch):
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: FakeResponse(lines=[chunk("one "), chunk("two ")]))
    stop = threading.Event()
    got = []
    for piece in gc.GeminiClient("g").generate_stream("Why?", stop=stop):
        got.append(piece)
        stop.set()
    assert got == ["one "]


def test_the_local_model_answers_when_gemini_fails(key, monkeypatch):
    monkeypatch.setattr(gc.requests, "post", lambda *a, **k: FakeResponse(status=429, text="quota"))
    client = gc.GeminiClient("g", fallback=LocalModel())
    assert client.generate_answer("Why?", "", is_complete_prompt=True) == "local answer"
    assert list(client.generate_stream("Why?")) == ["local ", "stream"]


def test_without_a_key_the_local_model_answers(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(gc, "ENV_FILE", tmp_path / ".env")  # no .env either
    client = gc.GeminiClient("g", fallback=LocalModel())
    assert not client.is_available()
    assert client.generate_answer("Why?", "", is_complete_prompt=True) == "local answer"


def test_the_key_is_read_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setattr(gc, "ENV_FILE", env)
    assert gc.gemini_api_key() == "from-file"


def test_a_rejected_thinking_setting_is_dropped(key, monkeypatch):
    bodies = []

    def post(url, headers, json, stream, timeout):
        bodies.append(json)
        if "thinkingConfig" in json["generationConfig"]:
            return FakeResponse(status=400, text="Unknown field thinkingConfig.thinkingLevel")
        return FakeResponse(data={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    monkeypatch.setattr(gc.requests, "post", post)
    assert gc.GeminiClient("g").generate_answer("Why?", "", is_complete_prompt=True) == "ok"
    assert len(bodies) == 2 and "thinkingConfig" not in bodies[1]["generationConfig"]


def test_the_local_client_never_loads_gemini_into_ollama(tmp_path, monkeypatch):
    from core import ollama_client

    cfg = tmp_path / "llm_config.yaml"
    cfg.write_text(yaml.dump({"default_model": "gemini", "models": {
        "gemini": {"provider": "gemini", "name": "gemini-3.8-flash", "local_model": "qwen3.5"},
        "qwen3.5": {"name": "qwen3.5:4b"}}}), encoding="utf-8")
    monkeypatch.setattr(ollama_client, "CONFIG_AVAILABLE", False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "llm_config.yaml").write_text(cfg.read_text(encoding="utf-8"), encoding="utf-8")
    client = ollama_client.OllamaClient.__new__(ollama_client.OllamaClient)
    assert client._load_model_from_config() == "qwen3.5:4b"
