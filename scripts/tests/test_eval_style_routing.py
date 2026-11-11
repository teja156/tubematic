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


# ── --openrouter: the same question through OpenRouter (TMDEV-220) ───────────

class _Resp:
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_openrouter_sends_the_skill_as_system_and_the_video_as_user(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout):
        sent["url"], sent["auth"], sent["timeout"] = req.full_url, req.get_header("Authorization"), timeout
        sent["body"] = json.loads(req.data)
        return _Resp({"choices": [{"message": {"content": 'ok {"style": "system_flow", "runner_up": "stick"}'}}],
                      "usage": {"cost": 0.0012}})

    monkeypatch.setattr(ev.urllib.request, "urlopen", fake_urlopen)
    answer, err, cost = ev.ask_openrouter("the video", "the skill", "deepseek/deepseek-v4.1-flash", 60, "k-test")
    assert answer["style"] == "system_flow" and err == "" and cost == 0.0012
    assert sent["url"] == ev.OPENROUTER_URL and sent["auth"] == "Bearer k-test" and sent["timeout"] == 60
    assert sent["body"]["model"] == "deepseek/deepseek-v4.1-flash"
    assert sent["body"]["messages"] == [{"role": "system", "content": "the skill"},
                                        {"role": "user", "content": "the video"}]


def test_openrouter_reports_a_reply_with_no_answer_as_an_error(monkeypatch):
    monkeypatch.setattr(ev.urllib.request, "urlopen",
                        lambda req, timeout: _Resp({"choices": [{"message": {"content": "I cannot decide."}}]}))
    answer, err, cost = ev.ask_openrouter("v", "s", "m", 5, "k")
    assert answer is None and "no JSON answer" in err and cost == 0.0
    monkeypatch.setattr(ev.urllib.request, "urlopen", lambda req, timeout: _Resp({"error": {"message": "x"}}))
    answer, err, _ = ev.ask_openrouter("v", "s", "m", 5, "k")
    assert answer is None and err.startswith("no answer")


def test_openrouter_without_a_key_stops_before_any_call(monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(ev.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    assert ev.main(["--openrouter", "deepseek/deepseek-v4.1-flash"]) == 2
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_the_report_shows_the_cost_when_there_is_one():
    rows = [{"case": CASE, "style": "system_flow", "verdict": "best", "reason": "r"}]
    assert "Cost: $0.0300" in ev.render_report(rows, "openrouter:m", "2026-11-11 12:00", 0.03)
    assert "Cost:" not in ev.render_report(rows, "sonnet", "2026-11-11 12:00")
