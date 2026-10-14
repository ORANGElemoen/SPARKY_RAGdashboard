"""clean_for_speech: chat-formatted LLM text -> text Piper can read aloud."""

from core.services.simple_rag_service import DEFAULT_LANGUAGE_STRINGS
from core.services.voice_service import clean_for_speech, split_sentences

EN = DEFAULT_LANGUAGE_STRINGS


def test_real_slime_answer():
    text = (
        "Hi there, friend! *beep boop* I'm Sparky! **Slime Recipe** "
        "2. Add 2 tablespoons of PVA glue (that's a special kind of glue that makes slime). "
        "4. Add a few drops of food color (if you want your slime to be colorful!). "
        "5. Add 1/2 teaspoon of special powder called borax (don't worry, it's safe!). 😄"
    )
    out = clean_for_speech(text, EN)
    for bad in ["*", "(", ")", "/", "😄", "beep boop"]:
        assert bad not in out, (bad, out)
    assert "Slime Recipe" in out
    assert "PVA glue, that's a special kind of glue that makes slime." in out
    assert "to be colorful!" in out and "colorful!," not in out and "colorful!." not in out
    assert "Add one half teaspoon" in out


def test_fractions_and_slashes():
    assert clean_for_speech("Eat 3/4 of it and 5/8 of that.", EN) == (
        "Eat three quarters of it and 5 over 8 of that."
    )
    assert clean_for_speech("Born on 12/10/2026, and/or later.", EN) == (
        "Born on 12/10/2026, and or later."
    )


def test_language_file_words_are_used():
    de = {"speech_fractions": {"1/2": "ein halb"}, "speech_fraction_template": "{numerator} durch {denominator}"}
    assert clean_for_speech("1/2 und 2/5", de) == "ein halb und 2 durch 5"


def test_plain_text_unchanged():
    text = "Plants make their own food using sunlight, water, and air."
    assert clean_for_speech(text, EN) == text


def test_split_sentences_cleans_first():
    assert split_sentences("Wow! *wink* It's (really) cool.") == ["Wow!", "It's, really, cool."]
