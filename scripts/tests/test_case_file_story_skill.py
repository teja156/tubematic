"""The Case File Story skill (TMDEV-202). The operator hands a video to it by
the name its style pack gives (get_video's style.authoring_skill), so the name,
the pack and the operator's routing must agree, and the skill must be loadable
by an unattended run. Its limits, icons and beat fields must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused. It must also teach the two calls that keep the lead the same
character (the lead sheet from the house lead, then every still from that
sheet): an agent that skips either paints a different person into each picture.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-case-file-story"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import case_file_story as cfs  # noqa: E402

EXTRA = tvs.pack("case_file_story")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-case-file-story$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("case_file_story")["authoring_skill"] == "tubematic-case-file-story"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-case-file-story" in operator


def test_the_skill_and_contract_list_every_accent_beat_kind_and_icon():
    text, contract = _text(), _contract()
    for key in ("accents", "beats", "meter_kinds", "icons"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
            assert f"`{value}`" in contract, (key, value)


def test_the_skill_states_the_validators_limits():
    text = _text()
    L, T = cfs.LIMITS, cfs.TIMING
    for phrase in (f"{L['minMeters']} or {L['maxMeters']}, each", f"at most {L['meterLabelChars']} characters in capitals",
                   f"within {T['snap']} frames", f"at most {L['maxBeats']} beats",
                   f"at most **{L['maxImages']} different ones per video**",
                   f"lasts at least {L['minShotSeconds']} second", f"at least {T['punchMargin']} frames after",
                   f"at least {T['barStep']} frames apart", f"at least {T['readFrames']} frames on screen",
                   f"title is at most {L['titleChars']} characters", f"unit line {L['unitChars']}",
                   f"result {L['resultChars']}", f"bar label {L['barLabelChars']}",
                   f"threshold label {L['thresholdLabelChars']}", f"payoff line {L['payoffChars']}",
                   f"term {L['termChars']}", f"definition {L['definitionChars']}", f"stamp {L['stampChars']}",
                   f"citation {L['citationChars']}", f"option {L['optionChars']}",
                   f"at least every {L['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_contract_states_the_field_limits_and_the_fixed_delays():
    text = _contract()
    L, T, C = cfs.LIMITS, cfs.TIMING, cfs.CAMERA
    for phrase in (f"1 to {L['maxBeats']} beats", f"1 to {L['meterLabelChars']} characters", f"0 to {L['maxValue']}",
                   f"[{C['focusU']}, {C['focusV']}]", f"{C['punch']} times tighter", f"{C['push'] * 100:g}% per second",
                   f"over {T['hudDissolve']} frames", f"over {T['panelCount']} frames",
                   f"start {T['countStart']} frames after the card and run for {T['countFrames']}",
                   f"{T['resultDelay']} frames after the counter stops",
                   f"{L['minBars']} to {L['maxBars']} bars", f"{T['payoffDelay']} frames after the last bar",
                   f"{T['definitionDelay']} frames after the card starts", f"{T['stampDelay']} frames after the definition",
                   f"{T['stampIn'] + T['citationDelay']} frames after the stamp lands",
                   f"{T['optionFirst']} and {T['optionFirst'] + T['optionStep']} frames after the beat starts",
                   f"grid of {cfs.GEOMETRY['gridCols'] * cfs.GEOMETRY['gridRows']} icons",
                   f"to y {cfs.GEOMETRY['cardBottom']}"):
        assert phrase in text, phrase


def test_the_contract_shows_numbers_the_way_they_are_drawn():
    text = _contract()
    for kind, value in (("money", 4200), ("money", 40000), ("money", 1250000), ("count", 4200), ("count", 1250000),
                        ("percent", 58)):
        assert cfs.format_value(kind, value) in text, (kind, value)


def test_the_skill_teaches_the_lead_sheet_then_stills_from_it_and_never_characters():
    text = _text()
    for tool in ("get_video", "get_timeline", "generate_image", "read_image", "write_scene_config",
                 "validate_job", "submit_render"):
        assert tool in text
    assert f'generate_image(video_id, "{cfs.LEAD_NAME}", "<the outfit, in one sentence>", reference="{cfs.HOUSE_REFERENCE}")' in text
    assert f'reference="{cfs.LEAD_NAME}"' in text
    assert "never call `generate_character`" in text
    assert "No people." in text
    # the server writes the lead and the painting style into the prompt; the agent must not
    assert "do not describe the lead's head or the art style" in text
    # what a paid picture may never be asked for
    assert "Never ask for writing, a logo, a brand, a real bank or a real place" in text
    assert "never for a weapon or violence" in text


def test_the_skill_leaves_the_captions_to_the_style():
    assert "Leave `subtitles` out of the config" in _text()


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    assert "subtitles" not in config
    words = timeline["words"]
    assert cfs.check(config, timeline["fps"], [w["startFrame"] for w in words], EXTRA, "vid_example01") == []
    data = config["scenes"][0]["props"]["caseFile"]
    # the example shows every kind of beat the skill teaches, a punch-in, a meter change and a panel
    assert {b["type"] for b in data["beats"]} == set(cfs.BEAT_TYPES)
    shots = [b for b in data["beats"] if b["type"] == "shot"]
    assert any("punch" in s for s in shots) and any("set" in s for s in shots) and any("panel" in s for s in shots)
    assert any(s.get("hud") is False for s in shots)


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-case-file-story"' in (REPO / "uninstall.py").read_text()
