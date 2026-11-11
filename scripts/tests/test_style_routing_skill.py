"""The style-routing skill (TMDEV-203). Auto picks a video's style with it,
before the script, from the candidates get_video's style_routing lists.

The rule this file exists to keep: the skill reads the styles from data and
names none of them, so a new style pack is pickable the day it ships with no
edit to the skill. A skill that named styles would quietly prefer the ones it
knew about. It must also agree with the tool it calls and with the operator
that hands videos to it.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-style-routing"
sys.path.insert(0, str(REPO))

from tubematic_core import visual_styles as tvs  # noqa: E402


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-style-routing$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_skill_names_no_style():
    text = _text().lower()
    for sid, pack in tvs.PACKS.items():
        assert not re.search(rf"\b{re.escape(sid)}\b", text), sid
        assert pack["label"].lower() not in text, pack["label"]


def test_the_skill_reads_every_routing_field_the_candidates_carry():
    text = _text()
    for field in ("best_for", "avoid_for", "signals", "moods", "images", "available",
                  "unavailable_reason", "style_routing.candidates", "style_routing.decided",
                  "style_routing.domain"):
        assert field in text, field
    candidate = tvs.routing_candidates(True, "working", False)[0]
    assert set(candidate["routing"]) >= {"best_for", "avoid_for", "signals", "moods", "images"}


def test_the_fallback_it_names_is_the_real_one():
    assert f"`{tvs.SCENES}`" in _text()


def test_the_skill_calls_the_tool_with_its_real_arguments_and_limit():
    text = _text()
    assert "choose_visual_style(video_id, style=" in text
    assert "runner_up=" in text
    assert f"at most {tvs.STYLE_REASON_MAX_CHARS} characters" in text


def test_the_operator_runs_it_before_the_script():
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    row = next(line for line in operator.splitlines() if line.startswith("| `TOPIC_APPROVED` | **First"))
    assert row.index("tubematic-style-routing") < row.index("tubematic-script-writing-skill")
    assert "style_routing.decided" in row


def test_the_script_writer_follows_the_style_guidance():
    writer = (REPO / "agent_files" / "skills" / "tubematic-script-writing-skill" / "SKILL.md").read_text()
    assert "style.script" in writer


def test_the_uninstaller_and_the_readme_know_the_skill():
    assert '"tubematic-style-routing"' in (REPO / "uninstall.py").read_text()
    assert "`tubematic-style-routing/`" in (REPO / "agent_files" / "skills" / "README.md").read_text()
