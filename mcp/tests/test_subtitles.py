"""Tests for burned-in subtitles (TMDEV-101) as write_scene_config sees them.

Subtitles are drawn by the renderer from the narration's own word timings, so
the only thing reachable from Python is the config block that configures them.
The chunking and the on-screen layout live in
renderer/remotion/src/scenes/installed/Subtitles.tsx and have no test runner to
reach them — same position as every other installed component.

What is worth pinning here is the default and the ceiling. The default is
"on when the key is absent", which is the only reason the feature reaches a
video whose config was written by a skill from before it existed. The ceiling
is 7 words, which is the control's entire purpose.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
import pathlib
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make_video(video_id="vid_sub", status="VOICE_READY"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?, ?)",
                (video_id, "t", status, _now(), _now()),
            )
        return video_id

    return make_video


def _config(subtitles=...):
    cfg = {
        "totalFrames": 300,
        "fps": 30,
        "scenes": [{"type": "generated", "src": "s", "startFrame": 0,
                    "durationInFrames": 300}],
        "sfx": [],
    }
    if subtitles is not ...:
        cfg["subtitles"] = subtitles
    return cfg


def _written(video_id):
    return json.loads((server.JOBS_DIR / video_id / "scene-config.json").read_text())


# ── The default ─────────────────────────────────────────────────────────────

def test_an_absent_subtitles_key_means_subtitles_are_on(job_db):
    """The whole point of the default. A config from an older skill carries no
    subtitles key at all, and must still come out captioned."""
    vid = job_db()
    assert server.write_scene_config(vid, _config())["subtitles_enabled"] is True


def test_an_absent_key_is_not_filled_in(job_db):
    """Deliberately NOT written into the file. Materialising the defaults would
    freeze them at whatever they were the day the config was authored, so a
    later change to a default would reach new videos only."""
    vid = job_db()
    server.write_scene_config(vid, _config())
    assert "subtitles" not in _written(vid)


def test_opting_out_is_explicit_and_round_trips(job_db):
    vid = job_db()
    out = server.write_scene_config(vid, _config({"enabled": False}))
    assert out["subtitles_enabled"] is False
    assert _written(vid)["subtitles"] == {"enabled": False}


def test_a_full_block_is_stored_verbatim(job_db):
    vid = job_db()
    block = {"enabled": True, "maxWords": 3, "fontFamily": "Oswald",
             "fontSize": 70, "color": "#ffcc00", "background": "shadow",
             "position": 0.8, "uppercase": True}
    server.write_scene_config(vid, _config(block))
    assert _written(vid)["subtitles"] == block


# ── The ceiling ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [1, 4, 7])
def test_the_whole_permitted_word_range_is_accepted(job_db, n):
    vid = job_db()
    assert "error" not in server.write_scene_config(vid, _config({"maxWords": n}))


@pytest.mark.parametrize("n", [0, 8, 25])
def test_a_word_count_outside_one_to_seven_is_rejected(job_db, n):
    """Seven is the readable ceiling at speaking speed; clamping silently would
    hide the fact that the request was impossible."""
    vid = job_db()
    err = server.write_scene_config(vid, _config({"maxWords": n}))["error"]
    assert "maxWords" in err and "1" in err and "7" in err


def test_a_fractional_word_count_is_rejected(job_db):
    vid = job_db()
    assert "whole number" in server.write_scene_config(
        vid, _config({"maxWords": 3.5}))["error"]


def test_true_is_not_a_word_count(job_db):
    """bool is an int in Python, so True would otherwise pass as 1."""
    vid = job_db()
    assert "error" in server.write_scene_config(vid, _config({"maxWords": True}))


# ── Everything else ─────────────────────────────────────────────────────────

def test_an_unknown_key_is_rejected_rather_than_dropped(job_db):
    """A silently ignored typo shows up only as a caption that does not look
    the way it was asked to — after a render."""
    vid = job_db()
    err = server.write_scene_config(vid, _config({"fontWeight": 900}))["error"]
    assert "fontWeight" in err


def test_a_non_object_subtitles_block_is_rejected(job_db):
    vid = job_db()
    assert "error" in server.write_scene_config(vid, _config(True))


def test_an_unknown_background_is_rejected(job_db):
    vid = job_db()
    err = server.write_scene_config(vid, _config({"background": "box"}))["error"]
    assert "pill" in err and "shadow" in err


def test_null_colour_is_allowed_and_means_follow_the_canvas(job_db):
    vid = job_db()
    assert "error" not in server.write_scene_config(vid, _config({"color": None}))


def test_an_empty_colour_or_font_is_rejected(job_db):
    vid = job_db()
    assert "error" in server.write_scene_config(vid, _config({"color": "  "}))
    assert "error" in server.write_scene_config(vid, _config({"fontFamily": ""}))


@pytest.mark.parametrize("pos", [0.0, 1.0])
def test_a_position_off_the_frame_is_rejected(job_db, pos):
    vid = job_db()
    assert "error" in server.write_scene_config(vid, _config({"position": pos}))


def test_a_rejected_block_writes_nothing(job_db):
    """Same contract as every other validation failure here."""
    vid = job_db()
    assert "error" in server.write_scene_config(vid, _config({"maxWords": 99}))
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


# ── Source guards for Subtitles.tsx (review follow-up) ──────────────────────
#
# renderer/remotion/ has no JS test runner, so the caption component's own
# behaviour cannot be asserted from pytest. These guard the two decisions that
# a later edit would most plausibly undo, and both were verified behaviourally
# at the time by bundling the real module with esbuild and executing it against
# synthetic word timings — that check is not committed because it needs Node 22
# under nvm, which no other test in this repo requires.

def _subtitles_src() -> str:
    return (pathlib.Path(server.__file__).resolve().parents[1] / "renderer" /
            "remotion" / "src" / "scenes" / "installed" / "Subtitles.tsx").read_text()


def test_a_caption_does_not_hold_forever_through_a_silence():
    """A chunk holds until the next one starts, which is right for the gap
    between clauses and wrong for a deliberate pause: a <break time="1.5s"/>
    left the previous words on screen for the better part of two seconds with
    nothing being said. The cap is what bounds that, and removing it looks
    like a simplification."""
    src = _subtitles_src()
    assert "MAX_HOLD_FRAMES" in src
    # The cap must combine with the next chunk's start, not replace it —
    # taking the cap alone would reintroduce the flicker the hold prevents.
    assert "Math.min(next[0].startFrame, held)" in src


def test_every_webfont_is_pinned_to_one_weight_and_subset_list():
    """A bare loader fetches every style, weight and subset a family
    publishes, and throws outright on Remotion v5. Since this component renders
    on every video, an unpinned loader turns a Remotion upgrade into a
    pipeline-wide render failure."""
    src = _subtitles_src()
    for family in ("loadInter", "loadOswald", "loadRoboto", "loadMontserrat"):
        call = src[src.index(f"{family}(\"normal\""):]
        head = call[:call.index(")") + 1]
        assert "weights:" in head and "subsets:" in head, family


def test_oswald_is_loaded_at_700_not_800():
    """Oswald's heaviest published weight is 700. Asking a family for a weight
    it does not publish RAISES, so unifying the four families on one weight —
    the obvious tidy-up — breaks this option outright rather than degrading
    it."""
    src = _subtitles_src()
    call = src[src.index('loadOswald("normal"'):]
    assert '"700"' in call[:call.index(")") + 1]


def test_the_default_font_is_not_a_webfont():
    """Subtitles are on by default, so their default font is on the critical
    path of every render. A Google font is fetched from the network by the
    render browser; the container-local family is the one proven to resolve
    there. Changing this default turns a cosmetic choice into an egress
    dependency for the whole pipeline."""
    src = (pathlib.Path(server.__file__).resolve().parents[1] / "renderer" /
           "remotion" / "src" / "scenes" / "installed" / "Subtitles.tsx").read_text()
    assert 'const DEFAULT_FONT = "system-ui, sans-serif";' in src
    assert "fontFamily = DEFAULT_FONT," in src

