"""The script-writing comparison's plumbing (TMDEV-211): what it sends, how
it reads an answer, how it scores and what it reports. The model call itself
is never made here; the comparison is run by hand.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import eval_script_writing as ev  # noqa: E402
from tubematic_core import formulas as tformulas  # noqa: E402

TOPIC = {"title": "Why 0.1 plus 0.2 is not 0.3", "brief": "Binary fractions.",
         "shape": "a tool did something that looks wrong", "formula": "broken-expectation"}
ANSWER = {
    "script_segments": [
        {"id": "seg-1", "beat": "The symptom", "visual": "a terminal",
         "voice": 'You type zero point one plus zero point two. <respell as="x">It</respell> lies.'},
        {"id": "seg-2", "voice": "But it is not broken. [pause] Follow for more.", "visual": ""},
    ],
    "publish_title": "The sum your computer gets wrong",
    "publish_description": "Why.",
    "formula_id": "broken-expectation",
    "hooks": [{"type": "problem", "text": "You type zero point one plus zero point two.", "kept": True},
              {"type": "question", "text": "Why?"}, {"type": "myth", "text": "Sums are exact."}],
}


def test_the_topic_set_is_usable_and_names_no_install():
    data = json.loads(ev.TOPICS.read_text())
    topics = data["topics"]
    assert len(topics) >= 10
    assert len({t["title"] for t in topics}) == len(topics)
    for t in topics:
        assert set(t) == {"title", "brief", "shape", "formula"}
        assert all(isinstance(t[k], str) and t[k].strip() for k in t)
        # The pick a fresh install's router could make: a core formula.
        assert not tformulas.FORMULAS[t["formula"]]["experimental"], t["title"]
        assert len(t["title"]) <= 70      # the dashboard's display-title limit


def test_the_prompt_carries_the_video_as_the_skill_reads_it():
    prompt = ev.build_prompt(TOPIC)
    video = json.loads(prompt.split("```json\n")[1].split("\n```")[0])
    assert video["status"] == "TOPIC_APPROVED"
    assert video["title"] == TOPIC["title"] and video["topic"] == TOPIC["brief"]
    assert video["script_profile_id"] == "" and video["style"]["script"] == ""
    assert video["pronunciation_mode"] == "respell"
    # The formula is picked before the writer runs; the prompt carries the pick.
    assert video["formula_routing"]["decided"] is True
    assert video["formula_routing"]["pick"] == TOPIC["formula"]
    assert '"user_preferences": ""' in prompt


def test_the_new_side_carries_every_formula_file_and_the_old_side_none():
    new = ev.new_skill()
    assert new.startswith("---\nname: tubematic-script-writing-skill")
    for fid in tformulas.FORMULAS:
        assert f"=== formulas/{fid}.md ===" in new
    assert "Use only the one for this video's formula" in new


def test_the_old_side_is_read_from_git(monkeypatch):
    seen = {}

    class Proc:
        returncode, stdout, stderr = 0, "old skill text", ""

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return Proc()

    monkeypatch.setattr(ev.subprocess, "run", fake_run)
    assert ev.old_skill("v9.9.9") == "old skill text"
    assert seen["cmd"][-1] == "v9.9.9:agent_files/skills/tubematic-script-writing-skill/SKILL.md"


def test_the_answer_is_the_last_json_object_with_a_script():
    text = 'Thinking {"script_segments": "not a list"} then ' + json.dumps(ANSWER)
    assert ev.parse_answer(text)["formula_id"] == "broken-expectation"
    assert ev.parse_answer('{"publish_title": "x"}') is None
    assert ev.parse_answer("no json here") is None


def test_spoken_text_drops_markup():
    assert ev.spoken('The <respell as="Gitt">Git</respell> log. [long pause] Stops '
                     '<break time="0.5s" /> here.') == "The Git log. Stops here."


def test_a_script_is_scored_with_its_record():
    row = ev.score(ANSWER)
    assert row["script"].startswith("You type zero point one plus zero point two. It lies.")
    assert row["words"] == 19
    assert (row["formula_id"], row["hook_type"]) == ("broken-expectation", "problem")
    ids = [w["id"] for w in row["warnings"]]
    assert "closing_ask" in ids and "length_band" in ids
    assert "no_formula" not in ids and "hook_mismatch" not in ids


def test_an_old_script_is_scored_without_a_record():
    old = {k: v for k, v in ANSWER.items() if k not in ("formula_id", "hooks")}
    row = ev.score(old)
    ids = [w["id"] for w in row["warnings"]]
    assert row["formula_id"] == "" and "no_formula" in ids and "length_band" not in ids


def test_a_formula_the_checks_do_not_know_is_reported_and_not_measured():
    row = ev.score({**ANSWER, "formula_id": "five-beats"})
    assert row["formula_id"] == "five-beats"
    assert "no_formula" in [w["id"] for w in row["warnings"]]


def test_the_reports_show_both_sides_and_count_each_warning():
    old = ev.score({k: v for k, v in ANSWER.items() if k not in ("formula_id", "hooks")})
    rows = [{"topic": TOPIC, "results": {"old": old, "new": ev.score(ANSWER)}},
            {"topic": {**TOPIC, "title": "Second"}, "results": {"old": {"error": "timed out"}}}]
    summary = ev.render_summary(rows, "sonnet", "v2.1.1", "2026-11-11 10:00", 1.5)
    assert "| Why 0.1 plus 0.2 is not 0.3 | 19 |" in summary
    assert "| Second | error | error | - | - | - | - |" in summary
    assert "| `closing_ask` | 1 | 1 |" in summary
    assert "| `no_formula` | 1 | 0 |" in summary
    assert "$1.50" in summary and "`v2.1.1`" in summary
    page = ev.render_topic(TOPIC, rows[0]["results"])
    assert "## Old skill" in page and "## New skill" in page
    assert "formula `broken-expectation`, opening `problem`" in page
    assert "**seg-1** (The symptom):" in page
    assert "- `problem` (used): You type zero point one" in page


def test_slug():
    assert ev.slug("Why 0.1 plus 0.2 is not 0.3 on a computer") == "why-0-1-plus-0-2-is-not-0-3-on-a-computer"
