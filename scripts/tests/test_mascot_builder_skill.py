"""The mascot builder skill is invoked BY NAME from the poller's mascot lane, so it
must be loadable by an unattended run: unlike the troubleshooting skill it must
NOT be explicit-only on any agent CLI. It must also keep naming the three MCP
tools the build loop is made of (the tools own the shapes; the skill owns the
workflow), and the poller's prompt must name the skill it invokes.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-mascot-builder"


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    m = re.match(r"^---\n(.*?)\n---\n", _text(), re.S)
    assert m, "SKILL.md has no frontmatter"
    fm = m.group(1)
    assert re.search(r"^name: tubematic-mascot-builder$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm
    assert not (SKILL / "agents" / "openai.yaml").exists()


def test_skill_names_the_three_tools_of_the_build_loop():
    text = _text()
    for tool in ("get_mascot_job", "render_mascot_sheets", "submit_mascot"):
        assert tool in text
    assert (SKILL / "reference" / "guide.md").is_file()


def test_the_poller_prompt_invokes_this_skill_by_name():
    assert "tubematic-mascot-builder" in (REPO / "scripts" / "poll.py").read_text()


def test_the_contract_keeps_its_hard_rules():
    """bx is what stops a silent NaN blush; no talking mouth is a product decision."""
    guide = (SKILL / "reference" / "guide.md").read_text()
    assert "bx" in guide and "required" in guide
    assert "boilSeed" in guide and "Math.random()" in guide
    assert "no talking mouth" in guide.lower()
