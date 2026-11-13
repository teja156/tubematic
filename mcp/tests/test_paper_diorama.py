"""Paper Diorama (TMDEV-228): the scene-config checks that keep an unattended
agent from shipping a prop that does not exist, two props on top of each
other, an event off the narration, a prop in the banner or off the frame, or a
still stage; their agreement with the renderer's contract.ts and the style
pack; and their place in write_scene_config, the text audit and the picture
checks.

Each refusal guards something the renderer cannot fix: it draws whatever it is
given, so a prop standing in the critter's place or an event in an insert
window would ship as it is.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import paper_diorama as pd
import picture_checks
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
KIT = REPO / "renderer/remotion/src/scenes/installed/paperDiorama"
CONTRACT_TS = KIT / "contract.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/paper_diorama_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-paper-diorama/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
PACK = tvs.pack("paper_diorama")
EXTRA = PACK["extra"]
LIBRARY = json.loads((KIT / "props.json").read_text())
VID = "vid_paper0001"


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    body = re.sub(r"//.*", "", body)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)(?=\s*(?:[,}\n]|$))", body)}


def _ts_keys(name: str) -> tuple[str, ...]:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    return tuple(k.strip('"') for k in re.findall(r'("[\w-]+"|\w+):\s*[{"#\d]', re.sub(r"//.*", "", body)))


def _ts_array(name: str) -> tuple[str, ...]:
    src = CONTRACT_TS.read_text()
    return tuple(re.findall(r'"([\w-]+)"', re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.S).group(1)))


def _data(cfg):
    return cfg["scenes"][0]["props"]["paperDiorama"]


def _check(cfg=None, quiet=(), silences=()):
    return pd.check(cfg or EXAMPLE, 30, WORD_STARTS, EXTRA, quiet=quiet, silences=silences)


def _stalls(errors):
    """Every "nothing new happens from frame A to C" refusal as (A, C)."""
    return [(int(a), int(c)) for e in errors if "nothing new happens" in e
            for a, c in [re.search(r"from frame (\d+) to (\d+)", e).groups()]]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


# ── agreement with the renderer and the pack ────────────────────────────────

def test_the_constants_equal_the_renderers_contract():
    assert _ts_block("ZONES") == pd.ZONES
    assert _ts_block("SLOTS") == pd.SLOTS
    assert _ts_block("LEVELS") == pd.LEVELS
    assert _ts_block("SCALES") == pd.SCALES
    assert _ts_block("TIMING") == pd.TIMING
    assert _ts_block("LIMITS") == pd.LIMITS
    assert _ts_keys("COLORS") == pd.COLORS
    rooms_ts = dict(re.findall(r'"?([\w-]+)"?: \{ floorY: (\d+)', CONTRACT_TS.read_text()))
    assert {k: int(v) for k, v in rooms_ts.items()} == pd.ROOMS
    for name, ours in (("EVENTS", pd.EVENTS), ("ENTERS", pd.ENTERS), ("CUTS", pd.CUTS),
                       ("SHAPES", pd.SHAPES), ("FONTS", pd.FONTS)):
        assert _ts_array(name) == ours, name
    src = CONTRACT_TS.read_text()
    for key in ("expressions", "accessories"):
        listed = re.search(rf"{key}: \[(.*?)\]", src).group(1)
        assert tuple(re.findall(r'"(\w+)"', listed)) == pd.CRITTER[key]


def test_the_pack_lists_what_the_contract_holds():
    assert EXTRA["rooms"] == list(pd.ROOMS)
    assert EXTRA["slots"] == list(pd.SLOTS) and EXTRA["levels"] == list(pd.LEVELS)
    assert EXTRA["scales"] == list(pd.SCALES) and EXTRA["events"] == list(pd.EVENTS)
    assert EXTRA["enters"] == list(pd.ENTERS) and EXTRA["cuts"] == list(pd.CUTS)
    assert EXTRA["expressions"] == list(pd.CRITTER["expressions"])
    assert EXTRA["accessories"] == list(pd.CRITTER["accessories"])
    assert EXTRA["critter_colors"] == list(pd.CRITTER_COLORS)


def test_the_pack_lists_every_shipped_prop_at_its_size():
    """The server checks sizes and overlaps from the pack; a prop redrawn at another size in
    props.json without the pack would pass checks the render then breaks."""
    assert EXTRA["props"] == {name: [d["w"], d["h"]] for name, d in LIBRARY.items()}


def test_every_shipped_prop_is_a_valid_custom_prop_too():
    for name, prop in LIBRARY.items():
        assert pd.prop_errors(name, prop) == [], name


def test_the_shared_cases_agree():
    for c in CASES["pop_scale"]:
        assert pd.pop_scale(c["age"]) == pytest.approx(c["scale"])
    for c in CASES["slot_box"]:
        assert list(pd.slot_box(c["room"], c["slot"], c["level"], c["w"], c["h"])) == pytest.approx(c["box"])
    for c in CASES["stage_scale"]:
        assert pd.stage_scale(c["zooms"], c["frame"]) == pytest.approx(c["scale"])
    for c in CASES["banner_font_size"]:
        assert pd.banner_font_size(c["text"]) == c["size"]
    assert (pd.CRITTER_W, pd.CRITTER_H) == pytest.approx((CASES["critter"]["w"], CASES["critter"]["h"]))


def test_the_captions_are_the_tags_look_the_server_accepts():
    assert PACK["captions"]["look"] == "tags"
    assert server._validate_subtitles(PACK["captions"]) == ""


# ── the checks ───────────────────────────────────────────────────────────────

def test_the_skills_worked_example_passes():
    assert _check() == []


def test_the_scene_is_this_styles_alone():
    assert "used only when" in pd.check_scene_use("stick", EXAMPLE["scenes"])
    assert pd.check_scene_use("stick", [{"src": "Other"}]) == ""
    two = EXAMPLE["scenes"] + [{"type": "generated", "src": "x"}]
    assert "exactly one scene" in pd.check_scene_use("paper_diorama", two)


@pytest.mark.parametrize("field", ["room", "slot", "level", "scale", "target", "to", "from", "prop"])
@pytest.mark.parametrize("value", [["x"], {"x": 1}])
def test_a_list_or_object_where_a_name_belongs_is_refused_not_raised(field, value):
    def put(d):
        s = d["sets"][1]
        s["room"] = value if field == "room" else s["room"]
        for it in s["items"]:
            for k in ("slot", "level", "scale", "prop"):
                if field == k:
                    it[k] = value
        for e in s["events"]:
            if field in ("target", "to", "from", "level", "prop"):
                e[field] = value
    assert _check(_with(put))   # a list of problems, never a TypeError


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d["sets"][0].update(room="moon-base"), "room must be one of"),
    (lambda d: d["sets"][0].update(banner=""), "banner must be"),
    (lambda d: d["sets"][0].update(banner="x" * 29), "banner must be"),
    (lambda d: d["sets"][1].update(start=d["sets"][1]["start"] + 5), "not on a word"),
    (lambda d: d["sets"][0]["items"][0].update(prop="spaceship"), "neither a shipped prop"),
    (lambda d: d["sets"][0]["items"][0].update(slot="far"), "slot must be one of"),
    (lambda d: d["sets"][0]["items"][1].update(at=d["sets"][0]["items"][1]["at"] + 5), "not on a word"),
    (lambda d: d["sets"][0]["items"][0].update(slot="l"), "on top of each other"),
    (lambda d: d["sets"][0]["items"][0].update(slot="r", scale="l"), "runs off the right edge"),
    (lambda d: d["sets"][3]["items"][1].update(level="air", scale="l"), "reaches the banner"),
    (lambda d: d["sets"][1]["events"][0].update(target="ghost"), "target must be an item"),
    (lambda d: d["sets"][1]["events"][2].update(text="WAY TOO LONG FOR IT"), "text must be 1 to 12"),
    (lambda d: d["sets"][2]["events"][0].update(prop="laptop"), "swap to a prop of the same size"),
    (lambda d: d["sets"][2]["events"].append({"at": d["sets"][2]["start"], "do": "expr", "target": "critter",
                                              "value": "angry"}), "value must be one of"),
    (lambda d: d["sets"][2]["events"].append({"at": d["sets"][2]["start"], "do": "ring", "target": "critter"}),
     "the critter takes only"),
    (lambda d: d["sets"][3]["events"][0].update(**{"from": "server"}), "from must be another item"),
    (lambda d: d["sets"][0]["events"][0].update(do="explode"), "do must be one of"),
    (lambda d: d["sets"][0].update(camera="push"), "unknown field"),
    (lambda d: d.update(critter={"color": "green"}), "critter.color"),
    (lambda d: d["sets"][0]["items"][0].update(colour="red"), "unknown field"),
    # JSON true equals 1 in Python; the renderer takes only the numbers 1 and -1.
    (lambda d: d["sets"][0]["critter"].update(face=True), "critter.face must be"),
    (lambda d: d["sets"][0]["critter"].update(face=False), "critter.face must be"),
])
def test_a_bad_config_is_refused_with_its_cause(mutate, fragment):
    errors = _check(_with(mutate))
    assert any(fragment in e for e in errors), errors


def test_an_event_on_an_item_that_has_left_or_not_arrived_is_refused():
    def late(d):
        d["sets"][2]["events"].append({"at": d["sets"][2]["events"][1]["at"] + 0, "do": "hop", "target": "lock"})
    assert any("already left" in e for e in _check(_with(late)))

    def early(d):
        s = d["sets"][1]
        s["events"].append({"at": s["start"], "do": "hop", "target": "spy"})
    assert any("has not entered yet" in e for e in _check(_with(early)))


def test_the_critter_walking_onto_a_prop_is_refused():
    def walk(d):
        s = d["sets"][0]   # the laptop stands at c on the floor, the critter at l
        at = next(w for w in WORD_STARTS if 30 < w < 200)
        s["events"].append({"at": at, "do": "move", "target": "critter", "to": "c"})
    assert any("the critter and item" in e and "on top of each other" in e for e in _check(_with(walk)))


def test_an_event_after_an_exit_is_refused_whatever_the_list_order():
    def late_exit(d):
        s = d["sets"][1]
        it = s["items"][0]
        later = next(w for w in WORD_STARTS if w > it["at"] + 40 and w < s["start"] + 200)
        s["events"].insert(0, {"at": later, "do": "hop", "target": it["id"]})
        s["events"].append({"at": later - 20 if (later - 20) in WORD_STARTS else
                            max(w for w in WORD_STARTS if it["at"] < w < later), "do": "exit", "target": it["id"]})
    assert any("has already left" in e for e in _check(_with(late_exit)))


def test_too_many_zooms_are_refused():
    def zooms(d):
        s = d["sets"][3]
        z = s["events"][1]["at"]
        s["events"] += [{"at": z, "do": "zoom", "target": "server"} for _ in range(3)]
    assert any("snaps the camera" in e for e in _check(_with(zooms)))


def test_a_still_stage_is_refused_and_an_event_fixes_it():
    def still(d):
        d["sets"][0]["events"] = [e for e in d["sets"][0]["events"] if e["do"] != "hop"]
    errors = _check(_with(still))
    assert any("nothing new happens" in e for e in errors), errors


def test_a_silent_pause_is_not_a_stall():
    # [long pause] voices as silence: no word to put an event on, so the stretch across it may hold
    def still(d):
        d["sets"][0]["events"] = [e for e in d["sets"][0]["events"] if e["do"] != "hop"]
    cfg = _with(still)
    stalls = _stalls(_check(cfg))
    assert stalls
    assert _check(cfg, silences=[(a + 5, c - 5) for a, c in stalls]) == []
    a, c = stalls[0]
    assert any("nothing new happens" in e for e in _check(cfg, silences=[(a + 5, a + 20)]))   # a short gap is no cover   # a short gap is no cover


def test_a_custom_prop_is_checked_piece_by_piece():
    good = {"w": 120, "h": 120, "pieces": [{"shape": "rect", "fill": "go", "x": 0, "y": 0, "w": 120, "h": 120, "r": 8},
                                           {"shape": "text", "fill": "white", "text": "OK", "x": 60, "y": 60}]}
    assert pd.prop_errors("badge", good) == []

    def use(d, prop):
        d["customProps"] = {"badge": prop}
        d["sets"][1]["items"][0].update(prop="badge")
    assert _check(_with(lambda d: use(d, good))) == []
    for bad, fragment in [
        ({**good, "w": 900}, "w and h must be"),
        ({**good, "pieces": []}, "pieces must list"),
        ({**good, "pieces": [{"shape": "star", "fill": "go"}]}, "shape must be"),
        ({**good, "pieces": [{"shape": "rect", "fill": "#FF0000", "x": 0, "y": 0, "w": 10, "h": 10}]}, "colour name"),
        ({**good, "pieces": [{"shape": "rect", "fill": "go", "x": 100, "y": 0, "w": 60, "h": 10}]}, "outside the prop"),
        ({**good, "pieces": [{"shape": "text", "fill": "ink", "text": "X" * 20, "x": 60, "y": 60}]}, "text must be"),
        ({**good, "pieces": [{"shape": "poly", "fill": "go", "points": [[0, 0], [10, 10]]}]}, "points must list"),
    ]:
        assert any(fragment in e for e in pd.prop_errors("badge", bad)), (fragment, pd.prop_errors("badge", bad))
    assert any("is a shipped prop" in e for e in _check(_with(lambda d: d.update(customProps={"laptop": good}))))


def test_nothing_starts_inside_an_insert_window_and_a_window_is_not_still():
    s1 = EXAMPLE["scenes"][0]["props"]["paperDiorama"]["sets"][1]
    w = (s1["start"] - 30, s1["start"] + 30)
    assert any("inside an insert" in e for e in _check(quiet=[w]))
    # a window over a quiet stretch of a set: nothing starts in it, and it is not still
    s0 = EXAMPLE["scenes"][0]["props"]["paperDiorama"]["sets"][0]
    hop = next(e["at"] for e in s0["events"] if e["do"] == "hop")
    assert _check(quiet=[(hop + 5, hop + 40)]) == []


# ── the text audit and the picture checks ────────────────────────────────────

def test_the_text_audit_samples_each_set_after_its_last_event():
    windows = pd.beat_windows(EXAMPLE)
    sets = _data(EXAMPLE)["sets"]
    assert len(windows) == len(sets)
    for (first, end), s in zip(windows, sets):
        assert s["start"] <= first < end
    passes = text_audit.plan_passes(EXAMPLE)["passes"] if isinstance(text_audit.plan_passes(EXAMPLE), dict) \
        else text_audit.plan_passes(EXAMPLE)
    assert passes


def test_the_picture_checks_read_the_style():
    assert picture_checks.style_of(EXAMPLE) == "paper_diorama"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    empty = _with(lambda d: d["sets"][0].update(items=[{**d["sets"][0]["items"][0], "at": 120}]))
    assert picture_checks.first_frame_warnings(empty)
    frames = picture_checks.change_frames("paper_diorama", EXAMPLE)
    assert 0 in frames and _data(EXAMPLE)["sets"][1]["start"] in frames


# ── write_scene_config ───────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make(style="paper_diorama"):
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                        "VALUES (?, NULL, 'how a VPN works', 'VOICE_READY', ?, ?, ?)", (VID, style, _now(), _now()))
        d = tmp_path / "jobs" / VID
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return VID

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video, tmp_path):
    vid = make_video()
    out = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in out, out
    written = json.loads((tmp_path / "jobs" / vid / "scene-config.json").read_text())
    assert written["subtitles"]["look"] == "tags" and written["subtitles"]["maxWords"] == 3


def test_a_broken_config_writes_nothing_and_the_scene_is_refused_on_another_style(make_video, tmp_path):
    vid = make_video()
    bad = _with(lambda d: d["sets"][0].update(room="moon-base"))
    assert "Paper Diorama video has problems" in server.write_scene_config(vid, bad)["error"]
    assert not (tmp_path / "jobs" / vid / "scene-config.json").exists()


def test_a_paper_diorama_video_never_sends_a_paid_image_request(make_video, monkeypatch):
    import httpx

    def no_call(*a, **k):
        raise AssertionError("generate_image reached the paid API")

    monkeypatch.setattr(httpx, "Client", no_call)
    monkeypatch.setattr(server, "_openai_key", lambda: "sk-test")
    vid = make_video()
    err = server.generate_image(vid, "server", "a server rack")["error"]
    assert "takes no generated images" in err and "Paper Diorama" in err


def test_a_long_pause_in_the_script_cannot_wedge_write_scene_config(make_video, tmp_path):
    """The reported case: [long pause] voiced as ~3 s of silence leaves no word to put an event on."""
    def still(d):
        d["sets"][0]["events"] = [e for e in d["sets"][0]["events"] if e["do"] != "hop"]
    cfg = _with(still)
    vid = make_video()
    # as the timeline stands, the stretch with no event is refused
    assert "nothing new happens" in server.write_scene_config(vid, copy.deepcopy(cfg))["error"]
    # the same stretch, but the narration is silent through the middle of it
    stalls = _stalls(_check(cfg))
    silent = json.loads(json.dumps(EXAMPLE_TIMELINE))
    silent["words"] = [w for w in silent["words"]
                       if not any(a + 8 < w["startFrame"] < c for a, c in stalls)]   # one word, then silence
    (tmp_path / "jobs" / vid / "timeline.json").write_text(json.dumps(silent))
    assert server._timeline_silences(vid), "the gap is read as a pause"
    out = server.write_scene_config(vid, copy.deepcopy(cfg))
    assert "error" not in out, out


def test_the_scene_on_another_style_is_refused(make_video):
    with server._conn() as con:
        con.execute("DELETE FROM videos")
    vid = make_video(style="stick")
    assert "used only when" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


# ── render_paper_props ───────────────────────────────────────────────────────

BADGE = {"w": 120, "h": 120, "pieces": [{"shape": "rect", "fill": "go", "x": 0, "y": 0, "w": 120, "h": 120, "r": 8}]}


def test_render_paper_props_refuses_what_it_cannot_preview(make_video):
    vid = make_video()
    assert "no Paper Diorama scene-config yet" in server.render_paper_props(vid)["error"]
    assert "error" not in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "has no customProps" in server.render_paper_props(vid)["error"]
    with server._conn() as con:
        con.execute("UPDATE videos SET visual_style = 'stick'")
    assert "for Paper Diorama videos" in server.render_paper_props(vid)["error"]


def test_render_paper_props_returns_the_picture_of_the_videos_own_props(make_video, monkeypatch, tmp_path):
    from PIL import Image as PILImage
    vid = make_video()
    cfg = _with(lambda d: d.update(customProps={"badge": BADGE}))
    assert "error" not in server.write_scene_config(vid, cfg)
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0, script=None):
        seen.update(spec=spec, script=script)
        PILImage.new("RGB", (1080, 1920), (232, 223, 211)).save(out_png)

    monkeypatch.setattr(server.bean_preview, "render_preview", fake_render)
    meta, image = server.render_paper_props(vid)
    assert json.loads(meta) == {"video_id": vid, "props": ["badge"]}
    assert seen["script"] == server.bean_preview.PAPER_SCRIPT and seen["spec"] == {"props": {"badge": BADGE}}
    assert image is not None
    # a prop broken in the file after the write is caught before any render
    path = tmp_path / "jobs" / vid / "scene-config.json"
    written = json.loads(path.read_text())
    written["scenes"][0]["props"]["paperDiorama"]["customProps"]["badge"]["w"] = 9000
    path.write_text(json.dumps(written))
    seen.clear()
    assert "customProps have problems" in server.render_paper_props(vid)["error"] and not seen


def test_the_preview_script_is_shipped():
    assert (REPO / "renderer/remotion" / server.bean_preview.PAPER_SCRIPT).is_file()
