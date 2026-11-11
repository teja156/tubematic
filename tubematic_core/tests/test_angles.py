"""Topic angles (TMDEV-214): the kinds, the score rubric and the one validator.

Both processes that file or edit a topic call angles.angle_error, the research
skill's reference block and the mining prompt are rendered from this module,
and the dashboard reads the kinds through GET /angle-kinds. A kind that points
at a formula which does not exist would send the script writer to a reference
file that is not there.
"""
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import angles as ta  # noqa: E402
from tubematic_core import formulas as tf  # noqa: E402

GOOD = "Deleting a file frees no space until the last program holding it lets go."


def test_every_kind_names_a_formula_that_exists():
    assert len(ta.ANGLE_KINDS) == 10
    for kind, spec in ta.ANGLE_KINDS.items():
        assert spec["formula"] in tf.FORMULAS, kind
        assert spec["label"] and spec["means"], kind


def test_every_core_formula_is_some_kinds_first_choice():
    # Today the kinds and the formulas pair off one to one. A formula added
    # later needs no kind, so this checks one direction only.
    assert {s["formula"] for s in ta.ANGLE_KINDS.values()} <= set(tf.FORMULAS)
    assert len({s["formula"] for s in ta.ANGLE_KINDS.values()}) == len(ta.ANGLE_KINDS)


def test_a_perfect_angle_scores_the_maximum():
    assert sum(points for points, _ in ta.ANGLE_RUBRIC if points > 0) == ta.ANGLE_SCORE_MAX
    assert any(points < 0 for points, _ in ta.ANGLE_RUBRIC)


def test_formula_for_a_kind():
    assert ta.formula_for("incident") == "incident-file"
    assert ta.formula_for("") == ""
    assert ta.formula_for("nonsense") == ""
    assert ta.formula_for(None) == ""


def test_clean_collapses_whitespace_and_leaves_other_types_alone():
    assert ta.clean("  two\n words  ") == "two words"
    assert ta.clean(None) is None
    assert ta.clean(7) == 7


def test_a_valid_angle_passes():
    assert ta.angle_error(GOOD, "paradox", 7, required=True) is None
    assert ta.angle_error(GOOD, "paradox") is None
    assert ta.angle_error("", "") is None


@pytest.mark.parametrize("angle, kind", [(GOOD, ""), ("", "paradox")])
def test_sentence_and_kind_go_together(angle, kind):
    assert "together" in ta.angle_error(angle, kind)


def test_an_unknown_kind_is_refused_and_the_message_lists_the_kinds():
    err = ta.angle_error(GOOD, "surprise")
    assert "surprise" in err
    for kind in ta.ANGLE_KINDS:
        assert kind in err


def test_the_sentence_is_capped():
    assert ta.angle_error("x" * ta.ANGLE_MAX_CHARS, "myth") is None
    err = ta.angle_error("x" * (ta.ANGLE_MAX_CHARS + 1), "myth")
    assert str(ta.ANGLE_MAX_CHARS) in err


@pytest.mark.parametrize("angle, kind", [(7, "myth"), (["a"], "myth"), (GOOD, 3), (None, "myth")])
def test_wrong_types_are_refused(angle, kind):
    assert "must be a string" in ta.angle_error(angle, kind)


@pytest.mark.parametrize("score", [-1, 11, 2.5, "7", True, None])
def test_the_score_is_a_whole_number_from_0_to_10(score):
    assert "angle_score" in ta.angle_error(GOOD, "myth", score)


def test_a_score_needs_an_angle():
    assert "angle_score" in ta.angle_error("", "", 6)


def test_required_refuses_a_missing_angle_and_says_not_to_invent_one():
    err = ta.angle_error("", "", 0, required=True)
    assert "not proposed" in err
    assert "run summary" in err


@pytest.mark.parametrize("score", [1, 4])
def test_required_refuses_a_weak_angle(score):
    err = ta.angle_error(GOOD, "myth", score, required=True)
    assert f"below {ta.ANGLE_MIN_SCORE}" in err
    assert "run summary" in err


@pytest.mark.parametrize("word", ["none", "None.", " N/A ", "null", "no angle"])
def test_says_none_knows_the_words_for_no_angle(word):
    assert ta.says_none(word)


@pytest.mark.parametrize("value", ["", "paradox", "Nonetheless it works.", None, 3])
def test_says_none_leaves_everything_else(value):
    assert not ta.says_none(value)


def test_an_unknown_kind_says_how_to_send_no_angle_only_where_that_is_allowed():
    assert "leave angle, angle_kind and angle_score out" in ta.angle_error("A sentence.", "nope")
    assert "leave angle" not in ta.angle_error("A sentence.", "nope", 7, required=True)


@pytest.mark.parametrize("angle, kind, none", [
    ("none", "", True), ("", "no angle", True), (None, "-", True), ("", "N/A", True),
    ("A real sentence.", "none", False), ("", "paradox", False), ("", "", False),
])
def test_sent_no_angle_reads_the_raw_values(angle, kind, none):
    assert ta.sent_no_angle(angle, kind) is none


def test_required_asks_for_a_score_that_was_left_out():
    """0 is unscored. Read as weak, it would have the agent drop a subject
    that has an angle."""
    err = ta.angle_error(GOOD, "myth", 0, required=True)
    assert "angle_score was not passed" in err
    assert "run summary" not in err


@pytest.mark.parametrize("raw, kind", [("Paradox", "paradox"), ("Broken expectation.", "broken_expectation"),
                                       ("design-question", "design_question"), (" MYTH ", "myth")])
def test_clean_kind_brings_a_spelling_to_its_id(raw, kind):
    assert ta.clean_kind(raw) == kind
    assert ta.clean_kind(None) is None


def test_not_required_takes_any_score():
    assert ta.angle_error(GOOD, "myth", 0) is None
    assert ta.angle_error(GOOD, "myth", 3) is None


def test_public_list_is_the_kinds_in_order():
    listed = ta.public_list()
    assert [k["id"] for k in listed] == list(ta.ANGLE_KINDS)
    assert set(listed[0]) == {"id", "label", "means"}


@pytest.mark.parametrize("render", [ta.reference_markdown, ta.prompt_text])
def test_both_renderings_carry_every_kind_and_every_signal(render):
    text = render()
    for kind, spec in ta.ANGLE_KINDS.items():
        assert kind in text
        assert spec["means"] in text
    for _points, signal in ta.ANGLE_RUBRIC:
        assert signal in text
    assert str(ta.ANGLE_MIN_SCORE) in text


def test_the_reference_names_each_kinds_formula():
    text = ta.reference_markdown()
    for spec in ta.ANGLE_KINDS.values():
        assert tf.FORMULAS[spec["formula"]]["label"] in text
