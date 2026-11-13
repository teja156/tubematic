"""The Code Scenes skill (TMDEV-239). A main style's author reaches it through
tubematic-inserts by the name the pack gives (authoring_skill), so the name and
the pack must agree. Its limits, its language list and its worked example must
be the ones the validator enforces: a skill that teaches a refused value
teaches the agent to be refused. It must also keep the boundary with Terminal
Doc and the rule that output is shown only when certain, because nothing runs
the code.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-code-scenes"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import code_scenes as cs  # noqa: E402


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def test_frontmatter_names_the_skill_and_the_pack_points_at_it():
    head = (SKILL / "SKILL.md").read_text().split("---")[1]
    assert re.search(r"^name: tubematic-code-scenes$", head, re.M)
    assert "description:" in head and "disable-model-invocation" not in head
    assert tvs.pack("code_scenes")["authoring_skill"] == "tubematic-code-scenes"


def test_the_skill_states_the_validators_limits():
    text = _text()
    lim = cs.LIMITS
    for phrase in (f"At most {lim['maxLines']} lines of code and {lim['maxCols']} characters per line",
                   f"At least {lim['minStepGap']} frames", f"at least {lim['endHold']} frames before",
                   f"more than {lim['maxStillSeconds']} seconds", f"at most {lim['typeChars']} characters",
                   f"at most {lim['errorChars']} characters", f"up to {lim['outputLines']} lines of at most "
                   f"{lim['outputChars']} characters", f"at most {lim['outputLabelChars']} characters"):
        assert phrase in text, phrase


def test_the_skill_lists_exactly_the_validators_languages():
    row = next(line for line in (SKILL / "SKILL.md").read_text().splitlines() if line.startswith("| `lang` |"))
    assert re.findall(r"`([a-z]+)`", row)[1:] == list(cs.LANGS)


def test_the_worked_example_passes_the_validator():
    ex = json.loads((SKILL / "reference" / "example-insert.json").read_text())
    assert cs.check_insert(ex["insert"], 30, ex["word_starts"], []) == []
    steps = ex["insert"]["props"]["codeScenes"]["steps"]
    for step in steps:
        assert f"at {step['at']}" in _text()


def test_the_skill_keeps_the_terminal_doc_boundary_and_the_output_rule():
    text = _text()
    assert "A command typed at a shell and what it prints" in text and "| Terminal Doc |" in text
    assert "nothing runs it for you" in text
    assert "never a shell prompt" in text


def test_the_skill_has_one_check_and_submit_step():
    assert (SKILL / "SKILL.md").read_text().count("## Check and submit") == 1


def test_uninstall_removes_the_skill():
    assert '"tubematic-code-scenes"' in (REPO / "uninstall.py").read_text()
