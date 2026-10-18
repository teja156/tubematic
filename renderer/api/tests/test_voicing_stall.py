"""The render worker's stalled-VOICING backstop (TMDEV-112).

VOICING is agent-workable, so a video no tick manages to voice is picked up on
every tick, forever: an agent that refuses generate_voice, a generate_voice that
keeps erroring, a poller that stopped running. Before this, all of those were
indistinguishable from an agent that simply had not run yet — nothing escalated
and nothing reported it. What is tested here is that a stall surfaces, once,
somewhere a human will see it.

Load-bearing behaviours:

  * **It fires once per arrival**, not once per 20-second pass.
  * **It does not fire early.** The threshold is a few poll intervals, read from
    the interval the install actually runs at.
  * **The comment does not depend on Discord.** No webhook, or a failed send,
    still leaves the dashboard-visible comment and the ERROR line.
  * **updated_at is not touched** — it is what the stall is measured on, and the
    FIFO key for the render claim.

Run from renderer/api/: pytest tests/test_voicing_stall.py
"""
import logging
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
MIN = 60


def _ago(secs: float) -> str:
    return time.strftime(_FMT, time.gmtime(time.time() - secs))


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    monkeypatch.delenv("POLL_INTERVAL_MINS", raising=False)
    monkeypatch.setattr(worker, "DB_PATH", db)
    pipeline._init_db(db)
    sent = []
    monkeypatch.setattr(worker.discord_notify, "send",
                        lambda url, payload, **kw: sent.append((url, payload)))
    return SimpleNamespace(db=db, sent=sent)


def _sql(env, query, params=()):
    con = sqlite3.connect(env.db)
    rows = con.execute(query, params).fetchall()
    con.commit()
    con.close()
    return rows


def _settings(env, **kwargs):
    for key, value in kwargs.items():
        _sql(env, "INSERT INTO settings (key, value) VALUES (?, ?)"
                  " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
             (key, str(value)))


def _video(env, vid="vid-1", status="VOICING", age=0, **cols):
    _sql(env, "INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?, ?, ?)",
         ("proj-1", "Networking", _ago(9999)))
    stamp = _ago(age)
    columns = {"id": vid, "project_id": "proj-1", "topic": "How DNS works",
               "strategy": "curriculum", "producibility_score": 8,
               "status": status, "created_at": stamp, "updated_at": stamp, **cols}
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    _sql(env, f"INSERT INTO videos ({names}) VALUES ({marks})", tuple(columns.values()))
    return vid


def _comments(env, vid="vid-1"):
    return [r[0] for r in _sql(
        env, "SELECT content FROM comments WHERE video_id = ? ORDER BY id", (vid,))]


def _updated_at(env, vid="vid-1"):
    return _sql(env, "SELECT updated_at FROM videos WHERE id = ?", (vid,))[0][0]


# ── When it fires ────────────────────────────────────────────────────────────

def test_a_video_stuck_past_three_intervals_gets_a_comment(env):
    _video(env, age=91 * MIN)  # default interval is 30 min
    worker._sweep_stalled_voicing()
    [comment] = _comments(env)
    assert "VOICING" in comment
    assert "1h 31m" in comment


def test_it_does_not_fire_before_the_threshold(env):
    _video(env, age=89 * MIN)
    worker._sweep_stalled_voicing()
    assert _comments(env) == []


def test_the_threshold_follows_the_installed_poll_interval(env):
    """A 10-minute cron reaches "several ticks" three times sooner than the
    default — a fixed threshold would be either noisy or late on one of them."""
    _settings(env, poll_interval_mins=10)
    _video(env, age=31 * MIN)
    worker._sweep_stalled_voicing()
    assert len(_comments(env)) == 1


def test_a_garbage_interval_falls_back_to_the_default(env):
    _settings(env, poll_interval_mins="soon")
    _video(env, age=60 * MIN)
    worker._sweep_stalled_voicing()
    assert _comments(env) == []


def test_it_fires_once_per_arrival_not_once_per_pass(env):
    _settings(env, discord_webhook_url=URL)
    _video(env, age=120 * MIN)
    for _ in range(3):
        worker._sweep_stalled_voicing()
    assert len(_comments(env)) == 1
    assert len(env.sent) == 1


def test_a_fresh_arrival_at_voicing_can_fire_again(env):
    """A pronunciation fix moves a video back into VOICING. If that re-voice
    stalls too, it is a new stall and the human needs to hear about it."""
    _video(env, age=120 * MIN)
    worker._sweep_stalled_voicing()
    _sql(env, "UPDATE videos SET updated_at = ? WHERE id = 'vid-1'", (_ago(100 * MIN),))
    worker._sweep_stalled_voicing()
    assert len(_comments(env)) == 2


def test_other_statuses_are_left_alone(env):
    """SCRIPT_READY sitting for days is a human who has not decided yet, not a
    stall. The checkpoint notifications own those."""
    for vid, status in (("a", "SCRIPT_READY"), ("b", "VOICE_READY"), ("c", "TOPIC_APPROVED")):
        _video(env, vid=vid, status=status, age=999 * MIN)
    worker._sweep_stalled_voicing()
    assert _sql(env, "SELECT COUNT(*) FROM comments")[0][0] == 0


def test_an_archived_video_is_left_alone(env):
    _video(env, age=999 * MIN, archived_at=_ago(1))
    worker._sweep_stalled_voicing()
    assert _comments(env) == []


def test_a_video_that_moves_mid_sweep_is_not_flagged(env):
    """Guarded on updated_at like _mark_notified: if the agent voiced it between
    the SELECT and the flag, there is nothing to report."""
    _video(env, age=120 * MIN)
    row = {"id": "vid-1", "updated_at": _ago(999 * MIN)}  # a stale read
    assert worker._flag_stalled(row, "anything") is False
    assert _comments(env) == []


# ── A paused pipeline is not a stall ─────────────────────────────────────────
#
# poll.py exits before touching workable videos while pipeline_paused is set, so
# nothing is *supposed* to voice anything. Flagging then would be a false alarm,
# and it would spend the arrival's one-shot marker, silencing a real stall after
# resume.

def _marker(env, vid="vid-1"):
    return _sql(env, "SELECT notified_status FROM videos WHERE id = ?", (vid,))[0][0]


def test_nothing_is_flagged_while_the_pipeline_is_paused(env):
    _settings(env, pipeline_paused="true", discord_webhook_url=URL)
    _video(env, age=999 * MIN)
    worker._sweep_stalled_voicing()
    assert _comments(env) == []
    assert env.sent == []
    assert _marker(env) == ""  # the one-shot is still unspent


def test_resuming_does_not_flag_straight_away(env):
    """A video approved during a long pause is already "old" the moment the
    pipeline resumes — before any tick has had a chance to voice it."""
    _settings(env, pipeline_paused="true")
    _video(env, age=999 * MIN)
    worker._sweep_stalled_voicing()
    _settings(env, pipeline_paused="false")
    worker._sweep_stalled_voicing()
    assert _comments(env) == []


def test_a_real_stall_after_resuming_is_still_flagged(env):
    """Three intervals after the last paused pass, the grace window is over and
    a video still in VOICING is a genuine stall."""
    _video(env, age=999 * MIN)
    _settings(env, voicing_stall_paused_at=time.strftime(_FMT, time.gmtime(time.time() - 91 * MIN)))
    worker._sweep_stalled_voicing()
    assert len(_comments(env)) == 1


def test_the_grace_window_is_measured_from_the_last_paused_pass(env):
    _video(env, age=999 * MIN)
    _settings(env, voicing_stall_paused_at=time.strftime(_FMT, time.gmtime(time.time() - 89 * MIN)))
    worker._sweep_stalled_voicing()
    assert _comments(env) == []


# ── Where it surfaces ────────────────────────────────────────────────────────

def test_updated_at_is_not_touched(env):
    _video(env, age=120 * MIN)
    before = _updated_at(env)
    worker._sweep_stalled_voicing()
    assert _updated_at(env) == before


def test_it_logs_at_error_level(env, caplog):
    _video(env, age=120 * MIN)
    with caplog.at_level(logging.ERROR, logger=worker.log.name):
        worker._sweep_stalled_voicing()
    assert any(r.levelno == logging.ERROR and "VOICING" in r.getMessage()
               for r in caplog.records)


def test_discord_is_alerted_when_a_webhook_is_set(env):
    """Regardless of the per-checkpoint toggles: those choose which routine
    checkpoints are announced, and this is not a checkpoint — it is the pipeline
    being stuck, which is what a configured webhook is for."""
    _settings(env, discord_webhook_url=URL, notify_script_ready="false")
    _video(env, age=120 * MIN)
    worker._sweep_stalled_voicing()
    [(url, payload)] = env.sent
    assert url == URL
    assert "voicing" in payload["embeds"][0]["title"].lower()


def test_no_webhook_still_comments(env):
    _video(env, age=120 * MIN)
    worker._sweep_stalled_voicing()
    assert env.sent == []
    assert len(_comments(env)) == 1


def test_a_failed_discord_send_keeps_the_comment_and_does_not_repeat_it(env, monkeypatch):
    """The comment is the record; Discord is a courtesy on top. Retrying the
    send by leaving the marker unadvanced would post a duplicate comment every
    20 seconds for as long as Discord is down."""
    def boom(url, payload, **kw):
        raise discord_notify.DiscordError("Discord returned HTTP 500")
    monkeypatch.setattr(worker.discord_notify, "send", boom)
    _settings(env, discord_webhook_url=URL)
    _video(env, age=120 * MIN)
    worker._sweep_stalled_voicing()
    worker._sweep_stalled_voicing()
    assert len(_comments(env)) == 1


def test_the_sweep_never_raises(env, monkeypatch):
    """Same contract as the other sweeps: an escaping exception restarts the
    container, which counts as a render failure against an unrelated video."""
    monkeypatch.setattr(worker, "_sweep_stalled_voicing_once",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    worker._sweep_stalled_voicing()


def test_the_checkpoint_sweep_is_unaffected(env):
    """Both sweeps share notified_status. VOICING is not one of the checkpoint
    sweep's statuses, so a stall marker must not make it announce anything."""
    _settings(env, discord_webhook_url=URL, notify_topic_proposed="true",
              notify_script_ready="true", notify_video_ready="true")
    _video(env, age=120 * MIN)
    worker._sweep_stalled_voicing()
    env.sent.clear()
    worker._sweep_notifications()
    assert env.sent == []
