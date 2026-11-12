"""The formula routing eval's plumbing (TMDEV-213): what it sends and how it
scores. The model call itself is never made here; the eval is run by hand.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import eval_formula_routing as ev  # noqa: E402
import eval_style_routing as style_ev  # noqa: E402
from tubematic_core import formulas as tf  # noqa: E402

CASE = {"title": "What happens when you tap a contactless card", "brief": "Reader, coil, chip, bank.",
        "expect": ["follow-the-flow"], "ok": ["paradox-mechanism-reframe"], "style": "system_flow"}


def _video(case):
    return json.loads(ev.build_prompt(case).split("```json\n")[1].split("\n```")[0])


def test_the_prompt_carries_the_video_as_get_video_returns_it():
    video = _video(CASE)
    assert video["status"] == "TOPIC_APPROVED"
    assert video["title"] == CASE["title"] and video["topic"] == CASE["brief"]
    # The style is decided and the formula is not: the state the skill runs in.
    assert video["style_routing"]["decided"] is True and video["visual_style"] == "system_flow"
    assert video["style"]["script"]          # the style's own script text reaches the router
    routing = video["formula_routing"]
    assert routing["decided"] is False and routing["choice"] == ""
    cands = {c["id"]: c for c in routing["candidates"]}
    assert list(cands) == list(tf.FORMULAS)
    assert cands["follow-the-flow"]["suits_style"]


def test_a_topic_is_routed_with_experimental_formulas_only_when_it_says_so():
    off = {c["id"]: c for c in _video(CASE)["formula_routing"]["candidates"]}
    assert not off["news-take"]["available"]
    on = {c["id"]: c for c in _video({**CASE, "experimental": True})["formula_routing"]["candidates"]}
    assert on["news-take"]["available"]


def test_a_topic_with_no_style_is_a_video_on_mixed_scenes():
    video = _video({k: v for k, v in CASE.items() if k != "style"})
    assert video["visual_style"] == "auto" and video["style_routing"]["pick"] == "scenes"
    assert not any(c["suits_style"] for c in video["formula_routing"]["candidates"])


def test_the_answer_is_the_last_json_object_with_a_formula():
    text = 'Thinking {"style": "x"} ... {"formula": "scene-story", "runner_up": "", "reason": "r"}'
    assert style_ev.parse_answer(text, "formula")["formula"] == "scene-story"
    assert style_ev.parse_answer("no json here", "formula") is None
    assert style_ev.parse_answer(text)["style"] == "x"      # the style eval's own key still works


def test_the_report_counts_overall_and_by_formula():
    rows = [{"case": CASE, "formula": "follow-the-flow", "verdict": "best", "reason": "r"},
            {"case": {**CASE, "title": "T2"}, "formula": "scene-story", "verdict": "wrong",
             "reason": "x", "shape": "s", "scores": {}},
            {"case": {**CASE, "title": "T3", "expect": ["scene-story"]}, "formula": "scene-story",
             "verdict": "best", "reason": "r"},
            {"case": {**CASE, "title": "T4"}, "verdict": "error", "error": "timed out"}]
    report = ev.render_report(rows, "sonnet", "2026-11-11 12:00")
    assert "Best pick: 2/4" in report and "Best or acceptable: 2/4" in report and "Errors: 1" in report
    assert "| follow-the-flow | 3 | 1 | 1 |" in report
    assert "| scene-story | 1 | 1 | 1 |" in report
    assert "## Wrong picks" in report and "### T2" in report


def test_the_system_prompt_is_the_skill_the_agent_reads():
    assert ev.SKILL.read_text().startswith("---\nname: tubematic-formula-routing")
    assert "choose_script_formula" in ev.INSTRUCTION


def test_every_case_in_the_topic_set_builds_a_prompt():
    for case in json.loads(ev.CASES.read_text(encoding="utf-8"))["cases"]:
        assert case["title"] in ev.build_prompt(case)


def test_a_topic_with_an_angle_carries_it_as_get_video_does_and_one_without_carries_none():
    with_angle = _video({**CASE, "angle": "A card with no battery signs a payment.", "angle_kind": "process"})
    assert (with_angle["angle"], with_angle["angle_kind"], with_angle["angle_formula"]) == \
        ("A card with no battery signs a payment.", "process", "follow-the-flow")
    without = _video(CASE)
    assert (without["angle"], without["angle_kind"], without["angle_formula"]) == ("", "", "")


def test_a_case_without_figures_is_routed_with_no_points():
    routing = _video(CASE)["formula_routing"]
    assert routing["learned"]["active"] is False
    assert all(c["learned"]["points"] == 0 for c in routing["candidates"])


def test_a_learned_case_hands_over_its_points_as_the_server_does():
    case = {**CASE, "learned": {"mode": "learned", "points": {"scene-story": 2,
                                                             "follow-the-flow": -1}}}
    routing = _video(case)["formula_routing"]
    assert routing["learned"]["active"] is True and routing["learned"]["mode"] == "learned"
    cands = {c["id"]: c for c in routing["candidates"]}
    assert cands["scene-story"]["learned"]["points"] == 2
    assert cands["scene-story"]["learned"]["standing"] == "better"
    assert cands["follow-the-flow"]["learned"]["standing"] == "worse"
    assert cands["incident-file"]["learned"] == {"points": 0, "standing": "thin", "videos": 0}
    assert routing["learned"]["accounts"] == 1


def test_a_trial_case_gives_its_points_to_thin_formulas_and_counts_the_rest():
    case = {**CASE, "learned": {"mode": "explore", "points": {"scene-story": 2}}}
    cands = {c["id"]: c for c in _video(case)["formula_routing"]["candidates"]}
    assert cands["scene-story"]["learned"] == {"points": 2, "standing": "thin", "videos": 0}
    assert cands["follow-the-flow"]["learned"] == {"points": 0, "standing": "even", "videos": 24}


def test_an_inactive_case_has_the_servers_inactive_shape():
    learned = _video(CASE)["formula_routing"]["learned"]
    assert learned["accounts"] == 0 and learned["stamp"] == "" and learned["openings"] == []
