"""The Whiteboard skill (TMDEV-197). The operator hands a video to it by the
name its style pack gives (get_video's style.authoring_skill), so the name, the
pack and the operator's routing must agree, and the skill must be loadable by
an unattended run. Its doodle list, layouts and limits must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused, and its worked example must pass the validator for the same reason.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-whiteboard"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import whiteboard as wb  # noqa: E402


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-whiteboard$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("whiteboard")["authoring_skill"] == "tubematic-whiteboard"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-whiteboard" in operator


def test_the_skill_lists_exactly_the_doodles_the_validator_accepts():
    section = _text().split("**Doodles**, by name:")[1].split("Pick the nearest")[0]
    assert set(re.findall(r"`(\w+)`", section)) == set(tvs.pack("whiteboard")["extra"]["doodles"])


def test_the_skill_lists_exactly_the_layouts_and_slots():
    text = _text()
    for layout, slots in wb.LAYOUTS.items():
        assert f"| `{layout}` |" in text, layout
    contract = (SKILL / "reference" / "contract.md").read_text()
    for layout, slots in wb.LAYOUTS.items():
        for slot in slots:
            if not re.fullmatch(r"(left|right)_[23]", slot):  # written as left_1..left_3
                assert f"`{slot}`" in contract, (layout, slot)


def test_the_skill_states_the_validators_limits():
    text = _text()
    min_region = wb.TIMING["glide"] + int(wb.LIMITS["recapMinSeconds"] * 30)
    for phrase in (f"{wb.LIMITS['minRegions']} to {wb.LIMITS['maxRegions']} regions", f"at least {min_region} frames",
                   f"camera's {wb.TIMING['glide']}-frame glide", f"{wb.TIMING['glide'] - wb.TIMING['lag']} frames after",
                   f"finished {wb.TIMING['read']} frames before", f"every {wb.LIMITS['maxStillSeconds']} seconds",
                   f"at most {wb.LIMITS['recapMaxSeconds']} seconds", f"at least\n  {wb.LIMITS['recapMinSeconds']} seconds",
                   f"so {wb.recap_min_frames(6)} frames for six regions",
                   f"{wb.FLOOR['doodle']} frames plus its label", f"about {wb.TIMING['lag']} frames later"):
        assert phrase in text, phrase


def test_the_skill_names_the_tools_it_uses_and_never_the_image_tools_as_steps():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_config", "validate_job", "submit_render"):
        assert tool in text
    assert "never call `generate_image`" in text


def test_the_worked_example_passes_the_validator_against_its_own_timeline():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    assert wb.check_scene_use("whiteboard", config["scenes"]) == ""
    starts = [w["startFrame"] for w in timeline["words"]]
    assert wb.check(config, timeline["fps"], starts, tvs.pack("whiteboard")["extra"]["doodles"]) == []
    assert (ref / "contract.md").is_file()


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-whiteboard"' in (REPO / "uninstall.py").read_text()
