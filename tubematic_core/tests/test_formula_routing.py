"""Formula routing (TMDEV-213): the candidate list and the topic set.

Choosing a formula is the agent's judgement, made by the
tubematic-formula-routing skill from data, so no test here can run it;
scripts/eval_formula_routing.py does, by hand. What CI can hold is everything
around that judgement:

- the candidate list is read from the formula files (a new formula is a
  candidate with no edit anywhere), an experimental formula is off for Auto
  until the setting allows it, and a person's own choice is never off;
- the marks the router ranks by (the video's style, the domain's recent
  formulas) come from the arguments, never from stored state;
- the fixed topic set names only real formulas, and every core formula is the
  expected answer for enough topics that the eval measures it. A new core
  formula fails here until its change adds its topics.
"""
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import formulas as tf  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

CASES_PATH = pathlib.Path(__file__).resolve().parent / "fixtures" / "formula_routing_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
MIN_CASES_PER_CORE_FORMULA = 3
CORE = [fid for fid, f in tf.FORMULAS.items() if not f["experimental"]]
EXPERIMENTAL = [fid for fid, f in tf.FORMULAS.items() if f["experimental"]]


def _by_id(*args, **kw):
    return {c["id"]: c for c in tf.routing_candidates(*args, **kw)}


# ── the candidate list ───────────────────────────────────────────────────────

def test_every_formula_is_a_candidate_in_formula_order():
    assert [c["id"] for c in tf.routing_candidates()] == list(tf.FORMULAS)


def test_a_new_formula_becomes_a_candidate_with_no_other_edit(monkeypatch):
    extra = json.loads((tf.FORMULAS_DIR / "scene-story.json").read_text(encoding="utf-8"))
    extra.update(id="zz-new", label="New Formula", order=999)
    monkeypatch.setitem(tf.FORMULAS, "zz-new",
                        tf._check_formula(pathlib.Path("zz-new.json"), extra))
    assert tf.routing_candidates()[-1]["id"] == "zz-new"


def test_each_candidate_carries_what_the_router_scores_by():
    for c in tf.routing_candidates("system_flow", True, ["scene-story"]):
        f = tf.FORMULAS[c["id"]]
        for key in ("label", "family", "experimental", "line", "best_for", "also_for",
                    "avoid_for", "signals", "words"):
            assert c[key] == f[key], (c["id"], key)
        assert set(c) == {"id", "label", "family", "experimental", "line", "best_for", "also_for",
                          "avoid_for", "signals", "words", "suits_style", "recent", "available",
                          "unavailable_reason"}


def test_experimental_formulas_are_off_for_auto_until_the_setting_allows_them():
    off = _by_id("", False)
    assert [fid for fid, c in off.items() if not c["available"]] == EXPERIMENTAL
    for fid in EXPERIMENTAL:
        assert off[fid]["unavailable_reason"] == tf.EXPERIMENTAL_OFF
    for fid in CORE:
        assert off[fid]["available"] and off[fid]["unavailable_reason"] == ""
    on = _by_id("", True)
    assert all(c["available"] and c["unavailable_reason"] == "" for c in on.values())


def test_a_persons_own_choice_is_available_whatever_the_setting_says():
    picked = EXPERIMENTAL[0]
    cands = _by_id("", False, (), picked)
    assert cands[picked]["available"] and cands[picked]["unavailable_reason"] == ""
    assert not cands[EXPERIMENTAL[1]]["available"]


@pytest.mark.parametrize("style", ["", "auto", "scenes", "no_such_style"])
def test_no_formula_suits_a_style_that_is_not_a_pack(style):
    assert not any(c["suits_style"] for c in tf.routing_candidates(style))


def test_suits_style_follows_the_formulas_own_list():
    for style in tvs.PACKS:
        for c in tf.routing_candidates(style):
            assert c["suits_style"] == (style in tf.FORMULAS[c["id"]]["styles"]), (style, c["id"])


def test_the_style_never_removes_a_candidate():
    # A ranking signal: a style no formula names still gets every formula.
    for style in list(tvs.PACKS) + [""]:
        assert len(tf.routing_candidates(style)) == len(tf.FORMULAS)


def test_recent_marks_the_formulas_the_domain_just_used():
    cands = _by_id("", False, ["scene-story", "incident-file"])
    assert {fid for fid, c in cands.items() if c["recent"]} == {"scene-story", "incident-file"}
    assert not any(c["recent"] for c in tf.routing_candidates())
    # An id that is no formula any more (a formula a later version dropped) is ignored.
    assert not any(c["recent"] for c in tf.routing_candidates("", False, ["retired-formula"]))


def test_a_candidate_list_never_shares_state_with_the_formulas():
    first = tf.routing_candidates()
    first[0]["best_for"].append("changed")
    first[0]["words"][0] = 1
    assert "changed" not in tf.FORMULAS[first[0]["id"]]["best_for"]
    assert tf.routing_candidates()[0]["words"] == list(tf.FORMULAS[first[0]["id"]]["words"])


def test_the_reset_names_the_three_pick_columns_and_not_the_persons_choice():
    assert tf.PICK_RESET_SET == "formula_pick = '', formula_runner_up = '', formula_reason = ''"
    assert "formula_choice" not in tf.PICK_RESET_SET
    assert "formula_id" not in tf.PICK_RESET_SET


# ── the topic set ────────────────────────────────────────────────────────────

def test_every_case_names_only_real_formulas_and_styles():
    for case in CASES:
        assert case["expect"], case["title"]
        for fid in case["expect"] + case["ok"]:
            assert fid in tf.FORMULAS, (case["title"], fid)
        assert not set(case["expect"]) & set(case["ok"]), case["title"]
        assert case.get("style", "") in ("",) + tuple(tvs.PACKS), case["title"]
        assert case["title"].strip() and len(case["brief"]) > 80, case["title"]


def test_titles_are_unique():
    titles = [c["title"] for c in CASES]
    assert len(set(titles)) == len(titles)


@pytest.mark.parametrize("formula", CORE)
def test_every_core_formula_is_the_expected_answer_for_enough_topics(formula):
    # Counted over the cases routed with the setting off: what every install runs.
    n = sum(1 for c in CASES if not c.get("experimental") and c["expect"][0] == formula)
    assert n >= MIN_CASES_PER_CORE_FORMULA, (
        f"{formula} is the first expectation of {n} topic(s); add topics to "
        f"{CASES_PATH.name} so the routing eval measures it")


def test_a_case_expects_an_experimental_formula_only_with_the_setting_on():
    for case in CASES:
        first_is_experimental = tf.FORMULAS[case["expect"][0]]["experimental"]
        assert first_is_experimental == bool(case.get("experimental")), case["title"]


@pytest.mark.parametrize("formula", EXPERIMENTAL)
def test_every_experimental_formula_has_a_topic(formula):
    assert any(c["expect"][0] == formula for c in CASES), formula


def test_the_topics_name_no_install():
    # The set ships in the source tree; a domain or a channel of one install
    # in it would turn one person's data into everyone's fixture.
    text = CASES_PATH.read_text(encoding="utf-8")
    assert "TMDEV-" not in text and "http" not in text


def test_cases_with_an_angle_use_real_kinds_and_some_cases_have_none():
    # The eval routes both: a topic that arrives with an angle, and one with
    # none (a person's own topic, or one filed before topics had angles).
    from tubematic_core import angles as tangles
    with_angle = [c for c in CASES if c.get("angle_kind")]
    assert with_angle and len(with_angle) < len(CASES)
    for case in CASES:
        assert bool(case.get("angle")) == bool(case.get("angle_kind")), case["title"]
    for case in with_angle:
        assert case["angle_kind"] in tangles.ANGLE_KINDS, case["title"]
        # The angle's formula is the expected one, so the eval measures
        # whether the router takes the angle's lead.
        assert tangles.formula_for(case["angle_kind"]) == case["expect"][0], case["title"]
