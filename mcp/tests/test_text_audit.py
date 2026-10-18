"""Tests for the deterministic pre-render text-layout audit (VQA-9).

The audit's browser half (TextLayoutProbe.tsx) and its Remotion driver
(run-text-layout-audit.mjs) cannot be exercised on a dev host at all — Remotion
needs Node >= 20 and this host is on 18 — so every *decision* the audit makes
lives in text_audit.py precisely so it can be covered here. These tests are the
only automated gate on the geometry.

The overlap cases below are the MEASURED geometry of the real regression
fixture, mounted/scenes/generated/vid_835937dcf8e5/text-overlap.tsx, captured
from a live in-container run rather than estimated. Its three cases have
known-exact answers: A and B collide, C must NOT be flagged.

Run from repo root: pytest mcp/tests/
"""

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

import server
import text_audit


# ── Element helpers ─────────────────────────────────────────────────────────

def el(index, x, y, width, height, text="t", opacity=1.0, rotated=False,
       ancestors=None, font_size=0, line_height=None):
    return {
        "index": index,
        "tag": "span",
        "text": text,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "fontSize": font_size,
        "lineHeight": line_height,
        "opacity": opacity,
        "rotated": rotated,
        "ancestorIndices": ancestors or [],
    }


# MEASURED, not estimated. These are the exact values TextLayoutProbe reported
# for text-overlap.tsx at frame 146, running in the renderer container
# (tubematic-vqa9-audit:test, Chromium 149, Liberation Sans).
#
# Note height vs lineHeight: a 78px headline measures 88px tall against a CSS
# line box of 117. The probe measures a Range over the element's contents, and a
# Range rect is tight to the glyph run — no leading. Do not reintroduce a
# leading correction on top of these (see _ink_box).
A1 = el(0, 80, 394, 823.34375, 88, "THE FIRST HEADLINE", font_size=78, line_height=117)
A2 = el(1, 80, 418, 843.6875, 88, "SECOND ONE ON TOP", font_size=78, line_height=117)
B1 = el(2, 80, 910, 680, 136, "A caption that gets covered up", font_size=52, line_height=78)
B2 = el(3, 420, 938, 566.265625, 58, "OVERLAPPING LABEL", font_size=52, line_height=78)
C1 = el(4, 80, 1328, 718.890625, 49, "These two lines are close together",
        font_size=44, line_height=66)
C2 = el(5, 80, 1390, 645.390625, 49, "but they do not actually collide",
        font_size=44, line_height=66)

FIXTURE_FRAME = [A1, A2, B1, B2, C1, C2]

# Two lines a hair tighter than the fixture's case C: 56px text on a 78.4px CSS
# line box, stacked 66px apart. Under the retired element-rect measurement their
# LINE boxes intersected ~16%, and only a leading correction separated them from
# a real collision. Under Range measurement their ink is ~63px tall, so they do
# not intersect at all. Kept as a negative control, not as a threshold guard.
TIGHT1 = el(6, 80, 900, 700, 63, "tight but clean line one",
            font_size=56, line_height=78.4)
TIGHT2 = el(7, 80, 966, 700, 63, "tight but clean line two",
            font_size=56, line_height=78.4)


# ── The fixture's three cases ───────────────────────────────────────────────

def test_fixture_reports_exactly_the_two_real_collisions():
    """The whole point of the ticket: A and B are collisions, C is not."""
    hits = text_audit.find_overlaps(FIXTURE_FRAME)
    assert len(hits) == 2
    texts = {frozenset((h["a"]["text"], h["b"]["text"])) for h in hits}
    assert frozenset((A1["text"], A2["text"])) in texts
    assert frozenset((B1["text"], B2["text"])) in texts


def test_fixture_negative_control_lines_do_not_collide():
    """Case C, the fixture's own negative control."""
    assert text_audit.find_overlaps([C1, C2]) == []
    assert text_audit.overlap_fraction(C1, C2) == 0.0


def test_tight_but_clean_lines_are_not_a_collision():
    """Tighter than case C, and still clean because Range rects carry no leading."""
    assert text_audit.find_overlaps([TIGHT1, TIGHT2]) == []


def test_case_a_is_a_large_fraction_and_case_b_a_partial_one():
    """Both are above threshold, but B is the tightest true positive — the
    threshold has to stay well under it."""
    a = text_audit.overlap_fraction(A1, A2)
    b = text_audit.overlap_fraction(B1, B2)
    assert a == pytest.approx(0.727, abs=0.01)
    assert b == pytest.approx(0.600, abs=0.01)
    assert text_audit.OVERLAP_MIN_FRACTION < b < a


def test_threshold_leaves_headroom_under_the_tightest_true_positive():
    """A guard on the constant itself: if someone raises it past case B, the
    fixture silently stops reporting a real collision."""
    assert text_audit.OVERLAP_MIN_FRACTION <= text_audit.overlap_fraction(B1, B2) / 2


# ── Exclusions ──────────────────────────────────────────────────────────────

def test_nested_pair_is_not_a_collision():
    """A parent's rect contains its child's, so the pair always looks like a
    total overlap. The probe reports leaf text only, this is the second guard."""
    parent = el(0, 80, 380, 900, 90, "outer")
    child = el(1, 80, 380, 400, 90, "inner", ancestors=[0])
    assert text_audit.find_overlaps([parent, child]) == []


def test_nesting_is_detected_from_either_side():
    parent = el(0, 80, 380, 900, 90, "outer", ancestors=[])
    child = el(1, 80, 380, 400, 90, "inner", ancestors=[0])
    assert text_audit._is_nested(parent, child)
    assert text_audit._is_nested(child, parent)


def test_rotated_elements_are_skipped():
    """getBoundingClientRect() gives the axis-aligned bbox, which for rotated
    text is far larger than the glyphs — comparing those invents collisions."""
    a = dict(A1, rotated=True)
    assert text_audit.find_overlaps([a, A2]) == []
    assert not text_audit.is_measurable(a)


def test_elements_below_the_opacity_floor_are_skipped():
    """Mid-fade text is not a visible collision. This is why effective inherited
    opacity is measured at all."""
    faint = dict(A1, opacity=0.5)
    assert text_audit.find_overlaps([faint, A2]) == []


def test_element_exactly_at_the_opacity_floor_is_kept():
    assert text_audit.is_measurable(dict(A1, opacity=text_audit.OPACITY_FLOOR))


def test_zero_area_elements_are_skipped():
    assert not text_audit.is_measurable(el(0, 80, 380, 0, 90))
    assert not text_audit.is_measurable(el(0, 80, 380, 900, 0))


def test_touching_edges_are_not_an_overlap():
    """Rects that share a boundary have zero intersection area."""
    a = el(0, 0, 0, 100, 100)
    b = el(1, 100, 0, 100, 100)
    assert text_audit.overlap_fraction(a, b) == 0.0


def test_fraction_is_relative_to_the_smaller_rect():
    """A small label fully inside a big block is a 100% collision for the label,
    even though it covers little of the block."""
    big = el(0, 0, 0, 1000, 1000)
    small = el(1, 10, 10, 50, 50)
    assert text_audit.overlap_fraction(big, small) == pytest.approx(1.0)


# ── The subprocess boundary ─────────────────────────────────────────────────
#
# These drive the REAL _run_driver against a stub `node` on PATH. Everything
# else in this file hands a parsed dict to summarise(), which is exactly how the
# original stdout-parsing bug survived a green suite and then failed on the
# first real in-container run: Remotion forwards browser console logs to stdout,
# and the probe reports measurements *as* console logs.


def _fake_node(tmp_path, *, file_payload=None, stdout="", stderr="", code=0):
    """Put a stub `node` on PATH standing in for the real Remotion driver.

    Written in Python, not sh: the stub has to pull outputPath out of a JSON
    argument, and doing that in shell needs escaping fragile enough that a
    broken stub reads exactly like a broken audit.

    file_payload: written to the config's outputPath (None = write nothing,
    i.e. a driver that died before producing a document).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = f"""#!{sys.executable}
import json, sys
cfg = json.loads(sys.argv[2])
sys.stdout.write({stdout!r})
sys.stderr.write({stderr!r})
payload = {file_payload!r}
if payload is not None:
    open(cfg["outputPath"], "w").write(payload)
sys.exit({code!r})
"""
    node = bin_dir / "node"
    node.write_text(stub)
    node.chmod(0o755)
    remotion = tmp_path / "remotion"
    (remotion / "audit").mkdir(parents=True, exist_ok=True)
    (remotion / "audit" / "run-text-layout-audit.mjs").write_text("// stub")
    return bin_dir, remotion


# Remotion's real stdout during an audit: the probe's own console lines, echoed
# by Remotion, plus download/progress chatter.
PROBE_NOISE = (
    '[Tab 0, src/audit/TextLayoutProbe.tsx:220] '
    '__TUBEMATIC_TEXT_AUDIT__{"frame":45,"elements":[]}\n'
    'Downloading Chrome Headless Shell - 9.5 Mb/91.9 Mb\n'
)

# What audit_text_layout hands _run_driver, minus the outputPath it adds itself.
CFG_PASSES = {
    "sceneConfigPath": "/public/vid_x/scene-config.json",
    "timelinePath": "/public/vid_x/timeline.json",
    "audioPath": "/public/vid_x/audio.mp3",
    "passes": [{"scene": 0, "first": 45, "step": 101, "count": 4}],
    "browserExecutable": None,
}

REAL_PAYLOAD = json.dumps({
    "passes": [{"scene": 0, "requestedFrames": [45],
                "frames": [{"frame": 45, "elements": [A1, A2]}]}],
    "errors": [],
})


def test_driver_result_is_read_despite_remotion_polluting_stdout(tmp_path, monkeypatch):
    """The regression test for the bug the first real in-container run found."""
    bin_dir, remotion = _fake_node(tmp_path, file_payload=REAL_PAYLOAD, stdout=PROBE_NOISE)
    monkeypatch.setenv("PATH", str(bin_dir))
    out = text_audit._run_driver(remotion, dict(CFG_PASSES))
    assert out["errors"] == []
    assert out["passes"][0]["frames"][0]["elements"][0]["text"] == A1["text"]


def test_the_polluted_stdout_alone_would_not_parse(tmp_path, monkeypatch):
    """Proves the fixture above is a real reproduction: the same stdout, with no
    result file, is not JSON — which is exactly how the original failed."""
    with pytest.raises(json.JSONDecodeError):
        json.loads(PROBE_NOISE)


def test_driver_output_file_is_cleaned_up(tmp_path, monkeypatch):
    bin_dir, remotion = _fake_node(tmp_path, file_payload=REAL_PAYLOAD)
    monkeypatch.setenv("PATH", str(bin_dir))
    before = set(Path(tempfile.gettempdir()).glob("tubematic-text-audit-*"))
    text_audit._run_driver(remotion, dict(CFG_PASSES))
    after = set(Path(tempfile.gettempdir()).glob("tubematic-text-audit-*"))
    assert after == before, "temp result file leaked"


def test_stdout_is_the_fallback_when_no_file_was_written(tmp_path, monkeypatch):
    """The driver rejects a config before it learns outputPath -> stdout only."""
    payload = json.dumps({"passes": [], "errors": ["missing outputPath"]})
    bin_dir, remotion = _fake_node(tmp_path, stdout=payload, code=1)
    monkeypatch.setenv("PATH", str(bin_dir))
    out = text_audit._run_driver(remotion, dict(CFG_PASSES))
    assert out["errors"] == ["missing outputPath"]


def test_noise_on_stdout_with_no_file_reports_the_stderr_tail(tmp_path, monkeypatch):
    """Unparseable stdout must NOT be reported as a JSON error — that would bury
    the one line that says what actually broke."""
    bin_dir, remotion = _fake_node(
        tmp_path, stdout=PROBE_NOISE, stderr="Error: bundling blew up\n", code=1)
    monkeypatch.setenv("PATH", str(bin_dir))
    with pytest.raises(RuntimeError, match="bundling blew up"):
        text_audit._run_driver(remotion, dict(CFG_PASSES))


def test_junk_in_the_result_file_is_reported_as_a_parse_failure(tmp_path, monkeypatch):
    bin_dir, remotion = _fake_node(tmp_path, file_payload="not json at all")
    monkeypatch.setenv("PATH", str(bin_dir))
    with pytest.raises(RuntimeError, match="was not JSON"):
        text_audit._run_driver(remotion, dict(CFG_PASSES))


def test_audit_reports_a_driver_failure_as_a_warning_and_never_raises(tmp_path, monkeypatch):
    """The fail-open contract, end to end through the real subprocess path."""
    bin_dir, remotion = _fake_node(tmp_path, stderr="boom\n", code=1)
    monkeypatch.setenv("PATH", str(bin_dir))
    cfg = {"fps": 30, "totalFrames": 450,
           "scenes": [{"src": "vid_x/a", "durationInFrames": 450}]}
    (tmp_path / "cfg.json").write_text(json.dumps(cfg))
    out = text_audit.audit_text_layout(
        "vid_x", cfg, tmp_path / "cfg.json", tmp_path / "t.json",
        tmp_path / "a.mp3", remotion)
    assert len(out) == 1
    assert "could not run" in out[0]


# ── Safe zone ───────────────────────────────────────────────────────────────
#
# Modelled on the second fixture, safe-zone-violation.tsx, which has three text
# elements and exactly two violations.

# Violation 1: paddingBottom 8 with justifyContent flex-end -> box bottom at
# y=1912, deep inside the 170px bottom exclusion zone.
SZ_BOTTOM = el(0, 60, 1838, 960, 74, "THIS LINE SITS BELOW THE BOTTOM SAFE ZONE",
               font_size=64)
# Violation 2: left 720, whiteSpace nowrap, 56px -> runs way past the frame edge.
SZ_RIGHT = el(1, 720, 1400, 1430, 64, "THIS TEXT RUNS OFF THE RIGHT EDGE OF THE FRAME",
              font_size=56)
# Not a violation: the centred "Safe zone test" span.
SZ_OK = el(2, 400, 930, 280, 83, "Safe zone test", font_size=72)

SAFE_ZONE_FRAME = [SZ_BOTTOM, SZ_RIGHT, SZ_OK]


def test_safe_zone_fixture_reports_exactly_two_violations():
    hits = text_audit.find_safe_zone_violations(SAFE_ZONE_FRAME)
    assert len(hits) == 2
    assert {h["element"]["index"] for h in hits} == {0, 1}


def test_bottom_violation_names_the_bottom_edge():
    hits = text_audit.find_safe_zone_violations([SZ_BOTTOM])
    assert len(hits) == 1
    assert any("bottom" in b for b in hits[0]["breaches"])
    assert not hits[0]["clipped"]  # inside the frame, just under the platform UI


def test_offscreen_text_is_both_a_breach_and_clipped():
    """The text_offscreen case: past the safe zone AND past the frame itself."""
    hits = text_audit.find_safe_zone_violations([SZ_RIGHT])
    assert len(hits) == 1
    assert any("right" in b for b in hits[0]["breaches"])
    assert hits[0]["clipped"]


def test_text_inside_the_zone_is_not_a_violation():
    assert text_audit.find_safe_zone_violations([SZ_OK]) == []


def test_hanuman_style_captions_are_not_violations():
    """The real video the VLM fabricated a violation on: text at paddingBottom
    250-320 against a 170px zone, i.e. 80-150px INSIDE it."""
    for padding_bottom in (250, 280, 320):
        bottom = 1920 - padding_bottom
        caption = el(0, 60, bottom - 67, 960, 67, "a caption", font_size=56)
        assert text_audit.find_safe_zone_violations([caption]) == [], padding_bottom


def test_each_edge_is_detected_independently():
    assert any("left" in b for b in
               text_audit.safe_zone_breaches(el(0, 10, 900, 200, 60)))
    assert any("right" in b for b in
               text_audit.safe_zone_breaches(el(0, 900, 900, 200, 60)))
    assert any("top" in b for b in
               text_audit.safe_zone_breaches(el(0, 100, 10, 200, 60)))
    assert any("bottom" in b for b in
               text_audit.safe_zone_breaches(el(0, 100, 1800, 200, 60)))


def test_text_exactly_on_the_safe_zone_boundary_is_allowed():
    """x 60-1020, y 150-1750 is the documented inclusive box."""
    flush = el(0, 60, 150, 960, 1600)
    assert text_audit.safe_zone_breaches(flush) == []
def test_faint_and_rotated_elements_are_excluded_from_the_safe_zone_check_too():
    assert text_audit.find_safe_zone_violations([dict(SZ_BOTTOM, opacity=0.2)]) == []
    assert text_audit.find_safe_zone_violations([dict(SZ_BOTTOM, rotated=True)]) == []


def test_safe_zone_warning_names_the_element_and_the_edge():
    frames = [{"frame": 45, "elements": SAFE_ZONE_FRAME}]
    out = text_audit.summarise(_driver_output(frames), CFG)
    assert len(out) == 2
    joined = " | ".join(out)
    # Full string, untruncated: the excerpt is how the agent locates the element
    # in its own TSX, so a real headline has to survive intact.
    assert "THIS LINE SITS BELOW THE BOTTOM SAFE ZONE" in joined
    assert "CLIPPED" in joined  # the off-frame one is called out as worse


def test_very_long_text_is_truncated_with_an_ellipsis():
    long_text = "x" * 200
    warned = text_audit._excerpt(el(0, 0, 0, 10, 10, long_text))
    assert warned.endswith("…")
    assert len(warned) == text_audit._TEXT_EXCERPT + 1


def test_safe_zone_violation_reported_once_not_per_frame():
    frames = [{"frame": f, "elements": [SZ_BOTTOM]} for f in (45, 146, 247)]
    out = text_audit.summarise(_driver_output(frames), CFG)
    assert len(out) == 1


def test_overlap_and_safe_zone_findings_coexist():
    frames = [{"frame": 45, "elements": [A1, A2, SZ_BOTTOM]}]
    out = text_audit.summarise(_driver_output(frames), CFG)
    assert len(out) == 2
    assert any("Text overlap" in w for w in out)
    assert any("outside the safe zone" in w for w in out)


# ── Settled-window / frame planning ─────────────────────────────────────────

def _scene(start, duration, transition=None, src="s"):
    scene = {"type": "generated", "src": src, "startFrame": start,
             "durationInFrames": duration}
    if transition is not None:
        scene["transitionToNext"] = transition
    return scene


def test_first_scene_has_no_fade_in_but_still_skips_the_entrance():
    """Frame 0 is the worst possible sample — entrance springs make text both
    invisible and displaced there."""
    scenes = [_scene(0, 450)]
    start, end, degenerate = text_audit.settled_window(scenes, 0)
    assert start == text_audit.ENTRANCE_ALLOWANCE_FRAMES
    assert end == 449  # last scene: no fade-out
    assert not degenerate


def test_middle_scene_excludes_default_fades_on_both_sides():
    scenes = [_scene(0, 300), _scene(300, 300), _scene(600, 300)]
    start, end, _ = text_audit.settled_window(scenes, 1)
    # fade-in (8) is smaller than the entrance allowance, so the allowance wins
    assert start == 300 + text_audit.ENTRANCE_ALLOWANCE_FRAMES
    assert end == 599 - text_audit.DEFAULT_FADE_FRAMES


def test_explicit_transition_overrides_the_default_fade():
    scenes = [_scene(0, 300, {"durationInFrames": 12}), _scene(300, 300)]
    start, end, _ = text_audit.settled_window(scenes, 0)
    assert end == 299 - 12


def test_hard_cut_transition_of_zero_removes_the_fade_out():
    scenes = [_scene(0, 300, {"durationInFrames": 0}), _scene(300, 300)]
    _, end, _ = text_audit.settled_window(scenes, 0)
    assert end == 299


def test_long_fade_in_beats_the_entrance_allowance():
    """A previous scene with a very long crossfade pushes the window later than
    the entrance allowance would."""
    scenes = [_scene(0, 300, {"durationInFrames": 90}), _scene(300, 300)]
    start, _, _ = text_audit.settled_window(scenes, 1)
    assert start == 300 + 90


def test_short_scene_degenerates_to_its_midpoint():
    scenes = [_scene(0, 30), _scene(30, 30)]
    start, end, degenerate = text_audit.settled_window(scenes, 0)
    assert degenerate
    assert start == end == 15


def test_plan_passes_spreads_samples_inside_the_window():
    """Several frames per scene, because no single settled frame fits every
    scene type — an ImageFX overlay moves all scene long."""
    scenes = [_scene(0, 450)]
    passes, notes = text_audit.plan_passes({"scenes": scenes})
    assert notes == []
    assert len(passes) == 1
    p = passes[0]
    assert p["count"] == text_audit.SAMPLES_PER_SCENE
    frames = [p["first"] + p["step"] * k for k in range(p["count"])]
    assert frames[0] == 45
    assert frames[-1] <= 449
    assert frames == sorted(set(frames))


def test_plan_passes_never_samples_past_the_window_end():
    """Guards the integer-division arithmetic: a frame past the window sits in
    the fade-out, which is exactly the false positive being avoided."""
    for duration in range(50, 400, 7):
        scenes = [_scene(0, duration), _scene(duration, 300)]
        passes, _ = text_audit.plan_passes({"scenes": scenes})
        _, window_end, _ = text_audit.settled_window(scenes, 0)
        p = passes[0]
        assert p["first"] + p["step"] * (p["count"] - 1) <= window_end, duration


def test_plan_passes_notes_a_scene_too_short_to_settle():
    passes, notes = text_audit.plan_passes({"scenes": [_scene(0, 20)]})
    assert len(passes) == 1
    assert passes[0]["count"] == 1
    assert len(notes) == 1
    assert "too short for a settled window" in notes[0]


def test_plan_passes_covers_every_scene_of_the_real_fixture_video():
    """The Hanuman regression video: 15 scenes, shortest 166 frames with an
    explicit 12-frame transition. Every scene must get a full sample set."""
    scenes = [_scene(0, 444), _scene(444, 473), _scene(917, 573),
              _scene(1490, 613), _scene(2103, 342), _scene(2445, 415),
              _scene(2860, 497), _scene(3357, 166, {"durationInFrames": 12}),
              _scene(3523, 641), _scene(4164, 844), _scene(5008, 645),
              _scene(5653, 452), _scene(6105, 261), _scene(6366, 456),
              _scene(6822, 689)]
    passes, notes = text_audit.plan_passes({"scenes": scenes})
    assert len(passes) == 15
    assert notes == []
    assert all(p["count"] == text_audit.SAMPLES_PER_SCENE for p in passes)


def test_plan_passes_skips_zero_duration_scenes():
    passes, _ = text_audit.plan_passes({"scenes": [_scene(0, 0), _scene(0, 450)]})
    assert [p["scene"] for p in passes] == [1]


def test_plan_passes_handles_textreveal_scenes():
    scenes = [{"type": "TextReveal", "startFrame": 0, "durationInFrames": 450}]
    passes, _ = text_audit.plan_passes({"scenes": scenes})
    assert len(passes) == 1


def test_plan_passes_on_an_empty_config():
    assert text_audit.plan_passes({}) == ([], [])


# ── Reporting ───────────────────────────────────────────────────────────────

def _driver_output(frames, scene=0, errors=None, requested=None):
    return {
        "passes": [{
            "scene": scene,
            "requestedFrames": requested if requested is not None
            else [f["frame"] for f in frames],
            "frames": frames,
        }],
        "errors": errors or [],
    }


CFG = {"scenes": [{"type": "generated", "src": "text-overlap",
                   "startFrame": 0, "durationInFrames": 450}]}


def test_one_warning_per_colliding_pair_not_per_frame():
    """A collision shows up at every sampled frame; reporting it five times
    would bury everything else."""
    frames = [{"frame": f, "elements": FIXTURE_FRAME} for f in (45, 146, 247)]
    out = text_audit.summarise(_driver_output(frames), CFG)
    assert len(out) == 2


def test_warning_names_the_elements_scene_and_coordinates():
    frames = [{"frame": 45, "elements": [A1, A2]}]
    out = text_audit.summarise(_driver_output(frames), CFG)
    assert len(out) == 1
    assert "THE FIRST HEADLINE" in out[0]
    assert "SECOND ONE ON TOP" in out[0]
    assert "text-overlap" in out[0]
    assert "frame 45" in out[0]
    assert "80,394" in out[0]


def test_worst_frame_is_the_one_reported():
    """When a projected overlay drifts, the frame where it is worst is the
    useful one to name."""
    mild = el(1, 80, 460, 900, 89.6, "SECOND ONE ON TOP")
    frames = [
        {"frame": 45, "elements": [A1, mild]},
        {"frame": 146, "elements": [A1, A2]},
    ]
    out = text_audit.summarise(_driver_output(frames), CFG)
    assert len(out) == 1
    assert "frame 146" in out[0]


def test_clean_frames_produce_no_warnings():
    frames = [{"frame": 45, "elements": [C1, C2]}]
    assert text_audit.summarise(_driver_output(frames), CFG) == []


def test_unmeasured_frames_are_reported_as_a_gap():
    """Silence must not be mistaken for "checked and clean"."""
    frames = [{"frame": 45, "elements": []}]
    out = text_audit.summarise(_driver_output(frames, requested=[45, 146]), CFG)
    assert len(out) == 1
    assert "could not measure" in out[0]
    assert "146" in out[0]


def test_driver_errors_are_surfaced():
    out = text_audit.summarise(_driver_output([], errors=["boom"]), CFG)
    assert any("boom" in w for w in out)


# ── Execution, staging and fail-open ────────────────────────────────────────

@pytest.fixture
def job(tmp_path):
    """A staged-able job triplet plus a remotion dir to stage into."""
    jobs = tmp_path / "jobs" / "vid-1"
    (jobs / "images").mkdir(parents=True)
    (jobs / "scene-config.json").write_text(json.dumps(CFG))
    (jobs / "timeline.json").write_text(json.dumps({"totalFrames": 450}))
    (jobs / "audio.mp3").write_bytes(b"\x00" * 100)
    (jobs / "images" / "hero.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    remotion = tmp_path / "remotion"
    (remotion / "audit").mkdir(parents=True)
    (remotion / "audit" / "run-text-layout-audit.mjs").write_text("// stub")
    return jobs, remotion


def _audit(job, **kw):
    jobs, remotion = job
    return text_audit.audit_text_layout(
        "vid-1", CFG, jobs / "scene-config.json", jobs / "timeline.json",
        jobs / "audio.mp3", remotion, **kw)


class FakePopen:
    """Stands in for the node driver.

    `document` is the result JSON, written to the config's outputPath the way the
    real driver does. `stdout` is literal stdout — in a real run that carries
    Remotion's console chatter, NOT the result. Keeping them separate is what
    makes the fallback path testable independently.
    """

    def __init__(self, stdout="", stderr="", returncode=0, timeout=False,
                 document=None):
        self._stdout, self._stderr = stdout, stderr
        self.returncode, self._timeout = returncode, timeout
        self._document = document
        self.pid = 4242
        self.args = ["node"]

    def on_launch(self, config):
        if self._document is not None:
            Path(config["outputPath"]).write_text(self._document)

    def communicate(self, timeout=None):
        if self._timeout:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return self._stdout, self._stderr

    def wait(self):
        return self.returncode


def _patch_driver(monkeypatch, fake):
    def _popen(cmd, *a, **k):
        fake.on_launch(json.loads(cmd[2]))
        return fake

    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(text_audit.subprocess, "Popen", _popen)
    monkeypatch.setattr(text_audit.os, "killpg", lambda *a: None)
    monkeypatch.setattr(text_audit.os, "getpgid", lambda _: 4242)


def test_happy_path_stages_files_and_returns_warnings(job, monkeypatch):
    frames = [{"frame": 45, "elements": [A1, A2]}]
    _patch_driver(monkeypatch, FakePopen(document=json.dumps(_driver_output(frames))))
    out = _audit(job)
    assert len(out) == 1
    assert "Text overlap" in out[0]


def test_staged_public_dir_is_cleaned_up(job, monkeypatch):
    """Left behind, these would accumulate a full copy of every audited video
    inside the api container."""
    jobs, remotion = job
    _patch_driver(monkeypatch, FakePopen(document=json.dumps({"passes": [], "errors": []})))
    _audit(job)
    assert not (remotion / "public" / "vid-1").exists()


def test_images_are_staged_so_img_does_not_abort_the_render(job, monkeypatch):
    """An <Img> whose src doesn't resolve calls cancelRender() after two
    retries, which kills the audit outright rather than degrading."""
    jobs, remotion = job
    seen = {}

    def capture(*a, **k):
        seen["images"] = (remotion / "public" / "vid-1" / "images" / "hero.png").exists()
        seen["config"] = (remotion / "public" / "vid-1" / "scene-config.json").exists()
        return FakePopen(document=json.dumps({"passes": [], "errors": []}))

    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(text_audit.subprocess, "Popen", capture)
    _audit(job)
    assert seen == {"images": True, "config": True}


def test_missing_node_fails_open(job, monkeypatch):
    monkeypatch.setattr(text_audit.shutil, "which", lambda _: None)
    out = _audit(job)
    assert len(out) == 1
    assert "could not run" in out[0]
    assert "node not found" in out[0]


def test_missing_driver_script_fails_open(job, monkeypatch):
    jobs, remotion = job
    (remotion / "audit" / "run-text-layout-audit.mjs").unlink()
    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    out = _audit(job)
    assert len(out) == 1
    assert "audit driver missing" in out[0]


def test_timeout_fails_open_and_kills_the_process_group(job, monkeypatch):
    """A plain subprocess timeout would leave Chromium orphaned."""
    killed = []
    fake = FakePopen(timeout=True)
    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(text_audit.subprocess, "Popen", lambda *a, **k: fake)
    monkeypatch.setattr(text_audit.os, "getpgid", lambda _: 4242)
    monkeypatch.setattr(text_audit.os, "killpg", lambda pgid, sig: killed.append((pgid, sig)))
    out = _audit(job)
    assert killed == [(4242, text_audit.signal.SIGKILL)]
    assert "timed out" in out[0]


def test_unparseable_output_fails_open(job, monkeypatch):
    _patch_driver(monkeypatch, FakePopen(document="not json at all"))
    out = _audit(job)
    assert "not JSON" in out[0]


def test_console_chatter_with_no_document_fails_open_on_the_stderr_tail(job, monkeypatch):
    """The shape of the bug the first real in-container run hit: Remotion floods
    stdout and the result never lands. Reported as the stderr tail, not as a
    misleading JSON-parse error."""
    _patch_driver(monkeypatch, FakePopen(stdout=PROBE_NOISE, stderr="EACCES: denied",
                                         returncode=1))
    out = _audit(job)
    assert "could not run" in out[0]
    assert "EACCES: denied" in out[0]


def test_no_output_reports_the_drivers_stderr_tail(job, monkeypatch):
    _patch_driver(monkeypatch, FakePopen(stdout="", stderr="line one\nEACCES: denied",
                                        returncode=1))
    out = _audit(job)
    assert "EACCES: denied" in out[0]


def test_staging_failure_fails_open(job, monkeypatch):
    jobs, _ = job
    (jobs / "audio.mp3").unlink()
    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    out = _audit(job)
    assert len(out) == 1
    assert "could not run" in out[0]


def test_a_second_concurrent_audit_of_one_video_is_skipped(job, monkeypatch):
    """Both would stage into the same public dir and one would delete it from
    under the other. validate_job is deliberately not under the scene claim."""
    jobs, remotion = job
    inner = {}

    def reentrant(*a, **k):
        inner["result"] = _audit(job)
        return FakePopen(document=json.dumps({"passes": [], "errors": []}))

    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(text_audit.subprocess, "Popen", reentrant)
    _audit(job)
    assert len(inner["result"]) == 1
    assert "already running" in inner["result"][0]


def test_the_in_progress_marker_is_always_released(job, monkeypatch):
    monkeypatch.setattr(text_audit.shutil, "which", lambda _: None)
    _audit(job)
    assert "vid-1" not in text_audit._audits_in_progress


def test_scenes_with_no_passes_skip_the_subprocess_entirely(job, monkeypatch):
    """Nothing to sample means nothing to render — don't pay for a bundle."""
    jobs, remotion = job
    called = []
    monkeypatch.setattr(text_audit.shutil, "which", lambda _: "/usr/bin/node")
    monkeypatch.setattr(text_audit.subprocess, "Popen",
                        lambda *a, **k: called.append(1) or FakePopen())
    out = text_audit.audit_text_layout(
        "vid-1", {"scenes": []}, jobs / "scene-config.json",
        jobs / "timeline.json", jobs / "audio.mp3", remotion)
    assert called == []
    assert out == []


# ── validate_job's contract ────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()

    def make_video(video_id, **paths):
        with server._conn() as con:
            con.execute(
                """INSERT INTO videos (id, topic, voice_file_path, timeline_path,
                                       scene_config_path, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (video_id, "t", paths.get("audio", ""), paths.get("timeline", ""),
                 paths.get("config", ""), _now(), _now()),
            )

    return make_video


def test_unknown_video_still_carries_a_warnings_key(db):
    """Callers can read result["warnings"] unconditionally."""
    result = server.validate_job("nope")
    assert result["passed"] is False
    assert result["warnings"] == []


def test_missing_job_files_still_carry_a_warnings_key(db):
    db("vid-1")
    result = server.validate_job("vid-1")
    assert result["passed"] is False
    assert result["warnings"] == []
    assert any("Missing" in e for e in result["errors"])


def test_audit_is_skipped_when_the_setting_is_off(db, tmp_path, monkeypatch):
    """The kill switch has to actually stop the subprocess, not just hide
    output."""
    called = []
    monkeypatch.setattr(server, "_get_setting", lambda k, d="": "false" if k == "text_layout_audit_enabled" else d)
    monkeypatch.setattr(text_audit, "audit_text_layout", lambda *a, **k: called.append(1) or [])
    db("vid-1")
    server.validate_job("vid-1")
    assert called == []
