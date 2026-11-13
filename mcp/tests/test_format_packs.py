"""Format Packs (TMDEV-240): the insert validator in mcp/format_packs.py.

Format Packs is an insert style: one phone-native format per insert (a chat
thread, a numbered list, a quiz board, a news strap), timed on the video's
frames. These tests pin the shared contract with the renderer (the fixture
both sides run), the impersonation line the user drew (no real-looking phone
numbers, no verified ticks, no app names in a header), and the refusals an
unattended agent can hit: text that does not fit, arrivals off the
narration's words, and a still stretch.
"""
import copy
import json
import pathlib

import pytest

import format_packs as fp
from tubematic_core import visual_styles as tvs

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "format_packs_contract.json").read_text())
FPS = 30
WORDS = list(range(600, 900, 10))


def _wrap(data, start=600, dur=240):
    return {"style": "format_packs", "startFrame": start, "durationInFrames": dur, "props": {"formatPacks": data}}


def _chat(**over):
    data = {"format": "chat", "title": "The 'Hi Mum' scam",
            "contact": {"name": "Unknown number", "number": "07700 900461"},
            "messages": [{"at": 600, "from": "them", "text": "Hi Mum, I dropped my phone, this is my new number"},
                         {"at": 660, "from": "me", "text": "Oh no! You ok?"},
                         {"at": 720, "from": "them", "text": "I need to pay a bill today, can you send £800?"}],
            "marks": [{"at": 690, "message": 0, "match": "new number", "kind": "underline", "label": "New number"},
                      {"at": 760, "message": 2, "match": "£800", "kind": "ring", "label": "Money"}]}
    data.update(over)
    return _wrap(data)


def _list(**over):
    data = {"format": "list", "title": "Three signs it's a scam",
            "items": [{"at": 600, "lead": "A new number", "text": "Someone you know, texting from a number you don't"},
                      {"at": 680, "lead": "A rush", "text": "It has to be today, right now"},
                      {"at": 760, "lead": "Money", "text": "A transfer to an account you have never used"}]}
    data.update(over)
    return _wrap(data)


def _quiz(**over):
    data = {"format": "quiz", "question": "Which password takes longest to crack?",
            "options": [{"at": 640, "text": "P@ssw0rd!"}, {"at": 670, "text": "correct horse battery"},
                        {"at": 700, "text": "Qx7!"}],
            "answer": 1, "lockAt": 760}
    data.update(over)
    return _wrap(data)


def _strap(**over):
    data = {"format": "strap", "kicker": "Price change", "headline": "Streaming plan goes up again this spring",
            "date": "12 Mar 2026",
            "marks": [{"at": 660, "match": "goes up"}],
            "flap": {"label": "Monthly price", "from": "$9.99", "to": "$12.99", "at": 730}}
    data.update(over)
    return _wrap(data)


def _check(entry, words=WORDS):
    return fp.check_insert(entry, FPS, words, [])


def _data(entry):
    return entry["props"]["formatPacks"]


# ── the shared contract ─────────────────────────────────────────────────────

def test_the_constants_match_the_fixture():
    assert list(fp.FORMATS) == FIXTURE["formats"]
    assert fp.LIMITS == FIXTURE["limits"]
    assert fp.TIMING == FIXTURE["timing"]
    assert {k: list(v) for k, v in fp.WRAP.items()} == FIXTURE["wrap_boxes"]
    assert {k: list(v) for k, v in fp.ONE_LINE.items()} == FIXTURE["one_line"]
    assert list(fp.BAND) == FIXTURE["band"]
    assert fp.LAYOUT == FIXTURE["layout"]
    assert list(fp.TICKS) == FIXTURE["ticks"]
    assert list(fp.APPS) == FIXTURE["apps"]


def test_the_pack_draws_in_the_contract_band():
    block = tvs.pack("format_packs")["insert"]
    assert block["block"] == list(fp.BAND)
    assert block["props_key"] == fp.PROPS_KEY and block["component"] == fp.SCENE_SRC


@pytest.mark.parametrize("case", FIXTURE["wrap"])
def test_wrapping_matches_the_fixture(case):
    assert fp.wrap_lines(case["text"], case["kind"]) == case["lines"]


@pytest.mark.parametrize("case", FIXTURE["thread_height"])
def test_thread_height_matches_the_fixture(case):
    assert fp.thread_height(case["texts"]) == case["height"]


@pytest.mark.parametrize("number", FIXTURE["fiction_numbers"])
def test_fiction_numbers_pass(number):
    assert fp.is_fiction_number(number)


@pytest.mark.parametrize("number", FIXTURE["real_numbers"])
def test_real_looking_numbers_do_not(number):
    assert not fp.is_fiction_number(number)


@pytest.mark.parametrize("case", FIXTURE["app_headers"])
def test_app_names_match_the_fixture(case):
    assert fp.app_names(case["text"]) == case["apps"]


# ── good inserts ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("make", [_chat, _list, _quiz, _strap])
def test_a_good_insert_of_each_format_passes(make):
    assert _check(make()) == []


def test_a_strap_with_a_source_passes():
    e = _strap(source="Company price notice, Mar 2026")
    assert _check(e) == []


def test_amounts_and_dates_are_not_phone_numbers():
    e = _chat()
    _data(e)["messages"][2]["text"] = "Send £800 by 12.03.2026, or £1,250,000 next week"
    assert _check(e) == []


# ── the impersonation line ───────────────────────────────────────────────────

@pytest.mark.parametrize("change, fragment", [
    (lambda e: _data(e)["contact"].update(number="07911 123456"), "fiction"),
    (lambda e: _data(e)["contact"].update(number="(415) 555-2671"), "fiction"),
    (lambda e: _data(e)["messages"][0].update(text="Call me back on 0207 946 1234 now"), "looks like a real phone number"),
    (lambda e: _data(e)["contact"].update(name="Bank ✔"), "verified mark"),
    (lambda e: _data(e)["messages"][1].update(text="Done ✅"), "verified mark"),
    (lambda e: _data(e)["contact"].update(name="WhatsApp Support"), "names WhatsApp"),
    (lambda e: _data(e).update(title="Spot the X scam"), "names X"),
])
def test_what_passes_for_a_real_app_is_refused(change, fragment):
    e = _chat()
    change(e)
    errors = _check(e)
    assert any(fragment in m for m in errors), errors


def test_an_app_name_in_a_list_title_or_strap_kicker_is_refused():
    assert any("names Instagram" in m for m in _check(_list(title="Instagram scams to know")))
    assert any("names TikTok" in m for m in _check(_strap(kicker="TikTok news")))


# ── refusals ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("make, change, fragment", [
    (_chat, lambda d: d.update(format="poll"), "must be one of"),
    (_chat, lambda d: d.update(colour="red"), "remove ['colour']"),
    (_chat, lambda d: d.update(messages=d["messages"][:1]), "2 to 5"),
    (_chat, lambda d: d["messages"][0].update(at=610), "on screen with the insert"),
    (_chat, lambda d: d["messages"][1].update(at=605), "not on a word"),
    (_chat, lambda d: d["messages"][1].update(at=610), "at least 18"),
    (_chat, lambda d: d["messages"][2].update(at=830), "outside the insert"),
    (_chat, lambda d: d["messages"][0].update(text="x" * 91), "1 to 90"),
    (_chat, lambda d: d["messages"][0].update(**{"from": "bank"}), "from \"them\" or \"me\""),
    (_chat, lambda d: d["marks"][0].update(match="old number"), "words in message 0"),
    (_chat, lambda d: d["marks"][0].update(at=600), "before its message is on screen"),
    (_chat, lambda d: d["marks"][0].update(kind="arrow"), "kind \"underline\" or \"ring\""),
    (_chat, lambda d: d["marks"][0].update(message=7), "index (from 0)"),
    (_chat, lambda d: d["marks"][0].update(label="A label far too long"), "1 to 16"),
    (_list, lambda d: d.update(items=d["items"] + [dict(d["items"][0], at=790)] * 2), "2 to 4"),
    (_list, lambda d: d["items"][0].update(text="W" * 24 + " " + "W" * 24), "more than 2 lines"),
    (_list, lambda d: d.update(title="A title so long that it needs three lines to fit on the card"), "1 to 40"),
    (_quiz, lambda d: d.update(answer=5), "index (from 0) of the right option"),
    (_quiz, lambda d: d.update(lockAt=710), "before every option has been read"),
    (_quiz, lambda d: d["options"][0].update(text="An option much too long for a row"), "1 to 30"),
    (_strap, lambda d: d["marks"][0].update(match="goes down"), "words in the headline"),
    (_strap, lambda d: d["flap"].update(to="$9.99"), "the same"),
    (_strap, lambda d: d.update(headline="word " * 15), "1 to 70"),
    (_strap, lambda d: d.update(headline="goes up " + "w" * 23 + " " + "w" * 23 + " end"), "more than 3 lines"),
])
def test_a_bad_insert_is_refused(make, change, fragment):
    e = make()
    change(_data(e))
    errors = _check(e)
    assert any(fragment in m for m in errors), errors


def test_a_thread_too_tall_for_the_phone_is_refused():
    long = "This message is long enough to take four whole lines on the phone screen, near the limit"
    e = _chat(messages=[{"at": 600 + i * 30, "from": "them" if i % 2 == 0 else "me", "text": long} for i in range(5)],
              marks=[])
    assert any("do not fit on the phone" in m for m in _check(e))


def test_a_still_stretch_is_refused():
    e = _strap(marks=[], flap=None)
    _data(e).pop("flap")
    errors = _check(e)
    assert any("Nothing changes" in m for m in errors), errors


def test_errors_are_capped():
    e = _chat(messages=[{"at": "x", "from": "?", "text": 3}] * 5, marks=[{"at": "y"}] * 3)
    assert len(_check(e)) <= fp.MAX_ERRORS


def test_props_must_hold_the_data():
    assert "props must hold" in _check({"startFrame": 0, "durationInFrames": 90, "props": {}})[0]


def test_unit_windows_cover_the_insert():
    assert fp.insert_unit_windows(_quiz()) == [(600, 640), (640, 670), (670, 700), (700, 760), (760, 840)]


def test_the_component_is_never_a_scene():
    assert "insert style" in fp.check_scene_use([{"type": "generated", "src": "FormatPacks"}])
    assert fp.check_scene_use([{"type": "generated", "src": "Other"}]) == ""


def test_the_check_leaves_the_entry_alone():
    e = _chat()
    before = copy.deepcopy(e)
    _check(e)
    assert e == before


# ── through write_scene_config ──────────────────────────────────────────────

from test_inserts import _config, video  # noqa: E402,F401  (the shared video fixture)


def test_write_scene_config_writes_a_format_packs_insert(video):  # noqa: F811
    import server
    vid = video(marks={"s3": "format_packs"}, allowed='["format_packs"]')
    result = server.write_scene_config(vid, copy.deepcopy(_config(_chat())))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["inserts"][0]["src"] == "FormatPacks"
    assert written["inserts"][0]["palette"] == "light"


def test_write_scene_config_names_the_format_packs_problem(video):  # noqa: F811
    import server
    vid = video(marks={"s3": "format_packs"}, allowed='["format_packs"]')
    e = _chat()
    _data(e)["contact"]["number"] = "07911 123456"
    result = server.write_scene_config(vid, copy.deepcopy(_config(e)))
    assert "The insert scenes have problems" in result["error"] and "fiction" in result["error"]


def test_the_format_packs_component_is_refused_as_a_scene(video):  # noqa: F811
    import server
    vid = video(marks={})
    cfg = _config()
    cfg["scenes"] = [{"type": "generated", "source": "installed", "src": "FormatPacks", "startFrame": 0,
                      "durationInFrames": 1500, "props": {"formatPacks": _data(_chat())}}]
    assert "Format Packs is an insert style" in server.write_scene_config(vid, cfg)["error"]


def test_the_text_audit_samples_a_format_packs_insert():
    import text_audit
    passes, _ = text_audit.plan_passes(_config(_quiz()))
    units = [p for p in passes if p["scene"] == 1]
    assert units and all(600 <= p["first"] < 840 for p in units)
    assert text_audit._unit_label(_config(_quiz()), 1) == "insert 1 (format_packs)"


# ── review round 1 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("number", ["212.867.5309", "212/867/5309", "212–867–5309", "+44 20.7946.0000"])
def test_phone_numbers_written_with_dots_slashes_or_dashes_are_refused(number):
    e = _chat()
    e["props"]["formatPacks"]["messages"][0]["text"] = f"Call me on {number} now"
    errors = _check(e)
    assert any("looks like a real phone number" in m for m in errors), errors


def test_prices_and_dates_with_dots_or_slashes_are_not_phone_numbers():
    e = _chat()
    e["props"]["formatPacks"]["messages"][0]["text"] = "It went from 1.299.000 to 12/03/2026 overnight"
    assert not any("phone number" in m for m in _check(e))


def test_a_phone_number_on_the_flap_is_refused():
    e = _strap()
    e["props"]["formatPacks"]["flap"].update({"from": "2125550000", "to": "2128675309"})
    assert any("looks like a real phone number" in m for m in _check(e))


def test_a_chat_title_that_wraps_above_the_phone_is_refused():
    errors = _check(_chat(title="What a fake parcel text looks like"))
    assert any("does not fit one line above the phone" in m for m in errors), errors


def test_overlapping_marks_on_one_message_are_refused():
    e = _chat()
    e["props"]["formatPacks"]["marks"].append({"at": 800, "message": 2, "match": "£80", "kind": "underline"})
    errors = _check(e)
    assert any("overlap another mark on message 2" in m for m in errors), errors


def test_overlapping_marks_on_the_headline_are_refused():
    e = _strap()
    e["props"]["formatPacks"]["marks"].append({"at": 700, "match": "goes"})
    errors = _check(e)
    assert any("overlap another mark on the headline" in m for m in errors), errors


def test_a_flap_still_flipping_at_the_end_is_refused():
    e = _strap()
    e["props"]["formatPacks"]["flap"].update({"from": "$1,000,000", "to": "$2,500,000", "at": 800})
    errors = _check(e)
    assert any("would still be flipping" in m for m in errors), errors


def test_wide_letters_wrap_a_bubble_to_more_lines_than_their_count():
    # A count of characters cannot tell narrow letters from wide ones; the
    # width estimate can, so a thread of wide bubbles no longer slips past.
    assert fp.wrap_lines("W" * 22, "bubble") > fp.wrap_lines("i" * 22, "bubble")
    e = _chat()
    for m in e["props"]["formatPacks"]["messages"]:
        m["text"] = "W" * 22 + " " + "W" * 22
    e["props"]["formatPacks"]["messages"] += [{"at": 790, "from": "them", "text": "W" * 22 + " " + "W" * 22}]
    e["props"]["formatPacks"]["marks"] = []
    assert any("do not fit on the phone" in m for m in _check(e))


def test_a_quiz_option_too_wide_for_its_row_is_refused():
    e = _quiz()
    e["props"]["formatPacks"]["options"][1]["text"] = "W" * 30
    assert any("does not fit its row" in m for m in _check(e))


def test_a_flap_with_only_its_first_tile_changing_may_start_late():
    # Unchanged tiles are already in place, so only the changing ones take time.
    assert fp.flap_frames("AAAAAAAAAA", "BAAAAAAAAA") == fp.TIMING["flip"]
    assert fp.flap_frames("$9.99", "$12.99") == 2 * fp.TIMING["flipPerTile"] + fp.TIMING["flip"]
    e = _strap()
    e["props"]["formatPacks"]["flap"].update({"from": "AAAAAAAAAA", "to": "BAAAAAAAAA", "at": 800})
    assert not any("still be flipping" in m for m in _check(e))


def test_an_emoji_on_the_flap_is_refused():
    e = _strap()
    e["props"]["formatPacks"]["flap"].update({"to": "\U0001F4C8 up"})
    assert any("tile cannot show" in m for m in _check(e))


@pytest.mark.parametrize("number", ["867.5309", "867/5309"])
def test_a_local_number_written_with_dots_or_slashes_is_refused(number):
    e = _chat()
    e["props"]["formatPacks"]["messages"][0]["text"] = f"Text me on {number}"
    assert any("looks like a real phone number" in m for m in _check(e))


def test_a_phone_shaped_flap_value_is_refused_and_a_bare_count_is_not():
    e = _strap()
    e["props"]["formatPacks"]["flap"].update({"from": "867-5309", "to": "867-5310", "at": 730})
    assert any("looks like a real phone number" in m for m in _check(e))
    e["props"]["formatPacks"]["flap"].update({"from": "1500000", "to": "2500000"})
    assert not any("phone number" in m for m in _check(e))
