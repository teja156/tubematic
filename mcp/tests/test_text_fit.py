"""The width estimate the Code Scenes and Format Packs validators share with
the renderer's fitText.ts (TMDEV-239/240). Both sides run the same cases, so a
text the validator passes is one the renderer can fit and wrap the same way.
"""
import json
import pathlib

import pytest

import text_fit as tf

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "text_fit_contract.json").read_text())


@pytest.mark.parametrize("case", FIXTURE["widths"])
def test_widths_match_the_fixture(case):
    assert tf.width(case["text"], case["size"], case["spacing"]) == pytest.approx(case["width"], abs=1e-3)


@pytest.mark.parametrize("case", FIXTURE["fits"])
def test_fitted_sizes_match_the_fixture(case):
    assert tf.fit_size(case["text"], case["max"], case["base"], case["min"], case["spacing"]) == case["size"]


@pytest.mark.parametrize("case", FIXTURE["wraps"])
def test_line_counts_match_the_fixture(case):
    assert tf.wrap_count(case["text"], case["size"], case["max"]) == case["lines"]


def test_wide_letters_are_wider_than_narrow_ones_and_emoji_wider_still():
    assert tf.width("WWWW", 40) > 2 * tf.width("iiii", 40)
    assert tf.char_em("\U0001F600") > tf.char_em("W")


def test_a_word_wider_than_its_box_is_broken_across_lines():
    assert tf.wrap_count("W" * 40, 44, 580) >= 3
