"""Isometric Infographic: the scene-config checks that keep an unattended agent
from shipping a crowded, off-board, mistimed or still board, or a part of its
own that is not built from the kit's solids, their agreement with the
renderer's contract.ts and stage.ts and the style pack, and their place in
write_scene_config, the text audit and render_style_parts.

Each refusal guards something the renderer cannot fix: two props on one tile
draw into each other, a prop or a route off the board floats on the paper, a
mover that leaves before its route draws breaks the line-leads rule, a pin on
nothing points at nothing, a cutaway on a building with no inside opens onto
nothing, and four seconds with nothing new is a dead board.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import isometric_infographic as iso
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/isometric_infographic_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-isometric-infographic/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("isometric_infographic")["extra"]


def test_the_constants_and_cases_match_the_renderer():
    c = CASES["constants"]
    assert iso.LIMITS == c["LIMITS"] and iso.TIMING == c["TIMING"] and iso.GEOMETRY == c["GEOMETRY"]
    data = CASES["data"]
    assert [iso.event_frames(b) for b in data["boards"]] == CASES["event_frames"]
    assert iso.quiet_spans(data, CASES["total"]) == CASES["quiet_spans"]
    for case in CASES["grouped"]:
        assert iso.grouped(case["n"]) == case["text"]


def test_the_pack_carries_the_catalogues():
    assert {"house", "warehouse", "data_centre", "truck", "server_rack"} <= set(EXTRA["props"])
    assert set(EXTRA["rooms"]) <= set(EXTRA["props"]) and set(EXTRA["stacks"]) <= set(EXTRA["props"])
    assert "server_rack" in EXTRA["stacks"] and "warehouse" in EXTRA["rooms"]
    assert {"red", "gold", "slate"} <= set(EXTRA["colors"]) and "water" in EXTRA["areas"]
    assert EXTRA["solids"] == list(iso.SOLIDS)


def _check(config=None, quiet=()):
    return iso.check(config or EXAMPLE, 30, WORD_STARTS, EXTRA, "vid_example", quiet=quiet)


def _data(cfg):
    return cfg["scenes"][0]["props"]["isometric"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _b(d, i=0):
    return d["boards"][i]


def test_the_example_passes():
    assert _check() == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(title="A TITLE THAT IS FAR TOO LONG"), "title must be"),
    (lambda d: d.update(colour="red"), "unknown field"),
    (lambda d: d["boards"].extend([copy.deepcopy(d["boards"][0])] * 3), "boards must list"),
    (lambda d: _b(d)["areas"].append({"kind": "lava", "rect": [0, 0, 1, 1]}), "kind must be one of"),
    (lambda d: _b(d)["areas"].append({"kind": "land", "rect": [5, 5, 4, 6]}), "x0 < x1"),
    (lambda d: _b(d)["props"][0].update(what="spaceship"), "is not a library prop"),
    (lambda d: _b(d)["props"][0].update(at=[12, 1]), "on the board"),
    (lambda d: _b(d)["props"][1].update(at=_b(d)["props"][0]["at"]), "ground; move it"),
    (lambda d: _b(d)["props"][0].update(color="purple"), "color must be one of"),
    (lambda d: _b(d)["props"][0].update(scale=3), "scale must be from"),
    (lambda d: _b(d)["routes"][0]["points"].append([11, 3]), "points"),
    (lambda d: _b(d)["movers"][0].update(route="nowhere"), "one of the board's routes"),
    (lambda d: _b(d)["movers"][0].update(at=_b(d)["routes"][0]["at"] - 0) or _b(d)["routes"][0].update(at=_b(d)["movers"][0]["at"] + 9999),
     "frame from"),
    (lambda d: _b(d)["pins"][0].update(on="ghost"), "a prop id of the board"),
    (lambda d: _b(d)["pins"][0].update(label="A LABEL TOO LONG"), "label must be"),
    (lambda d: _b(d)["camera"][0].update(zoom=4), "zoom must be"),
    (lambda d: _b(d)["cutaways"][0].update(prop="home") or _b(d)["props"][2].update(what="tree"), "is not a building that opens"),
    (lambda d: _b(d)["explodes"][0].update(prop="depot"), "is not a stack that separates"),
    (lambda d: d["readout"]["steps"][0].update(red=True), "turns red once"),
    (lambda d: d["readout"]["cubes"].update(per=1), "per is too small"),
    (lambda d: d["readout"]["cubes"].update(per=0.5), "a number of 1 or more"),
    (lambda d: d.update(readout="bad"), "readout takes"),
    (lambda d: d["readout"]["steps"][0].update(red="false"), "red must be true or false"),
    (lambda d: _b(d)["movers"][0].update(back="no"), "back must be true or false"),
    (lambda d: _b(d)["props"][0].update(what="crane", at=[0.6, 5], scale=1.4), "hang off the board"),
    (lambda d: d["legend"]["items"].extend([{"color": "red", "label": "ANOTHER ONE"}] * 3), "legend"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_mover_never_leaves_before_its_route_draws():
    def early(d):
        r = _b(d)["routes"][0]
        m = _b(d)["movers"][0]
        r["at"], m["at"] = m["at"], r["at"]
    problems = _check(_with(early))
    assert any("the line leads every move" in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    def still(d):
        _b(d).pop("explodes")
        _b(d)["camera"] = [c for c in _b(d)["camera"] if c.get("focus") != "db"]
        _b(d)["props"] = [p for p in _b(d)["props"] if p["id"] != "db"]
    assert any("nothing new happens" in p for p in _check(_with(still)))


@pytest.mark.parametrize("part, fragment", [
    ({"id": "kiosk", "solids": [{"s": "sphere", "x": 0, "y": 0, "h": 1, "c": "main"}], "main": "red", "height": 1}, "s must be one of"),
    ({"id": "kiosk", "solids": [{"s": "box", "x": 2, "y": 0, "w": 0.4, "d": 0.4, "h": 1, "c": "main"}], "main": "red", "height": 1}, "x and y"),
    ({"id": "kiosk", "solids": [{"s": "box", "x": 0, "y": 0, "w": 0.4, "d": 0.4, "h": 1, "c": "#123456"}], "main": "red", "height": 1}, "c must be"),
    ({"id": "house", "solids": [{"s": "box", "x": 0, "y": 0, "w": 0.4, "d": 0.4, "h": 1, "c": "main"}], "main": "red", "height": 1}, "not a library prop"),
    ({"id": "kiosk", "solids": [], "main": "red", "height": 1}, "solids must list"),
    ({"id": "kiosk", "solids": [{"s": "box", "x": -0.8, "y": 0, "w": 1.6, "d": 0.4, "h": 1, "c": "main"}], "main": "red", "height": 1}, "own footprint"),
    ({"id": "kiosk", "solids": [{"s": "cyl", "x": 0.5, "y": 0, "r": 0.5, "h": 1, "c": "gold"}], "main": "red", "height": 1}, "own footprint"),
])
def test_a_bad_custom_prop_is_refused(part, fragment):
    problems = _check(_with(lambda d: d.update(customProps=[part])))
    assert any(fragment in p for p in problems), problems


def test_a_custom_prop_stands_on_the_board():
    kiosk = {"id": "kiosk", "main": "teal", "height": 0.9,
             "solids": [{"s": "box", "x": 0, "y": 0, "w": 0.5, "d": 0.5, "h": 0.6, "c": "main"},
                        {"s": "gable", "x": 0, "y": 0, "z": 0.6, "w": 0.5, "d": 0.5, "h": 0.25, "c": "red"}]}

    def use(d):
        d["customProps"] = [kiosk]
        _b(d)["props"].append({"id": "k", "what": "kiosk", "at": [3, 8]})
    assert _check(_with(use)) == []


def test_nothing_happens_inside_an_insert():
    d = _data(EXAMPLE)
    lift = _b(d)["lifts"][0]["at"]
    assert any("inside an insert" in p for p in _check(quiet=[(lift - 5, lift + 40)]))


def test_a_prop_may_fall_behind_an_insert_and_land_after_it():
    d = _data(EXAMPLE)
    lands = next(p["enter"] for p in _b(d)["props"] if "enter" in p)
    assert not any("inside an insert" in p for p in _check(quiet=[(lands - 10, lands)]))
    assert any("inside an insert" in p for p in _check(quiet=[(lands - 10, lands + 1)]))


def test_the_last_change_on_a_board_and_the_last_readout_step_are_left_on_screen():
    cfg = copy.deepcopy(EXAMPLE)
    d = _data(cfg)
    total = cfg["totalFrames"]
    end = _b(d, 1)["start"] if len(d["boards"]) > 1 else total
    _b(d)["pins"][0]["at"] = end - 5
    problems = iso.check(cfg, 30, WORD_STARTS + [end - 5], EXTRA, "vid_example")
    assert any("frames to see it" in p for p in problems), problems
    cfg = copy.deepcopy(EXAMPLE)
    _data(cfg)["legend"]["at"] = total - 3
    problems = iso.check(cfg, 30, WORD_STARTS + [total - 3], EXTRA, "vid_example")
    assert any("finishes changing" in p for p in problems), problems


def test_the_scene_use_rule_and_the_audit_windows():
    assert iso.check_scene_use("isometric_infographic", EXAMPLE["scenes"]) == ""
    assert "visual_style is isometric_infographic" in iso.check_scene_use("stick", EXAMPLE["scenes"])
    windows = iso.board_windows(EXAMPLE)
    assert len(windows) == len(_data(EXAMPLE)["boards"])
    passes, _ = text_audit.plan_passes(EXAMPLE)
    assert [p["first"] for p in passes] == [w[0] for w in windows]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")

    def make(video_id, style="isometric_infographic"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'a parcel trip', 'VOICE_READY', ?, ?, ?)", (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_card_captions(make_video):
    vid = make_video("vid_iso1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("isometric_infographic")["captions"]
    assert written["subtitles"]["background"] == "card"


def test_another_style_cannot_use_the_isometric_scene(make_video):
    vid = make_video("vid_iso2", style="stick")
    assert "visual_style is isometric_infographic" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_render_style_parts_sends_the_compositions(make_video, monkeypatch):
    vid = make_video("vid_iso3")
    cfg = _with(lambda d: d.update(customProps=[{"id": "kiosk", "main": "teal", "height": 0.9,
                                                 "solids": [{"s": "box", "x": 0, "y": 0, "w": 0.5, "d": 0.5, "h": 0.6, "c": "main"}]}]))
    assert "error" not in server.write_scene_config(vid, cfg)
    seen = {}

    def fake(remotion, spec, out_png, script=None):
        from PIL import Image
        seen.update(spec=spec)
        Image.new("RGB", (1080, 1920), "white").save(out_png)
    monkeypatch.setattr(server.bean_preview, "render_preview", fake)
    out = server.render_style_parts(vid)
    assert json.loads(out[0])["parts"] == ["kiosk"]
    assert seen["spec"]["style"] == "isometric_infographic" and seen["spec"]["parts"][0]["id"] == "kiosk"


def test_the_footprint_matches_the_renderer():
    for case in CASES["footprint"]:
        assert iso.footprint(case["solids"]) == case["half"]
    assert EXTRA["footprints"]["crane"] > EXTRA["footprints"]["person"]


def test_two_large_props_cannot_share_their_ground():
    def crowd(d):
        props = _b(d)["props"]
        props[0].update(what="warehouse")
        props[1].update(what="data_centre", at=[props[0]["at"][0] + 0.9, props[0]["at"][1]])
    assert any("ground; move it" in p for p in _check(_with(crowd)))


def test_a_mover_going_back_still_waits_for_its_route():
    def early(d):
        r, m = _b(d)["routes"][0], _b(d)["movers"][0]
        m["back"] = True
        r["at"], m["at"] = m["at"], r["at"]
    assert any("the line leads every move" in p for p in _check(_with(early)))


def test_a_pin_waits_for_its_prop_to_land():
    cfg = copy.deepcopy(EXAMPLE)
    b = _b(_data(cfg))
    prop = next(p for p in b["props"] if "enter" in p)
    b["pins"][0].update(on=prop["id"], at=prop["enter"] - 30)
    problems = iso.check(cfg, 30, WORD_STARTS + [prop["enter"] - 30], EXTRA, "vid_example")
    assert any("before " + prop["id"] + " lands" in p for p in problems), problems


def test_a_move_still_running_at_the_board_end_is_refused():
    cfg = copy.deepcopy(EXAMPLE)
    d = _data(cfg)
    end = _b(d, 1)["start"]
    _b(d)["movers"][0]["at"] = end - 25
    problems = iso.check(cfg, 30, WORD_STARTS + [end - 25], EXTRA, "vid_example")
    assert any("settles at frame" in p for p in problems), problems


def test_a_legend_is_held_from_when_it_has_risen():
    cfg = copy.deepcopy(EXAMPLE)
    total = cfg["totalFrames"]
    at = total - iso.TIMING["legend"] - iso.TIMING["readFrames"]
    _data(cfg)["legend"]["at"] = at
    assert not any("finishes changing" in p for p in iso.check(cfg, 30, WORD_STARTS + [at], EXTRA, "vid_example"))


def test_a_wrong_typed_value_is_reported_not_raised():
    problems = _check(_with(lambda d: _b(d)["props"][0].update(what={"a": 1})))
    assert any("wrong type" in p for p in problems), problems
    assert _check(_with(lambda d: _b(d).update(props=True)))



def test_lifts_cutaways_and_explodes_wait_for_their_prop_and_come_in_order():
    d = _data(EXAMPLE)
    landing = next(p for p in _b(d)["props"] if "enter" in p)

    def early(dd):
        _b(dd)["lifts"][0].update(prop=landing["id"], at=landing["enter"] - 30)
    problems = iso.check(_with(early), 30, WORD_STARTS + [landing["enter"] - 30], EXTRA, "vid_example")
    assert any("before " + landing["id"] + " lands" in p for p in problems), problems

    def out_of_order(dd):
        lifts = _b(dd)["lifts"]
        lifts.append(dict(lifts[0], at=lifts[0]["at"] - 1))
    problems = iso.check(_with(out_of_order), 30, WORD_STARTS + [_b(d)["lifts"][0]["at"] - 1], EXTRA, "vid_example")
    assert any("in time order" in p for p in problems), problems


def test_names_and_clocks_end_at_the_end():
    assert not iso._ID.match("abc\n")
    assert iso.grouped(2.5) == "3" and iso.grouped(1234.5) == "1,235"
