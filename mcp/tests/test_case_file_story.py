"""Case File Story (TMDEV-202): the scene-config checks that keep an unattended
agent from shipping a meter that overflows its cell, a card cut before it can
be read, a mistimed punch-in, a still video or a story with no consequence
before its choice; their agreement with the renderer's contract.ts and the
style pack; their place in write_scene_config and the text audit; and what
generate_image does for this style: the reference picture that keeps the lead
the same character, the fixed painting instructions, and the cap on paid stills.

Each refusal guards something the renderer cannot fix. A reference that does
not exist would be found only after the paid call; a still made without the
lead sheet shows a different character; a seventeenth still is money the
style's budget does not allow.

Run from repo root: pytest mcp/tests/
"""
import base64
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import case_file_story as cfs
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_TS = REPO / "renderer/remotion/src/scenes/installed/caseFileStory/contract.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/case_file_story_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-case-file-story/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
PACK = tvs.pack("case_file_story")
EXTRA = PACK["extra"]
VID = "vid_example01"
STILLS = ("the-bag", "counting", "the-bank", "the-counter", "cash-machine", "the-desk", "the-knock", "the-door")
# The example's beats by index.
BAG, COUNTING, COUNT, STREET, COUNTER, ATM, BARS, DESK, TERM, KNOCK, CHOICE = range(11)


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    body = re.sub(r"//.*", "", body)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)", body)}


def _ts_array(name: str) -> tuple[str, ...]:
    src = CONTRACT_TS.read_text()
    return tuple(re.findall(r'"([\w-]+)"', re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.S).group(1)))


def _data(cfg):
    return cfg["scenes"][0]["props"]["caseFile"]


def _check(cfg=None):
    return cfs.check(cfg if cfg is not None else EXAMPLE, 30, WORD_STARTS, EXTRA, VID)


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_limits_timings_geometry_and_camera_match_the_renderer():
    assert _ts_block("LIMITS") == cfs.LIMITS
    assert _ts_block("TIMING") == cfs.TIMING
    assert _ts_block("GEOMETRY") == cfs.GEOMETRY
    assert _ts_block("CAMERA") == cfs.CAMERA


@pytest.mark.parametrize("ts, py", [
    ("ACCENT_NAMES", tuple(cfs.ACCENTS)), ("BEAT_TYPES", cfs.BEAT_TYPES), ("METER_KINDS", cfs.METER_KINDS),
    ("ICONS", cfs.ICONS),
])
def test_the_catalogues_match_the_renderer(ts, py):
    assert _ts_array(ts) == py


def test_the_accent_colours_match_the_renderer():
    body = re.search(r"export const ACCENTS = \{(.*?)\} as const;", CONTRACT_TS.read_text(), re.S).group(1)
    assert dict(re.findall(r'(\w+): "(#[0-9A-F]{6})"', body)) == cfs.ACCENTS


def test_the_pack_lists_exactly_what_the_renderer_draws():
    assert tuple(EXTRA["accents"]) == tuple(cfs.ACCENTS)
    assert tuple(EXTRA["beats"]) == cfs.BEAT_TYPES
    assert tuple(EXTRA["meter_kinds"]) == cfs.METER_KINDS
    assert tuple(EXTRA["icons"]) == cfs.ICONS


def test_the_pack_caps_pictures_at_the_stills_limit_plus_the_lead_sheet():
    assert PACK["routing"]["images"] == cfs.LIMITS["maxImages"] + 1


def test_numbers_cameras_and_cards_are_computed_the_same_way():
    for c in CASES["format_value"]:
        assert cfs.format_value(c["kind"], c["value"]) == c["text"]
    for c in CASES["hud_cells"]:
        assert [list(x) for x in cfs.hud_cells(c["n"])] == [pytest.approx(x) for x in c["cells"]]
    for c in CASES["shot_scale"]:
        assert cfs.shot_scale(c["t"], c["fps"], c["punchAfter"]) == pytest.approx(c["scale"])
    for c in CASES["shot_view"]:
        assert list(cfs.shot_view(c["scale"], c["u"], c["v"])) == pytest.approx(c["view"])
    for c in CASES["term_font_size"]:
        assert cfs.term_font_size(c["term"]) == c["size"]
    for c in CASES["bar_layout"]:
        got = cfs.bar_layout(c["values"], c["threshold"])
        assert [list(b) for b in got["bars"]] == [pytest.approx(b) for b in c["bars"]]
        assert got["lineY"] == pytest.approx(c["lineY"])
    for c in CASES["part_frames"]:
        assert cfs.part_frames(c["beat"]) == c["frames"]
    for c in CASES["quiet_spans"]:
        assert cfs.quiet_spans(c["data"], c["total"]) == c["spans"]


# ── the validator ────────────────────────────────────────────────────────────

def test_the_example_passes():
    assert _check() == []


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(accent="green"), "accent must be one of"),
    (lambda d: d.update(hud=d["hud"][:1]), "hud must list 2 or 3 meters"),
    (lambda d: d["hud"][0].update(id="Cash"), "short lower-case name"),
    (lambda d: d["hud"][1].update(id="cash"), "short lower-case name"),
    (lambda d: d["hud"][0].update(kind="euros"), "kind must be one of"),
    (lambda d: d["hud"][0].update(label="Cash"), "in capitals"),
    (lambda d: d["hud"][0].update(label="CASH ON THE TABLE"), "1 to 12 characters"),
    (lambda d: d["hud"][0].update(value=-1), "whole number from 0"),
    (lambda d: d["hud"][0].update(value=1.5), "whole number from 0"),
    (lambda d: d["hud"][2].update(value=140), "at most 100"),
    (lambda d: d["beats"][BAG].update(start=3), "first beat must start at frame 0"),
    (lambda d: d["beats"][STREET].update(start=d["beats"][STREET]["start"] + 4), "not on a word"),
    (lambda d: d["beats"].insert(0, d["beats"].pop(COUNT) | {"start": 0}), "must increase"),
    (lambda d: d["beats"][BAG].update(type="term"), "opens in its scene"),
    (lambda d: d["beats"].pop(), "ends on the choice"),
    (lambda d: d["beats"].insert(DESK, d["beats"][CHOICE] | {"start": d["beats"][DESK]["start"] - 20}), "ends on the choice"),
    (lambda d: d["beats"].pop(TERM), "consequence comes before the choice"),
    (lambda d: d["beats"][BAG].update(zoom=2), "unknown field(s) ['zoom']"),
    (lambda d: d["beats"][BAG].update(image="/public/vid_other/images/the-bag.png"), "public_path generate_image returned"),
    (lambda d: d["beats"][BAG].update(image="/jobs/vid_example01/images/the-bag.png"), "public_path generate_image returned"),
    (lambda d: d["beats"][BAG].update(image="/public/vid_example01/images/lead.png"), "the lead's reference sheet"),
    (lambda d: d["beats"][BAG].update(focus=[0.5, 1.4]), "focus must be [u, v]"),
    (lambda d: d["beats"][BAG].update(punch={"frame": 5, "at": [0.5, 0.5]}), "at least 12 frames"),
    (lambda d: d["beats"][BAG].update(punch={"frame": d["beats"][BAG]["punch"]["frame"] + 5, "at": [0.5, 0.5]}), "is not on a word"),
    (lambda d: d["beats"][BAG].update(punch={"frame": 60}), "punch must be"),
    (lambda d: d["beats"][DESK].update(hud="no"), "hud must be true or false"),
    (lambda d: d["beats"][DESK]["set"].update(heat=3), "which hud does not list"),
    (lambda d: d["beats"][DESK]["set"].update(suspicion=180), "at most 100"),
    (lambda d: d["beats"][DESK].update(panel="heat"), "name a meter this shot's set changes"),
    (lambda d: d["beats"][DESK].update(hud=False), "panel needs the meter row"),
    (lambda d: d["beats"][COUNT].update(title=""), "title must be 1 to 26"),
    (lambda d: d["beats"][COUNT].update(unit="x" * 27), "unit must be 1 to 26"),
    (lambda d: d["beats"][COUNT].update(icon="diamond"), "icon must be one of"),
    (lambda d: d["beats"][COUNT].update(to=0), "must be more than 0"),
    (lambda d: d["beats"][COUNT].update(result="a result line much too long"), "result must be 1 to 14"),
    (lambda d: d["beats"][COUNT].update(resultFrame=d["beats"][COUNT]["start"] + 20), "after the counter stops"),
    (lambda d: d["beats"][STREET].update(start=d["beats"][COUNT]["resultFrame"] + 12), "frames on screen to be read"),
    (lambda d: d["beats"][BARS].update(kind="dollars"), "kind must be one of"),
    (lambda d: d["beats"][BARS].update(threshold={"value": 0, "label": "LIMIT"}), "threshold must be"),
    (lambda d: d["beats"][BARS].update(bars=d["beats"][BARS]["bars"][:1]), "bars must list 2 to 6"),
    (lambda d: d["beats"][BARS]["bars"][1].update(label="TUESDAY"), "bar 2 must be"),
    (lambda d: d["beats"][BARS]["bars"][1].pop("frame"), "bar 2 must be"),
    (lambda d: d["beats"][BARS]["bars"][1].update(frame=d["beats"][BARS]["bars"][0]["frame"] + 3), "at least 8 frames apart"),
    (lambda d: d["beats"][BARS]["bars"][1].update(frame=d["beats"][BARS]["bars"][1]["frame"] + 5), "is not on a word"),
    (lambda d: d["beats"][BARS].update(payoff="x" * 31), "payoff must be 1 to 30"),
    (lambda d: d["beats"][BARS].update(payoffFrame=d["beats"][BARS]["bars"][0]["frame"]), "after the last bar"),
    (lambda d: d["beats"][TERM].update(term="Structuring"), "term must be in capitals"),
    (lambda d: d["beats"][TERM].update(term="A TERM THAT RUNS FAR TOO LONG"), "term must be 1 to 18"),
    (lambda d: d["beats"][TERM].update(definition="x" * 111), "definition must be 1 to 110"),
    (lambda d: d["beats"][TERM].update(stamp="Federal crime"), "stamp must be 1 to 16"),
    (lambda d: d["beats"][TERM].update(citation="x" * 35), "citation must be 1 to 34"),
    (lambda d: d["beats"][TERM].update(stampFrame=d["beats"][TERM]["start"] + 5), "after the definition"),
    (lambda d: d["beats"][CHOICE].update(options=["HIDE"]), "two different labels"),
    (lambda d: d["beats"][CHOICE].update(options=["HIDE", "HIDE"]), "two different labels"),
    (lambda d: d["beats"][CHOICE].update(options=["Hide", "Hand in"]), "two different labels"),
    (lambda d: d["beats"][CHOICE].update(options=["HIDE", "HAND IT ALL IN"]), "two different labels"),
    (lambda d: d["beats"][CHOICE].update(optionFrames=[9000, 9001]), "optionFrames must be two frames"),
    (lambda d: d["beats"][CHOICE].update(optionFrames=[d["beats"][CHOICE]["optionFrames"][0] + 5,
                                                       d["beats"][CHOICE]["optionFrames"][1]]), "is not on a word"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_shot_that_sits_still_too_long_is_refused_and_a_punch_in_fixes_it():
    cfg = _with(lambda d: d["beats"][BAG].pop("punch"))
    assert any("nothing new appears from frame 0" in p and "Add a punch-in" in p for p in _check(cfg))
    assert _check() == []


def test_a_card_held_long_after_its_last_part_is_refused():
    # without its own frame the stamp lands early, and the card then sits finished for over five seconds
    cfg = _with(lambda d: d["beats"][TERM].pop("stampFrame"))
    problems = _check(cfg)
    assert any("Beat 9 (term): nothing new appears" in p and "Time its parts to later words" in p for p in problems), problems


def test_too_many_stills_are_refused():
    """Sixteen shots with a still each, plus the choice's own: seventeen."""
    cfg = copy.deepcopy(EXAMPLE)
    data = _data(cfg)
    starts, frames = sorted(set(WORD_STARTS)), [0]
    while len(frames) < 16:
        frames.append(next(f for f in starts if f >= frames[-1] + 45))
    shots = [{"type": "shot", "start": f, "image": f"/public/{VID}/images/s{k}.png"} for k, f in enumerate(frames)]
    term = {k: v for k, v in data["beats"][TERM].items() if k not in ("stampFrame", "definitionFrame")}
    term["start"] = next(f for f in starts if f >= frames[-1] + 45)
    choice = {k: v for k, v in data["beats"][CHOICE].items() if k != "optionFrames"}
    assert choice["start"] > term["start"] + 90
    data["beats"] = shots + [term, choice]
    problems = _check(cfg)
    assert any("17 different stills" in p and "at most 16" in p for p in problems), problems
    data["beats"][15]["image"] = data["beats"][0]["image"]     # reuse one: sixteen is fine
    assert not any("different stills" in p for p in _check(cfg))


def test_the_scene_use_rule():
    scene = EXAMPLE["scenes"][0]
    assert cfs.check_scene_use("case_file_story", [scene]) == ""
    assert "exactly one scene" in cfs.check_scene_use("case_file_story", [scene, scene])
    assert "exactly one scene" in cfs.check_scene_use("case_file_story", [{"type": "generated", "src": "intro"}])
    assert "visual_style is case_file_story" in cfs.check_scene_use("stick", [scene])
    assert cfs.check_scene_use("stick", [{"type": "generated", "src": "intro"}]) == ""


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(beats="none"),
    lambda d: d.update(beats=[1, 2]),
    lambda d: d.update(hud={"cash": 1}),
    lambda d: d["beats"][BAG].update(start="0"),
    lambda d: d["beats"][BAG].update(image=7, punch="soon", set=[1]),
    lambda d: d["beats"][COUNT].update(to="many", resultFrame="later", kind=3),
    lambda d: d["beats"][BARS].update(bars=[1, 2], threshold="high"),
    lambda d: d["beats"][BARS].update(bars=[{"label": "A", "value": 1, "frame": "x"}] * 2),
    lambda d: d["beats"][TERM].update(term=None, definitionFrame="x", stampFrame=[1]),
    lambda d: d["beats"][CHOICE].update(options="HIDE", optionFrames="now"),
])
def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash(mutate):
    problems = _check(_with(mutate))
    assert problems and all(isinstance(p, str) for p in problems)


def test_the_text_audit_samples_each_beat_once_its_last_part_is_up():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = cfs.beat_windows(EXAMPLE)
    beats = _data(EXAMPLE)["beats"]
    assert len(passes) == len(windows) == len(beats)
    for p, (settled, end), b in zip(passes, windows, beats):
        last = p["first"] + p["step"] * (p["count"] - 1)
        assert p["first"] == settled and last < end
        if b["type"] != "shot":
            assert settled >= cfs.part_frames(b)[-1]


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "_image_reservations", {})

    def make(video_id=VID, style="case_file_story", images=STILLS):
        from PIL import Image
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'a bag of cash and a reporting limit', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        for name in images:
            Image.new("RGB", (64, 112)).save(d / "images" / f"{name}.png")
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video):
    vid = make_video()
    cfg = copy.deepcopy(EXAMPLE)
    assert "subtitles" not in cfg          # the skill tells the agent to leave them to the style
    result = server.write_scene_config(vid, cfg)
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == PACK["captions"]
    assert written["subtitles"]["look"] == "fill"
    assert written["canvas"] == "dark"


def test_a_broken_config_is_refused_and_nothing_is_written(make_video):
    vid = make_video()
    result = server.write_scene_config(vid, _with(lambda d: d["beats"].pop(TERM)))
    assert result["error"].startswith("The Case File Story video has problems:")
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_scene(make_video):
    vid = make_video(style="motion_graphics")   # a dark style, so the canvas rule does not answer first
    assert "visual_style is case_file_story" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_a_case_file_story_video_cannot_be_built_from_other_scenes(make_video):
    vid = make_video()
    cfg = {"totalFrames": 900, "scenes": [{"type": "generated", "src": "intro", "startFrame": 0, "durationInFrames": 900}]}
    assert "exactly one scene" in server.write_scene_config(vid, cfg)["error"]


@pytest.mark.parametrize("look, ok", [("fill", True), ("selection", True), ("plain", True), ("glow", False)])
def test_the_caption_look_is_checked(look, ok):
    assert (server._validate_subtitles({"look": look}) == "") is ok


# ── generate_image: the reference, the painting instructions and the cap ─────

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


def test_the_house_sheet_ships_with_the_server():
    from PIL import Image
    assert server.CASE_FILE_HOUSE_SHEET.is_file()
    with Image.open(server.CASE_FILE_HOUSE_SHEET) as im:
        assert im.format == "PNG" and im.width > im.height


def test_the_lead_sheet_is_made_from_the_house_sheet_in_the_given_outfit(make_video, paid):
    vid = make_video(images=())
    out = server.generate_image(vid, "lead", "a grey hooded jacket and black jeans", reference="house")
    assert "error" not in out, out
    (call,) = paid
    assert call["url"] == server.OPENAI_IMAGE_EDITS_URL
    name, body, mime = call["files"]["image[]"]
    assert body == server.CASE_FILE_HOUSE_SHEET.read_bytes() and mime == "image/png"
    assert call["data"]["size"] == "1920x1088" and "background" not in call["data"]
    prompt = call["data"]["prompt"]
    assert prompt.startswith(EXTRA["sheet_lead"]) and prompt.endswith(EXTRA["sheet_style"])
    assert "a grey hooded jacket and black jeans" in prompt
    assert out["aspect_ratio"] == "16:9" and out["reference"] == "house"
    assert (server.JOBS_DIR / vid / "images" / "lead.png").is_file()


def test_a_still_with_the_lead_is_painted_from_the_videos_own_sheet(make_video, paid):
    vid = make_video(images=("lead",))
    out = server.generate_image(vid, "the-desk", "Night. You sit at a desk, typing.", reference="lead")
    assert "error" not in out, out
    (call,) = paid
    assert call["url"] == server.OPENAI_IMAGE_EDITS_URL
    assert call["files"]["image[]"][1] == (server.JOBS_DIR / vid / "images" / "lead.png").read_bytes()
    assert call["data"]["size"] == "1088x1920"
    assert call["data"]["prompt"] == f"{EXTRA['still_lead']} Night. You sit at a desk, typing. {EXTRA['still_style']}"


def test_a_still_without_the_lead_gets_the_painting_instructions_and_no_reference(make_video, paid):
    vid = make_video(images=())
    out = server.generate_image(vid, "the-bag", "A duffel bag of banknotes on a table. No people.")
    assert "error" not in out, out
    (call,) = paid
    assert call["url"] == server.OPENAI_IMAGES_URL and call["files"] is None
    assert call["json"]["prompt"] == f"A duffel bag of banknotes on a table. No people. {EXTRA['still_style']}"


@pytest.mark.parametrize("name, reference, images, fragment", [
    ("lead", "", (), "is made from the house lead"),
    ("lead", "the-desk", ("the-desk",), "is made from the house lead"),
    ("the-desk", "house", (), "only makes the lead sheet"),
    ("the-desk", "lead", (), "Make the lead sheet first"),
    ("the-desk", "the-bag", (), "is not an image of this video yet"),
    ("the-desk", "../lead", ("lead",), "reference"),
])
def test_a_wrong_reference_is_refused_before_the_paid_call(make_video, paid, name, reference, images, fragment):
    vid = make_video(images=images)
    out = server.generate_image(vid, name, "a scene", reference=reference)
    assert fragment in out["error"], out
    assert paid == []


def test_a_reference_is_refused_for_every_other_style_and_their_prompts_are_untouched(make_video, paid):
    vid = make_video(style="illustrated", images=("lead",))
    assert "case_file_story video only" in server.generate_image(vid, "a", "a scene", reference="lead")["error"]
    assert paid == []
    out = server.generate_image(vid, "a", "a scene")
    assert "error" not in out, out
    assert paid[0]["json"]["prompt"] == "a scene" and paid[0]["url"] == server.OPENAI_IMAGES_URL


def test_a_picture_past_the_cap_is_refused_before_the_paid_call(make_video, paid):
    vid = make_video(images=["lead"] + [f"s{k}" for k in range(16)])
    out = server.generate_image(vid, "one-more", "a scene", reference="lead")
    assert "the most a video may use (17)" in out["error"] and "lead sheet" in out["error"]
    assert paid == []
    assert "error" not in server.generate_image(vid, "s3", "the same scene again", reference="lead")   # a regeneration
    assert len(paid) == 1


def test_the_under_the_hood_cap_keeps_its_own_number_and_words(make_video):
    vid = make_video("vid_uth", style="under_the_hood", images=[f"p{k}" for k in range(12)])
    err = server._image_cap_error(vid, "p12", server.JOBS_DIR / vid / "images")
    assert "Under the Hood" in err and "(12)" in err
