"""Prompt-side tutor behaviour: canned-refusal softening, grade sentence, language files."""

from pathlib import Path

import pytest
import yaml

import core.services.simple_rag_service as rag
from core.services.simple_rag_service import DEFAULT_LANGUAGE_STRINGS as EN

LANGS = sorted(Path("config/languages").glob("*.yaml"))


@pytest.mark.parametrize("answer", [
    "I cannot provide information on how to start a fire with petrol. Can I help you with something else?",
    "I can't provide instructions on how to start a fire with petrol.",
    "  I can't help with that request.",
])
def test_canned_refusal_becomes_safety_redirect(answer):
    assert rag._soften_refusal(answer, EN) == EN["safety_redirect"]


@pytest.mark.parametrize("answer", [
    "I can't help but get excited about volcanoes! They erupt when pressure builds up.",
    "I can't wait to tell you about rainbows!",
    "Plants make food. I cannot provide a better example than a baobab tree!",  # not at the start
])
def test_real_answers_are_left_alone(answer):
    assert rag._soften_refusal(answer, EN) == answer


def test_english_refusal_caught_in_other_languages():
    de = yaml.safe_load(open("config/languages/de.yaml", encoding="utf-8"))
    assert rag._soften_refusal("I cannot provide information on that.", de) == de["safety_redirect"]
    assert rag._soften_refusal("Ich kann dir keine Anleitung dazu geben.", de) == de["safety_redirect"]
    assert rag._soften_refusal("Ich kann es kaum erwarten, dir das zu zeigen!", de).startswith("Ich kann es")


def test_grade_instruction(tmp_path, monkeypatch):
    cfg = tmp_path / "learner_config.yaml"
    monkeypatch.setattr(rag, "LEARNER_CONFIG_PATH", cfg)

    assert rag.grade_instruction(EN) == ""  # no config file
    for grade, age in [("R", 5), ("2", 8), ("7", 13)]:
        cfg.write_text(f"grade: '{grade}'\n")
        line = rag.grade_instruction(EN)
        assert f"Grade {grade}" in line and f"about {age} years old" in line
    cfg.write_text("grade: banana\n")  # hand-edited nonsense must not break answering
    assert rag.grade_instruction(EN) == ""


@pytest.mark.parametrize("path", LANGS, ids=lambda p: p.stem)
def test_language_file_is_complete(path):
    s = yaml.safe_load(open(path, encoding="utf-8"))
    for key in ("prompt_template", "general_prompt_template"):
        assert "Sparky" in s[key]
        s[key].format(query="q", context="c", conversation_history="", grade_instruction="G")
    s["grade_instruction"].format(grade="3", age=9)
    assert s["safety_redirect"] and s["refusal_pattern"] and s["speech_fractions"]["1/2"]


def test_history_keeps_sparkys_closing_question():
    answer = "Spiders are amazing! " * 40 + "Can you guess how many legs a spider has?"
    block = rag.SimpleRAGService._build_conversation_history_block(
        None, [{"question_text": "Tell me about spiders", "answer_text": answer}], EN)
    assert "Can you guess how many legs a spider has?" in block
    assert "Spiders are amazing!" in block  # the start (topic) is kept too
    assert len(block) < 900


def test_short_replies_to_sparkys_questions_are_valid():
    svc = rag.SimpleRAGService.__new__(rag.SimpleRAGService)
    svc.config = type("C", (), {"max_query_length": 1000})()
    for reply in ["No", "8", "Ja"]:
        assert svc._is_valid_query(reply)
    assert not svc._is_valid_query("   ")
