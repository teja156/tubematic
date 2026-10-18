"""Tests for TMDEV-26 follow-up: upsert_pronunciation_lexicon /
remove_pronunciation_lexicon — the install-wide {term, respell} lexicon that
replaced ElevenLabs pronunciation dictionaries (alias-rule dictionaries did
not audibly work on eleven_multilingual_v2, confirmed live). Pure local DB
writes now — no HTTP, no network mocking needed.

Run from repo root: pytest mcp/tests/
"""

import pytest

import server


@pytest.fixture
def settings_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file, initialized fresh."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()


# ── upsert: add ──────────────────────────────────────────────────────────────

def test_upsert_adds_a_new_entry(settings_db):
    result = server.upsert_pronunciation_lexicon(
        [{"term": "SYN", "respell": "S-Y-N"}]
    )

    assert "error" not in result
    assert result == {"entries": [{"term": "SYN", "respell": "S-Y-N"}]}
    assert server._get_lexicon() == [{"term": "SYN", "respell": "S-Y-N"}]


def test_upsert_adds_multiple_entries_in_one_call(settings_db):
    result = server.upsert_pronunciation_lexicon(
        [
            {"term": "SYN", "respell": "S-Y-N"},
            {"term": "ACK", "respell": "A-C-K"},
        ]
    )

    assert "error" not in result
    assert {e["term"] for e in result["entries"]} == {"SYN", "ACK"}


def test_upsert_accumulates_across_calls(settings_db):
    server.upsert_pronunciation_lexicon([{"term": "SYN", "respell": "S-Y-N"}])
    result = server.upsert_pronunciation_lexicon([{"term": "ACK", "respell": "A-C-K"}])

    assert {e["term"] for e in result["entries"]} == {"SYN", "ACK"}


# ── upsert: edit (this IS the correction mechanism for user feedback) ────────

def test_upsert_over_an_existing_term_edits_in_place(settings_db):
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vay-gar"}])

    result = server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah-gar"}])

    assert result == {"entries": [{"term": "Vhagar", "respell": "Vah-gar"}]}
    assert server._get_lexicon() == [{"term": "Vhagar", "respell": "Vah-gar"}]


def test_upsert_edit_does_not_duplicate_the_term(settings_db):
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vay-gar"}])
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah-gar"}])

    lexicon = server._get_lexicon()
    assert len(lexicon) == 1
    assert lexicon[0]["respell"] == "Vah-gar"


# ── validation ───────────────────────────────────────────────────────────────

def test_upsert_empty_entries_list_returns_error(settings_db):
    result = server.upsert_pronunciation_lexicon([])
    assert "error" in result


def test_upsert_entry_missing_term_returns_error(settings_db):
    result = server.upsert_pronunciation_lexicon([{"respell": "S-Y-N"}])
    assert "error" in result


def test_upsert_entry_missing_respell_returns_error(settings_db):
    result = server.upsert_pronunciation_lexicon([{"term": "SYN"}])
    assert "error" in result


def test_upsert_rejects_whitespace_in_respell(settings_db):
    """respell must be a single token — it replaces the term as one unit in
    tts_text, so a multi-word respelling would change the segment/word
    lockstep's token count."""
    result = server.upsert_pronunciation_lexicon([{"term": "whoami", "respell": "who am i"}])

    assert "error" in result
    assert server._get_lexicon() == []


def test_upsert_partial_failure_writes_nothing(settings_db):
    """One bad entry in the batch must not partially apply the good ones —
    same all-or-nothing contract as _validate_script_segments."""
    result = server.upsert_pronunciation_lexicon(
        [
            {"term": "SYN", "respell": "S-Y-N"},
            {"term": "whoami", "respell": "who am i"},  # invalid: whitespace
        ]
    )

    assert "error" in result
    assert server._get_lexicon() == []


# ── remove ───────────────────────────────────────────────────────────────────

def test_remove_deletes_an_entry(settings_db):
    server.upsert_pronunciation_lexicon([{"term": "SYN", "respell": "S-Y-N"}])

    result = server.remove_pronunciation_lexicon(["SYN"])

    assert result == {"entries": []}
    assert server._get_lexicon() == []


def test_remove_only_deletes_named_terms(settings_db):
    server.upsert_pronunciation_lexicon(
        [{"term": "SYN", "respell": "S-Y-N"}, {"term": "ACK", "respell": "A-C-K"}]
    )

    result = server.remove_pronunciation_lexicon(["SYN"])

    assert result == {"entries": [{"term": "ACK", "respell": "A-C-K"}]}


def test_remove_unknown_term_is_silently_ignored(settings_db):
    server.upsert_pronunciation_lexicon([{"term": "SYN", "respell": "S-Y-N"}])

    result = server.remove_pronunciation_lexicon(["never-registered"])

    assert result == {"entries": [{"term": "SYN", "respell": "S-Y-N"}]}


def test_remove_empty_terms_list_returns_error(settings_db):
    result = server.remove_pronunciation_lexicon([])
    assert "error" in result


# ── no network at all ────────────────────────────────────────────────────────

def test_upsert_makes_no_http_call(settings_db, monkeypatch):
    """This tool used to call ElevenLabs; it's now a pure local DB write. Fail
    loudly if anything ever reaches for httpx.Client again."""
    def _boom(*args, **kwargs):
        raise AssertionError("upsert_pronunciation_lexicon must not make HTTP calls")

    import httpx
    monkeypatch.setattr(httpx, "Client", _boom)

    result = server.upsert_pronunciation_lexicon([{"term": "SYN", "respell": "S-Y-N"}])
    assert "error" not in result


# ── the respelling form the guidance teaches ─────────────────────────────────
#
# A hyphenated respelling ("Day-mon") is not spoken correctly by ElevenLabs; a
# plain single-word spelling of the same sounds ("Daymon") is. Proven live, at
# the cost of real credit, on three terms at once.
#
# This matters more than a wording preference. An unhonoured respelling comes
# back from AI review as a `mispronunciation` must-fix, every finding routes the
# video to REVISION_REQUESTED, and each round costs a paid re-voice. Advice that
# steers an agent to the hyphen therefore bills the user on a loop.
#
# These are the guard on that, in the same spirit as
# test_ai_review.py::test_mispronunciation_bar_is_not_lowered: they assert
# against the real strings an agent reads, so a later edit cannot quietly put
# the hyphen advice back. Nothing pinned these before -- the three existing
# whitespace-rejection tests assert only that an error came back, never what it
# said -- so each assertion below was run against the pre-fix strings and
# confirmed to fail first.

import pathlib
import re as _re

_SKILLS = pathlib.Path(__file__).resolve().parents[2] / "agent_files" / "skills"


def _pronunciation_section() -> str:
    """The script-writing skill's Pronunciation section — the one place that
    tells an agent how to author a respelling in the first place."""
    text = (_SKILLS / "tubematic-script-writing-skill" / "SKILL.md").read_text()
    start = text.index("### Pronunciation")
    return text[start:text.index("\n### ", start + 1)]


def test_the_respell_tag_error_does_not_send_an_agent_back_to_the_hyphen(settings_db):
    """The message an agent sees the moment its respelling is rejected — the
    highest-leverage place to get this right, and where it was most wrong: it
    used to answer a rejected respelling with "use a single hyphenated token".

    The assertion is on that phrase, not on the word "hyphen", because the
    replacement wording has to *name* the hyphenated form in order to warn
    against it."""
    err = server._validate_respell_tags('<respell as="Vah gar">Vhagar</respell>')

    assert err is not None
    assert "hyphenated token" not in err.lower()
    assert "one plain word" in err.lower()


def test_the_lexicon_whitespace_error_does_not_send_an_agent_back_to_the_hyphen(settings_db):
    result = server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah gar"}])

    assert "error" in result
    assert "hyphenated token" not in result["error"].lower()
    assert "one plain word" in result["error"].lower()


def test_the_lexicon_tool_contract_teaches_the_plain_form(settings_db):
    """The docstring is the tool contract an agent reads before calling it. It
    used to offer "Vah-gar" as the worked example of a good respelling."""
    doc = server.upsert_pronunciation_lexicon.__doc__ or ""

    assert "hyphenated token" not in doc.lower()
    assert "Vah-gar" not in doc
    assert "Daymon" in doc


def test_the_script_writing_skill_teaches_no_hyphenated_respelling():
    """A sound-respelling must be one plain word. Spelling an acronym out letter
    by letter (S-Y-N) is a different intent and is deliberately still allowed,
    so this looks only at the `as="..."` values the section demonstrates."""
    section = _pronunciation_section()

    for as_value in _re.findall(r'<respell as="([^"]*)"', section):
        if as_value == "...":           # the elided form, not an example
            continue
        assert as_value.isupper() or "-" not in as_value, (
            f'the skill demonstrates a hyphenated sound-respelling: as="{as_value}"'
        )


def test_the_script_writing_skill_says_why_the_plain_form_is_required():
    """The reason has to travel with the rule. An agent told only 'do not
    hyphenate', with no why, hyphenates again the moment a respelling fails."""
    section = _pronunciation_section().lower()

    assert "plain" in section
    assert "elevenlabs" in section


def test_the_skill_never_demonstrates_a_respelling_the_server_rejects():
    """The phoneme-mode section used to show `<respell as="S Y N">SYN</respell>`,
    which _validate_respell_tags hard-errors on for the whitespace. The skill was
    teaching a form that update_video refuses."""
    skill = (_SKILLS / "tubematic-script-writing-skill" / "SKILL.md").read_text()

    for tag in _re.findall(r'<respell as="[^"]*">[^<]*</respell>', skill):
        if 'as="..."' in tag:
            continue
        assert server._validate_respell_tags(tag) is None, (
            f"the skill demonstrates a tag the server rejects: {tag}"
        )


def test_the_rejection_messages_keep_the_acronym_exception(settings_db):
    """Categorical "no hyphens" advice is wrong, and wrong in a way that bites.

    The tag validator's whitespace branch is reached by exactly one realistic
    input -- as="S Y N", an acronym someone spelled with spaces -- so a message
    that says only "no hyphens" answers the acronym case with the sound rule and
    turns a spelled-out acronym into a word. Both rules have to be present."""
    tag_err = server._validate_respell_tags('<respell as="S Y N">SYN</respell>')
    lex_err = server.upsert_pronunciation_lexicon(
        [{"term": "SYN", "respell": "S Y N"}]
    )["error"]

    for err in (tag_err, lex_err):
        assert "S-Y-N" in err, f"the acronym exception is missing from: {err}"
        assert "acronym" in err.lower()


def test_the_elevenlabs_docs_pointer_keeps_its_guards():
    """The skill points the agent at ElevenLabs' docs for syntax it lacks
    (TMDEV-122). Without its guards that pointer undoes decisions: the docs
    allow a 3s break against the skill's 1.0s, and contradict each other on
    which models take phoneme tags. The skill has to stay the authority."""
    section = _pronunciation_section()

    assert "https://elevenlabs.io/docs/llms.txt" in section
    assert "syntax only" in section
    assert "this skill wins" in section
    assert "get_pipeline_status()" in section
    assert "every script" in section, "must say not to fetch the docs every time"
