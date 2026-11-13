"""The Paper Diorama skill (TMDEV-228). The operator hands a video to it by
the name its style pack gives (get_video's style.authoring_skill), so the name,
the pack and the operator's routing must agree, and the skill must be loadable
by an unattended run. Its rooms, slots, events and limits must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused. It must never send the agent to an image tool: the style makes no
images, and a call would be money spent on nothing.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-paper-diorama"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import paper_diorama as pd  # noqa: E402

EXTRA = tvs.pack("paper_diorama")["extra"]


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return " ".join((SKILL / "reference" / "contract.md").read_text().split())


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-paper-diorama$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("paper_diorama")["authoring_skill"] == "tubematic-paper-diorama"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-paper-diorama" in operator


def test_the_skill_and_contract_list_every_room_event_and_face():
    text, contract = _text(), _contract()
    for key in ("rooms", "slots", "events", "expressions"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)
            assert f"`{value}`" in contract, (key, value)
    for key in ("levels", "scales", "enters", "cuts", "accessories", "critter_colors"):
        for value in EXTRA[key]:
            assert f"`{value}`" in contract, (key, value)
    for color in pd.COLORS:
        assert f"`{color}`" in contract, color


def test_the_skill_states_the_validators_limits():
    text, contract = _text(), _contract()
    L, T = pd.LIMITS, pd.TIMING
    for phrase in (f"within {T['snap']} frames", f"at least {T['readFrames']} frames before",
                   f"at least {L['minSetSeconds']} seconds", f"at most {L['maxSets']}",
                   f"at most six things on stage", f"a banner at most {L['bannerChars']} characters",
                   f"a label {L['labelChars']}, a stamp {L['stampChars']}", f"at most {L['maxZooms']} `zoom`",
                   f"at least every {L['maxStillSeconds']} seconds"):
        assert phrase in text, phrase
    for phrase in (f"At most {L['maxCustomProps']} props", f"1 to {L['maxPieces']} pieces",
                   f"`w` 20 to {L['maxPropW']}", f"`h` 20 to {L['maxPropH']}", f"1 to {L['textChars']} characters",
                   f"at most {round(pd.OVERLAP_SHARE * 100)}%"):
        assert phrase in contract, phrase
    for room, floor in pd.ROOMS.items():
        assert f"`{room}`" in contract and str(floor) in contract
    assert L["maxItemsPerSet"] == 6


def test_the_skill_never_sends_the_agent_to_an_image_tool():
    text = _text()
    assert "never call `generate_image` or `generate_character`" in text
    assert "render_paper_props" in text


def test_the_skill_hands_inserts_to_the_insert_skill():
    text = _text()
    assert "invoke the **tubematic-inserts** skill" in text and "any `inserts`" in text


def test_the_worked_example_is_valid_json_with_one_scene():
    import json
    cfg = json.loads((SKILL / "reference" / "example-config.json").read_text())
    assert [s["src"] for s in cfg["scenes"]] == ["PaperDiorama"]
    assert "subtitles" not in cfg
