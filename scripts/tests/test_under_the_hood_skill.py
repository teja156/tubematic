"""The Under the Hood skill (TMDEV-201). The operator hands a video to it by
the name its style pack gives (get_video's style.authoring_skill), so the name,
the pack and the operator's routing must agree, and the skill must be loadable
by an unattended run. Its limits, poses and event fields must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused, and a pose it does not list is a pose the agent will not use.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-under-the-hood"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import under_the_hood as uth  # noqa: E402

EXTRA = tvs.pack("under_the_hood")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-under-the-hood$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("under_the_hood")["authoring_skill"] == "tubematic-under-the-hood"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-under-the-hood" in operator


def test_the_skill_and_contract_list_every_pose_event_and_tone():
    text, contract = _text(), _contract()
    for key in ("poses", "events", "tones"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
            assert f"`{value}`" in contract, (key, value)


def test_the_skill_states_the_validators_limits():
    text = _text()
    L, T = uth.LIMITS, uth.TIMING
    for phrase in (f"within {T['snap']} frames", f"at least {L['minPlateSeconds']} seconds long",
                   f"at most {L['maxPlates']} plates", f"at most **{L['maxImages']} different ones per video**",
                   f"at most {L['maxEventsPerPlate']} events", f"at most {L['maxElementsPerPlate']} callouts",
                   f"at least {T['minPoseGap']} frames after the last pose", f"at least {T['readFrames']} frames before",
                   f"{T['zoomOut']} frames early", f"callout is at most {L['calloutChars']} characters",
                   f"stat label {L['statLabelChars']}", f"chart label {L['chartLabelChars']}",
                   f"footnote {L['footnoteChars']}", f"chip {L['chipChars']}", f"sign {L['affixChars']}",
                   f"at least every {L['maxStillSeconds']} seconds", f"at least {uth.GEOMETRY['minLeaderPx']} px"):
        assert phrase in text, phrase


def test_the_contract_states_the_field_limits():
    text = " ".join(_contract().split())
    L, T, C = uth.LIMITS, uth.TIMING, uth.CAMERA
    for phrase in (f"{C['minZoom']} to {C['maxZoom']}", f"1 to {L['calloutChars']} characters",
                   f"{L['minArcs']} to {L['maxArcs']}", f"1 to {L['maxCounters']}", f"0 to {L['maxCounterValue']}",
                   f"{L['minChartPoints']} to {L['maxChartPoints']} numbers", f"{T['chartMin']} to {T['chartMax']} frames",
                   f"1 to {L['statLabelChars']} characters", f"1 to {L['footnoteChars']}",
                   f"characters x {uth.GEOMETRY['chipCharPx']} + {2 * uth.GEOMETRY['chipPadPx']}"):
        assert phrase in text, phrase


def test_the_skill_makes_and_checks_photographs_and_never_characters():
    text = _text()
    for tool in ("get_video", "get_timeline", "generate_image", "read_image", "write_scene_config",
                 "validate_job", "submit_render"):
        assert tool in text
    assert 'aspect_ratio="1:1"' in text
    assert "never call `generate_character`" in text
    assert "No text, no labels, no logos" in text


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    words = timeline["words"]
    assert uth.check(config, timeline["fps"], [w["startFrame"] for w in words], EXTRA, "vid_example01") == []
    # the example shows every kind of event the skill teaches
    kinds = {e["type"] for p in config["scenes"][0]["props"]["underTheHood"]["plates"] for e in p["events"]}
    assert kinds == set(uth.EVENT_TYPES)


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-under-the-hood"' in (REPO / "uninstall.py").read_text()
