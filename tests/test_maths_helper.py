"""Maths helper: exact sums from children's wording, and checking their answer."""

from fractions import Fraction

import pytest
import yaml

from core.services.maths_helper import find_sum, maths_note

EN = yaml.safe_load(open("config/languages/en.yaml", encoding="utf-8"))
WORDS = EN["maths_words"]


@pytest.mark.parametrize("text, value", [
    ("What is one half plus one quarter?", Fraction(3, 4)),
    ("what's a half plus a quarter", Fraction(3, 4)),
    ("What is 3 x 4?", 12),
    ("what is twenty-five divided by five", 5),
    ("one and a half take away three quarters", Fraction(3, 4)),
    ("What is 12 + 8 * 2?", 28),
    ("what is three hundred and twenty plus five", 325),
])
def test_sums(text, value):
    assert find_sum(text, WORDS)[1] == value


@pytest.mark.parametrize("text", [
    "I counted 25 beats in 15 seconds. Is that normal?",
    "Which one is the biggest?",
    "It rained 12 millimetres. Is that a lot?",
])
def test_no_sum_no_note(text):
    assert maths_note(text, None, EN) == ""


def test_checks_childs_answer():
    note = maths_note("I got two sixths. Is that right?", "What is one half plus one quarter?", EN)
    assert "not right yet" in note and "3/4" in note
    assert "is right" in maths_note("three quarters", "What is one half plus one quarter?", EN)
