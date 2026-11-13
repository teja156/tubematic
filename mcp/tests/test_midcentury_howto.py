"""Mid-century How-To (TMDEV-233): the scene-config checks that keep an
unattended agent from shipping a mistimed, crowded or still video, their
agreement with the renderer's contract.ts and stage.ts (through the shared
fixture character-tools/sync-contract.mjs writes), and their place in
write_scene_config, validate_job, render_style_props, the picture checks and
the text audit.

Each refusal guards something the renderer cannot fix: a cut or a press off
the words reads as out of sync, an object the library does not draw renders
nothing, a label over an object hides it, an object over the presenter is a
pile-up, and more than three seconds with nothing new is a held frame.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import character_styles
import midcentury_howto as mc
import picture_checks
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/midcentury_howto_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-midcentury-howto/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
WORDS = [w["word"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("midcentury_howto")["extra"]
C = CASES["constants"]


def _data(cfg=None) -> dict:
    return (cfg or EXAMPLE)["scenes"][0]["props"]["midcenturyHowTo"]


def _with(mutate) -> dict:
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _check(cfg, quiet=(), sources=None, video_id=""):
    return mc.check(cfg, 30, WORD_STARTS, WORDS, EXTRA, video_id, sources, quiet=quiet)


def _shot(cfg, start):
    return next(s for s in _data(cfg)["shots"] if s["start"] == start)


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    assert C["LIMITS"] == mc.LIMITS
    assert C["TIMING"] == mc.TIMING
    assert C["GEOMETRY"] == mc.GEOMETRY
    assert tuple(C["GROUNDS"]) == mc.GROUNDS
    for name in ("EVENT_TYPES", "POSES", "SUMMARY_POSES", "AIM_POSES", "FACES", "OUTFITS", "HAIRS", "SIDES", "ENTRANCES"):
        assert tuple(C[name]) == getattr(mc, name), name
    assert (C["OBJECT_SCALE"]["min"], C["OBJECT_SCALE"]["max"]) == mc.OBJECT_SCALE
    assert C["CUSTOM"] == mc.CUSTOM
    assert {k: (v["w"], v["h"]) for k, v in C["OBJECTS"].items()} == mc.OBJECT_BOXES


def test_the_pack_lists_exactly_what_the_renderer_draws():
    assert EXTRA["objects"] == {k: {"text": v["text"], "acts": v["acts"]} for k, v in C["OBJECTS"].items()}
    assert EXTRA["grounds"] == list(C["GROUNDS"])
    assert EXTRA["poses"] == C["POSES"] and EXTRA["summary_poses"] == C["SUMMARY_POSES"]
    for key in ("faces", "outfits", "hairs", "sides", "entrances"):
        assert EXTRA[key] == C[key.upper()], key


def test_the_geometry_matches_the_renderer():
    for c in CASES["object_box"]:
        assert mc.object_box(c["object"], c["x"], c["y"], c["scale"]) == pytest.approx(tuple(c["box"]))
    for c in CASES["label_box"]:
        assert mc.label_box(c["text"], c["x"], c["y"]) == pytest.approx(tuple(c["box"]))
    for c in CASES["inset_box"]:
        assert mc.inset_box(c["x"], c["y"]) == pytest.approx(tuple(c["box"]))
    for c in CASES["presenter_box"]:
        assert mc.presenter_box(c["side"]) == pytest.approx(tuple(c["box"]))
    for c in CASES["in_reach"]:
        assert mc.in_reach(c["side"], c["x"], c["y"]) is c["reach"]
    assert any(c["reach"] for c in CASES["in_reach"]) and not all(c["reach"] for c in CASES["in_reach"])
    for c in CASES["press_point"]:
        assert mc.press_point(c["object"], 540, 960, 1.2, c["act"]) == pytest.approx(tuple(c["point"]))
    for c in CASES["screen_lines"]:
        assert mc.screen_lines(c["text"]) == c["lines"]
    for c in CASES["blink"]:
        assert mc.blink_at(c["frame"], c["seed"]) is c["blink"]


def test_the_style_is_registered_for_the_server_the_checks_and_the_audit():
    assert character_styles.BY_ID["midcentury_howto"] is mc
    assert tvs.pack("midcentury_howto")["mascot"] is False
    assert "midcentury_howto" in tvs.NO_MASCOT_STYLES


# ── the worked example and the refusals ──────────────────────────────────────

def test_the_worked_example_passes():
    assert _check(EXAMPLE) == []


S1 = _data()["steps"][0]["start"]
S3 = _data()["steps"][2]["start"]
SUM = _data()["summary"]


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(title="x" * 31), "title must be text of 1 to 30"),
    (lambda d: d.update(kicker="x" * 23), "kicker must be text of at most 22"),
    (lambda d: d["presenter"].update(outfit="plaid"), "presenter.outfit must be one of"),
    (lambda d: d.update(steps=d["steps"][:1]), "steps must list 2 to 6"),
    (lambda d: d["steps"][1].update(header="x" * 19), "header must be text of 1 to 18"),
    (lambda d: d["steps"][1].update(ground="plaid"), "ground must be one of"),
    (lambda d: d["steps"][1].update(start=d["steps"][1]["start"] + 1), "where no shot starts"),
    (lambda d: (d["shots"][1].update(start=20), d["steps"][0].update(start=20)), "opens on the title card for at least"),
    (lambda d: d.update(summary=SUM + 1), "summary starts at frame"),
    (lambda d: d["shots"][-1]["events"].append({"type": "label", "frame": SUM + 20, "text": "Done", "x": 0.3, "y": 0.5}),
     "only the presenter's poses go in its shot"),
    (lambda d: d["shots"][-1]["events"][0].update(pose="point"), "keeps his arms clear of the step list"),
    (lambda d: d["shots"][-1].update(presenter="left"), "the presenter stands on the right"),
    (lambda d: d["shots"][3]["events"].insert(0, {"type": "pose", "frame": S3, "pose": "stand", "face": "smile"}),
     "this shot has no presenter"),
    (lambda d: d["shots"][1]["events"][1].update(pose="wave"), "leave it out of a 'wave' pose"),
    (lambda d: d["shots"][1]["events"][1].update(at="nothing"), "which is not on stage yet"),
    (lambda d: d["shots"][1]["events"][0].update(object="spaceship"), "object must be from the library"),
    (lambda d: d["shots"][1]["events"][0].update(x=0.2), "overlaps the presenter on the left"),
    (lambda d: d["shots"][1]["events"][0].update(y=0.2), "reaches outside the stage"),
    (lambda d: d["shots"][1]["events"][0].update(text="x" * 81), "text must be at most 80"),
    (lambda d: d["shots"][2]["events"][1].update(text="hi"), "has no text slot"),
    (lambda d: d["shots"][1]["events"][-1].update(act="row9"), "acts are row1, row2, row3, done"),
    (lambda d: d["shots"][1]["events"][-1].update(frame=S1 + 2), "list the events in frame order"),
    (lambda d: d["shots"][3]["events"][1].update(frame=S3 + 3), "starts at frame"),
    (lambda d: d["shots"][3]["events"][3].update(text="x" * 11), "a short number or word, 1 to 10"),
    (lambda d: d["shots"][3]["events"][3].update(x=0.5, y=0.45), "it overlaps the keypad object"),
    (lambda d: d["shots"][3]["events"][-1].update(text="a stolen password is"), "repeats the narration"),
    (lambda d: d["shots"][0]["events"].pop(2), "Nothing changes from frame"),
])
def test_each_rule_is_refused_with_a_reason(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_press_lands_on_a_word_and_keeps_its_distance():
    cfg = _with(lambda d: d["shots"][1]["events"].append({"type": "press", "frame": _shot(EXAMPLE, S1)["events"][-1]["frame"] + 4, "target": "phone"}))
    assert any("presses need 16 frames between them" in p or "not a word" in p or "on a word" in p for p in _check(cfg))


def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash():
    for mutate in (
        lambda d: d["shots"][1]["events"][1].update(at=["phone"]),
        lambda d: d["shots"][1]["events"][-1].update(target=7),
        lambda d: d["steps"][0].update(header=None),
        lambda d: d.update(presenter="tall"),
        lambda d: d["shots"][2].update(events="none"),
        lambda d: d["shots"][1]["events"][0].update(scale="big"),
    ):
        problems = _check(_with(mutate))
        assert problems and all(isinstance(p, str) for p in problems)


def test_scene_use_rules():
    assert "used only when the video's visual_style is midcentury_howto" in mc.check_scene_use("stick", EXAMPLE["scenes"])
    assert mc.check_scene_use("stick", []) == ""
    two = EXAMPLE["scenes"] + [{"type": "generated", "source": "generated", "src": "vid/x", "startFrame": 0, "durationInFrames": 10}]
    assert "exactly one scene" in mc.check_scene_use("midcentury_howto", two)


# ── inserts ──────────────────────────────────────────────────────────────────

def test_nothing_starts_inside_an_insert_and_the_window_is_not_still():
    press = next(e for e in _shot(EXAMPLE, S1)["events"] if e["type"] == "press")["frame"]
    problems = _check(EXAMPLE, quiet=[(press - 5, press + 40)])
    assert any("inside an insert" in p for p in problems)
    # A long window with nothing of the main style in it is not a still stretch.
    cfg = _with(lambda d: d["shots"][0]["events"].pop(2))
    still = [p for p in _check(cfg) if "Nothing changes" in p]
    a, b = (int(x) for x in still[0].split("frame ")[1].split(" (")[0].split(" to "))
    assert not any("Nothing changes" in p for p in _check(cfg, quiet=[(a + 10, b - 10)]))


# ── custom props ─────────────────────────────────────────────────────────────

ALARM = (REF / "example-prop-alarm.tsx").read_text()


def _with_alarm(vid="vid_mc1") -> dict:
    def add(d):
        d["customProps"] = [{"id": "alarm", "src": f"{vid}/prop-alarm", "w": 260, "h": 260, "acts": ["beep"]}]
        d["shots"][2]["events"].append({"type": "object", "frame": d["shots"][2]["events"][-1]["frame"],
                                        "id": "alarm", "object": "alarm", "x": 0.85, "y": 0.4, "scale": 0.6})
        d["shots"][2]["events"].sort(key=lambda e: e["frame"])
    return _with(add)


def test_the_example_custom_prop_passes_the_source_rules():
    cfg = _with_alarm()
    assert [p for p in _check(cfg, sources={"vid_mc1/prop-alarm": ALARM}, video_id="vid_mc1") if "customProps" in p] == []


@pytest.mark.parametrize("bad, fragment", [
    ("const f = useCurrentFrame();", "a React or Remotion hook"),
    ('<filter id="x" />', "an SVG filter"),
    ('strokeDasharray="4 4"', "a dashed stroke"),
    ("Math.random()", "randomness or the clock"),
    ('import x from "../../installed/beanExplainer/bean";', "imports ../../installed/beanExplainer/bean"),
])
def test_a_custom_prop_breaking_a_source_rule_is_refused(bad, fragment):
    problems = _check(_with_alarm(), sources={"vid_mc1/prop-alarm": ALARM + "\n" + bad}, video_id="vid_mc1")
    assert any(fragment in p for p in problems), problems


# ── write_scene_config, validate_job, render_style_props ─────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")

    def make(video_id, style="midcentury_howto"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'turn on 2FA', 'VOICE_READY', ?, ?, ?)", (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_mc1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("midcentury_howto")["captions"]


def test_a_broken_config_is_refused_by_name(make_video):
    vid = make_video("vid_mc1")
    cfg = _with(lambda d: d["steps"][1].update(ground="plaid"))
    assert server.write_scene_config(vid, cfg)["error"].startswith("The Mid-century How-To video has problems:")


def test_another_style_may_not_use_the_scene(make_video):
    vid = make_video("vid_mc2", style="stick")
    assert "used only when the video's visual_style is midcentury_howto" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_write_scene_config_and_validate_job_read_the_prop_files(make_video, tmp_path):
    vid = make_video("vid_mc1")
    cfg = _with_alarm()
    assert "write it with write_scene_file first" in server.write_scene_config(vid, copy.deepcopy(cfg))["error"]
    folder = tmp_path / "generated" / vid
    folder.mkdir(parents=True)
    (folder / "prop-alarm.tsx").write_text(ALARM)
    assert "error" not in server.write_scene_config(vid, copy.deepcopy(cfg))
    assert server._character_custom_prop_errors(vid, cfg) == []
    (folder / "prop-alarm.tsx").write_text(ALARM + "\nconst t = useState(0);")
    assert any("a React or Remotion hook" in e for e in server._character_custom_prop_errors(vid, cfg))
    assert "_character_custom_prop_errors(video_id, scene_config)" in pathlib.Path(server.__file__).read_text()


def test_render_style_props_refuses_what_it_cannot_preview(make_video):
    assert "is for Mid-century How-To" in server.render_style_props(make_video("vid_rp1", style="stick"))["error"]
    vid = make_video("vid_rp2")
    assert "no Mid-century How-To scene-config yet" in server.render_style_props(vid)["error"]
    assert "error" not in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "lists no customProps" in server.render_style_props(vid)["error"]


def test_render_style_props_returns_the_picture(make_video, tmp_path, monkeypatch):
    from PIL import Image as PILImage
    vid = make_video("vid_mc1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "prop-alarm.tsx").write_text(ALARM)
    assert "error" not in server.write_scene_config(vid, _with_alarm())
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0, script=None):
        seen["spec"], seen["script"] = spec, script
        PILImage.new("RGB", (1080, 1920), (127, 156, 192)).save(out_png)

    monkeypatch.setattr(server.bean_preview, "render_preview", fake_render)
    result = server.render_style_props(vid)
    assert isinstance(result, list) and json.loads(result[0])["props"] == ["alarm"]
    assert seen["spec"]["style"] == "midcentury_howto"
    assert seen["spec"]["props"][0]["src"] == "vid_mc1/prop-alarm"
    assert seen["script"] == server.bean_preview.CHARACTER_SCRIPT


def test_render_style_props_waits_its_turn_behind_heavy_checks(make_video, tmp_path, monkeypatch):
    vid = make_video("vid_mc1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "prop-alarm.tsx").write_text(ALARM)
    assert "error" not in server.write_scene_config(vid, _with_alarm())
    monkeypatch.setattr(server, "HEAVY_CHECK_WAIT_SECS", 0.05)
    assert server._heavy_checks_lock.acquire(timeout=1)
    try:
        assert "call render_style_props again" in server.render_style_props(vid)["error"]
    finally:
        server._heavy_checks_lock.release()


def test_the_preview_script_knows_this_style():
    script = (REPO / "renderer/remotion" / server.bean_preview.CHARACTER_SCRIPT).read_text()
    assert 'midcentury_howto: { module: "midcenturyHowTo/MidcenturySheet", component: "MidcenturyPropPreview" }' in script


# ── picture checks and the text audit ────────────────────────────────────────

def test_the_picture_checks_read_this_style():
    assert picture_checks.style_of(EXAMPLE) == "midcentury_howto"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    bare = _with(lambda d: d["shots"][0]["events"].pop(0))
    assert "the title card has no object" in picture_checks.first_frame_warnings(bare)[0]
    frames = picture_checks.change_frames("midcentury_howto", EXAMPLE)
    label = next(e["frame"] for e in _shot(EXAMPLE, S3)["events"] if e["type"] == "label")
    press = next(e["frame"] for e in _shot(EXAMPLE, S1)["events"] if e["type"] == "press")
    assert press in frames and label not in frames


def test_the_text_audit_samples_each_shot_once_settled():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = mc.audit_windows(EXAMPLE)
    assert len(windows) == len(_data()["shots"])
    assert [p["first"] for p in passes] == [w[0] for w in windows]
    starts = [s["start"] for s in _data()["shots"]]
    assert all(w[0] >= s + mc.TIMING["headerIn"] for w, s in zip(windows, starts))
