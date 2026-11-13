"""The Mid-century How-To skill (TMDEV-233). The operator hands a video to it by
the name its style pack gives (get_video's style.authoring_skill), so the
name, the pack and the operator's routing must agree, and the skill must be
loadable by an unattended run. Its limits and its object catalogue must be the
ones the validator enforces: a skill that teaches a refused value teaches the
agent to be refused, and an object it does not list is one the agent will not
use.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-midcentury-howto"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import midcentury_howto as mc  # noqa: E402

EXTRA = tvs.pack("midcentury_howto")["extra"]


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-midcentury-howto$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("midcentury_howto")["authoring_skill"] == "tubematic-midcentury-howto"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-midcentury-howto" in operator


def test_the_contract_lists_exactly_the_objects_and_catalogues_the_validator_accepts():
    text = _contract()
    listed = set(re.findall(r"^\| `(\w+)` \| \d+ x \d+ \|", text, re.M))
    assert listed == set(EXTRA["objects"])
    for key in ("poses", "summary_poses", "faces", "outfits", "hairs", "grounds", "entrances"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
    for obj, spec in EXTRA["objects"].items():
        row = re.search(rf"^\| `{obj}` \|.*$", text, re.M).group(0)
        assert f"| {spec['text'] or '-'} |" in row, obj
        for act in spec["acts"]:
            assert f"`{act}`" in row, (obj, act)


def test_the_skill_states_the_validators_limits():
    text = " ".join(_text().split())
    L, T = mc.LIMITS, mc.TIMING
    for phrase in (f"at least {L['minIntroSeconds']} s in", f"{L['minSteps']} to {L['maxSteps']}",
                   f"at least {L['minStepSeconds']} seconds long", f"within {mc.SNAP_FRAMES} frames",
                   f"at least {L['minShotSeconds']} seconds long, at most {L['maxShots']}",
                   f"at least {T['endMargin']} frames before the next cut", f"at most {L['maxEventsPerShot']} a shot",
                   f"At most {L['maxElementsPerShot']} objects, labels and insets", f"at least {T['minPoseGap']} frames apart",
                   f"at least {T['minPressGap']} frames apart", f"at least {T['pressLead']} frames into its",
                   f"({T['objectIn']} frames after it appears)", f"title up to {L['titleChars']} characters",
                   f"kicker {L['kickerChars']}", f"a step header {L['headerChars']}", f"a tag {L['tagChars']}",
                   f"a label {L['labelChars']}", f"an inset {L['insetChars']}", f"{L['labelEchoWords']} or more narration words",
                   f"at least every {L['maxStillSeconds']} seconds", f"at least {L['minSummarySeconds']} seconds"):
        assert phrase in text, phrase


def test_the_skill_names_the_tools_it_uses_and_never_the_image_tools_as_steps():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_config", "validate_job", "submit_render", "render_style_props"):
        assert tool in text
    assert "never call `generate_image`" in text
    # the presenter never talks; the slot for looking at frames before submitting is reserved in one place
    assert "never moves\nhis mouth to talk" in text or "never moves his mouth to talk" in " ".join(text.split())
    assert text.count("**Look before you submit.**") == 1


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    words = timeline["words"]
    assert mc.check(config, timeline["fps"], [w["startFrame"] for w in words], [w["word"] for w in words], EXTRA) == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-midcentury-howto"' in (REPO / "uninstall.py").read_text()


def test_the_skill_teaches_objects_of_your_own_within_the_validators_limits():
    text = " ".join(_text().split())
    for phrase in (f"at most {mc.CUSTOM['maxProps']}", f"{mc.CUSTOM['minSide']} to {mc.CUSTOM['maxSide']} px",
                   f"at most {mc.CUSTOM['maxText']} characters", f"at most {mc.CUSTOM['maxActs']} acts",
                   "write_scene_file", "example-prop-alarm.tsx", "midcenturyHowTo/cel"):
        assert phrase in text, phrase


def test_the_example_prop_passes_the_validators_source_checks():
    body = (SKILL / "reference" / "example-prop-alarm.tsx").read_text()
    spec = json.loads(re.search(r"^//\s+(\{.*\})$", body, re.M).group(1))
    spec["src"] = "vid_x/prop-alarm"
    errs, _, _ = mc.custom_prop_errors([spec], "vid_x", EXTRA["objects"], {"vid_x/prop-alarm": body})
    assert errs == []
