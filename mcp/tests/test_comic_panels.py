"""Comic Panels (TMDEV-234): the scene-config checks that keep an unattended
agent from shipping a mistimed, cut-off, crowded or still video, their
agreement with the renderer's contract.ts (through the shared fixture
character-tools/sync-contract.mjs writes), and their place in
write_scene_config, render_style_props, the picture checks and the text audit.

Each refusal guards something the renderer cannot fix: an item that reaches
past its panel is cut by the panel's border, an item that starts after its
panel is read is never on camera, a balloon with no one to point at has a tail
into nothing, two balloons in one panel cover each other, a balloon that
repeats the narration doubles the captions, and more than three seconds with
nothing new is a held frame.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import character_styles
import comic_panels as cp
import picture_checks
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/comic_panels_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-comic-panels/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
WORDS = [w["word"] for w in EXAMPLE_TIMELINE["words"]]
EXTRA = tvs.pack("comic_panels")["extra"]
C = CASES["constants"]


def _data(cfg=None) -> dict:
    return (cfg or EXAMPLE)["scenes"][0]["props"]["comicPanels"]


def _with(mutate) -> dict:
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _check(cfg, quiet=(), sources=None, video_id=""):
    return cp.check(cfg, 30, WORD_STARTS, WORDS, EXTRA, video_id, sources, quiet=quiet)


def _panel(d, page=0, panel=0) -> dict:
    return d["pages"][page]["panels"][panel]


def _item(d, type_, page=0, panel=0) -> dict:
    return next(i for i in _panel(d, page, panel)["items"] if i["type"] == type_)


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_constants_match_the_renderer():
    assert C["LIMITS"] == cp.LIMITS
    assert C["TIMING"] == cp.TIMING
    assert C["LAYOUTS"] == cp.LAYOUTS
    assert C["ACTOR"] == cp.ACTOR
    assert C["CUSTOM"] == cp.CUSTOM
    assert (C["SCALE"]["min"], C["SCALE"]["max"]) == cp.SCALE
    for name in ("CAST_KINDS", "HAIRS", "OUTFITS", "SKINS", "POSES", "FACES", "BALLOONS", "LINES", "ITEM_TYPES", "TONES"):
        assert tuple(C[name]) == getattr(cp, name), name
    assert {k: (v["w"], v["h"]) for k, v in C["PROPS"].items()} == cp.PROP_BOXES


def test_the_pack_lists_exactly_what_the_renderer_draws():
    assert EXTRA["props"] == {k: {"text": v["text"], "acts": []} for k, v in C["PROPS"].items()}
    assert EXTRA["layouts"] == list(C["LAYOUTS"])
    for key, const in (("tones", "TONES"), ("cast_kinds", "CAST_KINDS"), ("hairs", "HAIRS"), ("outfits", "OUTFITS"),
                       ("skins", "SKINS"), ("poses", "POSES"), ("faces", "FACES"), ("balloons", "BALLOONS"), ("lines", "LINES")):
        assert EXTRA[key] == C[const], key


def test_the_helpers_match_the_renderer():
    for c in CASES["item_box"]:
        rect = cp.LAYOUTS[c["layout"]][c["panel"]]
        assert list(cp.item_box(rect, c["x"], c["y"], c["w"], c["h"], c["scale"])) == pytest.approx(c["box"])
    for c in CASES["balloon_size"]:
        assert cp.balloon_size(c["text"]) == (c["size"]["w"], c["size"]["h"])
    for c in CASES["sfx_size"]:
        assert cp.sfx_size(c["text"]) == (c["size"]["w"], c["size"]["h"])


def test_the_style_is_registered_and_takes_no_mascot():
    assert character_styles.BY_ID["comic_panels"] is cp
    assert tvs.pack("comic_panels")["mascot"] is False
    assert "comic_panels" in tvs.NO_MASCOT_STYLES


# ── the worked example and the refusals ──────────────────────────────────────

def test_the_worked_example_passes():
    assert _check(EXAMPLE) == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d["cast"].extend([{"id": f"p{c}", "kind": "person"} for c in "abc"]), "cast must list 1 to 4"),
    (lambda d: d["cast"].append({"id": "you", "kind": "person"}), "id must be a unique lowercase name"),
    (lambda d: d["cast"][0].update(kind="robot"), "kind must be one of"),
    (lambda d: d["cast"].append({"id": "pal", "kind": "hero"}), "Only one character may be the house hero"),
    (lambda d: d["cast"].append({"id": "pal", "kind": "person", "hair": "mohawk"}), "hair must be one of"),
    (lambda d: d["pages"][0].update(start=5), "The first page must start at frame 0"),
    (lambda d: d["pages"][0].update(layout="grid9"), "layout must be one of"),
    (lambda d: d["pages"][0].update(title="x" * 29), "title must be text of 1 to 28"),
    (lambda d: d["pages"][0]["panels"].pop(), "has 4 panels; list exactly that many"),
    (lambda d: _panel(d, 0, 2).update(tone="neon"), "tone must be one of"),
    (lambda d: _panel(d, 0, 3).update(start=_panel(d, 0, 3)["start"] + 30), "a panel needs at least 1.5 s"),
    (lambda d: _item(d, "sfx").update(frame=_item(d, "sfx")["frame"] + 5), "items appear on words"),
    (lambda d: _item(d, "actor").update(x=0.02), "reaches past its panel's top or sides"),
    (lambda d: _item(d, "prop").update(x=0.98), "reaches past its panel's edge"),
    (lambda d: _item(d, "prop").update(prop="unicorn"), "prop must be from the library"),
    (lambda d: _item(d, "prop", 0, 2).update(text="CODE"), "has no text slot"),
    (lambda d: _item(d, "balloon", 0, 1).update(text="x" * 41), "1 to 40 characters"),
    (lambda d: _item(d, "balloon", 0, 1).update(to="nobody"), "to must name a character or prop already in this panel"),
    (lambda d: _item(d, "balloon", 0, 1).update(kind="whisper"), "kind must be one of"),
    (lambda d: _item(d, "sfx").update(text="KABOOOOOOOM"), "a sound of 1 to 10 characters"),
    (lambda d: _item(d, "caption").update(text="Your phone rings at dinner"), "repeats the narration word for word"),
    (lambda d: _item(d, "actor").update(pose="dab"), "pose must be one of"),
    (lambda d: _item(d, "actor").update(who="ghost"), "who must be a cast id"),
    (lambda d: _item(d, "actor", 0, 3).update(scale=2), "scale must be from 0.5 to 1.6"),
    (lambda d: _panel(d, 0, 2).update(items=[i for i in _panel(d, 0, 2)["items"] if i["type"] not in ("prop", "actor")]),
     "has no character or prop"),
    (lambda d: d.update(splash=d["pages"][1]["start"] - 10), "splash must be a whole frame on the last page"),
    (lambda d: d["pages"][1]["panels"][1].update(items=[i for i in d["pages"][1]["panels"][1]["items"] if i["type"] == "actor"]),
     "Nothing changes from frame"),
])
def test_each_rule_is_refused_with_a_reason(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_balloons_and_sound_effects_in_a_panel_may_not_cover_each_other():
    def add_balloon(d):
        b = _item(d, "balloon", 0, 1)
        _panel(d, 0, 1)["items"].append({**b, "frame": b["frame"] + 12, "text": "Hurry up!"})
        _panel(d, 0, 1)["items"].sort(key=lambda i: i["frame"])

    def sfx_under_balloon(d):
        b = _item(d, "balloon", 1, 1)
        _item(d, "sfx", 1, 1).update(x=b["x"], y=b["y"])
    for mutate in (add_balloon, sfx_under_balloon):
        assert any("overlaps a balloon or sound effect" in p for p in _check(_with(mutate)))


def test_hits_are_spaced_across_a_page_not_only_inside_a_panel():
    """The camera shakes for the page, so a hit at the end of one panel and
    another at the start of the next blur into one shake."""
    def two_hits(d):
        nxt = _panel(d, 0, 3)
        _item(d, "hit", 0, 3)["frame"] = nxt["start"]
        nxt["items"].sort(key=lambda i: i["frame"])
        _panel(d, 0, 2)["items"].append({"type": "hit", "frame": nxt["start"] - cp.TIMING["endMargin"]})
    problems = _check(_with(two_hits))
    assert any("blur into one shake" in p for p in problems), problems


def test_a_character_may_be_cut_off_at_the_bottom_of_its_panel():
    """Panels frame people from the waist up, so a bust reaching below the
    border is a crop, not a defect; the top and sides still count."""
    assert _check(_with(lambda d: _item(d, "actor").update(y=0.95))) == []


def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash():
    for mutate in (
        lambda d: _item(d, "actor").update(who=["you"]),
        lambda d: _item(d, "actor").update(face=None),
        lambda d: d.update(cast="many"),
        lambda d: d.update(pages={"a": 1}),
        lambda d: _item(d, "balloon", 0, 1).update(to=["caller"]),
        lambda d: _item(d, "prop").update(scale="big"),
        lambda d: _panel(d).update(items="lots"),
        lambda d: d["pages"][0].update(title=7),
    ):
        problems = _check(_with(mutate))
        assert problems and all(isinstance(p, str) for p in problems)


def test_scene_use_rules():
    assert "used only when the video's visual_style is comic_panels" in cp.check_scene_use("stick", EXAMPLE["scenes"])
    two = EXAMPLE["scenes"] + [{"type": "generated", "source": "generated", "src": "vid/x", "startFrame": 0, "durationInFrames": 10}]
    assert "exactly one scene" in cp.check_scene_use("comic_panels", two)


def test_nothing_starts_inside_an_insert():
    f = _item(EXAMPLE["scenes"][0]["props"]["comicPanels"], "sfx")["frame"]
    assert any("inside an insert" in p for p in _check(EXAMPLE, quiet=[(f - 2, f + 40)]))


# ── custom props ─────────────────────────────────────────────────────────────

TROPHY = (REF / "example-prop-trophy.tsx").read_text()


def _with_trophy(vid="vid_cp1") -> dict:
    def add(d):
        d["customProps"] = [{"id": "trophy", "src": f"{vid}/prop-trophy", "w": 180, "h": 220, "text": 0}]
        p = _item(d, "prop", 1, 2)
        p.update(prop="trophy", scale=1)
    return _with(add)


def test_the_example_prop_passes_the_source_rules():
    assert _check(_with_trophy(), sources={"vid_cp1/prop-trophy": TROPHY}, video_id="vid_cp1") == []


@pytest.mark.parametrize("bad, fragment", [
    ("const f = useCurrentFrame();", "a React or Remotion hook"),
    ('<pattern id="p" />', "an SVG pattern"),
    ('import x from "../../installed/processCast/ink";', "imports ../../installed/processCast/ink"),
])
def test_a_custom_prop_breaking_a_source_rule_is_refused(bad, fragment):
    problems = _check(_with_trophy(), sources={"vid_cp1/prop-trophy": TROPHY + "\n" + bad}, video_id="vid_cp1")
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

    def make(video_id, style="comic_panels"):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'a bank scam call', 'VOICE_READY', ?, ?, ?)", (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_cp1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    assert json.loads(pathlib.Path(result["path"]).read_text())["subtitles"] == tvs.pack("comic_panels")["captions"]
    cfg = _with(lambda d: d["pages"][0].update(layout="grid9"))
    assert server.write_scene_config(vid, cfg)["error"].startswith("The Comic Panels video has problems:")


def test_render_style_props_previews_this_style(make_video, tmp_path, monkeypatch):
    from PIL import Image as PILImage
    vid = make_video("vid_cp1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "prop-trophy.tsx").write_text(TROPHY)
    assert "error" not in server.write_scene_config(vid, _with_trophy())
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0, script=None):
        seen["spec"] = spec
        PILImage.new("RGB", (1080, 1920), (244, 236, 214)).save(out_png)

    monkeypatch.setattr(server.bean_preview, "render_preview", fake_render)
    result = server.render_style_props(vid)
    assert isinstance(result, list) and json.loads(result[0])["props"] == ["trophy"]
    assert seen["spec"]["style"] == "comic_panels"
    script = (REPO / "renderer/remotion" / server.bean_preview.CHARACTER_SCRIPT).read_text()
    assert 'comic_panels: { module: "comicPanels/ComicPanelsSheet", component: "ComicPanelsPropPreview" }' in script


# ── picture checks and the text audit ────────────────────────────────────────

def test_the_picture_checks_and_the_audit_read_this_style():
    assert picture_checks.style_of(EXAMPLE) == "comic_panels"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    late = _with(lambda d: [i.update(frame=10) for i in _panel(d)["items"][:2]])
    assert "the first panel has no character or prop by frame 3" in picture_checks.first_frame_warnings(late)[0]
    frames = picture_checks.change_frames("comic_panels", EXAMPLE)
    assert _panel(_data(), 0, 1)["start"] in frames
    assert _item(_data(), "caption")["frame"] not in frames or any(
        i["frame"] == _item(_data(), "caption")["frame"] and i["type"] != "caption" for p in _data()["pages"] for pn in p["panels"] for i in pn["items"])
    passes, _ = text_audit.plan_passes(EXAMPLE)
    assert [p["first"] for p in passes] == [w[0] for w in cp.audit_windows(EXAMPLE)]
    # each window waits until the camera has arrived and the first item has popped
    assert cp.audit_windows(EXAMPLE)[1][0] >= _panel(_data(), 0, 1)["start"] + cp.TIMING["read"]
