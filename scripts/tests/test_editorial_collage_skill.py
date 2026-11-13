"""The Editorial Collage skill (TMDEV-229). The operator hands a video to it
by the name its style pack gives (get_video's style.authoring_skill), so the
name, the pack and the operator's routing must agree, and the skill must be
loadable by an unattended run. Its headline kinds, hero kinds, events and
limits must be the ones the validator enforces: a skill that teaches a
refused value teaches the agent to be refused. It must send every still
through the print or sticker treatment and never ask for a named person in a
picture: a real person is named in words only.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-editorial-collage"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import editorial_collage as ec  # noqa: E402

EXTRA = tvs.pack("editorial_collage")["extra"]
BANNED = ("deliberately", "on purpose", "by design", "silently", "exactly", "precisely", "simply", "actually",
          "really", "load-bearing")


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-editorial-collage$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("editorial_collage")["authoring_skill"] == "tubematic-editorial-collage"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-editorial-collage" in operator


def test_the_skill_and_contract_list_every_kind_and_event():
    text, contract = _text(), _contract()
    for key in ("headline_kinds", "hero_kinds", "events"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
            assert f"`{value}`" in contract, (key, value)
    assert EXTRA["headline_kinds"] == list(ec.HEADLINE_KINDS) and EXTRA["hero_kinds"] == list(ec.HERO_KINDS)
    assert EXTRA["events"] == list(ec.EVENTS)


def test_the_skill_states_the_validators_limits():
    text, contract = _text(), _contract()
    L, T = ec.LIMITS, ec.TIMING
    for phrase in (f"within {T['snap']} frames", f"at least {T['readFrames']} frames before",
                   f"at least {L['minStationSeconds']} seconds", f"at most {L['maxStations']}",
                   f"glides for {T['glide']} frames", f"at most {L['headlineChars']} characters",
                   f"the kicker at most {L['kickerChars']} characters", f"caption at most {L['captionChars']} characters",
                   f"a sticker's label {L['labelChars']}", f"an index line {L['lineChars']}",
                   f"a figure's label {L['figureLabelChars']}, its prefix {L['prefixChars']} and its suffix {L['suffixChars']}",
                   f"a stack item's caption {L['stackCaptionChars']}", f"a stamp {L['stampChars']} capital letters",
                   f"{T['typeRate']} characters a second", f"At most **{L['maxImages']} different stills per video**",
                   f"at least every {L['maxStillSeconds']} seconds", f"from 0 to {L['maxFigure']}"):
        assert phrase in text, phrase
    for phrase in (f"1 to {L['maxStations']} stations", f"1 to {L['headlineChars']} characters",
                   f"1 to {L['kickerChars']} characters", f"1 to {L['maxLines']} lines",
                   f"{L['minStack']} to {L['maxStack']} items", f"{ec.DESK['dy']} px lower",
                   f"for {T['glide']} frames", f"Headline | {ec.ZONES['headTop']} | {ec.ZONES['headBottom']} |",
                   f"Hero | {ec.ZONES['heroTop']} | {ec.ZONES['heroBottom']} |", f"{T['typeRate']} characters a second",
                   f"at most {L['maxImages']} different stills"):
        assert phrase in contract, phrase
    for spec in ec.HEADLINE.values():
        assert ", ".join(str(s) for s in spec["sizes"]) in contract


def test_every_still_is_treated_and_no_named_person_is_pictured():
    text = _text()
    assert 'treat_image(video_id, "<name>", "print")' in text and '"sticker"' in text
    assert "/images/treated/<name>.print.png" in text and "/images/treated/<name>.sticker.png" in text
    assert "never call `generate_character`" in text
    assert "Never ask for a named person in a still," in text
    assert "one isolated object on a plain flat light grey background" in text
    assert "read_image" in text
    for note in ec.NOTES.values():
        assert f'"{note}"' in text and f'"{note}"' in _contract()


def test_the_skill_hands_inserts_to_the_insert_skill():
    text = _text()
    assert "invoke the **tubematic-inserts** skill" in text and "any `inserts`" in text


def test_the_look_step_points_at_the_frame_preview():
    assert "`preview_frames(" in (SKILL / "SKILL.md").read_text()


def test_the_skill_is_written_plainly():
    for path in (SKILL / "SKILL.md", SKILL / "reference" / "contract.md"):
        body = path.read_text()
        assert "—" not in body, path
        low = body.lower()
        for word in BANNED:
            assert not re.search(rf"\b{word}\b", low), (path, word)


def test_the_worked_example_is_valid_json_with_one_scene_and_only_its_emphasis():
    cfg = json.loads((SKILL / "reference" / "example-config.json").read_text())
    assert [s["src"] for s in cfg["scenes"]] == ["EditorialCollage"]
    assert set(cfg.get("subtitles", {})) == {"emphasis"}
