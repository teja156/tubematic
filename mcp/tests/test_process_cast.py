"""Process Cast (TMDEV-235): the scene-config checks that keep an unattended
agent from shipping an off-camera, mistimed, crowded or still video, their
agreement with the renderer's contract.ts and stage.ts (through the shared
fixture character-tools/sync-contract.mjs writes), and their place in
write_scene_config, render_style_props, the picture checks and the text audit.

Each refusal guards something the renderer cannot fix: an event at a station
the camera does not show happens off screen, two characters in one slot
overlap, a card handed to someone at another station flies off screen, a
clone of a clone has no name, and more than three seconds with nothing new is
a held frame.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import character_styles
import picture_checks
import process_cast as pc
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/process_cast_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-process-cast/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
WORDS = [w["word"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("process_cast")["extra"]
C = CASES["constants"]


def _data(cfg=None) -> dict:
    return (cfg or EXAMPLE)["scenes"][0]["props"]["processCast"]


def _with(mutate) -> dict:
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _check(cfg, quiet=(), sources=None, video_id=""):
    return pc.check(cfg, 30, WORD_STARTS, WORDS, EXTRA, video_id, sources, quiet=quiet)


def _event(cfg, type_, n=0):
    return [e for e in _data(cfg)["events"] if e["type"] == type_][n]


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    assert C["LIMITS"] == pc.LIMITS
    assert C["TIMING"] == pc.TIMING
    assert C["GEOMETRY"] == pc.GEOMETRY
    for name in ("BODIES", "ACCESSORIES", "FACES", "MARKS", "ENTRANCES", "CAMERA_MOVES", "EVENT_TYPES"):
        assert tuple(C[name]) == getattr(pc, name), name
    assert tuple(C["TINTS"]) == pc.TINTS
    assert tuple(C["STATIONS"]) == pc.STATION_KINDS
    assert C["CUSTOM"] == pc.CUSTOM


def test_the_pack_lists_exactly_what_the_renderer_draws():
    assert EXTRA["props"] == {k: {"text": v["text"], "acts": []} for k, v in C["PROPS"].items()}
    assert EXTRA["stations"] == list(C["STATIONS"])
    for key, const in (("bodies", "BODIES"), ("accessories", "ACCESSORIES"), ("faces", "FACES"), ("marks", "MARKS"),
                       ("entrances", "ENTRANCES"), ("camera_moves", "CAMERA_MOVES")):
        assert EXTRA[key] == C[const], key
    assert EXTRA["tints"] == list(C["TINTS"])


def test_the_helpers_match_the_renderer():
    for c in CASES["body_size"]:
        assert pc.body_size(c["body"], c["units"]) == (c["size"]["w"], c["size"]["h"])
    for c in CASES["slot_count"]:
        assert pc.slot_count(c["kind"]) == c["n"]
    for c in CASES["clone_id"]:
        assert pc.clone_id(c["who"], c["n"]) == c["id"]


def test_the_style_is_registered_and_takes_no_mascot():
    assert character_styles.BY_ID["process_cast"] is pc
    assert tvs.pack("process_cast")["mascot"] is False
    assert "process_cast" in tvs.NO_MASCOT_STYLES
    # the style is told apart from the mascot feature: its name and routing never say mascot
    pack = tvs.pack("process_cast")
    assert "mascot" not in (pack["label"] + pack["tagline"] + json.dumps(pack["routing"])).lower()


# ── the worked example and the refusals ──────────────────────────────────────

def test_the_worked_example_passes():
    assert _check(EXAMPLE) == []


def _move_camera_earlier(d):
    cam = next(e for e in d["events"] if e["type"] == "camera")
    cam["frame"] = next(e for e in d["events"] if e["type"] == "join")["frame"]
    d["events"].sort(key=lambda e: e["frame"])


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d["cast"].append({"id": "x", "body": "bean", "tint": "teal"}) or d["cast"].extend([{"id": f"a{c}", "body": "bean", "tint": "teal"} for c in "bcdef"]),
     "cast must list 1 to 6"),
    (lambda d: d["cast"][0].update(id="bit2"), "may not end in a digit"),
    (lambda d: d["cast"][0].update(body="robot"), "body must be one of"),
    (lambda d: d["cast"][0].update(units=17), "units must be a whole number from 1 to 16"),
    (lambda d: d["cast"].append({"id": "pen", "body": "bean", "tint": "teal", "units": 2}), "units is for a units body only"),
    (lambda d: d["cast"][0].update(name="x" * 15), "name must be text of 1 to 14"),
    (lambda d: d["stations"][0].update(kind="kitchen"), "kind must be one of"),
    (lambda d: d["stations"][0].update(sign="x" * 15), "sign must be text of 1 to 14"),
    (lambda d: d["stations"].append({"id": "spare", "kind": "desk", "sign": "SPARE"}), "never shows station spare"),
    (lambda d: d["events"].reverse(), "List the events in frame order"),
    (lambda d: d["events"][0].update(slot=7), "slot must be a whole number from 0 to 4"),
    (lambda d: next(e for e in d["events"] if e["who"] == "more" and e["type"] == "enter").update(slot=1), "is taken by bit"),
    (lambda d: next(e for e in d["events"] if e["type"] == "clone").update(count=5), "count is how many there are after the split"),
    (lambda d: next(e for e in d["events"] if e["type"] == "join").update(**{"with": "ghost"}), "with must be another actor on stage"),
    (lambda d: next(e for e in d["events"] if e["type"] == "carry").update(text="x" * 19), "at most 18 characters"),
    (lambda d: next(e for e in d["events"] if e["type"] == "react").update(face="angry"), "face must be one of"),
    (lambda d: next(e for e in d["events"] if e["type"] == "prop").update(station="bits"), "appears off screen"),
    (lambda d: next(e for e in d["events"] if e["type"] == "prop").update(prop="rocket"), "prop must be from the library"),
    (lambda d: next(e for e in d["events"] if e["type"] == "prop").update(text="x" * 19), "takes at most 18 characters"),
    (lambda d: d["events"].pop(0), "Nothing enters at frame 0"),
    (_move_camera_earlier, "happens off screen"),
    (lambda d: next(e for e in d["events"] if e["type"] == "react").update(frame=next(e for e in d["events"] if e["type"] == "react")["frame"] + 5),
     "events land on words"),
    (lambda d: [d["events"].remove(e) for e in [e for e in d["events"] if e["type"] in ("react", "carry", "look")][:5]], "Nothing changes from frame"),
])
def test_each_rule_is_refused_with_a_reason(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_card_is_handed_only_at_one_station_and_only_when_held():
    def add(d):
        f = next(e for e in d["events"] if e["type"] == "enter" and e["who"] == "more")["frame"]
        d["events"].append({"type": "hand", "frame": f + 0, "from": "more", "to": "bit"})
        d["events"].sort(key=lambda e: e["frame"])
    assert any("holds no card" in p or "still busy" in p for p in _check(_with(add)))


def test_a_clone_merges_back_and_a_clone_does_not_split():
    def split_clone(d):
        merge = next(e for e in d["events"] if e["type"] == "merge")
        d["events"].insert(d["events"].index(merge), {"type": "clone", "frame": merge["frame"], "who": "bit2", "count": 2})
    assert any("only an original actor splits" in p or "busy" in p or "twitch" in p for p in _check(_with(split_clone)))


def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash():
    for mutate in (
        lambda d: d["events"][0].update(who=["bit"]),
        lambda d: d["events"][1].update(face=None),
        lambda d: d.update(cast="many"),
        lambda d: d["stations"][0].update(sign=7),
        lambda d: next(e for e in d["events"] if e["type"] == "look").update(at=["more"]),
        lambda d: next(e for e in d["events"] if e["type"] == "clone").update(count="three"),
    ):
        problems = _check(_with(mutate))
        assert problems and all(isinstance(p, str) for p in problems)


def test_scene_use_rules():
    assert "used only when the video's visual_style is process_cast" in pc.check_scene_use("stick", EXAMPLE["scenes"])
    two = EXAMPLE["scenes"] + [{"type": "generated", "source": "generated", "src": "vid/x", "startFrame": 0, "durationInFrames": 10}]
    assert "exactly one scene" in pc.check_scene_use("process_cast", two)


def test_nothing_starts_inside_an_insert():
    f = _event(EXAMPLE, "carry")["frame"]
    assert any("inside an insert" in p for p in _check(EXAMPLE, quiet=[(f - 2, f + 40)]))


# ── custom props ─────────────────────────────────────────────────────────────

TICKET = (REF / "example-prop-ticket.tsx").read_text()


def _with_ticket(vid="vid_pc1") -> dict:
    def add(d):
        d["customProps"] = [{"id": "ticket", "src": f"{vid}/prop-ticket", "w": 200, "h": 120, "text": 10}]
        next(e for e in d["events"] if e["type"] == "prop").update(prop="ticket", text="SEAT 12A")
    return _with(add)


def test_the_example_prop_passes_the_source_rules():
    assert _check(_with_ticket(), sources={"vid_pc1/prop-ticket": TICKET}, video_id="vid_pc1") == []


@pytest.mark.parametrize("bad, fragment", [
    ("const f = useCurrentFrame();", "a React or Remotion hook"),
    ('<pattern id="p" />', "an SVG pattern"),
    ('import x from "../../installed/midcenturyHowTo/cel";', "imports ../../installed/midcenturyHowTo/cel"),
])
def test_a_custom_prop_breaking_a_source_rule_is_refused(bad, fragment):
    problems = _check(_with_ticket(), sources={"vid_pc1/prop-ticket": TICKET + "\n" + bad}, video_id="vid_pc1")
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

    def make(video_id, style="process_cast"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'bits and bytes', 'VOICE_READY', ?, ?, ?)", (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_pc1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    assert json.loads(pathlib.Path(result["path"]).read_text())["subtitles"] == tvs.pack("process_cast")["captions"]
    cfg = _with(lambda d: d["stations"][0].update(kind="kitchen"))
    assert server.write_scene_config(vid, cfg)["error"].startswith("The Process Cast video has problems:")


def test_render_style_props_previews_this_style(make_video, tmp_path, monkeypatch):
    from PIL import Image as PILImage
    vid = make_video("vid_pc1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "prop-ticket.tsx").write_text(TICKET)
    assert "error" not in server.write_scene_config(vid, _with_ticket())
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0, script=None):
        seen["spec"] = spec
        PILImage.new("RGB", (1080, 1920), (233, 230, 223)).save(out_png)

    monkeypatch.setattr(server.bean_preview, "render_preview", fake_render)
    result = server.render_style_props(vid)
    assert isinstance(result, list) and json.loads(result[0])["props"] == ["ticket"]
    assert seen["spec"]["style"] == "process_cast" and seen["spec"]["props"][0]["sample"] == "SEAT 12A"
    script = (REPO / "renderer/remotion" / server.bean_preview.CHARACTER_SCRIPT).read_text()
    assert 'process_cast: { module: "processCast/ProcessCastSheet", component: "ProcessCastPropPreview" }' in script


# ── picture checks and the text audit ────────────────────────────────────────

def test_the_picture_checks_and_the_audit_read_this_style():
    assert picture_checks.style_of(EXAMPLE) == "process_cast"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    late = _with(lambda d: d["events"][0].update(frame=10))
    assert "no actor enters by frame 3" in picture_checks.first_frame_warnings(late)[0]
    look = _event(EXAMPLE, "look")["frame"]
    frames = picture_checks.change_frames("process_cast", EXAMPLE)
    assert _event(EXAMPLE, "camera")["frame"] in frames
    assert look not in frames or any(e["frame"] == look and e["type"] != "look" for e in _data()["events"])
    passes, _ = text_audit.plan_passes(EXAMPLE)
    assert [p["first"] for p in passes] == [w[0] for w in pc.audit_windows(EXAMPLE)]
    cam = _event(EXAMPLE, "camera")["frame"]
    assert pc.audit_windows(EXAMPLE)[1][0] >= cam + pc.TIMING["glide"]


def test_bodies_that_would_overlap_are_refused():
    """A wide units body next to another actor, or against the furniture, would
    draw one over the other: the slots are spaced for ordinary bodies only."""
    def crowd(d):
        next(c for c in d["cast"] if c["id"] == "more")["units"] = 8  # the join makes a 12-cube body, 320 wide
    problems = _check(_with(crowd))
    assert any("overlap" in p for p in problems), problems
    assert pc.crowding({"a": {"station": "s", "slot": 0, "body": "bean", "units": 1},
                        "b": {"station": "s", "slot": 2, "body": "bean", "units": 1}}, {"s": "desk"}) == ""
    assert "overlaps the desk" in pc.crowding({"a": {"station": "s", "slot": 2, "body": "units", "units": 16}}, {"s": "desk"})
