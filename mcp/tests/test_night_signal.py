"""Night Signal: the scene-config checks that keep an unattended agent from
shipping a crowded, mistimed or still warning video, their agreement with the
renderer's contract.ts and stage.ts and the style pack, and their place in
write_scene_config and the text audit.

Each refusal guards something the renderer cannot fix: two red threats make
the warning unclear, a part nobody drew renders nothing, two things in one
slot overlap, a card cut before it can be read is lost, five seconds with
nothing new is a dead screen, and a scene that starts under an insert is never
seen.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import night_signal as ns
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/night_signal_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-night-signal/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("night_signal")["extra"]
TS = (REPO / "renderer/remotion/src/scenes/installed/nightSignal/contract.ts").read_text()


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    c = CASES["constants"]
    assert ns.LIMITS == c["LIMITS"]
    assert ns.TIMING == c["TIMING"]
    assert ns.CAMERA == c["CAMERA"]
    assert ns.GEOMETRY == c["GEOMETRY"]


def test_the_catalogues_match_the_renderer_and_the_pack():
    for name, py in [("SCENE_KINDS", ns.SCENE_KINDS), ("SETTINGS", ns.SETTINGS), ("SLOTS", ns.SLOTS),
                     ("SCREENS", ns.SCREENS), ("MARKS", ns.MARKS), ("CUTS", ns.CUTS), ("BUBBLES", ns.BUBBLES),
                     ("SHAPES", ns.SHAPES), ("TONES", ns.TONES)]:
        line = next(ln for ln in TS.splitlines() if ln.startswith(f"export const {name} = ["))
        assert tuple(line.split("[", 1)[1].split("]")[0].replace('"', "").replace(" ", "").split(",")) == py, name
    assert EXTRA["sceneKinds"] == list(ns.SCENE_KINDS)
    assert EXTRA["slots"] == list(ns.SLOTS)
    assert EXTRA["tones"] == list(ns.TONES)
    assert {"person", "person_phone", "dog", "door", "qr", "phone"} <= ns.library(EXTRA)


def test_events_still_stretches_tears_and_the_timecode_are_worked_out_the_same_way():
    data = CASES["data"]
    assert [ns.event_frames(s) for s in data["scenes"]] == CASES["event_frames"]
    assert ns.quiet_spans(data, CASES["total"]) == CASES["quiet_spans"]
    for case in CASES["tear_at"]:
        got = ns.tear_at(data, case["frame"])
        assert (list(got) if got else None) == case["tear"], case["frame"]
    for case in CASES["timecode"]:
        assert ns.timecode(case["clock"], case["frame"], 30) == case["text"]
    for case in CASES["fit_font_size"]:
        assert ns.fit_font_size(case["text"], case["size"]) == case["fit"]


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None, quiet=()):
    return ns.check(config or EXAMPLE, 30, WORD_STARTS, EXTRA, "vid_example", quiet=quiet)


def _data(cfg):
    return cfg["scenes"][0]["props"]["nightSignal"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _scene(d, kind, k=0):
    return [s for s in d["scenes"] if s["kind"] == kind][k]


def test_the_example_passes():
    assert _check() == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(file={"number": 0, "title": "X"}), "file must be"),
    (lambda d: d.update(clock="25:00"), "clock must be"),
    (lambda d: d.update(colour="red"), "unknown field"),
    (lambda d: d["scenes"].__setitem__(slice(1, None), []), "scenes must list"),
    (lambda d: d["scenes"][0].update(start=4), "first scene must start at frame 0"),
    (lambda d: d["scenes"].insert(0, d["scenes"].pop(1)), "first scene must"),
    (lambda d: d["scenes"][1].update(kind="poster"), "kind is one of"),
    (lambda d: d["scenes"][0]["items"][0].update(what="unicorn"), "is not a library part"),
    (lambda d: d["scenes"][0]["items"][0].update(slot="top"), "slot must be one of"),
    (lambda d: d["scenes"][0]["items"][0].update(slot="right"), "two things stand in the right slot"),
    (lambda d: d["scenes"][0]["items"][0].update(threat=True), "red marks one thing"),
    (lambda d: d["scenes"][0]["items"][0].update(redAt=40), "redAt is for the threat"),
    (lambda d: d["scenes"][0]["items"][0].update(to={"slot": "right", "at": 40}), "where something already stands"),
    (lambda d: d["scenes"][0]["connector"].update(to="center"), "joins two different slots"),
    (lambda d: d["scenes"][0]["bubble"].update(icon="spaceship"), "the bubble's icon"),
    (lambda d: d["scenes"][0]["bubble"].update(at=3), "not on a word"),
    (lambda d: _scene(d, "rule").update(number=100), "number must be"),
    (lambda d: _scene(d, "rule").update(lines=["A VERY LONG RULE LINE"]), "lines must list"),
    (lambda d: _scene(d, "camera").update(label="A camera label far too long to fit"), "label must be"),
    (lambda d: _scene(d, "camera")["button"].update(text="UNLOCKED"), "button must be"),
    (lambda d: _scene(d, "phone").update(screen="video"), "screen must be one of"),
    (lambda d: _scene(d, "phone").update(lines=["a", "b", "c", "d"]), "lines must list"),
    (lambda d: _scene(d, "phone")["mark"].update(kind="star"), "mark must be"),
    (lambda d: _scene(d, "steps").update(steps=[{"text": "Only one", "at": _scene(d, "steps")["start"]}]),
     "steps must list"),
    (lambda d: _scene(d, "steps")["steps"].reverse(), "step 2: at must be"),
    (lambda d: d["scenes"][1].update(cut="fade"), "cut must be one of"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_scene_too_short_to_see_is_refused():
    cfg = _with(lambda d: d["scenes"][2].update(start=d["scenes"][1]["start"] + 30))
    assert any("needs at least 1.5 s" in p for p in _check(cfg))


def test_a_card_cut_before_it_can_be_read_is_refused():
    cfg = copy.deepcopy(EXAMPLE)
    d = _data(cfg)
    late = d["scenes"][2]["start"] - 10
    d["scenes"][1]["slashAt"] = late
    problems = ns.check(cfg, 30, WORD_STARTS + [late], EXTRA, "vid_example")
    assert any("frames to read it" in p for p in problems), problems


def test_green_is_used_once():
    def two_checks(d):
        phone = _scene(d, "phone")
        phone["mark"]["kind"] = "check"
        d["scenes"].insert(d["scenes"].index(phone) + 1, copy.deepcopy(phone))
        d["scenes"][d["scenes"].index(phone) + 1]["start"] = phone["mark"]["at"] + 40
    problems = _check(_with(two_checks))
    assert any("Green is used once" in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    def still(d):
        server_scene = _scene(d, "tableau", 1)
        for key in ("connector", "bubble"):
            server_scene.pop(key)
        server_scene["items"][1].pop("redAt")
    problems = _check(_with(still))
    assert any("nothing new happens" in p for p in problems), problems


@pytest.mark.parametrize("shape, fragment", [
    ({"shape": "circle", "cx": 0, "cy": -50, "r": 0, "tone": "ink"}, "a circle needs"),
    ({"shape": "circle", "cx": 0, "cy": 50, "r": 10, "tone": "ink"}, "a circle needs"),
    ({"shape": "rect", "x": -50, "y": -100, "w": 300, "h": 50, "tone": "ink"}, "a rect needs"),
    ({"shape": "circle", "cx": 190, "cy": -50, "r": 30, "tone": "ink"}, "the whole circle"),
    ({"shape": "line", "points": [[0, 0]], "width": 10, "tone": "ink"}, "a line needs"),
    ({"shape": "line", "points": [[195, -10], [195, -100]], "width": 20, "tone": "ink"}, "half its width"),
    ({"shape": "line", "points": [[0, 0], [0, -50]], "width": 90, "tone": "ink"}, "width from 2 to 60"),
    ({"shape": "poly", "points": [[0, 0], [10, -10]], "tone": "ink"}, "a poly needs"),
    ({"shape": "star", "tone": "ink"}, "shape must be one of"),
    ({"shape": "circle", "cx": 0, "cy": -50, "r": 10, "tone": "blue"}, "tone must be one of"),
])
def test_a_bad_custom_part_is_refused(shape, fragment):
    def add(d):
        d["customParts"] = [{"id": "sign", "shapes": [shape]}]
    problems = _check(_with(add))
    assert any(fragment in p for p in problems), problems


def test_a_custom_part_can_stand_in_a_scene_and_cannot_take_a_library_name():
    part = {"id": "parking_meter", "shapes": [{"shape": "line", "points": [[0, 0], [0, -180]], "width": 14, "tone": "grey"},
                                               {"shape": "rect", "x": -40, "y": -260, "w": 80, "h": 90, "r": 14, "tone": "ink"}]}

    def use(d):
        d["customParts"] = [part]
        d["scenes"][0]["items"].append({"what": "parking_meter", "slot": "center"})
    assert _check(_with(use)) == []

    def clash(d):
        d["customParts"] = [{**part, "id": "door"}]
    assert any("not a library name" in p for p in _check(_with(clash)))


def test_nothing_starts_inside_an_insert_and_an_insert_is_not_a_still_stretch():
    d = _data(EXAMPLE)
    cam = _scene(d, "camera")
    phone = d["scenes"][d["scenes"].index(cam) + 1]
    # A window over the camera scene's quiet tail, ending before the next scene starts.
    last = ns.event_frames(cam)[-1]
    quiet = [(last + 12, phone["start"] - 4)]
    assert _check(quiet=quiet) == []
    # A window over the camera's cross-out is refused.
    over = [(cam["button"]["crossAt"] - 10, cam["button"]["crossAt"] + 50)]
    assert any("inside an insert" in p for p in _check(quiet=over))
    # A window over a scene's start is refused.
    over_start = [(phone["start"] - 20, phone["start"] + 40)]
    assert any("starts at frame" in p and "inside an insert" in p for p in _check(quiet=over_start))
    # A scene may start on a window's end (its tear's first frames ride the insert's way out) ...
    assert _check(quiet=[(last + 12, phone["start"])]) == []
    # ... but a tear may not run on into a window that starts right after the scene does.
    assert any("its tear runs" in p for p in _check(quiet=[(phone["start"] + 1, phone["start"] + 30)]))


def test_the_scene_use_rule():
    assert ns.check_scene_use("night_signal", EXAMPLE["scenes"]) == ""
    assert "visual_style is night_signal" in ns.check_scene_use("stick", EXAMPLE["scenes"])
    two = EXAMPLE["scenes"] + [{"type": "generated", "source": "installed", "src": "KenBurnsImage"}]
    assert "exactly one scene" in ns.check_scene_use("night_signal", two)


def test_the_text_audit_samples_every_scene_once_it_has_settled():
    windows = ns.scene_windows(EXAMPLE)
    assert len(windows) == len(_data(EXAMPLE)["scenes"])
    passes, _ = text_audit.plan_passes(EXAMPLE)
    firsts = [p["first"] for p in passes]
    assert firsts == [w[0] for w in windows]
    rule = _data(EXAMPLE)["scenes"][1]
    assert windows[1][0] >= rule["slashAt"]


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")

    def make(video_id, style="night_signal"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'a stranger sends you a QR code', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_ns1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("night_signal")["captions"]


def test_a_broken_config_is_refused_before_anything_is_written(make_video):
    vid = make_video("vid_ns2")
    cfg = _with(lambda d: d["scenes"][0]["items"][0].update(what="unicorn"))
    result = server.write_scene_config(vid, cfg)
    assert "Night Signal video has problems" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_night_signal_scene(make_video):
    vid = make_video("vid_ns3", style="motion_graphics")
    assert "visual_style is night_signal" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_letter_spacing_is_a_caption_key_in_its_range(make_video):
    vid = make_video("vid_ns4")
    cfg = copy.deepcopy(EXAMPLE)
    cfg["subtitles"] = {"letterSpacing": 0.1}
    assert "error" not in server.write_scene_config(vid, cfg)
    cfg["subtitles"] = {"letterSpacing": 0.9}
    assert "letterSpacing" in server.write_scene_config(vid, cfg)["error"]
