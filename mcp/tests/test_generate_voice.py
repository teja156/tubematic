"""Tests for generate_voice: segment-derived TTS text, model/pronunciation-mode
settings wiring (TMDEV-26 — dictionary vs phoneme), and the segment/word
lockstep alignment written into timeline.json.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import base64
import json
import re
import sqlite3
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _set_install_model(model_id):
    """One roster voice on model_id, made the install default. The model
    follows the voice (TMDEV-121), so this is how a test picks the model a
    video with no voice of its own is scripted and voiced with."""
    server._set_setting("elevenlabs_voices", json.dumps(
        [{"name": "Test", "voice_id": "test-voice-id", "model_id": model_id}]))
    server._set_setting("elevenlabs_voice_id", "test-voice-id")


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file, initialized fresh. Returns
    a make_video factory."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()

    def make_video(video_id, script="", script_segments=None, project_id=None, status="VOICING",
                   voice_id=""):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos "
                "(id, project_id, topic, status, script, script_segments, voice_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    video_id, project_id, "test topic", status, script,
                    json.dumps(script_segments) if script_segments else None,
                    voice_id, _now(), _now(),
                ),
            )

    return make_video


@pytest.fixture
def voice_env(job_db, tmp_path, monkeypatch):
    """Configure the ElevenLabs API key + install-default voice_id (DB-backed,
    like every other setting — there's no .env fallback) and redirect
    JOBS_DIR to a tmp dir. Depends on job_db (not just requested alongside it
    in a test signature) so DB init always runs before this seeds a row into
    it, regardless of parameter order in any given test."""
    monkeypatch.setattr(server, "_elevenlabs_key", lambda: "test-api-key")
    _set_install_model("eleven_multilingual_v2")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")


def _char_alignment(text: str, char_dur: float = 0.05) -> dict:
    """Build a fake per-character ElevenLabs alignment for `text`."""
    chars = list(text)
    return {
        "characters": chars,
        "character_start_times_seconds": [i * char_dur for i in range(len(chars))],
        "character_end_times_seconds": [(i + 1) * char_dur for i in range(len(chars))],
    }


_FAKE_PHONEME_TAG_RE = re.compile(r'<phoneme\b[^>]*\bph="([^"]*)"[^>]*>.*?</phoneme>', re.IGNORECASE | re.DOTALL)


def _fake_normalize(text: str) -> str:
    """Simulate ElevenLabs' normalized_alignment text: a live probe (TMDEV-26
    Step 0) showed a <phoneme> tag collapses into a single space-free
    phonetic placeholder built from its `ph` attribute — never the original
    word. Building the fake this way (rather than just echoing the word back)
    is what makes these tests actually exercise generate_voice's word-text
    override, instead of passing by coincidence.

    A second probe (TMDEV-26, pause support) showed a <break/> tag collapses
    not to nothing but to a lone '.' token at the tag's position — which is
    why generate_voice has to drop punctuation-only marker tokens on this
    path rather than relying on the character-index skip.
    """
    text = _FAKE_PHONEME_TAG_RE.sub(lambda m: "@" + "@".join(m.group(1).split()), text)
    return re.sub(r'<break\b[^>]*>', ".", text, flags=re.IGNORECASE)


class _FakeResponse:
    def __init__(self, status_code, json_data, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data


class _FakeClient:
    """Records the payload of the last POST call and returns a canned
    alignment response derived from the payload's own `text` field, so the
    fake alignment always matches whatever tts_text generate_voice built."""

    last_payload = None
    credits = 42  # what the fake `character-cost` header reports

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, json=None, headers=None):
        _FakeClient.last_payload = json
        text = json["text"]
        return _FakeResponse(200, {
            "audio_base64": base64.b64encode(b"fake-audio-bytes").decode(),
            "alignment": _char_alignment(text),
            "normalized_alignment": _char_alignment(_fake_normalize(text)),
        }, headers={"character-cost": str(_FakeClient.credits), "request-id": "req-fake"})


@pytest.fixture
def fake_httpx(monkeypatch):
    import httpx
    _FakeClient.last_payload = None
    monkeypatch.setattr(httpx, "Client", _FakeClient)
    return _FakeClient


def _voice_events(video_id):
    """The ElevenLabs usage events recorded against a video."""
    with server._conn() as con:
        return con.execute(
            "SELECT e.* FROM usage_events e JOIN usage_event_videos l ON l.event_id = e.id "
            "WHERE l.video_id = ? AND e.service = 'elevenlabs'", (video_id,)).fetchall()


def _voice_credits(video_id):
    import json as _json
    return sum(_json.loads(e["units"]).get("credits", 0) for e in _voice_events(video_id))


# ── _strip_phoneme_tags ──────────────────────────────────────────────────────

def test_strip_phoneme_tags_removes_markup_keeps_word():
    text = 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.'
    assert server._strip_phoneme_tags(text) == "The word Madison is here."


def test_strip_phoneme_tags_is_noop_without_tags():
    text = "Plain text with no tags."
    assert server._strip_phoneme_tags(text) == text


# ── _segment_word_tokens ──────────────────────────────────────────────────────

def test_segment_word_tokens_strips_tags_before_tokenizing():
    segments = [
        {
            "id": "s1",
            "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
            "visual": "",
        },
    ]
    assert server._segment_word_tokens(segments) == [["The", "word", "Madison", "is", "here."]]


# ── _lockstep_segment_frames (pure unit, no API involved) ───────────────────

def test_lockstep_segment_frames_builds_correct_spans():
    words = [
        {"word": "Hello",   "startFrame": 0,  "endFrame": 10},
        {"word": "there.",  "startFrame": 11, "endFrame": 20},
        {"word": "This",    "startFrame": 21, "endFrame": 25},
        {"word": "is",      "startFrame": 26, "endFrame": 28},
        {"word": "segment", "startFrame": 29, "endFrame": 40},
        {"word": "two.",    "startFrame": 41, "endFrame": 50},
    ]
    segments = [
        {"id": "s1", "voice": "Hello there.", "visual": ""},
        {"id": "s2", "voice": "This is segment two.", "visual": ""},
    ]

    result = server._lockstep_segment_frames(segments, words)

    assert result == [
        {"id": "s1", "startFrame": 0, "endFrame": 20},
        {"id": "s2", "startFrame": 21, "endFrame": 50},
    ]


def test_lockstep_segment_frames_single_word_segment():
    words = [{"word": "Hi.", "startFrame": 0, "endFrame": 5}]
    segments = [{"id": "s1", "voice": "Hi.", "visual": ""}]

    result = server._lockstep_segment_frames(segments, words)

    assert result == [{"id": "s1", "startFrame": 0, "endFrame": 5}]


def test_lockstep_segment_frames_raises_on_token_count_mismatch():
    words = [{"word": "Hello", "startFrame": 0, "endFrame": 10}]
    segments = [{"id": "s1", "voice": "Hello there.", "visual": ""}]  # 2 tokens, 1 word

    with pytest.raises(ValueError):
        server._lockstep_segment_frames(segments, words)


def test_lockstep_segment_frames_raises_on_zero_word_segment():
    """A segment that tokenizes to zero words (e.g. a phoneme tag wrapping
    only whitespace) must raise a clean ValueError instead of an uncaught
    IndexError from indexing an empty word span."""
    words = [{"word": "Hello", "startFrame": 0, "endFrame": 10}]
    # Total token count (0 + 1) happens to equal len(words), so the earlier
    # total-count guard alone would not catch this — the zero-count check
    # inside the per-segment loop is what's actually exercised here.
    segments = [
        {"id": "s0", "voice": '<phoneme alphabet="cmu-arpabet" ph="X">  </phoneme>', "visual": ""},
        {"id": "s1", "voice": "Hello", "visual": ""},
    ]

    with pytest.raises(ValueError):
        server._lockstep_segment_frames(segments, words)


def test_lockstep_segment_frames_ignores_extra_internal_whitespace():
    """Multiple spaces inside a segment's voice text must not change its
    token count relative to how the flush loop tokenizes the alignment."""
    words = [
        {"word": "Hello", "startFrame": 0, "endFrame": 5},
        {"word": "there", "startFrame": 6, "endFrame": 10},
    ]
    segments = [{"id": "s1", "voice": "Hello   there", "visual": ""}]

    result = server._lockstep_segment_frames(segments, words)

    assert result == [{"id": "s1", "startFrame": 0, "endFrame": 10}]


def test_lockstep_segment_frames_strips_phoneme_tags_before_counting():
    """A <phoneme> tag's attributes contain spaces (e.g. ph="M AE1 D IH0 S
    AH0 N") — without stripping first, tokenizing on whitespace would shatter
    one tagged word into many spurious tokens. This is the TMDEV-26 phoneme-
    mode bug this refactor fixes."""
    words = [
        {"word": "The",                   "startFrame": 0,  "endFrame": 5},
        {"word": "word",                  "startFrame": 6,  "endFrame": 10},
        {"word": "@M@AE1@D@IH0@S@AH0@N",  "startFrame": 11, "endFrame": 20},
        {"word": "is",                    "startFrame": 21, "endFrame": 23},
        {"word": "here.",                 "startFrame": 24, "endFrame": 30},
    ]
    segments = [{
        "id": "s1",
        "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
        "visual": "",
    }]

    result = server._lockstep_segment_frames(segments, words)

    assert result == [{"id": "s1", "startFrame": 0, "endFrame": 30}]


# ── _join_segment_voice ──────────────────────────────────────────────────────

def test_join_segment_voice_matches_update_video_derivation():
    segments = [
        {"id": "s1", "voice": "  Hello there.  ", "visual": ""},
        {"id": "s2", "voice": "This is segment two.", "visual": ""},
    ]
    assert server._join_segment_voice(segments) == "Hello there. This is segment two."


# ── generate_voice: the model is the voice's own ───────────────────────────

def test_generate_voice_uses_the_voices_model(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_turbo_v2_5")
    job_db("vid_m1", script="Hello world.")

    result = server.generate_voice("vid_m1", "Hello world.")

    assert "error" not in result
    assert fake_httpx.last_payload["model_id"] == "eleven_turbo_v2_5"


def test_generate_voice_writes_where_every_reader_derives(job_db, voice_env, fake_httpx):
    """Agreement (TMDEV-162): the worker, validate_job and the API no longer read
    the stored paths; they derive them through tubematic_core.jobfiles. If this
    writer's names drifted from those, every voiced video would read as missing."""
    from tubematic_core import jobfiles
    job_db("vid_w1", script="Hello world.")

    result = server.generate_voice("vid_w1", "Hello world.")

    assert result["audio_path"] == str(jobfiles.job_file(server.JOBS_DIR, "vid_w1", jobfiles.AUDIO))
    assert result["timeline_path"] == str(
        jobfiles.job_file(server.JOBS_DIR, "vid_w1", jobfiles.TIMELINE))
    assert jobfiles.job_file(server.JOBS_DIR, "vid_w1", jobfiles.AUDIO).is_file()


def test_generate_voice_refuses_a_symlinked_audio_file_before_spend(job_db, voice_env,
                                                                   fake_httpx, tmp_path):
    job_db("vid_w2", script="Hello world.")
    (server.JOBS_DIR / "vid_w2").mkdir(parents=True)
    victim = tmp_path / "victim.bin"
    victim.write_bytes(b"keep")
    (server.JOBS_DIR / "vid_w2" / "audio.mp3").symlink_to(victim)

    result = server.generate_voice("vid_w2", "Hello world.")

    assert "symlink" in result["error"]
    assert fake_httpx.last_payload is None
    assert victim.read_bytes() == b"keep"


def test_generate_voice_default_voice_is_on_multilingual_v2(job_db, voice_env, fake_httpx):
    job_db("vid_m2", script="Hello world.")

    result = server.generate_voice("vid_m2", "Hello world.")

    assert "error" not in result
    assert fake_httpx.last_payload["model_id"] == "eleven_multilingual_v2"


# ── generate_voice: pronunciation lexicon + inline <respell> (TMDEV-26 ─────
# follow-up — replaced ElevenLabs pronunciation dictionaries entirely: alias
# rules did not audibly work on eleven_multilingual_v2, confirmed live. Both
# mechanisms below are mode-independent plain-text substitution, unlike
# <phoneme>, so they apply regardless of pronunciation_mode.

def test_generate_voice_applies_lexicon_substitution_to_spoken_text(job_db, voice_env, fake_httpx):
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah-gar"}])
    job_db("vid_lex1", script="ignored", script_segments=[
        {"id": "s1", "voice": "Only Vhagar could match Caraxes.", "visual": ""}
    ])

    result = server.generate_voice("vid_lex1", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "Only Vah-gar could match Caraxes."


def test_generate_voice_lexicon_substitution_is_whole_word_only(job_db, voice_env, fake_httpx):
    """A term must not match as a substring of a longer word — \\b-bounded,
    same semantics the old ElevenLabs alias rules used."""
    server.upsert_pronunciation_lexicon([{"term": "SYN", "respell": "S-Y-N"}])
    job_db("vid_lex2", script="ignored", script_segments=[
        {"id": "s1", "voice": "SYNergy is not SYN.", "visual": ""}
    ])

    result = server.generate_voice("vid_lex2", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "SYNergy is not S-Y-N."


def test_generate_voice_lexicon_leaves_captions_and_lockstep_at_original_spelling(job_db, voice_env, fake_httpx):
    """The lexicon substitution only ever touches tts_text — seg["voice"] is
    untouched, so captions and videos.script keep the original spelling for
    free, and the lockstep's authored-token-count check is unaffected (a
    lexicon entry's respell is enforced single-token at write time, so the
    substitution never changes the word count)."""
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah-gar"}])
    job_db("vid_lex3", script="ignored", script_segments=[
        {"id": "s1", "voice": "Vhagar flew fast.", "visual": ""}
    ])

    result = server.generate_voice("vid_lex3", "ignored")

    assert "error" not in result
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_lex3", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == ["Vhagar", "flew", "fast."]


def test_generate_voice_persists_the_substituted_tts_text(job_db, voice_env, fake_httpx):
    """VQA-6: videos.tts_text is the record of what was actually spoken, so
    the post-render AI review can check pronunciation against it. It must
    store the substituted form — re-deriving it later would re-read the
    install-wide lexicon, which can change between voicing and review."""
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah-gar"}])
    job_db("vid_tts1", script="ignored", script_segments=[
        {"id": "s1", "voice": 'Vhagar met <respell as="Kuh-rack-seez">Caraxes</respell>.',
         "visual": ""}
    ])

    result = server.generate_voice("vid_tts1", "ignored")

    assert "error" not in result
    with server._conn() as con:
        stored = con.execute("SELECT tts_text, script FROM videos WHERE id = 'vid_tts1'").fetchone()
    assert stored["tts_text"] == "Vah-gar met Kuh-rack-seez."
    assert stored["tts_text"] == fake_httpx.last_payload["text"]
    # The authored wording (what captions show) is a separate column and is
    # deliberately not overwritten by the spoken form.
    assert stored["script"] == "ignored"


def test_generate_voice_persists_tts_text_for_legacy_flat_scripts(job_db, voice_env, fake_httpx):
    job_db("vid_tts2", script="Hello [Show Card] world.")

    result = server.generate_voice("vid_tts2", "Hello [Show Card] world.")

    assert "error" not in result
    with server._conn() as con:
        stored = con.execute("SELECT tts_text FROM videos WHERE id = 'vid_tts2'").fetchone()
    assert stored["tts_text"] == "Hello world."


def test_init_db_adds_tts_text_column_to_an_old_db(tmp_path, monkeypatch):
    """Mirrors the same guard in renderer/api/pipeline.py's _init_db (the two
    copies are deliberately duplicated — separate processes)."""
    db_path = tmp_path / "no_tts.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE videos (
            id TEXT PRIMARY KEY, project_id TEXT, topic TEXT NOT NULL,
            strategy TEXT NOT NULL DEFAULT 'manual',
            producibility_score INTEGER NOT NULL DEFAULT 0,
            script TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL,
            author TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    con.execute(
        "INSERT INTO videos (id, topic, script, created_at, updated_at) "
        "VALUES ('vid_old', 'old topic', 'an old script', ?, ?)",
        (_now(), _now()),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()
    server._init_db()  # idempotent — the column-exists guard must hold

    with server._conn() as con:
        row = con.execute("SELECT script, tts_text FROM videos WHERE id = 'vid_old'").fetchone()
    assert row["tts_text"] == ""
    assert row["script"] == "an old script"


def test_generate_voice_no_lexicon_entries_is_a_no_op(job_db, voice_env, fake_httpx):
    job_db("vid_lex4", script="Hello world.")

    result = server.generate_voice("vid_lex4", "Hello world.")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "Hello world."


def test_generate_voice_respell_tag_substitutes_spoken_text_but_keeps_authored_caption(
    job_db, voice_env, fake_httpx
):
    segments = [{
        "id": "s1",
        "voice": 'Only <respell as="Vah-gar">Vhagar</respell> could match Caraxes.',
        "visual": "",
    }]
    job_db("vid_r1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_r1", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "Only Vah-gar could match Caraxes."
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_r1", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == ["Only", "Vhagar", "could", "match", "Caraxes."]


def test_generate_voice_inline_respell_overrides_lexicon_for_that_occurrence(job_db, voice_env, fake_httpx):
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vah-gar"}])
    segments = [{
        "id": "s1",
        "voice": 'Only <respell as="VAY-gar">Vhagar</respell> could match it.',
        "visual": "",
    }]
    job_db("vid_r2", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_r2", "ignored")

    assert "error" not in result
    # Inline tag wins — spoken text uses "VAY-gar", not the lexicon's "Vah-gar".
    assert fake_httpx.last_payload["text"] == "Only VAY-gar could match it."


def test_generate_voice_ignores_normalized_alignment_number_expansion_without_phoneme_tag(
    job_db, voice_env, monkeypatch
):
    """Regression: normalized_alignment reflects ElevenLabs' general text
    normalization (e.g. "33" -> "thirty three"), not just phoneme-tag
    collapsing — reading it unconditionally for any script_segments video
    would desync the segment/word lockstep on a plain script that happens to
    contain a number. generate_voice must only switch to normalized_alignment
    when tts_text actually contains a <phoneme> tag; a plain segment (even
    with a number) always reads plain `alignment` instead."""
    segments = [{"id": "s1", "voice": "There are 33 ways.", "visual": ""}]
    job_db("vid_n1", script="ignored", script_segments=segments)

    class _NumberExpansionClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            _FakeClient.last_payload = json
            text = json["text"]  # "There are 33 ways." — 4 tokens
            return _FakeResponse(200, {
                "audio_base64": base64.b64encode(b"fake-audio-bytes").decode(),
                "alignment": _char_alignment(text),
                # Simulates ElevenLabs expanding "33" -> "thirty three" (5
                # tokens instead of 4) — would break the lockstep if used.
                "normalized_alignment": _char_alignment("There are thirty three ways."),
            })

    import httpx
    monkeypatch.setattr(httpx, "Client", _NumberExpansionClient)

    result = server.generate_voice("vid_n1", "ignored")

    assert "error" not in result
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_n1", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == ["There", "are", "33", "ways."]


def test_generate_voice_refuses_phoneme_tags_on_a_respell_model_before_spend(job_db, voice_env, fake_httpx):
    """A voice's model can change after approval (Settings, or a direct status
    move past the checkpoint). Stripping the tag would voice the word as
    spelled on a paid request, so it is refused before any call instead."""
    segments = [{
        "id": "s1",
        "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
        "visual": "",
    }]
    job_db("vid_d1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_d1", "ignored")

    assert "<phoneme>" in result["error"]
    assert fake_httpx.last_payload is None


# ── generate_voice: phoneme mode ────────────────────────────────────────────

def test_generate_voice_phoneme_mode_preserves_tags_and_sets_ssml_parsing(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_turbo_v2")
    segments = [{
        "id": "s1",
        "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
        "visual": "",
    }]
    job_db("vid_p1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_p1", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["model_id"] == "eleven_turbo_v2"
    assert fake_httpx.last_payload["enable_ssml_parsing"] is True
    assert fake_httpx.last_payload["text"] == (
        'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.'
    )

    timeline = json.loads(server.JOBS_DIR.joinpath("vid_p1", "timeline.json").read_text())
    # Caption word text must be the authored word, not ElevenLabs' phonetic
    # rewrite of the tagged word (which is what normalized_alignment itself
    # would show without the override in generate_voice).
    assert [w["word"] for w in timeline["words"]] == ["The", "word", "Madison", "is", "here."]
    assert timeline["segments"] == [{"id": "s1", "startFrame": timeline["words"][0]["startFrame"],
                                      "endFrame": timeline["words"][-1]["endFrame"]}]


def test_generate_voice_records_the_credits_elevenlabs_reports(job_db, voice_env, fake_httpx):
    """Credits come from the `character-cost` header — the exact plan credits
    the call deducted, after the model's discount — never a local count, which
    strips markup ElevenLabs does bill and ignores the Flash/Turbo half rate."""
    _set_install_model("eleven_turbo_v2")
    segments = [{
        "id": "s1",
        "voice": '<phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme>',
        "visual": "",
    }]
    job_db("vid_c1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_c1", "ignored")

    assert "error" not in result
    assert result["credits"] == 42
    [event] = _voice_events("vid_c1")
    assert event["model"] == "eleven_turbo_v2"
    assert event["operation"] == "voice"
    assert event["cost_basis"] == "credits" and event["cost_usd"] is None
    assert event["estimated"] == 0
    assert event["request_id"] == "req-fake"


# ── generate_voice: segmented script → tts_text + timeline.segments ────────

def test_generate_voice_uses_segment_join_as_tts_text_no_regex_cleanup(job_db, voice_env, fake_httpx):
    segments = [
        {"id": "s1", "voice": "Hello there.", "visual": "[Show intro card]"},
        {"id": "s2", "voice": "This is segment two.", "visual": ""},
    ]
    job_db("vid_4", script="Hello there. This is segment two.", script_segments=segments)

    # The script argument is ignored when segments are present — pass junk
    # to prove it has no effect on the outgoing text.
    result = server.generate_voice("vid_4", "ignored legacy arg [Should Not Appear] —")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "Hello there. This is segment two."

    timeline = json.loads(server.JOBS_DIR.joinpath("vid_4", "timeline.json").read_text())
    assert [s["id"] for s in timeline["segments"]] == ["s1", "s2"]
    assert timeline["segments"][0]["startFrame"] == timeline["words"][0]["startFrame"]
    assert timeline["segments"][0]["endFrame"] == timeline["words"][1]["endFrame"]
    assert timeline["segments"][1]["startFrame"] == timeline["words"][2]["startFrame"]
    assert timeline["segments"][1]["endFrame"] == timeline["words"][-1]["endFrame"]


def test_generate_voice_returns_error_and_writes_no_files_on_segment_word_mismatch(job_db, voice_env, monkeypatch):
    """If ElevenLabs' alignment doesn't reconcile with segment token counts,
    generate_voice must fail loudly and not leave partial files behind."""
    segments = [{"id": "s1", "voice": "Hello there.", "visual": ""}]  # 2 tokens
    job_db("vid_5", script="Hello there.", script_segments=segments)

    class _MismatchClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            # Alignment for a single word only, but the segment tokenizes to two.
            return _FakeResponse(200, {
                "audio_base64": base64.b64encode(b"x").decode(),
                "alignment": _char_alignment("Hello"),
                "normalized_alignment": _char_alignment("Hello"),
            })

    import httpx
    monkeypatch.setattr(httpx, "Client", _MismatchClient)

    result = server.generate_voice("vid_5", "Hello there.")

    assert "error" in result
    job_dir = server.JOBS_DIR / "vid_5"
    assert not (job_dir / "audio.mp3").exists()
    assert not (job_dir / "timeline.json").exists()

    # ElevenLabs was already charged for this call — the spend must still be
    # recorded even though the integrity check rejected the result.
    assert _voice_credits("vid_5") > 0


# ── generate_voice: legacy flat-script fallback unchanged ───────────────────

def test_generate_voice_legacy_flat_script_regex_cleanup_unchanged(job_db, voice_env, fake_httpx):
    job_db("vid_6", script="[Show Card] Hello — world.")

    result = server.generate_voice("vid_6", "[Show Card] Hello — world.")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "Hello world."

    timeline = json.loads(server.JOBS_DIR.joinpath("vid_6", "timeline.json").read_text())
    assert "segments" not in timeline


def test_generate_voice_missing_video_returns_error(job_db, voice_env, fake_httpx):
    result = server.generate_voice("nonexistent", "Hello world.")
    assert "error" in result


# ── generate_voice: per-video voice_id (TMDEV-51) ───────────────────────────

def test_generate_voice_uses_video_voice_id_over_default(job_db, voice_env, fake_httpx):
    server._set_setting("elevenlabs_voices", '[{"name": "A", "voice_id": "voice_a", "model_id": "eleven_multilingual_v2"}]')
    job_db("vid_voice_pick", script="Hello world.", voice_id="voice_a")

    result = server.generate_voice("vid_voice_pick", "Hello world.")

    assert "error" not in result
    assert fake_httpx.last_payload is not None
    with server._conn() as con:
        row = con.execute(
            "SELECT voice_id FROM videos WHERE id = ?", ("vid_voice_pick",)
        ).fetchone()
    # video's own voice_id is unaffected by generate_voice (it only writes
    # audio/timeline paths) — the ElevenLabs URL itself carried voice_a.
    assert row["voice_id"] == "voice_a"


def test_generate_voice_falls_back_to_install_default_when_video_voice_id_blank(
    job_db, voice_env, fake_httpx
):
    job_db("vid_no_voice", script="Hello world.")  # voice_id defaults to ""

    result = server.generate_voice("vid_no_voice", "Hello world.")

    assert "error" not in result


def test_generate_voice_errors_when_no_voice_id_anywhere(job_db, monkeypatch, tmp_path):
    """No video voice_id and no settings.elevenlabs_voice_id — there is no
    .env fallback to reach for (TMDEV-51 follow-up), so this must fail
    before any ElevenLabs request rather than silently pick something."""
    monkeypatch.setattr(server, "_elevenlabs_key", lambda: "test-api-key")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    job_db("vid_no_default", script="Hello world.")  # voice_id defaults to ""
    # settings.elevenlabs_voice_id left unset entirely.

    result = server.generate_voice("vid_no_default", "Hello world.")

    assert "error" in result


def test_generate_voice_errors_before_spend_when_video_voice_id_removed_from_roster(
    job_db, voice_env, fake_httpx
):
    """A video's voice_id can go stale if the voice was deleted from the
    roster after being assigned — must error before any ElevenLabs request,
    never silently fall back to the default (that would spend against a
    voice nobody chose)."""
    job_db("vid_stale_voice", script="Hello world.", voice_id="deleted_voice")
    # elevenlabs_voices left empty/unset — the video's voice_id names nothing.

    result = server.generate_voice("vid_stale_voice", "Hello world.")

    assert "error" in result
    assert fake_httpx.last_payload is None
    assert _voice_events("vid_stale_voice") == []


# ── generate_voice: concurrent-call claim (code review finding #1) ─────────

def test_try_claim_voicing_is_mutually_exclusive():
    """Pure unit test of the claim primitive itself, independent of any
    threading/HTTP plumbing."""
    assert server._try_claim_voicing("vid_claim_1") is True
    assert server._try_claim_voicing("vid_claim_1") is False  # already claimed
    server._release_voicing_claim("vid_claim_1")
    assert server._try_claim_voicing("vid_claim_1") is True  # free again
    server._release_voicing_claim("vid_claim_1")


def test_generate_voice_concurrent_calls_only_one_charges_elevenlabs(job_db, voice_env, monkeypatch):
    """The VOICING-status precondition alone is a plain read, not an atomic
    claim — two concurrent generate_voice calls for the same video could
    both pass it before either has written anything, and both charge
    ElevenLabs. Proves the fix: a second call arriving while the first is
    still genuinely in flight (mid ElevenLabs request, status still
    "VOICING" in the DB) is rejected before ever reaching ElevenLabs."""
    import threading
    import httpx as httpx_module

    job_db("vid_concurrent", script="Hello world.")

    call_count = {"n": 0}
    thread1_in_flight = threading.Event()
    release_thread1 = threading.Event()

    class _SlowFakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            call_count["n"] += 1
            # Signal the test that this call has genuinely started (claimed
            # the video and is now "talking to ElevenLabs"), then hold here
            # until the test releases it — widens the race window so a
            # second concurrent call's claim attempt happens while the
            # video's DB status is still "VOICING" (unchanged so far).
            thread1_in_flight.set()
            assert release_thread1.wait(timeout=5), "test never released thread1"
            text = json["text"]
            return _FakeResponse(200, {
                "audio_base64": base64.b64encode(b"fake-audio-bytes").decode(),
                "alignment": _char_alignment(text),
            })

    monkeypatch.setattr(httpx_module, "Client", _SlowFakeClient)

    results = {}

    def _call1():
        results["t1"] = server.generate_voice("vid_concurrent", "Hello world.")

    t1 = threading.Thread(target=_call1)
    t1.start()
    assert thread1_in_flight.wait(timeout=5), "thread1 never reached the (blocked) ElevenLabs call"

    # thread1 has claimed vid_concurrent and is blocked mid-flight; the video's
    # status is still "VOICING" in the DB. A second concurrent call must be
    # rejected by the claim itself, not by the (not-yet-changed) status check.
    result2 = server.generate_voice("vid_concurrent", "Hello world.")

    release_thread1.set()
    t1.join(timeout=5)

    assert "error" not in results["t1"]
    assert result2["error"] == "status_mismatch"
    assert "already in progress" in result2["detail"]
    assert call_count["n"] == 1  # ElevenLabs was only ever actually called once

    assert len(_voice_events("vid_concurrent")) == 1  # billed exactly once
    assert _voice_credits("vid_concurrent") == results["t1"]["credits"]


# ── generate_voice: TMDEV-30 status precondition + ssml/model guards ───────

def test_generate_voice_rejects_when_not_voicing(job_db, voice_env, fake_httpx):
    """No ElevenLabs request — and no charge — for a video that isn't
    currently VOICING, e.g. a double-invocation on an already-advanced
    video."""
    job_db("vid_precond", script="Hello world.", status="VOICE_READY")

    result = server.generate_voice("vid_precond", "Hello world.")

    assert result["error"] == "status_mismatch"
    assert fake_httpx.last_payload is None
    assert _voice_events("vid_precond") == []


def test_generate_voice_derives_phoneme_mode_purely_from_model(job_db, voice_env, fake_httpx):
    """pronunciation_mode is not an independent setting (TMDEV-26 second
    follow-up) — it's derived from elevenlabs_model_id alone, so it's
    impossible for it to disagree with the model. No pronunciation_mode row
    is ever set here; a phoneme-compatible model is enough."""
    _set_install_model("eleven_turbo_v2")
    segments = [{
        "id": "s1",
        "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
        "visual": "",
    }]
    job_db("vid_derive", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_derive", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["enable_ssml_parsing"] is True
    assert fake_httpx.last_payload["text"] == (
        'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.'
    )


def test_generate_voice_ssml_parsing_off_for_legacy_script_even_in_phoneme_mode(job_db, voice_env, fake_httpx):
    """A legacy flat-script video (no segments, so tts_text never contains a
    <phoneme> tag) must not get enable_ssml_parsing turned on just because
    the derived mode happens to be 'phoneme' — gated on actual tag
    presence, not on mode."""
    _set_install_model("eleven_turbo_v2")
    job_db("vid_legacy_phoneme", script="Hello world.")

    result = server.generate_voice("vid_legacy_phoneme", "Hello world.")

    assert "error" not in result
    assert "enable_ssml_parsing" not in fake_httpx.last_payload


def test_generate_voice_final_status_noop_surfaces_warning(job_db, voice_env, fake_httpx, monkeypatch):
    """If the video's status changes out from under generate_voice between
    the top-of-function precondition check and the final guarded status
    update, audio/timeline are still written and cost still recorded, but a
    warning must be surfaced instead of silently reporting plain success."""
    job_db("vid_race", script="Hello world.")

    real_set_status = server._set_status

    def _flip_then_call(video_id, new_status, only_if=None):
        # Simulate another actor moving the video on right before the final
        # guarded update fires.
        with server._conn() as con:
            con.execute("UPDATE videos SET status = 'TOPIC_REJECTED' WHERE id = ?", (video_id,))
        return real_set_status(video_id, new_status, only_if=only_if)

    monkeypatch.setattr(server, "_set_status", _flip_then_call)

    result = server.generate_voice("vid_race", "Hello world.")

    assert "error" not in result
    assert "warning" in result
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_race",)).fetchone()
    assert row["status"] == "TOPIC_REJECTED"


# ── TMDEV-26: pause markup (<break/> and eleven_v3 [pause] audio tags) ───────

def test_strip_pause_markup_removes_break_and_collapses_whitespace():
    text = 'Here is the catch. <break time="0.6s" /> It never verifies.'
    assert server._strip_pause_markup(text) == "Here is the catch. It never verifies."


def test_strip_pause_markup_removes_all_three_v3_tags():
    for tag in ("[pause]", "[short pause]", "[long pause]"):
        assert server._strip_pause_markup(f"Wait. {tag} Go.") == "Wait. Go."


def test_strip_pause_markup_is_noop_without_markup():
    assert server._strip_pause_markup("Plain prose here.") == "Plain prose here."


def test_strip_non_spoken_removes_both_markup_kinds():
    text = ('The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> '
            'matters. <break time="0.6s" /> Truly.')
    assert server._strip_non_spoken(text) == "The word Madison matters. Truly."


def test_generate_voice_break_tag_sent_verbatim_without_ssml_parsing(job_db, voice_env, fake_httpx):
    """A live probe confirmed break tags are honored with enable_ssml_parsing
    absent — so the flag must NOT be turned on for them. Turning it on would
    reinterpret bare & and < in ordinary prose as markup, for the default
    dictionary-mode configuration."""
    segments = [{"id": "s1", "voice": 'Here is the catch. <break time="0.6s" /> It never verifies.',
                 "visual": ""}]
    job_db("vid_b1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_b1", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == (
        'Here is the catch. <break time="0.6s" /> It never verifies.'
    )
    assert "enable_ssml_parsing" not in fake_httpx.last_payload


def test_generate_voice_break_tag_excluded_from_timeline_words(job_db, voice_env, fake_httpx):
    """Markup must not become caption words, and the silence it produces
    should survive as a gap between the surrounding words' frame spans."""
    segments = [{"id": "s1", "voice": 'Here is the catch. <break time="0.6s" /> It never verifies.',
                 "visual": ""}]
    job_db("vid_b2", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_b2", "ignored")

    assert "error" not in result
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_b2", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == [
        "Here", "is", "the", "catch.", "It", "never", "verifies.",
    ]
    catch = next(w for w in timeline["words"] if w["word"] == "catch.")
    it = next(w for w in timeline["words"] if w["word"] == "It")
    assert it["startFrame"] > catch["endFrame"], "break should leave a caption gap"


def test_generate_voice_without_the_header_falls_back_to_an_estimate(
    job_db, voice_env, monkeypatch
):
    """A 200 with no `character-cost` header is still recorded — from the local
    spoken-character count, marked estimated, so it is never a silent gap."""
    import httpx

    class _NoHeaderClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            resp = super().post(url, json=json, headers=headers)
            resp.headers = {}
            return resp
    monkeypatch.setattr(httpx, "Client", _NoHeaderClient)
    segments = [{"id": "s1", "voice": 'Madison <break time="1.0s" /> matters.', "visual": ""}]
    job_db("vid_b3", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_b3", "ignored")

    assert "error" not in result
    assert result["credits"] == len("Madison matters.")
    [event] = _voice_events("vid_b3")
    assert event["estimated"] == 1


def test_generate_voice_records_credits_for_a_200_it_cannot_use(job_db, voice_env, monkeypatch):
    """A 200 whose body has no audio was still charged. It used to raise out of
    the tool before the cost was written; now the credits land first."""
    import httpx

    class _NoAudioClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            return _FakeResponse(200, {"alignment": {}}, headers={"character-cost": "17"})
    monkeypatch.setattr(httpx, "Client", _NoAudioClient)
    job_db("vid_noaudio", script="Hello world.")

    result = server.generate_voice("vid_noaudio", "Hello world.")

    assert "error" in result
    assert _voice_credits("vid_noaudio") == 17


def test_generate_voice_records_nothing_for_a_non_200(job_db, voice_env, monkeypatch):
    import httpx

    class _RejectingClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            return _FakeResponse(401, {}, text="invalid_api_key")
    monkeypatch.setattr(httpx, "Client", _RejectingClient)
    job_db("vid_401", script="Hello world.")

    assert "error" in server.generate_voice("vid_401", "Hello world.")
    assert _voice_events("vid_401") == []


def test_generate_voice_break_tag_keeps_segment_lockstep(job_db, voice_env, fake_httpx):
    segments = [
        {"id": "s1", "voice": 'Here is the catch. <break time="0.6s" /> It never verifies.', "visual": ""},
        {"id": "s2", "voice": "That is the whole trick.", "visual": ""},
    ]
    job_db("vid_b4", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_b4", "ignored")

    assert "error" not in result
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_b4", "timeline.json").read_text())
    assert [s["id"] for s in timeline["segments"]] == ["s1", "s2"]
    assert len(timeline["words"]) == 12  # 7 + 5, markup contributing none


def test_generate_voice_v3_pause_tag_excluded_from_timeline_words(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_v3")
    segments = [{"id": "s1", "voice": "Here is the catch. [long pause] It never verifies.",
                 "visual": ""}]
    job_db("vid_v1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_v1", "ignored")

    assert "error" not in result
    # Sent verbatim — the tag is an instruction to eleven_v3, not caption text.
    assert "[long pause]" in fake_httpx.last_payload["text"]
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_v1", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == [
        "Here", "is", "the", "catch.", "It", "never", "verifies.",
    ]


def test_generate_voice_rejects_break_tag_on_eleven_v3(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_v3")
    segments = [{"id": "s1", "voice": 'Wait. <break time="0.6s" /> Go.', "visual": ""}]
    job_db("vid_x1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_x1", "ignored")

    assert "error" in result
    assert "<break/>" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


def test_generate_voice_rejects_v3_pause_tag_on_non_v3_model(job_db, voice_env, fake_httpx):
    segments = [{"id": "s1", "voice": "Wait. [pause] Go.", "visual": ""}]
    job_db("vid_x2", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_x2", "ignored")

    assert "error" in result
    assert "eleven_v3" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


def test_generate_voice_break_plus_phoneme_drops_normalized_marker_token(job_db, voice_env, fake_httpx):
    """Phoneme mode reads normalized_alignment, where a <break/> shows up as a
    lone '.' token rather than verbatim markup — the character-index skip
    can't see it, so the marker-drop path has to."""
    _set_install_model("eleven_turbo_v2")
    segments = [{
        "id": "s1",
        "voice": ('The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> '
                  'matters. <break time="0.6s" /> Truly.'),
        "visual": "",
    }]
    job_db("vid_bp1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_bp1", "ignored")

    assert "error" not in result
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_bp1", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == [
        "The", "word", "Madison", "matters.", "Truly.",
    ]


def test_generate_voice_number_expansion_gate_still_narrow_with_break_tag(job_db, voice_env, fake_httpx):
    """Regression guard for commit 132c2e9's hazard, now reachable via breaks.

    A break tag must NOT push a dictionary-mode script onto
    normalized_alignment, because that field also spells out numbers and would
    expand one authored token into several. Fails against a gate naively
    widened to `"<phoneme" in tts_text or "<break" in tts_text`.
    """
    def _expanding_normalize(text):
        return _fake_normalize(text).replace("2026", "twenty twenty six")

    class _NumberClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            _FakeClient.last_payload = json
            text = json["text"]
            return _FakeResponse(200, {
                "audio_base64": base64.b64encode(b"fake-audio-bytes").decode(),
                "alignment": _char_alignment(text),
                "normalized_alignment": _char_alignment(_expanding_normalize(text)),
            })

    import httpx
    httpx.Client = _NumberClient

    segments = [{"id": "s1", "voice": 'It shipped in 2026. <break time="0.6s" /> Nobody noticed.',
                 "visual": ""}]
    job_db("vid_n1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_n1", "ignored")

    assert "error" not in result
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_n1", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == [
        "It", "shipped", "in", "2026.", "Nobody", "noticed.",
    ]


def test_generate_voice_empty_normalized_alignment_reports_real_mismatch(job_db, voice_env, fake_httpx):
    """If normalized_alignment comes back empty we fall back to plain
    alignment, so the break-marker drop must not run — otherwise it hunts for
    '.' tokens that were never there and reports a misleading marker-count
    error instead of the real segment/word mismatch."""
    class _NoNormalizedClient(_FakeClient):
        def post(self, url, json=None, headers=None):
            _FakeClient.last_payload = json
            text = json["text"]
            return _FakeResponse(200, {
                "audio_base64": base64.b64encode(b"fake-audio-bytes").decode(),
                "alignment": _char_alignment(text),
                "normalized_alignment": None,
            })

    import httpx
    httpx.Client = _NoNormalizedClient

    _set_install_model("eleven_turbo_v2")
    segments = [{
        "id": "s1",
        "voice": ('The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> '
                  'matters. <break time="0.6s" /> Truly.'),
        "visual": "",
    }]
    job_db("vid_nn1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_nn1", "ignored")

    assert "error" in result
    assert "Segment/word count mismatch" in result["error"]
    assert "marker token" not in result["error"]


# ── TMDEV-122: which models get phoneme tags, and markup values ─────────────

def test_phoneme_models_are_the_two_probed_to_apply_the_tag():
    """Probed live with speech-to-text: "Madison" tagged with the phonemes for
    "tomato" is spoken "tomato" on exactly these two. The 2.5 models EAT the
    tagged word, so adding them "for completeness" deletes words from audio."""
    assert server.PHONEME_COMPATIBLE_MODELS == {"eleven_flash_v2", "eleven_turbo_v2"}
    assert server.PHONEME_COMPATIBLE_MODELS <= server.DICTIONARY_COMPATIBLE_MODELS


def test_eleven_english_v1_is_not_offered():
    """ElevenLabs answers 400 model_not_found for it — offering it means every
    voicing on that install fails."""
    assert "eleven_english_v1" not in server.DICTIONARY_COMPATIBLE_MODELS


def test_break_tags_are_every_model_except_v3_and_v4():
    """ElevenLabs: v3 and v4 do not support SSML break tags; every other model
    does. Kept independent of the phoneme set on purpose — see
    docs/developer/08-scripting-and-voice.md."""
    assert "eleven_v3" not in server.BREAK_TAG_COMPATIBLE_MODELS
    assert "eleven_v4" not in server.BREAK_TAG_COMPATIBLE_MODELS
    assert server.BREAK_TAG_COMPATIBLE_MODELS == (
        server.DICTIONARY_COMPATIBLE_MODELS - {"eleven_v3", "eleven_v4"})


@pytest.mark.parametrize("model", ["eleven_flash_v2_5", "eleven_turbo_v2_5"])
def test_generate_voice_sends_nothing_to_models_that_eat_the_word(
        job_db, voice_env, fake_httpx, model):
    _set_install_model(model)
    segments = [{
        "id": "s1",
        "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
        "visual": "",
    }]
    job_db("vid_eat", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_eat", "ignored")

    assert "<phoneme>" in result["error"]
    assert fake_httpx.last_payload is None


def test_generate_voice_rejects_unknown_alphabet_before_spend(job_db, voice_env, fake_httpx):
    """A script stored before the check existed still has to be caught here."""
    _set_install_model("eleven_flash_v2")
    segments = [{"id": "s1", "voice": 'The <phoneme alphabet="klingon" ph="X">word</phoneme> here.',
                 "visual": ""}]
    job_db("vid_ab1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_ab1", "ignored")

    assert "alphabet" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


def test_generate_voice_rejects_break_over_three_seconds_before_spend(job_db, voice_env, fake_httpx):
    segments = [{"id": "s1", "voice": 'Wait. <break time="4s" /> Go.', "visual": ""}]
    job_db("vid_ab2", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_ab2", "ignored")

    assert "break" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


@pytest.mark.parametrize("voice", [
    'The <phoneme data-alphabet="cmu-arpabet" ph="X">word</phoneme> here.',
    'The <phoneme alphabet="ipa" alphabet="klingon" ph="X">word</phoneme> here.',
    'Wait. <break note=\'time="1s"\' /> Go.',
    'Wait. <break data-time="1s" /> Go.',
])
def test_generate_voice_rejects_pseudo_attributes_before_spend(job_db, voice_env, fake_httpx, voice):
    """A prefixed or nested `alphabet=`/`time=` is not the real attribute —
    ElevenLabs would see a tag without one."""
    _set_install_model("eleven_flash_v2")
    job_db("vid_ab3", script="ignored", script_segments=[{"id": "s1", "voice": voice, "visual": ""}])

    result = server.generate_voice("vid_ab3", "ignored")

    assert "error" in result
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


# ── generate_voice: inline <ipa> tags on eleven_v3 ───────────────────────────

def test_generate_voice_ipa_tag_is_sent_as_slash_ipa_but_captions_keep_the_word(
    job_db, voice_env, fake_httpx
):
    """ElevenLabs' documented v3 syntax is the IPA between slashes, inside
    double quotes. A live probe showed v3's alignment mirrors that text
    exactly, one whitespace token per quoted span, so the lockstep holds and
    the caption word is restored from the authored text."""
    _set_install_model("eleven_v3")
    segments = [{"id": "s1", "voice": 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa>, could match it.',
                 "visual": ""}]
    job_db("vid_ipa1", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_ipa1", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == 'Only "/vɑːˈɡɑːr/", could match it.'
    assert "enable_ssml_parsing" not in fake_httpx.last_payload
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_ipa1", "timeline.json").read_text())
    assert [w["word"] for w in timeline["words"]] == ["Only", "Vhagar,", "could", "match", "it."]
    with server._conn() as con:
        row = con.execute("SELECT tts_text FROM videos WHERE id = ?", ("vid_ipa1",)).fetchone()
    assert row["tts_text"] == 'Only "/vɑːˈɡɑːr/", could match it.'


def test_generate_voice_on_v4_sends_ipa_and_pause_tags_and_keeps_the_caption_words(
    job_db, voice_env, fake_httpx
):
    """eleven_v4 takes v3's markup (TMDEV-172). Probed live: its alignment
    mirrors "/ph/" and [pause] tags verbatim and, unlike v3, the pause tag's
    own characters span the silence — the fake alignment gives every
    character a duration too, so the word after the tag must start after it."""
    _set_install_model("eleven_v4")
    segments = [{"id": "s1", "visual": "",
                 "voice": 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could. [long pause] Then silence.'}]
    job_db("vid_v4", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_v4", "ignored")

    assert "error" not in result
    sent = fake_httpx.last_payload["text"]
    assert sent == 'Only "/vɑːˈɡɑːr/" could. [long pause] Then silence.'
    assert fake_httpx.last_payload["model_id"] == "eleven_v4"
    assert "enable_ssml_parsing" not in fake_httpx.last_payload
    timeline = json.loads(server.JOBS_DIR.joinpath("vid_v4", "timeline.json").read_text())
    words = timeline["words"]
    assert [w["word"] for w in words] == ["Only", "Vhagar", "could.", "Then", "silence."]
    pause_end = (sent.index("[long pause]") + len("[long pause]")) * 0.05
    assert words[3]["startFrame"] >= round(pause_end * server.FPS)


def test_generate_voice_rejects_break_tag_on_eleven_v4(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_v4")
    segments = [{"id": "s1", "voice": 'First. <break time="0.6s" /> Second.', "visual": ""}]
    job_db("vid_v4b", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_v4b", "ignored")

    assert "<break/>" in result["error"]
    assert fake_httpx.last_payload is None


def test_generate_voice_refuses_ipa_before_spend_when_the_model_is_no_longer_v3(
    job_db, voice_env, fake_httpx
):
    """The model is install-wide and can change between authoring and voicing."""
    _set_install_model("eleven_multilingual_v2")
    segments = [{"id": "s1", "voice": 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.',
                 "visual": ""}]
    job_db("vid_ipa2", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_ipa2", "ignored")

    assert "eleven_v3" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


def test_generate_voice_ipa_tag_wins_over_the_lexicon(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_v3")
    server.upsert_pronunciation_lexicon([{"term": "Vhagar", "respell": "Vaygar"}])
    segments = [{"id": "s1", "voice": 'Vhagar and <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> differ.',
                 "visual": ""}]
    job_db("vid_ipa3", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_ipa3", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == 'Vaygar and "/vɑːˈɡɑːr/" differ.'


def test_generate_voice_respell_and_lexicon_still_work_on_v3(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_v3")
    server.upsert_pronunciation_lexicon([{"term": "SYN", "respell": "S-Y-N"}])
    segments = [{"id": "s1", "voice": 'A SYN hit <respell as="Vaygar">Vhagar</respell>.',
                 "visual": ""}]
    job_db("vid_ipa4", script="ignored", script_segments=segments)

    result = server.generate_voice("vid_ipa4", "ignored")

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == "A S-Y-N hit Vaygar."


def test_generate_voice_refuses_ipa_in_a_legacy_flat_script_on_another_model(job_db, voice_env, fake_httpx):
    """The flat-script path must not quietly strip the tag and charge for a
    voicing that ignores the pronunciation — same refusal as the segment path."""
    job_db("vid_ipa5", script='Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.')

    result = server.generate_voice("vid_ipa5", 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.')

    assert "eleven_v3" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


def test_generate_voice_legacy_flat_script_sends_ipa_on_v3(job_db, voice_env, fake_httpx):
    _set_install_model("eleven_v3")
    job_db("vid_ipa6", script="ignored")

    result = server.generate_voice("vid_ipa6", 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.')

    assert "error" not in result
    assert fake_httpx.last_payload["text"] == 'Only "/vɑːˈɡɑːr/" could match it.'


@pytest.mark.parametrize("script", [
    "Only Vhagar</ipa> could match it.",                          # closer, no opener
    'Only <ipa ph="vɑː ˈɡɑːr">Vhagar</ipa> could match it.',      # malformed on v3
])
def test_generate_voice_legacy_flat_script_validates_ipa_before_spend(job_db, voice_env, fake_httpx, script):
    """The flat path has no update_video in front of it, so the tag syntax is
    checked here — otherwise stray or malformed IPA markup is voiced and billed."""
    _set_install_model("eleven_v3")
    job_db("vid_ipa7", script=script)

    result = server.generate_voice("vid_ipa7", script)

    assert "ipa" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


def test_generate_voice_legacy_flat_script_checks_ipa_before_respell_can_hide_it(
    job_db, voice_env, fake_httpx
):
    """A <respell> wrapping an <ipa> replaces the whole thing, so checking IPA
    after _apply_respell would never see the tag — and would voice, and bill,
    on a model that cannot use it."""
    script = 'Only <respell as="Vaygar"><ipa ph="vɑːˈɡɑːr">Vhagar</ipa></respell> could.'
    job_db("vid_ipa8", script=script)

    result = server.generate_voice("vid_ipa8", script)

    assert "eleven_v3" in result["error"]
    assert fake_httpx.last_payload is None, "must fail before any ElevenLabs spend"


# ── Failures reach the log (TMDEV-126) ────────────────────────────────────────

def _stub_voice_post(monkeypatch, outcome):
    import httpx

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(httpx, "Client", _Client)


def test_an_elevenlabs_error_status_is_one_error_line(job_db, voice_env, monkeypatch, through_mcp):
    job_db("vid_f1", script="Hello world.")
    _stub_voice_post(monkeypatch, _FakeResponse(401, {}, text='{"detail": {"status": "quota_exceeded"}}'))
    out, (rec,) = through_mcp("generate_voice", video_id="vid_f1", script="Hello world.")
    assert out == {"error": 'ElevenLabs 401: {"detail": {"status": "quota_exceeded"}}'}
    assert (rec.levelname, rec.outcome) == ("ERROR", "error")
    assert (rec.provider_service, rec.provider_status, rec.provider_model,
            rec.provider_operation) == ("elevenlabs", 401, "eleven_multilingual_v2", "voice")
    assert rec.video_id == "vid_f1"


def test_an_elevenlabs_request_that_never_got_a_response_is_logged(job_db, voice_env, monkeypatch,
                                                                  through_mcp):
    import httpx
    job_db("vid_f2", script="Hello world.")
    _stub_voice_post(monkeypatch, httpx.ReadTimeout("timed out"))
    out, (rec,) = through_mcp("generate_voice", video_id="vid_f2", script="Hello world.")
    assert out == {"error": "ElevenLabs request failed: timed out"}
    assert rec.levelname == "ERROR"
    assert rec.provider_status is None
    assert "ReadTimeout" in rec.provider_body


def test_an_unusable_elevenlabs_200_is_logged(job_db, voice_env, monkeypatch, through_mcp):
    job_db("vid_f3", script="Hello world.")
    _stub_voice_post(monkeypatch, _FakeResponse(200, {"no_audio": True},
                                                headers={"character-cost": "12"}))
    out, (rec,) = through_mcp("generate_voice", video_id="vid_f3", script="Hello world.")
    assert out["error"].startswith("ElevenLabs returned an unusable response")
    assert (rec.levelname, rec.provider_status) == ("ERROR", 200)


def test_a_billed_reply_whose_break_markers_do_not_add_up_is_a_provider_failure(
        job_db, voice_env, monkeypatch, fake_httpx, through_mcp):
    """ElevenLabs charged for a 200 whose alignment cannot be trusted — a paid
    failure, so it is an `error`, not a refusal-grade warning."""
    import sys
    # This normalizer drops the break marker instead of rendering it as '.'.
    monkeypatch.setattr(sys.modules[__name__], "_fake_normalize",
                        lambda text: re.sub(r'<break\b[^>]*>', "",
                                            _FAKE_PHONEME_TAG_RE.sub("@x", text)))
    _set_install_model("eleven_turbo_v2")
    job_db("vid_f4", script="ignored", script_segments=[{
        "id": "s1",
        "voice": ('The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> '
                  'matters. <break time="0.6s" /> Truly.'),
        "visual": "",
    }])
    out, (rec,) = through_mcp("generate_voice", video_id="vid_f4", script="ignored")
    assert "break-tag marker" in out["error"]
    assert (rec.levelname, rec.provider_status) == ("ERROR", 200)
    assert "break-tag marker" in rec.provider_body


def test_a_billed_reply_that_breaks_the_segment_lockstep_is_a_provider_failure(
        job_db, voice_env, monkeypatch, fake_httpx, through_mcp):
    def mismatch(segments, words):
        raise ValueError("segment s1 expects 5 words but the alignment has 4")

    monkeypatch.setattr(server, "_lockstep_segment_frames", mismatch)
    job_db("vid_f5", script="ignored", script_segments=[
        {"id": "s1", "voice": "Only Vhagar could match Caraxes.", "visual": ""}])
    out, (rec,) = through_mcp("generate_voice", video_id="vid_f5", script="ignored")
    assert out == {"error": "segment s1 expects 5 words but the alignment has 4"}
    assert (rec.levelname, rec.provider_status) == ("ERROR", 200)
    assert "expects 5 words" in rec.provider_body
    assert "audio_base64" not in rec.provider_body  # the reply is mostly audio; keep it out


def test_generate_voice_refuses_a_job_dir_linked_to_another_video(job_db, voice_env,
                                                                  fake_httpx):
    """vid_w3 -> vid_w4 stays inside the jobs directory, so only the
    per-component symlink walk stops A's voice overwriting B's."""
    job_db("vid_w3", script="Hello world.")
    (server.JOBS_DIR / "vid_w4").mkdir(parents=True)
    (server.JOBS_DIR / "vid_w4" / "audio.mp3").write_bytes(b"B")
    (server.JOBS_DIR / "vid_w3").symlink_to(server.JOBS_DIR / "vid_w4")

    result = server.generate_voice("vid_w3", "Hello world.")

    assert "symlink" in result["error"]
    assert fake_httpx.last_payload is None
    assert (server.JOBS_DIR / "vid_w4" / "audio.mp3").read_bytes() == b"B"
