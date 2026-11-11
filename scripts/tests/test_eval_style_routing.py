"""The routing eval's plumbing (TMDEV-203): what it sends and how it scores.
The model call itself is never made here; the eval is run by hand.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import eval_style_routing as ev  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

CASE = {"title": "How DNS finds a website", "brief": "Resolvers and caching.",
        "expect": ["system_flow"], "ok": ["stick"]}


def test_the_prompt_carries_the_video_as_get_video_returns_it():
    candidates = tvs.routing_candidates(True, "working", False)
    prompt = ev.build_prompt(CASE, candidates)
    video = json.loads(prompt.split("```json\n")[1].split("\n```")[0])
    assert video["status"] == "TOPIC_APPROVED" and video["visual_style"] == "auto"
    assert video["title"] == CASE["title"] and video["topic"] == CASE["brief"]
    assert video["style_routing"]["decided"] is False
    assert [c["id"] for c in video["style_routing"]["candidates"]] == list(tvs.ROUTE_CHOICES)


def test_the_answer_is_the_last_json_object_with_a_style():
    text = 'Thinking {"not": "it"} ... {"style": "stick", "runner_up": "scenes", "reason": "r"}'
    assert ev.parse_answer(text)["style"] == "stick"
    assert ev.parse_answer("no json here") is None


def test_verdicts():
    assert ev.verdict(CASE, "system_flow") == "best"
    assert ev.verdict(CASE, "stick") == "ok"
    assert ev.verdict(CASE, "motion_graphics") == "wrong"


def test_the_report_counts_and_lists_wrong_picks():
    rows = [{"case": CASE, "style": "system_flow", "verdict": "best", "reason": "r"},
            {"case": {**CASE, "title": "T2"}, "style": "motion_graphics", "verdict": "wrong",
             "reason": "x", "description": "d", "scores": {}},
            {"case": {**CASE, "title": "T3"}, "verdict": "error", "error": "timed out"}]
    report = ev.render_report(rows, "sonnet", "2026-11-10 12:00")
    assert "Best pick: 1/3" in report and "Best or acceptable: 1/3" in report and "Errors: 1" in report
    assert "## Wrong picks" in report and "### T2" in report


def test_the_system_prompt_is_the_skill_the_agent_reads():
    assert ev.SKILL.read_text().startswith("---\nname: tubematic-style-routing")
