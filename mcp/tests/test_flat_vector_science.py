"""Flat Vector Science: the scene-config checks that keep an unattended agent
from shipping a crowded, mistimed or still science video, or a drawing of its
own the renderer cannot afford, their agreement with the renderer's
contract.ts and stage.ts and the style pack, and their place in
write_scene_config, validate_job and the text audit.

Each refusal guards something the renderer cannot fix: a prop nobody drew
renders nothing, two props in one slot overlap, two red numbers make the
payoff unclear, a pill wider than the frame is cut off, a ladder rung cut
before it lands is lost, four seconds with nothing new is a dead shot, and a
prop that uses a filter or the frame breaks the bitmap it is drawn into.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import flat_vector_science as fv
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/flat_vector_science_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-flat-vector-science/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("flat_vector_science")["extra"]
OCTOPUS = (REF / "example-prop-octopus.tsx").read_text()
TS = (REPO / "renderer/remotion/src/scenes/installed/flatVector/contract.ts").read_text()


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    c = CASES["constants"]
    assert fv.LIMITS == c["LIMITS"]
    assert fv.TIMING == c["TIMING"]
    assert fv.GEOMETRY == c["GEOMETRY"]


def test_the_catalogues_match_the_renderer_and_the_pack():
    for name, py in [("SHOT_KINDS", fv.SHOT_KINDS), ("BACKDROPS", fv.BACKDROPS), ("SLOTS", fv.SLOTS),
                     ("SIZES", fv.SIZES), ("CUTS", fv.CUTS)]:
        line = next(ln for ln in TS.splitlines() if ln.startswith(f"export const {name} = ["))
        assert tuple(line.split("[", 1)[1].split("]")[0].replace('"', "").replace(" ", "").split(",")) == py, name
    assert EXTRA["shotKinds"] == list(fv.SHOT_KINDS) and EXTRA["backdrops"] == list(fv.BACKDROPS)
    lib = fv.library(EXTRA)
    assert {"whale", "earth", "cell", "bus", "mountain", "sun"} <= set(lib)
    assert set(lib) == {p for group in EXTRA["props"].values() for p in group}
    assert set(EXTRA["lights"]) <= set(lib)


def test_events_still_stretches_and_the_helpers_are_worked_out_the_same_way():
    data = CASES["data"]
    assert [fv.event_frames(s) for s in data["shots"]] == CASES["event_frames"]
    assert fv.quiet_spans(data, CASES["total"]) == CASES["quiet_spans"]
    for case in CASES["pill_width"]:
        assert fv.pill_width(case["parts"]) == case["width"]
    for case in CASES["grouped"]:
        assert fv.grouped(case["n"]) == case["text"]
    for case in CASES["prop_scale"]:
        assert fv.prop_scale(fv.library(EXTRA)[case["what"]], case["size"]) == pytest.approx(case["scale"])


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None, quiet=(), sources=None):
    return fv.check(config or EXAMPLE, 30, WORD_STARTS, EXTRA, "vid_example", sources=sources, quiet=quiet)


def _data(cfg):
    return cfg["scenes"][0]["props"]["flatVector"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _shot(d, kind, k=0):
    return [s for s in d["shots"] if s["kind"] == kind][k]


def test_the_example_passes():
    assert _check() == []


def test_the_example_shows_every_kind_of_shot():
    assert {s["kind"] for s in _data(EXAMPLE)["shots"]} == set(fv.SHOT_KINDS)


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(colour="red"), "unknown field"),
    (lambda d: d["shots"].__setitem__(slice(2, None), []), "shots must list"),
    (lambda d: d["shots"][0].update(start=3), "first shot must start at frame 0"),
    (lambda d: d["shots"][0].update(cut="lens"), "first shot arrives on a cut"),
    (lambda d: d["shots"][1].update(kind="poster"), "kind is one of"),
    (lambda d: d["shots"][0].update(backdrop="desert"), "backdrop must be one of"),
    (lambda d: d["shots"][1].update(cut="spin"), "cut must be one of"),
    (lambda d: d["shots"][0]["items"][0].update(what="unicorn"), "is not a library prop"),
    (lambda d: d["shots"][0]["items"][0].update(size="xl"), "size must be one of"),
    (lambda d: d["shots"][0]["items"].append({"what": "moon", "slot": "center", "size": "s"}), "two props stand"),
    (lambda d: d["shots"][0]["pills"][0].update(on="left"), "the slot of one of the shot's items"),
    (lambda d: d["shots"][0]["pills"][0]["parts"][0].update(text="A PILL THAT IS FAR TOO LONG"), "parts must list"),
    (lambda d: d["shots"][0]["pills"][0]["parts"][0].update(at=3), "not on a word"),
    (lambda d: _shot(d, "subject", 1)["pills"][0]["parts"][0].update(red=True), "red marks one"),
    (lambda d: _shot(d, "subject", 1)["rule"].update(beside="left"), "rule must be"),
    (lambda d: _shot(d, "ladder")["rungs"].__setitem__(slice(1, None), []), "rungs must list"),
    (lambda d: _shot(d, "ladder")["rungs"][0].update(value="A VALUE TOO LONG"), "label 1 to"),
    (lambda d: _shot(d, "descent")["layers"][1].update(value=10), "deeper than the layer before"),
    (lambda d: _shot(d, "descent").update(unit="metres"), "unit must be at most"),
    (lambda d: _shot(d, "stages")["steps"].reverse(), "step 2: at must be"),
    (lambda d: _shot(d, "zoom")["levels"][0].update(label="A VERY LONG LABEL"), "label must be 1 to"),
    (lambda d: d["shots"][0].update(counter={"label": "DEPTH", "value": -5, "unit": "m", "at": d["shots"][0]["pills"][0]["parts"][0]["at"]}),
     "value must be a number from 0"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    def still(d):
        s = _shot(d, "subject", 1)
        s.pop("rule")
        s.pop("pills")
        for it in s["items"]:
            it.pop("at", None)
    problems = _check(_with(still))
    assert any("nothing new arrives" in p for p in problems), problems


def test_a_rung_cut_before_it_lands_is_refused():
    cfg = copy.deepcopy(EXAMPLE)
    d = _data(cfg)
    ladder = _shot(d, "ladder")
    nxt = d["shots"][d["shots"].index(ladder) + 1]["start"]
    late = nxt - 10
    ladder["rungs"][-1]["at"] = late
    problems = fv.check(cfg, 30, WORD_STARTS + [late], EXTRA, "vid_example")
    assert any("frames to read it" in p for p in problems), problems


def test_nothing_arrives_inside_an_insert_and_no_transition_runs_into_one():
    d = _data(EXAMPLE)
    subj = _shot(d, "subject", 2)  # the lungs
    nxt = d["shots"][d["shots"].index(subj) + 1]
    last = fv.event_frames(subj)[-1]
    # a window over the lungs shot's quiet tail, ending well before the zoom's lens starts
    ok = [(last + 6, nxt["start"] - fv.TIMING["lens"] - 2)]
    assert _check(quiet=ok) == []
    # the zoom arrives through a lens over the 18 frames before its start: a window there is refused
    into = [(last + 6, nxt["start"] - 4)]
    assert any("transition runs" in p for p in _check(quiet=into))
    over = [(fv.event_frames(subj)[1] - 4, fv.event_frames(subj)[1] + 40)]
    assert any("inside an insert" in p for p in _check(quiet=over))


def test_the_scene_use_rule():
    assert fv.check_scene_use("flat_vector_science", EXAMPLE["scenes"]) == ""
    assert "visual_style is flat_vector_science" in fv.check_scene_use("stick", EXAMPLE["scenes"])


def test_the_text_audit_samples_every_shot():
    windows = fv.shot_windows(EXAMPLE)
    assert len(windows) == len(_data(EXAMPLE)["shots"])
    passes, _ = text_audit.plan_passes(EXAMPLE)
    assert [p["first"] for p in passes] == [w[0] for w in windows]


# ── the video's own props ─────────────────────────────────────────────────────

def _custom(changes=None):
    c = {"id": "octopus", "src": "vid_example/prop-octopus", "box": [360, 360]}
    c.update(changes or {})
    return c


def _with_octopus(changes=None):
    def add(d):
        d["customProps"] = [_custom(changes)]
        d["shots"][0]["items"][0]["what"] = "octopus"
    return _with(add)


def test_the_example_octopus_passes():
    assert _check(_with_octopus(), sources={"vid_example/prop-octopus": OCTOPUS}) == []


@pytest.mark.parametrize("changes, fragment", [
    ({"id": "whale"}, "not a library prop"),
    ({"src": "other_video/prop-octopus"}, "src must be"),
    ({"box": [10, 400]}, "box is [width, height]"),
    ({"light": "gold"}, "light is the colour"),
    ({"acts": []}, "must be {"),
])
def test_a_bad_custom_prop_entry_is_refused(changes, fragment):
    problems = _check(_with_octopus(changes), sources={"vid_example/prop-octopus": OCTOPUS})
    assert any(fragment in p for p in problems), problems


@pytest.mark.parametrize("line, fragment", [
    ('<filter id="b"><feGaussianBlur stdDeviation="4" /></filter>', "SVG filter"),
    ("const f = useCurrentFrame();", "a hook or the frame"),
    ("<text x={0} y={0}>OCTOPUS</text>", "SVG text"),
    ('import { x } from "../../installed/whiteboard/doodles";', "it imports"),
    ("const r = Math.random();", "randomness"),
])
def test_a_prop_file_that_breaks_the_rules_is_refused(line, fragment):
    body = OCTOPUS.replace("export default function Octopus() {", f"{line}\nexport default function Octopus() {{")
    problems = _check(_with_octopus(), sources={"vid_example/prop-octopus": body})
    assert any(fragment in p for p in problems), problems


def test_a_missing_prop_file_is_refused():
    assert any("write it with write_scene_file first" in p for p in _check(_with_octopus(), sources={}))


# ── write_scene_config and validate_job ──────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")

    def make(video_id, style="flat_vector_science", octopus=False):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'how deep the ocean goes', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        if octopus:
            (tmp_path / "generated" / video_id).mkdir(parents=True, exist_ok=True)
            (tmp_path / "generated" / video_id / "prop-octopus.tsx").write_text(OCTOPUS)
        return video_id

    return make


def _for(video_id):
    cfg = _with_octopus({"src": f"{video_id}/prop-octopus"})
    return cfg


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_fv1", octopus=True)
    result = server.write_scene_config(vid, _for(vid))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("flat_vector_science")["captions"]


def test_a_missing_prop_file_is_refused_by_the_tool(make_video):
    vid = make_video("vid_fv2")
    assert "write it with write_scene_file first" in server.write_scene_config(vid, _for(vid))["error"]


def test_another_style_cannot_use_the_flat_vector_scene(make_video):
    vid = make_video("vid_fv3", style="motion_graphics")
    assert "visual_style is flat_vector_science" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_validate_job_rechecks_a_redrawn_prop(make_video, tmp_path):
    vid = make_video("vid_fv4", octopus=True)
    assert "error" not in server.write_scene_config(vid, _for(vid))
    (tmp_path / "generated" / vid / "prop-octopus.tsx").write_text(OCTOPUS.replace("<g>", "<g filter=\"url(#x)\">", 1))
    errors = server._fv_custom_prop_errors(vid, _for(vid))
    assert any("SVG filter" in e for e in errors), errors


def test_render_style_parts_refuses_what_it_cannot_preview(make_video):
    vid = make_video("vid_fv5", style="stick")
    assert "is for Night Signal, Flat Vector Science and Isometric Infographic videos" in server.render_style_parts(vid)["error"]
    vid2 = make_video("vid_fv6")
    assert "no Flat Vector Science scene-config yet" in server.render_style_parts(vid2)["error"]
    assert "error" not in server.write_scene_config(vid2, copy.deepcopy(EXAMPLE))
    assert "nothing of yours" in server.render_style_parts(vid2)["error"]


def test_render_style_parts_sends_the_props_to_the_renderer(make_video, monkeypatch):
    vid = make_video("vid_fv7", octopus=True)
    assert "error" not in server.write_scene_config(vid, _for(vid))
    seen = {}

    def fake(remotion, spec, out_png, script=None):
        from PIL import Image
        seen.update(spec=spec, script=script)
        Image.new("RGB", (1080, 1920), "black").save(out_png)
    monkeypatch.setattr(server.bean_preview, "render_preview", fake)
    out = server.render_style_parts(vid)
    assert json.loads(out[0])["parts"] == ["octopus"]
    assert seen["spec"]["style"] == "flat_vector_science" and seen["spec"]["props"][0]["id"] == "octopus"
    assert seen["script"] == server.bean_preview.STYLE_PARTS_SCRIPT
