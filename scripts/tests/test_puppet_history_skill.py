"""The Puppet History skill (TMDEV-232). The operator hands a video to it by the
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
SKILL = REPO / "agent_files" / "skills" / "tubematic-puppet-history"
sys.path.insert(0, str(REPO))
sys.path.append(str(REPO / "mcp"))  # last, so it never shadows a scripts module

from tubematic_core import visual_styles as tvs  # noqa: E402
import puppet_history as ph  # noqa: E402

EXTRA = tvs.pack("puppet_history")["extra"]


def _text() -> str:
    return (SKILL / "SKILL.md").read_text()


def _contract() -> str:
    return (SKILL / "reference" / "contract.md").read_text()


def test_frontmatter_names_the_skill_and_is_not_explicit_only():
    fm = re.match(r"^---\n(.*?)\n---\n", _text(), re.S).group(1)
    assert re.search(r"^name: tubematic-puppet-history$", fm, re.M)
    assert "disable-model-invocation" not in fm and "opencode/autoinvoke" not in fm


def test_the_style_pack_names_this_skill_and_the_operator_routes_by_it():
    assert tvs.pack("puppet_history")["authoring_skill"] == "tubematic-puppet-history"
    operator = (REPO / "agent_files" / "skills" / "tubematic-operator" / "SKILL.md").read_text()
    assert "tubematic-puppet-history" in operator


def test_the_contract_lists_exactly_the_catalogues_the_validator_accepts():
    text = _contract()
    assert set(re.findall(r"^\| `(\w+)` \| \d+ x \d+ \| [\d-]+ \|", text, re.M)) == set(EXTRA["props"])
    for key in ("costumes", "sets", "poses", "faces", "stamp_colors", "fills", "entrances"):
        for value in EXTRA[key]:
            assert f"`{value}`" in text, (key, value)


def test_the_skill_states_the_validators_limits():
    text = " ".join(_text().split())
    L, T = ph.LIMITS, ph.TIMING
    for phrase in (f"1 to {L['maxCast']} puppets", f"at most {L['nameChars']} characters", f"1 to {L['maxBeats']}",
                   f"at least {L['minBeatSeconds']} seconds", f"1 to {L['maxFocus']} countries",
                   f"at most {L['titleChars']} characters", f"1 to {L['cardLines']} `lines` of at most {L['lineChars']}",
                   f"repeats {L['echoWords']} narration words", f"at most {L['maxEvents']} in the video",
                   f"within {ph.SNAP_FRAMES} frames", f"at least {T['endMargin']} frames before",
                   f"busy for {T['slide']} frames after a slide-in", f"{T['pop']} after a pop-in",
                   f"at least {T['minActorGap']} frames apart", f"a sign at most {L['signChars']} characters",
                   f"a stamp at most {L['stampChars']}", f"a date at most {L['dateChars']}",
                   f"new value at most {L['strikeChars']}", f"a map label at most {L['labelChars']}",
                   f"at most {L['maxArrows']} arrows", f"at least every {L['maxStillSeconds']} seconds"):
        assert phrase in text, phrase


def test_the_skill_keeps_real_people_unrecognisable_and_tragedy_out_of_the_gags():
    text = " ".join(_text().split())
    assert "The puppet has no likeness and you never add one" in text
    assert "**Never** put a living person or a leader of a regime still in power on a plate" in text
    assert "**Never** play a tragedy for laughs" in text
    assert "this style takes no mascot" in text.lower() or "This style takes no mascot" in text
    assert "never call `generate_image`" in text and "Nothing here runs code or a shell" in text
    assert "Maps use today's borders" in text
    assert text.count("**Look before you submit.**") == 1


def test_the_pack_carries_the_same_rules_to_routing_script_and_review():
    pack = tvs.pack("puppet_history")
    avoid = " ".join(pack["routing"]["avoid_for"])
    assert "a living person, a living leader or a regime still in power" in avoid
    assert "tragedy" in avoid
    assert "never a living person" in pack["script"] and "Never play a tragedy for laughs" in pack["script"]
    assert "a living person or a living leader named on a plate" in pack["review"]


def test_the_reference_example_passes_the_validator_and_the_prop_its_source_rules():
    ref = SKILL / "reference"
    config = json.loads((ref / "example-config.json").read_text())
    timeline = json.loads((ref / "example-timeline.json").read_text())
    words = timeline["words"]
    assert ph.check(config, timeline["fps"], [w["startFrame"] for w in words], [w["word"] for w in words], EXTRA) == []
    body = (ref / "example-prop-hourglass.tsx").read_text()
    spec = json.loads(re.search(r"^//\s+(\{.*\})$", body, re.M).group(1))
    spec["src"] = "vid_x/prop-hourglass"
    errs, _, _ = ph.custom_prop_errors([spec], "vid_x", EXTRA["props"], {"vid_x/prop-hourglass": body})
    assert errs == []


def test_the_uninstaller_knows_the_skill():
    assert '"tubematic-puppet-history"' in (REPO / "uninstall.py").read_text()
