"""The Comic Panels skill (TMDEV-234). The operator hands a video to it by the
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
SKILL = REPO / "agent_files" / "skills" / "tubematic-comic-panels"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import comic_panels as cp  # noqa: E402

EXTRA = tvs.pack("comic_panels")["extra"]


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-comic-panels$", fm, re.M)
    assert "disable-model-invocation" not in fm and "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("comic_panels")["authoring_skill"] == "tubematic-comic-panels"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "tubematic-comic-panels" in operator


def test_the_contract_lists_exactly_the_catalogues_the_validator_accepts():
    text = _contract()
    assert set(re.findall(r"^\| `(\w+)` \| \d+ x \d+ \| \d+ \|", text, re.M)) == set(EXTRA["props"])
    assert set(re.findall(r"^\| `([\w+]+)` \| (?:three|four|two|one|a grid)", text, re.M)) == set(EXTRA["layouts"])
    for key in ("tones", "cast_kinds", "hairs", "outfits", "skins", "poses", "faces", "balloons", "lines"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)


def test_the_skill_states_the_validators_limits():
    text = " ".join(_text().split())
    L, T = cp.LIMITS, cp.TIMING
    for phrase in (f"1 to {L['maxCast']} characters", f"1 to {L['maxPages']}", f"at most {L['maxItemsPerPanel']} a panel",
                   f"at most {L['titleChars']} characters", f"within {cp.SNAP_FRAMES} frames",
                   f"at least {L['minPanelSeconds']} seconds", f"at least {T['minItemGap']} frames apart",
                   f"at least {T['endMargin']} frames before the panel ends",
                   f"a balloon at most {L['balloonChars']} characters", f"a caption box at most {L['captionChars']}",
                   f"a sound effect at most {L['sfxChars']}", f"repeats {L['echoWords']} narration words",
                   f"at least every {L['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_skill_keeps_the_cast_invented_and_the_narrator_off_screen():
    text = " ".join(_text().split())
    assert "this style takes no mascot" in text and "never draws a real, recognisable person" in text
    assert "never the narration read aloud" in text
    assert "never call `generate_image`" in text and "Nothing here runs code or a shell" in text
    assert text.count("**Look before you submit.**") == 1


def test_the_reference_example_passes_the_validator_and_the_prop_its_source_rules():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    words = timeline["words"]
    assert cp.check(config, timeline["fps"], [w["startFrame"] for w in words], [w["word"] for w in words], EXTRA) == []
    body = (ref / "example-prop-trophy.tsx").read_text()
    spec = json.loads(re.search(r"^//\s+(\{.*\})$", body, re.M).group(1))
    spec["src"] = "vid_x/prop-trophy"
    errs, _, _ = cp.custom_prop_errors([spec], "vid_x", EXTRA["props"], {"vid_x/prop-trophy": body})
    assert errs == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-comic-panels"' in (REPO / "uninstall.py").read_text()
