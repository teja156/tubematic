"""Storybook Reveal (TMDEV-231): the scene-config checks that keep an
unattended agent from shipping a foreign or untreated picture, the hero sheet
as a page, a pencil plate that is not its page's own, a reveal off the
narration, a colour that arrives too late to be seen, or a still page; their
agreement with the renderer's contract.ts and the style pack; their place in
write_scene_config, the text audit and the picture checks; and the hero
sheet, the page cap and the pencil treatment that guard the paid image calls.

Each refusal guards something the renderer cannot fix: it draws whatever it is
given, so a pencil plate of another picture would ship as a drawing that the
colour does not cover, and a colour flooding in the page's last frames would
leave the viewer a pencil sketch.

Run from repo root: pytest mcp/tests/
"""
import base64
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import picture_checks
import server
import storybook_reveal as sr
from quiet_windows import silent_windows
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
KIT = REPO / "renderer/remotion/src/scenes/installed/storybookReveal"
CONTRACT_TS = KIT / "contract.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/storybook_reveal_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-storybook-reveal/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
PACK = tvs.pack("storybook_reveal")
EXTRA = PACK["extra"]
PICS = PACK["pictures"]
VID = "vid_example01"
STAIRS, STORM, BEAM, DAWN, KIND = 0, 1, 2, 3, 4

# Marks the tests that need the style wired into write_scene_config, the text
# audit and the picture checks (mcp/server.py, mcp/text_audit.py,
# mcp/picture_checks.py); they run once that wiring is in.
wired = pytest.mark.skipif(not hasattr(server, "storybook_reveal"), reason="wired in WIRING-storybook-reveal.md")


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    body = re.sub(r"//.*", "", body)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)(?=\s*(?:[,}\n]|$))", body)}


def _ts_array(name: str) -> tuple:
    body = re.search(rf"export const {name} = \[(.*?)\] as const;", CONTRACT_TS.read_text(), re.S).group(1)
    return tuple(re.findall(r'"([\w-]+)"', body)) or tuple(int(v) for v in re.findall(r"\d+", body))


def _data(cfg):
    return cfg["scenes"][0]["props"]["reveal"]


def _check(cfg=None, quiet=(), video_id=VID, words=None, silences=None):
    # the example's narration has real pauses in it (the way a [long pause] script does), as the server reads them
    if silences is None:
        silences = silent_windows(EXAMPLE_TIMELINE["words"])
    return sr.check(cfg or EXAMPLE, 30, WORD_STARTS if words is None else words, EXTRA, video_id, quiet=quiet,
                    silences=silences)


def _stalls(errors):
    """Every "nothing new happens from frame A to C" refusal as (A, C)."""
    return [(int(a), int(c)) for e in errors if "nothing new happens" in e
            for a, c in [re.search(r"from frame (\d+) to (\d+)", e).groups()]]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _page(d, i):
    return d["pages"][i]


def _paths(name, vid=VID):
    return {"image": f"/public/{vid}/images/{name}.png", "pencil": f"/public/{vid}/images/treated/{name}.pencil.png"}


# ── agreement with the renderer and the pack ────────────────────────────────

def test_the_constants_equal_the_renderers_contract():
    assert _ts_block("ZONES") == sr.ZONES
    assert _ts_block("LIMITS") == sr.LIMITS
    assert _ts_block("TIMING") == sr.TIMING
    assert _ts_array("TURNS") == sr.TURNS
    assert _ts_array("TITLE_SIZES") == sr.TITLE_SIZES
    assert f"TITLE_CHAR_W = {sr.TITLE_CHAR_W};" in CONTRACT_TS.read_text()


def test_the_pack_lists_what_the_contract_holds():
    assert EXTRA["turns"] == list(sr.TURNS)
    assert EXTRA["treatment"] == sr.TREATMENT and PICS["treatments"] == [sr.TREATMENT]
    assert EXTRA["sheet"] == sr.SHEET and PICS["sheet"]["name"] == sr.SHEET and PICS["apart"] == [sr.SHEET]
    # twelve pages' stills and the hero sheet in a slot of its own
    assert PACK["routing"]["images"] == sr.LIMITS["maxImages"] + 1
    assert "house" not in PICS["sheet"] and PICS["still_aspect"] == "1:1"
    assert PACK["inserts"] == {"host": True, "transition": "wipe"}
    assert PACK["canvas"] == "light" and PACK["mascot"] is False and PACK["order"] == 140
    assert tvs.needs_openai_key("storybook_reveal") is True and tvs.needs_gpu("storybook_reveal") is False


def test_the_routing_text_names_who_fits_instead():
    avoid = " ".join(PACK["routing"]["avoid_for"])
    for other in ("Storybook Atlas", "Archive and Engraving", "Illustrated", "Stick Explainer", "Bean Explainer"):
        assert other in avoid, other
    assert "real people" in PACK["routing"]["cannot_show"]
    for phrase in ("one protagonist", "moral", "never a real or named person", "brand"):
        assert phrase in PACK["script"].replace("Never", "never"), phrase


def test_the_shared_cases_agree():
    for c in CASES["title_size"]:
        assert sr.title_size(c["text"]) == c["size"]
    for c in CASES["picture_box"]:
        assert list(sr.picture_box(c["w"], c["h"])) == pytest.approx(c["box"])
    for c in CASES["push_scale"]:
        assert sr.push_scale(c["frame"], c["land"], c["end"]) == pytest.approx(c["scale"])
    for c in CASES["pushed_box"]:
        assert list(sr.pushed_box(c["box"], c["scale"], c["focus"])) == pytest.approx(c["out"])
    for c in CASES["land_frame"]:
        assert sr.land_frame(c["colourAt"]) == c["land"]


def test_every_title_fits_its_line_at_the_smallest_size():
    longest = "x" * sr.LIMITS["titleChars"]
    assert len(longest) * sr.TITLE_SIZES[1] * sr.TITLE_CHAR_W <= sr.ZONES["titleWidth"]
    assert sr.title_size(longest) * len(longest) * sr.TITLE_CHAR_W <= sr.ZONES["titleWidth"]


def test_the_captions_are_the_fill_look_with_no_plate_the_server_accepts():
    caps = PACK["captions"]
    assert caps["look"] == "fill" and caps["background"] == "none" and caps["position"] == 0.72
    assert caps["maxWords"] == 5 and "Lora" in caps["fontFamily"]
    centre = caps["position"] * 1920
    assert sr.ZONES["captionTop"] < centre < sr.ZONES["captionBottom"]
    assert server._validate_subtitles(caps) == ""


# ── the checks ───────────────────────────────────────────────────────────────

def test_the_skills_worked_example_passes():
    assert _check() == []


def test_the_scene_is_this_styles_alone():
    assert "used only when" in sr.check_scene_use("stick", EXAMPLE["scenes"])
    assert sr.check_scene_use("stick", [{"src": "Other"}]) == ""
    two = EXAMPLE["scenes"] + [{"type": "generated", "src": "x"}]
    assert "one scene" in sr.check_scene_use("storybook_reveal", two)


def _image(d, i, value):
    _page(d, i)["image"] = value


def _pencil(d, i, value):
    _page(d, i)["pencil"] = value


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: _page(d, STORM).update(start=_page(d, STORM)["start"] + 5), "not on a word"),
    (lambda d: _page(d, STAIRS).update(title="The keeper who never slept"), "title must be 1 to 3 words"),
    (lambda d: _page(d, STAIRS).update(title="Unforgettableness Again"[:20] + "xxxxxxx"), "at most 24 characters"),
    (lambda d: _page(d, STAIRS).update(title=""), "title must be"),
    (lambda d: _image(d, STAIRS, f"/public/{VID}/images/treated/page-stairs.pencil.png"), "a still of this video"),
    (lambda d: _image(d, STAIRS, "/public/vid_other/images/page-stairs.png"), "a still of this video"),
    (lambda d: _image(d, STAIRS, f"/jobs/{VID}/images/page-stairs.png"), "a still of this video"),
    (lambda d: _image(d, STAIRS, f"/public/{VID}/images/page-stairs.jpg"), "a still of this video"),
    (lambda d: _page(d, STAIRS).update(_paths("hero")), "hero sheet"),
    (lambda d: _pencil(d, STAIRS, f"/public/{VID}/images/treated/page-storm.pencil.png"), "pencil plate of this page's own image"),
    (lambda d: _pencil(d, STAIRS, f"/public/{VID}/images/page-stairs.png"), "pencil plate of this page's own image"),
    (lambda d: _pencil(d, STAIRS, f"/public/{VID}/images/treated/page-stairs.engraving.png"), "pencil plate"),
    (lambda d: _pencil(d, STAIRS, "/public/vid_other/images/treated/page-stairs.pencil.png"), "pencil plate"),
    (lambda d: _page(d, STAIRS).update(focus=[0.5, 1.4]), "focus must be [u, v]"),
    (lambda d: _page(d, STORM).update(turn="fold"), "turn must be one of"),
    (lambda d: _page(d, STAIRS).update(turn="curl"), "first page cannot turn"),
    (lambda d: _page(d, STORM).update(pencilAt=_page(d, STORM)["start"] + 2), "at least 6 frames after"),
    (lambda d: _page(d, STORM).update(pencilAt=_page(d, STORM)["pencilAt"] + 5), "pencilAt is frame"),
    (lambda d: _page(d, STORM).update(pencilAt=_page(d, BEAM)["start"] + 10), "pencilAt must be a frame inside"),
    (lambda d: _page(d, STORM).update(colourAt=_page(d, STORM)["pencilAt"] + 10), "once the pencil plate has wiped in"),
    (lambda d: _page(d, STORM).update(colourAt=_page(d, STORM)["colourAt"] + 5), "not on a word"),
    (lambda d: _page(d, KIND).update(colourAt=WORD_STARTS[-2]), "within a second"),
    (lambda d: _page(d, STAIRS).update(colour="gold"), "unknown field"),
    (lambda d: d.update(music="soft"), "unknown field"),
])
def test_a_bad_config_is_refused_with_its_cause(mutate, fragment):
    errors = _check(_with(mutate))
    assert any(fragment in e for e in errors), errors


def test_the_first_page_may_open_on_its_pencil_or_wipe_it_in_on_a_word():
    assert _check() == [] and _page(_data(EXAMPLE), STAIRS)["pencilAt"] == 0
    later = _with(lambda d: _page(d, STAIRS).update(pencilAt=WORD_STARTS[0]))
    assert _check(later) == []
    assert any("at least 6 frames after" in e for e in _check(_with(lambda d: _page(d, STAIRS).update(pencilAt=3))))


def test_a_colour_too_close_to_its_pages_end_is_refused():
    # a page 100 frames long whose colour follows its pencil in time but lands 7 frames before it ends
    words = list(range(0, 2000, 3))
    cfg = {"totalFrames": 100, "scenes": [{"type": "generated", "source": "installed", "src": "StorybookReveal",
                                           "startFrame": 0, "durationInFrames": 100, "props": {"reveal": {"pages": [
                                               {"start": 0, "title": "Late", **_paths("page-dawn"), "pencilAt": 60,
                                                "colourAt": 75}]}}}]}
    errors = _check(cfg, words=words)
    assert any("too close to the page's end" in e for e in errors), errors


def _many(n, curl_every=0, distinct=True):
    """n pages of 3 s each over a word every 10 frames: a sound page, n times."""
    words = list(range(0, 90 * n + 100, 10))
    pages = []
    for k in range(n):
        p = {"start": 90 * k, "title": f"Page {k + 1}", **_paths(f"p{k}" if distinct else "p0"),
             "pencilAt": 90 * k + 10, "colourAt": 90 * k + 30}
        if curl_every and k and k % curl_every == 0:
            p["turn"] = "curl"
        pages.append(p)
    cfg = {"totalFrames": 90 * n, "scenes": [{"type": "generated", "source": "installed", "src": "StorybookReveal",
                                              "startFrame": 0, "durationInFrames": 90 * n,
                                              "props": {"reveal": {"pages": pages}}}]}
    return cfg, words


def test_twelve_stills_pass_and_a_thirteenth_is_refused():
    cfg, words = _many(12)
    assert _check(cfg, words=words) == []
    cfg, words = _many(13)
    assert any("at most 12" in e for e in _check(cfg, words=words))
    cfg, words = _many(13, distinct=False)                     # one still shown on every page
    assert _check(cfg, words=words) == []


def test_more_pages_than_the_limit_are_refused():
    cfg, words = _many(sr.LIMITS["maxPages"] + 1, distinct=False)
    assert any("1 to 24 pages" in e for e in _check(cfg, words=words))


def test_at_most_two_curls():
    cfg, words = _many(4, curl_every=1, distinct=False)
    assert any("at most 2" in e for e in _check(cfg, words=words))
    cfg, words = _many(4, curl_every=2, distinct=False)
    assert _check(cfg, words=words) == []


def _early_dawn(d):
    """The dawn page left out: the page before it lasts to the end of the dawn, its colour landed 7 s before."""
    d["pages"].pop(DAWN)


def test_the_colour_follows_the_pencil_within_a_second():
    for gap, ok in ((10, False), (20, True), (30, True), (40, False)):
        cfg, words = _many(1)
        _data(cfg)["pages"][0].update(colourAt=10 + gap)
        errors = _check(cfg, words=words)
        assert (errors == []) is ok, (gap, errors)
        if not ok:
            assert any("within a second" in e for e in errors), errors


def test_a_still_page_is_refused_and_the_push_does_not_count():
    early = _with(_early_dawn)
    errors = _check(early, silences=[])
    assert any("nothing new happens" in e and "slow push does not count" in e for e in errors), errors


def test_a_silent_pause_is_not_a_stall():
    early = _with(_early_dawn)
    stalls = _stalls(_check(early, silences=[]))
    assert stalls
    assert _check(early, silences=[(a + 5, c - 5) for a, c in stalls]) == []
    a, c = stalls[0]
    assert any("nothing new happens" in e for e in _check(early, silences=[(a + 5, a + 20)]))


def test_a_page_left_an_empty_card_for_long_is_refused():
    cfg, _ = _many(1)
    words = list(range(0, 600, 10))
    cfg["totalFrames"] = cfg["scenes"][0]["durationInFrames"] = 600
    _data(cfg)["pages"][0].update(pencilAt=300, colourAt=320)
    errors = _check(cfg, words=words, silences=[])
    assert any("empty card" in e and "300" in e for e in errors), errors


def test_the_pencil_and_the_colour_may_play_through_a_silent_pause():
    """A pause right after a page starts: no word to wipe on for seconds, so a page would sit empty."""
    cfg, _ = _many(1)
    words = [0, 10, 20, 30, 200, 210, 220]
    cfg["totalFrames"] = cfg["scenes"][0]["durationInFrames"] = 300
    pause = silent_windows([{"startFrame": 0, "endFrame": 8}, {"startFrame": 10, "endFrame": 18},
                            {"startFrame": 200, "endFrame": 208}])
    assert pause == [(18, 200)]
    page = _data(cfg)["pages"][0]
    page.update(start=0, pencilAt=40, colourAt=60)   # inside the pause, a second and a bit in
    assert _check(cfg, words=words, silences=pause) == []
    assert any("not on a word" in e for e in _check(cfg, words=words, silences=[]))


def test_nothing_starts_inside_an_insert_window_and_a_window_is_not_still():
    storm = _page(_data(EXAMPLE), STORM)
    assert any("runs into an insert" in e and "turns in" in e
               for e in _check(quiet=[(storm["start"] - 10, storm["start"] + 10)]))
    assert any("floods its colour" in e for e in _check(quiet=[(storm["colourAt"] - 5, storm["colourAt"] + 5)]))
    # an insert that opens while the flood is still running hides its end
    late = (storm["colourAt"] + sr.TIMING["colour"] - 4, storm["colourAt"] + sr.TIMING["colour"] + 40)
    assert any("floods its colour" in e and "runs into an insert" in e for e in _check(quiet=[late]))
    early = _with(_early_dawn)
    beam = _page(_data(early), BEAM)
    land = sr.land_frame(beam["colourAt"])
    assert any("nothing new happens" in e for e in _check(early, silences=[]))
    assert _check(early, silences=[], quiet=[(land + 20, land + 120)]) == []


# ── the text audit and the picture checks ────────────────────────────────────

def test_each_page_is_sampled_once_its_colour_has_landed():
    windows = sr.page_windows(EXAMPLE)
    pages = _data(EXAMPLE)["pages"]
    assert len(windows) == len(pages)
    for (first, end), p in zip(windows, pages):
        assert sr.land_frame(p["colourAt"]) <= first < end
    assert sr.page_windows({"scenes": [{"src": "Other"}]}) == []


def test_the_change_frames_are_each_pages_start_pencil_and_colour():
    frames = sr.change_frames(EXAMPLE)
    for p in _data(EXAMPLE)["pages"]:
        assert {p["start"], p["pencilAt"], p["colourAt"]} <= set(frames)


@wired
def test_the_text_audit_samples_each_page():
    plan = text_audit.plan_passes(EXAMPLE)
    assert plan["passes"] if isinstance(plan, dict) else plan


@wired
def test_the_picture_checks_read_the_style():
    assert picture_checks.style_of(EXAMPLE) == "storybook_reveal"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    late = _with(lambda d: _page(d, STAIRS).update(pencilAt=WORD_STARTS[0]))
    assert picture_checks.first_frame_warnings(late)
    frames = picture_checks.change_frames("storybook_reveal", EXAMPLE)
    for p in _data(EXAMPLE)["pages"]:
        assert {p["start"], p["colourAt"]} <= set(frames)


# ── write_scene_config, the hero sheet, the page cap and treat_image ─────────

def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "_image_reservations", {})

    def make(video_id=VID, style="storybook_reveal", images=("page-stairs", "page-storm", "page-dawn")):
        from PIL import Image
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                        "VALUES (?, NULL, 'the lighthouse keeper', 'VOICE_READY', ?, ?, ?)",
                        (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        for name in images:
            Image.new("RGB", (68, 120), (240, 230, 200)).save(d / "images" / f"{name}.png")
        return video_id

    return make


@wired
def test_a_sound_config_is_written_with_the_styles_captions(make_video, tmp_path):
    vid = make_video()
    cfg = copy.deepcopy(EXAMPLE)
    assert "subtitles" not in cfg
    out = server.write_scene_config(vid, cfg)
    assert "error" not in out, out
    written = json.loads((tmp_path / "jobs" / vid / "scene-config.json").read_text())
    assert written["subtitles"]["look"] == "fill" and written["subtitles"]["background"] == "none"
    assert written["subtitles"]["color"] == "#38382F"


@wired
def test_a_broken_config_writes_nothing(make_video, tmp_path):
    vid = make_video()
    bad = _with(lambda d: _page(d, STAIRS).update(_paths("hero")))
    assert "Storybook Reveal video has problems" in server.write_scene_config(vid, bad)["error"]
    assert not (tmp_path / "jobs" / vid / "scene-config.json").exists()


@wired
def test_the_scene_on_another_style_is_refused(make_video):
    vid = make_video(style="stick")
    assert "used only when" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture
def paid(monkeypatch):
    """httpx.Client replaced by one that records each paid call and answers with a picture."""
    calls = []

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None, files=None, data=None):
            calls.append({"url": url, "json": json, "files": files, "data": data})

            class R:
                status_code, text = 200, ""

                def json(self):
                    return {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}
            return R()

    import httpx
    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(server, "_openai_key", lambda: "sk-test")
    monkeypatch.setattr(server, "_guard_scene_work", lambda *a, **k: None)
    return calls


def test_the_hero_sheet_is_made_from_the_description_alone_and_is_wide(make_video, paid):
    vid = make_video(images=())
    out = server.generate_image(vid, "hero", "an old lighthouse keeper with grey hair in a bun, a yellow raincoat")
    assert "error" not in out, out
    (call,) = paid
    assert call["url"] == server.OPENAI_IMAGES_URL and call["files"] is None
    assert call["json"]["size"] == "1920x1088" and out["aspect_ratio"] == "16:9"
    prompt = call["json"]["prompt"]
    assert prompt == (f"{PICS['sheet']['lead']} an old lighthouse keeper with grey hair in a bun, a yellow "
                      f"raincoat. {PICS['sheet']['style']}")
    assert (server.JOBS_DIR / vid / "images" / "hero.png").is_file()


def test_a_page_with_the_hero_is_painted_from_the_videos_own_sheet(make_video, paid):
    vid = make_video(images=("hero",))
    out = server.generate_image(vid, "page-stairs", "She climbs the stone stairs with a lantern.", aspect_ratio="16:9",
                                reference="hero")
    assert "error" not in out, out
    (call,) = paid
    assert call["url"] == server.OPENAI_IMAGE_EDITS_URL
    assert call["files"]["image[]"][1] == (server.JOBS_DIR / vid / "images" / "hero.png").read_bytes()
    assert call["data"]["size"] == server.OPENAI_SIZE_BY_ASPECT["1:1"] and out["aspect_ratio"] == "1:1"
    assert call["data"]["prompt"] == (f"{PICS['still_lead']} She climbs the stone stairs with a lantern. "
                                      f"{PICS['still_style']}")


def test_a_page_without_the_hero_gets_the_page_style_and_no_reference(make_video, paid):
    vid = make_video(images=())
    out = server.generate_image(vid, "the-sea", "A calm sea at dawn with a small boat")
    assert "error" not in out, out
    (call,) = paid
    assert call["url"] == server.OPENAI_IMAGES_URL and call["json"]["size"] == server.OPENAI_SIZE_BY_ASPECT["1:1"]
    assert call["json"]["prompt"] == f"A calm sea at dawn with a small boat. {PICS['still_style']}"


@pytest.mark.parametrize("name, reference, images, fragment", [
    ("hero", "hero", ("hero",), "your description alone"),
    ("hero", "page-stairs", ("page-stairs",), "your description alone"),
    ("page-stairs", "hero", (), "Make the reference sheet first"),
    ("page-stairs", "page-storm", (), "is not an image of this video yet"),
])
def test_a_wrong_reference_is_refused_before_the_paid_call(make_video, paid, name, reference, images, fragment):
    vid = make_video(images=images)
    out = server.generate_image(vid, name, "a scene", reference=reference)
    assert fragment in out["error"], out
    assert paid == []


def test_a_reference_on_another_style_is_refused(make_video, paid):
    vid = make_video(style="illustrated", images=("hero",))
    assert "only for a style painted from a reference sheet" in server.generate_image(
        vid, "a", "a scene", reference="hero")["error"]
    assert paid == []


def test_a_thirteenth_page_still_is_refused_while_the_hero_keeps_its_slot(make_video, paid):
    vid = make_video(images=[f"p{k}" for k in range(12)])
    out = server.generate_image(vid, "one-more", "a scene")
    assert "already has 12 page pictures" in out["error"] and "(12)" in out["error"]
    assert paid == []
    assert "error" not in server.generate_image(vid, "hero", "a young fox in a green scarf")
    assert "error" not in server.generate_image(vid, "p3", "the same scene again", reference="hero")   # a regeneration
    assert len(paid) == 2
    assert "already has 12" in server.generate_image(vid, "one-more", "a scene", reference="hero")["error"]


def test_treat_image_bakes_a_pencil_plate_and_refuses_another_look(make_video, tmp_path):
    vid = make_video()
    out = server.treat_image(vid, "page-stairs", "pencil")
    assert "error" not in out, out
    assert out["public_path"] == f"/public/{vid}/images/treated/page-stairs.pencil.png"
    assert sr._PENCIL_SRC.match(out["public_path"])                       # the path the validator wants
    assert (tmp_path / "jobs" / vid / "images" / "treated" / "page-stairs.pencil.png").is_file()
    assert (out["width"], out["height"]) == (68, 120)                      # lines up with its still
    assert "expected one of ['pencil']" in server.treat_image(vid, "page-stairs", "print")["error"]
    assert server._image_cap_error(vid, "page-stairs", server.JOBS_DIR / vid / "images") == ""
