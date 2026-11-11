"""tubematic_core/mascots.py: what makes a mascot pickable, where its code and
sheets live, and the checks on the cue track the per-video agent writes.

The cue track is data the agent authors, so cue_errors is the only thing
between a bad cue and a mascot standing over the captions or off the safe
zone in a finished video. The geometry tests use the engine's real box
(560x640 canvas, feet 50 above its bottom) rather than invented numbers.
"""
import pathlib
import re
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import jobfiles, mascots  # noqa: E402

TOTAL = 900
ON = {"frame": 0, "on": True, "x": 0.5, "y": 0.5, "emotion": "happy"}


def _errs(cues, total=TOTAL, subtitles=None):
    return mascots.cue_errors(cues, total, subtitles)


def _con():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE mascots (id TEXT PRIMARY KEY, builtin INT DEFAULT 0, approved_version INT DEFAULT 0, "
                "archived INT DEFAULT 0)")
    con.execute("CREATE TABLE mascot_versions (mascot_id TEXT, version INT, code TEXT DEFAULT '')")
    return con


# ---------- constants ----------

def test_constants_match_the_design():
    assert mascots.MASCOT_STATUSES == ("PENDING", "BUILDING", "IN_REVIEW", "READY", "FAILED")
    assert mascots.MAX_MASCOT_ATTEMPTS == 2
    assert mascots.MAX_SHEET_RENDERS_PER_ATTEMPT == 6
    assert mascots.SHEETS == ("turn", "feels", "act")


def test_emotions_equal_the_sheet_engine_feels():
    sheet_js = pathlib.Path(__file__).resolve().parents[2] / "renderer/remotion/public/mascot/sheet.js"
    m = re.search(r"const names = \[([^\]]+)\]", sheet_js.read_text())
    names = tuple(re.findall(r"'([a-z]+)'", m.group(1)))
    assert mascots.EMOTIONS == names


# ---------- pickable / resolve_default ----------

def test_pickable():
    assert mascots.pickable({"approved_version": 1, "archived": 0})
    assert not mascots.pickable({"approved_version": 0, "archived": 0})
    assert not mascots.pickable({"approved_version": 2, "archived": 1})


def test_holds_pickable_sql_agrees_with_pickable():
    con = _con()
    con.executemany("INSERT INTO mascots (id, approved_version, archived) VALUES (?, ?, ?)",
                    [("ok", 1, 0), ("wip", 0, 0), ("gone", 2, 1)])
    con.execute("CREATE TABLE videos (id TEXT, mascot_id TEXT)")
    con.executemany("INSERT INTO videos VALUES (?, ?)",
                    [("a", ""), ("b", "ok"), ("c", "wip"), ("d", "gone"), ("e", "ghost"), ("f", None)])
    held = {r[0] for r in con.execute(f"SELECT id FROM videos WHERE {mascots.holds_pickable_sql()}")}
    assert held == {"a", "b", "f"}
    bound = mascots.holds_pickable_sql("?")
    assert [con.execute(f"SELECT {bound}", (m, m)).fetchone()[0] for m in ("", "ok", "gone")] == [1, 1, 0]


def test_cartoon_mascot_clash_sql_names_only_the_pair_the_renderer_refuses():
    con = _con()
    con.execute("CREATE TABLE videos (id TEXT, visual_style TEXT, resolved_renderer TEXT, mascot_id TEXT)")
    con.executemany("INSERT INTO videos VALUES (?, ?, ?, ?)",
                    [("a", "cartoon_3d", "", "moss"), ("b", "auto", "cartoon_3d", "moss"),
                     ("c", "cartoon_3d", "", ""), ("d", "auto", "dom", "moss"), ("e", None, None, None)])
    clash = {r[0] for r in con.execute(f"SELECT id FROM videos WHERE {mascots.cartoon_mascot_clash_sql()}")}
    assert clash == {"a", "b"}
    bound = mascots.cartoon_mascot_clash_sql("?", "?", "?")
    assert con.execute(f"SELECT {bound}", ("cartoon_3d", "", "moss")).fetchone()[0] == 1
    assert con.execute(f"SELECT {bound}", ("cartoon_3d", "", "")).fetchone()[0] == 0
    # a pack that takes no mascot is in the pair too (TMDEV-201)
    assert con.execute(f"SELECT {bound}", ("under_the_hood", "", "moss")).fetchone()[0] == 1
    assert con.execute(f"SELECT {bound}", ("bean_explainer", "", "moss")).fetchone()[0] == 0


def test_no_mascot_error_names_each_style_that_takes_none():
    assert mascots.no_mascot_error("cartoon_3d") == mascots.MASCOT_NOT_ON_CARTOON_3D
    assert "presenter" in mascots.no_mascot_error("under_the_hood")
    assert mascots.no_mascot_error("stick") == mascots.no_mascot_error("") == mascots.no_mascot_error("auto") == ""


def test_resolve_default_none_empty_and_unpickable():
    con = _con()
    con.execute("INSERT INTO mascots (id, approved_version, archived) VALUES ('ok', 1, 0), ('arch', 1, 1), ('new', 0, 0)")
    r = mascots.resolve_default
    assert r(con, "none", "ok") == ""            # 'none' beats the install default
    assert r(con, "", "ok") == "ok"              # '' inherits
    assert r(con, "ok", "") == "ok"              # the project's own wins
    assert r(con, "", "") == ""
    assert r(con, "arch", "ok") == ""            # archived: dropped, not replaced by the install default
    assert r(con, "new", "") == ""               # never approved
    assert r(con, "", "arch") == ""
    assert r(con, "ghost", "") == ""             # no such row


# ---------- code_for ----------

def test_code_for_user_mascot_reads_the_db(tmp_path):
    con = _con()
    con.execute("INSERT INTO mascots (id, builtin) VALUES ('moss', 0)")
    con.execute("INSERT INTO mascot_versions VALUES ('moss', 1, 'CODE1'), ('moss', 2, '')")
    assert mascots.code_for(con, tmp_path, "moss", 1) == "CODE1"
    with pytest.raises(mascots.MascotError):
        mascots.code_for(con, tmp_path, "moss", 2)      # empty
    with pytest.raises(mascots.MascotError):
        mascots.code_for(con, tmp_path, "moss", 9)      # missing
    with pytest.raises(mascots.MascotError):
        mascots.code_for(con, tmp_path, "ghost", 1)     # no mascot


def test_code_for_builtin_reads_the_versioned_file_not_the_db(tmp_path):
    con = _con()
    con.execute("INSERT INTO mascots (id, builtin) VALUES ('tubi', 1)")
    con.execute("INSERT INTO mascot_versions VALUES ('tubi', 1, '')")
    d = mascots.builtin_dir(tmp_path, "tubi", 1)
    assert d == tmp_path / "mascot-builtin" / "tubi" / "v1"
    d.mkdir(parents=True)
    (d / "mascot.js").write_text("TUBI")
    assert mascots.code_for(con, tmp_path, "tubi", 1) == "TUBI"
    with pytest.raises(mascots.MascotError):
        mascots.code_for(con, tmp_path, "tubi", 2)      # no file for v2


def test_paths_are_validated(tmp_path):
    assert mascots.sheet_file(tmp_path, "moss", 3, "feels") == tmp_path / "mascots" / "moss" / "v3" / "feels.png"
    for bad_id in ("../x", "A b", "", "a/b", "."):
        with pytest.raises(mascots.MascotError):
            mascots.sheet_file(tmp_path, bad_id, 1, "turn")
        with pytest.raises(mascots.MascotError):
            mascots.builtin_dir(tmp_path, bad_id, 1)
    with pytest.raises(mascots.MascotError):
        mascots.sheet_file(tmp_path, "moss", 1, "../turn")
    with pytest.raises(mascots.MascotError):
        mascots.sheet_file(tmp_path, "moss", 0, "turn")
    with pytest.raises(mascots.MascotError):
        mascots.builtin_dir(tmp_path, "tubi", True)


def test_a_symlink_below_the_root_is_refused(tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "mascots").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(jobfiles.UnsafePath):
        mascots.sheet_file(tmp_path, "moss", 1, "turn")


# ---------- GPU gate ----------

def test_mascot_gpu_error():
    assert mascots.mascot_gpu_error("working") == ""
    assert mascots.mascot_gpu_error("unknown") == mascots.MASCOT_GPU_UNKNOWN
    for s in ("not_configured", "not_usable", "", "anything"):
        assert mascots.mascot_gpu_error(s) == mascots.MASCOT_NEEDS_GPU
    assert "Test GPU" in mascots.MASCOT_GPU_UNKNOWN and "--step gpu" in mascots.MASCOT_NEEDS_GPU
    assert "Mascots" in mascots.MASCOT_NEEDS_GPU


# ---------- geometry ----------

def test_box_at_is_the_engine_canvas_around_the_feet():
    x0, y0, x1, y1 = mascots.box_at({"x": 0.5, "y": 0.5, "scale": 1})
    assert (x0, x1) == (540 - 280, 540 + 280)
    assert (y0, y1) == (960 - 590, 960 + 50)
    big = mascots.box_at({"x": 0.5, "y": 0.5, "scale": 2})
    assert big[2] - big[0] == 1120 and big[3] - big[1] == 1280
    assert mascots.box_at({"x": 0.5, "y": 0.5}) == (x0, y0, x1, y1)   # scale defaults to 1


def test_caption_band_defaults_and_moves_with_the_subtitles():
    y0, y1 = mascots.caption_band(None)
    centre = 0.78 * 1920
    assert y0 < centre < y1
    assert (y1 - y0) / 2 >= 62 * 1.15 + 14          # two lines, plus padding
    assert mascots.caption_band({"enabled": False}) is None
    assert mascots.caption_band({"enabled": True}) == (y0, y1)
    moved = mascots.caption_band({"position": 0.3, "fontSize": 100})
    assert moved[0] < 0.3 * 1920 < moved[1] and (moved[1] - moved[0]) > (y1 - y0)


def test_caption_band_covers_the_worst_case_line_count():
    y0, y1 = mascots.caption_band({"position": 0.78, "fontSize": 120, "maxWords": 7})
    # real captions at 120/7 wrap to 3-4 lines and span about y1208-1788
    assert y0 <= 1208 and y1 >= 1788
    # the default config is unchanged: two lines
    d0, d1 = mascots.caption_band(None)
    assert (d0, d1) == mascots.caption_band({"maxWords": 4, "fontSize": 62})
    assert (d1 - d0) / 2 == pytest.approx(2 * 62 * 1.15 / 2 + 14 + 40)


# ---------- cue_errors ----------

def test_a_valid_track_passes():
    cues = [{"frame": 0, "on": True, "x": 0.5, "y": 0.5, "emotion": "happy"},
            {"frame": 120, "emotion": "surprised", "jump": True, "look": "up", "facing": "left"},
            {"frame": 300, "x": 0.6, "y": 0.5}]
    assert _errs(cues) == []


def test_not_a_list_or_a_cue_not_an_object():
    assert _errs("x") and _errs([1]) and _errs({})


def test_unknown_keys_and_values_are_refused_naming_the_frame():
    assert "talk" in " ".join(_errs([ON, {"frame": 10, "talk": True}]))
    assert "frame 10" in " ".join(_errs([ON, {"frame": 10, "emotion": "furious"}]))
    assert _errs([ON, {"frame": 10, "look": "diagonal"}])
    assert _errs([ON, {"frame": 10, "facing": "back"}])
    assert _errs([ON, {"frame": 10, "jump": "yes"}])
    assert _errs([{**ON, "on": "yes"}])


def test_frame_bounds_and_duplicates():
    assert _errs([ON, {"frame": TOTAL}])                       # frame >= totalFrames
    assert _errs([ON, {"frame": -1}])
    assert _errs([ON, {"frame": 1.5}])
    assert _errs([ON, {"frame": True}])
    assert _errs([ON, {"frame": 0, "emotion": "sad"}])         # two cues on one frame
    assert _errs([ON, {"frame": 50}, {"frame": 20}]) == []     # unsorted is fine: the engine sorts


def test_numeric_bounds():
    for bad in ({"x": -0.1}, {"x": 1.1}, {"y": 2}, {"scale": 0.1}, {"scale": 5}, {"x": "0.5"}, {"x": True}):
        assert _errs([ON, {"frame": 10, **bad}]), bad


def test_must_come_on_screen():
    assert any("on screen" in e for e in _errs([{"frame": 0, "emotion": "happy"}]))
    assert any("on screen" in e for e in _errs([]))


def test_total_frames_must_be_positive():
    assert _errs([ON], total=0)


def test_box_outside_the_safe_zone_is_refused():
    assert _errs([{**ON, "x": 0.05}])        # left edge
    assert _errs([{**ON, "y": 0.1}])         # top of the box above y 150
    assert _errs([{**ON, "y": 0.95}])        # below y 1750
    assert _errs([{**ON, "x": 0.5, "y": 0.5}]) == []


def test_box_over_the_caption_band_is_refused_and_a_hidden_band_frees_it():
    low = {**ON, "y": 0.72, "scale": 0.5}
    y1 = mascots.box_at({"x": .5, "y": .72, "scale": .5})[3]
    band = mascots.caption_band(None)
    assert y1 > band[0]                                  # setup: it really overlaps
    assert any("caption" in e for e in _errs([low]))
    assert _errs([low], subtitles={"enabled": False}) == []
    # moving the band out of the way frees it
    assert _errs([low], subtitles={"position": 0.9}) == []


def test_a_walk_whose_path_crosses_the_band_is_refused_though_both_ends_are_clear():
    # one end is above the band and the other below it: both rests are clear, the walk between them is not
    band = mascots.caption_band({"position": 0.5, "fontSize": 62})
    top = {"frame": 0, "on": True, "x": 0.5, "y": 0.3, "scale": 0.4}
    bottom = {"frame": 100, "x": 0.5, "y": 0.8, "scale": 0.4}
    assert mascots.box_at({"x": .5, "y": .3, "scale": .4})[3] < band[0]
    assert mascots.box_at({"x": .5, "y": .8, "scale": .4})[1] > band[1]
    errs = _errs([top, bottom], subtitles={"position": 0.5})
    assert any("frame 100" in e and "caption" in e for e in errs)


def test_one_bad_walk_is_reported_once_per_kind_and_stays_short():
    cues = [{"frame": 0, "on": True, "x": .3, "y": .5, "scale": .4}, {"frame": 60, "x": .5, "scale": 1.2}]
    errs = _errs(cues)
    assert len([e for e in errs if "frame 60" in e and "safe zone" in e]) == 1
    assert sum(len(e) for e in errs) < 1500
    rest = _errs([{"frame": 0, "on": True, "x": .02, "y": .5}])
    assert len([e for e in rest if "safe zone" in e]) == 1


def test_a_walk_between_clear_positions_on_one_side_passes():
    a = {"frame": 0, "on": True, "x": 0.4, "y": 0.4, "scale": 0.8}
    b = {"frame": 100, "x": 0.65, "y": 0.45}
    assert _errs([a, b]) == []


def test_walk_on_and_off_at_a_valid_height_pass():
    cues = [{"frame": 30, "on": True, "x": 0.5, "y": 0.5},
            {"frame": 400, "on": False}]
    assert _errs(cues) == []


def test_walk_on_at_a_height_that_hits_the_band_is_refused():
    errs = _errs([{"frame": 30, "on": True, "x": 0.5, "y": 0.75, "scale": 0.5}])
    assert any("frame 30" in e for e in errs)


def test_a_scale_jump_during_a_walk_that_leaves_the_safe_zone_is_refused():
    cues = [{"frame": 0, "on": True, "x": .3, "y": .5, "scale": .4}, {"frame": 60, "x": .5, "scale": 1.2}]
    assert any("frame 60" in e and "safe zone" in e for e in _errs(cues))


def test_coming_on_screen_means_standing_in_view_not_just_an_on_cue():
    assert _errs([{"frame": 299, "on": True, "x": .5, "y": .5}], total=300)
    assert _errs([{"frame": 0, "on": True, "x": .5, "y": .5}], total=300) == []
    assert _errs([{"frame": 0, "on": True, "x": .5, "y": .5}], total=30)   # walk-on eats the whole video


def test_the_second_in_view_must_be_one_unbroken_stretch_not_a_sum():
    # The walk-on from x 0.5 ends at frame 80.6, so this stands still for frames 81-95 and,
    # after a 15-frame step, 111-125: 30 frames at rest in all, never 30 in a row.
    split = [{"frame": 0, "on": True, "x": .5, "y": .5}, {"frame": 96, "x": .55}, {"frame": 126, "on": False}]
    errs = _errs(split)
    assert any("not on screen long enough" in e and "in a row" in e for e in errs)
    # standing still for frames 81-110, then walking off: exactly one unbroken second
    assert _errs([{"frame": 0, "on": True, "x": .5, "y": .5}, {"frame": 111, "on": False}]) == []
    assert _errs([{"frame": 0, "on": True, "x": .5, "y": .5}, {"frame": 110, "on": False}])


def test_errors_name_the_cue_that_caused_them_not_a_later_one():
    rest = [{"frame": 0, "on": True, "x": .5, "y": .5}, {"frame": 30, "y": .2, "scale": .4}]
    base = _errs(rest + [{"frame": 40, "emotion": "sad"}])
    plain = _errs(rest)
    assert base == plain
    cross = [{"frame": 0, "on": True, "x": 0.5, "y": 0.3, "scale": 0.4}, {"frame": 100, "x": 0.5, "y": 0.8}]
    errs = _errs(cross + [{"frame": 110, "emotion": "sad"}], subtitles={"position": 0.5})
    assert errs and all("frame 100" in e and "110" not in e for e in errs)
    bad = _errs([{"frame": 0, "on": True, "x": .5, "y": .5}, {"frame": 30, "y": .72, "scale": .5},
                 {"frame": 40, "emotion": "sad"}])
    assert bad and all("frame 30" in e for e in bad) and not any("frame 40" in e for e in bad)


def test_an_edge_walk_message_does_not_advise_staying_on_one_side():
    errs = _errs([{"frame": 30, "on": True, "x": 0.5, "y": 0.75, "scale": 0.5}])
    walk = [e for e in errs if "walk" in e]
    assert walk and all("same side" not in e for e in walk)


# ---------- agreement with the other copies ----------

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _read(rel):
    return (ROOT / rel).read_text()


def test_safe_zone_matches_text_audit():
    m = re.search(r"^SAFE_ZONE = (\{[^}]*\})", _read("mcp/text_audit.py"), re.M)
    assert eval(m.group(1)) == mascots.SAFE_ZONE
    assert re.search(r"^FRAME_WIDTH = 1080$", _read("mcp/text_audit.py"), re.M)
    assert re.search(r"^FRAME_HEIGHT = 1920$", _read("mcp/text_audit.py"), re.M)
    assert (mascots.FRAME_WIDTH, mascots.FRAME_HEIGHT) == (1080, 1920)


def test_fps_matches_root_and_mcp():
    assert int(re.search(r"^FPS\s*=\s*(\d+)", _read("mcp/server.py"), re.M).group(1)) == mascots.FPS
    assert {int(n) for n in re.findall(r"fps=\{(\d+)\}", _read("renderer/remotion/src/Root.tsx"))} == {mascots.FPS}


def test_box_and_walk_constants_match_the_engine():
    frame = _read("renderer/remotion/public/mascot/frame.html")
    assert re.search(r"window\.KIT_W = SHEET \? \d+ : %d;" % mascots.BOX_W, frame)
    assert re.search(r"window\.KIT_H = SHEET \? \d+ : %d;" % mascots.BOX_H, frame)
    drv = _read("renderer/remotion/public/mascot/driver.js")
    assert re.search(r"FEET_Y = H - %d\b" % (mascots.BOX_H - mascots.FEET_Y), drv)
    assert int(re.search(r"WALK_PX_PER_S = (\d+)", drv).group(1)) == mascots.WALK_PX_PER_S
    assert re.search(r"clamp\(d / WALK_PX_PER_S, \.5, 3\.2\)", drv)
    assert (mascots.WALK_MIN_S, mascots.WALK_MAX_S) == (0.5, 3.2)
    assert re.search(r"EDGE_PX = W / 2 \+ 40\b", drv) and mascots.EDGE_PX == mascots.BOX_W / 2 + 40
    d = re.search(r"const st = \{ x: \.8, y: \.96, scale: 1,", drv)
    assert d and (mascots.DEFAULT_STATE["x"], mascots.DEFAULT_STATE["y"]) == (.8, .96)


def test_subtitle_defaults_match_subtitles_tsx():
    src = _read("renderer/remotion/src/scenes/installed/Subtitles.tsx")
    assert float(re.search(r"position = ([\d.]+),", src).group(1)) == mascots.SUBTITLE_POSITION
    assert int(re.search(r"fontSize = (\d+),", src).group(1)) == mascots.SUBTITLE_FONT_SIZE
    assert float(re.search(r"lineHeight: ([\d.]+),", src).group(1)) == mascots.SUBTITLE_LINE_HEIGHT
    assert int(re.search(r'padding: "(\d+)px \d+px"', src).group(1)) == mascots.SUBTITLE_PAD_Y


# ---------- boxes_at_frames (the audit's view of where the mascot stands) ----------

def test_boxes_at_frames_is_none_until_the_mascot_is_on_and_the_rest_box_after_the_walk():
    cues = [{"frame": 30, "on": True, "x": 0.5, "y": 0.5}]
    boxes = mascots.boxes_at_frames(cues, [0, 29, 600])
    assert boxes[0] is None and boxes[29] is None
    assert boxes[600] == mascots.box_at({"x": 0.5, "y": 0.5, "scale": 1.0})


def test_boxes_at_frames_follows_the_walk_and_hides_the_mascot_after_it_leaves():
    cues = [{"frame": 0, "on": True, "x": 0.5, "y": 0.5}, {"frame": 300, "on": False}]
    mid = mascots.boxes_at_frames(cues, [310, 899])
    assert mid[310] is not None and mid[310] != mascots.box_at({"x": 0.5, "y": 0.5})
    assert mid[899] is None


def test_boxes_at_frames_applies_the_cue_scale():
    cues = [{"frame": 0, "on": True, "x": 0.5, "y": 0.5, "scale": 0.5}]
    box = mascots.boxes_at_frames(cues, [800])[800]
    assert box == mascots.box_at({"x": 0.5, "y": 0.5, "scale": 0.5})
