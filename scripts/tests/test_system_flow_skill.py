"""The System Flow skill (TMDEV-196). The operator hands a video to it by the
name its style pack gives (get_video's style.authoring_skill), so the name, the
pack and the operator's routing must agree, and the skill must be loadable by
an unattended run. Its icon list and limits must be the ones the validator
enforces: a skill that teaches a refused value teaches the agent to be refused.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-system-flow"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import system_flow as sf  # noqa: E402


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-system-flow$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("system_flow")["authoring_skill"] == "tubematic-system-flow"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-system-flow" in operator


def test_the_skill_lists_exactly_the_icons_the_validator_accepts():
    listed = set(re.findall(r"`(\w+)`", _text().split("`icon`, one of:")[1].split("Pick the nearest")[0]))
    assert listed == set(tvs.pack("system_flow")["extra"]["icons"])


def test_the_skill_states_the_validators_limits():
    text = _text()
    for phrase in (f"at most {sf.LIMITS['maxNodesPerBoard']} nodes", f"at most {sf.LIMITS['maxPerRow']} side by side",
                   f"at most {sf.LIMITS['maxRows']} rows deep", f"2 lines of {sf.LIMITS['labelLineChars']} characters",
                   f"at most {sf.LIMITS['headlineChars']}", f"at least {sf.TIMING['edgeAfterSource']} frames",
                   f"within\n  {sf.TIMING['targetWithin']} frames", f"every {sf.LIMITS['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_skill_names_the_tools_it_uses_and_never_the_image_tools_as_steps():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_config", "validate_job", "submit_render"):
        assert tool in text
    assert "never call `generate_image`" in text


def test_the_reference_files_ship_and_the_example_timeline_matches_its_config():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    assert (ref / "contract.md").is_file()


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-system-flow"' in (REPO / "uninstall.py").read_text()
