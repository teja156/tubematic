"""The Terminal Doc skill (TMDEV-199). The operator hands a video to it by the
name its style pack gives (get_video's style.authoring_skill), so the name, the
pack and the operator's routing must agree, and the skill must be loadable by
an unattended run. Its limits and its move catalogue must be the ones the
validator enforces: a skill that teaches a refused value teaches the agent to
be refused, and a move it does not list is a move the agent will not use.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-terminal-doc"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import terminal_doc as td  # noqa: E402


def _text() -> str:
    return " ".join((SKILL / "SKILL.md").read_text().split())


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", (SKILL / "SKILL.md").read_text(), re.S).group(1)
    assert re.search(r"^name: tubematic-terminal-doc$", fm, re.M)
    assert "disable-model-invocation" not in fm
    assert "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("terminal_doc")["authoring_skill"] == "tubematic-terminal-doc"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "style.authoring_skill" in operator and "tubematic-terminal-doc" in operator


def test_the_skill_and_the_contract_teach_every_move_slot_size_and_tone():
    skill, contract = _text(), _contract()
    for move in td.MOVES:
        assert f"| `{move}` |" in skill, move
        assert f"| `{move}` |" in contract, move
    for slot in td.SLOTS:
        assert f"| `{slot}` |" in contract, slot
    for size, px in td.SIZES.items():
        assert re.search(rf"^\| `{size}` \| {px} \| {td.max_chars(size)} \|$", contract, re.M), size
    for slot, spec in td.SLOTS.items():
        row = re.search(rf"^\| `{slot}` \| (\d+) \| (.*?) \|", contract, re.M)
        assert int(row.group(1)) == spec["y"], slot
        assert set(re.findall(r"`(\w+)`", row.group(2))) == set(spec["sizes"]), slot
    for value in (*td.TONES, *td.SKINS, *td.REVEALS, *td.CUTS):
        assert f"`{value}`" in contract, value


def test_the_skill_states_the_validators_limits():
    text = _text()
    for size in td.SIZES:
        assert re.search(rf"{td.max_chars(size)} (characters )?at `{size}`", text), size
    for phrase in (f"within {td.TIMING['snap']} frames", f"at least {td.LIMITS['minBeatSeconds']} seconds long",
                   f"at most {td.LIMITS['maxBeats']} beats", f"at most {td.LIMITS['maxEventsPerBeat']}",
                   f"at least {td.TIMING['readMargin']} frames before its beat's cut",
                   f"at most {td.LIMITS['maxOnStage']} elements on screen at once",
                   f"{td.LIMITS['noteLines']} lines of {td.LIMITS['noteChars']} characters",
                   f"{td.LIMITS['echoWords']} or more narration words",
                   f"at least every {td.LIMITS['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_contract_states_the_move_limits():
    text = " ".join(_contract().split())
    for phrase in (f"1 to {td.LIMITS['labelChars']} characters", f"1 to {td.LIMITS['boxLabelChars']} characters",
                   f"1 to {td.LIMITS['maxGuesses']} strings",
                   f"{td.LIMITS['minStreamFrames']} to {td.LIMITS['maxStreamFrames']}",
                   f"{td.LIMITS['minGridRows']} to {td.LIMITS['maxGridRows']} strings",
                   f"up to {td.LIMITS['maxOutputLines']} lines",
                   f"{td.LIMITS['minPushFrames']} to {td.LIMITS['maxPushFrames']}",
                   f"{td.LIMITS['minPushScale']} to {td.LIMITS['maxPushScale']}",
                   f"1 to {td.LIMITS['maxCite']}", f"{td.COUNT_FRAMES[0]} to {td.COUNT_FRAMES[1]} frames",
                   f"{td.CUSTOM['minFrames']} to {td.CUSTOM['maxFrames']}", f"0 to {td.CUSTOM['maxText']}",
                   f"at most {td.CUSTOM['maxMoves']} moves of your own"):
        assert phrase in text, phrase


def test_the_skill_names_the_tools_it_uses_and_never_the_image_tools_as_steps():
    text = _text()
    for tool in ("get_video", "get_timeline", "write_scene_config", "validate_job", "submit_render",
                 "write_scene_file", "read_scene_file", "preview_terminal_moves"):
        assert tool in text
    assert "never call `generate_image`" in text


def test_the_skill_teaches_moves_of_your_own_within_the_validators_limits():
    text = _text()
    for phrase in (f"at most {td.CUSTOM['maxMoves']} per video",
                   f"{td.CUSTOM['minFrames']} to {td.CUSTOM['maxFrames']} frames",
                   f"at most {td.CUSTOM['maxText']} characters", "example-move-caesar.tsx",
                   "../../installed/terminalDoc/kit", "useCurrentFrame"):
        assert phrase in text, phrase


def test_the_reference_files_ship_and_the_example_passes_the_validator():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    assert config["totalFrames"] == timeline["totalFrames"]
    words = timeline["words"]
    assert td.check(config, timeline["fps"], [w["startFrame"] for w in words], [w["word"] for w in words]) == []
    # the example shows most of the shipped moves, so the agent has a pattern for each
    used = {e["type"] for b in config["scenes"][0]["props"]["terminalDoc"]["beats"] for e in b["events"]}
    assert len(used) >= 10, used


def test_the_example_move_passes_the_validators_source_checks():
    body = (SKILL / "reference" / "example-move-caesar.tsx").read_text()
    spec = json.loads(re.search(r'customMoves as (\{.*?\})\.', " ".join(
        line.lstrip("/ ") for line in body.splitlines() if line.startswith("//"))).group(1))
    spec["src"] = "vid_x/move-caesar"
    errs, _ = td.custom_move_errors([spec], "vid_x", {"vid_x/move-caesar": body})
    assert errs == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-terminal-doc"' in (REPO / "uninstall.py").read_text()
