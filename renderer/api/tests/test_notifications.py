"""The render worker's Discord notification sweep (TMDEV-5).

The sweep, not the message composition — that lives in test_discord_notify.py.
What is tested here is which videos get announced, when, and exactly once.

Four behaviours are load-bearing and would each be a real bug:

  * **No backfill blast.** The migration marks every existing row as already
    notified, so upgrading an install with months of parked videos must send
    nothing.
  * **A second arrival announces again**, including when the whole round happens
    between two sweeps — which is the normal case while a render holds the loop.
    Otherwise the human never learns their feedback was acted on.
  * **Disabled periods do not accumulate.** Enabling a trigger starts announcing
    from that moment; it must not replay everything parked while it was off.
  * **updated_at is not touched.** It is the FIFO ordering key for the render
    claim; notifying a video must not reorder the render queue.
  * **A failed send does not advance the marker**, so the next tick retries
    instead of losing the notification silently.

Run from renderer/api/: pytest tests/test_notifications.py
"""
import json
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import discord_notify
import pipeline
import worker

_FMT = "%Y-%m-%dT%H:%M:%SZ"
URL = ("https://discord.com/api/webhooks/123456789012345678/"
       "abcdefghij0123456789_KLMNOPqrstuvwxyz-ABCDE")


def _ago(secs: float) -> str:
    return time.strftime(_FMT, time.gmtime(time.time() - secs))


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    monkeypatch.setattr(worker, "DB_PATH", db)
    pipeline._init_db(db)
    sent = []
    monkeypatch.setattr(worker.discord_notify, "send",
                        lambda url, payload, **kw: sent.append((url, payload)))
    return SimpleNamespace(db=db, sent=sent)


def _sql(env, query, params=()):
    con = sqlite3.connect(env.db)
    cur = con.execute(query, params)
    rows = cur.fetchall()
    con.commit()
    con.close()
    return rows


def _settings(env, **kwargs):
    for key, value in kwargs.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        _sql(env, "INSERT INTO settings (key, value) VALUES (?, ?)"
                  " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
             (key, value))


def _on(env, **extra):
    """The usual configuration: a webhook and all three triggers enabled."""
    _settings(env, discord_webhook_url=URL, notify_topic_proposed=True,
              notify_script_ready=True, notify_video_ready=True, **extra)


def _video(env, vid="vid-1", status="TOPIC_PROPOSED", notified_status="",
           updated_at=None, project="proj-1", **cols):
    if project:
        _sql(env, "INSERT OR IGNORE INTO projects (id, name, created_at)"
                  " VALUES (?, ?, ?)", (project, "Networking", _ago(9999)))
    stamp = updated_at or _ago(9999)
    columns = {"id": vid, "project_id": project, "topic": "How DNS works",
               "strategy": "curriculum", "producibility_score": 8,
               "status": status, "notified_status": notified_status,
               "created_at": stamp, "updated_at": stamp, **cols}
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    _sql(env, f"INSERT INTO videos ({names}) VALUES ({marks})", tuple(columns.values()))
    return vid


def _marker(env, vid="vid-1"):
    return _sql(env, "SELECT notified_status FROM videos WHERE id = ?", (vid,))[0][0]


def _arrival(env, vid="vid-1"):
    """What the marker should read once this video's current arrival has been
    accounted for — announced or, while its trigger is off, stamped as seen."""
    status, updated = _sql(
        env, "SELECT status, updated_at FROM videos WHERE id = ?", (vid,))[0]
    return f"{status}@{updated}"


# ── The off switches ─────────────────────────────────────────────────────────

def test_nothing_is_sent_without_a_webhook_url(env):
    _settings(env, notify_topic_proposed=True)
    _video(env)
    worker._sweep_notifications()
    assert env.sent == []


def test_nothing_is_sent_when_every_trigger_is_off(env):
    _settings(env, discord_webhook_url=URL)
    _video(env)
    worker._sweep_notifications()
    assert env.sent == []


TRIGGERS = [
    ("TOPIC_PROPOSED", "notify_topic_proposed"),
    ("SCRIPT_READY", "notify_script_ready"),
    ("VIDEO_READY", "notify_video_ready"),
    ("PARTIALLY_PUBLISHED", "notify_partially_published"),
    ("FAILED", "notify_failed"),
]
NOTIFIABLE = [status for status, _ in TRIGGERS]


def test_every_trigger_defaults_off():
    """A bool default also applies on upgrade: an install with a webhook and only
    some triggers on must not start receiving alerts it never asked for."""
    for _, key in TRIGGERS:
        assert pipeline.SETTINGS_SPEC[key] == ("bool", "false")
    assert set(worker.NOTIFIABLE_STATUSES) == set(NOTIFIABLE)


@pytest.mark.parametrize("status,key", TRIGGERS)
def test_each_trigger_gates_only_its_own_event(env, status, key):
    _settings(env, discord_webhook_url=URL, **{key: True})
    _video(env, "wanted", status=status)
    for other in NOTIFIABLE:
        if other != status:
            _video(env, f"quiet-{other}", status=other)
    worker._sweep_notifications()
    assert len(env.sent) == 1
    assert _marker(env, "wanted") == _arrival(env, "wanted")
    # The others are stamped as seen rather than left pending, so switching
    # their trigger on later starts from that moment instead of replaying them.
    for other in NOTIFIABLE:
        if other != status:
            assert _marker(env, f"quiet-{other}") == _arrival(env, f"quiet-{other}")


# ── Selection ────────────────────────────────────────────────────────────────

def test_a_video_at_a_checkpoint_is_announced_once(env):
    _on(env)
    _video(env, status="SCRIPT_READY")
    worker._sweep_notifications()
    worker._sweep_notifications()
    assert len(env.sent) == 1
    assert _marker(env) == _arrival(env)


def test_a_video_in_an_intermediate_status_is_never_announced(env):
    _on(env)
    for status in ("TOPIC_APPROVED", "VOICING", "VOICE_READY", "RENDER_QUEUED",
                   "RENDERING", "REVISION_REQUESTED", "PUBLISHED", "FAILED"):
        _video(env, f"v-{status}", status=status)
    worker._sweep_notifications()
    assert env.sent == []


def test_an_archived_video_is_never_announced(env):
    """Its files are gone — there is nothing left for a human to look at."""
    _on(env)
    _video(env, status="VIDEO_READY", archived_at="2026-01-01T00:00:00Z")
    worker._sweep_notifications()
    assert env.sent == []


def test_the_migration_backfill_means_no_blast_on_upgrade(env):
    """_init_db marks every pre-existing row as already notified. Without that,
    the first sweep after an upgrade announces months of backlog at once.

    TMDEV-91: _init_db now runs migration 0001 once, tracked in
    schema_migrations, so dropping the column alone would leave a later
    _init_db call a no-op. Clearing that table too reproduces what a real
    pre-migration database looks like on disk."""
    con = sqlite3.connect(env.db)
    con.execute("ALTER TABLE videos DROP COLUMN notified_status")
    con.execute("DELETE FROM schema_migrations WHERE version = 1")  # only 0001 re-runs; it is the idempotent one
    con.commit()
    con.close()
    _on(env)
    for i, status in enumerate(("TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY")):
        _sql(env, "INSERT INTO videos (id, topic, strategy, status, created_at, updated_at)"
                  " VALUES (?, 'T', 'manual', ?, ?, ?)",
             (f"old-{i}", status, _ago(9999), _ago(9999)))

    pipeline._init_db(env.db)          # the upgrade
    worker._sweep_notifications()

    assert env.sent == []
    assert _marker(env, "old-0") == _arrival(env, "old-0")


# ── Bundling topics ──────────────────────────────────────────────────────────

def test_a_burst_of_topics_becomes_one_message(env):
    _on(env)
    for i in range(5):
        _video(env, f"t{i}", status="TOPIC_PROPOSED")
    worker._sweep_notifications()
    assert len(env.sent) == 1
    assert len(env.sent[0][1]["embeds"][0]["fields"]) == 5


def test_topics_still_settling_are_held_back_entirely(env):
    """Half a research run is worse than a slightly later whole one — the
    partial batch would be followed by a second message for the same run."""
    _on(env)
    _video(env, "old", status="TOPIC_PROPOSED", updated_at=_ago(9999))
    _video(env, "fresh", status="TOPIC_PROPOSED", updated_at=_ago(1))
    worker._sweep_notifications()
    assert env.sent == []
    assert _marker(env, "old") == ""


def test_a_settled_burst_goes_out_on_the_next_tick(env):
    _on(env)
    _video(env, "t0", status="TOPIC_PROPOSED",
           updated_at=_ago(worker.TOPIC_SETTLE_SECS + 5))
    worker._sweep_notifications()
    assert len(env.sent) == 1


def test_the_settle_window_does_not_delay_the_other_two_events(env):
    """Only topics arrive in bursts; a script or a video is one event."""
    _on(env)
    _video(env, "s", status="SCRIPT_READY", updated_at=_ago(1))
    _video(env, "v", status="VIDEO_READY", updated_at=_ago(1))
    worker._sweep_notifications()
    assert len(env.sent) == 2


def test_each_ready_video_gets_its_own_message(env):
    _on(env)
    _video(env, "a", status="VIDEO_READY")
    _video(env, "b", status="VIDEO_READY")
    worker._sweep_notifications()
    assert len(env.sent) == 2


# ── Re-arming ────────────────────────────────────────────────────────────────

def _move(env, status, vid="vid-1", when=None):
    """Change a video's status the way every real writer does — bumping
    updated_at with it."""
    _sql(env, "UPDATE videos SET status = ?, updated_at = ? WHERE id = ?",
         (status, when or _ago(0), vid))


def test_a_revision_round_notifies_again(env):
    """SCRIPT_READY -> REVISION_REQUESTED -> SCRIPT_READY, with a sweep in
    between to observe the middle status."""
    _on(env)
    _video(env, status="SCRIPT_READY")
    worker._sweep_notifications()

    _move(env, "REVISION_REQUESTED", when=_ago(60))
    worker._sweep_notifications()

    _move(env, "SCRIPT_READY", when=_ago(30))
    worker._sweep_notifications()
    assert len(env.sent) == 2


def test_a_revision_round_notifies_again_with_no_sweep_in_between(env):
    """The same round, but entirely between two sweeps — which is what happens
    while the worker is inside a render, since that holds the loop for up to
    forty minutes.

    This is why the marker is an arrival ("<status>@<updated_at>") and not a
    status name: with a bare status the second SCRIPT_READY reads as already
    announced, and the human who asked for the revision never hears it landed.
    """
    _on(env)
    _video(env, status="SCRIPT_READY")
    worker._sweep_notifications()
    assert len(env.sent) == 1

    # No sweep observes either of these.
    _move(env, "REVISION_REQUESTED", when=_ago(60))
    _move(env, "SCRIPT_READY", when=_ago(30))

    worker._sweep_notifications()
    assert len(env.sent) == 2


def test_the_marker_records_the_arrival_not_just_the_status(env):
    _on(env)
    _video(env, status="VIDEO_READY", updated_at="2026-01-01T00:00:00Z")
    worker._sweep_notifications()
    assert _marker(env) == "VIDEO_READY@2026-01-01T00:00:00Z"


def test_a_video_moving_mid_sweep_is_not_marked_as_announced(env, monkeypatch):
    """If the row changes between the SELECT and the marker write, the write
    must miss — so the new arrival is picked up next tick. A duplicate message
    is recoverable; a notification nobody ever gets is not."""
    _on(env)
    _video(env, status="VIDEO_READY")

    real_send = worker.discord_notify.send

    def send_then_move(url, payload, **kw):
        real_send(url, payload, **kw)
        _move(env, "VIDEO_READY", when=_ago(0))

    monkeypatch.setattr(worker.discord_notify, "send", send_then_move)
    worker._sweep_notifications()
    monkeypatch.setattr(worker.discord_notify, "send",
                        lambda url, payload, **kw: env.sent.append((url, payload)))

    worker._sweep_notifications()
    assert len(env.sent) == 2


# ── Enabling a trigger does not replay a backlog ─────────────────────────────

def test_enabling_notifications_later_does_not_fire_a_backlog(env):
    """Videos keep reaching checkpoints while the feature is off. Switching it
    on must start announcing from that moment, not replay everything parked —
    the same reasoning as the migration's backfill."""
    _settings(env, discord_webhook_url="")
    for i, status in enumerate(("TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY")):
        _video(env, f"old-{i}", status=status)
    worker._sweep_notifications()          # a tick while off

    _on(env)
    worker._sweep_notifications()
    assert env.sent == []


def test_enabling_one_trigger_does_not_fire_its_own_backlog(env):
    """Same trap one level down: a single disabled trigger accumulates too."""
    _settings(env, discord_webhook_url=URL, notify_video_ready=True)
    _video(env, "parked", status="SCRIPT_READY")
    worker._sweep_notifications()          # script-ready trigger off

    _settings(env, notify_script_ready=True)
    worker._sweep_notifications()
    assert env.sent == []


def test_a_video_arriving_after_enabling_still_notifies(env):
    """The backlog suppression must not also swallow real arrivals."""
    _settings(env, discord_webhook_url="")
    _video(env, "parked", status="VIDEO_READY")
    worker._sweep_notifications()

    _on(env)
    _video(env, "fresh", status="VIDEO_READY")
    worker._sweep_notifications()
    assert len(env.sent) == 1
    assert _marker(env, "parked").startswith("VIDEO_READY@")


# ── Invariants ───────────────────────────────────────────────────────────────

def test_notifying_never_touches_updated_at(env):
    """updated_at is the FIFO ordering key for the render claim — notifying a
    video must not reorder the render queue."""
    _on(env)
    stamp = _ago(9999)
    _video(env, status="VIDEO_READY", updated_at=stamp)
    worker._sweep_notifications()
    assert _sql(env, "SELECT updated_at FROM videos WHERE id = 'vid-1'")[0][0] == stamp


def test_a_failed_send_leaves_the_marker_so_the_next_tick_retries(env, monkeypatch):
    def boom(url, payload, **kw):
        raise discord_notify.DiscordError("Discord returned HTTP 500")

    monkeypatch.setattr(worker.discord_notify, "send", boom)
    _on(env)
    _video(env, status="VIDEO_READY")
    worker._sweep_notifications()
    assert _marker(env) == ""


def test_one_failing_event_does_not_stop_the_others(env, monkeypatch):
    def selective(url, payload, **kw):
        if "Script ready" in payload["embeds"][0]["title"]:
            raise discord_notify.DiscordError("nope")
        env.sent.append((url, payload))

    monkeypatch.setattr(worker.discord_notify, "send", selective)
    _on(env)
    _video(env, "s", status="SCRIPT_READY")
    _video(env, "v", status="VIDEO_READY")
    worker._sweep_notifications()
    assert len(env.sent) == 1
    assert _marker(env, "s") == ""
    assert _marker(env, "v") == _arrival(env, "v")


def test_the_sweep_never_raises(env, monkeypatch):
    """main() has no error handling: an escaping exception restarts the
    container, and the restart counts as a render failure against whatever
    video was rendering."""
    monkeypatch.setattr(worker, "_sweep_notifications_once",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    worker._sweep_notifications()


def test_the_sweep_never_waits_behind_a_render(env):
    """A render can hold a loop for an hour. The sweep runs in the worker,
    whose loop has no render in it, so a notification never waits for one."""
    import inspect
    body = inspect.getsource(worker.main)
    assert "_sweep_notifications()" in body
    assert "_claim_next" not in body and "_render_claimed" not in body


def _auto_pilot(env, project="proj-1", enabled=True, paused=False):
    _settings(env, auto_pilot_enabled=enabled, pipeline_paused=paused,
              auto_pilot_config=json.dumps({"projects": {project: []}, "account_limits": {}}))


def test_a_finished_video_auto_pilot_will_approve_is_not_announced(env):
    """The worker's review thread writes VIDEO_READY whenever a review ends, so
    one can land after the worker's Auto Pilot pass and before this sweep. Auto Pilot
    approves it on the next pass; asking a human to approve it is wrong."""
    _on(env)
    _auto_pilot(env)
    _video(env, status="VIDEO_READY")
    worker._sweep_notifications()
    assert env.sent == []
    # Skipped, not marked: switching Auto Pilot off before it acts announces it.
    assert _marker(env) == ""


def test_auto_pilot_skips_only_its_own_projects_finished_videos(env):
    _on(env)
    _auto_pilot(env, project="proj-1")
    _video(env, "mine", status="VIDEO_READY", project="proj-1")
    _video(env, "other", status="VIDEO_READY", project="proj-2")
    _video(env, "script", status="SCRIPT_READY", project="proj-1")
    worker._sweep_notifications()
    assert len(env.sent) == 2
    assert _marker(env, "mine") == ""
    assert _marker(env, "other") == _arrival(env, "other")
    assert _marker(env, "script") == _arrival(env, "script")


@pytest.mark.parametrize("enabled, paused", [(False, False), (True, True)])
def test_a_finished_video_is_announced_when_auto_pilot_will_not_act(env, enabled, paused):
    """Auto Pilot switched off, or the pipeline paused (which pauses Auto
    Pilot), leaves the approval to a human, so the human hears about it."""
    _on(env)
    _auto_pilot(env, enabled=enabled, paused=paused)
    _video(env, status="VIDEO_READY")
    worker._sweep_notifications()
    assert len(env.sent) == 1


# ── What the messages carry ──────────────────────────────────────────────────

def test_a_topic_message_names_its_project(env):
    _on(env)
    _video(env, status="TOPIC_PROPOSED")
    worker._sweep_notifications()
    assert "Networking" in env.sent[0][1]["embeds"][0]["fields"][0]["value"]


def test_a_script_message_names_the_voice_from_the_roster(env):
    _on(env)
    _settings(env, elevenlabs_voices='[{"name": "Rachel", "voice_id": "v1", "model_id": "eleven_multilingual_v2"}]')
    _video(env, status="SCRIPT_READY", voice_id="v1", script="a b c")
    worker._sweep_notifications()
    fields = {f["name"]: f["value"] for f in env.sent[0][1]["embeds"][0]["fields"]}
    assert fields["Voice"] == "Rachel"


def test_a_script_message_names_its_script_profile(env):
    _on(env)
    _sql(env, "INSERT INTO script_profiles (id, name, created_at, updated_at)"
              " VALUES ('sp1', 'Fireship', ?, ?)", (_ago(9999), _ago(9999)))
    _video(env, status="SCRIPT_READY", script_profile_id="sp1", script="a b")
    worker._sweep_notifications()
    fields = {f["name"]: f["value"] for f in env.sent[0][1]["embeds"][0]["fields"]}
    assert fields["Script profile"] == "Fireship"


def test_a_video_message_carries_the_duration_from_the_timeline(env, tmp_path, monkeypatch):
    # The timeline is found at the video's derived job path, not through the
    # stored timeline_path, which names somewhere else entirely here.
    monkeypatch.setattr(pipeline, "JOBS_DIR", tmp_path / "jobs")
    (tmp_path / "jobs" / "vid-1").mkdir(parents=True)
    (tmp_path / "jobs" / "vid-1" / "timeline.json").write_text('{"audioDurationSeconds": 132}')
    _on(env)
    _video(env, status="VIDEO_READY", timeline_path="/elsewhere/timeline.json")
    worker._sweep_notifications()
    fields = {f["name"]: f["value"] for f in env.sent[0][1]["embeds"][0]["fields"]}
    assert fields["Duration"] == "2m 12s"


def test_a_missing_timeline_does_not_break_the_message(env):
    _on(env)
    _video(env, status="VIDEO_READY", timeline_path="/nope/timeline.json")
    worker._sweep_notifications()
    assert len(env.sent) == 1


def test_a_video_message_summarises_the_ai_review(env):
    """Against the real stored markdown, not a hand-written approximation:
    ai_review._format_feedback leads with the overall verdict on purpose, and
    that ordering is what makes the first prose line the right one to show."""
    import ai_review
    feedback = ai_review._format_feedback("Clean render, no defects.", [], [])
    _on(env)
    _video(env, status="VIDEO_READY", gemini_feedback=feedback)
    worker._sweep_notifications()
    fields = {f["name"]: f["value"] for f in env.sent[0][1]["embeds"][0]["fields"]}
    assert "Clean render, no defects." in fields["AI review"]


def test_a_video_with_no_review_omits_the_verdict(env):
    """gemini_review_enabled can be off, and review fails open — an empty
    field would read as "the reviewer said nothing", which is not the same."""
    _on(env)
    _video(env, status="VIDEO_READY", gemini_feedback="")
    worker._sweep_notifications()
    assert "AI review" not in {f["name"] for f in env.sent[0][1]["embeds"][0]["fields"]}


def test_the_base_url_reaches_the_message(env):
    _on(env, dashboard_base_url="http://box:3000")
    _video(env, status="VIDEO_READY")
    worker._sweep_notifications()
    assert "http://box:3000/library" in env.sent[0][1]["embeds"][0]["description"]


# ── Partially published and failed (TMDEV-191) ───────────────────────────────

def _alerts(env, **extra):
    _settings(env, discord_webhook_url=URL, notify_partially_published=True,
              notify_failed=True, **extra)


def _pub(env, vid, account, status, *, url="", error="", post_id="sp_1", platform="youtube"):
    _sql(env, "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
              " postforme_post_id, status, post_url, error, created_at, updated_at)"
              " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
         (f"{vid}-{account}", vid, platform, account, post_id, status, url, error,
          _ago(60), _ago(60)))


def _comment(env, vid, text, created_at, author="agent"):
    _sql(env, "INSERT INTO comments (video_id, author, content, created_at) VALUES (?, ?, ?, ?)",
         (vid, author, text, created_at))


def test_a_partial_publish_names_the_failed_account_and_links_the_live_post(env):
    _alerts(env)
    _video(env, status="PARTIALLY_PUBLISHED")
    _pub(env, "vid-1", "spc_yt", "PUBLISHED", url="https://youtu.be/abc")
    _pub(env, "vid-1", "spc_ig", "FAILED", error="token expired", platform="instagram")
    worker._sweep_notifications()
    assert len(env.sent) == 1
    embed = env.sent[0][1]["embeds"][0]
    assert "1 of 2" in embed["title"]
    text = json.dumps(embed)
    assert "spc_ig" in text and "token expired" in text and "https://youtu.be/abc" in text
    assert _marker(env) == _arrival(env)


def test_a_failed_video_carries_the_reason_written_when_it_failed(env):
    """The comment written at the arrival, never an older one: a render that
    failed, retried and then failed for good must report the final reason."""
    _alerts(env)
    stamp = _ago(30)
    _video(env, status="FAILED", updated_at=stamp)
    _comment(env, "vid-1", "Render failed: an earlier retry", _ago(600))
    _comment(env, "vid-1", "Render failed 2 times (limit 1) — giving up. Last error: OOM", stamp)
    _comment(env, "vid-1", "a human aside", stamp, author="human")
    worker._sweep_notifications()
    desc = env.sent[0][1]["embeds"][0]["description"]
    assert "Last error: OOM" in desc
    assert "earlier retry" not in desc and "human aside" not in desc


def test_a_failed_video_with_no_fresh_reason_does_not_reuse_a_stale_one(env):
    _alerts(env)
    _video(env, status="FAILED", updated_at=_ago(30))
    _comment(env, "vid-1", "Render failed: an earlier retry", _ago(600))
    worker._sweep_notifications()
    desc = env.sent[0][1]["embeds"][0]["description"]
    assert "earlier retry" not in desc
    assert "No reason was recorded" in desc


def test_a_publish_failure_offers_retry_and_a_render_failure_does_not(env):
    _alerts(env)
    _video(env, "pub-fail", status="FAILED")
    _pub(env, "pub-fail", "spc_yt", "FAILED", error="quota")
    _video(env, "render-fail", status="FAILED")
    worker._sweep_notifications()
    by_id = {p["embeds"][0]["footer"]["text"]: p["embeds"][0]["description"] for _, p in env.sent}
    assert "Retry publishing" in by_id["Tubematic · pub-fail"]
    assert "Retry publishing" not in by_id["Tubematic · render-fail"]


def test_auto_pilot_never_hides_a_failure(env):
    """The Auto Pilot skip is for VIDEO_READY only — Auto Pilot approves those.
    Nothing approves its way out of a failure."""
    _alerts(env)
    _auto_pilot(env)
    _video(env, "partial", status="PARTIALLY_PUBLISHED")
    _video(env, "failed", status="FAILED")
    worker._sweep_notifications()
    assert len(env.sent) == 2


def test_a_publish_that_succeeds_everywhere_sends_no_partial_alert(env, monkeypatch):
    """Negative control, end to end: the publish poll settles the video, then
    the sweep runs. Every account succeeded, so the video is PUBLISHED and
    nothing is announced."""
    _alerts(env, publishing_enabled=True, postforme_api_key="pfm")
    _video(env, status="PUBLISHING")
    for account in ("spc_a", "spc_b"):
        _pub(env, "vid-1", account, "PENDING")
    import postforme
    monkeypatch.setattr(postforme, "get_post_results", lambda key, post_id: [
        {"social_account_id": a, "success": True, "platform_data": {"url": f"https://x/{a}"}}
        for a in ("spc_a", "spc_b")])
    worker._poll_publishing_videos()
    worker._sweep_notifications()
    assert _sql(env, "SELECT status FROM videos WHERE id = 'vid-1'")[0][0] == "PUBLISHED"
    assert env.sent == []


def test_a_publish_that_partly_fails_is_announced_on_the_same_tick(env, monkeypatch):
    """The positive twin: the derivation writes its comment and status before the
    sweep in the same loop, so the alert goes out on the tick it settles."""
    _alerts(env, publishing_enabled=True, postforme_api_key="pfm")
    _video(env, status="PUBLISHING")
    for account in ("spc_a", "spc_b"):
        _pub(env, "vid-1", account, "PENDING")
    import postforme
    monkeypatch.setattr(postforme, "get_post_results", lambda key, post_id: [
        {"social_account_id": "spc_a", "success": True, "platform_data": {"url": "https://x/a"}},
        {"social_account_id": "spc_b", "success": False, "error": {"message": "nope"}}])
    worker._poll_publishing_videos()
    worker._sweep_notifications()
    assert len(env.sent) == 1
    assert "1 of 2" in env.sent[0][1]["embeds"][0]["title"]
