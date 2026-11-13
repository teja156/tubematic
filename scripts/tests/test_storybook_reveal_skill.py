"""The Storybook Reveal skill (TMDEV-231). The operator hands a video to it by
the name its style pack gives (get_video's style.authoring_skill), so the
name, the pack and the operator's routing must agree, and the skill must be
loadable by an unattended run. Its turns and limits must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused. It must make the hero sheet once, paint every page from it, bake
every page's pencil plate, and never ask for a real or named person or a
brand.
"""
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-storybook-reveal"
OPERATOR = REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import storybook_reveal as sr  # noqa: E402

PACK = tvs.pack("storybook_reveal")


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-storybook-reveal$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill():
    assert PACK["authoring_skill"] == "tubematic-storybook-reveal"


@pytest.mark.skipif("tubematic-storybook-reveal" not in OPERATOR.read_text(),
                    reason="wired in WIRING-storybook-reveal.md")
def test_the_operator_routes_by_the_packs_skill_name():
    operator = OPERATOR.read_text()
    assert "style.authoring_skill" in operator and "tubematic-storybook-reveal" in operator


def test_the_skill_and_contract_list_every_turn():
    text, contract = _text(), _contract()
    for turn in PACK["extra"]["turns"]:
        assert f"`\"{turn}\"`" in contract or f"`{turn}`" in contract, turn
    assert PACK["extra"]["turns"] == list(sr.TURNS)
    assert "curl" in text and "cut" in text


def test_the_skill_states_the_validators_limits():
    text, contract = _text(), _contract()
    L, T = sr.LIMITS, sr.TIMING
    for phrase in (f"within {T['snap']} frames", f"at least {L['minPageSeconds']} seconds",
                   f"at most {L['maxPages']} pages", f"1 to {L['titleWords']} words and at most {L['titleChars']} characters",
                   f"at least {T['pencilAfter']} frames after the page starts",
                   f"{T['pencil']} to {T['colourWithin']} frames after `pencilAt`", "within a second of the pencil",
                   f"colour ({T['colour']} frames)", f"at least {T['read']} frames before the page ends",
                   f"**{L['maxImages']} different pictures per video**", f"at most {L['maxCurls']} per video",
                   f"at least every {L['maxHoldSeconds']} seconds"):
        assert phrase in text, phrase
    for phrase in (f"1 to {L['maxPages']} pages", f"{ZONE('panelWidth')} x {ZONE('panelHeight')} px",
                   f"from x {ZONE('panelLeft')}", f"y {ZONE('swashY')}", f"At most {L['maxImages']} different",
                   f"over {T['title']}", f"over {T['pencil']}", f"over {T['colour']}", f"takes {T['curl']}",
                   f"within 2 frames", f"at least every {L['maxHoldSeconds']} seconds", "from 1 to 1.06",
                   f"{sr.TITLE_SIZES[0]} px", f"{sr.TITLE_SIZES[1]} px", f"{ZONE('titleWidth')} px"):
        assert phrase in contract, phrase


def ZONE(key):
    return sr.ZONES[key]


def test_the_hero_sheet_is_made_once_and_every_page_is_painted_from_it():
    text = _text()
    assert 'generate_image(video_id, "hero", "<who the hero is and what they wear>")' in text
    assert 'read_image(video_id, "hero")' in text
    assert 'generate_image(video_id, "<name>", "<the scene>", reference="hero")' in text
    assert 'treat_image(video_id, "<name>", "pencil")' in text
    assert "/images/treated/<name>.pencil.png" in text and "read_image" in text
    assert "never call `generate_character`" in text
    assert PACK["pictures"]["sheet"]["name"] == "hero" and sr.SHEET == "hero"


def test_no_real_or_named_person_and_no_brand():
    text = _text()
    assert "Never a real or named person, and never a brand." in text
    assert "never a real or named person" in PACK["script"].lower()


def test_the_skill_hands_inserts_to_the_insert_skill():
    text = _text()
    assert "invoke the **tubematic-inserts** skill" in text and "any `inserts`" in text


def test_the_look_step_points_at_the_frame_preview():
    assert "`preview_frames`" in (SKILL / "SKILL.md").read_text()


def test_the_worked_example_is_valid_json_with_one_scene_and_three_pictures():
    cfg = json.loads((SKILL / "reference" / "example-config.json").read_text())
    assert [s["src"] for s in cfg["scenes"]] == ["StorybookReveal"]
    assert "subtitles" not in cfg
    pages = cfg["scenes"][0]["props"]["reveal"]["pages"]
    assert len({p["image"] for p in pages}) == 3
    timeline = json.loads((SKILL / "reference" / "example-timeline.json").read_text())
    assert 25 <= timeline["totalFrames"] / timeline["fps"] <= 40


def test_the_skills_text_keeps_the_writing_rules():
    for path in (SKILL / "SKILL.md", SKILL / "reference" / "contract.md"):
        text = path.read_text()
        assert "—" not in text, path
        for word in ("deliberately", "on purpose", "by design", "silently", "exactly", "precisely", "simply",
                     "actually", "really", "load-bearing"):
            assert not re.search(rf"\b{word}\b", text, re.I), (path, word)
