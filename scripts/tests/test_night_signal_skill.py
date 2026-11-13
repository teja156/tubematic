"""The Night Signal skill (TMDEV-238). The operator hands a video to it by the
name its style pack gives (get_video's style.authoring_skill), so the name, the
pack and the operator's routing must agree, and the skill must be loadable by
an unattended run. Its limits and catalogues must be the ones the validator
enforces: a skill that teaches a refused value teaches the agent to be refused.
It must also keep the style's two promises: one red threat per scene, and no
paid pictures (the style draws everything as pictograms).
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-night-signal"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import night_signal as ns  # noqa: E402

EXTRA = tvs.pack("night_signal")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-night-signal$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("night_signal")["authoring_skill"] == "tubematic-night-signal"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-night-signal" in operator


def test_the_contract_lists_every_catalogue_value_and_the_skill_every_kind_and_slot():
    text, contract = _text(), _contract()
    for key, values in EXTRA.items():
        for value in values:
            assert f"`{value}`" in contract, (key, value)
    for key in ("sceneKinds", "slots", "settings", "screens", "tones", "shapes"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)


def test_the_skill_states_the_validators_limits():
    text = _text()
    L, T = ns.LIMITS, ns.TIMING
    for phrase in (f"{L['minScenes']} to {L['maxScenes']} scenes", f"within {T['snap']} frames of a word's start",
                   f"lasts at least {L['minSceneSeconds']} s", f"holds 1 to {L['maxItems']} items",
                   "At most one item per scene", f"the file title {L['fileTitleChars']} characters",
                   f"a camera label {L['cameraLabelChars']}", f"a button {L['buttonChars']}",
                   f"a phone title {L['phoneTitleChars']}", f"1 to {L['phoneLines']} phone lines of {L['phoneLineChars']}",
                   f"1 or {L['ruleLines']} lines of {L['ruleLineChars']}", f"a case label {L['caseLabelChars']}",
                   f"name {L['caseNameChars']}", f"a stamp {L['stampChars']}", f"a steps title {L['stepsTitleChars']}",
                   f"{L['minSteps']} to {L['maxSteps']} steps of {L['stepChars']}",
                   f"at least {T['readFrames']} frames before", "at most one `check` mark",
                   f"more than {L['maxStillSeconds']} seconds", f"at most {L['maxCustomParts']} in `customParts`",
                   f"at most {L['maxShapes']} shapes", f"at least {T['slashDelay']} frames into the card",
                   f"x from -{L['partBox'] // 2} to {L['partBox'] // 2}", f"y from -{L['partBox']}"):
        assert phrase in text, phrase


def test_the_skill_teaches_the_tools_and_no_paid_pictures():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_config", "render_style_parts", "validate_job",
                 "submit_render"):
        assert tool in text
    assert "You never call `generate_image` or `generate_character`" in text
    assert "exactly one thing may be **red**" in text


def test_the_skill_leaves_the_captions_to_the_style_and_has_one_place_to_look_before_submitting():
    text = _text()
    assert "Leave `subtitles` out of the config" in text
    assert text.count("Before submit_render") == 1


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    assert "subtitles" not in config
    words = timeline["words"]
    assert ns.check(config, timeline["fps"], [w["startFrame"] for w in words], EXTRA, "vid_example") == []
    data = config["scenes"][0]["props"]["nightSignal"]
    kinds = {s["kind"] for s in data["scenes"]}
    assert {"tableau", "camera", "phone", "rule", "steps"} <= kinds
    items = [it for s in data["scenes"] for it in s.get("items", [])]
    assert any(it.get("redAt") for it in items) and any("at" in it for it in items)


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-night-signal"' in (REPO / "uninstall.py").read_text()
