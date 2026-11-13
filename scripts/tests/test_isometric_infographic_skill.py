"""The Isometric Infographic skill (TMDEV-237). The operator hands a video to it
by the name its style pack gives (get_video's style.authoring_skill), so the
name, the pack and the operator's routing must agree, and the skill must be
loadable by an unattended run. Its limits and catalogues must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-isometric-infographic"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import isometric_infographic as iso  # noqa: E402

EXTRA = tvs.pack("isometric_infographic")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-isometric-infographic$", fm, re.M)
    assert "disable-model-invocation" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("isometric_infographic")["authoring_skill"] == "tubematic-isometric-infographic"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "tubematic-isometric-infographic" in operator


def test_the_skill_and_contract_list_every_catalogue_value():
    text, contract = _text(), _contract()
    for key in ("props", "colors", "areas", "rooms", "stacks", "solids"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
            assert f"`{value}`" in contract, (key, value)


def test_the_skill_states_the_validators_limits():
    text = _text()
    L, T = iso.LIMITS, iso.TIMING
    for phrase in (f"A title of 1 to {L['titleChars']} characters", f"{L['minBoards']} to {L['maxBoards']} boards",
                   f"at least {L['minBoardSeconds']} s", f"within {T['snap']} frames of a word's start",
                   f"up to {L['maxAreas']} areas, 1 to {L['maxProps']} props, up to {L['maxRoutes']} routes of 2 to {L['maxRoutePoints']} points",
                   f"up to {L['maxMovers']} movers", f"up to {L['maxPins']} pins", f"up to {L['maxCamera']} camera moves",
                   "at least 0.6 tiles from each other", "the line leads every move",
                   f"a label of 1 to {L['labelChars']} characters, a value of 1 to {L['valueChars']}, a unit of up to {L['unitChars']}",
                   f"at a zoom from 1 to {iso.GEOMETRY['zoomMax']}", f"1 to {L['maxReadoutSteps']} steps",
                   f"at most {L['maxCubes']}", f"1 to {L['legendItems']} entries of 1 to {L['legendChars']} characters",
                   f"more than {L['maxStillSeconds']} seconds", f"at most {L['maxCustomProps']} in `customProps`",
                   f"at most {L['maxSolids']} solids"):
        assert phrase in text, phrase


def test_the_skill_teaches_the_tools_and_leaves_captions_to_the_style():
    text = _text()
    for tool in ("get_video", "get_timeline", "render_style_parts", "write_scene_config", "validate_job", "submit_render"):
        assert tool in text
    assert "Leave `subtitles` out of the config" in text
    assert text.count("Before submit_render") == 1


def test_the_reference_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert "subtitles" not in config
    assert iso.check(config, timeline["fps"], [w["startFrame"] for w in timeline["words"]], EXTRA, "vid_example") == []
    b = config["scenes"][0]["props"]["isometric"]["boards"][0]
    assert all(b.get(k) for k in ("routes", "movers", "pins", "camera", "lifts", "cutaways", "explodes"))


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-isometric-infographic"' in (REPO / "uninstall.py").read_text()
