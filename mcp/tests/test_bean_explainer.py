"""Bean Explainer (TMDEV-198): the scene-config checks that keep an unattended
agent from shipping a mistimed, crowded or still video, their agreement with
the renderer's contract.ts and the style pack, and their place in
write_scene_config and the text audit.

Each refusal guards something the renderer cannot fix: a cut or a pose off the
words reads as out of sync, a prop the library does not draw renders nothing,
a label over a prop hides it, more than three seconds with nothing new is the
held frame the look exists to avoid, and a label that repeats the narration
duplicates the captions.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import bean_explainer as be
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_TS = REPO / "renderer/remotion/src/scenes/installed/beanExplainer/contract.ts"
DRAWINGS_TS = REPO / "renderer/remotion/src/scenes/installed/beanExplainer/props/index.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/bean_explainer_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-bean-explainer/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
WORDS = [w["word"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("bean_explainer")["extra"]


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    return {k: float(v) if "." in v else int(v)
            for k, v in re.findall(r"^\s*(\w+):\s*([\d.]+),", body, re.M)}


def _ts_array(name: str) -> list[str]:
    src = CONTRACT_TS.read_text()
    return re.findall(r'"([\w-]+)"', re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.S).group(1))


def _ts_keys(name: str) -> list[str]:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    return re.findall(r"^\s*(\w+):", body, re.M)


def _ts_props() -> dict:
    return {m.group(1): {"w": int(m.group(2)), "h": int(m.group(3)), "text": int(m.group(4)),
                         "acts": re.findall(r'"(\w+)"', m.group(5))}
            for m in re.finditer(r"^\s*(\w+): \{ w: (\d+), h: (\d+), text: (\d+), acts: \[(.*?)\] \},",
                                 CONTRACT_TS.read_text(), re.M)}


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_limits_timings_and_geometry_match_the_renderer():
    assert _ts_block("LIMITS") == be.LIMITS
    assert _ts_block("TIMING") == be.TIMING
    assert _ts_block("GEOMETRY") == be.GEOMETRY
    m = re.search(r"export const PROP_SCALE = \{ min: ([\d.]+), max: ([\d.]+) \}", CONTRACT_TS.read_text())
    assert (float(m.group(1)), float(m.group(2))) == be.PROP_SCALE


def test_the_event_types_and_cast_match_the_renderer():
    assert tuple(_ts_array("EVENT_TYPES")) == be.EVENT_TYPES
    assert tuple(_ts_array("CAST_IDS")) == be.CAST_IDS
    assert tuple(_ts_array("LABEL_TONES")) == be.LABEL_TONES


@pytest.mark.parametrize("ts, pack_key", [
    ("POSES", "poses"), ("FACES", "faces"), ("LOOKS", "looks"), ("MARKS", "marks"),
    ("ACCESSORIES", "accessories"), ("TINTS", "tints"), ("ENTRANCES", "entrances"),
])
def test_the_pack_lists_exactly_what_the_renderer_draws(ts, pack_key):
    assert _ts_array(ts) == EXTRA[pack_key]


def test_the_fields_and_section_colours_match_the_renderer():
    assert _ts_keys("FIELDS") == EXTRA["fields"]
    assert _ts_keys("SECTION_COLORS") == EXTRA["section_colors"]


def test_the_prop_library_matches_the_renderer_and_the_pack():
    ts = _ts_props()
    assert len(ts) >= 40
    assert {k: (v["w"], v["h"]) for k, v in ts.items()} == be.PROP_BOXES
    assert {k: {"text": v["text"], "acts": v["acts"]} for k, v in ts.items()} == EXTRA["props"]
    # every prop has exactly one drawing
    drawn = set(re.findall(r"(\w+): \w+[,\n ]", DRAWINGS_TS.read_text().split("DRAWINGS")[1].split("};")[0]))
    assert drawn == set(ts)


def test_labels_wrap_the_same_way():
    for case in CASES["wrap_label"]:
        assert be.wrap_label(case["text"]) == case["lines"], case["text"]


def test_boxes_are_computed_the_same_way():
    for c in CASES["prop_box"]:
        assert list(be.prop_box(c["prop"], c["x"], c["y"], c["scale"])) == pytest.approx(c["box"])
    for c in CASES["label_box"]:
        assert list(be.label_box(c["text"], c["x"], c["y"])) == pytest.approx(c["box"])
    for c in CASES["bean_box"]:
        assert list(be.bean_box(c["x"], c["scale"])) == pytest.approx(c["box"])


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None):
    return be.check(config or EXAMPLE, 30, WORD_STARTS, WORDS, EXTRA)


def _data(cfg):
    return cfg["scenes"][0]["props"]["beanExplainer"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _event(shot, frame, **kw):
    return {"frame": frame, **kw}


def test_the_example_passes():
    assert _check() == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(field="orange"), "field must be one of"),
    (lambda d: d["cast"].append({"id": "other", "tint": "cream"}), "different tints"),
    (lambda d: d["cast"].__setitem__(0, {"id": "other"}), "first cast member must be the narrator"),
    (lambda d: d["cast"][0].update(accessory="crown"), "accessory must be one of"),
    (lambda d: d["sections"][0].update(header="A HEADER FAR TOO LONG"), "header must be text"),
    (lambda d: d["sections"][0].update(badge="rocket"), "badge must be a prop"),
    (lambda d: d["sections"][1].update(start=290), "where no shot starts"),
    (lambda d: d["shots"][2].update(start=295), "not on a word"),
    (lambda d: d["shots"][0].update(start=4), "first shot must start at frame 0"),
    (lambda d: d["shots"][1]["events"][0].update(pose="dab"), "pose must be one of"),
    (lambda d: d["shots"][1]["events"][0].update(frame=82), "a pose swaps on a word"),
    (lambda d: d["shots"][1]["events"][0].pop("x"), "first pose in a shot needs x"),
    (lambda d: d["shots"][1]["events"][1].update(prop="rocket"), "prop must be from the library"),
    (lambda d: d["shots"][1]["events"][1].update(text="x" * 41), "text must be at most 40"),
    (lambda d: d["shots"][1]["events"][1].update(scale=2), "scale must be from"),
    (lambda d: d["shots"][1]["events"][2].update(act="explode"), "acts are buzz"),
    (lambda d: d["shots"][1]["events"][2].update(frame=130), "once its prop has landed"),
    (lambda d: d["shots"][1]["events"][3].update(text="your account is locked so"), "repeats the narration"),
    (lambda d: d["shots"][1]["events"][3].update(x=0.3, y=0.5), "overlaps the narrator bean"),
    (lambda d: d["shots"][1]["events"][3].update(y=0.47), "overlaps the phone prop"),
    (lambda d: d["shots"][1]["events"][1].update(x=0.3), "overlaps the narrator bean"),
    (lambda d: d["shots"][1]["events"][1].update(y=0.2), "reaches outside the stage"),
    (lambda d: d["shots"][2]["events"][0].update(frame=300), "after the badge carousel"),
    (lambda d: d["shots"][3]["events"][-1].update(frame=712), "too close to the cut"),
    (lambda d: d["shots"][3]["events"][-1].update(target="ghost"), "already on stage"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    def drop(d):
        d["shots"][3]["events"] = [e for e in d["shots"][3]["events"] if e["frame"] < 560]
    problems = _check(_with(drop))
    assert any("Nothing changes from frame" in p for p in problems), problems


def test_two_pose_swaps_too_close_together_read_as_a_twitch():
    def add(d):
        d["shots"][1]["events"].insert(5, {"type": "pose", "frame": 222, "who": "narrator", "pose": "shrug", "face": "sad"})
        d["shots"][1]["events"].sort(key=lambda e: e["frame"])
    # 222 and 232 are both on words, ten frames apart: fine
    assert _check(_with(add)) == []

    def twitch(d):
        d["shots"][1]["events"].insert(5, {"type": "pose", "frame": 228, "who": "narrator", "pose": "shrug", "face": "sad"})
        d["shots"][1]["events"].sort(key=lambda e: e["frame"])
    assert any("read as a twitch" in p or "a pose swaps on a word" in p for p in _check(_with(twitch)))


def test_too_many_elements_in_one_shot_are_refused():
    def crowd(d):
        ev = d["shots"][3]["events"]
        for k, (x, y) in enumerate(((0.55, 0.3), (0.8, 0.3), (0.55, 0.62), (0.8, 0.62), (0.6, 0.66))):
            ev.append({"type": "label", "frame": 640 + k, "text": f"note {k}", "x": x, "y": y})
        ev.sort(key=lambda e: e["frame"])
    assert any("at most 6 fit" in p for p in _check(_with(crowd)))


def test_a_hop_sweeps_the_ground_between_its_ends():
    scale = be.bean_scale(1)
    spans = be.bean_spans([(78, 0.25), (195, 0.8)], 288, scale)
    assert [(a, b) for a, b, _ in spans] == [(78, 195), (195, 195 + be.HOP_FRAMES), (195 + be.HOP_FRAMES, 288)]
    sweep = spans[1][2]
    assert sweep[0] == be.bean_box(0.25, scale)[0] and sweep[2] == be.bean_box(0.8, scale)[2]


def _hop_shot(d, prop_frame):
    # both of the bean's spots are clear of the phone; only the hop crosses it
    d["shots"][1]["events"] = [
        {"type": "pose", "frame": 78, "who": "narrator", "pose": "stand", "face": "neutral", "x": 0.25},
        {"type": "prop", "frame": prop_frame, "prop": "phone", "x": 0.55, "y": 0.5, "scale": 0.6},
        {"type": "pose", "frame": 195, "who": "narrator", "pose": "stand", "face": "worried", "x": 0.8},
    ]
    d["shots"][1]["events"].sort(key=lambda e: e["frame"])


def test_a_hop_through_a_prop_is_refused():
    problems = _check(_with(lambda d: _hop_shot(d, 128)))
    assert any("phone prop overlaps the narrator bean (from frame 195)" in p for p in problems), problems


def test_a_prop_that_lands_after_the_hop_is_free():
    problems = _check(_with(lambda d: _hop_shot(d, 213)))
    assert not any("phone prop overlaps" in p for p in problems), problems


def test_at_only_on_a_reaching_pose():
    def aim_stand(d):
        d["shots"][1]["events"][0]["at"] = "phone"
    assert any("does not reach" in p for p in _check(_with(aim_stand)))


def test_a_list_needs_at_least_two_sections():
    def one(d):
        d["sections"] = d["sections"][:1]
    assert any("at least two items" in p for p in _check(_with(one)))


def test_props_may_overlap_each_other():
    # a magnifier over an address bar, a cursor over a phone: the gags rely on it
    assert _check() == []
    lens = [e for e in _data(EXAMPLE)["shots"][2]["events"] if e.get("id") == "lens"][0]
    fake = [e for e in _data(EXAMPLE)["shots"][2]["events"] if e.get("id") == "fake"][0]
    a, b = be.prop_box("magnifier", lens["x"], lens["y"], lens["scale"]), be.prop_box("browser", fake["x"], fake["y"], fake["scale"])
    assert a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_the_scene_use_rule():
    scenes = copy.deepcopy(EXAMPLE["scenes"])
    assert be.check_scene_use("bean_explainer", scenes) == ""
    assert "visual_style is bean_explainer" in be.check_scene_use("stick", scenes)
    scenes[0]["type"] = "TextReveal"
    assert "exactly one scene" in be.check_scene_use("bean_explainer", scenes)
    assert be.check_scene_use("stick", [{"src": "intro", "type": "generated"}]) == ""


def test_shot_windows():
    # the list sections after the first open with the carousel; their shots start after it
    assert be.shot_windows(EXAMPLE) == [(0, 78), (78, 288), (318, 447), (477, 716)]
    assert be.shot_windows({"scenes": []}) == []


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make(video_id, style="bean_explainer", with_timeline=True):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'every phishing trick', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        if with_timeline:
            d = tmp_path / "jobs" / video_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_be1")
    cfg = copy.deepcopy(EXAMPLE)
    del cfg["subtitles"]
    result = server.write_scene_config(vid, cfg)
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("bean_explainer")["captions"]
    assert written["canvas"] == "light"


def test_the_examples_own_captions_and_emphasis_are_kept(make_video):
    vid = make_video("vid_be2")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    assert json.loads(pathlib.Path(result["path"]).read_text())["subtitles"]["emphasis"] == [16, 25, 29, 42]


def test_a_broken_config_is_refused_before_anything_is_written(make_video):
    vid = make_video("vid_be3")
    cfg = _with(lambda d: d["shots"][1]["events"][1].update(prop="rocket"))
    result = server.write_scene_config(vid, cfg)
    assert "Bean Explainer video has problems" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_bean_scene(make_video):
    vid = make_video("vid_be4", style="stick")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "visual_style is bean_explainer" in result["error"]


def test_a_bean_video_cannot_be_built_from_other_scenes(make_video):
    vid = make_video("vid_be5")
    cfg = {"totalFrames": 716, "fps": 30, "sfx": [],
           "scenes": [{"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 716}]}
    assert "exactly one scene" in server.write_scene_config(vid, cfg)["error"]


@pytest.mark.parametrize("emphasis, fragment", [
    ([48], "the narration has 48 words"),
    ([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "at most one word in 5"),
    ([3, 3], "distinct word indexes"),
    (["panic"], "distinct word indexes"),
])
def test_bad_emphasis_is_refused(make_video, emphasis, fragment):
    vid = make_video(f"vid_em{abs(hash(str(emphasis))) % 10000}")
    cfg = copy.deepcopy(EXAMPLE)
    cfg["subtitles"]["emphasis"] = emphasis
    assert fragment in server.write_scene_config(vid, cfg)["error"]


def test_emphasis_works_on_any_style(make_video):
    """emphasis is a caption option, not a Bean Explainer one."""
    assert server._validate_subtitles({"emphasis": [0, 7]}) == ""
    assert server._emphasis_error({"emphasis": [0, 7]}, 40) == ""
    assert server._emphasis_error({"emphasis": [0, 7]}, 0) == ""  # no timeline: skipped


# ── the text audit samples every shot ────────────────────────────────────────

def test_the_text_audit_samples_each_shot():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = be.shot_windows(EXAMPLE)
    assert len(passes) == len(windows)
    for p, (start, end) in zip(passes, windows):
        assert start <= p["first"] and p["first"] + p["step"] * (p["count"] - 1) < end
