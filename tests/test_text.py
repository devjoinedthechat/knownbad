import random

import pytest

from knownbad.text import bump_number, normalise, numbers, overlap, same_answer, sentences


def test_sentences_keep_decimals_and_split_on_lines():
    text = "It weighs 1.9 kilograms. It sleeps 2 people!\nNever dry clean it."
    assert sentences(text) == [
        "It weighs 1.9 kilograms.",
        "It sleeps 2 people!",
        "Never dry clean it.",
    ]


def test_numbers_finds_grouped_and_decimal_but_not_identifiers():
    found = [m.group() for m in numbers("Up to 1,500 litres, 1.9 kg, 30 days, model X200 and v2.")]
    assert found == ["1,500", "1.9", "30"]


@pytest.mark.parametrize(
    "literal", ["0", "1", "2", "14", "30", "007", "1,500", "12,000,000", "1.9", "0.05", "9.9"]
)
def test_bump_number_always_differs_and_keeps_the_format(literal):
    for seed in range(50):
        changed = bump_number(literal, random.Random(seed))
        assert changed != literal
        assert ("," in changed) == ("," in literal) or len(literal.replace(",", "")) <= 3
        assert ("." in changed) == ("." in literal)
        assert not changed.startswith("-")
        if "." in literal:
            assert len(changed.split(".")[1]) == len(literal.split(".")[1])


def test_normalise_and_same_answer():
    assert normalise("  Paris.  ") == "paris"
    assert same_answer("Paris", "paris, France")
    assert not same_answer("Paris", "Rome")
    assert same_answer("", "  ")
    assert not same_answer("", "Rome")


def test_overlap_counts_content_words_and_numbers():
    assert overlap("Refunds take 14 days", "The answer must say refunds take 14 days") == 1.0
    assert overlap("Refunds take 14 days", "The answer must be complete and correct") == 0.0
