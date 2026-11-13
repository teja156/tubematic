"""Editorial Collage (TMDEV-229): the scene-config checks that keep an
unattended agent from shipping an untreated or foreign picture, a face for a
real person, a headline that runs off its paper, an event off the narration,
a glide or an event inside an insert, or a still desk; their agreement with
the renderer's contract.ts and the style pack; their place in
write_scene_config, the text audit and the picture checks; and the picture
cap and the print and sticker treatments that guard the paid image calls.

Each refusal guards something the renderer cannot fix: it draws whatever it is
given, so an untreated colour still or an underline on a word the headline
lacks would ship as it is. The notes "Illustration" and "Recreation" have no
field at all, so a config that tries to name one is refused.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import editorial_collage as ec
import picture_checks
import server
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
KIT = REPO / "renderer/remotion/src/scenes/installed/editorialCollage"
CONTRACT_TS = KIT / "contract.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/editorial_collage_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-editorial-collage/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
PACK = tvs.pack("editorial_collage")
EXTRA = PACK["extra"]
VID = "vid_example01"
OPEN, FIX, DARK, HOURS, THIRD, PAYOFF = range(6)


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    body = re.sub(r"//.*", "", body)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"(\w+):\s*([\d.]+)(?=\s*(?:[,}\n]|$))", body)}


def _ts_array(name: str) -> tuple:
    body = re.search(rf"export const {name} = \[(.*?)\] as const;", CONTRACT_TS.read_text(), re.S).group(1)
    return tuple(re.findall(r'"([\w-]+)"', body))


def _ts_headline() -> dict:
    body = re.search(r"export const HEADLINE = \{(.*?)\n\} as const;", CONTRACT_TS.read_text(), re.S).group(1)
    out = {}
    for kind, inner in re.findall(r"(\w+): \{(.*?)\}", body):
        spec = dict(re.findall(r"(\w+): ([\d.]+)", inner.split("]")[1]))
        out[kind] = {"sizes": tuple(int(v) for v in re.findall(r"\d+", inner.split("]")[0])),
                     **{k: float(v) if "." in v else int(v) for k, v in spec.items()}}
    return out


def _data(cfg):
    return cfg["scenes"][0]["props"]["collage"]


def _check(cfg=None, quiet=(), video_id=VID):
    return ec.check(cfg or EXAMPLE, 30, WORD_STARTS, EXTRA, video_id, quiet=quiet)


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _st(d, i):
    return d["stations"][i]


def _word(word, k=0):
    return [w["startFrame"] for w in EXAMPLE_TIMELINE["words"] if w["word"].strip(".,'?").lower() == word][k]


# ── agreement with the renderer and the pack ────────────────────────────────

def test_the_constants_equal_the_renderers_contract():
    assert _ts_block("ZONES") == ec.ZONES
    assert _ts_block("DESK") == ec.DESK
    assert _ts_block("LIMITS") == ec.LIMITS
    assert _ts_block("TIMING") == ec.TIMING
    assert _ts_headline() == ec.HEADLINE
    for name, ours in (("HEADLINE_KINDS", ec.HEADLINE_KINDS), ("HERO_KINDS", ec.HERO_KINDS), ("EVENTS", ec.EVENTS),
                       ("ARROW_SIDES", ec.ARROW_SIDES)):
        assert _ts_array(name) == ours, name
    assert f"KICKER_H = {ec.KICKER_H};" in CONTRACT_TS.read_text()
    notes = dict(re.findall(r'(\w+): "(\w+)"', re.search(r"export const NOTES = \{(.*?)\}", CONTRACT_TS.read_text()).group(1)))
    assert notes == ec.NOTES


def test_the_pack_lists_what_the_contract_holds():
    assert EXTRA["headline_kinds"] == list(ec.HEADLINE_KINDS) and EXTRA["hero_kinds"] == list(ec.HERO_KINDS)
    assert EXTRA["events"] == list(ec.EVENTS) and EXTRA["notes"] == ec.NOTES
    assert EXTRA["treatments"] == list(ec.TREATMENTS) == PACK["pictures"]["treatments"]
    assert PACK["routing"]["images"] == ec.LIMITS["maxImages"]
    assert "still_aspect" not in PACK["pictures"]


def test_the_shared_cases_agree():
    for c in CASES["stepped"]:
        assert ec.stepped(c["frame"]) == pytest.approx(c["stepped"])
    for c in CASES["station_center"]:
        assert list(ec.station_center(c["i"])) == c["xy"]
    for c in CASES["camera_at"]:
        assert list(ec.camera_at(c["starts"], c["frame"])) == pytest.approx(c["xy"])
    for c in CASES["headline_layout"]:
        assert ec.headline_layout(c["text"], c["kind"], c["kicker"]) == (c["size"], c["lines"], c["fits"])
    for c in CASES["typed_chars"]:
        assert ec.typed_chars(c["text"], c["at"], c["frame"]) == c["n"]
    for c in CASES["type_frames"]:
        assert ec.type_frames(c["text"]) == c["frames"]
    for c in CASES["figure_text"]:
        assert ec.figure_text(c["value"], c["prefix"], c["suffix"], c["k"]) == c["text"]
    for c in CASES["clean_word"]:
        assert ec.clean_word(c["word"]) == c["clean"]


def test_the_camera_glides_between_stations_in_a_zig_zag_and_rests_on_each():
    starts = [0, 100, 250]
    assert ec.camera_at(starts, 99) == (0.0, 0.0)
    assert ec.camera_at(starts, 100 + ec.TIMING["glide"]) == pytest.approx(ec.station_center(1))
    assert ec.camera_at(starts, 200) == pytest.approx(ec.station_center(1))
    left, right, lower = ec.station_center(0), ec.station_center(1), ec.station_center(2)
    assert left[0] == lower[0] != right[0] and left[1] < right[1] < lower[1]


def test_the_captions_are_the_highlight_look_the_server_accepts():
    caps = PACK["captions"]
    assert caps["look"] == "highlight" and caps["position"] == 0.73 and caps["maxWords"] == 4
    assert server._validate_subtitles(caps) == ""


# ── the checks ───────────────────────────────────────────────────────────────

def test_the_skills_worked_example_passes():
    assert _check() == []


def test_the_worked_example_shows_every_hero_kind_but_the_stack_and_every_headline_kind():
    stations = _data(EXAMPLE)["stations"]
    assert {s["headline"]["kind"] for s in stations} == set(ec.HEADLINE_KINDS)
    assert {s["hero"]["kind"] for s in stations if "hero" in s} == {"print", "index", "figure"}
    assert {e["do"] for s in stations for e in s.get("events", [])} == set(ec.EVENTS)


def test_the_scene_is_this_styles_alone():
    assert "used only when" in ec.check_scene_use("stick", EXAMPLE["scenes"])
    assert ec.check_scene_use("stick", [{"src": "Other"}]) == ""
    two = EXAMPLE["scenes"] + [{"type": "generated", "src": "x"}]
    assert "one scene" in ec.check_scene_use("editorial_collage", two)


def _hero(d, i, **fields):
    _st(d, i)["hero"].update(fields)


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: _st(d, FIX).update(start=_st(d, FIX)["start"] + 4), "not on a word"),
    (lambda d: _st(d, OPEN)["headline"].update(text="x" * 61), "1 to 60 characters"),
    (lambda d: _st(d, OPEN)["headline"].update(text="Antidisestablishmentarianism beats the web"),
     "does not fit its clipping"),
    (lambda d: _st(d, FIX)["headline"].update(text="Eleven words never fit a label bar whatever the size it is"),
     "does not fit its label"),
    (lambda d: _st(d, OPEN)["headline"].update(kind="banner"), "headline.kind must be one of"),
    (lambda d: _st(d, OPEN)["headline"].update(kicker="x" * 29), "kicker must be 1 to 28"),
    (lambda d: _st(d, OPEN).pop("hero"), "give it a hero"),
    (lambda d: _hero(d, OPEN, kind="photo"), "kind is one of"),
    (lambda d: _hero(d, OPEN, caption="x" * 41), "caption must be 1 to 40"),
    (lambda d: _hero(d, FIX, lines=_st(d, FIX)["hero"]["lines"] + [{"text": "x", "at": _word("number")}] * 2),
     "1 to 4 lines"),
    (lambda d: _st(d, FIX)["hero"]["lines"][1].update(text="x" * 35), "text must be 1 to 34"),
    (lambda d: _st(d, FIX)["hero"]["lines"][2].update(at=_st(d, FIX)["hero"]["lines"][1]["at"]), "type on in order"),
    (lambda d: _st(d, FIX)["hero"]["lines"][2].update(at=_word("wrong")), "still typing when the station ends"),
    (lambda d: _hero(d, FIX, recreation="yes"), "recreation must be true"),
    (lambda d: _hero(d, HOURS, value=-1), "value must be a number from 0"),
    (lambda d: _hero(d, HOURS, value=4.125), "at most 2 decimals"),
    (lambda d: _hero(d, HOURS, value=1e10), "value must be a number from 0"),
    (lambda d: _hero(d, HOURS, prefix="USD$"), "prefix must be 1 to 3"),
    (lambda d: _hero(d, HOURS, suffix="x" * 11), "suffix must be 1 to 10"),
    (lambda d: _hero(d, HOURS, label="x" * 25), "label must be 1 to 24"),
    (lambda d: _hero(d, HOURS, countAt=_word("four") + 5), "countAt is frame"),
    (lambda d: _st(d, OPEN)["events"][0].update(word="broke"), "one word of this station's headline"),
    (lambda d: _st(d, OPEN)["events"].append({**_st(d, OPEN)["events"][0]}), "already has a highlight"),
    (lambda d: _st(d, FIX)["events"].append({"at": _word("command"), "do": "highlight", "word": "fix"}),
     "on a label the white letters"),
    (lambda d: _st(d, DARK)["events"].append({"at": _word("whole"), "do": "circle"}), "this station has none"),
    (lambda d: _st(d, HOURS)["events"][0].update(text="Offline"), "capital letters"),
    (lambda d: _st(d, HOURS)["events"][0].update(text="X" * 13), "capital letters"),
    (lambda d: _st(d, HOURS)["events"].append({**_st(d, HOURS)["events"][0]}), "at most one stamp"),
    (lambda d: _st(d, THIRD)["events"][1].update(**{"from": "top"}), "from must be \"left\" or \"right\""),
    (lambda d: _st(d, OPEN)["events"].append({"at": _word("internet"), "do": "circle"}), "at most one circle"),
    (lambda d: _st(d, DARK)["events"].append({"at": _word("whole"), "do": "strike", "word": "far"}), "at most one strike"),
    (lambda d: _st(d, OPEN)["events"][0].update(do="explode"), "do must be one of"),
    (lambda d: _st(d, PAYOFF)["events"][2].update(at=_st(d, PAYOFF)["events"][2]["at"] + 5), "not on a word"),
    (lambda d: _st(d, OPEN)["events"][1].update(at=_st(d, FIX)["start"] - 2), "8 frames before the station ends"),
    (lambda d: _st(d, PAYOFF).update(colour="red"), "unknown field"),
    (lambda d: _st(d, OPEN).update(x=200), "takes no position"),
    (lambda d: _hero(d, OPEN, tilt=3), "takes no position"),
])
def test_a_bad_config_is_refused_with_its_cause(mutate, fragment):
    errors = _check(_with(mutate))
    assert any(fragment in e for e in errors), errors


@pytest.mark.parametrize("value", [
    "/public/vid_example01/images/print-aisle.png",                            # untreated
    "/public/vid_example01/images/treated/print-aisle.sticker.png",            # a sticker where a print belongs
    "/public/vid_example01/images/treated/print-aisle.engraving.png",          # another style's look
    "/public/vid_other/images/treated/print-aisle.print.png",                  # another video's still
    "/jobs/vid_example01/images/treated/print-aisle.print.png",                # not a public path
])
def test_an_untreated_or_wrong_treatment_print_is_refused(value):
    errors = _check(_with(lambda d: _hero(d, OPEN, image=value)))
    assert any("must be a treated still of this video" in e and "print" in e for e in errors), errors


def test_a_sticker_needs_the_sticker_treatment_and_a_stack_takes_either():
    sticker = f"/public/{VID}/images/treated/phone.sticker.png"
    print_ = f"/public/{VID}/images/treated/print-aisle.print.png"
    assert _check(_with(lambda d: _st(d, OPEN).update(hero={"kind": "sticker", "image": sticker, "label": "Desk phone"}))) == []
    errors = _check(_with(lambda d: _st(d, OPEN).update(hero={"kind": "sticker", "image": print_})))
    assert any("treat_image(video_id, name, \"sticker\")" in e for e in errors), errors
    stack = {"kind": "stack", "items": [{"image": sticker, "caption": "The phone"}, {"image": print_}]}
    assert _check(_with(lambda d: _st(d, OPEN).update(hero=stack))) == []
    errors = _check(_with(lambda d: _st(d, OPEN).update(hero={"kind": "stack", "items": [{"image": sticker}]})))
    assert any("2 to 3 prints or stickers" in e for e in errors), errors
    bad = {"kind": "stack", "items": [{"image": sticker}, {"image": "/public/x/images/a.png"}]}
    assert any("item 2: image" in e for e in _check(_with(lambda d: _st(d, OPEN).update(hero=bad))))


@pytest.mark.parametrize("field", ["face", "portrait", "person", "likeness"])
def test_a_face_or_a_portrait_field_is_refused_with_its_reason(field):
    errors = _check(_with(lambda d: _hero(d, OPEN, **{field: "the engineer"})))
    assert any("never shown with a face" in e for e in errors), errors
    errors = _check(_with(lambda d: _st(d, OPEN)["headline"].update({field: True})))
    assert any("never shown with a face" in e for e in errors), errors


@pytest.mark.parametrize("station, field", [(OPEN, "note"), (OPEN, "illustration"), (FIX, "footnote"),
                                            (OPEN, "showNote")])
def test_no_field_hides_a_note(station, field):
    errors = _check(_with(lambda d: _hero(d, station, **{field: False})))
    assert any("cannot be changed or hidden" in e for e in errors), errors


def test_a_print_always_shows_illustration_and_a_recreation_card_recreation():
    paint = (KIT / "paint.ts").read_text()
    assert "note(g, NOTES.print," in paint and "g.fillText(NOTES.recreation," in paint
    # the print's note is painted unconditionally; only the card's `recreation` flag chooses its note
    assert re.search(r"g\.drawImage\(img, 0, 0, w, h\);\n\s+note\(g, NOTES\.print,", paint)
    assert ec.NOTES == {"print": "Illustration", "recreation": "Recreation"}
    assert set(ec._HERO_KEYS["print"]) == {"kind", "image", "caption"}


def test_a_black_card_may_stand_alone_and_marks_need_a_headline():
    assert "hero" not in _st(_data(EXAMPLE), DARK)
    errors = _check(_with(lambda d: _st(d, DARK)["headline"].update(kind="clipping")))
    assert any("give it a hero" in e for e in errors), errors
    errors = _check(_with(lambda d: _st(d, OPEN).pop("headline")))
    assert any("this station has no headline" in e for e in errors), errors


def test_more_than_ten_stills_are_refused():
    def many(d):
        starts = [0]
        for w in WORD_STARTS:
            if w - starts[-1] >= 50 and len(starts) < 11:
                starts.append(w)
        d["stations"] = []
        for k, start in enumerate(starts):
            st = copy.deepcopy(_data(EXAMPLE)["stations"][OPEN])
            st.update(start=start, events=[])
            st["hero"]["image"] = f"/public/{VID}/images/treated/s{k}.print.png"
            d["stations"].append(st)
    errors = _check(_with(many))
    assert any("at most 10" in e for e in errors), errors


def test_a_still_desk_is_refused():
    errors = _check(_with(lambda d: _st(d, OPEN).update(events=[])))
    assert any("nothing new happens" in e for e in errors), errors


def test_nothing_starts_and_no_glide_runs_inside_an_insert_window():
    s = _data(EXAMPLE)["stations"][THIRD]["start"]
    # a window over the station's start
    assert any("glides from frame" in e for e in _check(quiet=[(s - 10, s + 10)]))
    # a window that starts inside the glide, after the station's start
    assert any("glides from frame" in e for e in _check(quiet=[(s + 30, s + 60)]))
    # an event inside a window
    at = _data(EXAMPLE)["stations"][HOURS]["events"][0]["at"]
    errors = _check(quiet=[(at - 4, at + 4)])
    assert any("inside an insert" in e for e in errors), errors
    # a window over a quiet stretch covers it: the still rule skips it
    ev = _data(EXAMPLE)["stations"][OPEN]["events"]
    cfg = _with(lambda d: _st(d, OPEN).update(events=[ev[1]]))
    assert any("nothing new happens" in e for e in _check(cfg))
    assert _check(cfg, quiet=[(10, ev[1]["at"] - 4)]) == []


# ── the text audit and the picture checks ────────────────────────────────────

def test_the_text_audit_samples_each_station_once_the_camera_has_stopped():
    windows = ec.beat_windows(EXAMPLE)
    stations = _data(EXAMPLE)["stations"]
    assert len(windows) == len(stations)
    for i, ((first, end), st) in enumerate(zip(windows, stations)):
        assert st["start"] <= first < end
        if i:
            assert first >= st["start"] + ec.TIMING["glide"]
    plan = text_audit.plan_passes(EXAMPLE)
    assert plan["passes"] if isinstance(plan, dict) else plan


def test_the_picture_checks_read_the_style():
    assert picture_checks.style_of(EXAMPLE) == "editorial_collage"
    assert picture_checks.first_frame_warnings(EXAMPLE) == []
    alone = _with(lambda d: (_st(d, OPEN).pop("hero"), _st(d, OPEN)["headline"].update(kind="black")))
    assert "no hero" in picture_checks.first_frame_warnings(alone)[0]
    blank = _with(lambda d: _st(d, OPEN).update(hero={"kind": "index", "lines": [{"text": "x", "at": 40}]}))
    assert "blank" in picture_checks.first_frame_warnings(blank)[0]
    frames = picture_checks.change_frames("editorial_collage", EXAMPLE)
    stations = _data(EXAMPLE)["stations"]
    assert 0 in frames and stations[FIX]["start"] in frames
    assert stations[FIX]["hero"]["lines"][1]["at"] in frames            # a line typing on counts
    assert stations[HOURS]["hero"]["countAt"] in frames                 # a figure counting counts
    assert stations[OPEN]["events"][0]["at"] not in frames              # a highlight alone does not
    assert stations[FIX]["events"][0]["at"] not in frames               # nor an underline


# ── write_scene_config, the picture cap and treat_image ──────────────────────

def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "_image_reservations", {})

    def make(style="editorial_collage", images=("print-aisle",), video_id=VID):
        from PIL import Image
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                        "VALUES (?, NULL, 'the typo that took down the internet', 'VOICE_READY', ?, ?, ?)",
                        (video_id, style, _now(), _now()))
        d = tmp_path / "jobs" / video_id
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        for name in images:
            im = Image.new("RGB", (96, 96), (200, 200, 200))
            for x in range(30, 66):
                for y in range(30, 66):
                    im.putpixel((x, y), (180, 30, 30))
            im.save(d / "images" / f"{name}.png")
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_captions(make_video, tmp_path):
    vid = make_video()
    cfg = copy.deepcopy(EXAMPLE)
    assert set(cfg["subtitles"]) == {"emphasis"}
    out = server.write_scene_config(vid, cfg)
    assert "error" not in out, out
    written = json.loads((tmp_path / "jobs" / vid / "scene-config.json").read_text())
    subs = written["subtitles"]
    assert subs["look"] == "highlight" and subs["accent"] == "#DACF08" and subs["maxWords"] == 4
    assert subs["emphasis"] == EXAMPLE["subtitles"]["emphasis"]


def test_a_broken_config_writes_nothing(make_video, tmp_path):
    vid = make_video()
    bad = _with(lambda d: _hero(d, OPEN, image=f"/public/{VID}/images/print-aisle.png"))
    assert "Editorial Collage video has problems" in server.write_scene_config(vid, bad)["error"]
    assert not (tmp_path / "jobs" / vid / "scene-config.json").exists()


def test_the_scene_on_another_style_is_refused(make_video):
    vid = make_video(style="stick")
    assert "used only when" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_an_eleventh_new_still_is_refused_before_the_paid_call(make_video):
    vid = make_video(images=[f"s{k}" for k in range(10)])
    images = server.JOBS_DIR / vid / "images"
    err = server._image_cap_error(vid, "one-more", images)
    assert "already has 10 prints and cut-outs" in err and "(10)" in err
    assert server._image_cap_error(vid, "s3", images) == ""          # regenerating a still stays allowed


def test_an_eleventh_still_never_reaches_openai(make_video, monkeypatch):
    vid = make_video(images=[f"s{k}" for k in range(10)])
    monkeypatch.setattr(server, "_openai_key", lambda: "sk-test")
    import httpx
    calls = []
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError))
    out = server.generate_image(vid, "one-more", "a server rack")
    assert "already has 10 prints and cut-outs" in out["error"] and calls == []


@pytest.mark.parametrize("aspect", ["1:1", "16:9", "9:16"])
def test_the_house_prompt_is_added_and_the_agents_shape_is_kept(aspect):
    plan = server._image_plan("editorial_collage", VID, "aisle", "A data-centre aisle", aspect, "")
    assert plan["aspect_ratio"] == aspect and plan["ref_path"] is None
    assert plan["prompt"].startswith("A data-centre aisle. Documentary news photograph")
    assert "No text, no letters, no logos, no watermark, no brand names" in plan["prompt"]
    assert "no detailed face" in plan["prompt"]
    assert "reference is only for" in server._image_plan("editorial_collage", VID, "x", "y", "1:1", "lead")["error"]


def test_treat_image_bakes_a_print_and_a_sticker_and_refuses_an_engraving(make_video, tmp_path):
    vid = make_video(images=("print-aisle", "phone"))
    out = server.treat_image(vid, "print-aisle", "print")
    assert "error" not in out, out
    assert out["public_path"] == f"/public/{vid}/images/treated/print-aisle.print.png"
    assert ec._IMAGE_SRC.match(out["public_path"])                     # the path the validator wants
    out = server.treat_image(vid, "phone", "sticker")
    assert "error" not in out, out
    assert out["public_path"] == f"/public/{vid}/images/treated/phone.sticker.png"
    assert (tmp_path / "jobs" / vid / "images" / "treated" / "phone.sticker.png").is_file()
    assert "expected one of ['print', 'sticker']" in server.treat_image(vid, "phone", "engraving")["error"]
    # the treated copies are no new stills: a video at its cap may still bake the ones it has
    assert server._image_cap_error(vid, "phone", server.JOBS_DIR / vid / "images") == ""
