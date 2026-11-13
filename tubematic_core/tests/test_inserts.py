"""Insert marks on a script (TMDEV-224): the rules a script write is held to.

An insert is one script segment marked with an insert style. The marks are
refused when they break the user's limits that can be judged from the words
alone (first or last segment, back to back), when the video's Inserts setting
is None, when inserts are not decided yet, or when the style is not one the
video may use. Length is only a warning here: it is measured for real on the
voiced timeline when the scenes are written.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import inserts as ti  # noqa: E402
from tubematic_core import visual_styles as tvs  # noqa: E402

STYLES = tvs.INSERT_STYLES


def _segs(*marks, voice="Short line here."):
    out = []
    for i, mark in enumerate(marks):
        seg = {"id": f"s{i}", "voice": voice, "visual": "v"}
        if mark:
            seg["insert"] = mark
        out.append(seg)
    return out


def _errors(segments, mode="auto", allowed=("system_flow",)):
    return ti.mark_errors(segments, insert_mode=mode, allowed=None if allowed is None else list(allowed),
                          insert_styles=STYLES)


def test_a_script_with_no_marks_is_always_fine():
    assert _errors(_segs("", "", ""), mode="none", allowed=None) == []


def test_a_mark_in_the_middle_is_fine():
    assert _errors(_segs("", "system_flow", "", "system_flow", "")) == []


@pytest.mark.parametrize("marks, fragment", [
    (("system_flow", "", ""), "first segment"),
    (("", "", "system_flow"), "last segment"),
    (("", "system_flow", "system_flow", ""), "back to back"),
])
def test_the_placement_limits(marks, fragment):
    errors = _errors(_segs(*marks))
    assert any(fragment in e for e in errors), errors


def test_inserts_set_to_none_refuse_any_mark():
    errors = _errors(_segs("", "system_flow", ""), mode="none")
    assert errors and "None" in errors[0]


def test_undecided_inserts_send_the_agent_to_the_routing_skill():
    errors = _errors(_segs("", "system_flow", ""), allowed=None)
    assert errors and "tubematic-insert-routing" in errors[0]


def test_a_style_the_video_did_not_choose_is_refused():
    errors = _errors(_segs("", "terminal_doc", ""), allowed=("system_flow",))
    assert any("not one of this video's insert styles" in e for e in errors)
    errors = _errors(_segs("", "terminal_doc", ""), allowed=())
    assert any("(none)" in e for e in errors)


def test_a_main_style_is_not_an_insert():
    errors = _errors(_segs("", "whiteboard", ""), allowed=("whiteboard",))
    assert any("is not an insert style" in e for e in errors)


def test_a_mark_must_be_a_string():
    segs = _segs("", "", "")
    segs[1]["insert"] = True
    assert any("must be a style id" in e for e in _errors(segs))


def test_a_long_insert_segment_warns_and_markup_does_not_count():
    long_voice = " ".join(["word"] * 30)
    warn = ti.mark_warnings(_segs("", "system_flow", "", voice=long_voice))
    assert [w["id"] for w in warn] == ["insert_long"]
    short = "Ten words <break time=\"1.0s\" /> [pause] <respell as=\"x\">here</respell> only."
    assert ti.mark_warnings(_segs("", "system_flow", "", voice=short)) == []
    # A faster voice gets through more words in the same time.
    edge = " ".join(["word"] * 25)
    assert ti.mark_warnings(_segs("", "system_flow", "", voice=edge), speed=1.0)
    assert ti.mark_warnings(_segs("", "system_flow", "", voice=edge), speed=1.25) == []


@pytest.mark.parametrize("raw, parsed", [
    ("", None), (None, None), ("  ", None), ("[]", []), ('["system_flow"]', ["system_flow"]),
    ("not json", []), ('{"a": 1}', []), ('["a", 3]', ["a"]),
])
def test_parse_styles(raw, parsed):
    assert ti.parse_styles(raw) == parsed


def test_dump_round_trips():
    assert ti.parse_styles(ti.dump_styles(["terminal_doc"])) == ["terminal_doc"]


def test_every_transition_has_a_frame_count():
    assert set(ti.TRANSITION_FRAMES) == set(ti.TRANSITIONS)
    assert ti.TRANSITION_FRAMES["cut"] == 0


def test_the_renderer_draws_every_transition_with_the_same_frame_counts():
    """The renderer's transitions.ts and this module name the same transitions
    with the same lengths: a transition only one side knew would be drawn as a
    cut while the checks reserve frames for it, or the reverse."""
    import re
    from pathlib import Path
    ts = (Path(__file__).resolve().parents[2] / "renderer" / "remotion" / "src" / "inserts"
          / "transitions.ts").read_text()
    m = re.search(r"TRANSITION_FRAMES: Record<InsertTransition, number> = \{([^}]*)\}", ts)
    frames = {k: int(v) for k, v in re.findall(r"(\w+): (\d+)", m.group(1))}
    assert frames == ti.TRANSITION_FRAMES
    union = re.search(r"export type InsertTransition = ([^;]*);", ts).group(1)
    assert set(re.findall(r'"(\w+)"', union)) == set(ti.TRANSITIONS)


def test_the_segment_that_opens_the_payoff_cannot_be_an_insert():
    from tubematic_core import formulas as tf
    formula = next(fid for fid in tf.FORMULAS if "payoff" in tf.beat_roles(fid).values())
    payoff = next(n for n, r in tf.beat_roles(formula).items() if r == "payoff")
    segs = _segs("", "system_flow", "", "")
    segs[1]["beat"] = payoff
    errors = ti.mark_errors(segs, insert_mode="auto", allowed=["system_flow"], insert_styles=STYLES,
                            formula_id=formula)
    assert any("opens the payoff" in e for e in errors), errors
    assert ti.payoff_index(segs, formula) == 1
    assert ti.mark_errors(segs, insert_mode="auto", allowed=["system_flow"], insert_styles=STYLES) == []


def test_a_style_that_takes_no_inserts_refuses_marks_with_its_own_reason():
    errors = ti.mark_errors(_segs("", "system_flow", ""), insert_mode="auto", allowed=None,
                            insert_styles=STYLES, hosts=False, host_message="Cartoon 3D takes none.")
    assert errors == ["Cartoon 3D takes none. Remove every segment's insert key."]
