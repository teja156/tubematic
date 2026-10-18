"""Tests for the TMDEV-2 script-segments data model: the videos.script_segments
migration, and the update_video/get_video segment support built on top of it.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

import server

# Every script write carries the publish metadata (TMDEV-132); these tests
# are about the script, so one fixed pair serves them all.
PUBLISH = {"publish_title": "A title", "publish_description": "A description."}


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
    """Point DB_FILE at a throwaway sqlite file, initialized fresh."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()

    def make_video(video_id, script=""):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, topic, status, script, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (video_id, "test topic", "TOPIC_APPROVED", script, _now(), _now()),
            )

    return make_video


# ── Migration ────────────────────────────────────────────────────────────────

def test_init_db_adds_new_columns_on_fresh_db(job_db):
    with server._conn() as con:
        video_cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)").fetchall()}
    assert "script_segments" in video_cols


def test_init_db_migrates_old_schema_db_without_new_columns(tmp_path, monkeypatch):
    """Simulate a pre-existing DB that predates this task's columns (but has
    everything up to the previous migration), then confirm _init_db adds the
    new columns without disturbing existing data."""
    db_path = tmp_path / "old.db"
    con = sqlite3.connect(str(db_path))
    con.executescript("""
        CREATE TABLE projects (
            id                  TEXT    PRIMARY KEY,
            name                TEXT    NOT NULL,
            description         TEXT    NOT NULL DEFAULT '',
            is_curriculum_seed  INTEGER NOT NULL DEFAULT 0,
            status              TEXT    NOT NULL DEFAULT 'active',
            created_at          TEXT    NOT NULL
        );
        CREATE TABLE videos (
            id                    TEXT PRIMARY KEY,
            project_id            TEXT REFERENCES projects(id),
            topic                 TEXT NOT NULL,
            strategy              TEXT NOT NULL DEFAULT 'manual',
            producibility_score   INTEGER NOT NULL DEFAULT 0,
            status                TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
            title                 TEXT NOT NULL DEFAULT '',
            script                TEXT NOT NULL DEFAULT '',
            voice_file_path       TEXT NOT NULL DEFAULT '',
            timeline_path         TEXT NOT NULL DEFAULT '',
            scene_config_path     TEXT NOT NULL DEFAULT '',
            video_path            TEXT NOT NULL DEFAULT '',
            video_version         INTEGER NOT NULL DEFAULT 1,
            gemini_feedback       TEXT NOT NULL DEFAULT '',
            youtube_url           TEXT NOT NULL DEFAULT '',
            cost_cents_elevenlabs INTEGER NOT NULL DEFAULT 0,
            cost_cents_gemini     INTEGER NOT NULL DEFAULT 0,
            cost_cents_claude     INTEGER NOT NULL DEFAULT 0,
            ai_review_count       INTEGER NOT NULL DEFAULT 0,
            render_fail_count     INTEGER NOT NULL DEFAULT 0,
            created_at            TEXT NOT NULL,
            updated_at            TEXT NOT NULL
        );
    """)
    con.execute(
        "INSERT INTO videos (id, project_id, topic, script, created_at, updated_at) "
        "VALUES ('vid_old', NULL, 'old topic', 'an old flat script', ?, ?)",
        (_now(), _now()),
    )
    con.execute(
        "INSERT INTO projects (id, name, created_at) VALUES ('proj_old', 'Old Project', ?)",
        (_now(),),
    )
    con.commit()
    con.close()

    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()
    # Idempotent: calling twice must not raise (column-exists guard).
    server._init_db()

    with server._conn() as con:
        video_cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)").fetchall()}
        video_row = con.execute("SELECT * FROM videos WHERE id = 'vid_old'").fetchone()
        project_row = con.execute("SELECT * FROM projects WHERE id = 'proj_old'").fetchone()

    assert "script_segments" in video_cols
    # Pre-existing data untouched, new column defaults to NULL.
    assert video_row["script"] == "an old flat script"
    assert video_row["script_segments"] is None
    assert project_row["name"] == "Old Project"


# ── update_video ─────────────────────────────────────────────────────────────

def test_update_video_derives_script_from_segments(job_db):
    job_db("vid_1")
    segments = [
        {"id": "s1", "voice": "  Hello there.  ", "visual": "[Show intro card]"},
        {"id": "s2", "voice": "This is segment two.", "visual": ""},
    ]

    result = server.update_video("vid_1", script_segments=segments, **PUBLISH)

    assert result == {"video_id": "vid_1", "updated_fields": ["script", "publish_title", "publish_description", "script_segments"]}
    with server._conn() as con:
        row = con.execute("SELECT script, script_segments FROM videos WHERE id = ?", ("vid_1",)).fetchone()
    assert row["script"] == "Hello there. This is segment two."
    import json
    assert json.loads(row["script_segments"]) == segments


def test_update_video_derives_script_stripping_phoneme_tags(job_db):
    """The flat `script` field (used for captions/display) must never carry
    inline <phoneme> markup, even when script_segments does (phoneme mode)."""
    _set_install_model("eleven_flash_v2")  # <phoneme> needs a voice that honours it
    job_db("vid_1b")
    segments = [
        {
            "id": "s1",
            "voice": 'The word <phoneme alphabet="cmu-arpabet" ph="M AE1 D IH0 S AH0 N">Madison</phoneme> is here.',
            "visual": "",
        },
    ]

    result = server.update_video("vid_1b", script_segments=segments, **PUBLISH)

    assert result == {"video_id": "vid_1b", "updated_fields": ["script", "publish_title", "publish_description", "script_segments"]}
    with server._conn() as con:
        row = con.execute("SELECT script FROM videos WHERE id = ?", ("vid_1b",)).fetchone()
    assert row["script"] == "The word Madison is here."


def test_update_video_rejects_segment_with_empty_voice(job_db):
    job_db("vid_2")
    segments = [
        {"id": "s1", "voice": "Fine.", "visual": ""},
        {"id": "s2", "voice": "   ", "visual": "some note"},
    ]

    result = server.update_video("vid_2", script_segments=segments, **PUBLISH)

    assert "error" in result
    with server._conn() as con:
        row = con.execute("SELECT script, script_segments FROM videos WHERE id = ?", ("vid_2",)).fetchone()
    # Nothing written on validation failure.
    assert row["script"] == ""
    assert row["script_segments"] is None


def test_update_video_rejects_duplicate_segment_ids(job_db):
    """tubematic-scene-config matches segments to timeline.segments by id —
    a duplicate id would make that matching ambiguous."""
    job_db("vid_dup")
    segments = [
        {"id": "s1", "voice": "Hello.", "visual": ""},
        {"id": "s1", "voice": "Duplicate id.", "visual": ""},
    ]

    result = server.update_video("vid_dup", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_rejects_segment_with_no_words_after_phoneme_strip(job_db):
    """A phoneme tag wrapping only empty/whitespace content passes the raw
    non-empty check but tokenizes to zero words — must be rejected here
    rather than reaching _lockstep_segment_frames as a zero-word segment."""
    job_db("vid_zero")
    segments = [
        {"id": "s1", "voice": '<phoneme alphabet="cmu-arpabet" ph="M">  </phoneme>', "visual": ""},
    ]

    result = server.update_video("vid_zero", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_derives_script_keeping_respell_authored_word(job_db):
    """The flat `script` field (captions/display) must keep the wrapped,
    authored word from a <respell> tag, not the "as" respelling — mirrors
    the <phoneme> stripping behavior above (TMDEV-26 follow-up)."""
    job_db("vid_r1")
    segments = [
        {"id": "s1", "voice": 'Only <respell as="Vah-gar">Vhagar</respell> could match it.', "visual": ""},
    ]

    result = server.update_video("vid_r1", script_segments=segments, **PUBLISH)

    assert result == {"video_id": "vid_r1", "updated_fields": ["script", "publish_title", "publish_description", "script_segments"]}
    with server._conn() as con:
        row = con.execute("SELECT script FROM videos WHERE id = ?", ("vid_r1",)).fetchone()
    assert row["script"] == "Only Vhagar could match it."


def test_update_video_accepts_well_formed_respell_tag(job_db):
    job_db("vid_r2")
    segments = [
        {"id": "s1", "voice": 'Only <respell as="Vah-gar">Vhagar</respell> could match it.', "visual": ""},
    ]

    result = server.update_video("vid_r2", script_segments=segments, **PUBLISH)

    assert "error" not in result


def test_update_video_rejects_respell_tag_with_empty_as_value(job_db):
    job_db("vid_r3")
    segments = [{"id": "s1", "voice": 'Only <respell as="">Vhagar</respell> could match it.', "visual": ""}]

    result = server.update_video("vid_r3", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_rejects_respell_tag_with_whitespace_in_as_value(job_db):
    """respell's "as" value must be a single token — it replaces the wrapped
    word as one unit in tts_text, so whitespace would change the segment/word
    lockstep's token count."""
    job_db("vid_r4")
    segments = [{"id": "s1", "voice": 'Only <respell as="Vah gar">Vhagar</respell> could match it.', "visual": ""}]

    result = server.update_video("vid_r4", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_rejects_respell_tag_wrapping_empty_text(job_db):
    job_db("vid_r5")
    segments = [{"id": "s1", "voice": 'Only <respell as="Vah-gar"></respell> could match it.', "visual": ""}]

    result = server.update_video("vid_r5", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_rejects_respell_tag_wrapping_multiple_words(job_db):
    job_db("vid_r6")
    segments = [{
        "id": "s1",
        "voice": 'Only <respell as="Vah-gar">the great Vhagar</respell> could match it.',
        "visual": "",
    }]

    result = server.update_video("vid_r6", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_rejects_unclosed_respell_tag(job_db):
    """An unclosed/malformed tag would otherwise reach ElevenLabs as literal,
    spoken-aloud text instead of being substituted."""
    job_db("vid_r7")
    segments = [{"id": "s1", "voice": 'Only <respell as="Vah-gar">Vhagar could match it.', "visual": ""}]

    result = server.update_video("vid_r7", script_segments=segments, **PUBLISH)

    assert "error" in result


def test_update_video_rejects_empty_segments_list(job_db):
    job_db("vid_3")
    result = server.update_video("vid_3", script_segments=[], **PUBLISH)
    assert "error" in result


def test_update_video_rejects_segment_missing_visual_key(job_db):
    job_db("vid_4")
    segments = [{"id": "s1", "voice": "Hello."}]
    result = server.update_video("vid_4", script_segments=segments, **PUBLISH)
    assert "error" in result


def test_update_video_flat_script_still_works(job_db):
    """Old call shape (script=... without script_segments) is unaffected."""
    job_db("vid_5")

    result = server.update_video("vid_5", script="A plain flat script.", **PUBLISH)

    assert result == {"video_id": "vid_5", "updated_fields": ["script", "publish_title", "publish_description"]}
    with server._conn() as con:
        row = con.execute("SELECT script, script_segments FROM videos WHERE id = ?", ("vid_5",)).fetchone()
    assert row["script"] == "A plain flat script."
    assert row["script_segments"] is None


# ── get_video ────────────────────────────────────────────────────────────────

def test_get_video_round_trips_script_segments(job_db):
    job_db("vid_6")
    segments = [{"id": "s1", "voice": "Hi.", "visual": "[Card]"}]
    server.update_video("vid_6", script_segments=segments, **PUBLISH)

    video = server.get_video("vid_6")

    assert video["script_segments"] == segments
    assert video["script"] == "Hi."


def test_get_video_script_segments_null_when_unset(job_db):
    job_db("vid_7", script="legacy flat script")

    video = server.get_video("vid_7")

    assert video["script_segments"] is None
    assert video["script"] == "legacy flat script"


# ── TMDEV-26: pause markup + bracket allowlist ──────────────────────────────

def test_update_video_derives_script_stripping_pause_markup(job_db):
    """The flat `script` (captions/display) must carry neither phoneme markup
    nor pause markup, and must not keep the double space the strip leaves."""
    job_db("vid_pm1")
    segments = [
        {"id": "s1", "voice": 'Here is the catch. <break time="0.6s" /> It never verifies.',
         "visual": ""},
    ]

    result = server.update_video("vid_pm1", script_segments=segments, **PUBLISH)

    assert "error" not in result
    with server._conn() as con:
        row = con.execute("SELECT script FROM videos WHERE id = ?", ("vid_pm1",)).fetchone()
    assert row["script"] == "Here is the catch. It never verifies."


def test_update_video_accepts_v3_pause_tags_on_v3(job_db):
    _set_install_model("eleven_v3")
    job_db("vid_pm2")
    segments = [{"id": "s1", "voice": "Here is the catch. [short pause] It never verifies.",
                 "visual": ""}]

    result = server.update_video("vid_pm2", script_segments=segments, **PUBLISH)

    assert "error" not in result
    with server._conn() as con:
        row = con.execute("SELECT script FROM videos WHERE id = ?", ("vid_pm2",)).fetchone()
    assert row["script"] == "Here is the catch. It never verifies."


def test_update_video_rejects_stage_direction_brackets(job_db):
    """Closes a real hole: before TMDEV-26 nothing checked brackets on the
    segments path, so a stray [Show Card] was voiced aloud verbatim."""
    job_db("vid_pm3")
    segments = [{"id": "s1", "voice": "Here is the catch. [Show Card] It never verifies.",
                 "visual": ""}]

    result = server.update_video("vid_pm3", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "[Show Card]" in result["error"]


def test_update_video_rejects_break_only_segment(job_db):
    job_db("vid_pm4")
    segments = [
        {"id": "s1", "voice": "Real words here.", "visual": ""},
        {"id": "s2", "voice": '<break time="0.6s" />', "visual": ""},
    ]

    result = server.update_video("vid_pm4", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "no words" in result["error"]


def test_update_video_rejects_standalone_punctuation_word(job_db):
    """Ellipses must attach to a word. A lone punctuation token would be
    indistinguishable from the '.' marker normalized_alignment emits for a
    <break/>, which is what makes the marker drop unambiguous."""
    job_db("vid_pm5")
    segments = [{"id": "s1", "voice": "Here is the catch ... it never verifies.", "visual": ""}]

    result = server.update_video("vid_pm5", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "standalone punctuation" in result["error"]


def test_update_video_allows_ellipsis_attached_to_word(job_db):
    job_db("vid_pm6")
    segments = [{"id": "s1", "voice": "Here is the catch... it never verifies.", "visual": ""}]

    result = server.update_video("vid_pm6", script_segments=segments, **PUBLISH)

    assert "error" not in result


def test_update_video_rejects_break_tag_on_v3(job_db):
    _set_install_model("eleven_v3")
    job_db("vid_pm7")
    segments = [{"id": "s1", "voice": 'Wait. <break time="0.6s" /> Go.', "visual": ""}]

    result = server.update_video("vid_pm7", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "<break/>" in result["error"]


def test_update_video_rejects_v3_pause_tag_on_default_model(job_db):
    job_db("vid_pm8")
    segments = [{"id": "s1", "voice": "Wait. [pause] Go.", "visual": ""}]

    result = server.update_video("vid_pm8", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "eleven_v3" in result["error"]


# ── TMDEV-122: markup values ElevenLabs gets silently wrong ─────────────────
# An unknown alphabet returns 200 with the word missing from the audio, and a
# break past 3s is undocumented — both must fail here, at authoring time.

@pytest.mark.parametrize("tag", [
    '<phoneme alphabet="klingon" ph="V AA1 G AA0 R">Vhagar</phoneme>',
    '<phoneme ph="V AA1 G AA0 R">Vhagar</phoneme>',
    '<phoneme alphabet="CMU-Arpabet" ph="V AA1 G AA0 R">Vhagar</phoneme>',
    # Pseudo-attributes: a search for `alphabet=` anywhere in the tag used to
    # find these and accept a tag that has no real alphabet attribute.
    '<phoneme data-alphabet="cmu-arpabet" ph="V AA1 G AA0 R">Vhagar</phoneme>',
    '<phoneme note=\'alphabet="ipa"\' ph="V AA1 G AA0 R">Vhagar</phoneme>',
    '<phoneme alphabet="ipa" alphabet="klingon" ph="V AA1 G AA0 R">Vhagar</phoneme>',
    '<phoneme ALPHABET="ipa" ph="V AA1 G AA0 R">Vhagar</phoneme>',
])
def test_update_video_rejects_unknown_phoneme_alphabet(job_db, tag):
    _set_install_model("eleven_flash_v2")  # <phoneme> needs a voice that honours it
    job_db("vid_mv1")
    segments = [{"id": "s1", "voice": f"The dragon {tag} took flight.", "visual": ""}]

    result = server.update_video("vid_mv1", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "alphabet" in result["error"]
    assert "cmu-arpabet" in result["error"]


@pytest.mark.parametrize("alphabet,ph", [("cmu-arpabet", "V AA1 G AA0 R"), ("ipa", "ˈvɑːɡɑːr")])
def test_update_video_accepts_documented_phoneme_alphabets(job_db, alphabet, ph):
    _set_install_model("eleven_flash_v2")  # <phoneme> needs a voice that honours it
    job_db("vid_mv2")
    voice = f'The dragon <phoneme alphabet="{alphabet}" ph="{ph}">Vhagar</phoneme> took flight.'

    result = server.update_video("vid_mv2", script_segments=[{"id": "s1", "voice": voice, "visual": ""}], **PUBLISH)

    assert "error" not in result


@pytest.mark.parametrize("tag", [
    '<break time="3.5s" />',
    '<break time="30s" />',
    '<break time="500ms" />',
    '<break time="0s" />',
    '<break time="soon" />',
    '<break />',
    '<break data-time="1s" />',
    '<break note=\'time="1s"\' />',
    '<break time="1s" time="9s" />',
])
def test_update_video_rejects_break_time_outside_documented_range(job_db, tag):
    job_db("vid_mv3")
    segments = [{"id": "s1", "voice": f"Wait. {tag} Go.", "visual": ""}]

    result = server.update_video("vid_mv3", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "break" in result["error"]
    assert "3s" in result["error"]


@pytest.mark.parametrize("tag", ['<break time="0.6s" />', '<break time="3s" />', "<break time='1.0s'/>"])
def test_update_video_accepts_break_time_in_seconds_up_to_three(job_db, tag):
    job_db("vid_mv4")
    segments = [{"id": "s1", "voice": f"Wait. {tag} Go.", "visual": ""}]

    result = server.update_video("vid_mv4", script_segments=segments, **PUBLISH)

    assert "error" not in result


# ── Inline <ipa> tags: eleven_v3's native IPA ─────────────────────────────────

def test_update_video_derives_script_keeping_ipa_authored_word(job_db):
    """The IPA reaches ElevenLabs only; the flat script (and so the captions)
    keeps the wrapped, authored word — viewers must never read IPA on screen."""
    _set_install_model("eleven_v3")
    job_db("vid_ipa1")
    segments = [{"id": "s1", "voice": 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.',
                 "visual": ""}]

    result = server.update_video("vid_ipa1", script_segments=segments, **PUBLISH)

    assert "error" not in result
    with server._conn() as con:
        row = con.execute("SELECT script FROM videos WHERE id = ?", ("vid_ipa1",)).fetchone()
    assert row["script"] == "Only Vhagar could match it."


@pytest.mark.parametrize("model", ["eleven_multilingual_v2", "eleven_flash_v2", "eleven_turbo_v2_5"])
def test_update_video_rejects_ipa_tag_on_a_model_other_than_v3(job_db, model):
    """Any other model reads the slashes and symbols aloud (probed on v2)."""
    _set_install_model(model)
    job_db("vid_ipa2")
    segments = [{"id": "s1", "voice": 'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.',
                 "visual": ""}]

    result = server.update_video("vid_ipa2", script_segments=segments, **PUBLISH)

    assert "error" in result
    assert "eleven_v3" in result["error"]
    assert model in result["error"]


@pytest.mark.parametrize("voice", [
    'Only <ipa ph="vɑːˈɡɑːr">Vhagar could match it.',          # unclosed
    'Only <ipa>Vhagar</ipa> could match it.',                   # no ph
    'Only <ipa ph="">Vhagar</ipa> could match it.',             # empty ph
    'Only <ipa ph="vɑː ˈɡɑːr">Vhagar</ipa> could match it.',    # whitespace in ph
    'Only <ipa ph="/vɑːˈɡɑːr/">Vhagar</ipa> could match it.',   # slashes are ours to add
    'Only <ipa ph="vɑːˈɡɑːr">the great Vhagar</ipa> could.',    # more than one word
    'Only <ipa ph="vɑːˈɡɑːr"></ipa> could match it.',           # wraps nothing
    'Only <ipa data-ph="vɑːˈɡɑːr">Vhagar</ipa> could match it.',  # not the ph attribute
    'Only <ipa ph="vɑː" ph="ɡɑːr">Vhagar</ipa> could match it.',    # ph twice
    'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa></ipa> could match it.',  # stray closer
    'Only Vhagar</ipa> could match it.',                            # closer, no opener
    'Only Vhagar</ipa extra> could match it.',                      # malformed closer
    'Only Vhagar</ipa could match it.',                             # incomplete closer
    'Only <ipa ph="vɑːˈɡɑːr">Vhagar</ipa extra> could match it.',   # opener + bad closer
])
def test_update_video_rejects_a_malformed_ipa_tag(job_db, voice):
    _set_install_model("eleven_v3")
    job_db("vid_ipa3")

    result = server.update_video("vid_ipa3", script_segments=[{"id": "s1", "voice": voice, "visual": ""}], **PUBLISH)

    assert "error" in result
    assert "ipa" in result["error"]


def test_pronunciation_mode_is_ipa_on_v3_only():
    assert server._pronunciation_mode_for_model("eleven_v3") == "ipa"
    assert server._pronunciation_mode_for_model("eleven_flash_v2") == "phoneme"
    assert server._pronunciation_mode_for_model("eleven_multilingual_v2") == "respell"
