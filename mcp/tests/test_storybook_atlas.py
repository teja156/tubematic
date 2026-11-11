"""Storybook Atlas: the scene-config checks that keep an unattended agent from
shipping a mistimed, crowded or still picture book, their agreement with the
renderer's contract.ts and stage.ts and the style pack, and their place in
write_scene_config, validate_job and the text audit.

Each refusal guards something the renderer cannot fix: an event off the words
reads as out of sync, a prop the library does not draw renders nothing, two
people standing in one place or a tag over a tag cannot be read, a push needs a
door to push through, and more than four seconds with nothing new is a dead page.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import server
import storybook_atlas as sa
import text_audit
from tubematic_core import mascots
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/storybook_atlas_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-storybook-atlas/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("storybook_atlas")["extra"]
MOTH = (REF / "example-prop-moth.tsx").read_text()


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    c = CASES["constants"]
    assert {k: list(v) if isinstance(v, tuple) else v for k, v in sa.LIMITS.items()} == c["LIMITS"]
    assert sa.TIMING == c["TIMING"]
    assert {k: list(v) if isinstance(v, tuple) else v for k, v in sa.STAGE.items()} == c["STAGE"]
    assert list(sa.ACTS) == c["ACTS"]
    assert list(sa.ENTERS) == c["ENTERS"]
    assert list(sa.FACINGS) == c["FACINGS"]
    assert sa.GLYPHS == c["GLYPHS"]
    assert list(sa.PLATE_EVENTS) == c["PLATE_EVENTS"]
    assert list(sa.PROP_ENTRANCES) == c["PROP_ENTRANCES"]


def test_titles_wrap_the_same_way():
    for case in CASES["wrap_title"]:
        assert sa.wrap_title(case["title"]) == case["lines"]


def test_walks_are_timed_the_same_way():
    for case in CASES["walk_frames"]:
        assert sa.walk_frames(case["a"], case["b"]) == case["frames"]
    for w in CASES["actor_at"]:
        for f, want in zip(w["frames"], w["states"]):
            got = sa.actor_at(w["moves"], f, w["start"])
            assert got == want, (w["moves"], f)


def test_the_pack_carries_the_catalogue():
    assert set(EXTRA) == {"coats", "backdrops", "guidePoses", "personPoses", "knobs", "props"}
    assert {"door", "porthole", "relaycabinet", "book"} <= set(EXTRA["props"])
    assert all(any(p.get("portal") for p in EXTRA["props"].values()) for _ in [0])
    for pid, p in EXTRA["props"].items():
        assert set(p["acts"]) <= set(sa.ACTS), pid


def test_the_caption_band_covers_the_label():
    """The mascot check keeps the mascot out of the caption band: the band the
    pack's captions give must hold a two-line label with its padding."""
    cap = tvs.pack("storybook_atlas")["captions"]
    y0, y1 = mascots.caption_band(cap)
    label_half = (2 * cap["fontSize"] * 1.12 + cap["fontSize"] * 0.52 + 4) / 2
    centre = cap["position"] * 1920
    assert y0 <= centre - label_half and y1 >= centre + label_half


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None, sources=None, video_id=""):
    return sa.check(config or EXAMPLE, 30, WORD_STARTS, EXTRA, video_id, sources)


def _data(cfg):
    return cfg["scenes"][0]["props"]["storybookAtlas"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _ev(d, chapter, kind, k=0):
    return [e for e in d["chapters"][chapter]["events"] if e["type"] == kind][k]


def test_the_example_passes():
    assert _check() == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d["guide"].update(coat="tweed"), "coat one of"),
    (lambda d: d["cast"][0].update(hat="crown"), "hat must be one of"),
    (lambda d: d["cast"][0].update(name="x" * 25), "name is the text on their tag"),
    (lambda d: d["cast"].extend([{**d["cast"][0], "id": f"p{i}"} for i in range(4)]), "at most 4 people"),
    (lambda d: d.update(chapters=d["chapters"][:2]), "3 to 5 chapters"),
    (lambda d: d["chapters"][0].update(start=6), "first chapter must start at frame 0"),
    (lambda d: d["chapters"][1].update(start=470), "within 2 frames of a word"),
    (lambda d: d["chapters"][2].update(start=1300), "a chapter lasts at least"),
    (lambda d: d["chapters"][0].update(title="A title much too long to fit on the plaque at all"), "must fit 2 lines"),
    (lambda d: d["chapters"][0].update(byline=""), "byline is the plaque"),
    (lambda d: d["chapters"][0].update(backdrop="moon"), "backdrop must be one of"),
    (lambda d: d["chapters"][2].update(enter="fade"), "enter must be one of"),
    (lambda d: _ev(d, 0, "prop").update(at=105), "within 2 frames of a word"),
    (lambda d: _ev(d, 0, "prop").update(prop="zeppelin"), "not in the prop library"),
    (lambda d: _ev(d, 0, "prop").update(scale=2), "scale must be from"),
    (lambda d: _ev(d, 0, "prop").update(x=950), "reaches outside the stage"),
    (lambda d: _ev(d, 0, "prop").update(enter="spiral"), "enter must be one of"),
    (lambda d: _ev(d, 2, "prop", 1).update(y=400), "y is its base line"),
    (lambda d: _ev(d, 0, "act").update(act="spin"), "can do"),
    (lambda d: _ev(d, 0, "act").update(at=101), "before cabinet has landed"),
    (lambda d: _ev(d, 0, "act").update(id="ghost"), "not on stage yet"),
    (lambda d: _ev(d, 0, "tag").update(on="ghost"), "not a prop on stage yet"),
    (lambda d: _ev(d, 0, "tag").update(text="x" * 25), "text of 1 to 24"),
    (lambda d: _ev(d, 0, "guide").update(x=600), "which relaycabinet covers (x 470 to 890)"),
    (lambda d: _ev(d, 0, "guide").update(pose="dance"), "pose must be one of"),
    (lambda d: _ev(d, 0, "guide").update(pose="walk1"), "pose must be one of"),
    (lambda d: _ev(d, 0, "guide").update(x=1050), "where the feet stop"),
    (lambda d: _ev(d, 1, "person").update(who="ada"), "not in the cast"),
    (lambda d: _ev(d, 1, "person").update(x=270), "stand in the same place"),
    (lambda d: _ev(d, 0, "gauge").update(until=300), "needs `until`"),
    (lambda d: _ev(d, 0, "gauge").update(to=5000), "between 0 and max"),
    (lambda d: _ev(d, 0, "gauge").update(danger=4000), "danger mark"),
    (lambda d: _ev(d, 0, "gauge").update(label=""), "needs a label"),
    (lambda d: _ev(d, 1, "morph").update(word="MOTH"), "a prop or a word, one of the two"),
    (lambda d: _ev(d, 1, "morph").update(prop="zeppelin"), "not a library or custom prop"),
    (lambda d: _ev(d, 2, "constellation").update(words=["BUG!"]), "letters or digits"),
    (lambda d: _ev(d, 2, "constellation").update(words=["THE", "FIRST", "BUG"]), "1 or 2 words"),
    (lambda d: _ev(d, 2, "constellation").update(thenAt=1250), "thenAt must be"),
    (lambda d: d["chapters"][0]["events"].append({"type": "guide", "at": 315, "pose": "hop"}), "while a plate is open"),
    (lambda d: d["chapters"][1]["events"].append({"type": "gauge", "at": 817, "until": 900, "label": "x", "from": 0, "to": 1, "max": 2}), "before the plate at frame 809"),
    (lambda d: d["chapters"][0]["events"].append({"type": "guide", "at": 466, "pose": "hop"}), "no later than 20 frames"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_push_needs_a_door_or_porthole_in_the_chapter_before():
    def no_portal(d):
        _ev(d, 0, "prop").update(prop="lamp")
        d["chapters"][0]["events"] = [e for e in d["chapters"][0]["events"] if e["type"] != "act"]
        d["chapters"][0]["events"].append({"type": "act", "at": 225, "id": "cabinet", "act": "switch"})
    problems = _check(_with(no_portal))
    assert any("enters with a push" in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    def drop(d):
        d["chapters"][2]["events"] = [e for e in d["chapters"][2]["events"] if e["at"] < 1100 or e["type"] == "constellation"]
    problems = _check(_with(drop))
    assert any("nothing changes on stage" in p for p in problems), problems


def test_three_people_at_once_are_refused():
    def crowd(d):
        for i, x in enumerate((300, 560)):
            d["cast"].append({**d["cast"][0], "id": f"extra{i}", "name": f"Clerk {i}"})
        d["chapters"][1]["events"] += [
            {"type": "person", "at": 592, "who": "extra0", "x": 300},
            {"type": "person", "at": 604, "who": "extra1", "x": 940},
        ]
    problems = _check(_with(crowd))
    assert any("people on stage" in p for p in problems), problems


def test_name_tags_that_collide_are_refused():
    def close(d):
        # Howard stands 180 px from Grace and from the guide: room for both of them,
        # but not for a long name tag beside Grace's
        d["cast"].append({**d["cast"][0], "id": "howard", "name": "Howard Aiken, professor"})
        d["chapters"][1]["events"].insert(0, {"type": "guide", "at": 478, "x": 110})
        d["chapters"][1]["events"].append({"type": "person", "at": 604, "who": "howard", "x": 290})
    problems = _check(_with(close))
    assert any("tags under" in p for p in problems), problems


def test_a_person_walking_past_the_guide_is_fine():
    """Grace walks in from the left past the guide at 210: only where people
    stand still is checked, so the example passes."""
    assert _check() == []


def test_the_scene_use_rule():
    assert sa.check_scene_use("stick", EXAMPLE["scenes"]).startswith("The StorybookAtlas scene draws")
    assert sa.check_scene_use("storybook_atlas", EXAMPLE["scenes"]) == ""
    assert "exactly one scene" in sa.check_scene_use("storybook_atlas", EXAMPLE["scenes"] * 2)
    assert sa.check_scene_use("stick", [{"type": "generated", "src": "Other"}]) == ""


def test_chapter_windows_cover_the_video_cut_at_each_event():
    windows = sa.chapter_windows(EXAMPLE)
    assert windows[0][0] == 0 and windows[-1][1] == EXAMPLE["totalFrames"]
    assert all(a < b for a, b in windows)
    assert all(w1[1] == w2[0] for w1, w2 in zip(windows, windows[1:]))
    cuts = {a for a, _ in windows}
    assert {e["at"] for c in _data(EXAMPLE)["chapters"] for e in c["events"]} <= cuts


def test_the_text_audit_samples_each_stretch():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = sa.chapter_windows(EXAMPLE)
    assert len(passes) == len(windows)
    for p, (start, end) in zip(passes, windows):
        assert start <= p["first"] and p["first"] + p["step"] * (p["count"] - 1) < end


# ── props the agent draws ────────────────────────────────────────────────────

MOTH_SPEC = _data(EXAMPLE)["customProps"][0]


def _custom(changes):
    return sa.custom_prop_errors([{**MOTH_SPEC, **changes}], "vid_example", EXTRA["props"], None)[0]


@pytest.mark.parametrize("changes, fragment", [
    ({"id": "lamp"}, "not a library prop"),
    ({"src": "other_video/prop-moth"}, "src must be"),
    ({"src": "vid_example/moth"}, "src must be"),
    ({"box": [30, 220]}, "box is [width, height]"),
    ({"place": "ceiling"}, "place must be"),
    ({"states": 9}, "states is how many drawings"),
    ({"acts": ["switch"]}, "switch and cycle need a second state"),
    ({"acts": ["explode"]}, "acts is a list"),
    ({"portal": [400, 0]}, "portal is a point inside its box"),
])
def test_a_bad_custom_prop_entry_is_refused(changes, fragment):
    assert any(fragment in e for e in _custom(changes))


@pytest.mark.parametrize("body, fragment", [
    (MOTH.replace("export default function", "function"), "default-export"),
    (MOTH.replace('import { INK, IVORY }', 'import { INK, IVORY }') + '\nimport x from "../../installed/storybookAtlas/stage";', "it imports"),
    (MOTH.replace("<g transform", '<filter id="b" /><g transform', 1), "an SVG filter"),
    (MOTH.replace("<g transform", '<text x="0">MOTH</text><g transform', 1), "SVG text"),
    (MOTH.replace("<g transform", '<linearGradient id="g" /><g transform', 1), "a gradient"),
    (MOTH.replace("void state;", "void state; Math.random();"), "randomness"),
])
def test_a_custom_prop_file_that_breaks_the_rules_is_refused(body, fragment):
    errs, _ = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: body})
    assert any(fragment in e for e in errs), errs


def test_the_example_moth_passes_the_source_checks():
    errs, catalog = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: MOTH})
    assert errs == [] and catalog["moth"]["place"] == "wall"


# ── write_scene_config, validate_job and the preview ─────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")

    def make(video_id, style="storybook_atlas", moth=True):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'the first computer bug', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        if moth:
            (tmp_path / "generated" / video_id).mkdir(parents=True, exist_ok=True)
            (tmp_path / "generated" / video_id / "prop-moth.tsx").write_text(MOTH)
        return video_id

    return make


def _for(video_id):
    cfg = copy.deepcopy(EXAMPLE)
    _data(cfg)["customProps"][0]["src"] = f"{video_id}/prop-moth"
    return cfg


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_sa1")
    result = server.write_scene_config(vid, _for(vid))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("storybook_atlas")["captions"]


def test_a_missing_prop_file_is_refused(make_video):
    vid = make_video("vid_sa2", moth=False)
    assert "write it with write_scene_file first" in server.write_scene_config(vid, _for(vid))["error"]


def test_a_broken_config_is_refused_before_anything_is_written(make_video):
    vid = make_video("vid_sa3")
    cfg = _for(vid)
    _ev(_data(cfg), 0, "prop").update(prop="zeppelin")
    result = server.write_scene_config(vid, cfg)
    assert "Storybook Atlas video has problems" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_storybook_scene(make_video):
    vid = make_video("vid_sa4", style="stick")
    assert "visual_style is storybook_atlas" in server.write_scene_config(vid, _for(vid))["error"]


def test_the_label_caption_background_is_accepted_on_any_style(make_video):
    vid = make_video("vid_sa5")
    cfg = _for(vid)
    cfg["subtitles"] = {"background": "label"}
    assert "error" not in server.write_scene_config(vid, cfg)
    cfg["subtitles"] = {"background": "parchment"}
    assert "background" in server.write_scene_config(vid, cfg)["error"]


def test_validate_job_rechecks_a_redrawn_prop(make_video, tmp_path):
    vid = make_video("vid_sa6")
    assert "error" not in server.write_scene_config(vid, _for(vid))
    (tmp_path / "generated" / vid / "prop-moth.tsx").write_text(MOTH.replace("<g transform", '<filter id="b" /><g transform', 1))
    errs = server._storybook_custom_prop_errors(vid, _for(vid))
    assert any("an SVG filter" in e for e in errs), errs


def test_render_storybook_props_refuses_what_it_cannot_preview(make_video):
    assert "for Storybook Atlas videos" in server.render_storybook_props(make_video("vid_rp1", style="stick"))["error"]
    vid = make_video("vid_rp2")
    assert "no Storybook Atlas scene-config yet" in server.render_storybook_props(vid)["error"]
    cfg = _for(vid)
    del _data(cfg)["customProps"]
    _ev(_data(cfg), 1, "morph").update(prop="lamp")
    _data(cfg)["chapters"][2]["events"] = [e for e in _data(cfg)["chapters"][2]["events"] if e.get("id") != "moth" and e.get("on") != "moth"]
    _data(cfg)["chapters"][2]["events"].insert(2, {"type": "guide", "at": 1109, "pose": "look"})
    assert "error" not in server.write_scene_config(vid, cfg), server.write_scene_config(vid, cfg)
    assert "lists no customProps" in server.render_storybook_props(vid)["error"]


def test_render_storybook_props_returns_the_picture(make_video, monkeypatch):
    from PIL import Image as PILImage
    vid = make_video("vid_rp3")
    assert "error" not in server.write_scene_config(vid, _for(vid))
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0, script=None):
        seen.update(spec=spec, script=script)
        PILImage.new("RGB", (1080, 1920), (235, 229, 210)).save(out_png)

    monkeypatch.setattr(server.bean_preview, "render_preview", fake_render)
    meta, image = server.render_storybook_props(vid)
    assert json.loads(meta) == {"video_id": vid, "props": ["moth"]}
    assert seen["script"] == server.bean_preview.STORYBOOK_SCRIPT
    assert seen["spec"]["props"][0]["src"] == f"{vid}/prop-moth"
    assert image is not None
