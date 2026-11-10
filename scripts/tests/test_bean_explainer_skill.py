"""The Bean Explainer skill (TMDEV-198). The operator hands a video to it by the
name its style pack gives (get_video's style.authoring_skill), so the name, the
pack and the operator's routing must agree, and the skill must be loadable by
an unattended run. Its limits and its prop catalogue must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused, and a prop it does not list is a prop the agent will not use.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-bean-explainer"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import bean_explainer as be  # noqa: E402

EXTRA = tvs.pack("bean_explainer")["extra"]


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-bean-explainer$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("bean_explainer")["authoring_skill"] == "tubematic-bean-explainer"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-bean-explainer" in operator


def test_the_contract_lists_exactly_the_props_and_catalogues_the_validator_accepts():
    text = _contract()
    listed = set(re.findall(r"^\| `(\w+)` \| \d+ x \d+ \|", text, re.M))
    assert listed == set(EXTRA["props"])
    for key in ("poses", "faces", "looks", "marks", "accessories", "tints", "entrances", "fields", "section_colors"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
    for prop, spec in EXTRA["props"].items():
        row = re.search(rf"^\| `{prop}` \|.*$", text, re.M).group(0)
        assert (f"up to {spec['text']} characters" in row) if spec["text"] else ("| none |" in row), prop
        for act in spec["acts"]:
            assert f"`{act}`" in row, (prop, act)


def test_the_skill_states_the_validators_limits():
    text = " ".join(_text().split())
    for phrase in (f"within {be.SNAP_FRAMES} frames", f"at least {be.LIMITS['minShotSeconds']} seconds long",
                   f"at most {be.LIMITS['maxShots']} shots", f"at most {be.LIMITS['maxSections']}",
                   f"events start {be.TIMING['carousel']} frames", f"at least {be.TIMING['minPoseGap']} frames apart",
                   f"at most {be.LIMITS['maxElementsPerShot']} props and labels", f"at most {be.LIMITS['maxEventsPerShot']} events",
                   f"at least {be.TIMING['endMargin']} frames", f"{be.LIMITS['labelLines']} lines of {be.LIMITS['labelLineChars']} characters",
                   f"{be.LIMITS['labelEchoWords']} or more narration words", f"{be.TIMING['propIn']} frames after it appears",
                   f"at least every {be.LIMITS['maxStillSeconds']} seconds", f"at most {be.LIMITS['headerChars']} characters",
                   f"at most {be.LIMITS['titleChars']} characters"):
        assert phrase in text, phrase


def test_the_skill_names_the_tools_it_uses_and_never_the_image_tools_as_steps():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_config", "validate_job", "submit_render"):
        assert tool in text
    assert "never call `generate_image`" in text


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    words = timeline["words"]
    assert be.check(config, timeline["fps"], [w["startFrame"] for w in words], [w["word"] for w in words], EXTRA) == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-bean-explainer"' in (REPO / "uninstall.py").read_text()
