"""The Process Cast skill (TMDEV-235). The operator hands a video to it by the
name its style pack gives (get_video's style.authoring_skill), so the name, the
pack and the operator's routing must agree. Its limits and catalogues must be
the ones the validator enforces, and it must keep the style apart from the
install's mascot feature: its characters are its own cast.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "agent_files" / "skills" / "tubematic-process-cast"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import process_cast as pc  # noqa: E402

EXTRA = tvs.pack("process_cast")["extra"]


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-process-cast$", fm, re.M)
    assert "disable-model-invocation" not in fm and "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("process_cast")["authoring_skill"] == "tubematic-process-cast"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "tubematic-process-cast" in operator


def test_the_contract_lists_exactly_the_catalogues_the_validator_accepts():
    text = _contract()
    assert set(re.findall(r"^\| `(\w+)` \| \d+ x \d+ \| [\d-]+ \|", text, re.M)) == set(EXTRA["props"])
    assert set(re.findall(r"^\| `(\w+)` \| \d+ x \d+ \| [a-z]", text, re.M)) == set(EXTRA["stations"])
    for key in ("bodies", "tints", "accessories", "faces", "marks", "entrances", "camera_moves"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)


def test_the_skill_states_the_validators_limits():
    text = " ".join(_text().split())
    L, T = pc.LIMITS, pc.TIMING
    for phrase in (f"1 to {L['maxCast']} characters", f"1 to {L['maxStations']}", f"at most {L['maxEvents']}",
                   f"at most {L['nameChars']} characters", f"1 to {L['maxUnits']} cubes", f"within {pc.SNAP_FRAMES} frames",
                   f"busy for {T['enter']} frames after it enters", f"{T['hop']} after a hop", f"{T['trip']} after a trip",
                   f"at least {T['minActorGap']} frames apart", f"at least {L['minStationSeconds']} seconds",
                   f"into 2 or {L['maxClones']}", f"at most {L['cardChars']} characters",
                   f"at least every {L['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_skill_keeps_the_cast_apart_from_the_mascot_and_never_lip_syncs():
    text = " ".join(_text().split())
    assert "nothing to do with an install's mascot" in text and "takes no mascot" in text
    assert "never moves its mouth with the words" in text
    assert "never call `generate_image`" in text and "Nothing here runs code or a shell" in text
    assert text.count("**Look before you submit.**") == 1


def test_the_reference_example_passes_the_validator_and_the_prop_its_source_rules():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    words = timeline["words"]
    assert pc.check(config, timeline["fps"], [w["startFrame"] for w in words], [w["word"] for w in words], EXTRA) == []
    body = (ref / "example-prop-ticket.tsx").read_text()
    spec = json.loads(re.search(r"^//\s+(\{.*\})$", body, re.M).group(1))
    spec["src"] = "vid_x/prop-ticket"
    errs, _, _ = pc.custom_prop_errors([spec], "vid_x", EXTRA["props"], {"vid_x/prop-ticket": body})
    assert errs == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-process-cast"' in (REPO / "uninstall.py").read_text()
