"""Under the Hood (TMDEV-201): the scene-config checks that keep an unattended
agent from shipping a label pinned off its photograph, a crowded or mistimed
plate or a still video, their agreement with the renderer's contract.ts and
the style pack, their place in write_scene_config and the text audit, and the
cap on paid photographs in generate_image.

Each refusal guards something the renderer cannot fix: a pinned point the
slow push carries out of the band leaves a leader pointing at nothing, a
photograph that does not cover the band shows its edge, two chips on top of
each other cannot be read, and a 13th photograph is money the style's budget
does not allow.

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
import under_the_hood as uth
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_TS = REPO / "renderer/remotion/src/scenes/installed/underTheHood/contract.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/under_the_hood_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-under-the-hood/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("under_the_hood")["extra"]
VID = "vid_example01"


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", body)}


def _ts_array(name: str) -> tuple[str, ...]:
    src = CONTRACT_TS.read_text()
    return tuple(re.findall(r'"([\w-]+)"', re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.S).group(1)))


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_limits_timings_geometry_and_camera_match_the_renderer():
    assert _ts_block("LIMITS") == uth.LIMITS
    assert _ts_block("TIMING") == uth.TIMING
    assert _ts_block("GEOMETRY") == uth.GEOMETRY
    assert _ts_block("CAMERA") == uth.CAMERA


@pytest.mark.parametrize("ts, py", [
    ("EVENT_TYPES", "EVENT_TYPES"), ("POSES", "POSES"), ("TONES", "TONES"), ("SHAPES", "SHAPES"),
    ("ENTRANCES", "ENTRANCES"), ("STAT_SLOTS", "STAT_SLOTS"),
])
def test_the_catalogues_match_the_renderer(ts, py):
    assert _ts_array(ts) == getattr(uth, py)


def test_the_pack_lists_exactly_what_the_renderer_draws():
    assert tuple(EXTRA["poses"]) == uth.POSES
    assert tuple(EXTRA["events"]) == uth.EVENT_TYPES
    assert tuple(EXTRA["tones"]) == uth.TONES


def test_the_pack_caps_photographs_at_the_contracts_limit():
    assert tvs.pack("under_the_hood")["routing"]["images"] == uth.LIMITS["maxImages"]


def test_points_and_boxes_are_computed_the_same_way():
    for c in CASES["project_at"]:
        assert list(uth.project_at(c["plate"], c["s"], *c["uv"])) == pytest.approx(c["point"])
    for c in CASES["image_box"]:
        assert list(uth.image_box(c["plate"], c["s"])) == pytest.approx(c["box"])
    for c in CASES["plate_scale"]:
        assert uth.plate_scale(c["plate"], c["t"], c["fps"]) == pytest.approx(c["s"])
    for c in CASES["chip_box"]:
        assert list(uth.chip_box(c["text"], c["chip"])) == pytest.approx(c["box"])
    for c in CASES["stat_box"]:
        assert list(uth.stat_box(c["stat"])) == pytest.approx(c["box"])
    for c in CASES["stat_text"]:
        assert uth.stat_text(c["value"], c["decimals"], c["prefix"], c["suffix"]) == c["text"]
    for c in CASES["chart_text_width"]:
        assert uth.chart_text_width(c["chart"]) == pytest.approx(c["width"])
    for c in CASES["counter_fits"]:
        assert uth.counter_fits(c["values"]) is c["fits"]
    for c in CASES["leader_start"]:
        assert list(uth.leader_start(c["box"], c["target"])) == pytest.approx(c["point"])
    for c in CASES["overlaps"]:
        assert uth.overlaps(c["a"], c["b"]) is c["overlaps"]


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None, video_id=VID):
    return uth.check(config or EXAMPLE, 30, WORD_STARTS, EXTRA, video_id)


def _plates(cfg):
    return cfg["scenes"][0]["props"]["underTheHood"]["plates"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_plates(cfg))
    return cfg


def test_the_example_passes():
    assert _check() == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda p: p[0].update(start=3), "first plate must start at frame 0"),
    (lambda p: p[2].update(start=303), "not on a word"),
    (lambda p: p[2].update(start=136), "a plate needs at least 1.5 s"),
    (lambda p: p[1].update(image="/public/vid_other/images/screen-layers.png"), "public_path generate_image returned"),
    (lambda p: p[1].update(image="/jobs/vid_example01/images/screen-layers.png"), "public_path generate_image returned"),
    (lambda p: p[0].update(focus=[0.4, 0.5]), "does not cover the plate band"),
    (lambda p: p[0].update(focus=[0.5, 0.3]), "does not cover the plate band"),
    (lambda p: p[0].update(zoom=4), "zoom must be from 1 to 3"),
    (lambda p: p[3].update(focus=[0.5, 0.5]), "applies to a photograph"),
    (lambda p: p[4].update(enter="zoom", through=[0.5, 0.5]), "needs a previous plate with one"),
    (lambda p: p[1].pop("through"), "a zoom entrance needs through"),
    (lambda p: p[2].update(through=[0.5, 0.5]), "only for enter"),
    (lambda p: p[1].update(enter="wipe"), "enter must be one of"),
    (lambda p: p[0]["events"][0].update(pose="dab"), "pose must be one of"),
    (lambda p: p[0]["events"][0].update(frame=20), "a pose swaps on a word"),
    (lambda p: p[0]["events"][2].update(text="A label far too long"), "1 to 18 characters"),
    (lambda p: p[0]["events"][2].update(at=[0.43, 1.2]), "two numbers from 0 to 1"),
    (lambda p: p[0]["events"][2].update(at=[0.43, 0.08]), "outside the visible part of the photograph"),
    (lambda p: p[0]["events"][2].update(chip=[0.18, 0.2]), "reaches outside the plate band"),
    (lambda p: p[0]["events"][2].update(chip=[0.02, 0.3]), "reaches outside the plate band"),
    (lambda p: p[0]["events"][2].update(chip=[0.43, 0.43]), "sits on the point it labels"),
    (lambda p: p[0]["events"][3].update(chip=[0.2, 0.31]), "overlaps"),
    (lambda p: p[0]["events"][3].update(tone="red"), "tone must be one of"),
    (lambda p: p[1]["events"][2].update(region=[0.5, 0.42, 0.4, 0.52]), "u0 < u1"),
    (lambda p: p[1]["events"][2].update(shape="circle"), "shape must be one of"),
    (lambda p: p[2]["events"][1].update(count=12), "count must be 3 to 9"),
    (lambda p: p[2]["events"][4].update(values=[{"from": 1, "to": 2}] * 5), "1 to 4"),
    (lambda p: p[2]["events"][4].update(values=[{"from": -1, "to": 2}]), "whole numbers from 0"),
    (lambda p: p[1]["events"][4].update(suffix="micron"), "at most 3 characters"),
    (lambda p: p[1]["events"][4].update(label=""), "label must be 1 to 22"),
    (lambda p: p[1]["events"][4].update(place="middle"), "place must be one of"),
    (lambda p: p[1]["events"][4].update(value=9999999), "too wide for the frame"),
    (lambda p: p[1]["events"][4].update(value=123456789), "must be numbers from -9999999"),
    (lambda p: p[1]["events"][4].update(value=1e308, decimals=1), "must be numbers from -9999999"),
    (lambda p: p[1]["events"][4].update(**{"from": -9999999}), "too wide for the frame"),
    (lambda p: p[3]["events"][2].update(points=[1, 999999.5], decimals=2, prefix="$"), "too wide for the frame"),
    (lambda p: p[3]["events"][2].update(points=[1, 1e22]), "numbers from -9999999"),
    (lambda p: p[2]["events"][4].update(values=[{"from": 9999, "to": 1}] * 4), "do not fit their columns"),
    (lambda p: p[0]["events"][2].update(chip=[0.42, 0.42]), "lies under the 'Finger' chip"),
    (lambda p: p[3]["events"][2].update(points=[1]), "points must list 2 to 24"),
    (lambda p: p[3]["events"][2].update(duration=200), "duration must be 30 to 150"),
    (lambda p: p[3]["events"][2].update(frame=600, duration=150), "too late to be read"),
    (lambda p: p[1]["events"][4].update(frame=258), "too late to be read"),
    (lambda p: p[2]["events"][4].update(frame=481), "too late to be read"),
    (lambda p: p[0]["events"][1].update(text="x" * 33), "1 to 32 characters"),
    (lambda p: p[2]["events"].append({"type": "chart", "frame": 480, "points": [1, 2], "label": "x"}), "plain dark plate"),
    (lambda p: p[3]["events"].insert(0, {"type": "callout", "frame": 520, "text": "x", "at": [0.5, 0.5], "chip": [0.3, 0.4]}), "this plate has none"),
    (lambda p: p[0]["events"].insert(4, {"type": "footnote", "frame": 80, "text": "again"}), "one footnote"),
    (lambda p: p[0]["events"].append({"type": "sticker", "frame": 100}), "type must be one of"),
    (lambda p: p[0]["events"].append({"type": "footnote", "frame": 105, "text": "late"}), "too late to be read"),
    (lambda p: p[0]["events"].reverse(), "frame order"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    cfg = _with(lambda p: p[3]["events"].pop(3))   # the pose at 603 bridges the chart's draw
    assert any("Nothing new happens from frame 536 to 669" in p for p in _check(cfg))


def test_two_pose_swaps_too_close_together_read_as_a_twitch():
    cfg = _with(lambda p: p[1]["events"].insert(1, {"type": "pose", "frame": 146, "pose": "think"}))
    assert any("read as a twitch" in p for p in _check(cfg))


def test_a_zoom_through_takes_the_plates_text_away_early():
    # text at 103 is readable before a plain cut at 123 (20 frames to read it) ...
    ok = _with(lambda p: (p[1].update(enter="cut"), p[1].pop("through"),
                          p[0]["events"].append({"type": "footnote", "frame": 103, "text": "x"}), p[0]["events"].pop(1)))
    assert _check(ok) == []
    # ... but not before a zoom-through, which takes the labels away 6 frames before the cut
    late = _with(lambda p: (p[0]["events"].append({"type": "footnote", "frame": 103, "text": "x"}), p[0]["events"].pop(1)))
    assert any("too late to be read" in p for p in _check(late))


def test_a_stat_or_counters_timed_to_finish_in_time_pass():
    # a stat needs its count (24) and reading time (20) before the cut at 299; counters 16 + 20 before 515
    assert _check(_with(lambda p: p[1]["events"][4].update(frame=255))) == []
    assert _check(_with(lambda p: (p[2]["events"][4].update(frame=479), p[2]["events"][5].update(frame=485)))) == []


def test_a_zoom_into_a_chart_plate_is_allowed_and_through_belongs_to_the_previous_photograph():
    cfg = _with(lambda p: p[3].update(enter="zoom", through=[0.49, 0.47]))
    assert _check(cfg) == []


def test_a_refused_plates_events_still_count_against_the_stillness_rule():
    problems = _check(_with(lambda p: p[3].update(focus=[0.5, 0.5])))
    assert any("applies to a photograph" in x for x in problems)
    assert not any("Nothing new happens" in x for x in problems), problems


def test_a_point_pushed_out_by_a_zoom_entrances_settle_is_refused():
    # v 0.83 on plate 2 stays inside the band through the whole push, but not at the 1.25x
    # the plate enters at: a callout timed on the plate's first frame would point outside it
    def at_entry(p):
        p[1]["events"][0].update(frame=123, at=[0.5, 0.83], chip=[0.2, 0.31])
    assert any("outside the visible part of the photograph when it appears" in x for x in _check(_with(at_entry)))
    def later(p):
        p[1]["events"][0].update(frame=146, at=[0.5, 0.83], chip=[0.2, 0.31])
    assert not any("outside the visible part" in x for x in _check(_with(later)))


def test_too_many_photographs_are_refused():
    cfg = copy.deepcopy(EXAMPLE)
    plates = _plates(cfg)
    # thirteen distinct photographs on plates two seconds apart, inside one long video
    cfg["totalFrames"] = 3900
    cfg["scenes"][0]["durationInFrames"] = 3900
    plates[:] = [{"start": k * 300, "image": f"/public/{VID}/images/p{k}.png",
                  "events": [{"type": "pose", "frame": k * 300 + 10, "pose": "point" if k % 2 else "explain"},
                             {"type": "pose", "frame": k * 300 + 100, "pose": "think"},
                             {"type": "pose", "frame": k * 300 + 190, "pose": "explain" if k % 2 else "point"},
                             {"type": "pose", "frame": k * 300 + 280, "pose": "think"}]}
                 for k in range(13)]
    problems = uth.check(cfg, 30, [], EXTRA, VID)
    assert any("13 different photographs" in p for p in problems), problems
    plates[12]["image"] = plates[0]["image"]   # a reused photograph is free
    assert uth.check(cfg, 30, [], EXTRA, VID) == []


def test_too_many_elements_on_one_plate_are_refused():
    def crowd(p):
        for k in range(5):
            p[0]["events"].append({"type": "outline", "frame": 100 + k, "region": [0.4, 0.45, 0.5, 0.5]})
    assert any("at most 6 fit" in p for p in _check(_with(crowd)))


def test_the_scene_use_rule():
    scenes = copy.deepcopy(EXAMPLE["scenes"])
    assert uth.check_scene_use("under_the_hood", scenes) == ""
    assert "visual_style is under_the_hood" in uth.check_scene_use("stick", scenes)
    scenes[0]["type"] = "TextReveal"
    assert "exactly one scene" in uth.check_scene_use("under_the_hood", scenes)
    assert uth.check_scene_use("stick", [{"src": "intro", "type": "generated"}]) == ""


def test_plate_windows_and_images():
    assert uth.plate_windows(EXAMPLE) == [(0, 123), (123, 299), (299, 515), (515, 721), (721, 858)]
    assert uth.plate_windows({"scenes": []}) == []


@pytest.mark.parametrize("mutate", [
    lambda p: p[0].update(start="0"),
    lambda p: p[0].update(focus="middle"),
    lambda p: p[0]["events"][2].update(text=7),
    lambda p: p[0]["events"][2].update(chip=None),
    lambda p: p[1]["events"][4].update(value="5"),
    lambda p: p[3]["events"][2].update(points=["a", "b"]),
    lambda p: p.__setitem__(0, "plate"),
])
def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash(mutate):
    problems = _check(_with(mutate))
    assert problems and all(isinstance(p, str) for p in problems)


def test_the_text_audit_samples_each_plate_away_from_the_zoom():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = uth.plate_windows(EXAMPLE)
    assert len(passes) == len(windows)
    for p, (start, end) in zip(passes, windows):
        last = p["first"] + p["step"] * (p["count"] - 1)
        assert start <= p["first"] and last < end - uth.TIMING["zoomOut"]


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make(video_id=VID, style="under_the_hood", images=("finger-over-glass", "screen-layers", "electrode-grid"),
             size=(64, 64)):
        from PIL import Image
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'how a touchscreen feels your finger', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        for name in images:
            Image.new("RGB", size).save(d / "images" / f"{name}.png")
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions_and_each_photographs_shape(make_video):
    vid = make_video(size=(64, 80))
    cfg = copy.deepcopy(EXAMPLE)
    del cfg["subtitles"]
    # a taller photograph covers the band with room to spare, so the example still fits
    result = server.write_scene_config(vid, cfg)
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("under_the_hood")["captions"]
    assert written["subtitles"]["look"] == "selection"
    assert written["canvas"] == "dark"
    plates = _plates(written)
    assert [p.get("aspect") for p in plates] == [1.25, 1.25, 1.25, None, 1.25]


def test_setting_only_emphasis_keeps_the_styles_caption_look(make_video):
    vid = make_video()
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    sub = json.loads(pathlib.Path(result["path"]).read_text())["subtitles"]
    assert sub["emphasis"] == [4, 15, 28, 36, 58] and sub["look"] == "selection"


def test_the_photographs_shape_decides_whether_a_point_fits(make_video):
    # a wide photograph is shorter than the band at zoom 1, so its edge would show
    vid = make_video(size=(100, 60))
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "does not cover the plate band" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_validate_job_finds_a_photograph_that_changed_shape(make_video):
    from PIL import Image
    vid = make_video()
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert server._uth_aspect_errors(vid, written) == []
    Image.new("RGB", (64, 96)).save(server.JOBS_DIR / vid / "images" / "screen-layers.png")
    errs = server._uth_aspect_errors(vid, written)
    assert len(errs) == 1 and "screen-layers.png" in errs[0] and "write_scene_config" in errs[0]


def test_another_style_cannot_use_the_scene(make_video):
    vid = make_video(style="motion_graphics")   # a dark style, so the canvas rule does not answer first
    assert "visual_style is under_the_hood" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_an_under_the_hood_video_cannot_be_built_from_other_scenes(make_video):
    vid = make_video()
    cfg = {"totalFrames": 858, "scenes": [{"type": "generated", "src": "intro", "startFrame": 0, "durationInFrames": 858}]}
    assert "exactly one scene" in server.write_scene_config(vid, cfg)["error"]


@pytest.mark.parametrize("look, ok", [("selection", True), ("plain", True), ("box", False), (1, False)])
def test_the_caption_look_is_checked(look, ok):
    err = server._validate_subtitles({"look": look})
    assert (err == "") is ok, err


# ── the cap on paid photographs ──────────────────────────────────────────────

def test_a_thirteenth_photograph_is_refused_before_the_paid_call(make_video, monkeypatch):
    vid = make_video(images=[f"p{k}" for k in range(12)])
    monkeypatch.setattr(server, "_openai_key", lambda: "sk-test")
    monkeypatch.setattr(server, "_guard_scene_work", lambda *a, **k: None)

    class NoCall:
        def __init__(self, *a, **k):
            raise AssertionError("the paid call went out")

    import httpx
    monkeypatch.setattr(httpx, "Client", NoCall)
    result = server.generate_image(vid, "p12", "a thirteenth photograph", aspect_ratio="1:1")
    assert "the most a video may use (12)" in result["error"]


def test_regenerating_a_photograph_and_other_styles_are_not_capped(make_video):
    vid = make_video(images=[f"p{k}" for k in range(12)])
    images = server.JOBS_DIR / vid / "images"
    assert server._image_cap_error(vid, "p3", images) == ""          # a regeneration replaces p3
    assert "the most a video may use" in server._image_cap_error(vid, "p12", images)
    other = make_video("vid_mixed", style="auto", images=[f"p{k}" for k in range(12)])
    assert server._image_cap_error(other, "p12", server.JOBS_DIR / other / "images") == ""
