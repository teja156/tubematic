"""The Format Packs skill (TMDEV-240). A main style's author reaches it through
tubematic-inserts by the name the pack gives (authoring_skill), so the name and
the pack must agree. Its limits and its worked example must be the ones the
validator enforces, and it must keep the user's impersonation line (made-up
threads, fiction-range numbers, no app or brand, the EXAMPLE tag), because a
still that passes for a real screenshot is the risk this style carries.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-format-packs"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import format_packs as fp  # noqa: E402


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def test_frontmatter_names_the_skill_and_the_pack_points_at_it():
    head = (SKILL / "SKILL.md").read_text().split("---")[1]
    assert re.search(r"^name: tubematic-format-packs$", head, re.M)
    assert "description:" in head and "disable-model-invocation" not in head
    assert tvs.pack("format_packs")["authoring_skill"] == "tubematic-format-packs"


def test_the_skill_names_every_format():
    for f in fp.FORMATS:
        assert f"| `{f}` |" in (SKILL / "SKILL.md").read_text(), f


def test_the_skill_states_the_validators_limits():
    text = _text()
    lim = fp.LIMITS
    for phrase in (f"messages` ({lim['minMessages']} to {lim['maxMessages']}", f"text at most {lim['messageChars']}",
                   f"at most {lim['markChars']}", f"`label` at most {lim['markLabelChars']}",
                   f"`items` ({lim['minItems']} to {lim['maxItems']}", f"`options` ({lim['minOptions']} to "
                   f"{lim['maxOptions']}", f"`headline` (at most {lim['headlineChars']}",
                   f"at least {lim['minGap']} frames after", f"at least {lim['endHold']} frames before",
                   f"more than {lim['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_skill_keeps_the_impersonation_line():
    text = _text()
    for phrase in ("Every thread is made up", "07700 900000", "555-0100", "No tick or verified mark",
                   "EXAMPLE", "Never invent a source"):
        assert phrase in text, phrase


def test_the_worked_example_passes_the_validator():
    ex = json.loads((SKILL / "reference" / "example-insert.json").read_text())
    assert fp.check_insert(ex["insert"], 30, ex["word_starts"], []) == []


def test_the_skill_has_one_check_and_submit_step():
    assert (SKILL / "SKILL.md").read_text().count("## Check and submit") == 1


def test_uninstall_removes_the_skill():
    assert '"tubematic-format-packs"' in (REPO / "uninstall.py").read_text()
