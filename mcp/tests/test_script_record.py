"""Tests for what update_video records with a script (TMDEV-211): the formula
it follows, the three openings the writer drafted, and the advisory warnings.

Three things here are easy to get wrong and expensive when they are:

- A warning must never refuse a write. A check that blocked would stop every
  script on its first false positive.
- A writer that sends no formula (an older skill during an upgrade) must still
  be able to write a script.
- The record must follow the script. A pronunciation fix resends the script
  with new markup and no record, and must keep it; a rewrite that sends none
  must not leave the old formula beside new words.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
from datetime import datetime, timezone

import pytest

import server

FORMULA = "broken-expectation"
OPENING = "You renamed one file and rewrote half of it in the same commit."
BODY = ("Now the history shows a deleted file and a brand new one, and the log stops dead at "
        "today. So you blame the rename and do it again with the move command. Same two lines, "
        "one red and one green. Then the log must be wrong. But every diff tells the same story. "
        "Nothing is broken. The rename was never written down. Each commit stores a list of "
        "names, and each name points at a blob of content. So a rename is one name vanishing and "
        "another appearing. When you ask for history, the tool pairs a deleted name with an added "
        "one and compares what is inside. Change nothing, and the two match completely. But "
        "rewrite half the lines and the match drops below the fifty percent the tool needs. It "
        "stops calling it a rename.")
ENDING = ("The file was never lost. The guess just failed, and a lower similarity threshold on "
          "the log command brings the whole history back.")
PUBLISH = {"publish_title": "Why Git Loses a File You Renamed",
           "publish_description": "What a rename is inside a repository, and why the log stops."}


def segments(ending=ENDING, opening=OPENING):
    return [{"id": "seg-1", "beat": "The symptom", "voice": opening, "visual": "a terminal"},
            {"id": "seg-2", "voice": BODY, "visual": "a diagram"},
            {"id": "seg-3", "beat": "Callback", "voice": ending, "visual": "the log again"}]


def hooks(**over):
    out = [{"type": "problem", "text": OPENING, "kept": True},
           {"type": "question", "text": "Why does the log stop at today when all you did was rename a file?"},
           {"type": "myth", "text": "A rename is recorded, obviously. Try one and read the commit.",
            "note": "claims a test the script never runs"}]
    for i, change in over.items():
        out[int(i[1:])].update(change)
    return out


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert(video_id, project_id=None, script="", created="2026-01-01T00:00:00Z"):
    with server._conn() as con:
        if project_id:
            con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?, ?, ?)",
                        (project_id, project_id, _now()))
        con.execute(
            "INSERT INTO videos (id, topic, status, project_id, script, created_at, updated_at) "
            "VALUES (?, 'test topic', 'TOPIC_APPROVED', ?, ?, ?, ?)",
            (video_id, project_id, script, created, _now()))


@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    _insert("vid1", project_id="git")
    return "vid1"


def _row(video_id="vid1"):
    with server._conn() as con:
        return dict(con.execute(
            "SELECT script, formula_id, hook_type, hook_alternatives, script_warnings "
            "FROM videos WHERE id = ?", (video_id,)).fetchone())


def write(video, **kw):
    kw.setdefault("script_segments", segments())
    return server.update_video(video, **PUBLISH, **kw)


def warning_ids(result):
    return [w["id"] for w in result["warnings"]]


# --- the record is written ------------------------------------------------

def test_a_script_is_stored_with_its_formula_and_openings(video):
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert result["warnings"] == []
    assert result["updated_fields"] == ["script", "publish_title", "publish_description",
                                        "script_segments", "formula_id", "hook_type",
                                        "hook_alternatives"]
    got = server.get_video(video)
    assert got["formula_id"] == FORMULA
    assert got["hook_type"] == "problem"
    assert [h["type"] for h in got["hook_alternatives"]] == ["problem", "question", "myth"]
    assert [h["kept"] for h in got["hook_alternatives"]] == [True, False, False]
    assert got["hook_alternatives"][2]["note"] == "claims a test the script never runs"
    assert got["script_warnings"] == []
    assert got["script_segments"][0]["beat"] == "The symptom"


def test_an_opening_is_stored_as_it_is_spoken(video):
    tagged = hooks(h1={"text": 'Why does <respell as="Gitt">Git</respell> stop at today? [pause]'})
    # [pause] is legal only on v3 and v4, but an opening is not sent to the voice.
    write(video, formula_id=FORMULA, hooks=tagged)
    assert server.get_video(video)["hook_alternatives"][1]["text"] == "Why does Git stop at today?"


def test_a_video_with_no_record_reads_as_empty_lists(video):
    got = server.get_video(video)
    assert (got["formula_id"], got["hook_type"]) == ("", "")
    assert got["hook_alternatives"] == [] and got["script_warnings"] == []


# --- the record's shape is checked ----------------------------------------

@pytest.mark.parametrize("kw, message", [
    ({"formula_id": FORMULA}, "pass both"),
    ({"hooks": hooks()}, "pass both"),
    ({"formula_id": "five-beats", "hooks": hooks()}, "is not a formula"),
    ({"formula_id": "", "hooks": hooks()}, "is not a formula"),
    ({"formula_id": FORMULA, "hooks": hooks()[:2]}, "exactly 3"),
    ({"formula_id": FORMULA, "hooks": "three openings"}, "exactly 3"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"type": "shout"})}, "opening types of"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"type": ["question"]})}, "opening types of"),
    # A real hook type that this formula's reference file does not offer.
    ({"formula_id": FORMULA, "hooks": hooks(h1={"type": "scene"})}, "opening types of"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"type": "problem"})}, "different types"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"kept": True})}, "exactly one"),
    ({"formula_id": FORMULA, "hooks": hooks(h0={"kept": False})}, "exactly one"),
    ({"formula_id": FORMULA, "hooks": hooks(h0={"kept": "yes"})}, "true or false"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"text": "  "})}, "spoken words"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"text": "[pause]"})}, "spoken words"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"text": "word " * 100})}, "longer than"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"note": "x" * 201})}, "note"),
    ({"formula_id": FORMULA, "hooks": hooks(h1={"score": 9})}, "'type' and 'text'"),
    ({"formula_id": FORMULA, "hooks": [{"type": "problem"}] * 3}, "'type' and 'text'"),
])
def test_a_malformed_record_is_refused_and_nothing_is_written(video, kw, message):
    result = write(video, **kw)
    assert message in result["error"]
    assert _row() == {"script": "", "formula_id": "", "hook_type": "",
                      "hook_alternatives": "", "script_warnings": ""}


def test_a_record_without_a_script_is_refused(video):
    result = server.update_video(video, formula_id=FORMULA, hooks=hooks())
    assert "script_segments" in result["error"]
    result = server.update_video(video, script="A flat script.", formula_id=FORMULA,
                                 hooks=hooks(), **PUBLISH)
    assert "script_segments" in result["error"]


# --- warnings never refuse ------------------------------------------------

def test_a_flagged_script_is_still_written(video):
    bad = segments(opening="Hey everyone, welcome back.",
                   ending="So remember, a rename is only a guess. Follow for more Git internals.")
    result = write(video, script_segments=bad, formula_id=FORMULA, hooks=hooks())
    assert "error" not in result
    assert {"greeting_opener", "hook_mismatch", "recap_ending", "closing_ask"} <= set(warning_ids(result))
    stored = server.get_video(video)
    assert stored["script"].startswith("Hey everyone")
    assert stored["script_warnings"] == result["warnings"]
    assert all(set(w) == {"id", "message"} for w in stored["script_warnings"])


def test_a_script_with_no_record_is_accepted_and_says_so(video):
    result = write(video)
    assert warning_ids(result) == ["no_formula"]
    assert _row()["formula_id"] == ""


def test_the_band_comes_from_the_recorded_formula(video):
    short = [{"id": "seg-1", "voice": OPENING + " But it was a guess.", "visual": ""}]
    result = write(video, script_segments=short, formula_id=FORMULA, hooks=hooks())
    assert "length_band" in warning_ids(result)


def test_the_title_checked_is_the_one_in_the_same_call(video):
    result = server.update_video(
        video, script_segments=segments(), formula_id=FORMULA, hooks=hooks(),
        publish_title="You renamed one file and rewrote half of it",
        publish_description="x")
    assert "title_repeat" in warning_ids(result)


def test_a_legacy_flat_script_gets_warnings_too(video):
    result = server.update_video(
        video, script='A flat script. <break time="0.5s" /> Follow for more.', **PUBLISH)
    assert set(warning_ids(result)) == {"no_formula", "closing_ask"}
    assert json.loads(_row()["script_warnings"]) == result["warnings"]


def test_a_write_that_touches_no_script_returns_no_warnings(video):
    write(video, formula_id=FORMULA, hooks=hooks())
    result = server.update_video(video, publish_title="A new title for the same script")
    assert "warnings" not in result
    assert _row()["script_warnings"] == "[]"


# --- the closing sentence against the domain ---------------------------------

def test_a_closing_shared_with_the_domains_scripts_is_flagged(video):
    _insert("old1", project_id="git", script="Something else. The guess just went the wrong way.")
    _insert("other_domain", project_id="dns", script="Start here. The guess just went the wrong way.")
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert warning_ids(result) == ["closing_repeat"]
    assert "1 of" in result["warnings"][0]["message"]


def test_a_video_is_not_compared_with_its_own_earlier_script(video):
    write(video, formula_id=FORMULA, hooks=hooks())
    again = write(video, formula_id=FORMULA, hooks=hooks())
    assert again["warnings"] == []


def test_only_the_domains_newest_scripts_are_read(video):
    limit = server.tchecks.RECENT_SCRIPTS
    _insert("oldest", project_id="git", script="Start here. The guess just went wrong.",
            created="2025-01-01T00:00:00Z")
    for i in range(limit):
        _insert(f"new{i}", project_id="git", script=f"Start here. Ending number {i} goes here.",
                created=f"2026-02-{i + 1:02d}T00:00:00Z" if i < 28 else f"2026-03-{i - 27:02d}T00:00:00Z")
    assert "closing_repeat" not in warning_ids(write(video, formula_id=FORMULA, hooks=hooks()))
    with server._conn() as con:
        con.execute("DELETE FROM videos WHERE id = 'new0'")
    assert "closing_repeat" in warning_ids(write(video, formula_id=FORMULA, hooks=hooks()))


def test_a_video_with_no_domain_skips_the_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    _insert("loose")
    _insert("other", script="Start here. The guess just went wrong.")
    assert write("loose", formula_id=FORMULA, hooks=hooks())["warnings"] == []
    # The same pair inside one domain is flagged, so the quiet above is the skip.
    _insert("in_a", project_id="git")
    _insert("in_b", project_id="git", script="Start here. The guess just went wrong.")
    assert warning_ids(write("in_a", formula_id=FORMULA, hooks=hooks())) == ["closing_repeat"]


# --- the record follows the script ----------------------------------------

def test_a_pronunciation_fix_keeps_the_record(video):
    write(video, formula_id=FORMULA, hooks=hooks())
    fixed = segments(opening=OPENING.replace("commit", '<respell as="komit">commit</respell>'))
    result = write(video, script_segments=fixed)
    assert "warnings" not in result          # the words are approved: nothing is checked again
    assert "formula_id" not in result["updated_fields"]
    row = _row()
    assert (row["formula_id"], row["hook_type"]) == (FORMULA, "problem")
    assert len(json.loads(row["hook_alternatives"])) == 3


def test_a_pronunciation_fix_on_a_script_with_no_record_raises_nothing(video):
    # A script from before records existed, ending on a follow line. The fix
    # goes straight to a paid re-voice, so a warning here would invite the
    # agent to change words a person approved.
    old = segments(ending="Follow for more Git internals.")
    with server._conn() as con:
        con.execute("UPDATE videos SET script = ?, script_segments = ? WHERE id = ?",
                    (server._strip_non_spoken(server._join_segment_voice(old)), json.dumps(old), video))
    fixed = segments(ending='Follow for more <respell as="Gitt">Git</respell> internals.')
    result = write(video, script_segments=fixed)
    assert "error" not in result and "warnings" not in result
    assert _row()["script_warnings"] == ""
    assert server.get_video(video)["script_warnings"] == []


def test_a_pronunciation_fix_on_a_stored_flat_script_raises_nothing(video):
    # A flat script is stored with its markup and its line breaks. Resent as
    # segments with a tag added, its spoken words are the same.
    with server._conn() as con:
        con.execute("UPDATE videos SET script = ? WHERE id = ?",
                    ('Daemon rode out at dawn.\nNobody followed. <break time="0.5s" /> '
                     "Follow for more.", video))
    fixed = [{"id": "s1", "visual": "",
              "voice": '<respell as="Daymon">Daemon</respell> rode out at dawn. Nobody followed. '
                       "Follow for more."}]
    result = write(video, script_segments=fixed)
    assert "error" not in result and "warnings" not in result
    flat = server.update_video(video, script='<respell as="Daymon">Daemon</respell> rode out at '
                               "dawn. Nobody followed. Follow for more.", **PUBLISH)
    assert "error" not in flat and "warnings" not in flat
    assert _row()["script_warnings"] == ""


def test_a_null_note_is_no_note(video):
    result = write(video, formula_id=FORMULA, hooks=hooks(h0={"note": None}))
    assert "error" not in result
    assert server.get_video(video)["hook_alternatives"][0]["note"] == ""


def test_a_fault_in_the_checks_does_not_stop_the_write(video, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("a check broke")
    monkeypatch.setattr(server.tchecks, "check", boom)
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert result["warnings"] == [] and _row()["formula_id"] == FORMULA


def test_a_rewrite_that_sends_no_record_clears_it(video):
    write(video, formula_id=FORMULA, hooks=hooks())
    rewritten = segments(ending="The file was there all along, under another name.")
    result = write(video, script_segments=rewritten)
    assert "no_formula" in warning_ids(result)
    row = _row()
    assert (row["formula_id"], row["hook_type"], row["hook_alternatives"]) == ("", "", "")
    assert server.get_video(video)["hook_alternatives"] == []


def test_a_rewrite_with_a_new_record_replaces_the_old_one(video):
    write(video, formula_id=FORMULA, hooks=hooks())
    opening = "Why don't sites just keep your password?"
    new_hooks = [{"type": "question", "text": opening, "kept": True},
                 {"type": "anomaly", "text": "A site can reset your password and cannot read it."},
                 {"type": "claim", "text": "Storing the password would end resets overnight."}]
    result = write(video, script_segments=segments(opening=opening),
                   formula_id="why-dont-they-just", hooks=new_hooks)
    assert "error" not in result
    row = _row()
    assert (row["formula_id"], row["hook_type"]) == ("why-dont-they-just", "question")


# --- the beat label ---------------------------------------------------------

@pytest.mark.parametrize("beat", ["", "   ", 7, "x" * 61])
def test_a_bad_beat_label_is_refused(video, beat):
    segs = segments()
    segs[0]["beat"] = beat
    assert "beat" in write(video, script_segments=segs)["error"]


def test_segments_without_a_beat_label_are_fine(video):
    segs = [{k: v for k, v in s.items() if k != "beat"} for s in segments()]
    assert "error" not in write(video, script_segments=segs, formula_id=FORMULA, hooks=hooks())


# --- the script follows the formula picked for it (TMDEV-213) ------------------

def _pick(video, formula):
    with server._conn() as con:
        con.execute("UPDATE videos SET formula_pick = ? WHERE id = ?", (formula, video))


def test_a_script_in_another_formula_than_the_pick_is_refused(video):
    _pick(video, "scene-story")
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert "scene-story" in result["error"] and "formula_routing" in result["error"]
    assert _row()["script"] in ("", None) and _row()["formula_id"] == ""


def test_a_script_in_the_picked_formula_is_written(video):
    _pick(video, FORMULA)
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert "error" not in result and _row()["formula_id"] == FORMULA


def test_with_no_pick_on_record_any_formula_is_taken(video):
    # A video scripted before picks existed, or a writer on an older skill.
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert "error" not in result and _row()["formula_id"] == FORMULA


def test_a_script_with_no_record_is_still_written_beside_a_pick(video):
    _pick(video, "scene-story")
    result = write(video)
    assert "error" not in result and "no_formula" in warning_ids(result)


def test_a_pronunciation_fix_is_not_checked_against_the_pick(video):
    write(video, formula_id=FORMULA, hooks=hooks())
    _pick(video, "scene-story")   # a switch that has not been rewritten yet
    assert "error" not in write(video)


# --- the opening varies across a domain (TMDEV-213) ----------------------------

def test_an_opening_type_the_domain_just_used_is_flagged(video):
    _insert("older", project_id="git", script="Other words entirely. And an end.",
            created="2025-12-01T00:00:00Z")
    with server._conn() as con:
        con.execute("UPDATE videos SET hook_type = 'problem' WHERE id = 'older'")
    assert "hook_type_repeat" in warning_ids(write(video, formula_id=FORMULA, hooks=hooks()))
    with server._conn() as con:
        con.execute("UPDATE videos SET hook_type = 'question' WHERE id = 'older'")
    assert "hook_type_repeat" not in warning_ids(write(video, formula_id=FORMULA, hooks=hooks()))


def test_an_opening_that_starts_like_the_domains_scripts_is_flagged(video):
    _insert("older", project_id="git", script="You renamed one branch. Then it broke.",
            created="2025-12-01T00:00:00Z")
    assert "opening_repeat" in warning_ids(write(video, formula_id=FORMULA, hooks=hooks()))


def test_a_persons_choice_binds_when_no_pick_was_recorded(video):
    # A writer that skipped the pick (an older skill) must not replace a
    # formula a person chose.
    with server._conn() as con:
        con.execute("UPDATE videos SET formula_choice = 'scene-story' WHERE id = ?", (video,))
    result = write(video, formula_id=FORMULA, hooks=hooks())
    assert "scene-story" in result["error"] and _row()["formula_id"] == ""


def test_a_choice_of_a_formula_this_version_lacks_does_not_bind(video):
    with server._conn() as con:
        con.execute("UPDATE videos SET formula_choice = 'retired-formula' WHERE id = ?", (video,))
    assert "error" not in write(video, formula_id=FORMULA, hooks=hooks())
