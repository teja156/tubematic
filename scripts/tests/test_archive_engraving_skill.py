"""The Archive and Engraving skill (TMDEV-230). The operator hands a video to
it by the name its style pack gives (get_video's style.authoring_skill), so
the name, the pack and the operator's routing must agree, and the skill must
be loadable by an unattended run. Its card kinds, events, emblems and limits
must be the ones the validator enforces: a skill that teaches a refused value
teaches the agent to be refused. It must send every still through the
engraving treatment and never ask for a named person in a picture: a real
person is a name card.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-archive-engraving"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import archive_engraving as ae  # noqa: E402

EXTRA = tvs.pack("archive_engraving")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-archive-engraving$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("archive_engraving")["authoring_skill"] == "tubematic-archive-engraving"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-archive-engraving" in operator


def test_the_skill_and_contract_list_every_card_event_and_emblem():
    text, contract = _text(), _contract()
    for key in ("card_kinds", "events", "emblems"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
            assert f"`{value}`" in contract, (key, value)
    assert EXTRA["card_kinds"] == list(ae.CARD_KINDS)
    assert EXTRA["events"] == list(ae.EVENTS) and EXTRA["emblems"] == list(ae.EMBLEMS)


def test_the_skill_states_the_validators_limits():
    text, contract = _text(), _contract()
    L, T = ae.LIMITS, ae.TIMING
    for phrase in (f"within {T['snap']} frames", f"at least {T['readFrames']} frames before",
                   f"at least {L['minBeatSeconds']} seconds", f"at most {L['maxBeats']}",
                   f"at most {L['titleChars']} characters", f"the header at most {L['headerChars']} characters",
                   f"a date {L['dateChars']}", f"a plate's name {L['nameChars']} and its note {L['noteChars']}",
                   f"dates {L['datesChars']} and role {L['roleChars']}", f"a document line {L['lineChars']}",
                   f"a strike's replacement {L['withChars']}", f"a stamp {L['stampChars']} capital letters",
                   f"At most **{L['maxImages']} different engravings per video**",
                   f"at least every {L['maxStillSeconds']} seconds"):
        assert phrase in text, phrase
    for phrase in (f"1 to {L['headerChars']} characters", f"1 to {L['maxBeats']} beats",
                   f"{L['minRoute']} to {L['maxRoute']} `[u, v]` points", f"{L['minPeople']} to {L['maxPeople']} people",
                   f"1 to {L['maxLines']} lines", f"1 to {L['maxInitials']} capital letters",
                   f"Years from {L['minYear']} to {L['maxYear']}", f"at least {ae.POINT_MARGIN} still pixels",
                   f"y {ae.ZONES['titleTop']}", f"{ae.ZONES['winW']} x {ae.ZONES['winH']} px"):
        assert phrase in contract, phrase
    for size in ae.TITLE_SIZES:
        assert str(size) in contract


def test_every_still_is_engraved_and_no_named_person_is_pictured():
    text = _text()
    assert 'treat_image(video_id, "<name>", "engraving")' in text
    assert "never call `generate_character`" in text
    assert "Never ask for a named person in a still," in text
    assert "/images/treated/<name>.engraving.png" in text and "read_image" in text
    for footnote in ae.FOOTNOTES.values():
        assert f'"{footnote}"' in text and f'"{footnote}"' in _contract()


def test_the_skill_hands_inserts_to_the_insert_skill():
    text = _text()
    assert "invoke the **tubematic-inserts** skill" in text and "any `inserts`" in text


def test_the_look_step_is_marked_for_the_frame_preview():
    assert "<!-- frame-preview:" in (SKILL / "SKILL.md").read_text()


def test_the_worked_example_is_valid_json_with_one_scene():
    cfg = json.loads((SKILL / "reference" / "example-config.json").read_text())
    assert [s["src"] for s in cfg["scenes"]] == ["ArchiveEngraving"]
    assert "subtitles" not in cfg
