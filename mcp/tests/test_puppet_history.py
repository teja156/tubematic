"""Puppet History (TMDEV-232): the scene-config checks that keep an unattended
agent from shipping a mistimed, crowded, off-map or still video, their
agreement with the renderer's contract.ts and stage.ts (through the shared
fixture character-tools/sync-contract.mjs writes), and their place in
write_scene_config, render_style_props, the picture checks and the text audit.

Each refusal guards something the renderer cannot fix: two puppets in one slot
overlap, an event for a puppet that never entered draws nothing, a map region
outside the beat's focus is off the fitted map, a country name the atlas does
not have draws nothing, a card that repeats the narration doubles the
captions, and more than three seconds with nothing new is a held frame.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import character_styles
import picture_checks
import puppet_history as ph
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/puppet_history_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-puppet-history/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
WORDS = [w["word"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("puppet_history")["extra"]
C = CASES["constants"]


def _data(cfg=None) -> dict:
    return (cfg or EXAMPLE)["scenes"][0]["props"]["puppetHistory"]


def _with(mutate) -> dict:
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _check(cfg, quiet=(), sources=None, video_id=""):
    return ph.check(cfg, 30, WORD_STARTS, WORDS, EXTRA, video_id, sources, quiet=quiet)


def _beat(d, kind, n=0) -> dict:
    return [b for b in d["beats"] if b["type"] == kind][n]


def _event(d, type_, kind=None, n=0) -> dict:
    return [e for b in d["beats"] if kind in (None, b["type"]) for e in b["events"] if e["type"] == type_][n]


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    assert C["LIMITS"] == ph.LIMITS
    assert C["TIMING"] == ph.TIMING
    assert C["CUSTOM"] == ph.CUSTOM
    assert CASES["slots"] == ph.SLOTS
    assert tuple(C["POSES"]) == ph.POSES
    for name in ("FACES", "COSTUMES", "SETS", "STAMP_COLORS", "FILLS", "ENTRANCES", "BEAT_TYPES", "EVENT_TYPES"):
        assert tuple(C[name]) == getattr(ph, name), name
    assert {k: tuple(v) for k, v in C["BEAT_EVENTS"].items()} == ph.BEAT_EVENTS


def test_the_pack_lists_exactly_what_the_renderer_draws():
    assert EXTRA["props"] == {k: {"text": v["text"], "acts": []} for k, v in C["PROPS"].items()}
    assert EXTRA["costumes"] == C["COSTUMES"] and EXTRA["sets"] == C["SETS"]
    assert EXTRA["poses"] == list(C["POSES"]) and EXTRA["faces"] == C["FACES"]
    # the map knows today's countries by world-atlas's own names
    assert len(EXTRA["countries"]) > 150 and {"France", "Italy", "United Kingdom"} <= set(EXTRA["countries"])


def test_the_style_is_registered_and_takes_no_mascot():
    assert character_styles.BY_ID["puppet_history"] is ph
    assert tvs.pack("puppet_history")["mascot"] is False
    assert "puppet_history" in tvs.NO_MASCOT_STYLES


# ── the worked example and the refusals ──────────────────────────────────────

def test_the_worked_example_passes():
    assert _check(EXAMPLE) == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d["cast"].extend([{"id": f"p{c}", "costume": "plain"} for c in "abc"]), "cast must list 1 to 4"),
    (lambda d: d["cast"][0].update(costume="astronaut"), "costume must be one of"),
    (lambda d: d["cast"][1].update(name="x" * 19), "name must be text of 1 to 18"),
    (lambda d: d["beats"][0].update(start=4), "The first beat must start at frame 0"),
    (lambda d: _beat(d, "set").update(set="moon"), "set must be one of"),
    (lambda d: _beat(d, "map").update(focus=["Italy", "Gaul"]), "'Gaul' is not a country on the map"),
    (lambda d: _beat(d, "card").update(title="x" * 23), "title must be text of 1 to 22"),
    (lambda d: _beat(d, "card").update(lines=["a"] * 6), "lines must list 1 to 5"),
    (lambda d: _beat(d, "card").update(lines=["Most of it goes back"]), "repeats the narration word for word"),
    (lambda d: _event(d, "enter").update(slot=3), "slot must be 0, 1 or 2"),
    (lambda d: _beat(d, "set", 1)["events"].insert(1, {"type": "enter", "frame": 390, "who": "caesar", "slot": 1}), "slot 1 is taken by you"),
    (lambda d: _event(d, "act").update(who="ghost"), "who must be a cast id"),
    (lambda d: _beat(d, "set", 1)["events"].insert(1, {"type": "act", "frame": 390, "who": "caesar", "face": "happy"}), "caesar is not on stage"),
    (lambda d: _event(d, "act").update(pose="dab"), "pose must be one of"),
    (lambda d: _event(d, "swap").update(costume="astronaut"), "costume must be one of"),
    (lambda d: _event(d, "sign").update(text="x" * 15), "at most 14 characters"),
    (lambda d: _event(d, "hold").update(prop="unicorn"), "prop must be from the library"),
    (lambda d: _event(d, "hold").update(text="SPADE"), "has no label"),
    (lambda d: _event(d, "stamp").update(text="x" * 11), "text must be 1 to 10"),
    (lambda d: _event(d, "stamp").update(color="gold"), "color must be one of"),
    (lambda d: _event(d, "strike").update(line=5), "line must be the index of one of the card's lines"),
    (lambda d: _event(d, "fill").update(region="Germany"), "region must be one of the beat's focus countries"),
    (lambda d: _event(d, "arrow").update(to="Italy"), "from and to must be two different focus countries"),
    (lambda d: _event(d, "label").update(text="x" * 19), "text must be 1 to 18"),
    (lambda d: _beat(d, "card")["events"].append({"type": "fill", "frame": 266, "region": "Italy", "color": "red"}), "a card beat takes only"),
    (lambda d: _event(d, "date").update(frame=_event(d, "date")["frame"] + 5), "events land on words"),
    (lambda d: d["beats"][0]["events"].pop(0), "Nothing is on the first set at frame 0"),
    (lambda d: _beat(d, "card").update(events=[e for e in _beat(d, "card")["events"] if e["type"] != "date"]), "Nothing changes from frame"),
])
def test_each_rule_is_refused_with_a_reason(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_puppet_is_busy_while_it_slides_in():
    def early(d):
        b = _beat(d, "set", 1)
        b["events"][0]["from"] = "slide"
        b["events"].insert(1, {"type": "act", "frame": b["events"][0]["frame"] + 10, "who": "you", "face": "happy"})
    problems = _check(_with(early))
    assert any("still entering or moving" in p for p in problems), problems


def test_a_slot_is_free_again_once_its_puppet_has_slid_out():
    def leave_and_return(d):
        b = _beat(d, "set", 1)
        b["events"] = [b["events"][0], {"type": "exit", "frame": 429, "who": "you"},
                       {"type": "enter", "frame": 460, "who": "caesar", "slot": 1, "from": "pop"}]
    problems = _check(_with(leave_and_return))
    assert not any("taken" in p for p in problems), problems


def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash():
    for mutate in (
        lambda d: _event(d, "enter").update(who=["you"]),
        lambda d: _event(d, "act").update(face=None),
        lambda d: d.update(cast="many"),
        lambda d: d.update(beats={"a": 1}),
        lambda d: _beat(d, "map").update(focus="Italy"),
        lambda d: _event(d, "strike").update(line="two"),
        lambda d: _beat(d, "card").update(lines=[1, 2]),
        lambda d: _beat(d, "set").update(events="lots"),
    ):
        problems = _check(_with(mutate))
        assert problems and all(isinstance(p, str) for p in problems)


def test_scene_use_rules():
    assert "used only when the video's visual_style is puppet_history" in ph.check_scene_use("stick", EXAMPLE["scenes"])
    two = EXAMPLE["scenes"] + [{"type": "generated", "source": "generated", "src": "vid/x", "startFrame": 0, "durationInFrames": 10}]
    assert "exactly one scene" in ph.check_scene_use("puppet_history", two)


def test_nothing_starts_inside_an_insert():
    f = _event(_data(), "arrow")["frame"]
    assert any("inside an insert" in p for p in _check(EXAMPLE, quiet=[(f - 2, f + 40)]))


# ── custom props ─────────────────────────────────────────────────────────────

HOURGLASS = (REF / "example-prop-hourglass.tsx").read_text()


def _with_hourglass(vid="vid_ph1") -> dict:
    def add(d):
        d["customProps"] = [{"id": "hourglass", "src": f"{vid}/prop-hourglass", "w": 110, "h": 170, "text": 0}]
        _event(d, "hold").update(prop="hourglass")
    return _with(add)


def test_the_example_prop_passes_the_source_rules():
    assert _check(_with_hourglass(), sources={"vid_ph1/prop-hourglass": HOURGLASS}, video_id="vid_ph1") == []


@pytest.mark.parametrize("bad, fragment", [
    ("const f = useCurrentFrame();", "a React or Remotion hook"),
    ('<pattern id="p" />', "an SVG pattern"),
    ('import x from "../../installed/comicPanels/ink";', "imports ../../installed/comicPanels/ink"),
    # found in review: names split from their call by a comment, a comma or a bracket
    ('import/**/("https://x/y.js")', "an import other than a static"),
    ("const m = import.meta;", "an import other than a static"),
    ('(0,eval)("1")', "eval"),
    ('require/**/("fs")', "require"),
    ('(()=>{}).constructor("return window")()', "a constructor lookup"),
    ('React["useState"](0)', "React[...] lookups"),
    ("const {useState: u} = React; u(0);", "a React or Remotion hook"),
])
def test_a_custom_prop_breaking_a_source_rule_is_refused(bad, fragment):
    problems = _check(_with_hourglass(), sources={"vid_ph1/prop-hourglass": HOURGLASS + "\n" + bad}, video_id="vid_ph1")
    assert any(fragment in p for p in problems), problems


# ── write_scene_config and render_style_props ────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")

    def make(video_id, style="puppet_history"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'life of a Roman legionary', 'VOICE_READY', ?, ?, ?)", (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_ph1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    assert json.loads(pathlib.Path(result["path"]).read_text())["subtitles"] == tvs.pack("puppet_history")["captions"]
    cfg = _with(lambda d: _beat(d, "set").update(set="moon"))
    assert server.write_scene_config(vid, cfg)["error"].startswith("The Puppet History video has problems:")


def test_render_style_props_previews_this_style(make_video, tmp_path, monkeypatch):
    from PIL import Image as PILImage
    vid = make_video("vid_ph1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "prop-hourglass.tsx").write_text(HOURGLASS)
    assert "error" not in server.write_scene_config(vid, _with_hourglass())
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0, script=None):
        seen["spec"] = spec
        PILImage.new("RGB", (1080, 1920), (243, 234, 223)).save(out_png)

    monkeypatch.setattr(server.bean_preview, "render_preview", fake_render)
    result = server.render_style_props(vid)
    assert isinstance(result, list) and json.loads(result[0])["props"] == ["hourglass"]
    assert seen["spec"]["style"] == "puppet_history"
    script = (REPO / "renderer/remotion" / server.bean_preview.CHARACTER_SCRIPT).read_text()
    assert 'puppet_history: { module: "puppetHistory/PuppetHistorySheet", component: "PuppetHistoryPropPreview" }' in script


# ── picture checks and the text audit ────────────────────────────────────────

def test_the_picture_checks_and_the_audit_read_this_style():
    assert picture_checks.style_of(EXAMPLE) == "puppet_history"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    late = _with(lambda d: d["beats"][0]["events"][0].update(frame=10))
    assert "no puppet is on the first set by frame 3" in picture_checks.first_frame_warnings(late)[0]
    frames = picture_checks.change_frames("puppet_history", EXAMPLE)
    assert _beat(_data(), "card")["start"] in frames and _event(_data(), "strike")["frame"] in frames
    passes, _ = text_audit.plan_passes(EXAMPLE)
    assert [p["first"] for p in passes] == [w[0] for w in ph.audit_windows(EXAMPLE)]
    # each window waits until a slide-in has landed
    assert ph.audit_windows(EXAMPLE)[1][0] >= _beat(_data(), "card")["start"] + ph.TIMING["slide"]


def test_a_wide_sign_from_a_side_slot_is_pulled_in_and_two_signs_never_overlap():
    """A 14-character sign is 536 wide: centred on a side slot it would leave
    the frame, so it is pulled in; two puppets' signs side by side would cover
    each other, so the second is refused."""
    for c in CASES["sign_x"]:
        assert ph.sign_x(c["slot"], c["text"]) == pytest.approx(c["x"])
    for c in CASES["sign_width"]:
        assert ph.sign_width(c["text"]) == c["w"]
    assert tuple(C["GEOMETRY"]["slots"]) == ph.SLOT_X

    def two_signs(d):
        b = _beat(d, "set", 1)
        b["events"][1:1] = [{"type": "enter", "frame": 390, "who": "caesar", "slot": 2, "from": "cut"}]
        b["events"].insert(3, {"type": "sign", "frame": 429, "who": "caesar", "text": "SO FAR"})
    assert any("would overlap" in p for p in _check(_with(two_signs)))

    def short_signs(d):
        two_signs(d)
        for e in _beat(d, "set", 1)["events"]:
            if e["type"] == "sign" and e["text"]:
                e["text"] = "NO" if e["who"] == "caesar" else "20 MILES"
    assert not any("would overlap" in p for p in _check(_with(short_signs)))
