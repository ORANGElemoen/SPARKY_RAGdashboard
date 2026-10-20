"""
Exact arithmetic for children's maths questions.

Small LLMs are unreliable at arithmetic ("two sixths is 11 twelfths"), so
when a learner's message contains a sum, it is worked out here with exact
fractions and handed to the model as a fact to explain, not recalculate.
Also checks a learner's answer ("I got 2/6") against the previous sum.

Number/fraction/operator words come from the language file's maths_words
(see config/languages/en.yaml); digits and + - * / work in every language.
"""

import re
from fractions import Fraction
from typing import Dict, List, Optional, Tuple, Union

Item = Union[Fraction, str]  # a number, an operator "+-*/", or "|" (a break)

_SYMBOLS = {"½": " 1/2 ", "¼": " 1/4 ", "¾": " 3/4 ", "⅓": " 1/3 ", "⅔": " 2/3 ",
            "×": " * ", "÷": " / ", "−": " - "}
_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?(?:/\d+)?|[^\W\d_]+|[-+*/]")


def _tokens(text: str, words: Dict) -> List[str]:
    t = text.lower()
    for sym, rep in _SYMBOLS.items():
        t = t.replace(sym, rep)
    t = re.sub(r"(?<=[^\W\d_])-(?=[^\W\d_])", " ", t)  # twenty-five -> twenty five
    t = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", t)     # 3x4 / 3 x 4 -> times
    for phrase, op in (words.get("operator_phrases") or {}).items():
        t = re.sub(rf"\b{re.escape(phrase)}\b", f" {op} ", t)
    return _TOKEN_RE.findall(t)


def _items(tokens: List[str], words: Dict) -> List[Item]:
    """Turn tokens into numbers, operators and breaks ("|" = not maths)."""
    numbers = words.get("numbers") or {}
    denominators = words.get("denominators") or {}
    operators = words.get("operators") or {}
    joiners = set(words.get("joiners") or [])  # "and" in "one and a half"

    items: List[Item] = []
    whole: Optional[Fraction] = None  # number before "and" in a mixed number
    small, big, have = 0, 0, False    # word-number accumulator

    def word_value() -> Optional[Fraction]:
        return Fraction(big + small) if have else None

    def flush():
        nonlocal whole, small, big, have
        value = word_value()
        if value is not None or whole is not None:
            items.append((whole or 0) + (value or 0))
        whole, small, big, have = None, 0, 0, False

    for i, tok in enumerate(tokens):
        if tok[0].isdigit():
            if have:
                flush()
            small, big, have = 0, 0, True
            whole_part = Fraction(tok)
            if i + 1 < len(tokens) and tokens[i + 1] in denominators:  # "2 thirds"
                small, have = whole_part, True
            else:
                items.append((whole or 0) + whole_part)
                whole, small, have = None, 0, False
        elif tok in numbers:
            value = numbers[tok]
            if value in (100, 1000) and have:
                if value == 100:
                    small *= 100
                else:
                    big, small = (big + small) * 1000, 0
            else:
                small += value
            have = True
        elif tok in denominators:
            count = word_value() if have else Fraction(1)
            frac = Fraction(count) / denominators[tok]
            items.append((whole or 0) + frac)
            whole, small, big, have = None, 0, 0, False
        elif tok in joiners and have and i + 1 < len(tokens) and (
                tokens[i + 1] in denominators or (i + 2 < len(tokens) and tokens[i + 2] in denominators)):
            whole, small, big, have = word_value(), 0, 0, False
        elif tok in joiners and have and i + 1 < len(tokens) and tokens[i + 1] in numbers:
            continue  # "three hundred and twenty" is one number
        elif tok in operators or tok in "+-*/":
            flush()
            items.append(operators.get(tok, tok))
        else:
            flush()
            items.append("|")
    flush()
    return items


def _evaluate(run: List[Item]) -> Optional[Fraction]:
    """Evaluate number op number ... with * and / before + and -."""
    try:
        terms: List[Item] = [run[0]]
        for op, num in zip(run[1::2], run[2::2]):
            if op in "*/":
                terms[-1] = terms[-1] * num if op == "*" else terms[-1] / num
            else:
                terms += [op, num]
        total = terms[0]
        for op, num in zip(terms[1::2], terms[2::2]):
            total = total + num if op == "+" else total - num
        return total
    except ZeroDivisionError:
        return None


def _runs(items: List[Item]) -> List[List[Item]]:
    """Maximal number (op number)+ sequences."""
    runs, cur = [], []
    for item in items + ["|"]:
        expects_number = not cur or isinstance(cur[-1], str)
        if isinstance(item, Fraction) and expects_number:
            cur.append(item)
        elif isinstance(item, str) and item in "+-*/" and cur and isinstance(cur[-1], Fraction):
            cur.append(item)
        else:
            if isinstance(cur[-1:] and cur[-1], str):
                cur.pop()
            if len(cur) >= 3:
                runs.append(cur)
            cur = [item] if isinstance(item, Fraction) else []
    return runs


def show(value: Fraction) -> str:
    """3/4 -> "3/4 (= 0.75)", 7/4 -> "7/4 (= 1 3/4 = 1.75)", 6 -> "6"."""
    if value.denominator == 1:
        return str(value.numerator)
    decimal = f"{float(value):.4f}".rstrip("0").rstrip(".")
    whole = int(value) if value > 0 else -int(-value)
    if abs(value) > 1 and whole:
        rest = abs(value - whole)
        return f"{value} (= {whole} {rest} = {decimal})"
    return f"{value} (= {decimal})"


def _describe(run: List[Item]) -> str:
    return " ".join(str(x) for x in run)


def find_sum(text: str, words: Dict) -> Optional[Tuple[str, Fraction]]:
    runs = _runs(_items(_tokens(text, words), words))
    for run in runs:
        value = _evaluate(run)
        if value is not None:
            return _describe(run), value
    return None


def find_single_value(text: str, words: Dict) -> Optional[Fraction]:
    """The one number in a short reply like "Two sixths!" / "I got 2/6", else None."""
    if len(text.split()) > 12:
        return None
    numbers = [x for x in _items(_tokens(text, words), words) if isinstance(x, Fraction)]
    return numbers[0] if len(numbers) == 1 else None


def maths_note(query: str, previous_query: Optional[str], strings: Dict) -> str:
    """Prompt note with the exact answer, or "" if the message has no sum."""
    if "maths_note" not in strings:
        return ""
    words = strings.get("maths_words") or {}
    found = find_sum(query, words)
    if found:
        expr, value = found
        return strings["maths_note"].format(fact=f"{expr} = {show(value)}")

    if previous_query:
        earlier = find_sum(previous_query, words)
        child = find_single_value(query, words)
        if earlier and child is not None:
            expr, value = earlier
            verdict = strings["maths_correct"] if child == value else strings["maths_incorrect"]
            return strings["maths_check_note"].format(
                child=show(child), expr=expr, answer=show(value), verdict=verdict)
    return ""
