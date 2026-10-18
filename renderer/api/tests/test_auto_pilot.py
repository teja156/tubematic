"""Auto Pilot (TMDEV-139): the /autopilot routes and the worker's sweep.

Auto Pilot removes every human checkpoint for the projects it is switched on
for, so most of this file is about what it must NOT touch: an unselected
project, a paused pipeline, a video a dashboard approval would refuse, an
account that is over its daily number, a post a human cancelled.

Run from renderer/api/: pytest tests/test_auto_pilot.py
"""
import datetime as dt
import json
import os
import sqlite3
import time
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
import postforme
import worker

_FMT = "%Y-%m-%dT%H:%M:%SZ"
ACCOUNTS = [{"id": "spc_yt", "platform": "youtube"}, {"id": "spc_ig", "platform": "instagram"}]


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _at(delta_secs: float = 0) -> str:
    return time.strftime(_FMT, time.gmtime(time.time() + delta_secs))


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = str(tmp_path / "test.db")
    monkeypatch.setenv("TUBEMATIC_DB", db)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = tmp_path / "output_videos"
    out.mkdir()
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)
    monkeypatch.setattr(worker, "DB_PATH", db)
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "UTC")
    monkeypatch.setattr(worker, "_auto_pilot_retry", {})
    pipeline._init_db(db)
    return SimpleNamespace(db=db, out=out)


@pytest.fixture
def client(env):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(pipeline.create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _sql(env, query, params=()):
    con = sqlite3.connect(env.db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(query, params).fetchall()]
    con.commit()
    con.close()
    return rows


def _setting(env, key, value):
    _sql(env, "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def _project(env, pid):
    _sql(env, "INSERT OR IGNORE INTO projects (id, name, created_at) VALUES (?, ?, 'now')",
         (pid, pid))


def _auto_pilot(env, projects, limits=None, enabled=True, gap_mins=0, max_in_flight=0):
    """Switch Auto Pilot on for `projects` ({project_id: [account ids]})."""
    for pid in projects:
        _project(env, pid)
    _setting(env, "auto_pilot_enabled", "true" if enabled else "false")
    _setting(env, "auto_pilot_gap_mins", str(gap_mins))
    _setting(env, "auto_pilot_max_in_flight", str(max_in_flight))
    _setting(env, "auto_pilot_config",
             json.dumps({"projects": projects, "account_limits": limits or {}}))


def _publishing(env, allowed=("spc_yt", "spc_ig")):
    _setting(env, "publishing_enabled", "true")
    _setting(env, "postforme_api_key", "pfm")
    _setting(env, "publishing_accounts", json.dumps(list(allowed)))


def _video(env, vid, status, project="auto", file=False, **cols):
    _project(env, project)
    cols = {"id": vid, "project_id": project, "topic": "DNS resolution", "status": status,
            "strategy": "curriculum", "video_path": f"/output_videos/{project}/{vid}.mp4",
            "created_at": _at(-3600), "updated_at": _at(-3600), **cols}
    _sql(env, "INSERT INTO videos (%s) VALUES (%s)"
         % (",".join(cols), ",".join("?" * len(cols))), tuple(cols.values()))
    if file:
        mp4 = env.out / project / f"{vid}.mp4"
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"mp4")


def _row(env, vid):
    return _sql(env, "SELECT * FROM videos WHERE id = ?", (vid,))[0]


def _comments(env, vid):
    return [c["content"] for c in _sql(
        env, "SELECT content FROM comments WHERE video_id = ? ORDER BY id", (vid,))]


def _posted(env, account, when, vid=None, status="PUBLISHED"):
    """An existing post on `account` at `when` (a UTC stamp)."""
    vid = vid or f"old-{account}-{when}"
    _video(env, vid, "PUBLISHED", project="other")
    _sql(env,
         "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
         " postforme_post_id, status, published_at, created_at, updated_at)"
         " VALUES (?, ?, 'youtube', ?, 'sp_old', ?, ?, ?, ?)",
         (f"pub-{vid}", vid, account, status, when, when, when))


def _postforme():
    """Patch the four postforme calls a publish makes; yields the create_post mock."""
    stack = mock.patch.multiple(
        postforme,
        list_accounts=mock.Mock(return_value=ACCOUNTS),
        create_upload_url=mock.Mock(return_value={"upload_url": "https://u",
                                                  "media_url": "https://m"}),
        upload_media=mock.Mock(),
        create_post=mock.Mock(return_value={"id": "sp_1"}),
    )
    return stack


# ── the configuration routes ─────────────────────────────────────────────────

def test_auto_pilot_is_off_and_empty_by_default(client):
    body = client.get("/autopilot").get_json()
    assert body["enabled"] is False
    assert body["projects"] == {} and body["account_limits"] == {}
    assert body["gap_mins"] == int(pipeline.SETTINGS_SPEC["auto_pilot_gap_mins"][1])
    assert body["default_daily_limit"] == pipeline.AUTO_PILOT_DEFAULT_DAILY
    # No limit unless one is set: 0 means unlimited.
    assert body["max_in_flight"] == 0 and body["in_flight"] == 0


def test_the_configuration_round_trips(env, client):
    _project(env, "auto")
    _publishing(env)
    saved = client.post("/autopilot", json={
        "enabled": True, "gap_mins": 90,
        "projects": {"auto": ["spc_yt"]}, "account_limits": {"spc_yt": 3}})
    assert saved.status_code == 200
    body = client.get("/autopilot").get_json()
    assert (body["enabled"], body["gap_mins"]) == (True, 90)
    assert body["projects"] == {"auto": ["spc_yt"]}
    assert body["account_limits"] == {"spc_yt": 3}


def test_a_project_may_be_selected_with_no_accounts(env, client):
    # It then auto-approves and waits at VIDEO_APPROVED, and it needs no
    # publishing setup at all.
    _project(env, "auto")
    saved = client.post("/autopilot", json={
        "enabled": True, "gap_mins": 0, "projects": {"auto": []}, "account_limits": {}})
    assert saved.status_code == 200


def test_an_account_outside_the_allowlist_is_refused(env, client):
    # Auto Pilot must never be a way to post to an account Socials has off.
    _project(env, "auto")
    _publishing(env, allowed=("spc_yt",))
    r = client.post("/autopilot", json={
        "enabled": True, "gap_mins": 0,
        "projects": {"auto": ["spc_ig"]}, "account_limits": {}})
    assert r.status_code == 400 and "spc_ig" in r.get_json()["error"]
    assert client.get("/autopilot").get_json()["enabled"] is False


def test_an_account_that_left_the_allowlist_never_blocks_a_save(env, client):
    """An account selected earlier and then switched off on the Socials page is
    still in the stored configuration. Refusing every save that carries it
    would block the one save that matters most: turning Auto Pilot off."""
    _project(env, "auto")
    _publishing(env)
    cfg = {"enabled": True, "gap_mins": 0,
           "projects": {"auto": ["spc_ig", "spc_yt"]}, "account_limits": {}}
    assert client.post("/autopilot", json=cfg).status_code == 200
    _publishing(env, allowed=("spc_yt",))

    off = client.post("/autopilot", json={**cfg, "enabled": False})
    assert off.status_code == 200 and off.get_json()["enabled"] is False
    # Kept for that project only: it is not a way to add the account elsewhere.
    _project(env, "other")
    r = client.post("/autopilot", json={
        **cfg, "projects": {"auto": ["spc_ig", "spc_yt"], "other": ["spc_ig"]}})
    assert r.status_code == 400 and "spc_ig" in r.get_json()["error"]


@pytest.mark.parametrize("body", [
    {"enabled": True, "gap_mins": 0, "projects": {"ghost": []}, "account_limits": {}},
    {"enabled": True, "gap_mins": 0, "projects": {"auto": "spc_yt"}, "account_limits": {}},
    {"enabled": True, "gap_mins": 0, "projects": {}, "account_limits": {"spc_yt": -1}},
    {"enabled": True, "gap_mins": 0, "projects": {}, "account_limits": {"spc_yt": 51}},
    {"enabled": True, "gap_mins": 0, "projects": {}, "account_limits": {"spc_yt": True}},
    {"enabled": True, "gap_mins": 10081, "projects": {}, "account_limits": {}},
    {"enabled": "yes", "gap_mins": 0, "projects": {}, "account_limits": {}},
    {"gap_mins": 0, "projects": {}, "account_limits": {}},
    {"enabled": True, "gap_mins": 0, "max_in_flight": 501, "projects": {}, "account_limits": {}},
    {"enabled": True, "gap_mins": 0, "max_in_flight": -1, "projects": {}, "account_limits": {}},
    {"enabled": True, "gap_mins": 0, "max_in_flight": "lots", "projects": {},
     "account_limits": {}},
])
def test_a_malformed_configuration_writes_nothing(env, client, body):
    _project(env, "auto")
    assert client.post("/autopilot", json=body).status_code == 400
    assert _sql(env, "SELECT key FROM settings WHERE key LIKE 'auto_pilot%'") == []


def test_waiting_counts_what_switching_a_project_on_would_act_on(env, client):
    _video(env, "a", "TOPIC_PROPOSED")
    _video(env, "b", "TOPIC_PROPOSED")
    _video(env, "c", "SCRIPT_READY")
    _video(env, "d", "RENDERING")
    _video(env, "e", "VIDEO_READY", archived_at=_at())
    waiting = client.get("/autopilot").get_json()["waiting"]
    assert waiting == {"auto": {"TOPIC_PROPOSED": 2, "SCRIPT_READY": 1}}


def test_a_corrupt_config_row_reads_as_nothing_selected(env):
    _setting(env, "auto_pilot_config", "{not json")
    with pipeline._db(env.db) as con:
        assert pipeline._auto_pilot_config(con) == {"projects": {}, "account_limits": {}}
    _setting(env, "auto_pilot_config", json.dumps(
        {"projects": {"p": "x", "q": ["a", 1]}, "account_limits": {"a": "3", "b": 2}}))
    with pipeline._db(env.db) as con:
        assert pipeline._auto_pilot_config(con) == {
            "projects": {"q": ["a"]}, "account_limits": {"b": 2}}


# ── the approve pass ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,approved", [
    ("TOPIC_PROPOSED", "TOPIC_APPROVED"),
    ("SCRIPT_READY", "VOICING"),
    ("VIDEO_READY", "VIDEO_APPROVED"),
])
def test_each_checkpoint_is_approved(env, status, approved):
    _auto_pilot(env, {"auto": []})
    _video(env, "v", status)
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == approved
    assert any("Auto Pilot" in c for c in _comments(env, "v"))


def test_an_approval_clears_a_stuck_flag_like_a_human_one(env):
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "TOPIC_PROPOSED", agent_no_progress_count=3, agent_stuck_at=_at())
    worker._sweep_auto_pilot()
    row = _row(env, "v")
    assert (row["agent_no_progress_count"], row["agent_stuck_at"]) == (0, None)


def test_a_project_not_selected_is_left_at_its_checkpoint(env):
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "SCRIPT_READY", project="manual-only")
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "SCRIPT_READY"
    assert _comments(env, "v") == []


def test_nothing_is_approved_while_auto_pilot_is_off(env):
    _auto_pilot(env, {"auto": []}, enabled=False)
    _video(env, "v", "SCRIPT_READY")
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "SCRIPT_READY"


def test_nothing_is_approved_while_the_pipeline_is_paused(env):
    # Approving a script spends ElevenLabs credit; pause is the stop-spend switch.
    _auto_pilot(env, {"auto": []})
    _setting(env, "pipeline_paused", "true")
    _video(env, "v", "SCRIPT_READY")
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "SCRIPT_READY"


def test_an_archived_video_is_never_moved(env):
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "VIDEO_READY", archived_at=_at())
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "VIDEO_READY"


def test_other_statuses_are_not_touched(env):
    _auto_pilot(env, {"auto": []})
    for i, status in enumerate(("TOPIC_APPROVED", "VOICING", "RENDER_QUEUED",
                                "REVISION_REQUESTED", "TOPIC_REJECTED", "FAILED")):
        _video(env, f"v{i}", status)
    worker._sweep_auto_pilot()
    assert [r["status"] for r in _sql(env, "SELECT status FROM videos ORDER BY id")] == [
        "TOPIC_APPROVED", "VOICING", "RENDER_QUEUED", "REVISION_REQUESTED",
        "TOPIC_REJECTED", "FAILED"]


def test_an_illustrated_topic_with_no_openai_key_is_not_approved(env):
    """The dashboard refuses this approval; Auto Pilot must not wave it through.
    It says so once, however many times the worker ticks."""
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "TOPIC_PROPOSED", visual_style="illustrated")
    for _ in range(3):
        worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "TOPIC_PROPOSED"
    notes = _comments(env, "v")
    assert len(notes) == 1 and "OpenAI" in notes[0]


def test_a_blocked_topic_is_approved_once_the_cause_is_fixed(env):
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "TOPIC_PROPOSED", visual_style="illustrated")
    worker._sweep_auto_pilot()
    _setting(env, "openai_api_key", "sk-test")
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "TOPIC_APPROVED"


def test_a_script_its_voice_cannot_speak_is_not_approved(env):
    # <ipa> is eleven_v3 only; approving this would send it on to a voicing
    # the voice refuses.
    _auto_pilot(env, {"auto": []})
    _setting(env, "elevenlabs_voices", json.dumps(
        [{"name": "V2", "voice_id": "v2", "model_id": "eleven_multilingual_v2"}]))
    _setting(env, "elevenlabs_voice_id", "v2")
    _video(env, "v", "SCRIPT_READY", voice_id="v2",
           script='Say <ipa ph="təˈmeɪtoʊ">tomato</ipa> now.')
    for _ in range(2):
        worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "SCRIPT_READY"
    assert len(_comments(env, "v")) == 1


def test_a_failing_sweep_never_escapes_the_worker_loop(env):
    # An escaping exception restarts the container, which the render
    # reconciliation counts as a render failure.
    _auto_pilot(env, {"auto": []})
    with mock.patch.object(worker, "_auto_pilot_once", side_effect=RuntimeError("boom")):
        worker._sweep_auto_pilot()


def test_an_auto_approved_checkpoint_is_never_announced(env, monkeypatch):
    sent = []
    monkeypatch.setattr(worker.discord_notify, "send", lambda *a, **k: sent.append(a) or True)
    _setting(env, "discord_webhook_url", "https://discord.test/hook")
    _setting(env, "notify_script_ready", "true")
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "SCRIPT_READY")
    worker._sweep_auto_pilot()
    worker._sweep_notifications()
    assert sent == []


# ── the publish pass ─────────────────────────────────────────────────────────

def test_an_approved_video_is_posted_to_its_projects_accounts(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt", "spc_ig"]})
    _video(env, "v", "VIDEO_APPROVED", file=True, publish_title="DNS in 60s",
           publish_description="How a name becomes an address.")
    with _postforme():
        worker._sweep_auto_pilot()
        create = postforme.create_post.call_args.kwargs
    assert create["social_account_ids"] == ["spc_yt", "spc_ig"]
    assert create["scheduled_at"] is None
    assert create["caption"].startswith("DNS in 60s")
    assert _row(env, "v")["status"] == "PUBLISHING"
    assert any("Auto Pilot" in c for c in _comments(env, "v"))


def test_auto_posts_are_public(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
        configs = postforme.create_post.call_args.kwargs["platform_configurations"]
    assert configs["youtube"]["privacy_status"] == "public"


def test_a_recent_post_schedules_the_next_one_a_gap_later(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 10}, gap_mins=240)
    _posted(env, "spc_yt", _at(-3600))
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
        sent_at = postforme.create_post.call_args.kwargs["scheduled_at"]
    row = _row(env, "v")
    assert row["status"] == "SCHEDULED" and row["scheduled_at"] == sent_at
    due = dt.datetime.strptime(sent_at, _FMT)
    expected = _utcnow() + dt.timedelta(hours=3)
    assert abs((due - expected).total_seconds()) < 120


def test_an_account_at_its_daily_number_waits_for_tomorrow(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 1})
    today = _utcnow().strftime("%Y-%m-%dT00:00:01Z")
    _posted(env, "spc_yt", today)
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
    tomorrow = (_utcnow() + dt.timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
    assert _row(env, "v")["scheduled_at"] == tomorrow


def test_an_account_with_no_stored_number_posts_once_a_day(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _posted(env, "spc_yt", _utcnow().strftime("%Y-%m-%dT00:00:01Z"))
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "SCHEDULED"


def test_a_failed_post_does_not_use_up_the_day(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 1})
    _posted(env, "spc_yt", _utcnow().strftime("%Y-%m-%dT00:00:01Z"),
            status="FAILED")
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "PUBLISHING"


def test_auto_pilots_own_queue_spreads_across_days(env):
    """Three approved videos, one a day: each tick's schedule counts toward the
    next, so they land today, tomorrow and the day after."""
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 1})
    for i in range(3):
        _video(env, f"v{i}", "VIDEO_APPROVED", file=True, updated_at=_at(-3600 + i))
    with _postforme():
        for _ in range(3):
            worker._sweep_auto_pilot()
    days = [_row(env, f"v{i}")["scheduled_at"][:10] for i in range(3)]
    today = _utcnow().date()
    assert days[0] == ""
    assert days[1:] == [str(today + dt.timedelta(days=1)), str(today + dt.timedelta(days=2))]


def test_one_video_is_started_per_pass(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 10})
    _video(env, "v0", "VIDEO_APPROVED", file=True, updated_at=_at(-200))
    _video(env, "v1", "VIDEO_APPROVED", file=True, updated_at=_at(-100))
    with _postforme():
        worker._sweep_auto_pilot()
    assert _row(env, "v0")["status"] == "PUBLISHING"
    assert _row(env, "v1")["status"] == "VIDEO_APPROVED"


def test_a_project_with_no_accounts_waits_at_video_approved(env):
    _publishing(env)
    _auto_pilot(env, {"auto": []})
    _video(env, "v", "VIDEO_READY", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
        worker._sweep_auto_pilot()
        postforme.create_post.assert_not_called()
    assert _row(env, "v")["status"] == "VIDEO_APPROVED"


@pytest.mark.parametrize("accounts,limits,allowed", [
    ([], {}, ("spc_yt",)),
    (["spc_yt"], {"spc_yt": 0}, ("spc_yt",)),
    (["spc_yt"], {}, ()),
])
def test_a_video_with_nowhere_to_post_costs_no_postforme_call(env, accounts, limits, allowed):
    """Waiting at Video Approved is a supported, indefinite state. Asking
    postforme for its accounts on every 20-second tick while in it would be
    thousands of pointless requests a day."""
    _publishing(env, allowed=allowed)
    _auto_pilot(env, {"auto": accounts}, limits=limits)
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        for _ in range(3):
            worker._sweep_auto_pilot()
        postforme.list_accounts.assert_not_called()
    assert _row(env, "v")["status"] == "VIDEO_APPROVED"


@pytest.mark.parametrize("why", ["off_allowlist", "disconnected", "zero_a_day"])
def test_an_unusable_account_is_dropped_from_the_post(env, why):
    _publishing(env, allowed=("spc_yt",) if why == "off_allowlist" else ("spc_yt", "spc_ig"))
    limits = {"spc_ig": 0} if why == "zero_a_day" else {}
    _auto_pilot(env, {"auto": ["spc_yt", "spc_ig"]}, limits=limits)
    _video(env, "v", "VIDEO_APPROVED", file=True)
    live = ACCOUNTS[:1] if why == "disconnected" else ACCOUNTS
    with _postforme():
        postforme.list_accounts.return_value = live
        worker._sweep_auto_pilot()
        assert postforme.create_post.call_args.kwargs["social_account_ids"] == ["spc_yt"]


def test_nothing_is_posted_with_publishing_disabled(env):
    _publishing(env)
    _setting(env, "publishing_enabled", "false")
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
        postforme.list_accounts.assert_not_called()
    assert _row(env, "v")["status"] == "VIDEO_APPROVED"


def test_a_video_in_an_unselected_project_is_never_posted(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "VIDEO_APPROVED", project="manual-only", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
        postforme.create_post.assert_not_called()


def test_a_cancelled_schedule_is_not_scheduled_again(env, client):
    """Without the hold, the cancel returns the video to VIDEO_APPROVED and the
    next tick schedules it again — a human could never pull a post back."""
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 10}, gap_mins=240)
    _posted(env, "spc_yt", _at(-60))
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        worker._sweep_auto_pilot()
        assert _row(env, "v")["status"] == "SCHEDULED"
        with mock.patch("postforme.delete_post"):
            assert client.post("/videos/v/schedule/cancel").status_code == 200
        postforme.create_post.reset_mock()
        worker._sweep_auto_pilot()
        postforme.create_post.assert_not_called()
    row = _row(env, "v")
    assert (row["status"], row["auto_pilot_hold"]) == ("VIDEO_APPROVED", 1)


def test_a_failed_upload_is_not_retried_every_tick(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        postforme.upload_media.side_effect = postforme.PostformeError("upload failed")
        for _ in range(3):
            worker._sweep_auto_pilot()
        assert postforme.upload_media.call_count == 1
    assert _row(env, "v")["status"] == "VIDEO_APPROVED"
    assert len(_comments(env, "v")) == 1


def test_a_video_with_no_rendered_file_says_so_once(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "VIDEO_APPROVED", file=False)
    with _postforme():
        for _ in range(3):
            worker._sweep_auto_pilot()
    notes = _comments(env, "v")
    assert len(notes) == 1 and "No rendered video file" in notes[0]


def test_a_backed_off_video_does_not_block_the_next_one(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 10})
    _video(env, "broken", "VIDEO_APPROVED", file=False, updated_at=_at(-200))
    _video(env, "good", "VIDEO_APPROVED", file=True, updated_at=_at(-100))
    with _postforme():
        worker._sweep_auto_pilot()
        worker._sweep_auto_pilot()
    assert _row(env, "good")["status"] == "PUBLISHING"


def test_an_unreachable_postforme_defers_the_pass(env):
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "VIDEO_APPROVED", file=True)
    with _postforme():
        postforme.list_accounts.side_effect = postforme.PostformeError("down")
        worker._sweep_auto_pilot()
        postforme.create_post.assert_not_called()
    assert _row(env, "v")["status"] == "VIDEO_APPROVED"
    assert _comments(env, "v") == []


# ── the in-progress limit ────────────────────────────────────────────────────
#
# auto_pilot_max_in_flight (TMDEV-150, replacing TMDEV-143's scheduled-post
# ceiling). It counts every video past the paid gate that has not published,
# and holds back only that gate (SCRIPT_READY -> VOICING) and, once full, topic
# approvals. Approving a finished video and scheduling it always run: they move
# a video within the count, and scheduling is the only thing that drains it.

VOICED = {"voice_file_path": "/jobs/v/audio.mp3"}


def _count(env, projects=("auto",)):
    with pipeline._db(env.db) as con:
        return pipeline.in_flight_count(con, list(projects))


def _statuses(env, *vids):
    return [_row(env, v)["status"] for v in vids]


def test_no_limit_is_the_default_and_ignores_the_backlog(env):
    assert pipeline.SETTINGS_SPEC["auto_pilot_max_in_flight"] == ("int", "0")
    assert "auto_pilot_max_scheduled" not in pipeline.SETTINGS_SPEC
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 10})
    for i in range(5):
        _video(env, f"b{i}", "VIDEO_APPROVED", **VOICED)
        _video(env, f"q{i}", "SCHEDULED", project="other", scheduled_at=_at(3600))
    _video(env, "t", "TOPIC_PROPOSED")
    _video(env, "s", "SCRIPT_READY", script="Plain words.")
    worker._sweep_auto_pilot()
    assert _statuses(env, "t", "s") == ["TOPIC_APPROVED", "VOICING"]


@pytest.mark.parametrize("status,project,cols,counted", [
    # past the gate, in an Auto Pilot project
    ("VOICING", "auto", {}, True),             # no voice file yet: the status counts
    ("VOICE_READY", "auto", VOICED, True),
    ("RENDERING", "auto", VOICED, True),
    ("VIDEO_READY", "auto", VOICED, True),
    ("VIDEO_APPROVED", "auto", VOICED, True),
    ("PUBLISHING", "auto", VOICED, True),
    ("SCHEDULED", "auto", {**VOICED, "scheduled_at": _at(3600)}, True),
    # a revision keeps its slot wherever it goes back to
    ("SCRIPT_READY", "auto", VOICED, True),
    ("TOPIC_PROPOSED", "auto", VOICED, True),
    ("REVISION_REQUESTED", "auto", VOICED, True),
    # never voiced
    ("TOPIC_PROPOSED", "auto", {}, False),
    ("SCRIPT_READY", "auto", {}, False),
    ("REVISION_REQUESTED", "auto", {}, False),
    # out of the pipeline
    ("PUBLISHED", "auto", VOICED, False),
    ("FAILED", "auto", VOICED, False),
    ("TOPIC_REJECTED", "auto", {}, False),
    ("VIDEO_APPROVED", "auto", {**VOICED, "archived_at": _at()}, False),
    # held: nothing in the dashboard clears it, so counting it would shut the gate for good
    ("VIDEO_APPROVED", "auto", {**VOICED, "auto_pilot_hold": 1}, False),
    # a project not on Auto Pilot: only its future posts count
    ("VIDEO_APPROVED", "other", VOICED, False),
    ("SCHEDULED", "other", {"scheduled_at": _at(3600)}, True),   # a human's post counts
    ("SCHEDULED", "other", {"scheduled_at": _at(-60)}, False),   # overdue, not yet released
    ("PUBLISHING", "other", {"scheduled_at": _at(3600)}, False), # ambiguous, reconciling
    ("SCHEDULED", "other", {"scheduled_at": _at(3600), "archived_at": _at()}, False),
])
def test_what_the_count_includes(env, status, project, cols, counted):
    _video(env, "v", status, project=project, **cols)
    assert _count(env) == int(counted)


def test_with_no_project_selected_only_future_posts_count(env):
    _video(env, "a", "VIDEO_APPROVED", **VOICED)
    _video(env, "q", "SCHEDULED", project="other", scheduled_at=_at(3600))
    assert _count(env, projects=()) == 1


def test_a_two_account_post_counts_once(env, client):
    _video(env, "q0", "SCHEDULED", project="other", scheduled_at=_at(3600))
    for account in ("spc_yt", "spc_ig"):
        _sql(env,
             "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
             " status, created_at, updated_at) VALUES (?, 'q0', 'youtube', ?, 'PENDING',"
             " 'now', 'now')", (f"pub-{account}", account))
    _video(env, "q1", "SCHEDULED", project="other", scheduled_at=_at(3600))
    assert client.get("/autopilot").get_json()["in_flight"] == 2


def test_new_scripts_are_voiced_only_up_to_the_room_left(env):
    """3 new scripts, 1 in flight, a limit of 3: exactly 2 voiced, oldest first,
    in a single pass — the gate never overshoots."""
    _auto_pilot(env, {"auto": []}, max_in_flight=3)
    _video(env, "busy", "RENDERING", **VOICED)
    for i in range(3):
        _video(env, f"s{i}", "SCRIPT_READY", script="Plain words.", updated_at=_at(-300 + i))
    worker._sweep_auto_pilot()
    assert _statuses(env, "s0", "s1", "s2") == ["VOICING", "VOICING", "SCRIPT_READY"]
    worker._sweep_auto_pilot()     # now full: the next pass adds none
    assert _row(env, "s2")["status"] == "SCRIPT_READY"


def test_a_backlog_over_the_limit_voices_nothing(env):
    _auto_pilot(env, {"auto": []}, max_in_flight=2)
    for i in range(4):
        _video(env, f"b{i}", "VIDEO_APPROVED", **VOICED)
    _video(env, "s", "SCRIPT_READY", script="Plain words.")
    worker._sweep_auto_pilot()
    assert _row(env, "s")["status"] == "SCRIPT_READY"
    assert _comments(env, "s") == []


def test_topics_wait_only_while_the_limit_is_full(env):
    _auto_pilot(env, {"auto": []}, max_in_flight=1)
    _video(env, "busy", "RENDERING", **VOICED)
    _video(env, "t", "TOPIC_PROPOSED")
    worker._sweep_auto_pilot()
    assert _row(env, "t")["status"] == "TOPIC_PROPOSED"
    # Room again: topics are not budgeted, so every waiting one is approved.
    _sql(env, "UPDATE videos SET status = 'PUBLISHED' WHERE id = 'busy'")
    _video(env, "t2", "TOPIC_PROPOSED")
    worker._sweep_auto_pilot()
    assert _statuses(env, "t", "t2") == ["TOPIC_APPROVED", "TOPIC_APPROVED"]


def test_a_voiced_revision_keeps_its_slot_and_is_revoiced_at_the_limit(env):
    """A revision back at SCRIPT_READY is still counted, so a new script cannot
    take its slot; and it passes the gate without room, or a full set of them
    would wait at SCRIPT_READY forever."""
    _auto_pilot(env, {"auto": []}, max_in_flight=1)
    _video(env, "rev", "SCRIPT_READY", script="Plain words.", updated_at=_at(-60), **VOICED)
    _video(env, "new", "SCRIPT_READY", script="Plain words.", updated_at=_at(-600))
    worker._sweep_auto_pilot()
    assert _statuses(env, "rev", "new") == ["VOICING", "SCRIPT_READY"]


def test_a_full_set_of_revisions_is_never_deadlocked(env):
    _auto_pilot(env, {"auto": []}, max_in_flight=2)
    for vid in ("r0", "r1"):
        _video(env, vid, "SCRIPT_READY", script="Plain words.", **VOICED)
    _video(env, "t", "TOPIC_PROPOSED", **VOICED)   # a re-scoped topic, voiced before
    worker._sweep_auto_pilot()
    assert _statuses(env, "r0", "r1", "t") == ["VOICING", "VOICING", "TOPIC_APPROVED"]


def test_at_the_limit_finished_videos_are_still_approved_and_scheduled(env):
    """The fix for videos stranded at VIDEO_APPROVED: the old ceiling stopped
    the scheduler as well, so nothing drained while it was full."""
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]}, limits={"spc_yt": 10}, max_in_flight=1)
    _video(env, "r", "VIDEO_READY", file=True, **VOICED)
    _video(env, "a", "VIDEO_APPROVED", file=True, updated_at=_at(-7200), **VOICED)
    _video(env, "s", "SCRIPT_READY", script="Plain words.")
    _video(env, "t", "TOPIC_PROPOSED")
    with _postforme():
        worker._sweep_auto_pilot()
        assert postforme.create_post.call_count == 1
    assert _statuses(env, "r", "a", "s", "t") == [
        "VIDEO_APPROVED", "PUBLISHING", "SCRIPT_READY", "TOPIC_PROPOSED"]


def test_nothing_new_is_voiced_while_posting_is_blocked(env):
    """The reported defect: with nowhere to post, nothing reaches SCHEDULED, so
    the old ceiling never bound and production ran on without limit."""
    _auto_pilot(env, {"auto": []}, max_in_flight=3)
    for i in range(5):
        _video(env, f"a{i}", "VIDEO_APPROVED", **VOICED)
    _video(env, "s", "SCRIPT_READY", script="Plain words.")
    for _ in range(3):
        worker._sweep_auto_pilot()
    assert _row(env, "s")["status"] == "SCRIPT_READY"


def test_a_held_video_never_holds_the_gate_shut(env):
    _auto_pilot(env, {"auto": []}, max_in_flight=1)
    _video(env, "held", "VIDEO_APPROVED", auto_pilot_hold=1, **VOICED)
    _video(env, "s", "SCRIPT_READY", script="Plain words.")
    worker._sweep_auto_pilot()
    assert _row(env, "s")["status"] == "VOICING"


def test_one_video_publishing_lets_exactly_one_more_be_voiced(env):
    """It tops up at the limit rather than draining to zero."""
    _auto_pilot(env, {"auto": []}, max_in_flight=2)
    _video(env, "a0", "VIDEO_APPROVED", **VOICED)
    _video(env, "a1", "VIDEO_APPROVED", **VOICED)
    _video(env, "s0", "SCRIPT_READY", script="Plain words.", updated_at=_at(-200))
    _video(env, "s1", "SCRIPT_READY", script="Plain words.", updated_at=_at(-100))
    worker._sweep_auto_pilot()
    assert _statuses(env, "s0", "s1") == ["SCRIPT_READY", "SCRIPT_READY"]
    _sql(env, "UPDATE videos SET status = 'PUBLISHED' WHERE id = 'a0'")
    worker._sweep_auto_pilot()
    worker._sweep_auto_pilot()
    assert _statuses(env, "s0", "s1") == ["VOICING", "SCRIPT_READY"]


def test_a_blocked_script_uses_no_room(env):
    _auto_pilot(env, {"auto": []}, max_in_flight=1)
    _setting(env, "elevenlabs_voices", json.dumps(
        [{"name": "V2", "voice_id": "v2", "model_id": "eleven_multilingual_v2"}]))
    _setting(env, "elevenlabs_voice_id", "v2")
    _video(env, "bad", "SCRIPT_READY", voice_id="v2", updated_at=_at(-600),
           script='Say <ipa ph="təˈmeɪtoʊ">tomato</ipa> now.')
    _video(env, "ok", "SCRIPT_READY", voice_id="v2", script="Plain words.")
    worker._sweep_auto_pilot()
    assert _statuses(env, "bad", "ok") == ["SCRIPT_READY", "VOICING"]


def test_the_limit_round_trips_and_an_absent_one_is_kept(env, client):
    _project(env, "auto")
    cfg = {"enabled": True, "gap_mins": 0, "projects": {"auto": []}, "account_limits": {}}
    saved = client.post("/autopilot", json={**cfg, "max_in_flight": 5})
    assert saved.status_code == 200 and saved.get_json()["max_in_flight"] == 5
    # A dashboard tab opened before the upgrade sends the old max_scheduled, or
    # nothing; saving from it must not reset the limit.
    again = client.post("/autopilot", json={**cfg, "enabled": False, "max_scheduled": 1})
    assert again.status_code == 200 and again.get_json()["max_in_flight"] == 5
    assert _sql(env, "SELECT key FROM settings WHERE key = 'auto_pilot_max_scheduled'") == []


def test_the_limit_is_bounded_through_settings_too(client):
    r = client.post("/settings", json={
        "auto_pilot_max_in_flight": pipeline.MAX_AUTO_PILOT_IN_FLIGHT + 1})
    assert r.status_code == 400
    assert client.post("/settings", json={
        "auto_pilot_max_in_flight": pipeline.MAX_AUTO_PILOT_IN_FLIGHT}).status_code == 200


def test_end_to_end_from_proposed_topic_to_a_post(env):
    """One video walked through every checkpoint by the sweep alone, with the
    stages in between done by hand as the agent and the render would."""
    _publishing(env)
    _auto_pilot(env, {"auto": ["spc_yt"]})
    _video(env, "v", "TOPIC_PROPOSED", file=True)
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "TOPIC_APPROVED"
    _sql(env, "UPDATE videos SET status = 'SCRIPT_READY', script = 'Plain words.'")
    worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "VOICING"
    _sql(env, "UPDATE videos SET status = 'VIDEO_READY'")
    with _postforme():
        worker._sweep_auto_pilot()
    assert _row(env, "v")["status"] == "PUBLISHING"
