"""Tests for the TMDEV-1 pipeline status changes: SCRIPTING removal + its DB
migration, and the FAILED status being a normal, unrestricted status value.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import json
import pathlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    """Point DB_FILE at a throwaway sqlite file, initialized fresh."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()

    def make_video(video_id, status):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (video_id, "test topic", status, _now(), _now()),
            )

    return make_video


def test_scripting_status_not_in_workable_statuses():
    assert "SCRIPTING" not in server.WORKABLE_STATUSES
    assert "TOPIC_APPROVED" in server.WORKABLE_STATUSES


def test_init_db_migrates_stranded_scripting_rows(job_db):
    job_db("vid_stranded", "SCRIPTING")

    # TMDEV-91: _init_db now runs migration 0001 once and is tracked in
    # schema_migrations, so a bare second call is a no-op. Clearing that table
    # reproduces what a real pre-migration database looks like on disk.
    with server._conn() as con:
        con.execute("DELETE FROM schema_migrations WHERE version = 1")  # only 0001 re-runs; it is the idempotent one
        con.commit()
    server._init_db()

    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_stranded",)).fetchone()
    assert row["status"] == "TOPIC_APPROVED"


def test_init_db_migrates_render_ready_to_voice_ready(job_db):
    """TMDEV-32: RENDER_READY was renamed VOICE_READY (the old name meant
    'still needs scene authoring', the opposite of ready-to-render).

    TMDEV-91: _init_db now runs migration 0001 once and is tracked in
    schema_migrations, so a bare second call is a no-op. Clearing that table
    reproduces what a real pre-migration database looks like on disk.
    """
    job_db("vid_stranded", "RENDER_READY")

    with server._conn() as con:
        con.execute("DELETE FROM schema_migrations WHERE version = 1")  # only 0001 re-runs; it is the idempotent one
        con.commit()
    server._init_db()

    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_stranded",)).fetchone()
    assert row["status"] == "VOICE_READY"


def test_init_db_leaves_other_statuses_untouched(job_db):
    job_db("vid_normal", "RENDERING")
    server._init_db()

    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_normal",)).fetchone()
    assert row["status"] == "RENDERING"


def test_set_video_status_accepts_failed(job_db):
    job_db("vid_fail", "REVISION_REQUESTED")

    result = server.set_video_status("vid_fail", "FAILED", only_if_current_status="REVISION_REQUESTED")

    assert result == {"video_id": "vid_fail", "status": "FAILED"}
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_fail",)).fetchone()
    assert row["status"] == "FAILED"


def test_get_pipeline_status_has_no_research_due_field(job_db):
    """TMDEV-44: the 22h research_due gate was replaced by
    research_runs_today/max_research_runs_per_day."""
    server._set_setting("last_research_at", _now())
    status = server.get_pipeline_status()
    assert "research_due" not in status


def test_get_pipeline_status_research_runs_today_default_zero(job_db):
    status = server.get_pipeline_status()
    assert status["research_runs_today"] == 0
    assert status["max_research_runs_per_day"] == 8
    assert status["research_window_resets_at"] is None


def test_get_pipeline_status_matches_flask_shape_for_research_window(job_db):
    """MCP and Flask payloads must agree — both expose the same three keys
    replacing research_due (see renderer/api/pipeline.py's mirrored fields)."""
    server._set_setting("research_run_timestamps", '["' + _now() + '"]')
    status = server.get_pipeline_status()
    assert status["research_runs_today"] == 1
    assert status["research_window_resets_at"] is not None


def test_init_db_adds_render_fail_count_column(job_db):
    with server._conn() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)").fetchall()}
    assert "render_fail_count" in cols


def test_init_db_adds_voice_id_column(job_db):
    """TMDEV-51: an existing DB pre-dating the multi-voice feature must gain
    videos.voice_id via migration, not just fresh installs via the DDL."""
    with server._conn() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)").fetchall()}
    assert "voice_id" in cols


# ── TMDEV-51: elevenlabs_voices roster ───────────────────────────────────────

def test_get_pipeline_status_exposes_voices_and_default(job_db):
    server._set_setting("elevenlabs_voices", '[{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]')
    server._set_setting("elevenlabs_voice_id", "abc123")
    status = server.get_pipeline_status()
    assert status["elevenlabs_voices"] == [{"name": "Narrator", "voice_id": "abc123",
                                           "model_id": "eleven_multilingual_v2",
                                           "pronunciation_mode": "respell"}]
    assert status["elevenlabs_voice_id"] == "abc123"


def test_get_pipeline_status_voices_default_empty(job_db):
    status = server.get_pipeline_status()
    assert status["elevenlabs_voices"] == []


def test_get_pipeline_status_user_preferences_default_empty(job_db):
    """TMDEV-117: an interactive session reads the operator's preferences here,
    since only a cron run gets them in its prompt."""
    assert server.get_pipeline_status()["user_preferences"] == ""


def test_get_pipeline_status_returns_user_preferences_verbatim(job_db):
    text = "Research: favour Linux internals.\nScripts: calm tone."
    server._set_setting("user_preferences", text)
    assert server.get_pipeline_status()["user_preferences"] == text


def test_illustrated_is_unavailable_without_an_openai_key(job_db, monkeypatch):
    """The scene-config skill reads this before deciding character fidelity
    under "auto" — without it the agent reaches for generate_character and
    only learns there is no key after the video has been voiced."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert server.get_pipeline_status()["illustrated_available"] is False


def test_illustrated_is_available_with_a_key_and_the_key_never_leaks(job_db, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    server._set_setting("openai_api_key", "sk-secret-value-123")
    status = server.get_pipeline_status()
    assert status["illustrated_available"] is True
    assert "sk-secret-value-123" not in json.dumps(status)


def test_get_video_reports_illustrated_available_too(job_db, monkeypatch):
    """A scheduled session is scoped to one video and told not to go looking
    for work with get_pipeline_status, so the flag has to be on get_video."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    vid = server.create_video(project_id=_make_project(), topic="t", strategy="manual",
                              producibility_score=8)["video_id"]
    assert server.get_video(vid)["illustrated_available"] is False
    server._set_setting("openai_api_key", "sk-secret-value-123")
    video = server.get_video(vid)
    assert video["illustrated_available"] is True
    assert "sk-secret-value-123" not in json.dumps(video)


def test_the_scene_skill_reads_the_key_check_from_get_video():
    """The skill used to send the agent to get_pipeline_status for this, the
    one tool a scheduled session's prompt warned it off."""
    skill = (pathlib.Path(__file__).resolve().parents[2] / "agent_files" / "skills"
             / "tubematic-scene-config" / "SKILL.md").read_text()
    for line in skill.splitlines():
        assert not ("illustrated_available" in line and "get_pipeline_status" in line)
    flat = " ".join(skill.split())
    assert "`illustrated_available` from the `get_video` result" in flat
    assert "Under a forced `illustrated`, the style is the permission" in flat


def test_get_voices_degrades_to_empty_on_corrupt_setting(job_db):
    server._set_setting("elevenlabs_voices", "not json")
    assert server._get_voices() == []


def test_get_voices_degrades_to_empty_over_cap(job_db):
    voices = [{"name": f"v{i}", "voice_id": f"id{i}", "model_id": "eleven_v3"} for i in range(6)]
    server._set_setting("elevenlabs_voices", json.dumps(voices))
    assert server._get_voices() == []


# ── TMDEV-30: status/strategy allow-lists + atomic only_if guard ────────────

def test_set_video_status_rejects_invalid_status(job_db):
    job_db("vid_x", "VOICING")

    result = server.set_video_status("vid_x", "NOT_A_REAL_STATUS")

    assert "error" in result
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_x",)).fetchone()
    assert row["status"] == "VOICING"


def test_set_video_status_atomic_mismatch_leaves_status_unchanged(job_db):
    job_db("vid_y", "VOICING")

    result = server.set_video_status("vid_y", "VOICE_READY", only_if_current_status="TOPIC_APPROVED")

    assert result["error"] == "status_mismatch"
    with server._conn() as con:
        row = con.execute("SELECT status FROM videos WHERE id = ?", ("vid_y",)).fetchone()
    assert row["status"] == "VOICING"


class _RacingConn:
    """Wraps a real connection. On the first execute() whose SQL starts with
    `trigger_sql_prefix`, performs a side-channel write via a *separate* raw
    connection to the same DB file immediately after the wrapped call
    returns — simulating a concurrent writer landing in the window between
    two statements issued on the connection being wrapped (sqlite3.Connection
    itself doesn't allow monkeypatching .execute directly — it's a read-only
    attribute on the real C type — hence this wrapper object instead).
    """

    def __init__(self, real_con, trigger_sql_prefix, db_path, side_sql, side_params):
        self._real = real_con
        self._trigger = trigger_sql_prefix
        self._db_path = db_path
        self._side_sql = side_sql
        self._side_params = side_params
        self._fired = False

    def execute(self, sql, params=()):
        cur = self._real.execute(sql, params)
        if not self._fired and sql.strip().startswith(self._trigger):
            self._fired = True
            side = sqlite3.connect(str(self._db_path))
            side.execute(self._side_sql, self._side_params)
            side.commit()
            side.close()
        return cur

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_set_video_status_reports_fresh_status_after_race(job_db, monkeypatch):
    """A concurrent write landing between the initial SELECT and the atomic
    UPDATE must be reflected in the returned current_status — not the
    pre-race value the initial SELECT saw. Regression for a bug caught by
    code review: the atomic-guard fix made the *write* race-safe but the
    *error message* still reported the stale pre-race read."""
    job_db("vid_race", "VOICING")

    real_conn_ctx = server._conn

    @contextmanager
    def _racing_conn():
        with real_conn_ctx() as con:
            yield _RacingConn(
                con, "SELECT status, archived_at FROM videos", server.DB_FILE,
                "UPDATE videos SET status = 'TOPIC_REJECTED' WHERE id = ?", ("vid_race",),
            )

    monkeypatch.setattr(server, "_conn", _racing_conn)

    result = server.set_video_status("vid_race", "VOICE_READY", only_if_current_status="VOICING")

    assert result["error"] == "status_mismatch"
    assert result["current_status"] == "TOPIC_REJECTED"  # fresh, not the pre-race "VOICING"


def _make_project(project_id="proj_1"):
    with server._conn() as con:
        con.execute(
            "INSERT INTO projects (id, name, created_at) VALUES (?, ?, ?)",
            (project_id, "Test Project", _now()),
        )
    return project_id


def test_create_video_rejects_unknown_project(job_db):
    result = server.create_video(
        project_id="does_not_exist", topic="t", strategy="manual", producibility_score=8
    )
    assert "error" in result


def test_create_video_rejects_invalid_strategy(job_db):
    project_id = _make_project()

    result = server.create_video(
        project_id=project_id, topic="t", strategy="bogus", producibility_score=8
    )

    assert "error" in result


def test_create_video_rejects_sub_threshold_score(job_db):
    """TMDEV-56: the reject-below-5 branch had zero coverage anywhere in the
    repo before this test -- every prior test passed a score of 7 or 8. A
    rename or a rubric change that broke this branch would have shipped
    silently."""
    project_id = _make_project()

    result = server.create_video(
        project_id=project_id, topic="t", strategy="manual", producibility_score=4
    )

    assert "error" in result
    assert "4" in result["error"]


def test_create_video_accepts_score_at_threshold(job_db):
    project_id = _make_project()

    result = server.create_video(
        project_id=project_id, topic="t", strategy="manual", producibility_score=5
    )

    assert result["status"] == "TOPIC_PROPOSED"


def test_set_research_strategies_rejects_manual(job_db):
    """"manual" is a valid videos.strategy value (user-submitted jobs) but is
    never scheduled by poll.py, so it must not be settable as an "active
    research strategy" — a near-miss regression from widening
    VALID_STRATEGIES to include "manual" for create_video's sake."""
    result = server.set_research_strategies(["curriculum", "manual"])

    assert "error" in result


def test_set_research_strategies_accepts_schedulable_strategies(job_db):
    result = server.set_research_strategies(["curriculum", "trending"])

    assert result == {"strategies": ["curriculum", "trending"]}


# ── Mining needs a Gemini key (TMDEV-165) ─────────────────────────────────────

@pytest.fixture
def no_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_mining_is_left_out_of_the_status_without_a_gemini_key(job_db, no_gemini_key):
    """poll.py's research prompt is built from active_strategies: filtered here,
    the agent is never told to mine with no key."""
    status = server.get_pipeline_status()
    assert status["active_strategies"] == ["curriculum", "trending"]
    assert status["mining_available"] is False
    research = server.get_research_strategies()
    assert research["strategies"] == ["curriculum", "trending"]
    assert research["mining_available"] is False


def test_a_stored_key_brings_mining_back_and_never_leaks(job_db, no_gemini_key):
    server._set_setting("active_strategies", "mining,trending")
    assert server.get_pipeline_status()["active_strategies"] == ["trending"]
    server._set_setting("gemini_api_key", "AIza-secret-value-123")
    status = server.get_pipeline_status()
    assert status["active_strategies"] == ["mining", "trending"]
    assert status["mining_available"] is True
    assert "AIza-secret-value-123" not in json.dumps(status)
    assert "AIza-secret-value-123" not in json.dumps(server.get_research_strategies())
    # The filter never rewrote the row.
    assert server._get_setting("active_strategies") == "mining,trending"


def test_enabling_mining_without_a_key_is_refused_and_nothing_is_stored(job_db, no_gemini_key):
    server._set_setting("active_strategies", "curriculum")
    result = server.set_research_strategies(["curriculum", "mining"])
    assert result == {"error": server.MINING_NEEDS_GEMINI_KEY}
    assert server._get_setting("active_strategies") == "curriculum"


def test_a_save_with_no_key_keeps_the_stored_mining_choice(job_db, no_gemini_key):
    """The agent only sees the filtered list; writing it back must not drop
    mining for good."""
    server._set_setting("active_strategies", "curriculum,trending,mining")
    assert server.set_research_strategies(["trending"]) == {"strategies": ["trending"]}
    assert server.get_research_strategies()["strategies"] == ["trending"]
    server._set_setting("gemini_api_key", "AIza-key")
    assert server.get_research_strategies()["strategies"] == ["trending", "mining"]


def test_a_save_with_no_key_adds_no_mining_that_was_not_stored(job_db, no_gemini_key):
    server._set_setting("active_strategies", "curriculum")
    server.set_research_strategies(["trending"])
    assert server._get_setting("active_strategies") == "trending"


def test_enabling_mining_with_a_key_persists(job_db, no_gemini_key):
    server._set_setting("gemini_api_key", "AIza-key")
    assert server.set_research_strategies(["mining"]) == {"strategies": ["mining"]}
    assert server.get_research_strategies()["strategies"] == ["mining"]


def test_create_video_with_voice_id_in_roster(job_db):
    project_id = _make_project()
    server._set_setting("elevenlabs_voices", '[{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]')

    result = server.create_video(
        project_id=project_id, topic="t", strategy="manual", producibility_score=8,
        voice_id="abc123",
    )

    assert "error" not in result
    with server._conn() as con:
        row = con.execute(
            "SELECT voice_id FROM videos WHERE id = ?", (result["video_id"],)
        ).fetchone()
    assert row["voice_id"] == "abc123"


def test_create_video_rejects_voice_id_not_in_roster(job_db):
    project_id = _make_project()

    result = server.create_video(
        project_id=project_id, topic="t", strategy="manual", producibility_score=8,
        voice_id="ghost_voice",
    )

    assert "error" in result


def test_update_video_with_voice_id_in_roster(job_db):
    job_db("vid_voice", "SCRIPT_READY")
    server._set_setting("elevenlabs_voices", '[{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]')

    result = server.update_video("vid_voice", voice_id="abc123")

    assert "error" not in result
    with server._conn() as con:
        row = con.execute(
            "SELECT voice_id FROM videos WHERE id = ?", ("vid_voice",)
        ).fetchone()
    assert row["voice_id"] == "abc123"


def test_update_video_rejects_voice_id_not_in_roster(job_db):
    job_db("vid_voice", "SCRIPT_READY")

    result = server.update_video("vid_voice", voice_id="ghost_voice")

    assert "error" in result
    with server._conn() as con:
        row = con.execute(
            "SELECT voice_id FROM videos WHERE id = ?", ("vid_voice",)
        ).fetchone()
    assert row["voice_id"] == ""


def test_update_video_voice_id_empty_string_clears_to_default(job_db):
    job_db("vid_voice", "SCRIPT_READY")
    server._set_setting("elevenlabs_voices", '[{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]')
    server.update_video("vid_voice", voice_id="abc123")

    result = server.update_video("vid_voice", voice_id="")

    assert "error" not in result
    with server._conn() as con:
        row = con.execute(
            "SELECT voice_id FROM videos WHERE id = ?", ("vid_voice",)
        ).fetchone()
    assert row["voice_id"] == ""


def test_create_video_accepts_manual_strategy(job_db):
    # VALID_STRATEGIES previously omitted "manual" despite the docstring
    # listing it as valid — regression test for that fix.
    project_id = _make_project()

    result = server.create_video(
        project_id=project_id, topic="t", strategy="manual", producibility_score=8
    )

    assert result["status"] == "TOPIC_PROPOSED"


# ── mine_youtube_topics (TMDEV-56) ──────────────────────────────────────────
# No coverage existed for this tool at all before this ticket. The rubric
# rename made a JSON-key mismatch between the prompt and the parser the
# single highest-risk silent failure mode (c.get("producibility_score", 0)
# quietly skips every candidate) -- this locks in that the parser reads the
# renamed key and that the >= 5 filter still works on a mixed response.

URL_X, URL_A, URL_B = (f"https://youtu.be/{c * 11}" for c in "xab")


class _MineResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = {**payload, "usageMetadata": {"promptTokenCount": 5000,
                                                      "candidatesTokenCount": 200}}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _stub_mine_post(monkeypatch, resp):
    import httpx

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            return resp

    monkeypatch.setattr(httpx, "Client", _Client)


def test_mine_youtube_topics_drops_sub_threshold_candidates(job_db, monkeypatch):
    project_id = _make_project()
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")

    payload = {
        "candidates": [{"content": {"parts": [{"text": json.dumps([
            {"topic": "Best Python libraries 2026", "producibility_score": 3},
            {"topic": "How DNS really works", "producibility_score": 8},
        ])}]}}]
    }
    _stub_mine_post(monkeypatch, _MineResp(payload))

    result = server.mine_youtube_topics(project_id=project_id, youtube_urls=[URL_X])

    assert result["proposed"] == 1
    assert [t["topic"] for t in result["topics"]] == ["How DNS really works"]

    with server._conn() as con:
        rows = con.execute("SELECT topic FROM videos WHERE strategy = 'mining'").fetchall()
    assert [r["topic"] for r in rows] == ["How DNS really works"]


def test_mining_records_each_gemini_call_with_no_video(job_db, monkeypatch):
    """Each paid mining call lands in the usage ledger before its reply is
    parsed, with no video attached — one call can file several topics, or none."""
    project_id = _make_project()
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    _stub_mine_post(monkeypatch, _MineResp({"candidates": [{"content": {"parts": [
        {"text": "not json"}]}}]}))

    result = server.mine_youtube_topics(project_id=project_id, youtube_urls=[URL_X])

    assert result["skipped"] == 1
    with server._conn() as con:
        [event] = con.execute("SELECT * FROM usage_events").fetchall()
        links = con.execute("SELECT COUNT(*) FROM usage_event_videos").fetchone()[0]
    assert event["operation"] == "mining" and event["service"] == "gemini"
    assert json.loads(event["units"]) == {"input": 5000, "output": 200}
    assert links == 0


def test_a_failed_mining_url_is_the_calls_one_error_line(job_db, monkeypatch, through_mcp):
    """Mining carries on past a failed URL and returns success, so the failure
    rides on the call's own line as `partial` — naming the URL, and not
    repeated as a second, per-URL warning."""
    class _Quota:
        status_code = 429
        text = '{"error": {"message": "Your prepayment credits are depleted."}}'

    project_id = _make_project()
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    _stub_mine_post(monkeypatch, _Quota())
    out, records = through_mcp("mine_youtube_topics", project_id=project_id,
                               youtube_urls=[URL_X])
    assert out["skipped"] == 1 and out["proposed"] == 0
    (rec,) = records
    assert (rec.levelname, rec.outcome) == ("ERROR", "partial")
    assert (rec.provider_service, rec.provider_status, rec.provider_operation) == \
        ("gemini", 429, "mining")
    assert rec.provider_detail == "https://www.youtube.com/watch?v=xxxxxxxxxxx"  # canonical
    assert "prepayment credits are depleted" in rec.provider_body


def test_an_unparseable_mining_reply_keeps_its_own_warning(job_db, monkeypatch, through_mcp):
    """A billed 200 that will not parse is not a provider failure."""
    project_id = _make_project()
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    _stub_mine_post(monkeypatch, _MineResp({"candidates": [{"content": {"parts": [
        {"text": "not json"}]}}]}))
    out, records = through_mcp("mine_youtube_topics", project_id=project_id,
                               youtube_urls=[URL_X])
    assert out["skipped"] == 1
    assert [(r.levelname, getattr(r, "outcome", None)) for r in records] == \
        [("WARNING", None), ("INFO", "ok")]


# ── The mining cap and duplicate filtering ──────────────────────────────────

class _RecordingClient:
    """httpx.Client stand-in: records every Gemini payload, answers from a queue."""

    def __init__(self, answers, sent):
        self._answers, self._sent = answers, sent

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, json=None, _dumps=json.dumps):
        self._sent.append(json)
        answer = self._answers.pop(0) if self._answers else []
        return _MineResp({"candidates": [{"content": {"parts": [{"text": _dumps(answer)}]}}]})


def _mine(monkeypatch, answers, urls=(URL_A,), project_id=None):
    import httpx
    sent = []
    monkeypatch.setattr(server, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(httpx, "Client", _RecordingClient(list(answers), sent))
    result = server.mine_youtube_topics(project_id=project_id or _make_project(),
                                        youtube_urls=list(urls))
    return result, sent


def _prompt(payload):
    return payload["contents"][0]["parts"][1]["text"]


def test_mining_files_no_more_than_the_cap_and_rejects_nothing(job_db, monkeypatch):
    server._set_setting("max_mining_per_run", "2")
    answer = [{"topic": t, "producibility_score": s} for t, s in (
        ("Same-origin policy", 6), ("DNS rebinding", 9), ("TLS session resumption", 7),
        ("NAT traversal", 8))]
    result, sent = _mine(monkeypatch, [answer])
    assert result["cap"] == 2 and result["proposed"] == 2
    assert [t["topic"] for t in result["topics"]] == ["DNS rebinding", "NAT traversal"]  # best two
    assert [n["reason"] for n in result["not_filed"]] == ["over this run's mining cap"] * 2
    assert "at most 2" in _prompt(sent[0])
    with server._conn() as con:
        assert con.execute("SELECT COUNT(*) FROM videos WHERE strategy = 'mining'").fetchone()[0] == 2
        assert con.execute(
            "SELECT COUNT(*) FROM videos WHERE status = 'TOPIC_REJECTED'").fetchone()[0] == 0


def test_the_next_url_is_asked_only_for_what_is_left_and_sees_existing_topics(job_db, monkeypatch):
    server._set_setting("max_mining_per_run", "3")
    pid = _make_project()
    server.create_video(project_id=pid, topic="How TCP congestion control works",
                        strategy="manual", producibility_score=7)
    result, sent = _mine(monkeypatch, [
        [{"topic": "Same-origin policy", "producibility_score": 8}],
        [{"topic": "DNS rebinding", "producibility_score": 9}],
    ], urls=(URL_A, URL_B), project_id=pid)
    assert result["proposed"] == 2
    first, second = (_prompt(p) for p in sent)
    assert "at most 3" in first and "at most 2" in second
    assert "How TCP congestion control works" in first
    assert "Same-origin policy" in second   # filed this run, so covered for the next URL


def test_a_repeat_of_an_existing_topic_is_not_filed_even_if_rejected(job_db, monkeypatch):
    pid = _make_project()
    vid = server.create_video(project_id=pid, topic="Cron Job Scheduling", strategy="mining",
                              producibility_score=5)["video_id"]
    with server._conn() as con:
        con.execute("UPDATE videos SET status = 'TOPIC_REJECTED' WHERE id = ?", (vid,))
    result, _ = _mine(monkeypatch, [[{"topic": "Cron Jobs for Scheduling",
                                      "producibility_score": 8}]], project_id=pid)
    assert result["proposed"] == 0
    assert result["not_filed"] == [{"topic": "Cron Jobs for Scheduling",
                                    "reason": "repeats an existing topic"}]


def test_a_cap_of_zero_makes_no_gemini_call(job_db, monkeypatch):
    server._set_setting("max_mining_per_run", "0")
    result, sent = _mine(monkeypatch, [])
    assert result["proposed"] == 0 and result["cap"] == 0 and sent == []


def test_a_cap_of_zero_is_a_no_op_even_without_a_gemini_key(job_db, monkeypatch):
    """Mining off must not surface as a mining error on an install that never
    configured Gemini — the cap is read before the key."""
    server._set_setting("max_mining_per_run", "0")
    monkeypatch.setattr(server, "_gemini_key", lambda: "")
    result = server.mine_youtube_topics(project_id=_make_project(),
                                        youtube_urls=[URL_A])
    assert "error" not in result
    assert result["cap"] == 0 and result["proposed"] == 0 and "mining is off" in result["note"]


def test_each_run_starts_at_the_url_after_the_last_one_asked(job_db, monkeypatch):
    server._set_setting("max_mining_per_run", "1")
    pid = _make_project()
    firsts = []
    for topic in ("Same-origin policy", "DNS rebinding", "TLS session resumption"):
        _, sent = _mine(monkeypatch, [[{"topic": topic, "producibility_score": 8}]],
                        urls=(URL_A, URL_B), project_id=pid)
        firsts.append(sent[0]["contents"][0]["parts"][0]["file_data"]["file_uri"])
    # Gemini is handed the canonical form, never the URL as written.
    canon_a, canon_b = (f"https://www.youtube.com/watch?v={c * 11}" for c in "ab")
    assert firsts == [canon_a, canon_b, canon_a]


def test_the_agent_cannot_reject_a_topic(job_db):
    vid = server.create_video(project_id=_make_project(), topic="How DNS really works",
                              strategy="manual", producibility_score=7)["video_id"]
    result = server.set_video_status(vid, "TOPIC_REJECTED")
    assert result["error"] == "human_only_status"
    with server._conn() as con:
        status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    assert status == "TOPIC_PROPOSED"


def test_the_agent_cannot_schedule_a_post(job_db):
    """A scheduled video needs a post postforme is holding. Set by hand, the
    worker would move it to PUBLISHING and fail it — nothing was ever posted."""
    vid = server.create_video(project_id=_make_project(), topic="How DNS really works",
                              strategy="manual", producibility_score=7)["video_id"]
    result = server.set_video_status(vid, "SCHEDULED")
    assert result["error"] == "human_only_status"
    with server._conn() as con:
        status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    assert status == "TOPIC_PROPOSED"


def test_every_copy_of_the_status_list_agrees():
    """Three processes each hold the list; a status missing from one is
    refused there (MCP, Flask) or cannot be rendered (the dashboard's
    Record<VideoStatus, ...> maps). Read as source text, as the other
    cross-copy checks do."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    py = (root / "renderer" / "api" / "pipeline.py").read_text()
    block = re.search(r"^VALID_VIDEO_STATUSES = \{(.*?)\}", py, re.S | re.M)
    ts = (root / "dashboard" / "lib" / "types.ts").read_text()
    union = re.search(r"export type VideoStatus =(.*?);", ts, re.S)
    assert set(re.findall(r'"([A-Z_]+)"', block.group(1))) == server.VALID_VIDEO_STATUSES
    assert set(re.findall(r'"([A-Z_]+)"', union.group(1))) == server.VALID_VIDEO_STATUSES


# ── Migration idempotence (TMDEV-56) ────────────────────────────────────────

def test_init_db_renames_animatability_column(tmp_path, monkeypatch):
    """Build a DB with the pre-TMDEV-56 column name, run _init_db twice, and
    confirm: the column is renamed, existing data survives, and the second
    run is a clean no-op (doesn't error on an already-renamed column)."""
    db_path = tmp_path / "old.db"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE videos (
            id TEXT PRIMARY KEY, project_id TEXT, topic TEXT NOT NULL,
            strategy TEXT NOT NULL DEFAULT 'manual',
            animatability_score INTEGER NOT NULL DEFAULT 0,
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
        "INSERT INTO videos (id, topic, animatability_score, created_at, updated_at) "
        "VALUES ('vid_old', 'pre-existing topic', 7, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    con.commit()
    con.close()

    monkeypatch.setattr(server, "DB_FILE", db_path)

    server._init_db()
    with server._conn() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)")}
        row = con.execute("SELECT producibility_score FROM videos WHERE id = 'vid_old'").fetchone()
    assert "producibility_score" in cols
    assert "animatability_score" not in cols
    assert row["producibility_score"] == 7

    # Second run must be a clean no-op, not an error on the already-renamed column.
    server._init_db()
    with server._conn() as con:
        row = con.execute("SELECT producibility_score FROM videos WHERE id = 'vid_old'").fetchone()
    assert row["producibility_score"] == 7


def test_init_db_fresh_db_untouched_by_rename(job_db):
    """A DB created fresh (never had the old column) must not error when the
    rename guard runs — it should see no old column and skip cleanly."""
    with server._conn() as con:
        cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)")}
    assert "producibility_score" in cols
    assert "animatability_score" not in cols
