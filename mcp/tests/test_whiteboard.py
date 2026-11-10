"""Whiteboard (TMDEV-197): the scene-config checks that keep an unattended agent
from shipping a board whose writing does not fit, collides or cannot keep up
with the narration, their agreement with the renderer's whiteboard/*.ts, and
their place in write_scene_config and the text audit.

Every refusal below is one the renderer cannot survive gracefully: text wider
than its slot runs into the next slot, an arrow through other writing is
unreadable, a marker given less than its floor scribbles, an item drawn as the
camera leaves is never seen, and a long stretch with nothing new is the static
frame viewers scroll past.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import server
import text_audit
import whiteboard as wb
import doodle_preview
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
TS_DIR = REPO / "renderer/remotion/src/scenes/installed/whiteboard"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/whiteboard_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-whiteboard/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
DOODLES = tvs.pack("whiteboard")["extra"]["doodles"]


def _ts_object(name: str) -> dict:
    src = (TS_DIR / "contract.ts").read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\n\}}", src, re.S).group(1)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"^\s*(\w+):\s*([\d.]+),", body, re.M)}


# ── agreement with the renderer ──────────────────────────────────────────────

@pytest.mark.parametrize("name", ["BOARD", "SIZES", "LIMITS", "TIMING", "SPEED", "FLOOR"])
def test_the_constants_match_the_renderer(name):
    assert _ts_object(name) == getattr(wb, name)


def test_the_layouts_match_the_renderer():
    src = (TS_DIR / "contract.ts").read_text()
    body = src[src.index("export const LAYOUTS"):src.index("export const INKS")]
    ts = {}
    for layout, block in re.findall(r"^  (\w+): \{(.*?)^  \},", body, re.M | re.S):
        ts[layout] = {k: tuple(int(v) for v in vals.split(", "))
                      for k, vals in re.findall(r'^\s+"?(\w+)"?: \[([\d, ]+)\],', block, re.M)}
    assert ts == wb.LAYOUTS


def test_the_inks_and_kinds_match_the_renderer():
    src = (TS_DIR / "contract.ts").read_text()
    inks = dict(re.findall(r'^  (\w+): "(#[0-9a-f]{6})",', src[src.index("export const INKS"):], re.M)[:3])
    assert inks == wb.INKS
    marks = re.search(r"export const MARKS = \[(.*?)\] as const;", src).group(1)
    assert tuple(re.findall(r'"(\w+)"', marks)) == wb.MARKS


def test_the_glyph_widths_match_the_renderer():
    """Both sides wrap and centre text with these widths; a drift would let
    the validator pass text the board cannot fit."""
    src = (TS_DIR / "glyphs.ts").read_text()
    body = src[src.index("{") + 1:src.rindex("}")]
    ts = {json.loads(k): float(v) for k, v in re.findall(r'^\s+("(?:[^"\\]|\\.)*"): ([\d.]+),', body, re.M)}
    assert ts == wb.GLYPH_EM


def test_the_layout_helpers_mirror_layout_ts():
    """The functions the validator copies from layout.ts and schedule.ts."""
    src = (TS_DIR / "layout.ts").read_text() + (TS_DIR / "schedule.ts").read_text()
    for fn in ("regionOrigin", "placeItem", "fitProblem", "arrowEnds", "segmentHitsRect", "textLineCap", "schedule"):
        assert f"function {fn}(" in src, fn
    for name, value in (("DOODLE_MAX", wb.DOODLE_MAX), ("DOODLE_MIN", wb.DOODLE_MIN),
                        ("ARROW_CLEAR", wb.ARROW_CLEAR), ("DOODLE_LABEL_GAP", wb.DOODLE_LABEL_GAP)):
        assert re.search(rf"const {name} = {value};", src), name


def test_the_shared_cases():
    r3 = lambda v: round(v, 3)  # noqa: E731
    for c in CASES["wrap"]:
        assert wb.wrap_text(c["text"], c["size"], c["width"]) == c["lines"], c["text"]
    for c in CASES["text_width"]:
        assert r3(wb.text_width(c["text"], c["size"])) == c["width"]
    for c in CASES["timing"]:
        assert (wb.item_natural(c["item"]), wb.item_floor(c["item"])) == (c["natural"], c["floor"])
    for c in CASES["place"]:
        slot = wb.LAYOUTS[c["layout"]][c["slot"]]
        assert (wb.fit_problem(c["item"], slot) == "") == c["fits"], c
        if "bbox" in c:
            p = wb.place_item(c["item"], slot)
            assert [r3(v) for v in p["bbox"]] == c["bbox"]
            assert [l["text"] for l in p["lines"]] == c["lines"]
    for c in CASES["region_origin"]:
        assert list(wb.region_origin(c["i"])) == c["xy"]
    for c in CASES["arrow"]:
        assert [[r3(v) for v in pt] for pt in wb.arrow_ends(tuple(c["a"]), tuple(c["b"]))] == c["ends"]
    data = CASES["schedule"]["data"]
    out = [{"region": s["region"], "id": s["item"]["id"], "start": s["start"], "dur": s["dur"]}
           for s in wb.schedule(data["regions"], data["recapFrame"])]
    assert out == CASES["schedule"]["out"]


def test_the_pack_lists_exactly_the_doodles_the_renderer_draws():
    drawn = set(json.loads((TS_DIR / "doodles.json").read_text()))
    assert drawn == set(DOODLES)


LIBRARY = json.loads((TS_DIR / "doodles.json").read_text())


def test_the_expander_matches_the_renderer():
    """The shared cases: every primitive, and a digest of the whole library."""
    for c in CASES["expand"]:
        got = [[[round(x, 4), round(y, 4)] for x, y in st] for st in wb.expand_doodle(c["def"])]
        assert got == c["points"], c["name"]
    for name, d in LIBRARY.items():
        e = wb.expand_doodle(d)
        assert [len(st) for st in e] == CASES["library_digest"][name]["counts"], name
        assert round(sum(x + 2 * y for st in e for x, y in st), 3) == CASES["library_digest"][name]["sum"], name


def test_every_shipped_doodle_passes_the_rules_a_custom_one_must():
    """The library is the agent's reference: copying one must never be refused."""
    for name, d in LIBRARY.items():
        assert wb.doodle_problems(name, d) == [], name


def test_the_doodle_limits_match_the_renderer():
    assert _ts_object("DOODLE_LIMITS") == wb.DOODLE_LIMITS


def test_every_glyph_the_validator_allows_is_in_the_bundled_font():
    """GLYPH_EM is read from the font; it holds no character the font lacks."""
    assert "→" not in wb.GLYPH_EM and "√" not in wb.GLYPH_EM
    assert {"×", "÷", "²", "°", "½", "€", "£"} <= set(wb.GLYPH_EM)


def test_js_rounding_is_half_up():
    """Math.round, not Python's round: 2.5 rounds to 3 in the renderer."""
    assert wb._js_round(2.5) == 3 and round(2.5) == 2


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None):
    return wb.check(config or EXAMPLE, 30, WORD_STARTS, DOODLES)


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(cfg["scenes"][0]["props"]["whiteboard"])
    return cfg


def _item(board, region, iid):
    return next(i for i in board["regions"][region]["items"] if i["id"] == iid)


def test_the_skills_worked_example_passes():
    """The skill teaches from this file; a skill example the validator refuses
    teaches the agent to be refused."""
    assert wb.check_scene_use("whiteboard", EXAMPLE["scenes"]) == ""
    assert _check() == []


def test_only_a_whiteboard_video_may_use_the_scene():
    assert "visual_style is whiteboard" in wb.check_scene_use("stick", EXAMPLE["scenes"])
    assert wb.check_scene_use("stick", [{"src": "intro", "source": "generated"}]) == ""


def test_a_whiteboard_video_is_one_installed_generated_scene():
    two = EXAMPLE["scenes"] + [{"type": "generated", "src": "x", "startFrame": 0, "durationInFrames": 10}]
    assert "exactly one scene" in wb.check_scene_use("whiteboard", two)
    scenes = copy.deepcopy(EXAMPLE["scenes"])
    scenes[0]["source"] = "generated"
    assert "exactly one scene" in wb.check_scene_use("whiteboard", scenes)


@pytest.mark.parametrize("mutate, fragment", [
    (lambda b: b["regions"].__setitem__(slice(1, None), []), "2 to 6"),
    (lambda b: b["regions"][0].update(layout="grid"), "is not one of"),
    (lambda b: _item(b, 0, "bag").update(doodle="unicorn"), "neither a shipped doodle"),
    (lambda b: _item(b, 0, "rate").update(ink="green"), "ink 'green'"),
    (lambda b: _item(b, 0, "rate").update(slot="2"), "already used"),
    (lambda b: _item(b, 0, "rate").update(slot="left"), "not a slot of the stack layout"),
    (lambda b: _item(b, 0, "rate").update(text="a rate this long cannot fit in two lines of a stack row because it keeps going on"),
     "needs 3 lines"),
    (lambda b: _item(b, 0, "title").update(text="Compound interest explained"), "needs 2 lines; this slot holds 1"),
    (lambda b: _item(b, 0, "year1").update(text="100 × 1.1 × 1.1 × 1.1 × 1.1 = 146.41"), "too long for one line"),
    (lambda b: _item(b, 0, "rate").update(text="pays 10% → a year"), "has no →"),
    (lambda b: _item(b, 0, "rate").update(id="Rate"), "lowercase"),
    (lambda b: _item(b, 0, "u1").update(target="nope"), "earlier text, formula or doodle"),
    (lambda b: _item(b, 0, "u1").update(target="bag"), "an underline goes on text or a formula"),
    (lambda b: _item(b, 1, "hl").update(ink="blue"), "always yellow"),
    (lambda b: _item(b, 0, "rate").update(at=50), "is not on a word"),
    (lambda b: _item(b, 0, "rate").update(at=43), "later than the previous item's"),
    (lambda b: _item(b, 1, "head").update(at=304), "before the camera has reached this region"),
    (lambda b: b["regions"][1].update(startFrame=300), "not on a word"),
    (lambda b: b.update(recapFrame=1020), "must last 60 frames to 8 seconds"),
])
def test_a_bad_board_is_refused_with_a_reason(mutate, fragment):
    errs = _check(_with(mutate))
    assert any(fragment in e for e in errs), errs


def test_the_recap_must_leave_time_for_every_regions_number():
    """Number i pops recapPull + i * recapNumberStep frames into the recap; a
    six-region board with a two-second recap would end before the sixth."""
    assert wb.recap_min_frames(2) == 30 + 6 + 15
    assert wb.recap_min_frames(6) == 30 + 5 * 6 + 15 > 60
    errs = _check(_with(lambda b: b.update(recapFrame=1001)))  # 56 frames: under 2 s
    assert any("it must last 60 frames" in e for e in errs), errs


@pytest.mark.parametrize("mutate", [
    lambda b: _item(b, 0, "rate").update(slot=[]),
    lambda b: _item(b, 0, "rate").update(ink=["blue"]),
    lambda b: _item(b, 0, "rate").update(kind={}),
    lambda b: _item(b, 0, "bag").update(doodle=["coin"]),
    lambda b: _item(b, 0, "u1").update(target=["year1"]),
    lambda b: _item(b, 2, "point").update(**{"from": {}}),
    lambda b: b["regions"][0].update(layout=[]),
])
def test_a_wrong_type_is_reported_not_raised(mutate):
    """Agent-written JSON can hold a list where a name belongs; the tool must
    answer with a refusal, never an exception that fails the MCP call."""
    assert _check(_with(mutate))


def test_props_of_the_wrong_type_are_reported():
    cfg = copy.deepcopy(EXAMPLE)
    cfg["scenes"][0]["props"] = ["whiteboard"]
    assert any("props.whiteboard must be" in e for e in _check(cfg))


def test_big_must_be_a_boolean():
    """Python reads {} as false and JavaScript as true: the two sides would lay
    the text out at different sizes."""
    errs = _check(_with(lambda b: _item(b, 0, "rate").update(big={})))
    assert any("big must be true or false" in e for e in errs), errs


BICYCLE = [
    [{"circle": [24, 64, 16]}],
    [{"circle": [76, 64, 16]}],
    [{"line": [[24, 64], [44, 40], [68, 40], [76, 64]]}],
    [{"line": [[44, 40], [52, 64], [68, 40]]}],
    [{"line": [[40, 32], [50, 32]]}, {"line": [[66, 30], [74, 30]]}],
]


def _with_custom(doodles, slot_doodle="bicycle"):
    def mutate(b):
        b["doodles"] = doodles
        _item(b, 0, "bag").update(doodle=slot_doodle)
    return _with(mutate)


def test_a_video_may_draw_its_own_doodle():
    assert _check(_with_custom({"bicycle": BICYCLE})) == []


@pytest.mark.parametrize("doodles, fragment", [
    ({"coin": BICYCLE}, "is a shipped doodle"),
    ({"Bike": BICYCLE}, "lowercase"),
    ({"bicycle": BICYCLE, "unused": BICYCLE}, "defined but never drawn"),
    ({"bicycle": [[{"circle": [95, 50, 10]}]]}, "outside the 0-100 box"),
    ({"bicycle": [[{"spiral": [50, 50, 10]}]]}, "is not a primitive"),
    ({"bicycle": [[{"circle": [50, 50]}]]}, "circle takes 3 to 4 numbers"),
    ({"bicycle": [[{"arc": [50, 50, 10, 10, 0, 100000]}]]}, "at most a few full circles"),
    ({"bicycle": [[{"star": [50, 50, 10, 20, 1000]}]]}, "whole count from 3 to 12"),
    ({"bicycle": [[{"line": [[50, 50]]}]]}, "single point"),
    ({"bicycle": [[{"line": [[10, 10], [20, 20]]}]] * 21}, "at most 20"),
    ({"bicycle": "a bike"}, "non-empty list of strokes"),
    ("bike", "doodles must be an object"),
    ({f"d{i}": BICYCLE for i in range(9)}, "at most 8 per video"),
])
def test_a_bad_custom_doodle_is_refused(doodles, fragment):
    errs = _check(_with_custom(doodles))
    assert any(fragment in e for e in errs), errs


def test_a_doodle_name_that_is_neither_shipped_nor_defined_is_refused():
    errs = _check(_with_custom({}, slot_doodle="bicycle"))
    assert any("neither a shipped doodle nor one this video defines" in e for e in errs), errs


def test_a_second_highlight_in_a_region_is_refused():
    def two(b):
        b["regions"][1]["items"].append({"id": "hl2", "kind": "highlight", "target": "not_just", "at": 643})
    assert any("one highlight per region" in e for e in _check(_with(two)))


def test_an_arrow_through_other_writing_is_refused():
    """In a stack, an arrow from row 1 to row 3 passes through row 2."""
    def through(b):
        b["regions"][0]["items"].insert(4, {"id": "jump", "kind": "arrow", "from": "title", "to": "rate", "at": 223})
    assert any("would cross 'bag'" in e for e in _check(_with(through)))


def test_an_arrow_needs_two_earlier_placed_items():
    def bad(b):
        _item(b, 2, "point").update(to="ring")
    assert any("an arrow goes from one earlier" in e for e in _check(_with(bad)))


def test_a_marker_that_cannot_keep_up_is_refused():
    """Two items one word apart: the formula's floor is 11 frames, and the
    next item starts 10 frames later."""
    def crowd(b):
        _item(b, 0, "u1").update(at=201)
    errs = _check(_with(crowd))
    assert any("item 'year1'" in e and "needs at least 11 frames" in e for e in errs), errs


def test_an_item_drawn_as_the_camera_leaves_is_refused():
    """Region 1 ends at 294; the last item must finish 15 frames before."""
    def late(b):
        _item(b, 0, "u1").update(at=272)
    errs = _check(_with(late))
    assert any("item 'u1'" in e and "camera leaves the region" in e for e in errs), errs


def test_a_long_still_stretch_is_refused():
    def quiet(b):
        b["regions"][1]["items"] = [i for i in b["regions"][1]["items"] if i["id"] != "not_just"]
    assert any("Nothing new happens" in e for e in _check(_with(quiet)))


def test_the_stillness_rule_uses_the_narrations_fps():
    """At 300 fps the same frames are a tenth of the time: nothing is still."""
    def quiet(b):
        b["regions"][1]["items"] = [i for i in b["regions"][1]["items"] if i["id"] != "not_just"]
    assert not any("Nothing new" in e for e in wb.check(_with(quiet), 300, WORD_STARTS, DOODLES))


def test_errors_are_capped_so_the_message_stays_readable():
    def wreck(b):
        for r in b["regions"]:
            for it in r["items"]:
                it["ink"] = "nope"
    assert len(_check(_with(wreck))) <= wb.MAX_ERRORS


def test_region_windows():
    assert wb.region_windows(EXAMPLE) == [(0, 294), (294, 672), (672, 920), (920, 1057)]
    assert wb.region_windows({"scenes": []}) == []


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make(video_id, style="whiteboard", with_timeline=True):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'why compound interest snowballs', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        if with_timeline:
            d = tmp_path / "jobs" / video_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_board_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_wb1")
    cfg = copy.deepcopy(EXAMPLE)
    assert "subtitles" not in cfg  # the skill tells the agent to leave it out
    result = server.write_scene_config(vid, cfg)
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("whiteboard")["captions"]
    assert written["canvas"] == "light"


def test_a_bad_board_is_refused_before_anything_is_written(make_video):
    vid = make_video("vid_wb2")
    result = server.write_scene_config(vid, _with(lambda b: _item(b, 0, "bag").update(doodle="unicorn")))
    assert "Whiteboard board has problems" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_whiteboard_scene(make_video):
    vid = make_video("vid_wb3", style="stick")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "visual_style is whiteboard" in result["error"]


def test_a_whiteboard_video_cannot_be_built_from_other_scenes(make_video):
    vid = make_video("vid_wb4")
    cfg = {"totalFrames": 600, "fps": 30, "sfx": [],
           "scenes": [{"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 600}]}
    assert "exactly one scene" in server.write_scene_config(vid, cfg)["error"]


def test_a_whiteboard_video_cannot_be_painted_dark(make_video):
    vid = make_video("vid_wb5")
    cfg = copy.deepcopy(EXAMPLE)
    cfg["canvas"] = "dark"
    assert "canvas" in server.write_scene_config(vid, cfg)["error"]


def test_the_word_check_is_skipped_without_a_timeline(make_video):
    vid = make_video("vid_wb6", with_timeline=False)
    cfg = _with(lambda b: _item(b, 0, "rate").update(at=110))
    assert "error" not in server.write_scene_config(vid, cfg)


# ── the text audit samples every region ──────────────────────────────────────

def test_the_text_audit_samples_each_region_and_the_recap():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = wb.region_windows(EXAMPLE)
    assert len(passes) == len(windows) == 4
    for p, (start, end) in zip(passes, windows):
        assert p["first"] == start + text_audit.ENTRANCE_ALLOWANCE_FRAMES
        assert p["first"] + p["step"] * (p["count"] - 1) < end


# ── preview_doodles ──────────────────────────────────────────────────────────

def test_preview_draws_each_doodle_beside_the_shipped_references():
    import io as _io
    from PIL import Image
    meta, image = server.preview_doodles({"bicycle": BICYCLE, "dam": [[{"rect": [10, 30, 80, 50, 4]}]]})
    meta = json.loads(meta)
    assert meta["doodles"] == ["bicycle", "dam"]
    assert meta["references"] == list(server._DOODLE_PREVIEW_REFERENCES)
    with Image.open(_io.BytesIO(image.data)) as img:
        # four cells in one row: two of the agent's, two shipped
        assert img.size == (4 * doodle_preview.CELL, doodle_preview.CELL + doodle_preview.LABEL_H)
        assert max(img.size) <= server._READ_IMAGE_MAX_EDGE


def test_preview_refuses_what_write_scene_config_would():
    result = server.preview_doodles({"coin": BICYCLE, "blob": [[{"circle": [95, 50, 10]}]]})
    assert "is a shipped doodle" in result["error"] and "outside the 0-100 box" in result["error"]
    assert "give at least one" in server.preview_doodles({})["error"]
    assert "must be an object" in server.preview_doodles(["bicycle"])["error"]
