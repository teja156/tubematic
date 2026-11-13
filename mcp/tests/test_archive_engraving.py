"""Archive and Engraving (TMDEV-230): the scene-config checks that keep an
unattended agent from shipping an untreated or foreign picture, a picture or
a face for a real person, a title that runs off the page, an event off the
narration, a point that is off the plate, or a still page; their agreement
with the renderer's contract.ts and the style pack; their place in
write_scene_config, the text audit and the picture checks; and the picture
cap and the engraving treatment that guard the paid image calls.

Each refusal guards something the renderer cannot fix: it draws whatever it is
given, so an untreated colour still or a strike on a word the title lacks
would ship as it is. The footnotes "Illustration" and "Recreation" have no
field at all, so a config that tries to name one is refused.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import archive_engraving as ae
import picture_checks
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
KIT = REPO / "renderer/remotion/src/scenes/installed/archiveEngraving"
CONTRACT_TS = KIT / "contract.ts"
STAGE_TS = KIT / "stage.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/archive_engraving_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-archive-engraving/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
PACK = tvs.pack("archive_engraving")
EXTRA = PACK["extra"]
VID = "vid_example01"
PLATE, DOC, PEOPLE, PAYOFF = 0, 1, 2, 3


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    body = re.sub(r"//.*", "", body)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)(?=\s*(?:[,}\n]|$))", body)}


def _ts_array(name: str, src: str = None) -> tuple:
    src = src or CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \[(.*?)\] as const;", src, re.S).group(1)
    return tuple(re.findall(r'"([\w-]+)"', body)) or tuple(int(v) for v in re.findall(r"\d+", body))


def _data(cfg):
    return cfg["scenes"][0]["props"]["archive"]


def _check(cfg=None, quiet=(), video_id=VID, silences=()):
    return ae.check(cfg or EXAMPLE, 30, WORD_STARTS, EXTRA, video_id, quiet=quiet, silences=silences)


def _stalls(errors):
    """Every "nothing new happens from frame A to C" refusal as (A, C)."""
    return [(int(a), int(c)) for e in errors if "nothing new happens" in e
            for a, c in [re.search(r"from frame (\d+) to (\d+)", e).groups()]]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _beat(d, i):
    return d["beats"][i]


# ── agreement with the renderer and the pack ────────────────────────────────

def test_the_constants_equal_the_renderers_contract():
    assert _ts_block("ZONES") == ae.ZONES
    assert _ts_block("LIMITS") == ae.LIMITS
    assert _ts_block("TIMING") == ae.TIMING
    for name, ours in (("CARD_KINDS", ae.CARD_KINDS), ("EVENTS", ae.EVENTS), ("EMBLEMS", ae.EMBLEMS),
                       ("TITLE_SIZES", ae.TITLE_SIZES)):
        assert _ts_array(name) == ours, name
    assert _ts_array("RULER_STEPS", STAGE_TS.read_text()) == ae.RULER_STEPS
    assert f"TITLE_CHAR_W = {ae.TITLE_CHAR_W};" in CONTRACT_TS.read_text()
    footnotes = dict(re.findall(r'(\w+): "(\w+)"', re.search(r"export const FOOTNOTES = \{(.*?)\}", CONTRACT_TS.read_text()).group(1)))
    assert footnotes == ae.FOOTNOTES


def test_the_pack_lists_what_the_contract_holds():
    assert EXTRA["card_kinds"] == list(ae.CARD_KINDS)
    assert EXTRA["events"] == list(ae.EVENTS) and EXTRA["emblems"] == list(ae.EMBLEMS)
    assert EXTRA["treatment"] == ae.TREATMENT and PACK["pictures"]["treatments"] == [ae.TREATMENT]
    assert EXTRA["footnotes"] == ae.FOOTNOTES
    assert PACK["routing"]["images"] == ae.LIMITS["maxImages"]


def test_the_shared_cases_agree():
    for c in CASES["title_layout"]:
        assert ae.title_layout(c["text"]) == (c["size"], c["lines"])
    for c in CASES["push_scale"]:
        assert ae.push_scale(c["frame"], c["start"], c["end"]) == pytest.approx(c["scale"])
    for c in CASES["plate_view"]:
        assert list(ae.plate_view(c["scale"], c["focus"])) == pytest.approx(c["view"])
    for c in CASES["to_window"]:
        assert list(ae.to_window(ae.plate_view(c["scale"], c["focus"]), c["point"])) == pytest.approx(c["xy"])
    for c in CASES["ruler_scale"]:
        got = ae.ruler_scale(c["years"])
        assert (list(got) if got else None) == c["scale"]
    for c in CASES["ruler_scale_ticks"]:
        assert ae.ruler_scale(c["years"], c["max"]) is None
    for c in CASES["clean_word"]:
        assert ae.clean_word(c["word"]) == c["clean"]


def test_the_captions_are_the_fill_look_on_a_chip_the_server_accepts():
    caps = PACK["captions"]
    assert caps["look"] == "fill" and caps["background"] == "chip" and caps["position"] == 0.73
    assert server._validate_subtitles(caps) == ""


# ── the checks ───────────────────────────────────────────────────────────────

def test_the_skills_worked_example_passes():
    assert _check() == []


def test_the_scene_is_this_styles_alone():
    assert "used only when" in ae.check_scene_use("stick", EXAMPLE["scenes"])
    assert ae.check_scene_use("stick", [{"src": "Other"}]) == ""
    two = EXAMPLE["scenes"] + [{"type": "generated", "src": "x"}]
    assert "one scene" in ae.check_scene_use("archive_engraving", two)


def _plate_image(d, value):
    _beat(d, PLATE)["card"]["image"] = value


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(header="x" * 35), "header must be"),
    (lambda d: _beat(d, 1).update(start=_beat(d, 1)["start"] + 5), "not on a word"),
    (lambda d: _beat(d, PLATE)["title"].update(red="moth"), "title.red must be one word of the title"),
    (lambda d: _beat(d, PLATE)["title"].update(text="Electromagnetism superconductivity thermodynamic", red="thermodynamic"),
     "does not fit two lines"),
    (lambda d: _beat(d, PLATE).update(date="x" * 25), "date must be"),
    (lambda d: _beat(d, PLATE)["card"].update(kind="photo"), "kind is one of"),
    (lambda d: _plate_image(d, f"/public/{VID}/images/eng-machine.png"), "an engraving of this video"),
    (lambda d: _plate_image(d, f"/public/{VID}/images/treated/eng-machine.print.png"), "an engraving of this video"),
    (lambda d: _plate_image(d, "/public/vid_other/images/treated/eng-machine.engraving.png"), "an engraving of this video"),
    (lambda d: _plate_image(d, f"/jobs/{VID}/images/treated/eng-machine.engraving.png"), "an engraving of this video"),
    (lambda d: _beat(d, PLATE)["card"].update(focus=[1.2, 0.5]), "focus must be [u, v]"),
    (lambda d: _beat(d, PLATE)["card"].update(name="x" * 29), "name must be"),
    (lambda d: _beat(d, PLATE)["events"][2].update(point=[0.16, 0.05]), "outside the part of the still"),
    (lambda d: _beat(d, PLATE)["events"].append({"at": _beat(d, PLATE)["events"][2]["at"], "do": "route"}),
     "this beat's card is not a chart"),
    (lambda d: _beat(d, DOC)["events"][0].update(word="simile"), "word must be one word of this beat's title"),
    (lambda d: _beat(d, DOC)["events"][0].update(**{"with": "x" * 29}), "with must be"),
    (lambda d: _beat(d, DOC)["events"][1].update(text="Logged"), "capital letters"),
    (lambda d: _beat(d, DOC)["events"].append({**_beat(d, DOC)["events"][1]}), "at most one stamp"),
    (lambda d: _beat(d, DOC)["events"].append({"at": _beat(d, DOC)["events"][0]["at"], "do": "magnify",
                                                "point": [0.5, 0.5]}), "magnify needs a plate or a chart"),
    (lambda d: _beat(d, DOC)["card"]["lines"][2].update(at=_beat(d, DOC)["card"]["lines"][1]["at"]),
     "lines write on in order"),
    (lambda d: _beat(d, DOC)["card"]["lines"].extend([{"text": "x", "at": 556}] * 2), "1 to 6 lines"),
    (lambda d: _beat(d, DOC)["card"]["lines"][1].update(text="x" * 41), "text must be 1 to 40"),
    (lambda d: _beat(d, PEOPLE)["card"]["people"][0].update(emblem="sword"), "emblem must be one of"),
    (lambda d: _beat(d, PEOPLE)["card"]["people"][0].update(initials="TE"), "one of the two"),
    (lambda d: _beat(d, PEOPLE)["card"]["people"][1].update(initials="gh"), "capital letters"),
    (lambda d: _beat(d, PEOPLE)["card"]["people"].reverse(), "people arrive in order"),
    (lambda d: _beat(d, PEOPLE)["card"]["people"][0].update(at=_beat(d, PEOPLE)["card"]["people"][1]["at"] - 30),
     "leaves the card empty"),
    (lambda d: _beat(d, PEOPLE)["card"].update(people=_beat(d, PEOPLE)["card"]["people"][:1]), "2 to 4 people"),
    (lambda d: _beat(d, PEOPLE)["events"][2].update(to=2200), "years from 0 to 2100"),
    (lambda d: _beat(d, PEOPLE)["events"][0].update(do="explode"), "do must be one of"),
    (lambda d: _beat(d, PAYOFF)["events"][1].update(at=_beat(d, PAYOFF)["events"][1]["at"] + 5), "not on a word"),
    (lambda d: _beat(d, PAYOFF).update(colour="red"), "unknown field"),
])
def test_a_bad_config_is_refused_with_its_cause(mutate, fragment):
    errors = _check(_with(mutate))
    assert any(fragment in e for e in errors), errors


@pytest.mark.parametrize("field", ["image", "face", "photo", "portrait"])
def test_a_person_with_a_picture_or_a_face_is_refused(field):
    def person_card(d):
        _beat(d, PEOPLE)["card"] = {"kind": "person", "name": "Grace Hopper", "dates": "1906-1992",
                                    "role": "computer scientist", "initials": "GH",
                                    field: f"/public/{VID}/images/treated/hopper.engraving.png"}
    errors = _check(_with(person_card))
    assert any("has no picture or face" in e for e in errors), errors

    def in_a_row(d):
        _beat(d, PEOPLE)["card"]["people"][1][field] = "hopper"
    errors = _check(_with(in_a_row))
    assert any("has no picture or face" in e for e in errors), errors


def test_a_person_card_with_only_its_name_fields_passes():
    def person_card(d):
        b = _beat(d, PEOPLE)
        grace = b["card"]["people"][1]["at"]
        b["card"] = {"kind": "person", "name": "Grace Hopper", "dates": "1906-1992", "role": "computer scientist",
                     "emblem": "gear"}
        b["events"].append({"at": grace, "do": "stamp", "text": "MARK II"})   # her arrival was this beat's change
    assert _check(_with(person_card)) == []


@pytest.mark.parametrize("card, field", [(PLATE, "footnote"), (DOC, "recreation"), (PLATE, "showIllustration"),
                                         (DOC, "label")])
def test_no_field_hides_a_footnote(card, field):
    errors = _check(_with(lambda d: _beat(d, card)["card"].update({field: False})))
    assert any("cannot be changed or hidden" in e for e in errors), errors


def test_a_chart_needs_its_route_on_the_still_and_one_route_event():
    def chart(d, route=None, events=True):
        b = _beat(d, PAYOFF)
        b["card"] = {"kind": "chart", "image": f"/public/{VID}/images/treated/eng-chart.engraving.png",
                     "focus": [0.5, 0.42], "name": "A sea chart",
                     "route": route or [[0.3, 0.52], [0.4, 0.46], [0.47, 0.37], [0.62, 0.33]]}
        magnify = next(e for e in b["events"] if e["do"] == "magnify")
        b["events"] = [e for e in b["events"] if e["do"] != "magnify"]
        if events:
            b["events"].append({"at": magnify["at"], "do": "route"})
    assert _check(_with(chart)) == []
    assert any("one route event" in e for e in _check(_with(lambda d: chart(d, events=False))))
    assert any("route point is outside" in e for e in _check(_with(lambda d: chart(d, route=[[0.3, 0.5], [0.4, 0.95]]))))
    assert any("route must list" in e for e in _check(_with(lambda d: chart(d, route=[[0.3, 0.5]]))))


def test_more_than_ten_engravings_are_refused():
    def many(d):
        starts = [0]
        for w in WORD_STARTS:
            if w - starts[-1] >= 50 and len(starts) < 11:
                starts.append(w)
        d["beats"] = []
        for k, start in enumerate(starts):
            b = copy.deepcopy(EXAMPLE["scenes"][0]["props"]["archive"]["beats"][PLATE])
            b.update(start=start, events=[])
            b["card"]["image"] = f"/public/{VID}/images/treated/s{k}.engraving.png"
            d["beats"].append(b)
    errors = _check(_with(many))
    assert any("at most 10" in e for e in errors), errors


def test_a_still_page_is_refused():
    def still(d):
        _beat(d, PLATE)["events"] = [_beat(d, PLATE)["events"][0]]
    errors = _check(_with(still))
    assert any("nothing new happens" in e for e in errors), errors


def test_a_silent_pause_is_not_a_stall():
    cfg = _with(lambda d: _beat(d, PLATE).update(events=[]))
    stalls = _stalls(_check(cfg))
    assert stalls
    assert _check(cfg, silences=[(a + 5, c - 5) for a, c in stalls]) == []
    a, c = stalls[0]
    assert any("nothing new happens" in e for e in _check(cfg, silences=[(a + 5, a + 20)]))   # a short gap is no cover


def test_nothing_starts_inside_an_insert_window_and_a_window_is_not_still():
    b1 = _data(EXAMPLE)["beats"][1]["start"]
    assert any("inside an insert" in e for e in _check(quiet=[(b1 - 30, b1 + 30)]))
    # a window over the quiet stretch of beat 1 (between the underline and the magnify): nothing starts in
    # it, and with the plate's middle event removed the stretch is covered by the window
    ev = _data(EXAMPLE)["beats"][0]["events"]
    cfg = _with(lambda d: _beat(d, PLATE).update(events=[ev[0], ev[2]]))
    assert any("nothing new happens" in e for e in _check(cfg))
    assert _check(cfg, quiet=[(ev[0]["at"] + 4, ev[2]["at"] - 4)]) == []


# ── the text audit and the picture checks ────────────────────────────────────

def test_the_text_audit_samples_each_beat_after_its_last_event():
    windows = ae.beat_windows(EXAMPLE)
    beats = _data(EXAMPLE)["beats"]
    assert len(windows) == len(beats)
    for (first, end), b in zip(windows, beats):
        assert b["start"] <= first < end
    plan = text_audit.plan_passes(EXAMPLE)
    assert plan["passes"] if isinstance(plan, dict) else plan


def test_the_picture_checks_read_the_style():
    assert picture_checks.style_of(EXAMPLE) == "archive_engraving"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    late = _with(lambda d: (_beat(d, PEOPLE).update(start=0), d["beats"].insert(0, d["beats"].pop(PEOPLE))))
    assert picture_checks.first_frame_warnings(late)
    frames = picture_checks.change_frames("archive_engraving", EXAMPLE)
    beats = _data(EXAMPLE)["beats"]
    assert 0 in frames and beats[1]["start"] in frames
    assert beats[PEOPLE]["card"]["people"][1]["at"] in frames            # a person arriving counts
    assert beats[DOC]["card"]["lines"][3]["at"] in frames                # a line writing on counts
    assert beats[PEOPLE]["events"][0]["at"] not in frames                # an underline alone does not


# ── write_scene_config, the picture cap and treat_image ──────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "_image_reservations", {})

    def make(style="archive_engraving", images=("eng-machine",), video_id=VID):
        from PIL import Image
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                        "VALUES (?, NULL, 'the first computer bug', 'VOICE_READY', ?, ?, ?)",
                        (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        for name in images:
            Image.new("RGB", (64, 112), (120, 110, 100)).save(d / "images" / f"{name}.png")
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video, tmp_path):
    vid = make_video()
    cfg = copy.deepcopy(EXAMPLE)
    assert "subtitles" not in cfg
    out = server.write_scene_config(vid, cfg)
    assert "error" not in out, out
    written = json.loads((tmp_path / "jobs" / vid / "scene-config.json").read_text())
    assert written["subtitles"]["look"] == "fill" and written["subtitles"]["background"] == "chip"
    assert written["subtitles"]["accent"] == "#A83A3A"


def test_a_broken_config_writes_nothing(make_video, tmp_path):
    vid = make_video()
    bad = _with(lambda d: _plate_image(d, f"/public/{VID}/images/eng-machine.png"))
    assert "Archive and Engraving video has problems" in server.write_scene_config(vid, bad)["error"]
    assert not (tmp_path / "jobs" / vid / "scene-config.json").exists()


def test_the_scene_on_another_style_is_refused(make_video):
    vid = make_video(style="stick")
    assert "used only when" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_an_eleventh_new_engraving_is_refused_before_the_paid_call(make_video):
    vid = make_video(images=[f"s{k}" for k in range(10)])
    images = server.JOBS_DIR / vid / "images"
    err = server._image_cap_error(vid, "one-more", images)
    assert "already has 10 engravings" in err and "(10)" in err
    assert server._image_cap_error(vid, "s3", images) == ""          # regenerating a still stays allowed


def test_an_eleventh_still_never_reaches_openai(make_video, monkeypatch):
    vid = make_video(images=[f"s{k}" for k in range(10)])
    monkeypatch.setattr(server, "_openai_key", lambda: "sk-test")
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError))
    out = server.generate_image(vid, "one-more", "a sea chart")
    assert "already has 10 engravings" in out["error"] and calls == []


def test_the_engraving_prompt_and_shape_are_added_to_every_still():
    plan = server._image_plan("archive_engraving", VID, "eng-chart", "An antique sea chart", "1:1", "")
    assert plan["aspect_ratio"] == "9:16" and plan["ref_path"] is None
    assert plan["prompt"].startswith("An antique sea chart. Antique copperplate engraving")
    assert "no detailed face" in plan["prompt"]
    assert "reference is only for" in server._image_plan("archive_engraving", VID, "x", "y", "9:16", "lead")["error"]


def test_treat_image_bakes_an_engraving_and_refuses_another_look(make_video, tmp_path):
    vid = make_video()
    out = server.treat_image(vid, "eng-machine", "engraving")
    assert "error" not in out, out
    assert out["public_path"] == f"/public/{vid}/images/treated/eng-machine.engraving.png"
    assert ae._IMAGE_SRC.match(out["public_path"])                     # the path the validator wants
    assert (tmp_path / "jobs" / vid / "images" / "treated" / "eng-machine.engraving.png").is_file()
    assert "expected one of ['engraving']" in server.treat_image(vid, "eng-machine", "print")["error"]
    # the treated copy is no new still: a video at its cap may still bake the engravings it has
    assert server._image_cap_error(vid, "eng-machine", server.JOBS_DIR / vid / "images") == ""
