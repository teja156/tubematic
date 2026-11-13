"""The Flat Vector Science skill (TMDEV-236). The operator hands a video to it
by the name its style pack gives (get_video's style.authoring_skill), so the
name, the pack and the operator's routing must agree, and the skill must be
loadable by an unattended run. Its limits and catalogues must be the ones the
validator enforces, and the rules it teaches for the agent's own drawings must
be the ones the source checks enforce: a skill that teaches a refused value
teaches the agent to be refused.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-flat-vector-science"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import flat_vector_science as fv  # noqa: E402

EXTRA = tvs.pack("flat_vector_science")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-flat-vector-science$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("flat_vector_science")["authoring_skill"] == "tubematic-flat-vector-science"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-flat-vector-science" in operator


def test_the_skill_and_contract_list_every_prop_and_catalogue_value():
    text, contract = _text(), _contract()
    for group in EXTRA["props"].values():
        for name in group:
            assert f"`{name}`" in text and f"`{name}`" in contract, name
    for key in ("shotKinds", "backdrops", "slots", "sizes", "cuts"):
        for value in EXTRA[key]:
            assert f"`{value}`" in contract, (key, value)
    for key in ("shotKinds", "backdrops", "slots", "sizes"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)


def test_the_skill_states_the_validators_limits():
    text = _text()
    L, T = fv.LIMITS, fv.TIMING
    for phrase in (f"{L['minShots']} to {L['maxShots']} shots", f"within {T['snap']} frames of a word's start",
                   f"lasts at least {L['minShotSeconds']} s", f"holds 1 to {L['maxItems']} items",
                   f"up to {L['maxPills']} word-lit pills", f"1 to {L['pillChars']} characters",
                   f"A label is 1 to {L['labelChars']} characters", f"value or a rule or level label 1 to {L['valueChars']}",
                   f"a unit at most {L['unitChars']}", "At most one red thing in a shot",
                   f"at least {T['readFrames']} frames before", f"more than {L['maxStillSeconds']} seconds",
                   f"at most {L['maxCustomProps']} in `customProps`",
                   f"{L['minRungs']} to {L['maxRungs']} rungs", f"{L['minLevels']} to {L['maxLevels']} levels",
                   f"{L['minLayers']} to {L['maxLayers']} layers", f"{L['minSteps']} to {L['maxSteps']} stages"):
        assert phrase in text, phrase


def test_the_skill_teaches_the_drawing_rules_the_source_checks_enforce():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_file", "read_scene_file", "render_style_parts",
                 "write_scene_config", "validate_job", "submit_render"):
        assert tool in text
    assert "../../installed/flatVector/toon" in text
    assert fv._ALLOWED_IMPORT.match("../../installed/flatVector/toon") and fv._ALLOWED_IMPORT.match("react")
    assert "no hooks and nothing that depends on the frame" in text
    assert "You never call `generate_image` or `generate_character`" in text


def test_the_skill_leaves_the_captions_to_the_style_and_has_one_place_to_look_before_submitting():
    text = _text()
    assert "Leave `subtitles` out of the config" in text
    assert text.count("Before submit_render") == 1


def test_the_reference_files_ship_and_pass_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    assert "subtitles" not in config
    words = [w["startFrame"] for w in timeline["words"]]
    assert fv.check(config, timeline["fps"], words, EXTRA, "vid_example") == []
    kinds = {s["kind"] for s in config["scenes"][0]["props"]["flatVector"]["shots"]}
    assert kinds == set(fv.SHOT_KINDS)
    octopus = (ref / "example-prop-octopus.tsx").read_text()
    errs, _ = fv.custom_prop_errors([{"id": "octopus", "src": "vid_example/prop-octopus", "box": [360, 360]}],
                                    "vid_example", set(fv.library(EXTRA)), {"vid_example/prop-octopus": octopus})
    assert errs == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-flat-vector-science"' in (REPO / "uninstall.py").read_text()
