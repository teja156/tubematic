"""Per-voice ElevenLabs models on the MCP side (TMDEV-121).

The model follows the voice, and the model decides which markup a script may
carry. What these guard:

- The agent learns the model from get_video, per video — there is no
  install-wide value to read any more, and reading one would script a v3
  video's pauses as <break/> tags.
- update_video checks a script against the video's own voice and PINS that
  voice onto the video, so a later change to the install default cannot swap
  the model under an already-written script.
- update_video refuses a voice change the stored script cannot use (the
  same rule the HTTP PATCH answers with a 409).
- generate_voice sends the voice's own model.
- A project's default voice seeds every video filed into it.
"""
import json

import pytest

import server
from test_generate_voice import (  # noqa: F401 — fixtures
    _set_install_model, fake_httpx, job_db, voice_env,
)

V2 = {"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"}
V3 = {"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"}
FLASH = {"name": "Bella", "voice_id": "b1", "model_id": "eleven_flash_v2"}

# Every script write carries the publish metadata (TMDEV-132); these tests
# are about the script, so one fixed pair serves them all.
PUBLISH = {"publish_title": "A title", "publish_description": "A description."}


def _roster(*voices, default="r1"):
    server._set_setting("elevenlabs_voices", json.dumps(list(voices)))
    server._set_setting("elevenlabs_voice_id", default)


def _segs(*voices):
    return [{"id": f"s{i}", "voice": v, "visual": ""} for i, v in enumerate(voices)]


def _stored_voice(video_id):
    with server._conn() as con:
        return con.execute("SELECT voice_id FROM videos WHERE id = ?", (video_id,)).fetchone()[0]


IPA = 'Say <ipa ph="ˈmædɪsən">Madison</ipa> now.'


# ── the roster ───────────────────────────────────────────────────────────────

def test_a_voice_without_a_model_empties_the_roster(job_db):
    """Same corrupt-means-empty rule as the API reader: a voice with no model
    could not be voiced, and guessing one would voice with a model nobody
    chose."""
    server._set_setting("elevenlabs_voices", '[{"name": "A", "voice_id": "a"}]')
    assert server._get_voices() == []
    server._set_setting("elevenlabs_voices",
                        '[{"name": "A", "voice_id": "a", "model_id": "eleven_english_v1"}]')
    assert server._get_voices() == []


def test_an_unhashable_model_empties_the_roster_instead_of_raising(job_db):
    server._set_setting("elevenlabs_voices",
                        '[{"name": "A", "voice_id": "a", "model_id": ["eleven_v3"]}]')
    assert server._get_voices() == []


def test_pipeline_status_has_no_install_wide_model(job_db):
    _roster(V2, V3)
    status = server.get_pipeline_status()
    assert "elevenlabs_model_id" not in status and "pronunciation_mode" not in status
    assert status["elevenlabs_voices"] == [{**V2, "pronunciation_mode": "respell"},
                                           {**V3, "pronunciation_mode": "ipa"}]


def test_each_roster_voice_carries_the_mode_get_video_would_report(job_db):
    """A revision that changes the voice writes for a model get_video does not
    report yet, so the roster has to say which markup that voice takes — the
    same derivation get_video uses, never a second copy in skill prose."""
    _roster(V2, V3, FLASH)
    listed = {v["voice_id"]: v["pronunciation_mode"]
              for v in server.get_pipeline_status()["elevenlabs_voices"]}
    for voice in (V2, V3, FLASH):
        job_db(f"v-{voice['voice_id']}", voice_id=voice["voice_id"], status="TOPIC_APPROVED")
        assert listed[voice["voice_id"]] == \
            server.get_video(f"v-{voice['voice_id']}")["pronunciation_mode"]
    # Output only: the stored roster keeps its exact shape.
    assert server._get_voices() == [V2, V3, FLASH]


def test_pipeline_status_blanks_a_default_voice_off_the_roster(job_db):
    _roster(V2, default="ghost")
    assert server.get_pipeline_status()["elevenlabs_voice_id"] == ""


# ── get_video ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("voice_id,source,model,mode", [
    ("a1", "video", "eleven_v3", "ipa"),
    ("b1", "video", "eleven_flash_v2", "phoneme"),
    ("", "install", "eleven_multilingual_v2", "respell"),
])
def test_get_video_reports_the_videos_voice_and_its_model(job_db, voice_id, source, model, mode):
    _roster(V2, V3, FLASH)
    job_db("v", voice_id=voice_id, status="TOPIC_APPROVED")
    video = server.get_video("v")
    assert video["voice"]["source"] == source
    assert video["elevenlabs_model_id"] == model
    assert video["pronunciation_mode"] == mode


def test_get_video_with_no_voice_resolving(job_db):
    job_db("v", status="TOPIC_APPROVED")
    video = server.get_video("v")
    assert video["voice"] is None
    assert video["elevenlabs_model_id"] == "eleven_multilingual_v2"


# ── update_video: validate against the video's voice, then pin it ────────────

def test_a_script_is_checked_against_the_videos_own_voice(job_db):
    """The install default is on v2, but this video's voice is on v3, so v3
    pause tags are right and <break/> tags are wrong."""
    _roster(V2, V3)
    job_db("v", voice_id="a1", status="TOPIC_APPROVED")
    assert "error" not in server.update_video("v", script_segments=_segs("A. [pause] B."), **PUBLISH)
    err = server.update_video("v", script_segments=_segs('A. <break time="0.5s" /> B.'), **PUBLISH)
    assert "<break/>" in err["error"] and "Adam" in err["error"]


def test_writing_a_script_pins_the_voice_it_was_written_for(job_db):
    _roster(V2, V3)
    job_db("v", status="TOPIC_APPROVED")
    server.update_video("v", script_segments=_segs("Plain words."), **PUBLISH)
    assert _stored_voice("v") == "r1"
    # A later change of the install default no longer reaches this video.
    _roster(V2, V3, default="a1")
    assert server.get_video("v")["elevenlabs_model_id"] == "eleven_multilingual_v2"


def test_a_legacy_flat_script_pins_the_voice_too(job_db):
    _roster(V2)
    job_db("v", status="TOPIC_APPROVED")
    server.update_video("v", script="Plain words.", **PUBLISH)
    assert _stored_voice("v") == "r1"


def test_a_script_never_overwrites_a_voice_the_video_already_has(job_db):
    _roster(V2, V3)
    job_db("v", voice_id="a1", status="TOPIC_APPROVED")
    server.update_video("v", script_segments=_segs("Plain words."), **PUBLISH)
    assert _stored_voice("v") == "a1"


def test_a_voice_in_the_same_call_is_what_the_script_is_checked_against(job_db):
    _roster(V2, V3)
    job_db("v", status="TOPIC_APPROVED")
    assert "error" not in server.update_video("v", voice_id="a1",
                                              script_segments=_segs(IPA), **PUBLISH)
    assert _stored_voice("v") == "a1"


def test_an_explicitly_blank_voice_still_pins_the_resolved_default(job_db):
    """voice_id="" alongside a script means "the install default" — which
    is exactly the value that must be recorded, or a later default change
    swaps the narrator and model under the script."""
    _roster(V2, V3)
    job_db("v", voice_id="a1", status="TOPIC_APPROVED")
    assert "error" not in server.update_video("v", voice_id="",
                                              script_segments=_segs("Plain words."), **PUBLISH)
    assert _stored_voice("v") == "r1"


def test_phoneme_tags_are_refused_for_a_voice_that_ignores_them(job_db):
    """Written for the video's own voice, a script can only carry markup that
    voice can speak — which is what lets approval with its own voice always
    pass."""
    _roster(V2, FLASH)
    job_db("v", status="TOPIC_APPROVED")
    err = server.update_video("v", script_segments=_segs(
        'Say <phoneme alphabet="ipa" ph="x">word</phoneme>.'), **PUBLISH)
    assert "<phoneme>" in err["error"] and "Rachel" in err["error"]
    job_db("w", voice_id="b1", status="TOPIC_APPROVED")
    assert "error" not in server.update_video("w", script_segments=_segs(
        'Say <phoneme alphabet="ipa" ph="x">word</phoneme>.'), **PUBLISH)


def test_phoneme_tags_after_the_voices_own_model_was_edited_are_refused(job_db):
    _roster(V2, FLASH)
    job_db("v", voice_id="b1", status="SCRIPT_READY",
           script_segments=_segs('Say <phoneme alphabet="ipa" ph="x">word</phoneme>.'))
    _roster(V2, {**FLASH, "model_id": "eleven_multilingual_v2"})
    assert "<phoneme>" in server.update_video("v", voice_id="b1")["error"]


def test_with_no_voice_at_all_nothing_is_pinned(job_db):
    job_db("v", status="TOPIC_APPROVED")
    assert "error" not in server.update_video("v", script_segments=_segs("Plain words."), **PUBLISH)
    assert _stored_voice("v") == ""


# ── update_video: a voice change the script cannot use ───────────────────────

def test_a_voice_change_the_script_cannot_use_is_refused(job_db):
    _roster(V2, V3)
    job_db("v", voice_id="a1", status="SCRIPT_READY", script_segments=_segs(IPA))
    err = server.update_video("v", voice_id="r1")
    assert "<ipa>" in err["error"] and "request a revision" in err["error"]
    assert _stored_voice("v") == "a1"


def test_re_setting_the_videos_own_voice_is_never_refused(job_db):
    _roster(V2, V3)
    job_db("v", voice_id="a1", status="SCRIPT_READY", script_segments=_segs(IPA))
    assert "error" not in server.update_video("v", voice_id="a1")


def test_a_compatible_voice_change_passes(job_db):
    _roster(V2, V3, FLASH)
    job_db("v", voice_id="r1", status="SCRIPT_READY",
           script_segments=_segs('A <break time="0.5s" /> B.'))
    assert "error" not in server.update_video("v", voice_id="b1")
    assert _stored_voice("v") == "b1"


def test_clearing_to_the_install_default_is_checked_against_it(job_db):
    _roster(V2, V3)
    job_db("v", voice_id="a1", status="SCRIPT_READY", script_segments=_segs("A. [pause] B."))
    assert "error" in server.update_video("v", voice_id="")


def test_a_switch_that_loses_phoneme_tags_is_refused(job_db):
    _roster(V2, FLASH)
    job_db("v", voice_id="b1", status="SCRIPT_READY",
           script_segments=_segs('Say <phoneme alphabet="ipa" ph="x">word</phoneme>.'))
    assert "<phoneme>" in server.update_video("v", voice_id="r1")["error"]


# ── moving a scripted video to a voice on another model ─────────────────────

def test_a_cross_model_voice_needs_the_rewritten_script_in_the_same_call(job_db):
    """The revision path the operator skill teaches: the new voice alone is
    refused, because the stored script carries the old model's markup; the new
    voice with the script rewritten for its model, in one call, goes through
    and pins the new voice."""
    _roster(V2, V3)
    job_db("v", voice_id="r1", status="REVISION_REQUESTED",
           script_segments=_segs('A <break time="0.5s" /> B.'))
    assert "request a revision" in server.update_video("v", voice_id="a1")["error"]
    assert _stored_voice("v") == "r1"
    assert "error" not in server.update_video("v", voice_id="a1",
                                              script_segments=_segs("A. [pause] B."), **PUBLISH)
    assert _stored_voice("v") == "a1"


def test_a_stale_script_at_topic_proposed_blocks_no_voice(job_db):
    """A topic revision can leave an old script stored at TOPIC_PROPOSED; it is
    rewritten once the topic is approved, so it refuses nothing. The same row
    at SCRIPT_READY still does."""
    _roster(V2, V3)
    job_db("v", voice_id="r1", status="TOPIC_PROPOSED",
           script_segments=_segs('A <break time="0.5s" /> B.'))
    assert "error" not in server.update_video("v", voice_id="a1")
    assert _stored_voice("v") == "a1"
    job_db("w", voice_id="r1", status="SCRIPT_READY",
           script_segments=_segs('A <break time="0.5s" /> B.'))
    assert "error" in server.update_video("w", voice_id="a1")


def test_a_waived_voice_write_is_bound_to_topic_proposed(job_db, monkeypatch):
    """The check was waived because of the status, so a write landing after the
    video moved on (here: the script written mid-call) must fail rather than
    put the voice under a script it may not be able to speak."""
    _roster(V2, V3)
    job_db("v", voice_id="r1", status="TOPIC_PROPOSED",
           script_segments=_segs('A <break time="0.5s" /> B.'))
    real = server._resolve_voice

    def moved_on(voice_id):
        with server._conn() as con:
            con.execute("UPDATE videos SET status = 'SCRIPT_READY' WHERE id = 'v'")
        return real(voice_id)

    monkeypatch.setattr(server, "_resolve_voice", moved_on)
    err = server.update_video("v", voice_id="a1")
    assert "moved from TOPIC_PROPOSED to SCRIPT_READY" in err["error"]
    assert _stored_voice("v") == "r1"


# ── generate_voice ───────────────────────────────────────────────────────────

def test_generate_voice_sends_the_videos_voice_and_its_model(job_db, voice_env, fake_httpx):
    _roster(V2, V3)
    job_db("v", voice_id="a1", script="Hello world.")
    assert "error" not in server.generate_voice("v", "Hello world.")
    assert fake_httpx.last_payload["model_id"] == "eleven_v3"


def test_generate_voice_refuses_ipa_when_the_voices_model_changed(job_db, voice_env, fake_httpx):
    """A voice moved to another model in Settings after scripting: refused
    before any spend, naming the voice."""
    _roster(V2, {**V3, "model_id": "eleven_multilingual_v2"})
    job_db("v", voice_id="a1", script_segments=_segs(IPA))
    err = server.generate_voice("v", "")
    assert "Adam" in err["error"] and fake_httpx.last_payload is None


def test_generate_voice_refuses_phoneme_tags_when_the_voices_model_changed(
        job_db, voice_env, fake_httpx):
    """Approved while the voice was on flash_v2, then its model was changed:
    the checkpoint already passed, so only this check stands before spend."""
    _roster(V2, {**FLASH, "model_id": "eleven_multilingual_v2"})
    job_db("v", voice_id="b1",
           script_segments=_segs('Say <phoneme alphabet="ipa" ph="x">word</phoneme>.'))
    err = server.generate_voice("v", "")
    assert "<phoneme>" in err["error"] and "Bella" in err["error"]
    assert fake_httpx.last_payload is None


def test_generate_voice_with_a_default_off_the_roster_errors_before_spend(job_db, voice_env,
                                                                         fake_httpx):
    _roster(V2, default="ghost")
    job_db("v", script="Hello world.")
    assert "No default voice" in server.generate_voice("v", "Hello world.")["error"]
    assert fake_httpx.last_payload is None


# ── project default voice ────────────────────────────────────────────────────

@pytest.mark.parametrize("strategy", ["curriculum", "trending", "mining", "manual"])
def test_every_strategy_inherits_the_project_voice(job_db, strategy):
    _roster(V2, V3)
    server.upsert_project("p", "P", default_voice_id="a1")
    vid = server.create_video("p", "topic", strategy, 7)["video_id"]
    assert _stored_voice(vid) == "a1"


def test_an_explicit_voice_beats_the_project_default(job_db):
    _roster(V2, V3)
    server.upsert_project("p", "P", default_voice_id="a1")
    vid = server.create_video("p", "topic", "trending", 7, voice_id="r1")["video_id"]
    assert _stored_voice(vid) == "r1"


def test_a_project_default_that_left_the_roster_is_not_seeded(job_db):
    _roster(V2, V3)
    server.upsert_project("p", "P", default_voice_id="a1")
    _roster(V2)
    vid = server.create_video("p", "topic", "trending", 7)["video_id"]
    assert _stored_voice(vid) == ""


def test_upsert_project_default_voice_is_partial_and_checked_on_change(job_db):
    _roster(V2, V3)
    assert "error" in server.upsert_project("p", "P", default_voice_id="ghost")
    server.upsert_project("p", "P", default_voice_id="a1")
    # Omitting it leaves it alone.
    assert server.upsert_project("p", "P2")["default_voice_id"] == "a1"
    # Re-sending a stored value that has since left the roster is not refused.
    _roster(V2)
    assert server.upsert_project("p", "P3", default_voice_id="a1")["default_voice_id"] == "a1"
    # "" clears it.
    assert server.upsert_project("p", "P4", default_voice_id="")["default_voice_id"] == ""
