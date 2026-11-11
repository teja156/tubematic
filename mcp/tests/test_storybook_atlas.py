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


def test_a_tag_is_checked_from_its_own_frame():
    """A tag written after a person has left does not collide with that person's name tag."""
    def later(d):
        ch = d["chapters"][1]["events"]
        ch.append({"type": "prop", "at": 499, "id": "lamp", "prop": "lamp", "x": 760, "enter": "pop"})
        _ev(d, 1, "prop").update(x=900, scale=0.6)
        _ev(d, 1, "person").update(x=560)
        ch.append({"type": "person", "at": 745, "who": "grace", "exit": True})
        ch.append({"type": "tag", "at": 765, "on": "lamp", "text": "Oil lamp, 1947 lab"})
    problems = _check(_with(later))
    assert not any("tags under" in p for p in problems), problems


def test_a_second_tag_replaces_the_first():
    def two(d):
        d["chapters"][0]["events"].append({"type": "tag", "at": 159, "on": "cabinet", "text": "Harvard Mark II relay"})
    assert _check(_with(two)) == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: _ev(d, 0, "guide").update(x=None), "x is where the feet stop"),
    (lambda d: _ev(d, 1, "person").update(x=None), "x is where the feet stop"),
    (lambda d: _ev(d, 1, "person").update(who=["grace"]), "not in the cast"),
    (lambda d: _ev(d, 0, "tag").update(on=["cabinet"]), "not a prop on stage yet"),
    (lambda d: _ev(d, 0, "prop").update(prop=["lamp"]), "not in the prop library"),
    (lambda d: d["cast"][0].pop("name"), "name is the text on their tag"),
    (lambda d: _ev(d, 0, "guide").update(exit=True), "cannot exit"),
    (lambda d: _ev(d, 1, "morph").update(prop=["moth"]), "not a library or custom prop"),
    (lambda d: _ev(d, 0, "gauge").update(at=315, until=450), "must be closed"),
    (lambda d: d["chapters"][2]["events"].append({"type": "gauge", "at": 923, "until": 1008, "label": "x", "from": 0, "to": 1, "max": 2}),
     "still coming in"),
])
def test_malformed_and_ill_timed_events_are_refused_not_crashed(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_story_with_no_people_may_leave_the_cast_out():
    def castless(d):
        del d["cast"]
        d["chapters"][1]["events"] = [e for e in d["chapters"][1]["events"] if e["type"] != "person"]
        d["chapters"][1]["events"].append({"type": "guide", "at": 733, "pose": "point", "facing": "right"})
        d["chapters"][1]["events"].append({"type": "guide", "at": 637, "pose": "think"})
    assert _check(_with(castless)) == []


def test_on_one_frame_a_prop_comes_before_what_names_it():
    def tag_first(d):
        evs = d["chapters"][0]["events"]
        evs.insert(0, {"type": "tag", "at": 101, "on": "cabinet", "text": "Mark II"})
        evs[:] = [e for e in evs if not (e["type"] == "tag" and e["at"] == 138)]
    assert _check(_with(tag_first)) == []


def test_a_tag_off_the_frame_is_refused():
    def edge(d):
        d["cast"][0]["name"] = "Rear Admiral G. M. Hopper"[:24]
        _ev(d, 1, "person").update(x=130)
        _ev(d, 1, "guide").update(x=330)
    problems = _check(_with(edge))
    assert any("runs off the frame" in p for p in problems), problems


def test_an_entry_with_no_x_walks_to_the_middle_and_is_checked_there():
    assert sa.walk_ends([{"at": 100}], None) == [100 + sa.walk_frames(-160, 540)]

    def middle(d):
        # the last event of chapter 2: Grace enters with no x and stops at x 540, inside the relays
        _ev(d, 1, "prop").update(x=600, scale=0.85)
        d["chapters"][1]["events"] = [e for e in d["chapters"][1]["events"] if e["type"] not in ("person", "morph")]
        d["chapters"][1]["events"].append({"type": "guide", "at": 637, "pose": "think"})
        d["chapters"][1]["events"].append({"type": "person", "at": 809, "who": "grace"})
    problems = _check(_with(middle))
    assert any("grace needs the floor" in p for p in problems), problems


def test_a_walk_cut_short_never_counts_as_an_arrival():
    assert sa.walk_ends([{"at": 0, "x": 900}, {"at": 10, "pose": "think"}], 210) == []

    def cut(d):
        # the guide sets off for the cabinet's far side and is stopped by a pose ten frames later;
        # the walk's arrival never happens, so the stretch until the next event is still
        evs = [e for e in d["chapters"][2]["events"] if e["at"] < 1100 or e["type"] == "constellation"]
        evs += [{"type": "guide", "at": 1109, "x": 900}, {"type": "guide", "at": 1119, "pose": "think"}]
        d["chapters"][2]["events"] = evs
    problems = _check(_with(cut))
    assert any("nothing changes on stage" in p for p in problems), problems


def test_a_person_walking_past_the_guide_is_fine():
    """Grace walks in from the left past the guide at 210: only where people
    stand still is checked, so the example passes."""
    assert _check() == []


def test_the_scene_use_rule():
    assert sa.check_scene_use("stick", EXAMPLE["scenes"]).startswith("The StorybookAtlas scene draws")
    assert sa.check_scene_use("storybook_atlas", EXAMPLE["scenes"]) == ""
    assert "exactly one scene" in sa.check_scene_use("storybook_atlas", EXAMPLE["scenes"] * 2)
    assert sa.check_scene_use("stick", [{"type": "generated", "src": "Other"}]) == ""


def test_chapter_windows_cut_at_each_event_and_skip_the_transitions():
    windows = sa.chapter_windows(EXAMPLE)
    assert windows[0][0] == 0 and windows[-1][1] == EXAMPLE["totalFrames"]
    assert all(a < b for a, b in windows)
    chapters = _data(EXAMPLE)["chapters"]
    # chapter 2 is pushed into: the push out of chapter 1 and the white into chapter 2 are left out
    assert not any(a < chapters[1]["start"] + sa.TIMING["wipeFrames"] and b > chapters[1]["start"] - sa.TIMING["pushFrames"]
                   for a, b in windows)
    # chapter 3 is wiped into: its first frames are left out
    assert not any(a < chapters[2]["start"] + sa.TIMING["wipeFrames"] and b > chapters[2]["start"] for a, b in windows)
    cuts = {a for a, _ in windows}
    late = [e for c in chapters for e in c["events"] if e["at"] >= c["start"] + sa.TIMING["wipeFrames"]]
    assert {e["at"] for e in late if e["type"] not in sa.PLATE_EVENTS} <= cuts
    # a plate's stretch starts once its shutters are open; the opening itself is not sampled
    assert {e["at"] + sa.TIMING["plateOpen"] for e in late if e["type"] in sa.PLATE_EVENTS} <= cuts
    assert not {e["at"] for e in late if e["type"] in sa.PLATE_EVENTS} & cuts


def test_the_text_audit_samples_every_plate_while_it_is_open():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    frames = {p["first"] + p["step"] * k for p in passes for k in range(p["count"])}
    for c in _data(EXAMPLE)["chapters"]:
        for e in c["events"]:
            if e["type"] in sa.PLATE_EVENTS:
                assert any(e["at"] + sa.TIMING["plateOpen"] <= f < e["until"] for f in frames), e


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
    (MOTH.replace("void state;", "void state; setTimeout(() => 0, 1);"), "a timer"),
])
def test_a_custom_prop_file_that_breaks_the_rules_is_refused(body, fragment):
    errs, _ = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: body})
    assert any(fragment in e for e in errs), errs


def test_a_string_holding_comment_marks_does_not_hide_code():
    for line in ('const a = "/*";\nconst f = window.fetch;\nconst b = "*/";', 'const s = "//"; const f = window.fetch;',
                 'const t = `${"//"}`; fetch("u");'):
        errs, _ = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: MOTH + "\n" + line})
        assert errs, line


def test_ordinary_names_and_dashes_are_not_refused():
    body = MOTH + '\nconst window = (x: number) => x;\nconst d = <g id="document" strokeDasharray="1 11" />;\n'
    errs, _ = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: body})
    assert errs == []


@pytest.mark.parametrize("line", [
    'const k = 0; import * as R from "remotion";',
    'import R from"remotion";',
    'const m = import ("remotion");',
    'const t = performance.now();',
    'const r = crypto.getRandomValues(new Uint8Array(1));',
    'const f = globalThis["fe" + "tch"];',
    'const g = new Function("return 1");',
    'const d = document.title;',
])
def test_a_prop_cannot_slip_past_the_source_rules(line):
    body = MOTH + "\n" + line + "\n"
    errs, _ = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: body})
    assert errs, line


def test_comments_are_not_read_as_code():
    body = "// like the library's window, but no image or document here\n/* fetch nothing */\n" + MOTH
    errs, _ = sa.custom_prop_errors([MOTH_SPEC], "vid_example", EXTRA["props"], {MOTH_SPEC["src"]: body})
    assert errs == []


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
    other = make_video("vid_sa5s", style="motion_graphics")
    plain = {"totalFrames": EXAMPLE["totalFrames"], "fps": 30, "subtitles": {"background": "label"},
             "scenes": [{"type": "generated", "source": "installed", "src": "KenBurnsImage", "startFrame": 0,
                         "durationInFrames": EXAMPLE["totalFrames"], "props": {}}]}
    result = server.write_scene_config(other, plain)
    assert "background" not in result.get("error", ""), result
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
