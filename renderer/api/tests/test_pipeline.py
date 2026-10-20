import json
import os
import re
import sqlite3
import tempfile
import time
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline
from pipeline import create_pipeline_blueprint


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = p
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE projects (
            id TEXT PRIMARY KEY, name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_curriculum_seed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );
        CREATE TABLE videos (
            id TEXT PRIMARY KEY, project_id TEXT, title TEXT NOT NULL DEFAULT '',
            topic TEXT NOT NULL, strategy TEXT NOT NULL DEFAULT 'manual',
            producibility_score INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
            script TEXT NOT NULL DEFAULT '',
            voice_file_path TEXT NOT NULL DEFAULT '',
            timeline_path TEXT NOT NULL DEFAULT '',
            scene_config_path TEXT NOT NULL DEFAULT '',
            video_path TEXT NOT NULL DEFAULT '',
            video_version INTEGER NOT NULL DEFAULT 1,
            gemini_feedback TEXT NOT NULL DEFAULT '',
            youtube_url TEXT NOT NULL DEFAULT '',
            cost_cents_elevenlabs INTEGER NOT NULL DEFAULT 0,
            cost_cents_gemini INTEGER NOT NULL DEFAULT 0,
            cost_cents_claude INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL,
            author TEXT NOT NULL CHECK (author IN ('human','agent')),
            content TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    con.close()
    yield p


@pytest.fixture
def client(db_path):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _seed_video(db_path, status="TOPIC_PROPOSED"):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO videos
           (id, topic, strategy, producibility_score, status, created_at, updated_at)
           VALUES ('vid-1', 'DNS resolution', 'curriculum', 8, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
        (status,)
    )
    con.commit()
    con.close()


def _seed_video_with_segments(db_path, segments, video_id="vid-2", status="SCRIPT_READY"):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO videos
           (id, topic, strategy, producibility_score, status, script_segments, created_at, updated_at)
           VALUES (?, 'How TCP works', 'curriculum', 8, ?, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
        (video_id, status, json.dumps(segments)),
    )
    con.commit()
    con.close()


# ── /stats ──────────────────────────────────────────────────────────────────

def test_stats_empty(client):
    r = client.get("/stats")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data == {}


def test_stats_counts(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.get("/stats")
    data = json.loads(r.data)
    assert data["TOPIC_PROPOSED"] == 1


# ── /videos ─────────────────────────────────────────────────────────────────

def test_list_videos_empty(client):
    r = client.get("/videos")
    assert r.status_code == 200
    assert json.loads(r.data) == []


def test_list_videos_returns_seeded(client, db_path):
    _seed_video(db_path)
    r = client.get("/videos")
    data = json.loads(r.data)
    assert len(data) == 1
    assert data[0]["id"] == "vid-1"


def test_list_videos_filter_by_status(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.get("/videos?status=RENDERING")
    assert json.loads(r.data) == []
    r2 = client.get("/videos?status=TOPIC_PROPOSED")
    assert len(json.loads(r2.data)) == 1


def test_list_videos_parses_script_segments_as_list(client, db_path):
    segments = [{"id": "s1", "voice": "Hello there.", "visual": "intro"}]
    _seed_video_with_segments(db_path, segments)
    r = client.get("/videos")
    data = json.loads(r.data)
    assert len(data) == 1
    assert isinstance(data[0]["script_segments"], list)
    assert data[0]["script_segments"] == segments


def test_actionable_videos_parses_script_segments_as_list(client, db_path):
    segments = [{"id": "s1", "voice": "Hello there.", "visual": "intro"}]
    _seed_video_with_segments(db_path, segments, status="SCRIPT_READY")
    r = client.get("/videos/actionable")
    data = json.loads(r.data)
    assert len(data) == 1
    assert isinstance(data[0]["script_segments"], list)
    assert data[0]["script_segments"] == segments


def test_actionable_includes_checkpoint_statuses(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.get("/videos/actionable")
    data = json.loads(r.data)
    assert len(data) == 1


def test_actionable_excludes_non_checkpoint(client, db_path):
    _seed_video(db_path, "RENDERING")
    r = client.get("/videos/actionable")
    assert json.loads(r.data) == []


def test_get_video_includes_comments(client, db_path):
    _seed_video(db_path)
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO comments (video_id, author, content, created_at) VALUES ('vid-1', 'agent', 'hello', '2026-01-01T00:00:01Z')"
    )
    con.commit()
    con.close()
    r = client.get("/videos/vid-1")
    data = json.loads(r.data)
    assert data["id"] == "vid-1"
    assert len(data["comments"]) == 1
    assert data["comments"][0]["content"] == "hello"


def test_get_video_404(client):
    r = client.get("/videos/nonexistent")
    assert r.status_code == 404


def test_get_video_parses_script_segments_as_list(client, db_path):
    """Regression for the Flask/MCP contract mismatch: script_segments must
    come back as a parsed list of dicts, not the raw JSON TEXT string —
    dashboard's VideoModal calls .map() on it directly."""
    segments = [
        {"id": "s1", "voice": "Hello there.", "visual": "intro"},
        {"id": "s2", "voice": "Here's how it works.", "visual": "diagram"},
    ]
    _seed_video_with_segments(db_path, segments)
    r = client.get("/videos/vid-2")
    data = json.loads(r.data)
    assert isinstance(data["script_segments"], list)
    assert data["script_segments"] == segments


def test_get_video_script_segments_null_when_absent(client, db_path):
    _seed_video(db_path)
    r = client.get("/videos/vid-1")
    data = json.loads(r.data)
    assert data["script_segments"] is None


# ── PATCH /videos/<id> ──────────────────────────────────────────────────────

def test_patch_status(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.patch("/videos/vid-1", json={"status": "TOPIC_APPROVED"})
    assert r.status_code == 200
    r2 = client.get("/videos/vid-1")
    assert json.loads(r2.data)["status"] == "TOPIC_APPROVED"


def test_patch_only_if_current_status_matches(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.patch("/videos/vid-1", json={
        "status": "TOPIC_APPROVED",
        "onlyIfCurrentStatus": "TOPIC_PROPOSED"
    })
    assert r.status_code == 200


def test_patch_only_if_current_status_mismatch_returns_409(client, db_path):
    _seed_video(db_path, "RENDERING")
    r = client.patch("/videos/vid-1", json={
        "status": "TOPIC_APPROVED",
        "onlyIfCurrentStatus": "TOPIC_PROPOSED"
    })
    assert r.status_code == 409


def test_patch_invalid_status_returns_400(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.patch("/videos/vid-1", json={"status": "NOT_A_REAL_STATUS"})
    assert r.status_code == 400
    r2 = client.get("/videos/vid-1")
    assert json.loads(r2.data)["status"] == "TOPIC_PROPOSED"


def test_patch_status_accepts_render_queued(client, db_path):
    """RENDER_QUEUED (TMDEV-32 — the worker's durable queue signal) is a
    valid status, not just VOICE_READY/RENDERING either side of it."""
    _seed_video(db_path, "VOICE_READY")
    r = client.patch("/videos/vid-1", json={"status": "RENDER_QUEUED"})
    assert r.status_code == 200
    r2 = client.get("/videos/vid-1")
    assert json.loads(r2.data)["status"] == "RENDER_QUEUED"


class _RacingConn:
    """Wraps a real sqlite3.Connection. On the first execute() whose SQL
    starts with `trigger_sql_prefix`, performs a side-channel write via a
    *separate* raw connection to the same DB file immediately after the
    wrapped call returns — simulating a concurrent writer landing in the
    window between two statements issued on the connection being wrapped.
    (sqlite3.Connection doesn't allow monkeypatching .execute directly — it's
    a read-only attribute on the real C type — hence this wrapper instead.)
    """

    def __init__(self, real_con, trigger_sql_prefix, db_path, side_sql, side_params):
        object.__setattr__(self, "_real", real_con)
        object.__setattr__(self, "_trigger", trigger_sql_prefix)
        object.__setattr__(self, "_db_path", db_path)
        object.__setattr__(self, "_side_sql", side_sql)
        object.__setattr__(self, "_side_params", side_params)
        object.__setattr__(self, "_fired", False)

    def execute(self, sql, params=()):
        cur = self._real.execute(sql, params)
        if not self._fired and sql.strip().startswith(self._trigger):
            object.__setattr__(self, "_fired", True)
            side = sqlite3.connect(str(self._db_path))
            side.execute(self._side_sql, self._side_params)
            side.commit()
            side.close()
        return cur

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __setattr__(self, name, value):
        setattr(self._real, name, value)


def test_patch_video_voice_id_in_roster_persists(client, db_path):
    _seed_video(db_path, "SCRIPT_READY")
    client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}],
    })
    r = client.patch("/videos/vid-1", json={
        "status": "VOICING", "voice_id": "abc123",
        "onlyIfCurrentStatus": "SCRIPT_READY",
    })
    assert r.status_code == 200
    r2 = client.get("/videos/vid-1")
    data = json.loads(r2.data)
    assert data["voice_id"] == "abc123"
    assert data["status"] == "VOICING"


def test_patch_video_voice_id_not_in_roster_returns_400(client, db_path):
    _seed_video(db_path, "SCRIPT_READY")
    r = client.patch("/videos/vid-1", json={"voice_id": "ghost_voice"})
    assert r.status_code == 400
    r2 = client.get("/videos/vid-1")
    assert json.loads(r2.data)["voice_id"] == ""


def test_patch_video_reports_fresh_status_after_race(client, db_path, monkeypatch):
    """A concurrent write landing between patch_video's initial SELECT and
    its atomic UPDATE must be reflected in the 409 body's 'current' field —
    not the pre-race value the initial SELECT saw. Regression for a bug
    caught by code review: the atomic-guard fix made the *write* race-safe
    but the *error message* still reported the stale pre-race read."""
    _seed_video(db_path, "VOICING")

    real_connect = sqlite3.connect
    state = {"wrapped": False}

    def _connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        if not state["wrapped"]:
            state["wrapped"] = True
            return _RacingConn(
                con, "SELECT status, archived_at FROM videos", db_path,
                "UPDATE videos SET status = 'TOPIC_REJECTED' WHERE id = ?", ("vid-1",),
            )
        return con

    monkeypatch.setattr(sqlite3, "connect", _connect)

    r = client.patch("/videos/vid-1", json={
        "status": "TOPIC_APPROVED",
        "onlyIfCurrentStatus": "VOICING",
    })

    assert r.status_code == 409
    data = json.loads(r.data)
    assert data["current"] == "TOPIC_REJECTED"  # fresh, not the pre-race "VOICING"


# ── /videos/<id>/comments ───────────────────────────────────────────────────

def test_post_comment(client, db_path):
    _seed_video(db_path)
    r = client.post("/videos/vid-1/comments", json={"author": "human", "content": "looks good"})
    assert r.status_code == 201
    r2 = client.get("/videos/vid-1")
    comments = json.loads(r2.data)["comments"]
    assert comments[-1]["content"] == "looks good"


# ── POST /videos ─────────────────────────────────────────────────────────────

def test_create_video(client):
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "trending",
        "producibility_score": 7,
        "title": "gc-pauses-v1",
    })
    assert r.status_code == 201
    data = json.loads(r.data)
    assert data["status"] == "TOPIC_PROPOSED"
    assert "id" in data


def test_create_video_with_voice_id_in_roster(client):
    client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}],
    })
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "manual",
        "producibility_score": 7,
        "voice_id": "abc123",
    })
    assert r.status_code == 201
    assert json.loads(r.data)["voice_id"] == "abc123"


def test_create_video_with_unknown_voice_id_returns_400(client):
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "manual",
        "producibility_score": 7,
        "voice_id": "ghost_voice",
    })
    assert r.status_code == 400


# ── the title length cap ─────────────────────────────────────────────────────
# `title` is the short display name dashboard cards render; `topic` is the full
# descriptive brief. Create clips an over-length title so a research run is
# never lost to a cosmetic field; PATCH rejects, since that is a deliberate edit.

CAP = pipeline.VIDEO_TITLE_MAX_LEN


# _truncate_title is hand-duplicated from mcp/server.py behind a "Keep in sync"
# comment, so it needs its own direct coverage here — exercising it only through
# POST /videos would let the two copies drift on everything but the constant.

def test_truncate_title_leaves_a_short_title_alone():
    title = "How TLS negotiates a session key"
    assert pipeline._truncate_title(title) == (title, "")


def test_truncate_title_leaves_a_title_exactly_at_the_cap_alone():
    assert pipeline._truncate_title("x" * CAP) == ("x" * CAP, "")


def test_truncate_title_cuts_at_a_word_boundary():
    title = "How Chromium's renderer sandbox keeps untrusted JavaScript away from your filesystem"
    cut, warning = pipeline._truncate_title(title)
    assert len(cut) <= CAP
    assert warning
    assert title.startswith(cut)
    assert title[len(cut)] == " ", "must not end mid-word"


def test_truncate_title_hard_cuts_a_single_long_token():
    cut, warning = pipeline._truncate_title("x" * (CAP + 40))
    assert cut == "x" * CAP
    assert warning


def test_truncate_title_appends_no_ellipsis():
    cut, _ = pipeline._truncate_title("word " * 40)
    assert "…" not in cut and "..." not in cut


@pytest.mark.parametrize("title", [
    " " * 5 + "word " * 20,
    " " * 69 + "x" * 40,
    "  " + "x" * 80,
    "\t" * 10 + "word " * 30,
    " " * 68 + "ab cd",
])
def test_truncate_title_never_returns_a_blank_name(title):
    """Leading-whitespace inputs must not clip down to nothing."""
    cut, _ = pipeline._truncate_title(title)
    assert len(cut) <= CAP
    assert cut.strip(), f"clipped {title[:30]!r} to a blank name"


def test_truncate_title_matches_the_mcp_copy():
    """The two hand-copied helpers must agree, not just their constants."""
    import importlib.util
    import pathlib as _pathlib

    mcp_path = _pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py"
    src = mcp_path.read_text()
    # Import just the helper's source, not the whole fastmcp-dependent module.
    start = src.index("def _truncate_title")
    end = src.index("\n@mcp.tool", start)
    ns = {"VIDEO_TITLE_MAX_LEN": CAP}
    exec(compile(src[start:end], str(mcp_path), "exec"), ns)
    mcp_fn = ns["_truncate_title"]

    for title in ["short one", "x" * CAP, "x" * (CAP + 40), "word " * 40,
                  " " * 5 + "word " * 20, "  " + "x" * 80]:
        assert mcp_fn(title) == pipeline._truncate_title(title), f"copies disagree on {title[:30]!r}"


# ── TMDEV-90: _pick_agent_id ─────────────────────────────────────────────────

def _agents_db(tmp_path, agents):
    """A fresh _init_db'd DB holding `agents`: (id, weight, is_default, archived_at, created_at)."""
    db = str(tmp_path / "agents.db")
    pipeline._init_db(db)
    con = sqlite3.connect(db)
    for aid, weight, is_default, archived_at, created_at in agents:
        con.execute(
            "INSERT INTO agents (id, name, binary, run_path, models, is_default, weight,"
            " archived_at, created_at, updated_at) VALUES (?, ?, '/bin/x', '/w', '[\"m\"]',"
            " ?, ?, ?, ?, ?)",
            (aid, aid.title(), is_default, weight, archived_at, created_at, created_at))
    con.commit()
    return con


_T0, _T1, _T2 = "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"


def test_pick_agent_id_returns_none_with_no_agents(tmp_path):
    assert pipeline._pick_agent_id(_agents_db(tmp_path, [])) is None


def _db_path(con):
    return con.execute("PRAGMA database_list").fetchone()[2]


def _blocks(picks, size):
    return [picks[i:i + size] for i in range(0, len(picks), size)]


def test_every_full_deck_splits_exactly_by_weight(tmp_path):
    """A shuffled deck, not independent draws: 3:1 is exactly 3 and 1 of
    every 4 new videos — only the order within each deck is random."""
    import random
    con = _agents_db(tmp_path, [("a", 3, 0, None, _T0), ("b", 1, 0, None, _T1)])
    rng = random.Random(1234)
    blocks = _blocks([pipeline._pick_agent_id(con, rng) for _ in range(40)], 4)
    assert all(sorted(b) == ["a", "a", "a", "b"] for b in blocks), blocks
    assert len({tuple(b) for b in blocks}) > 1, "the order within a deck must vary"


def test_a_common_factor_in_the_weights_is_divided_out(tmp_path):
    """30:10 is dealt as 3:1 — decks of 4, not 40."""
    import random
    con = _agents_db(tmp_path, [("a", 30, 0, None, _T0), ("b", 10, 0, None, _T1)])
    rng = random.Random(5)
    blocks = _blocks([pipeline._pick_agent_id(con, rng) for _ in range(12)], 4)
    assert all(sorted(b) == ["a", "a", "a", "b"] for b in blocks), blocks


def test_a_weight_change_starts_a_new_deck(tmp_path):
    import random
    con = _agents_db(tmp_path, [("a", 3, 0, None, _T0), ("b", 1, 0, None, _T1)])
    rng = random.Random(9)
    pipeline._pick_agent_id(con, rng)
    con.execute("UPDATE agents SET weight = 3 WHERE id = 'b'")   # now 1:1
    assert sorted(pipeline._pick_agent_id(con, rng) for _ in range(2)) == ["a", "b"]


def test_the_deck_is_shared_across_connections(tmp_path):
    """Flask and MCP are separate processes dealing from one deck."""
    import random
    db = _db_path(_agents_db(tmp_path, [("a", 3, 0, None, _T0), ("b", 1, 0, None, _T1)]))
    cons = [sqlite3.connect(db), sqlite3.connect(db)]
    rng = random.Random(2)
    picks = []
    for i in range(8):
        con = cons[i % 2]
        picks.append(pipeline._pick_agent_id(con, rng))
        con.commit()
    assert all(sorted(b) == ["a", "a", "a", "b"] for b in _blocks(picks, 4)), picks


def test_a_rolled_back_insert_returns_its_card(tmp_path):
    con = _agents_db(tmp_path, [("a", 3, 0, None, _T0), ("b", 1, 0, None, _T1)])
    pipeline._pick_agent_id(con)
    con.commit()
    before = con.execute("SELECT signature, cards FROM agent_deck").fetchone()
    pipeline._pick_agent_id(con)
    con.rollback()
    assert con.execute("SELECT signature, cards FROM agent_deck").fetchone() == before


def test_a_deal_holds_the_write_lock_until_its_transaction_ends(tmp_path):
    """Its first statement is a write, so a second process cannot read the
    deck mid-deal and hand out the same card."""
    con1 = _agents_db(tmp_path, [("a", 3, 0, None, _T0), ("b", 1, 0, None, _T1)])
    con2 = sqlite3.connect(_db_path(con1), timeout=0.05)
    pipeline._pick_agent_id(con1)   # uncommitted
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        pipeline._pick_agent_id(con2)
    con1.commit()
    assert pipeline._pick_agent_id(con2) in {"a", "b"}


def test_pick_agent_id_never_picks_a_zero_weight_agent(tmp_path):
    import random
    con = _agents_db(tmp_path, [("a", 1, 0, None, _T0), ("b", 0, 1, None, _T1)])
    rng = random.Random(7)
    assert {pipeline._pick_agent_id(con, rng) for _ in range(500)} == {"a"}


def test_pick_agent_id_all_zero_weights_falls_back_to_the_default(tmp_path):
    con = _agents_db(tmp_path, [("a", 0, 0, None, _T0), ("b", 0, 1, None, _T1)])
    assert pipeline._pick_agent_id(con) == "b"


def test_pick_agent_id_all_zero_and_no_default_falls_back_to_the_oldest(tmp_path):
    con = _agents_db(tmp_path, [("b", 0, 0, None, _T1), ("a", 0, 0, None, _T0)])
    assert pipeline._pick_agent_id(con) == "a"


def test_pick_agent_id_never_picks_an_archived_agent(tmp_path):
    import random
    con = _agents_db(tmp_path, [("a", 1, 0, None, _T0), ("old", 100, 1, _T1, _T0)])
    rng = random.Random(3)
    assert {pipeline._pick_agent_id(con, rng) for _ in range(300)} == {"a"}
    sub = tmp_path / "only-archived"
    sub.mkdir()
    assert pipeline._pick_agent_id(_agents_db(sub, [("old", 5, 1, _T1, _T0)])) is None


def _mcp_source():
    import pathlib as _pathlib
    path = _pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py"
    return path, path.read_text()


def test_the_checkpoint_freeze_matches_the_mcp_copy():
    """Which fields reopen at which statuses is one rule held in two
    processes (TMDEV-110). A drift would let MCP change what the API refuses."""
    import ast
    _, src = _mcp_source()
    consts = {
        t.id: ast.literal_eval(node.value)
        for node in ast.parse(src).body if isinstance(node, ast.Assign)
        for t in node.targets if isinstance(t, ast.Name)
        and t.id in {"HUMAN_CHECKPOINT_STATUSES", "TOPIC_ONLY_FIELDS", "AGENT_CHECKPOINT_FIELDS"}
    }
    assert set(consts["HUMAN_CHECKPOINT_STATUSES"]) == pipeline.ACTIONABLE_STATUSES
    assert tuple(consts["TOPIC_ONLY_FIELDS"]) == pipeline.TOPIC_ONLY_FIELDS
    assert tuple(consts["AGENT_CHECKPOINT_FIELDS"]) == pipeline.AGENT_CHECKPOINT_FIELDS


def test_agent_id_error_matches_the_mcp_copy(tmp_path):
    mcp_path, src = _mcp_source()
    start = src.index("def _agent_id_error")
    end = src.index("\ndef ", start + 1)
    ns = {}
    exec(compile(src[start:end], str(mcp_path), "exec"), ns)
    mcp_fn = ns["_agent_id_error"]

    con = _agents_db(tmp_path, [("live", 1, 1, None, _T0), ("gone", 1, 0, _T1, _T0)])
    con.row_factory = sqlite3.Row
    for stored in (None, "live", "gone"):
        for new in ("live", "gone", "missing"):
            assert mcp_fn(con, stored, new) == pipeline._agent_id_error(con, stored, new), \
                (stored, new)


def test_pick_agent_id_matches_the_mcp_copy(tmp_path):
    """The two hand-copied pickers must deal identically for the same seeded
    rng — same precedent as the _truncate_title agreement test. Each copy gets
    its own DB, since the deck is state: sharing one would interleave them."""
    import math
    import pathlib as _pathlib
    import random

    mcp_path = _pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py"
    src = mcp_path.read_text()
    start = src.index("def _pick_agent_id")
    end = src.index("\n@mcp.tool", start)
    ns = {"random": random, "json": json, "math": math, "VIDEO_TITLE_MAX_LEN": CAP}
    exec(compile(src[start:end], str(mcp_path), "exec"), ns)
    mcp_fn = ns["_pick_agent_id"]

    agent_sets = [
        [],
        [("a", 1, 1, None, _T0)],
        [("a", 3, 0, None, _T0), ("b", 1, 1, None, _T1)],
        # Same created_at: the id tiebreak is what keeps the order stable.
        [("z", 2, 0, None, _T0), ("m", 5, 0, None, _T0), ("a", 1, 0, None, _T0)],
        [("a", 0, 0, None, _T0), ("b", 0, 1, None, _T1)],
        [("a", 0, 0, None, _T1), ("b", 0, 0, None, _T0)],
        [("a", 4, 0, _T2, _T0), ("b", 1, 0, None, _T1), ("c", 2, 1, None, _T2)],
    ]
    for i, agents in enumerate(agent_sets):
        for seed in (0, 1, 42):
            cons = []
            for side in ("ours", "theirs"):
                d = tmp_path / f"set{i}-seed{seed}-{side}"
                d.mkdir()
                cons.append(_agents_db(d, agents))
            r1, r2 = random.Random(seed), random.Random(seed)
            ours = [pipeline._pick_agent_id(cons[0], r1) for _ in range(50)]
            theirs = [mcp_fn(cons[1], r2) for _ in range(50)]
            assert ours == theirs, f"copies disagree on agent set {i}, seed {seed}"


def test_create_video_clips_an_over_length_title(client):
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "trending",
        "producibility_score": 7,
        "title": "How CPython's generational garbage collector decides when to pause your program",
    })
    assert r.status_code == 201
    data = json.loads(r.data)
    assert len(data["title"]) <= CAP
    assert str(CAP) in data["warning"]


def test_create_video_keeps_the_topic_whole_when_the_title_is_clipped(client):
    topic = "A brief that runs well past seventy characters. " * 10
    r = client.post("/videos", json={
        "topic": topic,
        "strategy": "trending",
        "producibility_score": 7,
        "title": "x" * (CAP + 10),
    })
    assert json.loads(r.data)["topic"] == topic


def test_create_video_does_not_warn_on_a_short_title(client):
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "trending",
        "producibility_score": 7,
        "title": "How CPython pauses for GC",
    })
    assert "warning" not in json.loads(r.data)


def test_patch_video_accepts_a_title_within_the_cap(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.patch("/videos/vid-1", json={"title": "How CPython pauses for GC"})
    assert r.status_code == 200
    assert json.loads(client.get("/videos/vid-1").data)["title"] == "How CPython pauses for GC"


def test_patch_video_over_length_title_returns_400(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.patch("/videos/vid-1", json={"title": "x" * (CAP + 1)})
    assert r.status_code == 400
    assert str(CAP) in json.loads(r.data)["error"]


@pytest.mark.parametrize("bad", [42, True, ["a"], {"x": 1}])
def test_create_video_non_string_title_returns_400(client, bad):
    """Was a 500 in two different ways: int/bool raised inside _truncate_title,
    while list/dict slipped past it and failed at the INSERT."""
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "trending",
        "producibility_score": 7,
        "title": bad,
    })
    assert r.status_code == 400
    assert "title" in json.loads(r.data)["error"]


@pytest.mark.parametrize("blank", [None, "", 0, False])
def test_create_video_treats_a_blank_title_as_absent(client, blank):
    """null/omitted/falsey means 'no title' — the UI falls back to topic."""
    r = client.post("/videos", json={
        "topic": "GC pauses in Python",
        "strategy": "trending",
        "producibility_score": 7,
        "title": blank,
    })
    assert r.status_code == 201
    assert json.loads(r.data)["title"] == ""


def test_patch_video_non_string_title_returns_400(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    assert client.patch("/videos/vid-1", json={"title": 42}).status_code == 400


def test_a_rejected_title_patch_writes_nothing(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    client.patch("/videos/vid-1", json={"title": "Kept"})
    client.patch("/videos/vid-1", json={"title": "x" * (CAP + 1), "status": "TOPIC_APPROVED"})
    data = json.loads(client.get("/videos/vid-1").data)
    assert data["title"] == "Kept"
    assert data["status"] == "TOPIC_PROPOSED", "the whole PATCH must be rejected, not just the title"


def test_the_title_is_editable_after_the_topic_checkpoint(client, db_path):
    """Cosmetic, unlike script_profile_id/agent_model, which are frozen after TOPIC_PROPOSED."""
    _seed_video(db_path, "VOICE_READY")
    assert client.patch("/videos/vid-1", json={"title": "Renamed late"}).status_code == 200

# ── /projects ────────────────────────────────────────────────────────────────

def test_list_projects_empty(client):
    r = client.get("/projects")
    assert r.status_code == 200
    assert json.loads(r.data) == []


def test_create_and_list_project(client):
    r = client.post("/projects", json={"name": "Python Internals"})
    assert r.status_code == 201
    data = json.loads(r.data)
    assert data["name"] == "Python Internals"
    assert data["is_curriculum_seed"] == 0
    assert data["status"] == "active"
    r2 = client.get("/projects")
    assert len(json.loads(r2.data)) == 1


def test_create_project_curriculum_seed(client):
    r = client.post("/projects", json={
        "name": "Python Internals",
        "is_curriculum_seed": True,
    })
    assert r.status_code == 201
    data = json.loads(r.data)
    assert data["is_curriculum_seed"] == 1


def test_create_project_invalid_status(client):
    r = client.post("/projects", json={"name": "Test", "status": "unknown"})
    assert r.status_code == 400


def test_set_project_status_pause(client):
    r = client.post("/projects", json={"name": "Python Internals", "id": "py-internals",
                                       "is_curriculum_seed": True})
    assert r.status_code == 201
    r2 = client.post("/projects/py-internals/status", json={"status": "paused"})
    assert r2.status_code == 200
    data = json.loads(r2.data)
    assert data["status"] == "paused"


def test_set_project_status_activate(client):
    client.post("/projects", json={"name": "Networking", "id": "networking",
                                   "is_curriculum_seed": True, "status": "paused"})
    r = client.post("/projects/networking/status", json={"status": "active"})
    assert r.status_code == 200
    assert json.loads(r.data)["status"] == "active"


def test_set_project_status_not_found(client):
    r = client.post("/projects/nonexistent/status", json={"status": "paused"})
    assert r.status_code == 404


def test_set_project_status_invalid(client):
    client.post("/projects", json={"name": "X", "id": "x"})
    r = client.post("/projects/x/status", json={"status": "deleted"})
    assert r.status_code == 400


# ── /research/strategies ─────────────────────────────────────────────────────

def _set_gemini_key(db_path, value):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('gemini_api_key', ?)",
                (value,))
    con.commit()
    con.close()


@pytest.fixture
def no_env_gemini_key(monkeypatch):
    """The key falls back to the environment, as every reader of it does."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_get_research_strategies_default(client, db_path, no_env_gemini_key):
    _set_gemini_key(db_path, "g-key")
    r = client.get("/research/strategies")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert set(data["strategies"]) == {"curriculum", "trending", "mining"}
    assert data["mining_available"] is True
    assert "g-key" not in r.get_data(as_text=True)


def test_mining_is_left_out_while_no_gemini_key_is_stored(client, no_env_gemini_key):
    """TMDEV-165: derived at the read boundary — the agent is never told to mine
    with no key, rather than told to and then hitting a tool error."""
    data = json.loads(client.get("/research/strategies").data)
    assert data["strategies"] == ["curriculum", "trending"]
    assert data["mining_available"] is False


def test_a_key_added_later_brings_mining_back_with_no_re_tick(client, db_path, no_env_gemini_key):
    """The stored row is never rewritten by the filter."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('active_strategies', 'trending,mining')")
    con.commit()
    con.close()
    assert json.loads(client.get("/research/strategies").data)["strategies"] == ["trending"]
    _set_gemini_key(db_path, "g-key")
    assert json.loads(client.get("/research/strategies").data)["strategies"] == \
        ["trending", "mining"]


def test_an_env_gemini_key_counts_as_stored(client, monkeypatch):
    """The same fallback _secret gives every other credential, and what the
    compose test stack relies on."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    data = json.loads(client.get("/research/strategies").data)
    assert "mining" in data["strategies"] and data["mining_available"] is True


def test_enabling_mining_without_a_gemini_key_is_refused(client, db_path, no_env_gemini_key):
    r = client.post("/research/strategies", json={"strategies": ["curriculum", "mining"]})
    assert r.status_code == 400
    assert json.loads(r.data)["error"] == pipeline.MINING_NEEDS_GEMINI_KEY
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT value FROM settings WHERE key='active_strategies'").fetchone()
    con.close()
    assert row is None  # nothing stored


def test_a_save_with_no_key_keeps_the_stored_mining_choice(client, db_path, no_env_gemini_key):
    """The Topics page posts back the filtered list it was shown. Storing that
    verbatim would drop mining for good, and a key added later would not bring
    it back."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('active_strategies', 'curriculum,trending,mining')")
    con.commit()
    con.close()
    r = client.post("/research/strategies", json={"strategies": ["trending"]})
    assert r.status_code == 200
    assert json.loads(r.data)["strategies"] == ["trending"]
    assert json.loads(client.get("/research/strategies").data)["strategies"] == ["trending"]
    _set_gemini_key(db_path, "g-key")
    assert json.loads(client.get("/research/strategies").data)["strategies"] == \
        ["trending", "mining"]


def test_a_save_with_no_key_adds_no_mining_that_was_not_stored(client, db_path, no_env_gemini_key):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('active_strategies', 'curriculum')")
    con.commit()
    con.close()
    client.post("/research/strategies", json={"strategies": ["trending"]})
    _set_gemini_key(db_path, "g-key")
    assert json.loads(client.get("/research/strategies").data)["strategies"] == ["trending"]


def test_enabling_mining_with_a_gemini_key_persists(client, db_path, no_env_gemini_key):
    _set_gemini_key(db_path, "g-key")
    r = client.post("/research/strategies", json={"strategies": ["mining"]})
    assert r.status_code == 200
    assert json.loads(client.get("/research/strategies").data)["strategies"] == ["mining"]


def test_the_mining_refusal_matches_the_mcp_copy():
    """Hand-copied across two processes: the Topics toggle and the agent's
    set_research_strategies must refuse in the same words."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py").read_text()
    start = src.index("MINING_NEEDS_GEMINI_KEY = (")
    end = src.index(")\n", start) + 2
    ns: dict = {}
    exec(src[start:end], ns)
    assert ns["MINING_NEEDS_GEMINI_KEY"] == pipeline.MINING_NEEDS_GEMINI_KEY


def test_set_and_get_research_strategies(client):
    r = client.post("/research/strategies", json={"strategies": ["curriculum", "trending"]})
    assert r.status_code == 200
    data = json.loads(r.data)
    assert set(data["strategies"]) == {"curriculum", "trending"}
    r2 = client.get("/research/strategies")
    assert set(json.loads(r2.data)["strategies"]) == {"curriculum", "trending"}


def test_set_research_strategies_invalid(client):
    r = client.post("/research/strategies", json={"strategies": ["curriculum", "viral"]})
    assert r.status_code == 400


# ── /pipeline/status ─────────────────────────────────────────────────────────

def test_pipeline_status_proposed_count(client, db_path):
    _seed_video(db_path, "TOPIC_PROPOSED")
    r = client.get("/pipeline/status")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["proposed_count"] == 1


def test_pipeline_status_leaves_mining_out_without_a_gemini_key(client, db_path,
                                                               no_env_gemini_key):
    """poll.py builds the research prompt from this list, so filtering here is
    what keeps a scheduled run from being told to mine (TMDEV-165)."""
    data = json.loads(client.get("/pipeline/status").data)
    assert data["active_strategies"] == ["curriculum", "trending"]
    assert data["mining_available"] is False
    _set_gemini_key(db_path, "g-key")
    data = json.loads(client.get("/pipeline/status").data)
    assert data["active_strategies"] == ["curriculum", "trending", "mining"]
    assert data["mining_available"] is True


def test_pipeline_status_proposed_count_zero_when_empty(client):
    r = client.get("/pipeline/status")
    data = json.loads(r.data)
    assert data["proposed_count"] == 0


def test_pipeline_status_reports_timezone(client, monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        r = client.get("/pipeline/status")
        data = json.loads(r.data)
        assert data["timezone"] == "America/New_York"
        assert re.match(r"^[A-Z]{2,5} \(UTC[+-]\d{2}:\d{2}\)$", data["timezone_label"])
    finally:
        monkeypatch.delenv("TZ", raising=False)
        time.tzset()


def test_pipeline_status_timezone_null_when_undetectable(client, monkeypatch):
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: None)
    r = client.get("/pipeline/status")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["timezone"] is None
    assert data["timezone_label"]  # label still present — computed independently


def test_pipeline_status_reports_the_installed_version(client):
    """The dashboard top bar's only source for the version (TMDEV-100).

    Asserted against tubematic_core.version.version() rather than a literal, so
    this test does not have to be edited on every release — and so it fails if a
    second definition of the version is ever introduced and drifts from it."""
    from tubematic_core.version import version

    r = client.get("/pipeline/status")
    assert r.status_code == 200
    assert json.loads(r.data)["version"] == version()


def test_pipeline_status_reports_the_github_repo(client):
    """The dashboard's update check reads the repo from here (TMDEV-114): its
    image cannot import tubematic_core, and the repo is spelled in one place."""
    from tubematic_core.version import GITHUB_REPO

    r = client.get("/pipeline/status")
    assert r.status_code == 200
    assert json.loads(r.data)["github_repo"] == GITHUB_REPO


def test_stats_stays_a_pure_status_count_map(client, db_path):
    """The version rides on /pipeline/status specifically so that /stats does not
    have to change shape. Callers iterate /stats expecting every value to be a
    count, so a non-count key here would break them — this is the guard on that
    decision, not a restatement of test_stats_counts."""
    _seed_video(db_path, "TOPIC_PROPOSED")
    data = json.loads(client.get("/stats").data)
    assert data
    assert all(isinstance(k, str) and isinstance(v, int) for k, v in data.items())


def test_timezone_is_not_a_setting(client):
    """timezone/timezone_label are read-only machine state reported by
    /pipeline/status — must not be PATCH-able via /settings."""
    r = client.post("/settings", json={"timezone": "America/Chicago"})
    assert r.status_code == 400


def test_pipeline_status_has_no_research_due_field(client):
    """research_due (22h-since-last-run gate) was replaced by
    research_runs_today/max_research_runs_per_day (TMDEV-44)."""
    r = client.get("/pipeline/status")
    data = json.loads(r.data)
    assert "research_due" not in data


def test_pipeline_status_research_window_defaults_empty(client):
    r = client.get("/pipeline/status")
    data = json.loads(r.data)
    assert data["research_runs_today"] == 0
    assert data["max_research_runs_per_day"] == 8
    assert data["research_window_resets_at"] is None


# ── /research/record-run ─────────────────────────────────────────────────────

def test_record_research_run_increments_count(client):
    r = client.post("/research/record-run")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data == {"research_runs_today": 1, "max_research_runs_per_day": 8}

    r2 = client.post("/research/record-run")
    data2 = json.loads(r2.data)
    assert data2["research_runs_today"] == 2


def test_record_research_run_reflected_in_pipeline_status(client):
    client.post("/research/record-run")
    r = client.get("/pipeline/status")
    data = json.loads(r.data)
    assert data["research_runs_today"] == 1
    assert data["research_window_resets_at"] is not None


def test_record_research_run_prunes_entries_older_than_24h(client, db_path):
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO settings (key, value) VALUES ('research_run_timestamps', ?)",
        (json.dumps([stale]),),
    )
    con.commit()
    con.close()

    r = client.post("/research/record-run")
    data = json.loads(r.data)
    # The 25h-old entry was pruned; only the fresh one just recorded counts.
    assert data["research_runs_today"] == 1


def test_research_window_resets_at_is_oldest_plus_24h(client):
    client.post("/research/record-run")
    r = client.get("/pipeline/status")
    data = json.loads(r.data)
    oldest = datetime.now(timezone.utc)
    resets_at = datetime.fromisoformat(data["research_window_resets_at"].replace("Z", "+00:00"))
    delta = resets_at - oldest
    # Should be ~24h from the recorded run, allowing slack for test execution time.
    assert 23.9 * 3600 < delta.total_seconds() < 24.1 * 3600


def test_max_research_runs_per_day_setting_roundtrip(client):
    r = client.post("/settings", json={"max_research_runs_per_day": 3})
    assert r.status_code == 200
    assert json.loads(r.data)["max_research_runs_per_day"] == 3

    r2 = client.get("/pipeline/status")
    assert json.loads(r2.data)["max_research_runs_per_day"] == 3


# ── /research/mining-sources ─────────────────────────────────────────────────

def test_get_mining_sources_empty(client):
    r = client.get("/research/mining-sources")
    assert r.status_code == 200
    assert json.loads(r.data) == {"youtube_urls": []}


def test_set_and_get_mining_sources(client):
    urls = ["https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=abcdefghijk"]
    canonical = ["https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                 "https://www.youtube.com/watch?v=abcdefghijk"]
    r = client.post("/research/mining-sources", json={"youtube_urls": urls})
    assert r.status_code == 200
    assert json.loads(r.data) == {"youtube_urls": canonical}

    r2 = client.get("/research/mining-sources")
    assert json.loads(r2.data) == {"youtube_urls": canonical}


def test_set_mining_sources_canonicalises_and_deduplicates(client):
    r = client.post("/research/mining-sources", json={"youtube_urls": [
        "https://youtu.be/dQw4w9WgXcQ?si=x", "https://www.youtube.com/shorts/abcdefghijk",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30"]})
    assert json.loads(r.data)["youtube_urls"] == [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=abcdefghijk"]


def test_set_mining_sources_refuses_the_whole_list_naming_each_bad_entry(client):
    good = ["https://youtu.be/dQw4w9WgXcQ"]
    client.post("/research/mining-sources", json={"youtube_urls": good})
    r = client.post("/research/mining-sources", json={"youtube_urls": [
        "https://youtu.be/abcdefghijk", "file:///etc/passwd", "http://169.254.169.254/"]})
    assert r.status_code == 400
    error = json.loads(r.data)["error"]
    assert "'file:///etc/passwd'" in error and "'http://169.254.169.254/'" in error
    stored = json.loads(client.get("/research/mining-sources").data)["youtube_urls"]
    assert stored == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]   # unchanged


def test_set_mining_sources_caps_the_list(client):
    r = client.post("/research/mining-sources", json={
        "youtube_urls": [f"https://youtu.be/{i:011d}" for i in range(51)]})
    assert r.status_code == 400 and "at most 50" in json.loads(r.data)["error"]


def test_set_mining_sources_clears_on_empty_list(client):
    client.post("/research/mining-sources", json={"youtube_urls": ["https://youtu.be/dQw4w9WgXcQ"]})
    r = client.post("/research/mining-sources", json={"youtube_urls": []})
    assert r.status_code == 200
    assert json.loads(r.data) == {"youtube_urls": []}


def test_set_mining_sources_invalid_not_list(client):
    r = client.post("/research/mining-sources", json={"youtube_urls": "not-a-list"})
    assert r.status_code == 400


def test_set_mining_sources_missing_key(client):
    r = client.post("/research/mining-sources", json={})
    assert r.status_code == 400


# ── /settings ────────────────────────────────────────────────────────────────

def test_get_settings_returns_all_defaults(client):
    r = client.get("/settings")
    assert r.status_code == 200
    data = json.loads(r.data)
    # All keys from SETTINGS_SPEC must be present with correct default types
    assert data["pipeline_paused"] is False
    # Off by default and experimental (TMDEV-165); an onboarded install has
    # the row written explicitly, so this reaches only an unanswered one.
    assert data["gemini_review_enabled"] is False
    assert data["max_render_retries"] == 1
    assert data["max_curriculum_per_run"] == 2
    assert data["max_trending_per_run"] == 2
    assert data["max_mining_per_run"] == 2
    assert data["research_pending_cap"] == 15
    assert data["max_research_runs_per_day"] == 8
    assert data["trending_sources"] == ["GitHub Trending", "Hacker News"]
    assert data["elevenlabs_voice_id"] == ""
    assert data["image_model"] == "gpt-image-2.5-flare"
    # Retired with the Gemini image provider (TMDEV-165).
    assert "image_provider" not in data
    assert data["render_timeout_secs"] == 2400


def test_post_settings_persists_int(client):
    r = client.post("/settings", json={"max_render_retries": 4})
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["max_render_retries"] == 4
    r2 = client.get("/settings")
    assert json.loads(r2.data)["max_render_retries"] == 4


def test_post_settings_pipeline_paused_reflects_in_pipeline_status(client):
    r = client.post("/settings", json={"pipeline_paused": True})
    assert r.status_code == 200
    r2 = client.get("/pipeline/status")
    assert json.loads(r2.data)["paused"] is True


def test_post_settings_unknown_key_returns_400(client):
    r = client.post("/settings", json={"bogus_key": 1})
    assert r.status_code == 400
    assert "Unknown settings" in json.loads(r.data)["error"]


def test_post_settings_negative_int_returns_400(client):
    r = client.post("/settings", json={"max_render_retries": -1})
    assert r.status_code == 400
    assert "max_render_retries" in json.loads(r.data)["error"]


def test_post_settings_invalid_bool_string_returns_400(client):
    r = client.post("/settings", json={"gemini_review_enabled": "nope"})
    assert r.status_code == 400
    assert "gemini_review_enabled" in json.loads(r.data)["error"]


def test_post_settings_elevenlabs_voice_id_persists_when_in_roster(client):
    client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "my_voice", "model_id": "eleven_multilingual_v2"}],
    })
    r = client.post("/settings", json={"elevenlabs_voice_id": "my_voice"})
    assert r.status_code == 200
    r2 = client.get("/settings")
    assert json.loads(r2.data)["elevenlabs_voice_id"] == "my_voice"


def test_post_settings_elevenlabs_voice_id_not_in_roster_is_blanked_on_read(client):
    # Stored, not rejected — the default/roster invariant is enforced on
    # read (_read_all_settings), not by rejecting the write (TMDEV-51).
    r = client.post("/settings", json={"elevenlabs_voice_id": "ghost_voice"})
    assert r.status_code == 200
    r2 = client.get("/settings")
    assert json.loads(r2.data)["elevenlabs_voice_id"] == ""


def test_post_settings_trending_sources_persists_as_list(client):
    r = client.post("/settings", json={"trending_sources": ["Lobsters"]})
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["trending_sources"] == ["Lobsters"]
    r2 = client.get("/settings")
    assert json.loads(r2.data)["trending_sources"] == ["Lobsters"]


def test_post_settings_elevenlabs_voice_id_empty_string_is_valid(client):
    r = client.post("/settings", json={"elevenlabs_voice_id": ""})
    assert r.status_code == 200
    assert json.loads(r.data)["elevenlabs_voice_id"] == ""

    r2 = client.post("/settings", json={"elevenlabs_voice_id": "   "})
    assert r2.status_code == 200
    assert json.loads(r2.data)["elevenlabs_voice_id"] == ""


def test_post_settings_mixed_valid_invalid_rejected_entirely(client):
    r = client.post("/settings", json={"max_render_retries": 4, "bogus_key": 1})
    assert r.status_code == 400
    # Verify the valid key was NOT partially applied
    r2 = client.get("/settings")
    assert json.loads(r2.data)["max_render_retries"] == 1  # still the default


def test_post_settings_elevenlabs_model_id_is_an_unknown_key(client):
    """The install-wide model is gone (TMDEV-121) — each voice carries its
    own. A POST still naming it (an open Settings tab from before the
    upgrade) gets the ordinary unknown-key 400, never a silent no-op."""
    r = client.post("/settings", json={"elevenlabs_model_id": "eleven_v3"})
    assert r.status_code == 400
    assert "elevenlabs_model_id" in json.loads(r.data)["error"]
    assert "elevenlabs_model_id" not in json.loads(client.get("/settings").data)


def test_post_settings_pronunciation_mode_rejected_as_unknown_key(client):
    """pronunciation_mode is derived from a voice's model, never stored, so a
    POST naming it hits the ordinary unknown-key 400."""
    r = client.post("/settings", json={"pronunciation_mode": "phoneme"})
    assert r.status_code == 400
    assert "pronunciation_mode" in json.loads(r.data)["error"]


def test_get_settings_carries_no_install_wide_pronunciation_mode(client):
    """There is no install-wide model to derive it from any more; the mode
    belongs to a voice, and the agent reads it per video from get_video."""
    assert "pronunciation_mode" not in json.loads(client.get("/settings").data)


def test_a_voice_without_a_model_is_rejected(client):
    r = client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "abc123"}]})
    assert r.status_code == 400
    assert "model_id" in json.loads(r.data)["error"]


@pytest.mark.parametrize("model", ["eleven_english_v1", "not_a_model", "", 3,
                                   ["eleven_v3"], {"id": "eleven_v3"}])
def test_a_voice_with_an_unknown_model_is_rejected(client, model):
    """eleven_english_v1 is retired at ElevenLabs (TMDEV-122), so a voice on
    it could never voice anything."""
    r = client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "abc123", "model_id": model}]})
    assert r.status_code == 400


def test_a_stored_roster_with_an_unhashable_model_reads_as_empty(client):
    """A corrupt stored value falls back to the default; an unhashable
    model_id must not escape that as a TypeError and 500 every settings read."""
    con = sqlite3.connect(os.environ["TUBEMATIC_DB"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('elevenlabs_voices', ?)",
                (json.dumps([{"name": "A", "voice_id": "a", "model_id": ["eleven_v3"]}]),))
    con.commit()
    con.close()
    r = client.get("/settings")
    assert r.status_code == 200
    assert json.loads(r.data)["elevenlabs_voices"] == []


def test_each_voice_keeps_its_own_model(client):
    roster = [{"name": "Rachel", "voice_id": "r1", "model_id": "eleven_multilingual_v2"},
              {"name": "Adam", "voice_id": "a1", "model_id": "eleven_v3"}]
    assert client.post("/settings", json={"elevenlabs_voices": roster}).status_code == 200
    assert json.loads(client.get("/settings").data)["elevenlabs_voices"] == roster


def test_the_elevenlabs_model_sets_match_the_dashboard_copy():
    """The model sets live once, in tubematic_core.voice_models, which the MCP
    server, this API and onboarding all import. The dashboard cannot, and keeps
    a TypeScript copy for the Settings notes. A comment is not a check, so it
    is compared as source text."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[3]

    def _models(text, name):
        m = re.search(name + r"\s*=\s*[\[{]([^\]}]*)[\]}]", text)
        assert m, f"could not find {name}"
        return set(re.findall(r'"(eleven_[a-z0-9_]+)"', m.group(1)))

    dash_src = (root / "dashboard" / "app" / "settings" / "page.tsx").read_text()
    assert _models(dash_src, "PHONEME_COMPATIBLE_MODELS") == pipeline.PHONEME_COMPATIBLE_MODELS
    assert _models(dash_src, "IPA_COMPATIBLE_MODELS") == pipeline.IPA_COMPATIBLE_MODELS
    assert _models(dash_src, "DICTIONARY_COMPATIBLE_MODELS") == pipeline.DICTIONARY_COMPATIBLE_MODELS


def test_the_api_uses_the_shared_model_sets():
    from tubematic_core import voice_models
    assert pipeline.DICTIONARY_COMPATIBLE_MODELS is voice_models.DICTIONARY_COMPATIBLE_MODELS


# ── pronunciation_lexicon (TMDEV-26 follow-up) ────────────────────────────────

def test_post_settings_pronunciation_lexicon_persists(client):
    entries = [{"term": "Vhagar", "respell": "Vah-gar"}, {"term": "SYN", "respell": "S-Y-N"}]
    r = client.post("/settings", json={"pronunciation_lexicon": entries})
    assert r.status_code == 200
    r2 = client.get("/settings")
    assert json.loads(r2.data)["pronunciation_lexicon"] == entries


def test_post_settings_pronunciation_lexicon_defaults_to_empty(client):
    r = client.get("/settings")
    assert json.loads(r.data)["pronunciation_lexicon"] == []


def test_post_settings_pronunciation_lexicon_rejects_whitespace_in_respell(client):
    r = client.post("/settings", json={
        "pronunciation_lexicon": [{"term": "whoami", "respell": "who am i"}]
    })
    assert r.status_code == 400
    assert "pronunciation_lexicon" in json.loads(r.data)["error"]


def test_post_settings_pronunciation_lexicon_rejects_duplicate_term(client):
    r = client.post("/settings", json={
        "pronunciation_lexicon": [
            {"term": "SYN", "respell": "S-Y-N"},
            {"term": "SYN", "respell": "sin"},
        ]
    })
    assert r.status_code == 400
    assert "pronunciation_lexicon" in json.loads(r.data)["error"]


def test_post_settings_pronunciation_lexicon_rejects_missing_keys(client):
    r = client.post("/settings", json={"pronunciation_lexicon": [{"term": "SYN"}]})
    assert r.status_code == 400


def test_post_settings_pronunciation_lexicon_rejects_over_cap(client):
    from pipeline import MAX_LEXICON_ENTRIES
    entries = [{"term": f"t{i}", "respell": f"r{i}"} for i in range(MAX_LEXICON_ENTRIES + 1)]
    r = client.post("/settings", json={"pronunciation_lexicon": entries})
    assert r.status_code == 400
    assert "pronunciation_lexicon" in json.loads(r.data)["error"]


# ── elevenlabs_voices (TMDEV-51) ──────────────────────────────────────────────

def test_post_settings_elevenlabs_voices_persists(client):
    voices = [
        {"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"},
        {"name": "Energetic", "voice_id": "def456", "model_id": "eleven_multilingual_v2"},
    ]
    r = client.post("/settings", json={"elevenlabs_voices": voices})
    assert r.status_code == 200
    r2 = client.get("/settings")
    assert json.loads(r2.data)["elevenlabs_voices"] == voices


def test_post_settings_elevenlabs_voices_rejects_over_cap(client):
    voices = [{"name": f"v{i}", "voice_id": f"id{i}"} for i in range(6)]
    r = client.post("/settings", json={"elevenlabs_voices": voices})
    assert r.status_code == 400
    assert "elevenlabs_voices" in json.loads(r.data)["error"]


def test_post_settings_elevenlabs_voices_rejects_duplicate_name(client):
    voices = [
        {"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"},
        {"name": "Narrator", "voice_id": "def456", "model_id": "eleven_multilingual_v2"},
    ]
    r = client.post("/settings", json={"elevenlabs_voices": voices})
    assert r.status_code == 400


def test_post_settings_elevenlabs_voices_rejects_duplicate_voice_id(client):
    voices = [
        {"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"},
        {"name": "Energetic", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"},
    ]
    r = client.post("/settings", json={"elevenlabs_voices": voices})
    assert r.status_code == 400


def test_post_settings_elevenlabs_voices_rejects_empty_name_or_id(client):
    r = client.post("/settings", json={"elevenlabs_voices": [{"name": "", "voice_id": "x", "model_id": "eleven_multilingual_v2"}]})
    assert r.status_code == 400
    r2 = client.post("/settings", json={"elevenlabs_voices": [{"name": "x", "voice_id": "", "model_id": "eleven_multilingual_v2"}]})
    assert r2.status_code == 400


def test_post_settings_elevenlabs_voices_rejects_bad_shape(client):
    r = client.post("/settings", json={"elevenlabs_voices": [{"name": "x"}]})
    assert r.status_code == 400
    r2 = client.post("/settings", json={"elevenlabs_voices": "not-a-list"})
    assert r2.status_code == 400


def test_corrupt_stored_voices_resets_to_empty_and_blanks_default(client, db_path):
    """A stored elevenlabs_voices value that no longer parses/validates falls
    back to [] (the SETTINGS_SPEC default) via the corrupt-value path in
    _read_all_settings, same as any other setting — and elevenlabs_voice_id,
    even though its own stored value is untouched, reads back blanked since
    it's no longer in the (now-empty) roster."""
    client.post("/settings", json={
        "elevenlabs_voices": [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}],
        "elevenlabs_voice_id": "abc123",
    })
    con = sqlite3.connect(db_path)
    con.execute(
        "UPDATE settings SET value = ? WHERE key = 'elevenlabs_voices'",
        ("not json",),
    )
    con.commit()
    con.close()

    r = client.get("/settings")
    data = json.loads(r.data)
    assert data["elevenlabs_voices"] == []
    assert data["elevenlabs_voice_id"] == ""


def test_unrelated_settings_save_succeeds_despite_corrupt_voices(client, db_path):
    """The default/roster invariant must be enforced by normalizing on read,
    not by a cross-field check in post_settings — otherwise a corrupt
    elevenlabs_voices row (see above) would make an unrelated settings save
    (e.g. max_render_retries) 400 for a reason that has nothing to do with
    voices."""
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO settings (key, value) VALUES ('elevenlabs_voices', 'not json')"
    )
    con.execute(
        "INSERT INTO settings (key, value) VALUES ('elevenlabs_voice_id', 'abc123')"
    )
    con.commit()
    con.close()

    r = client.post("/settings", json={"max_render_retries": 4})
    assert r.status_code == 200
    assert json.loads(r.data)["max_render_retries"] == 4


# ── /voices/<voice_id>/preview (TMDEV-51 follow-up) ───────────────────────────

def _seed_roster(client, voice_id="abc123", name="Narrator", model_id="eleven_multilingual_v2"):
    r = client.post("/settings", json={
        "elevenlabs_voices": [{"name": name, "voice_id": voice_id, "model_id": model_id}],
    })
    assert r.status_code == 200


def _mock_elevenlabs_response(status_code=200, content=b"fake-mp3-bytes", text="",
                              headers=None):
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = text
    resp.headers = {"character-cost": "117", "request-id": "req-1"} if headers is None \
        else headers
    return resp


def test_voice_preview_rejects_bad_voice_id_charset(client):
    r = client.post("/voices/not valid!/preview")
    assert r.status_code == 400
    assert "voice_id" in json.loads(r.data)["error"]


def test_voice_preview_rejects_voice_not_in_roster(client):
    r = client.post("/voices/nope123/preview")
    assert r.status_code == 400
    assert "not in elevenlabs_voices" in json.loads(r.data)["error"]


def test_voice_preview_no_api_key_returns_503(client, monkeypatch, tmp_path):
    import pipeline
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)
    r = client.post("/voices/abc123/preview")
    assert r.status_code == 503


def test_voice_preview_generates_and_caches(client, monkeypatch, tmp_path):
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)

    with mock.patch("httpx.Client") as mock_client_cls:
        mock_post = mock_client_cls.return_value.__enter__.return_value.post
        mock_post.return_value = _mock_elevenlabs_response()
        r = client.post("/voices/abc123/preview")

    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["cached"] is False
    assert data["credits"] == 117
    assert data["path"].startswith("/output_videos/voice-previews/")
    assert data["path"].endswith(".mp3")
    cached_file = tmp_path / "voice-previews" / data["path"].rsplit("/", 1)[-1]
    assert cached_file.read_bytes() == b"fake-mp3-bytes"

    # Second call: served from cache, no second ElevenLabs request.
    with mock.patch("httpx.Client") as mock_client_cls2:
        r2 = client.post("/voices/abc123/preview")
        mock_client_cls2.assert_not_called()

    assert r2.status_code == 200
    data2 = json.loads(r2.data)
    assert data2 == {"path": data["path"], "cached": True, "credits": 0}

    # Exactly one usage row — the generated preview, in credits, with no video.
    import sqlite3
    con = sqlite3.connect(pipeline.os.environ["TUBEMATIC_DB"])
    rows = con.execute("SELECT service, operation, units, cost_basis, request_id, "
                       "(SELECT COUNT(*) FROM usage_event_videos) FROM usage_events").fetchall()
    con.close()
    assert rows == [("elevenlabs", "voice_preview", '{"credits": 117}', "credits", "req-1", 0)]


def _preview(client, **kwargs):
    with mock.patch("httpx.Client") as mock_client_cls:
        post = mock_client_cls.return_value.__enter__.return_value.post
        post.return_value = _mock_elevenlabs_response()
        r = client.post("/voices/abc123/preview", **kwargs)
    sent = post.call_args.kwargs["json"]["model_id"] if post.called else None
    return r, sent


def test_voice_preview_uses_the_voices_own_model(client, monkeypatch, tmp_path):
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client, model_id="eleven_v3")
    r, sent = _preview(client)
    assert r.status_code == 200 and sent == "eleven_v3"


def test_changing_a_voices_model_regenerates_its_preview(client, monkeypatch, tmp_path):
    """The ticket's requirement: after a model change the next play is a new
    sample, not the cached one. The cache key includes the model."""
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)
    r1, _ = _preview(client)
    _seed_roster(client, model_id="eleven_turbo_v2")
    r2, sent = _preview(client)
    assert sent == "eleven_turbo_v2"
    assert json.loads(r1.data)["path"] != json.loads(r2.data)["path"]
    assert json.loads(r2.data)["cached"] is False


def test_voice_preview_body_model_previews_an_unsaved_change(client, monkeypatch, tmp_path):
    """The Settings page previews a model picked in its draft before it is
    saved, so a human can hear the choice before committing to it."""
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)
    r, sent = _preview(client, json={"model_id": "eleven_flash_v2_5"})
    assert r.status_code == 200 and sent == "eleven_flash_v2_5"


@pytest.mark.parametrize("model", ["eleven_english_v1", "nope", 7, ["eleven_v3"]])
def test_voice_preview_refuses_an_unknown_body_model_before_spend(client, monkeypatch, tmp_path, model):
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)
    r, sent = _preview(client, json={"model_id": model})
    assert r.status_code == 400 and sent is None


def test_voice_preview_with_a_non_json_body_uses_the_voices_model(client, monkeypatch, tmp_path):
    """The dashboard proxy forwards whatever body it was given; a preview with
    none, or with a stray non-JSON one, must still work."""
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client, model_id="eleven_v3")
    r, sent = _preview(client, data="x", content_type="text/plain")
    assert r.status_code == 200 and sent == "eleven_v3"


def test_voice_preview_elevenlabs_non_200_returns_502(client, monkeypatch, tmp_path):
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)

    with mock.patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value.post.return_value = (
            _mock_elevenlabs_response(status_code=401, content=b"", text="unauthorized")
        )
        r = client.post("/voices/abc123/preview")

    assert r.status_code == 502
    assert "ElevenLabs" in json.loads(r.data)["error"]


def test_voice_preview_elevenlabs_request_exception_returns_502(client, monkeypatch, tmp_path):
    import pipeline
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
    _seed_roster(client)

    with mock.patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value.post.side_effect = RuntimeError("boom")
        r = client.post("/voices/abc123/preview")

    assert r.status_code == 502


# ── image_model (TMDEV-29, OpenAI-only since TMDEV-165) ──────────────────────

def test_post_settings_image_model_invalid_returns_400(client):
    r = client.post("/settings", json={"image_model": "dall-e-9"})
    assert r.status_code == 400
    assert "image_model" in json.loads(r.data)["error"]


@pytest.mark.parametrize("model", ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
def test_post_settings_image_model_persists_any_openai_model(client, model):
    r = client.post("/settings", json={"image_model": model})
    assert r.status_code == 200
    assert json.loads(client.get("/settings").data)["image_model"] == model


@pytest.mark.parametrize("model", ["gemini-2.5-flash-image", "gemini-3.1-flash-image",
                                   "gemini-3-pro-image", "gemini-3-pro-image-preview",
                                   "gpt-image-2"])
def test_a_retired_image_model_is_refused(client, model):
    """Gemini left the image catalog (TMDEV-165) and gpt-image-2 lost its
    transparency (TMDEV-148); migrations 0016 and 0011 move stored rows off them."""
    r = client.post("/settings", json={"image_model": model})
    assert r.status_code == 400
    assert "image_model" in json.loads(r.data)["error"]


def test_image_provider_is_no_longer_a_setting(client):
    r = client.post("/settings", json={"image_provider": "openai"})
    assert r.status_code == 400
    assert "image_provider" in json.loads(r.data)["error"]


# ── character_model (TMDEV-148) ───────────────────────────────────────────────

def test_character_model_defaults_to_flare(client):
    assert json.loads(client.get("/settings").data)["character_model"] == "gpt-image-2.5-flare"


def test_character_model_is_independent_of_the_image_model(client):
    r = client.post("/settings", json={"character_model": "gpt-image-2.5-sunburst"})
    assert r.status_code == 200
    data = json.loads(client.get("/settings").data)
    assert (data["character_model"], data["image_model"]) == \
        ("gpt-image-2.5-sunburst", "gpt-image-2.5-flare")


def test_character_model_refuses_a_model_without_transparency(client):
    for bad in ("gpt-image-2", "gemini-2.5-flash-image", ""):
        r = client.post("/settings", json={"character_model": bad})
        assert r.status_code == 400, bad
        assert "transparent background" in json.loads(r.data)["error"]
    assert json.loads(client.get("/settings").data)["character_model"] == "gpt-image-2.5-flare"


# ── render_timeout_secs (TMDEV-57) ────────────────────────────────────────────

def test_post_settings_render_timeout_secs_persists(client):
    r = client.post("/settings", json={"render_timeout_secs": 2400})
    assert r.status_code == 200
    assert json.loads(client.get("/settings").data)["render_timeout_secs"] == 2400


def test_post_settings_render_timeout_secs_below_floor_returns_400(client):
    """Below 60s a render can never complete before timing out — every
    attempt would guarantee-fail (TMDEV-57)."""
    r = client.post("/settings", json={"render_timeout_secs": 30})
    assert r.status_code == 400
    assert "render_timeout_secs" in json.loads(r.data)["error"]
    assert json.loads(client.get("/settings").data)["render_timeout_secs"] == 2400  # unchanged


def test_post_settings_render_timeout_secs_at_floor_is_accepted(client):
    r = client.post("/settings", json={"render_timeout_secs": 60})
    assert r.status_code == 200
    assert json.loads(client.get("/settings").data)["render_timeout_secs"] == 60


def test_post_settings_render_timeout_secs_negative_returns_400(client):
    """The generic nonneg check fires before the render_timeout_secs-specific
    floor — both reject, but confirm the generic path isn't bypassed."""
    r = client.post("/settings", json={"render_timeout_secs": -1})
    assert r.status_code == 400


# ── AI review settings (VQA-7) ────────────────────────────────────────────

def test_ai_review_settings_defaults(client):
    s = json.loads(client.get("/settings").data)
    assert s["ai_review_model"] == "gemini-2.5-flash"   # unchanged for existing installs
    assert s["ai_review_fps"] == 10
    assert s["ai_review_max_loops"] == 1
    # The split: the render retry budget keeps its own, higher default.
    assert s["max_render_retries"] == 1


def test_post_settings_ai_review_model_persists(client):
    r = client.post("/settings", json={"ai_review_model": "gemini-3.6-flash"})
    assert r.status_code == 200
    assert json.loads(client.get("/settings").data)["ai_review_model"] == "gemini-3.6-flash"


def test_post_settings_ai_review_model_rejects_unknown_model(client):
    """Allowlisted rather than free-text: the fps clamp needs a measured
    tokens-per-frame figure per model, and an image model here would 400 on
    every review — which fails open, shipping videos unreviewed in silence."""
    for bad in ("gemini-2.5-flash-image", "gpt-image-2.5-flare", "gemini-9-turbo", ""):
        r = client.post("/settings", json={"ai_review_model": bad})
        assert r.status_code == 400, bad
        assert "ai_review_model" in json.loads(r.data)["error"]
    assert json.loads(client.get("/settings").data)["ai_review_model"] == "gemini-2.5-flash"


def test_post_settings_ai_review_fps_persists_across_the_valid_range(client):
    for good in (1, 10, 24):
        r = client.post("/settings", json={"ai_review_fps": good})
        assert r.status_code == 200, good
        assert json.loads(client.get("/settings").data)["ai_review_fps"] == good


def test_post_settings_ai_review_fps_rejects_out_of_range(client):
    """Gemini's documented videoMetadata.fps range is (0, 24]; outside it the
    request 400s and the review fails open — silently shipping the video."""
    for bad in (0, 25, 60, -1):
        r = client.post("/settings", json={"ai_review_fps": bad})
        assert r.status_code == 400, bad
    assert json.loads(client.get("/settings").data)["ai_review_fps"] == 10


def test_post_settings_ai_review_max_loops_rejects_out_of_range(client):
    """VQA-7 asked for default 1 and max 2. 0 is rejected too: the routing
    boundary is `count > cap`, so 0 would disable the revision loop outright
    rather than meaning 'review once'."""
    assert client.post("/settings", json={"ai_review_max_loops": 2}).status_code == 200
    for bad in (0, 3, 10):
        r = client.post("/settings", json={"ai_review_max_loops": bad})
        assert r.status_code == 400, bad
    assert json.loads(client.get("/settings").data)["ai_review_max_loops"] == 2


def test_max_render_retries_still_accepts_values_above_the_review_cap(client):
    """max_render_retries now caps render retries only, so it keeps its old
    unbounded-above behaviour — the 1-2 ceiling applies to the review loop."""
    r = client.post("/settings", json={"max_render_retries": 5})
    assert r.status_code == 200
    assert json.loads(client.get("/settings").data)["max_render_retries"] == 5


# ── /pipeline/pause ───────────────────────────────────────────────────────────

def test_pipeline_pause_true_then_false(client):
    r = client.post("/pipeline/pause", json={"paused": True})
    assert r.status_code == 200
    assert json.loads(r.data) == {"paused": True}

    r2 = client.get("/pipeline/status")
    assert json.loads(r2.data)["paused"] is True

    r3 = client.post("/pipeline/pause", json={"paused": False})
    assert r3.status_code == 200
    assert json.loads(r3.data) == {"paused": False}

    r4 = client.get("/pipeline/status")
    assert json.loads(r4.data)["paused"] is False


def test_pipeline_pause_invalid_value_returns_400(client):
    r = client.post("/pipeline/pause", json={"paused": "maybe"})
    assert r.status_code == 400


# ── /pipeline/status research_pending_cap ─────────────────────────────────────

def test_pipeline_status_research_pending_cap_default(client):
    r = client.get("/pipeline/status")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["research_pending_cap"] == 15


def test_pipeline_status_research_pending_cap_after_update(client):
    client.post("/settings", json={"research_pending_cap": 3})
    r = client.get("/pipeline/status")
    assert json.loads(r.data)["research_pending_cap"] == 3


# ── /research/mine is gone ───────────────────────────────────────────────────
# Mining runs only through the MCP tool, which checks every URL before the
# first paid call and allows one run at a time. The HTTP route had neither and
# nothing called it, so it was deleted rather than hardened twice.

def test_the_mining_route_is_gone(client):
    r = client.post("/research/mine", json={"project_id": "test-project",
                                             "youtube_urls": ["https://youtu.be/dQw4w9WgXcQ"]})
    assert r.status_code in (404, 405)


# ── Migration idempotence (TMDEV-56) ────────────────────────────────────────
# mcp/server.py has its own copy of this migration guard and its own test in
# mcp/tests/test_pipeline_status.py -- this mirrors it for pipeline.py's copy,
# which is the one that actually runs first against a live DB (it fires at
# Flask blueprint construction, i.e. container start, ahead of any agent tool
# call reaching mcp/server.py's _init_db).

def test_pipeline_init_db_renames_animatability_column(tmp_path):
    """Build a DB with the pre-TMDEV-56 column name, run pipeline._init_db
    twice, and confirm: the column is renamed, existing data survives, and
    the second run is a clean no-op."""
    from pipeline import _init_db as pipeline_init_db

    db_path = str(tmp_path / "old.db")
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

    pipeline_init_db(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)")}
    row = con.execute("SELECT producibility_score FROM videos WHERE id = 'vid_old'").fetchone()
    con.close()
    assert "producibility_score" in cols
    assert "animatability_score" not in cols
    assert row["producibility_score"] == 7

    # Second run must be a clean no-op, not an error on the already-renamed column.
    pipeline_init_db(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT producibility_score FROM videos WHERE id = 'vid_old'").fetchone()
    con.close()
    assert row["producibility_score"] == 7


def test_pipeline_init_db_adds_tts_text_column_to_an_old_db(tmp_path):
    """VQA-6: videos.tts_text is added by the same idempotent ADD-COLUMN loop.
    This is the copy that runs first against a live DB (Flask blueprint
    construction, i.e. container start), so the render worker can rely on the
    column existing before it ever selects it."""
    from pipeline import _init_db as pipeline_init_db

    db_path = str(tmp_path / "no_tts.db")
    con = sqlite3.connect(db_path)
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
        "VALUES ('vid_old', 'pre-existing topic', 'an old script', "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    con.commit()
    con.close()

    pipeline_init_db(db_path)
    pipeline_init_db(db_path)  # idempotent — the column-exists guard must hold

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT script, tts_text FROM videos WHERE id = 'vid_old'").fetchone()
    con.close()
    # An already-voiced row predating this column has no record of what was
    # spoken; the review degrades to the authored script rather than failing.
    assert row["tts_text"] == ""
    assert row["script"] == "an old script"


def test_pipeline_init_db_fresh_db_untouched_by_rename(db_path):
    """The db_path fixture already builds a fresh schema with producibility_score
    directly (no _init_db call needed) -- confirm that's consistent with what
    _init_db itself would produce, and that _init_db is a no-op against it."""
    from pipeline import _init_db as pipeline_init_db

    pipeline_init_db(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cols = {r["name"] for r in con.execute("PRAGMA table_info(videos)")}
    con.close()
    assert "producibility_score" in cols
    assert "animatability_score" not in cols


# ── db.py helpers ─────────────────────────────────────────────────────────────

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import db as db_module


@pytest.fixture
def bare_db(tmp_path):
    """Minimal DB with a single video row for db.py helper tests."""
    p = str(tmp_path / "bare.db")
    con = sqlite3.connect(p)
    con.executescript("""
        CREATE TABLE videos (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'TOPIC_PROPOSED',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            author TEXT NOT NULL CHECK (author IN ('human','agent')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    con.execute(
        "INSERT INTO videos (id, topic, status, updated_at) VALUES ('v1', 'DNS', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z')"
    )
    con.commit()
    con.close()
    return p


def test_set_status_basic(bare_db):
    result = db_module.set_status(bare_db, "v1", "TOPIC_APPROVED")
    assert result is True
    con = sqlite3.connect(bare_db)
    row = con.execute("SELECT status FROM videos WHERE id = 'v1'").fetchone()
    con.close()
    assert row[0] == "TOPIC_APPROVED"


def test_set_status_only_if_matches(bare_db):
    result = db_module.set_status(bare_db, "v1", "TOPIC_APPROVED", only_if="TOPIC_PROPOSED")
    assert result is True
    con = sqlite3.connect(bare_db)
    row = con.execute("SELECT status FROM videos WHERE id = 'v1'").fetchone()
    con.close()
    assert row[0] == "TOPIC_APPROVED"


def test_set_status_only_if_mismatch_noop(bare_db):
    result = db_module.set_status(bare_db, "v1", "TOPIC_APPROVED", only_if="RENDERING")
    assert result is False
    con = sqlite3.connect(bare_db)
    row = con.execute("SELECT status FROM videos WHERE id = 'v1'").fetchone()
    con.close()
    assert row[0] == "TOPIC_PROPOSED"  # unchanged


def test_set_status_unknown_video(bare_db):
    result = db_module.set_status(bare_db, "nonexistent", "TOPIC_APPROVED")
    assert result is False


def test_update_fields(bare_db):
    # Add a column we can update — reuse status for simplicity
    db_module.update_fields(bare_db, "v1", status="VOICING")
    con = sqlite3.connect(bare_db)
    row = con.execute("SELECT status FROM videos WHERE id = 'v1'").fetchone()
    con.close()
    assert row[0] == "VOICING"


def test_update_fields_sets_updated_at(bare_db):
    db_module.update_fields(bare_db, "v1", status="TOPIC_APPROVED")
    con = sqlite3.connect(bare_db)
    row = con.execute("SELECT updated_at FROM videos WHERE id = 'v1'").fetchone()
    con.close()
    assert row[0] != "2026-01-01T00:00:00Z"  # updated_at was changed


def test_add_comment(bare_db):
    db_module.add_comment(bare_db, "v1", "agent", "render started")
    con = sqlite3.connect(bare_db)
    row = con.execute("SELECT author, content FROM comments WHERE video_id = 'v1'").fetchone()
    con.close()
    assert row[0] == "agent"
    assert row[1] == "render started"


def test_add_comment_multiple(bare_db):
    db_module.add_comment(bare_db, "v1", "agent", "first")
    db_module.add_comment(bare_db, "v1", "agent", "second")
    con = sqlite3.connect(bare_db)
    rows = con.execute("SELECT content FROM comments WHERE video_id = 'v1' ORDER BY id").fetchall()
    con.close()
    assert [r[0] for r in rows] == ["first", "second"]


# ── ai_review.py ──────────────────────────────────────────────────────────────

import ai_review as ai_review_module



def test_ai_review_no_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    result = ai_review_module.run_ai_review(str(video), {})
    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "error" in result


def test_ai_review_passes(monkeypatch, tmp_path):
    # NOTE: run_ai_review is now a 4-request flow (resumable upload start,
    # byte upload, ACTIVE-state poll, generateContent) — see TMDEV-46 and the
    # dedicated wire-level coverage in tests/test_ai_review.py. This test
    # still mocks httpx.Client wholesale (its purpose is the end-to-end
    # passed/defects contract, not wire shape), just extended to the new
    # 4-call sequence instead of 2.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake-video-data")

    start_resp = mock.MagicMock()
    start_resp.raise_for_status = mock.MagicMock()
    start_resp.headers = {"x-goog-upload-url": "https://upload.example/session"}

    upload_resp = mock.MagicMock()
    upload_resp.raise_for_status = mock.MagicMock()
    upload_resp.json.return_value = {"file": {"uri": "gs://files/test", "name": "files/test"}}

    poll_resp = mock.MagicMock()
    poll_resp.raise_for_status = mock.MagicMock()
    poll_resp.json.return_value = {"state": "ACTIVE"}

    review_resp = mock.MagicMock()
    review_resp.raise_for_status = mock.MagicMock()
    review_resp.json.return_value = {
        "candidates": [{"content": {"parts": [
            {"text": '{"overall": "fine", "mustFix": [], "suggestions": []}'}
        ]}}]
    }

    client_instance = mock.MagicMock()
    client_instance.post.side_effect = [start_resp, upload_resp, review_resp]
    client_instance.get.return_value = poll_resp
    mock_ctx = mock.MagicMock()
    mock_ctx.__enter__ = mock.MagicMock(return_value=client_instance)
    mock_ctx.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch("httpx.Client", return_value=mock_ctx):
        result = ai_review_module.run_ai_review(str(video), {"scenes": []})

    assert result["must_fix"] == []
    assert result["suggestions"] == []


def test_ai_review_defects_found(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake-video-data")

    start_resp = mock.MagicMock()
    start_resp.raise_for_status = mock.MagicMock()
    start_resp.headers = {"x-goog-upload-url": "https://upload.example/session"}

    upload_resp = mock.MagicMock()
    upload_resp.raise_for_status = mock.MagicMock()
    upload_resp.json.return_value = {"file": {"uri": "gs://files/test", "name": "files/test"}}

    poll_resp = mock.MagicMock()
    poll_resp.raise_for_status = mock.MagicMock()
    poll_resp.json.return_value = {"state": "ACTIVE"}

    review_resp = mock.MagicMock()
    review_resp.raise_for_status = mock.MagicMock()
    review_resp.json.return_value = {
        "candidates": [{"content": {"parts": [
            {"text": '{"overall": "two issues", "mustFix": '
                     '[{"type": "text_offscreen"}, {"type": "sync_drift"}], "suggestions": []}'}
        ]}}]
    }

    # Each httpx.Client() call returns a context manager whose .post()/.get()
    # return the correct response in sequence (start, upload, [poll]*, review).
    client_instance = mock.MagicMock()
    client_instance.post.side_effect = [start_resp, upload_resp, review_resp]
    client_instance.get.return_value = poll_resp
    mock_ctx = mock.MagicMock()
    mock_ctx.__enter__ = mock.MagicMock(return_value=client_instance)
    mock_ctx.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch("httpx.Client", return_value=mock_ctx):
        result = ai_review_module.run_ai_review(str(video), {})

    types = [d["type"] for d in result["must_fix"]]
    assert "text_offscreen" in types
    assert "sync_drift" in types


def test_ai_review_upload_failure_fails_open(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake-video-data")

    upload_resp = mock.MagicMock()
    upload_resp.raise_for_status.side_effect = Exception("upload error")

    with mock.patch("httpx.Client") as mock_client_cls:
        mock_client_cls.return_value.__enter__.return_value.post.return_value = upload_resp
        result = ai_review_module.run_ai_review(str(video), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "error" in result


def test_ai_review_review_api_error_fails_open(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake-video-data")

    upload_resp = mock.MagicMock()
    upload_resp.raise_for_status = mock.MagicMock()
    upload_resp.json.return_value = {"file": {"uri": "gs://files/test"}}

    review_resp = mock.MagicMock()
    review_resp.raise_for_status.side_effect = Exception("API 500")

    client_instance = mock.MagicMock()
    client_instance.post.side_effect = [upload_resp, review_resp]
    mock_ctx = mock.MagicMock()
    mock_ctx.__enter__ = mock.MagicMock(return_value=client_instance)
    mock_ctx.__exit__ = mock.MagicMock(return_value=False)

    with mock.patch("httpx.Client", return_value=mock_ctx):
        result = ai_review_module.run_ai_review(str(video), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "error" in result


def test_ai_review_missing_file_fails_open(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    result = ai_review_module.run_ai_review("/nonexistent/path/video.mp4", {})
    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "error" in result


# ── gemini_feedback: clipped in lists, whole in the detail route (VQA-7) ──

def _seed_video_with_feedback(db_path, feedback: str, video_id="vid-fb"):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
        "gemini_feedback, created_at, updated_at) "
        "VALUES (?, 'proj-1', 't', 'manual', 8, 'VIDEO_READY', ?, "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (video_id, feedback),
    )
    con.commit()
    con.close()
    return video_id


def test_video_detail_returns_the_whole_review(client, db_path):
    """The agent and the dashboard's 'read more' both resolve here, and the
    stored review is uncapped — so this route must never clip it."""
    feedback = "x" * (pipeline.GEMINI_FEEDBACK_LIST_PREVIEW_CHARS * 3)
    vid = _seed_video_with_feedback(db_path, feedback)

    body = json.loads(client.get(f"/videos/{vid}").data)
    assert body["gemini_feedback"] == feedback
    assert body["gemini_feedback_truncated"] is False


def test_video_list_clips_a_long_review_and_flags_it(client, db_path):
    """GET /videos returns every row, so shipping full reviews there grows the
    payload without bound for content no list view renders."""
    feedback = "y" * (pipeline.GEMINI_FEEDBACK_LIST_PREVIEW_CHARS * 3)
    _seed_video_with_feedback(db_path, feedback)

    row = next(v for v in json.loads(client.get("/videos").data) if v["id"] == "vid-fb")
    assert len(row["gemini_feedback"]) == pipeline.GEMINI_FEEDBACK_LIST_PREVIEW_CHARS
    assert row["gemini_feedback_truncated"] is True
    # ...and the preview is a real prefix of the stored value, not a summary.
    assert feedback.startswith(row["gemini_feedback"])


def test_video_list_leaves_a_short_review_intact(client, db_path):
    short = "**Overall:** all good.\n\nNo blocking errors."
    _seed_video_with_feedback(db_path, short)

    row = next(v for v in json.loads(client.get("/videos").data) if v["id"] == "vid-fb")
    assert row["gemini_feedback"] == short
    assert row["gemini_feedback_truncated"] is False


def test_actionable_list_clips_too(client, db_path):
    """The pipeline view reads /videos/actionable, so it needs the same
    treatment — clipping only /videos would leave the main view unbounded."""
    feedback = "z" * (pipeline.GEMINI_FEEDBACK_LIST_PREVIEW_CHARS * 3)
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO videos (id, project_id, topic, strategy, producibility_score, status, "
        "gemini_feedback, created_at, updated_at) "
        "VALUES ('vid-act', 'proj-1', 't', 'manual', 8, 'VIDEO_READY', ?, "
        "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
        (feedback,),
    )
    con.commit()
    con.close()

    row = next(v for v in json.loads(client.get("/videos/actionable").data) if v["id"] == "vid-act")
    assert row["gemini_feedback_truncated"] is True
    assert len(row["gemini_feedback"]) == pipeline.GEMINI_FEEDBACK_LIST_PREVIEW_CHARS


# ── Secret settings: API keys in the DB (TMDEV-73) ──────────────────────────
# The DB is the single source of truth for credentials; .env is gone. Stored
# raw so every in-process consumer reads a usable key, masked at both /settings
# route boundaries so the dashboard never receives one.

SECRET_KEYS = [
    "elevenlabs_api_key",
    "gemini_api_key",
    "openai_api_key",
    "youtube_transcript_api_key",
    "postforme_api_key",
]


def _stored(db_path, key):
    """Read a settings row straight from SQLite, bypassing the mask."""
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    con.close()
    return row[0] if row else None


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_secret_defaults_to_empty_and_reads_as_empty_mask(client, key):
    data = json.loads(client.get("/settings").data)
    assert data[key] == ""


@pytest.mark.parametrize("key", SECRET_KEYS)
def test_secret_is_stored_raw_but_never_returned(client, db_path, key):
    r = client.post("/settings", json={key: "sk-live-abcdefghijkl4f2a"})
    assert r.status_code == 200
    # The POST response is what the dashboard keeps as local state — it must
    # be masked too, not just GET.
    assert json.loads(r.data)[key] == "••••••••4f2a"
    assert json.loads(client.get("/settings").data)[key] == "••••••••4f2a"
    # ...while the stored value stays usable for mcp/server.py and the worker.
    assert _stored(db_path, key) == "sk-live-abcdefghijkl4f2a"


def test_secret_is_never_leaked_by_an_unrelated_save(client):
    client.post("/settings", json={"gemini_api_key": "sk-gemini-secretvalue"})
    r = client.post("/settings", json={"max_render_retries": 3})
    assert r.status_code == 200
    body = json.loads(r.data)
    assert body["max_render_retries"] == 3
    assert "secretvalue" not in json.dumps(body)


def test_posting_the_mask_back_is_a_no_op(client, db_path):
    client.post("/settings", json={"gemini_api_key": "sk-gemini-realkey1234"})
    mask = json.loads(client.get("/settings").data)["gemini_api_key"]
    # This is exactly what the dashboard sends when the user edits some other
    # field: the untouched password input round-trips its displayed mask.
    r = client.post("/settings", json={"gemini_api_key": mask, "ai_review_fps": 5})
    assert r.status_code == 200
    assert json.loads(r.data)["ai_review_fps"] == 5
    assert _stored(db_path, "gemini_api_key") == "sk-gemini-realkey1234"


def test_posting_a_mask_shaped_value_when_nothing_is_stored_is_a_real_write(client, db_path):
    """The no-op only applies against a stored key. With nothing stored there is
    no mask to match, so the value is taken literally rather than silently
    dropped."""
    r = client.post("/settings", json={"openai_api_key": "••••••••4f2a"})
    assert r.status_code == 200
    assert _stored(db_path, "openai_api_key") == "••••••••4f2a"


def test_secret_can_be_cleared_with_empty_string(client, db_path):
    client.post("/settings", json={"gemini_api_key": "sk-gemini-realkey1234"})
    r = client.post("/settings", json={"gemini_api_key": ""})
    assert r.status_code == 200
    assert json.loads(r.data)["gemini_api_key"] == ""
    assert _stored(db_path, "gemini_api_key") == ""


def test_secret_is_stripped_before_storing(client, db_path):
    """A key pasted from a provider dashboard routinely carries a trailing
    newline; un-stripped it fails later as an opaque 401."""
    r = client.post("/settings", json={"gemini_api_key": "  sk-gemini-realkey1234\n"})
    assert r.status_code == 200
    assert _stored(db_path, "gemini_api_key") == "sk-gemini-realkey1234"


def test_secret_with_interior_whitespace_is_rejected(client):
    r = client.post("/settings", json={"gemini_api_key": "sk-gemini realkey"})
    assert r.status_code == 400
    assert "whitespace" in json.loads(r.data)["error"]


def test_secret_rejects_non_string(client):
    r = client.post("/settings", json={"gemini_api_key": 12345})
    assert r.status_code == 400


def test_short_secret_masks_completely(client):
    """A key shorter than the tail length must not be revealed outright."""
    client.post("/settings", json={"openai_api_key": "abc"})
    assert json.loads(client.get("/settings").data)["openai_api_key"] == "•••"


def test_pipeline_status_carries_no_secrets(client):
    """GET /pipeline/status is unauthenticated and polled by poll.py — it reads
    named keys directly rather than via _read_all_settings, and must stay that
    way."""
    client.post("/settings", json={"gemini_api_key": "sk-gemini-secretvalue"})
    body = client.get("/pipeline/status").data.decode()
    assert "secretvalue" not in body


# ── Discord notifications (TMDEV-5) ─────────────────────────────────────────

DISCORD_URL = ("https://discord.com/api/webhooks/123456789012345678/"
               "abcdefghij0123456789_KLMNOPqrstuvwxyz-ABCDE")


@pytest.fixture
def probe(monkeypatch):
    """Stub the live webhook probe and record every call.

    Autouse would be wrong — a test that forgets to stub must fail loudly
    rather than quietly hitting discord.com, which is how a suite ends up
    taking minutes and passing for the wrong reason.
    """
    class Probe(list):
        verdict = ("valid", "tubematic (channel 42)")

        def __call__(self, url, **kwargs):
            self.append(url)
            return self.verdict

    fake = Probe()
    monkeypatch.setattr(pipeline.discord_notify, "verify_webhook", fake)
    return fake


def test_notifications_are_off_by_default(client):
    """Two independent off switches: no webhook and no enabled trigger. An
    install that never opens this tab must behave as it did before."""
    data = json.loads(client.get("/settings").data)
    assert data["discord_webhook_url"] == ""
    assert data["notify_topic_proposed"] is False
    assert data["notify_script_ready"] is False
    assert data["notify_video_ready"] is False
    assert data["dashboard_base_url"] == ""


def test_the_webhook_url_is_masked_in_both_get_and_post(client, db_path, probe):
    """The URL *is* the credential — anyone holding it can post to that
    channel — so it is masked at both route boundaries like an API key."""
    r = client.post("/settings", json={"discord_webhook_url": DISCORD_URL})
    assert r.status_code == 200
    assert DISCORD_URL not in r.data.decode()
    assert DISCORD_URL not in client.get("/settings").data.decode()
    assert _stored(db_path, "discord_webhook_url") == DISCORD_URL


def test_a_malformed_webhook_url_is_rejected_before_any_probe(client, probe):
    r = client.post("/settings", json={"discord_webhook_url": "https://example.com/hook"})
    assert r.status_code == 400
    assert "discord.com/api/webhooks" in json.loads(r.data)["error"]
    assert probe == [], "shape is checked without the network"


def test_discord_rejecting_the_webhook_blocks_the_save(client, db_path, probe):
    probe.verdict = ("invalid", "Unknown Webhook")
    r = client.post("/settings", json={"discord_webhook_url": DISCORD_URL})
    assert r.status_code == 400
    assert "Unknown Webhook" in json.loads(r.data)["error"]
    assert _stored(db_path, "discord_webhook_url") is None


def test_an_unreachable_discord_still_saves(client, db_path, probe):
    """Only a positive rejection may gate a save. Refusing on a timeout would
    make Settings un-saveable whenever Discord has a bad afternoon — the same
    tri-state rule the onboarding key checks follow."""
    probe.verdict = ("unknown", "could not reach Discord: timed out")
    r = client.post("/settings", json={"discord_webhook_url": DISCORD_URL})
    assert r.status_code == 200
    assert _stored(db_path, "discord_webhook_url") == DISCORD_URL


def test_clearing_the_webhook_url_needs_no_probe(client, db_path, probe):
    client.post("/settings", json={"discord_webhook_url": DISCORD_URL})
    probe.clear()
    r = client.post("/settings", json={"discord_webhook_url": ""})
    assert r.status_code == 200
    assert _stored(db_path, "discord_webhook_url") == ""
    assert probe == []


def test_saving_another_field_does_not_reprobe_the_webhook(client, probe):
    """The dashboard round-trips the mask on every save. The existing secret
    no-op filter runs before the probe, so an unrelated save must not cost a
    request to Discord — or, worse, store the mask."""
    client.post("/settings", json={"discord_webhook_url": DISCORD_URL})
    probe.clear()
    masked = json.loads(client.get("/settings").data)["discord_webhook_url"]
    r = client.post("/settings", json={"discord_webhook_url": masked,
                                       "notify_video_ready": True})
    assert r.status_code == 200
    assert probe == []
    assert json.loads(r.data)["notify_video_ready"] is True


@pytest.mark.parametrize("key", ["notify_topic_proposed", "notify_script_ready",
                                 "notify_video_ready"])
def test_each_trigger_toggles_independently(client, key):
    r = client.post("/settings", json={key: True})
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data[key] is True
    assert all(not data[other] for other in
               ("notify_topic_proposed", "notify_script_ready", "notify_video_ready")
               if other != key)


def test_dashboard_base_url_must_name_a_scheme(client):
    r = client.post("/settings", json={"dashboard_base_url": "box:3000"})
    assert r.status_code == 400
    assert "http" in json.loads(r.data)["error"]


def test_dashboard_base_url_is_stored_without_a_trailing_slash(client, db_path):
    """So every consumer can concatenate a rooted path without producing "//"."""
    r = client.post("/settings", json={"dashboard_base_url": "http://box:3000/"})
    assert r.status_code == 200
    assert _stored(db_path, "dashboard_base_url") == "http://box:3000"


def test_dashboard_base_url_can_be_cleared(client, db_path):
    client.post("/settings", json={"dashboard_base_url": "http://box:3000"})
    r = client.post("/settings", json={"dashboard_base_url": ""})
    assert r.status_code == 200
    assert _stored(db_path, "dashboard_base_url") == ""


def test_a_corrupt_stored_webhook_url_reads_as_unset(client, db_path):
    """Anything written straight to SQLite bypasses the shape check. Falling
    back to '' turns notifications off rather than handing the worker a URL it
    would refuse to send to anyway."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO settings (key, value) VALUES ('discord_webhook_url', 'garbage')")
    con.commit()
    con.close()
    assert json.loads(client.get("/settings").data)["discord_webhook_url"] == ""


# ── User preferences (TMDEV-117) ─────────────────────────────────────────────
# Free text the operator writes once; poll.py and get_pipeline_status() hand it
# to the agent on every run.

def test_user_preferences_default_to_empty(client):
    """Empty means "no block in the prompt" — an install that never opens the
    tab must send the agent exactly what it did before."""
    assert json.loads(client.get("/settings").data)["user_preferences"] == ""


def test_user_preferences_keep_their_line_breaks_and_are_not_masked(client, db_path):
    text = "  Research: prefer Linux internals.\n\nScripts: no jokes.  \n"
    r = client.post("/settings", json={"user_preferences": text})
    assert r.status_code == 200
    expected = "Research: prefer Linux internals.\n\nScripts: no jokes."
    assert json.loads(r.data)["user_preferences"] == expected
    assert json.loads(client.get("/settings").data)["user_preferences"] == expected
    assert _stored(db_path, "user_preferences") == expected


def test_user_preferences_at_the_cap_are_accepted(client):
    r = client.post("/settings",
                    json={"user_preferences": "x" * pipeline.MAX_USER_PREFERENCES_CHARS})
    assert r.status_code == 200


def test_user_preferences_over_the_cap_are_rejected(client, db_path):
    """The whole prompt travels as one argv element, which Linux caps at
    128 KiB, so an unbounded value would fail every agent run with E2BIG."""
    r = client.post("/settings",
                    json={"user_preferences": "x" * (pipeline.MAX_USER_PREFERENCES_CHARS + 1)})
    assert r.status_code == 400
    assert str(pipeline.MAX_USER_PREFERENCES_CHARS) in json.loads(r.data)["error"]
    assert _stored(db_path, "user_preferences") is None


def test_user_preferences_with_a_nul_are_rejected(client, db_path):
    """The text ends up inside an argv element, and subprocess refuses one with
    an embedded NUL — a stored NUL would crash every scheduled agent run until
    someone cleared the setting."""
    r = client.post("/settings", json={"user_preferences": "avoid foo\u0000prefer bar"})
    assert r.status_code == 400
    assert "NUL" in json.loads(r.data)["error"]
    assert _stored(db_path, "user_preferences") is None


# ── agent_model is no longer a setting (TMDEV-90) ───────────────────────────
# The install-wide default model is now each agent's models[0].

def test_agent_model_is_no_longer_a_settings_key(client):
    assert "agent_model" not in pipeline.SETTINGS_SPEC
    assert len(pipeline.SETTINGS_SPEC) == 40
    assert "agent_model" not in json.loads(client.get("/settings").data)


def test_posting_agent_model_as_a_setting_is_an_unknown_key(client):
    r = client.post("/settings", json={"agent_model": "sonnet"})
    assert r.status_code == 400
    assert "Unknown settings" in json.loads(r.data)["error"]


def test_init_db_deletes_a_stored_agent_model_setting(tmp_path):
    """One-way: a leftover row would otherwise linger in the table forever.

    TMDEV-91: _init_db now runs migration 0001 once and is tracked in
    schema_migrations, so a bare second call is a no-op. Clearing that table
    reproduces what a real pre-migration database looks like on disk."""
    db = str(tmp_path / "retire.db")
    pipeline._init_db(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO settings (key, value) VALUES ('agent_model', 'opus')")
    con.execute("DELETE FROM schema_migrations WHERE version = 1")  # only 0001 re-runs; it is the idempotent one
    con.commit()
    con.close()
    pipeline._init_db(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT 1 FROM settings WHERE key = 'agent_model'").fetchone() is None
    con.close()


# ── Agents (TMDEV-90) ────────────────────────────────────────────────────────

def _seed_agent(db_path, aid="claude", models=("sonnet", "opus", "claude-sonnet-4-5-20250929"),
                is_default=1, weight=1, archived_at=None, created_at="2026-01-01T00:00:00Z",
                raw_models=None, effort="high"):
    """Needs the `client` fixture first — that is what runs _init_db and so
    creates the agents table on the hand-built test schema."""
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO agents (id, name, binary, run_path, install_scope, models, effort,"
        " is_default, weight, verified_at, archived_at, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, 'user', ?, ?, ?, ?, ?, ?, ?, ?)",
        (aid, aid.title(), f"/usr/local/bin/{aid}", f"/home/u/.{aid}-agent",
         raw_models if raw_models is not None else json.dumps(list(models)), effort,
         is_default, weight, created_at, archived_at, created_at, created_at))
    con.commit()
    con.close()


def _new_video(client):
    r = client.post("/videos", json={"topic": "t", "strategy": "manual", "producibility_score": 7})
    return json.loads(r.data)["id"]


def _agent_id_of(db_path, vid):
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT agent_id FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    finally:
        con.close()


def test_init_db_creates_the_agents_table_and_videos_agent_id(tmp_path):
    db = str(tmp_path / "schema.db")
    pipeline._init_db(db)
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(agents)")}
    vcols = {r[1]: r for r in con.execute("PRAGMA table_info(videos)")}
    con.close()
    assert cols == {"id", "name", "binary", "run_path", "install_scope", "models", "effort",
                    "is_default", "weight", "verified_at", "archived_at", "created_at",
                    "updated_at"}
    assert "agent_id" in vcols
    assert vcols["agent_id"][3] == 0 and vcols["agent_id"][4] is None  # nullable, no default


def test_create_video_pins_the_picked_agent(client, db_path):
    _seed_agent(db_path)
    r = client.post("/videos", json={"topic": "t", "strategy": "manual", "producibility_score": 7})
    assert r.status_code == 201
    assert json.loads(r.data)["agent_id"] == "claude"


def test_create_video_with_no_agent_installed_leaves_agent_id_null(client):
    r = client.post("/videos", json={"topic": "t", "strategy": "manual", "producibility_score": 7})
    assert r.status_code == 201
    assert json.loads(r.data)["agent_id"] is None


def test_create_video_never_pins_an_archived_agent(client, db_path):
    _seed_agent(db_path, "old", weight=100, is_default=0, archived_at="2026-01-02T00:00:00Z")
    _seed_agent(db_path, "claude")
    for _ in range(20):
        assert json.loads(client.post("/videos", json={
            "topic": "t", "strategy": "manual", "producibility_score": 7}).data)["agent_id"] == "claude"


def test_create_video_ignores_a_supplied_agent_id(client, db_path):
    _seed_agent(db_path)
    r = client.post("/videos", json={"topic": "t", "strategy": "manual",
                                     "producibility_score": 7, "agent_id": "someone-else"})
    assert json.loads(r.data)["agent_id"] == "claude"


# ── GET /agents ──

def test_get_agents_lists_every_row_including_archived(client, db_path):
    _seed_agent(db_path, "claude", created_at="2026-01-01T00:00:00Z")
    _seed_agent(db_path, "codex", is_default=0, weight=0, models=("gpt-5",),
                archived_at="2026-01-03T00:00:00Z", created_at="2026-01-02T00:00:00Z")
    r = client.get("/agents")
    assert r.status_code == 200
    rows = json.loads(r.data)
    assert [a["id"] for a in rows] == ["claude", "codex"]
    a = rows[0]
    assert set(a) == {"id", "name", "binary", "run_path", "install_scope", "models", "effort",
                      "is_default", "weight", "verified_at", "archived_at", "created_at",
                      "updated_at"}
    assert a["models"] == ["sonnet", "opus", "claude-sonnet-4-5-20250929"]
    assert a["is_default"] is True and a["weight"] == 1 and a["archived_at"] is None
    assert rows[1]["is_default"] is False and rows[1]["archived_at"] == "2026-01-03T00:00:00Z"


def test_get_agents_reads_a_corrupt_model_list_as_empty(client, db_path):
    _seed_agent(db_path, raw_models="{not json")
    assert json.loads(client.get("/agents").data)[0]["models"] == []


def test_get_agents_is_empty_with_none_installed(client):
    assert json.loads(client.get("/agents").data) == []


# ── PATCH /agents/<id> ──

def test_patch_agent_sets_the_weight(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"weight": 5})
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["weight"] == 5
    assert data["updated_at"] != "2026-01-01T00:00:00Z"


@pytest.mark.parametrize("w", [0, 100])
def test_patch_agent_weight_bounds_are_inclusive(client, db_path, w):
    _seed_agent(db_path)
    assert client.patch("/agents/claude", json={"weight": w}).status_code == 200


@pytest.mark.parametrize("w", [-1, 101, True, False, 1.5, "3", None])
def test_patch_agent_rejects_a_bad_weight(client, db_path, w):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"weight": w})
    assert r.status_code == 400
    assert "weight" in json.loads(r.data)["error"]
    assert json.loads(client.get("/agents").data)[0]["weight"] == 1


def test_patch_agent_default_flip_is_exclusive(client, db_path):
    _seed_agent(db_path, "claude", is_default=1)
    _seed_agent(db_path, "codex", is_default=0, models=("gpt-5",),
                created_at="2026-01-02T00:00:00Z")
    r = client.patch("/agents/codex", json={"is_default": True})
    assert r.status_code == 200
    assert json.loads(r.data)["is_default"] is True
    by_id = {a["id"]: a["is_default"] for a in json.loads(client.get("/agents").data)}
    assert by_id == {"claude": False, "codex": True}


def test_patch_agent_making_the_default_default_again_is_a_no_op(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"is_default": True})
    assert r.status_code == 200
    assert json.loads(r.data)["is_default"] is True


def test_patch_agent_cannot_clear_the_default(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"is_default": False})
    assert r.status_code == 400
    assert "make another agent the default instead" in json.loads(r.data)["error"]


@pytest.mark.parametrize("v", [1, "true", None])
def test_patch_agent_is_default_must_be_a_real_true(client, db_path, v):
    _seed_agent(db_path, is_default=0)
    assert client.patch("/agents/claude", json={"is_default": v}).status_code == 400
    assert json.loads(client.get("/agents").data)[0]["is_default"] is False


@pytest.mark.parametrize("key,value", [
    ("models", ["sonnet", "evil-model"]), ("binary", "/tmp/evil"), ("run_path", "/"),
    ("install_scope", "project"), ("name", "Renamed"), ("archived_at", None), ("id", "x"),
])
def test_patch_agent_rejects_installer_owned_fields(client, db_path, key, value):
    """The API rejects a model-list write — and every other field the
    installer owns. Those are validated against the real CLI on the host."""
    _seed_agent(db_path)
    before = json.loads(client.get("/agents").data)
    r = client.patch("/agents/claude", json={key: value})
    assert r.status_code == 400
    err = json.loads(r.data)["error"]
    assert key in err and "onboard.py --install-agent" in err
    assert json.loads(client.get("/agents").data) == before


def test_patch_agent_rejects_the_whole_body_if_any_key_is_disallowed(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"weight": 9, "models": ["x"]})
    assert r.status_code == 400
    assert json.loads(client.get("/agents").data)[0]["weight"] == 1


@pytest.mark.parametrize("body", [b"{}", b"[]", b"not json", b'"weight"'])
def test_patch_agent_needs_a_non_empty_json_object(client, db_path, body):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", data=body, content_type="application/json")
    assert r.status_code == 400


def test_patch_agent_unknown_is_404(client):
    assert client.patch("/agents/nope", json={"weight": 2}).status_code == 404


def test_patch_agent_archived_is_409(client, db_path):
    _seed_agent(db_path, is_default=0, archived_at="2026-01-02T00:00:00Z")
    assert client.patch("/agents/claude", json={"weight": 2}).status_code == 409
    assert client.patch("/agents/claude", json={"is_default": True}).status_code == 409
    assert json.loads(client.get("/agents").data)[0]["is_default"] is False


def test_patch_agent_on_an_archived_agent_does_not_clear_the_live_default(client, db_path):
    _seed_agent(db_path, "claude", is_default=1)
    _seed_agent(db_path, "old", is_default=0, archived_at="2026-01-02T00:00:00Z",
                created_at="2026-01-02T00:00:00Z")
    client.patch("/agents/old", json={"is_default": True})
    by_id = {a["id"]: a["is_default"] for a in json.loads(client.get("/agents").data)}
    assert by_id == {"claude": True, "old": False}


# ── default_model ──

def test_patch_agent_default_model_moves_it_to_the_front(client, db_path):
    """models[0] is the default everywhere, so picking one reorders the list."""
    _seed_agent(db_path)  # ["sonnet", "opus", "claude-sonnet-4-5-20250929"]
    r = client.patch("/agents/claude", json={"default_model": "opus"})
    assert r.status_code == 200
    assert json.loads(r.data)["models"] == ["opus", "sonnet", "claude-sonnet-4-5-20250929"]
    assert json.loads(client.get("/agents").data)[0]["models"][0] == "opus"


def test_patch_agent_default_model_already_first_is_a_no_op(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"default_model": "sonnet"})
    assert r.status_code == 200
    assert json.loads(r.data)["models"] == ["sonnet", "opus", "claude-sonnet-4-5-20250929"]


@pytest.mark.parametrize("v", ["haiku", "", "Opus"])
def test_patch_agent_default_model_must_be_an_installed_model(client, db_path, v):
    """Membership only — adding a model is the installer's job, since only it
    can check the model against the real CLI."""
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"default_model": v})
    assert r.status_code == 400
    assert "onboard.py --install-agent claude" in json.loads(r.data)["error"]
    assert json.loads(client.get("/agents").data)[0]["models"][0] == "sonnet"


@pytest.mark.parametrize("v", [None, 1, ["opus"]])
def test_patch_agent_default_model_must_be_a_string(client, db_path, v):
    _seed_agent(db_path)
    assert client.patch("/agents/claude", json={"default_model": v}).status_code == 400


def test_patch_agent_default_model_with_a_bad_key_changes_nothing(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"default_model": "opus", "models": ["opus"]})
    assert r.status_code == 400
    assert json.loads(client.get("/agents").data)[0]["models"][0] == "sonnet"


def test_patch_agent_default_model_on_an_uninstalled_agent_is_409(client, db_path):
    _seed_agent(db_path, is_default=0, archived_at="2026-01-02T00:00:00Z")
    r = client.patch("/agents/claude", json={"default_model": "opus"})
    assert r.status_code == 409
    assert "--install-agent claude" in json.loads(r.data)["error"]
    assert json.loads(client.get("/agents").data)[0]["models"][0] == "sonnet"


def test_patch_agent_default_model_unknown_agent_is_404(client):
    assert client.patch("/agents/nope", json={"default_model": "opus"}).status_code == 404


def test_patch_agent_default_model_combines_with_weight(client, db_path):
    _seed_agent(db_path)
    data = json.loads(client.patch("/agents/claude",
                                   json={"default_model": "opus", "weight": 7}).data)
    assert data["weight"] == 7 and data["models"][0] == "opus"


# ── Uninstalling is host-side only ──

def test_there_is_no_delete_agent_route(client, db_path):
    """Uninstalling is `onboard.py --uninstall-agent`, which also removes the
    files the installer deployed — nothing the API container can reach."""
    _seed_agent(db_path)
    assert client.delete("/agents/claude").status_code == 405
    assert json.loads(client.get("/agents").data)[0]["archived_at"] is None


def test_a_video_pinned_to_an_archived_agent_still_lists_it(client, db_path):
    _seed_agent(db_path)
    vid = _new_video(client)
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE agents SET archived_at = '2026-01-02T00:00:00Z', is_default = 0")
    listed = {v["id"]: v for v in json.loads(client.get("/videos").data)}
    assert listed[vid]["agent_id"] == "claude"
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_id"] == "claude"


# ── Per-video agent model (TMDEV-73; membership TMDEV-90) ───────────────────

def test_agent_model_column_defaults_to_blank(client, db_path):
    """Blank means the video's agent's own default model, its models[0]."""
    vid = _new_video(client)
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_model"] == ""


@pytest.mark.parametrize("value", ["sonnet", "claude-sonnet-4-5-20250929", ""])
def test_patch_video_accepts_a_model_the_agent_has(client, db_path, value):
    _seed_agent(db_path)
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_model": value})
    assert p.status_code == 200
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_model"] == value


@pytest.mark.parametrize("value", ["has space", "-flag"])
def test_patch_video_rejects_argv_corrupting_models(client, value):
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_model": value})
    assert p.status_code == 400
    assert "agent_model" in json.loads(p.data)["error"]


def test_patch_video_rejects_a_model_the_agent_does_not_have(client, db_path):
    """Used to be accepted: until agents carried a validated model list there
    was nothing to check against."""
    _seed_agent(db_path)
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_model": "not-released-yet"})
    assert p.status_code == 400
    err = json.loads(p.data)["error"]
    assert "'claude'" in err and "sonnet" in err and "opus" in err
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_model"] == ""


def test_patch_video_checks_the_videos_own_agent(client, db_path):
    """Membership is against the pinned agent, not the current default."""
    _seed_agent(db_path, "claude", is_default=1, weight=1)
    vid = _new_video(client)
    assert _agent_id_of(db_path, vid) == "claude"
    _seed_agent(db_path, "codex", is_default=0, models=("gpt-5",),
                created_at="2026-01-02T00:00:00Z")
    client.patch("/agents/codex", json={"is_default": True})
    assert client.patch(f"/videos/{vid}", json={"agent_model": "gpt-5"}).status_code == 400
    assert client.patch(f"/videos/{vid}", json={"agent_model": "opus"}).status_code == 200


def test_patch_video_null_agent_id_checks_the_default_agent(client, db_path):
    vid = _new_video(client)           # no agents yet: agent_id stays NULL
    assert _agent_id_of(db_path, vid) is None
    _seed_agent(db_path)
    assert client.patch(f"/videos/{vid}", json={"agent_model": "opus"}).status_code == 200
    assert client.patch(f"/videos/{vid}", json={"agent_model": "gpt-5"}).status_code == 400


def test_patch_video_rejects_a_model_when_the_agent_is_archived(client, db_path):
    _seed_agent(db_path)
    vid = _new_video(client)
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE agents SET archived_at = '2026-01-02T00:00:00Z', is_default = 0")
    p = client.patch(f"/videos/{vid}", json={"agent_model": "opus"})
    assert p.status_code == 400
    assert "uninstalled" in json.loads(p.data)["error"]
    assert client.patch(f"/videos/{vid}", json={"agent_model": ""}).status_code == 200


def test_patch_video_rejects_a_model_when_no_agent_is_installed(client):
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_model": "opus"})
    assert p.status_code == 400
    assert "python onboard.py --install-agent <agent>" in json.loads(p.data)["error"]
    assert client.patch(f"/videos/{vid}", json={"agent_model": ""}).status_code == 200


def test_patch_video_rejects_every_model_for_an_agent_with_a_corrupt_list(client, db_path):
    _seed_agent(db_path, raw_models="{not json")
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_model": "opus"})
    assert p.status_code == 400
    assert "no usable model list" in json.loads(p.data)["error"]


# ── Reassigning the agent at a human checkpoint (TMDEV-110) ─────────────────

def _two_agents(client, db_path):
    """claude (the default, dealt every card) and codex (weight 0, never
    dealt) — so a new video is always claude's and only a PATCH moves it."""
    _seed_agent(db_path)
    _seed_agent(db_path, "codex", is_default=0, weight=0, models=("gpt-5", "gpt-5-mini"),
                created_at="2026-01-02T00:00:00Z")
    return _new_video(client)


def _set_video(db_path, vid, **cols):
    con = sqlite3.connect(db_path)
    con.execute(f"UPDATE videos SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?",
                list(cols.values()) + [vid])
    con.commit()
    con.close()


def _video(client, vid):
    return json.loads(client.get(f"/videos/{vid}").data)


@pytest.mark.parametrize("status", ["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"])
def test_the_agent_can_be_changed_at_every_human_checkpoint(client, db_path, status):
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, status=status)
    r = client.patch(f"/videos/{vid}", json={"agent_id": "codex"})
    assert r.status_code == 200, r.data
    assert _agent_id_of(db_path, vid) == "codex"


@pytest.mark.parametrize("current,target", [
    ("TOPIC_PROPOSED", "TOPIC_APPROVED"),
    ("TOPIC_PROPOSED", "REVISION_REQUESTED"),
    ("SCRIPT_READY", "VOICING"),
    ("SCRIPT_READY", "REVISION_REQUESTED"),
    ("VIDEO_READY", "REVISION_REQUESTED"),
])
def test_the_agent_travels_with_the_checkpoint_action(client, db_path, current, target):
    """The dashboard sends the pick in the same PATCH that approves or revises.
    The guard reads the status *before* the UPDATE, so this must pass."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, status=current)
    r = client.patch(f"/videos/{vid}", json={
        "status": target, "onlyIfCurrentStatus": current,
        "agent_id": "codex", "agent_model": "gpt-5-mini", "agent_effort": "max",
    })
    assert r.status_code == 200, r.data
    data = json.loads(r.data)
    assert (data["status"], data["agent_id"], data["agent_model"], data["agent_effort"]) == \
        (target, "codex", "gpt-5-mini", "max")


@pytest.mark.parametrize("status", ["TOPIC_APPROVED", "VOICING", "VOICE_READY",
                                    "REVISION_REQUESTED", "VIDEO_APPROVED"])
@pytest.mark.parametrize("field,value", [("agent_id", "codex"),
                                         ("agent_model", "sonnet"),
                                         ("agent_effort", "max")])
def test_the_agent_group_is_frozen_outside_a_checkpoint(client, db_path, status, field, value):
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, status=status)
    r = client.patch(f"/videos/{vid}", json={field: value})
    assert r.status_code == 409
    err = json.loads(r.data)["error"]
    assert field in err and "human checkpoint" in err and status in err
    v = _video(client, vid)
    assert (v["agent_id"], v["agent_model"], v["agent_effort"]) == ("claude", "", "")


@pytest.mark.parametrize("value", ["", "   ", None, 5])
def test_the_agent_must_be_named(client, db_path, value):
    """There is no way to write NULL ("default at dispatch") back."""
    vid = _two_agents(client, db_path)
    r = client.patch(f"/videos/{vid}", json={"agent_id": value})
    assert r.status_code == 400
    assert "agent_id" in json.loads(r.data)["error"]
    assert _agent_id_of(db_path, vid) == "claude"


def test_an_unknown_agent_is_rejected(client, db_path):
    vid = _two_agents(client, db_path)
    r = client.patch(f"/videos/{vid}", json={"agent_id": "gemini"})
    assert r.status_code == 400
    assert "'gemini'" in json.loads(r.data)["error"]
    assert _agent_id_of(db_path, vid) == "claude"


def test_an_uninstalled_agent_is_never_offered(client, db_path):
    vid = _two_agents(client, db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE agents SET archived_at = '2026-01-03T00:00:00Z' WHERE id = 'codex'")
    con.commit()
    con.close()
    r = client.patch(f"/videos/{vid}", json={"agent_id": "codex"})
    assert r.status_code == 400
    assert "'codex'" in json.loads(r.data)["error"]
    assert _agent_id_of(db_path, vid) == "claude"


def test_echoing_the_videos_own_agent_is_a_no_op_even_when_uninstalled(client, db_path):
    """A client echoing the current value must never fail, and must not lose
    the model pinned against that agent."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, agent_model="opus")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE agents SET archived_at = '2026-01-03T00:00:00Z' WHERE id = 'claude'")
    con.commit()
    con.close()
    r = client.patch(f"/videos/{vid}", json={"agent_id": "claude"})
    assert r.status_code == 200, r.data
    assert (_agent_id_of(db_path, vid), _video(client, vid)["agent_model"]) == ("claude", "opus")


def test_changing_the_agent_clears_the_model(client, db_path):
    """opus is not in codex's list: kept, a later patch would 400 and a
    scheduled run would hand codex a foreign model every tick."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, agent_model="opus")
    assert client.patch(f"/videos/{vid}", json={"agent_id": "codex"}).status_code == 200
    assert _video(client, vid)["agent_model"] == ""


def test_pinning_the_default_agent_explicitly_keeps_the_model(client, db_path):
    """A NULL agent_id already runs under the default, so naming the default
    is not a change of agent."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, agent_id=None, agent_model="opus")
    assert client.patch(f"/videos/{vid}", json={"agent_id": "claude"}).status_code == 200
    assert (_agent_id_of(db_path, vid), _video(client, vid)["agent_model"]) == ("claude", "opus")


def test_a_model_sent_with_the_change_is_checked_against_the_new_agent(client, db_path):
    vid = _two_agents(client, db_path)
    bad = client.patch(f"/videos/{vid}", json={"agent_id": "codex", "agent_model": "opus"})
    assert bad.status_code == 400
    assert "'codex'" in json.loads(bad.data)["error"]
    assert _agent_id_of(db_path, vid) == "claude"
    ok = client.patch(f"/videos/{vid}", json={"agent_id": "codex", "agent_model": "gpt-5-mini"})
    assert ok.status_code == 200
    assert (_agent_id_of(db_path, vid), _video(client, vid)["agent_model"]) == \
        ("codex", "gpt-5-mini")


def test_the_effort_survives_an_agent_change(client, db_path):
    """Every agent takes the same five levels."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, agent_effort="max")
    assert client.patch(f"/videos/{vid}", json={"agent_id": "codex"}).status_code == 200
    assert _video(client, vid)["agent_effort"] == "max"


def test_a_model_write_racing_an_agent_change_is_refused(client, db_path, monkeypatch):
    """The model is checked against claude; if codex lands before the UPDATE,
    writing it would pin a model codex does not have."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, status="SCRIPT_READY")
    real_connect = sqlite3.connect
    state = {"wrapped": False}

    def _connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        if not state["wrapped"]:
            state["wrapped"] = True
            return _RacingConn(
                con, "SELECT agent_id FROM videos", db_path,
                "UPDATE videos SET agent_id = 'codex' WHERE id = ?", (vid,),
            )
        return con

    monkeypatch.setattr(sqlite3, "connect", _connect)
    r = client.patch(f"/videos/{vid}", json={"agent_model": "opus"})
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    assert r.status_code == 409
    assert "agent changed" in json.loads(r.data)["error"]
    assert (_agent_id_of(db_path, vid), _video(client, vid)["agent_model"]) == ("codex", "")


@pytest.mark.parametrize("seeded,moved_to,body", [
    ("SCRIPT_READY", "VOICING", {"agent_id": "codex"}),
    ("SCRIPT_READY", "VOICING", {"agent_effort": "max"}),
    ("TOPIC_PROPOSED", "TOPIC_APPROVED", {"visual_style": "stick"}),
])
def test_a_frozen_field_is_refused_if_the_video_moves_on_mid_request(client, db_path, monkeypatch,
                                                                     seeded, moved_to, body):
    """Without onlyIfCurrentStatus the freeze check and the UPDATE are two
    statements; a status change landing between them must not let the write
    through at a status where the field is frozen."""
    vid = _two_agents(client, db_path)
    _set_video(db_path, vid, status=seeded)
    real_connect = sqlite3.connect
    state = {"wrapped": False}

    def _connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        if not state["wrapped"]:
            state["wrapped"] = True
            return _RacingConn(
                con, "SELECT status, archived_at FROM videos", db_path,
                "UPDATE videos SET status = ? WHERE id = ?", (moved_to, vid),
            )
        return con

    monkeypatch.setattr(sqlite3, "connect", _connect)
    r = client.patch(f"/videos/{vid}", json=body)
    monkeypatch.setattr(sqlite3, "connect", real_connect)
    assert r.status_code == 409
    data = json.loads(r.data)
    assert (data["error"], data["current"], data["expected"]) == \
        ("Status precondition failed", moved_to, seeded)
    v = _video(client, vid)
    assert (v["agent_id"], v["agent_effort"], v["visual_style"]) == ("claude", "", "auto")


def test_an_override_leaves_the_deck_alone(client, db_path):
    """Weights are a dealing mechanism, not a quota."""
    vid = _two_agents(client, db_path)
    con = sqlite3.connect(db_path)
    before = con.execute("SELECT * FROM agent_deck").fetchall()
    con.close()
    assert client.patch(f"/videos/{vid}", json={"agent_id": "codex"}).status_code == 200
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT * FROM agent_deck").fetchall() == before
    con.close()


def test_patch_video_strips_the_model(client, db_path):
    _seed_agent(db_path)
    vid = _new_video(client)
    assert client.patch(f"/videos/{vid}", json={"agent_model": "  opus  "}).status_code == 200
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_model"] == "opus"


def _mk(client, status, agent_model="", agent_effort=""):
    r = client.post("/videos", json={
        "topic": f"t-{status}", "strategy": "manual", "producibility_score": 7})
    vid = json.loads(r.data)["id"]
    client.patch(f"/videos/{vid}", json={"status": status, "agent_model": agent_model,
                                         "agent_effort": agent_effort})
    return vid


def test_workable_videos_returns_the_workable_set(client):
    approved = _mk(client, "TOPIC_APPROVED")
    ready = _mk(client, "VOICE_READY")
    _mk(client, "TOPIC_PROPOSED")   # actionable, but not agent-workable
    _mk(client, "VIDEO_READY")      # human checkpoint

    ids = [v["id"] for v in json.loads(client.get("/videos/workable").data)]
    assert set(ids) == {approved, ready}


def test_workable_videos_carries_each_videos_model_and_agent(client, db_path):
    _seed_agent(db_path)
    _mk(client, "VOICE_READY", agent_model="opus", agent_effort="xhigh")
    rows = json.loads(client.get("/videos/workable").data)
    assert rows[0]["agent_model"] == "opus"
    assert rows[0]["agent_effort"] == "xhigh"
    assert rows[0]["agent_id"] == "claude"
    assert set(rows[0]) == {"id", "topic", "status", "agent_model", "agent_effort", "agent_id",
                            "updated_at"}


def test_workable_videos_keep_an_archived_agents_id(client, db_path):
    """Uninstalling an agent mid-flight must not blank the pin the poller reads."""
    _seed_agent(db_path)
    _mk(client, "VOICE_READY")
    with sqlite3.connect(db_path) as con:
        con.execute("UPDATE agents SET archived_at = '2026-01-02T00:00:00Z', is_default = 0")
    assert json.loads(client.get("/videos/workable").data)[0]["agent_id"] == "claude"


def test_workable_videos_is_not_the_actionable_set(client):
    """ACTIONABLE_STATUSES is the human-checkpoint set and is disjoint from
    WORKABLE_STATUSES — reusing /videos/actionable here would have sent the
    poller at videos waiting on a human."""
    assert not (set(pipeline.ACTIONABLE_STATUSES) & set(pipeline.WORKABLE_STATUSES))


def test_workable_videos_is_oldest_first(client):
    """poll.py fills its session slots in this order, so the order is
    load-bearing, not cosmetic: the oldest video is dispatched first."""
    first = _mk(client, "VOICE_READY")
    time.sleep(1.05)
    second = _mk(client, "TOPIC_APPROVED")
    ids = [v["id"] for v in json.loads(client.get("/videos/workable").data)]
    assert ids == [first, second]


# ── max_feedback_loops → max_render_retries key rename (TMDEV-74) ──────────

def _settings_rows(db_path):
    con = sqlite3.connect(db_path)
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
    return rows


def test_init_db_migrates_the_old_render_retry_key(tmp_path):
    """TMDEV-91: see test_init_db_deletes_a_stored_agent_model_setting's note —
    0001's stamp is cleared to reproduce a genuine pre-migration database.

    Only 0001's. It is the one migration written to be idempotent (pragma-
    guarded ALTERs, so it can adopt a database at any historical state);
    every later migration is plain SQL that runs exactly once, and clearing
    the whole table would re-run those against a schema they already built.
    """
    from pipeline import _init_db as pipeline_init_db
    db = str(tmp_path / "old.db")
    pipeline_init_db(db)
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('max_feedback_loops', '7')")
    con.execute("DELETE FROM schema_migrations WHERE version = 1")  # only 0001 re-runs; it is the idempotent one
    con.commit()
    con.close()

    pipeline_init_db(db)
    rows = _settings_rows(db)
    assert rows["max_render_retries"] == "7"
    assert "max_feedback_loops" not in rows

    # Idempotent — a second container start must not undo or re-copy anything.
    pipeline_init_db(db)
    assert _settings_rows(db)["max_render_retries"] == "7"


def test_init_db_does_not_clobber_a_freshly_seeded_render_retry_value(tmp_path):
    """The ordering that makes copy-if-absent load-bearing: onboarding seeds
    the settings table (step install_config) before this container is ever
    built (step renderer), so on an upgrade both rows exist and the new one is
    the answer the user just gave. An unconditional copy would discard it.

    TMDEV-91: see test_init_db_deletes_a_stored_agent_model_setting's note —
    schema_migrations is cleared to reproduce a genuine pre-migration database."""
    from pipeline import _init_db as pipeline_init_db
    db = str(tmp_path / "both.db")
    pipeline_init_db(db)
    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('max_feedback_loops', '7')")
    con.execute("INSERT OR REPLACE INTO settings VALUES ('max_render_retries', '3')")
    con.execute("DELETE FROM schema_migrations WHERE version = 1")  # only 0001 re-runs; it is the idempotent one
    con.commit()
    con.close()

    pipeline_init_db(db)
    rows = _settings_rows(db)
    assert rows["max_render_retries"] == "3"
    assert "max_feedback_loops" not in rows


def test_the_old_key_is_no_longer_accepted_by_the_settings_api(client):
    r = client.post("/settings", json={"max_feedback_loops": 4})
    assert r.status_code == 400
    assert "max_render_retries" in json.loads(client.get("/settings").data)


# ── /script-profiles (TMDEV-81) ─────────────────────────────────────────────

def _seed_profile(db_path, pid="prof-1", status="READY", name="Corpus A",
                  archived=0, attempt_count=0, markdown="# style"):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO script_profiles
           (id, name, status, markdown, corpus_summary, source_urls, archived,
            attempt_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, 'summary', '["https://youtu.be/aaaaaaaaaaa"]', ?, ?,
                   '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
        (pid, name, status, markdown, archived, attempt_count),
    )
    con.commit()
    con.close()


def _seed_transcript(db_path, pid="prof-1", youtube_id="aaaaaaaaaaa", text="spoken words"):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO script_profile_transcripts
           (profile_id, source_url, youtube_id, text, created_at)
           VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z')""",
        (pid, f"https://youtu.be/{youtube_id}", youtube_id, text),
    )
    con.commit()
    con.close()


def _transcript_count(db_path, pid):
    con = sqlite3.connect(db_path)
    n = con.execute(
        "SELECT COUNT(*) FROM script_profile_transcripts WHERE profile_id = ?", (pid,)
    ).fetchone()[0]
    con.close()
    return n


def _set_key(db_path, key="youtube_transcript_api_key", value="yt-key"):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
    con.commit()
    con.close()


def test_init_db_creates_the_script_profile_tables_and_column(tmp_path):
    from pipeline import _init_db as pipeline_init_db
    db = str(tmp_path / "profiles.db")
    pipeline_init_db(db)
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    cols = {r[1] for r in con.execute("PRAGMA table_info(videos)")}
    con.close()
    assert {"script_profiles", "script_profile_transcripts"} <= tables
    assert "script_profile_id" in cols


def test_creating_a_profile_without_a_transcript_key_reports_the_setup_gap(client):
    r = client.post("/script-profiles", json={"name": "A", "urls": ["https://youtu.be/aaaaaaaaaaa"]})
    assert r.status_code == 503
    assert "youtube-transcript.io" in json.loads(r.data)["error"]


def test_creating_a_profile_fetches_transcripts_and_parks_it_pending(client, db_path):
    _set_key(db_path)
    with mock.patch("transcripts.fetch_transcript", return_value="hello there"):
        r = client.post("/script-profiles", json={
            "name": "Corpus", "urls": ["https://youtu.be/aaaaaaaaaaa", "bbbbbbbbbbb"],
        })
    assert r.status_code == 201
    data = json.loads(r.data)
    assert data["status"] == "PENDING"
    assert data["transcripts_fetched"] == 2
    assert data["attempt_count"] == 0

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT youtube_id, text FROM script_profile_transcripts WHERE profile_id = ?",
        (data["id"],),
    ).fetchall()
    con.close()
    assert sorted(r[0] for r in rows) == ["aaaaaaaaaaa", "bbbbbbbbbbb"]
    assert rows[0][1] == "hello there"


def test_a_profile_is_not_created_when_no_transcript_could_be_fetched(client, db_path):
    _set_key(db_path)
    with mock.patch("transcripts.fetch_transcript", return_value=""):
        r = client.post("/script-profiles", json={"name": "A", "urls": ["https://youtu.be/aaaaaaaaaaa"]})
    assert r.status_code == 400
    assert json.loads(r.data)["failures"][0]["error"] == "no transcript available"
    assert json.loads(client.get("/script-profiles").data) == []


def test_an_unparseable_url_is_reported_per_url_and_does_not_sink_the_others(client, db_path):
    _set_key(db_path)
    with mock.patch("transcripts.fetch_transcript", return_value="text"):
        r = client.post("/script-profiles", json={
            "name": "A", "urls": ["not-a-youtube-url", "https://youtu.be/aaaaaaaaaaa"],
        })
    data = json.loads(r.data)
    assert r.status_code == 201
    assert data["transcripts_fetched"] == 1
    assert data["failures"][0]["url"] == "not-a-youtube-url"
    # source_urls records only what actually landed.
    assert data["source_urls"] == ["https://youtu.be/aaaaaaaaaaa"]


def test_creating_a_profile_requires_a_name_and_urls(client, db_path):
    _set_key(db_path)
    assert client.post("/script-profiles", json={"urls": ["x"]}).status_code == 400
    assert client.post("/script-profiles", json={"name": "A", "urls": []}).status_code == 400
    assert client.post("/script-profiles", json={
        "name": "A", "urls": ["u"] * (pipeline.MAX_PROFILE_URLS + 1)}).status_code == 400


def test_the_list_omits_markdown_and_archived_rows(client, db_path):
    _seed_profile(db_path, "prof-1")
    _seed_profile(db_path, "prof-2", archived=1)
    data = json.loads(client.get("/script-profiles").data)
    assert [p["id"] for p in data] == ["prof-1"]
    assert "markdown" not in data[0]
    assert data[0]["archived"] is False


def test_fetching_one_profile_returns_its_markdown(client, db_path):
    _seed_profile(db_path, "prof-1", markdown="# voice and tone")
    data = json.loads(client.get("/script-profiles/prof-1").data)
    assert data["markdown"] == "# voice and tone"
    assert data["corpus_summary"] == "summary"
    assert client.get("/script-profiles/nope").status_code == 404


def test_delete_archives_the_row_so_references_still_resolve(client, db_path):
    _seed_profile(db_path, "prof-1")
    assert client.delete("/script-profiles/prof-1").status_code == 200
    assert json.loads(client.get("/script-profiles").data) == []
    # Still fetchable by id — a video that picked it keeps a resolvable value,
    # and the flag lets the dashboard label it as deleted rather than showing a
    # name that can no longer be picked.
    fetched = client.get("/script-profiles/prof-1")
    assert fetched.status_code == 200
    assert json.loads(fetched.data)["archived"] is True
    assert client.delete("/script-profiles/nope").status_code == 404


@pytest.mark.parametrize("status", ["PENDING", "GENERATING", "FAILED"])
def test_archiving_an_unbuilt_profile_drops_its_transcripts(client, db_path, status):
    """complete_script_profile is the only other place transcripts are dropped,
    so a profile archived before it got there would strand them forever: both
    list endpoints exclude archived rows, and the ON DELETE CASCADE cannot fire
    because the profile row itself is never deleted."""
    _seed_profile(db_path, "prof-1", status=status)
    _seed_transcript(db_path, "prof-1")
    assert _transcript_count(db_path, "prof-1") == 1

    assert client.delete("/script-profiles/prof-1").status_code == 200
    assert _transcript_count(db_path, "prof-1") == 0
    # The profile row itself survives, so a video that picked it still resolves.
    assert client.get("/script-profiles/prof-1").status_code == 200


def test_archiving_a_ready_profile_keeps_its_markdown(client, db_path):
    """The transcript delete is unconditional; on a READY profile it is a no-op
    (they were already dropped at completion) and must not touch the style."""
    _seed_profile(db_path, "prof-1", status="READY", markdown="# style")
    assert client.delete("/script-profiles/prof-1").status_code == 200
    assert json.loads(client.get("/script-profiles/prof-1").data)["markdown"] == "# style"


def test_a_failed_delete_leaves_transcripts_alone(client, db_path):
    """The 404 must return before the delete, not after it."""
    _seed_profile(db_path, "prof-1", status="PENDING")
    _seed_transcript(db_path, "prof-1")
    assert client.delete("/script-profiles/nope").status_code == 404
    assert _transcript_count(db_path, "prof-1") == 1


def test_pending_includes_generating_so_a_crashed_attempt_retries(client, db_path):
    _seed_profile(db_path, "p-pending", status="PENDING")
    _seed_profile(db_path, "p-generating", status="GENERATING")
    _seed_profile(db_path, "p-ready", status="READY")
    _seed_profile(db_path, "p-failed", status="FAILED")
    _seed_profile(db_path, "p-archived", status="PENDING", archived=1)
    ids = {p["id"] for p in json.loads(client.get("/script-profiles/pending").data)}
    assert ids == {"p-pending", "p-generating"}


def test_record_attempt_caps_at_two_agent_sessions_then_fails_the_row(client, db_path):
    """The cap gates before incrementing, so MAX_PROFILE_ATTEMPTS is the number
    of agent sessions that actually run. Incrementing first and comparing after
    would allow one more than the constant says."""
    _seed_profile(db_path, "prof-1", status="PENDING")
    seen = []
    for _ in range(3):
        data = json.loads(client.post("/script-profiles/prof-1/record-attempt").data)
        seen.append((data["status"], data["attempt_count"]))
    assert seen == [("GENERATING", 1), ("GENERATING", 2), ("FAILED", 2)]

    row = json.loads(client.get("/script-profiles/prof-1").data)
    assert row["status"] == "FAILED"
    assert row["error"]


def test_record_attempt_refuses_a_settled_profile(client, db_path):
    _seed_profile(db_path, "p-ready", status="READY")
    _seed_profile(db_path, "p-failed", status="FAILED")
    assert client.post("/script-profiles/p-ready/record-attempt").status_code == 409
    assert client.post("/script-profiles/p-failed/record-attempt").status_code == 409
    assert client.post("/script-profiles/nope/record-attempt").status_code == 404


def test_pipeline_status_counts_pending_profiles(client, db_path):
    assert json.loads(client.get("/pipeline/status").data)["pending_script_profiles"] == 0
    _seed_profile(db_path, "p1", status="PENDING")
    _seed_profile(db_path, "p2", status="GENERATING")
    _seed_profile(db_path, "p3", status="READY")
    assert json.loads(client.get("/pipeline/status").data)["pending_script_profiles"] == 2


def test_patch_video_accepts_a_ready_profile(client, db_path):
    _seed_video(db_path)
    _seed_profile(db_path, "prof-1", status="READY")
    r = client.patch("/videos/vid-1", json={"script_profile_id": "prof-1"})
    assert r.status_code == 200
    assert json.loads(r.data)["script_profile_id"] == "prof-1"


def test_patch_video_rejects_a_profile_that_is_not_ready(client, db_path):
    _seed_video(db_path)
    _seed_profile(db_path, "p-pending", status="PENDING")
    _seed_profile(db_path, "p-archived", status="READY", archived=1)
    for pid in ("p-pending", "p-archived", "does-not-exist"):
        r = client.patch("/videos/vid-1", json={"script_profile_id": pid})
        assert r.status_code == 400, pid


def test_patch_video_can_clear_the_profile(client, db_path):
    _seed_video(db_path)
    _seed_profile(db_path, "prof-1", status="READY")
    client.patch("/videos/vid-1", json={"script_profile_id": "prof-1"})
    r = client.patch("/videos/vid-1", json={"script_profile_id": ""})
    assert r.status_code == 200
    assert json.loads(r.data)["script_profile_id"] == ""


# ── Per-video choices are frozen after the topic checkpoint ─────────────────

def test_profile_and_model_can_be_set_in_the_approving_patch(client, db_path):
    """The picker's own request carries the choices *and* the status change.
    It must pass: the guard reads the current status, which is still
    TOPIC_PROPOSED at that point."""
    _seed_video(db_path, "TOPIC_PROPOSED")
    _seed_profile(db_path, "prof-1", status="READY")
    _seed_agent(db_path)
    r = client.patch("/videos/vid-1", json={
        "status": "TOPIC_APPROVED", "onlyIfCurrentStatus": "TOPIC_PROPOSED",
        "script_profile_id": "prof-1", "agent_model": "opus", "agent_effort": "max",
    })
    assert r.status_code == 200
    data = json.loads(r.data)
    assert (data["status"], data["script_profile_id"], data["agent_model"],
            data["agent_effort"]) == ("TOPIC_APPROVED", "prof-1", "opus", "max")


@pytest.mark.parametrize("status", ["TOPIC_APPROVED", "SCRIPT_READY", "VOICE_READY",
                                    "VIDEO_READY", "REVISION_REQUESTED"])
@pytest.mark.parametrize("field,value", [("script_profile_id", "prof-1"),
                                         ("visual_style", "stick")])
def test_the_topic_choices_cannot_be_changed_after_the_topic_checkpoint(client, db_path, status,
                                                                        field, value):
    _seed_video(db_path, status)
    _seed_profile(db_path, "prof-1", status="READY")
    r = client.patch("/videos/vid-1", json={field: value})
    assert r.status_code == 409
    assert "TOPIC_PROPOSED" in json.loads(r.data)["error"]


def test_a_topic_choice_still_fails_when_sent_alongside_an_agent_pick(client, db_path):
    """SCRIPT_READY accepts the agent group but not the topic group — a
    request carrying both is refused whole, not half-applied."""
    _seed_video(db_path, "SCRIPT_READY")
    _seed_agent(db_path)
    r = client.patch("/videos/vid-1", json={"visual_style": "stick", "agent_effort": "max"})
    assert r.status_code == 409
    assert "TOPIC_PROPOSED" in json.loads(r.data)["error"]
    assert json.loads(client.get("/videos/vid-1").data)["agent_effort"] == ""


def test_the_lock_does_not_block_other_fields_later(client, db_path):
    """Only these two are frozen — the rest of the pipeline still writes freely."""
    _seed_video(db_path, "VOICE_READY")
    assert client.patch("/videos/vid-1", json={"gemini_feedback": "looks fine"}).status_code == 200


# ── TMDEV-83: publishing schema ──────────────────────────────────────────────

def test_init_db_creates_the_publishing_tables(tmp_path):
    from pipeline import _init_db as pipeline_init_db
    db = str(tmp_path / "publishing.db")
    pipeline_init_db(db)
    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    pub_cols = {r[1] for r in con.execute("PRAGMA table_info(video_publications)")}
    met_cols = {r[1] for r in con.execute("PRAGMA table_info(video_metrics)")}
    con.close()
    assert {"video_publications", "video_metrics"} <= tables
    assert pub_cols == {
        "id", "video_id", "platform", "social_account_id", "postforme_post_id",
        "status", "post_url", "error", "published_at", "created_at", "updated_at",
    }
    assert met_cols == {
        "id", "publication_id", "fetched_at", "views", "likes", "comments",
        "shares", "raw_json",
    }


def test_deleting_a_publication_takes_its_metric_snapshots_with_it(tmp_path):
    """video_metrics is a time series hanging off one publication; orphan rows
    would silently inflate every aggregate on the analytics page."""
    from pipeline import _init_db as pipeline_init_db
    db = str(tmp_path / "cascade.db")
    pipeline_init_db(db)
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('p', 'P', 'now')")
    con.execute(
        "INSERT INTO videos (id, project_id, topic, strategy, status, created_at, updated_at)"
        " VALUES ('v', 'p', 'T', 'manual', 'PUBLISHED', 'now', 'now')")
    con.execute(
        "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
        " postforme_post_id, status, created_at, updated_at)"
        " VALUES ('pub', 'v', 'youtube', 'spc_1', 'sp_1', 'PENDING', 'now', 'now')")
    con.execute(
        "INSERT INTO video_metrics (publication_id, fetched_at, views) VALUES ('pub', 'now', 5)")
    con.execute("DELETE FROM video_publications WHERE id = 'pub'")
    remaining = con.execute("SELECT COUNT(*) FROM video_metrics").fetchone()[0]
    con.close()
    assert remaining == 0


def test_no_process_declares_its_own_schema():
    """There was one schema definition per process, kept in sync by comment, and
    a cross-copy test that compared only the tables it had been taught about. It
    missed three statements: pipeline.py had the max_feedback_loops and
    agent_model settings fixups, mcp/server.py had the SCRIPTING recovery.

    The definition now lives in tubematic_core/migrations/. This test is the
    inverse of the old one: rather than checking that the copies agree, it checks
    that there are no copies."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    for rel in ("mcp/server.py", "renderer/api/pipeline.py",
                "onboard/actions.py", "scripts/clear_db.py"):
        src = (root / rel).read_text()
        assert "CREATE TABLE IF NOT EXISTS" not in src, (
            f"{rel} declares schema. Schema belongs in tubematic_core/migrations/")

    migrations = root / "tubematic_core" / "migrations"
    baseline = (migrations / "0001_baseline.py").read_text()
    for table in ("projects", "videos", "agents", "agent_deck", "comments",
                  "settings", "script_profiles", "script_profile_transcripts",
                  "video_publications", "video_metrics"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in baseline, (
            f"the baseline migration is missing {table}")


# ── TMDEV-83: publishing routes ──────────────────────────────────────────────

PFM_ACCOUNTS = [
    {"id": "spc_yt", "platform": "youtube", "username": "Chan",
     "profile_photo_url": "https://p/1", "status": "connected",
     "access_token": "<redacted>", "refresh_token": "<redacted>", "user_id": "UC1"},
    {"id": "spc_ig", "platform": "instagram", "username": "chan_",
     "profile_photo_url": "https://p/2", "status": "connected",
     "access_token": "<redacted>", "refresh_token": "<redacted>", "user_id": "17841"},
]


def _enable_publishing(db_path, key="pfm-key"):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('publishing_enabled', 'true')")
    con.execute("INSERT OR REPLACE INTO settings VALUES ('postforme_api_key', ?)", (key,))
    con.commit()
    con.close()


def _allow(db_path, ids):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('publishing_accounts', ?)",
                (json.dumps(ids),))
    con.commit()
    con.close()


def _approved_video(db_path, vid="vid_pub", status="VIDEO_APPROVED"):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute(
        "INSERT INTO videos (id, project_id, topic, title, strategy, status, video_path,"
        " created_at, updated_at) VALUES (?,'p','A topic','A Title','manual',?,?,'now','now')",
        (vid, status, f"/output_videos/p/{vid}.mp4"))
    con.commit()
    con.close()
    return vid


@pytest.fixture
def rendered(tmp_path, monkeypatch):
    """Point OUTPUT_DIR at a temp tree and drop a stand-in mp4 in it.

    videos.video_path holds a *container* path; _output_path rebases onto
    OUTPUT_DIR so this resolves without the test having to fake /output_videos.
    """
    out = tmp_path / "out"
    (out / "p").mkdir(parents=True)
    (out / "p" / "vid_pub.mp4").write_bytes(b"\x00mp4")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)
    return out


# ── accounts ──

def test_accounts_is_unavailable_while_publishing_is_off(client):
    r = client.get("/publishing/accounts")
    assert r.status_code == 503
    assert "publishing" in json.loads(r.data)["error"].lower()


def test_accounts_is_unavailable_without_a_key(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('publishing_enabled', 'true')")
    con.commit()
    con.close()
    r = client.get("/publishing/accounts")
    assert r.status_code == 503
    assert "postforme" in json.loads(r.data)["error"].lower()


def test_accounts_never_returns_oauth_credentials(client, db_path):
    """The single most important assertion in this file.

    postforme hands back the connected channel's live access_token and a
    refresh_token with no expiry. This payload crosses the Next proxy into a
    browser, so an allowlist projection is the only acceptable shape — a
    blocklist would leak the next credential field postforme adds.
    """
    _enable_publishing(db_path)
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS):
        r = client.get("/publishing/accounts")
    assert r.status_code == 200
    body = json.dumps(json.loads(r.data))
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "user_id" not in body


def test_accounts_marks_which_ones_tubematic_may_post_to(client, db_path):
    """The stored list is an allowlist, not a mirror: postforme may hold
    personal accounts that should never receive pipeline output."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS):
        accounts = json.loads(client.get("/publishing/accounts").data)
    by_id = {a["id"]: a for a in accounts}
    assert by_id["spc_yt"]["allowed"] is True
    assert by_id["spc_ig"]["allowed"] is False
    assert by_id["spc_yt"]["available"] is True


def test_an_allowlisted_account_removed_upstream_shows_as_unavailable(client, db_path):
    """Reconciliation, not a silent drop — otherwise the first sign of a
    disconnected account is a failed publish."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt", "spc_gone"])
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS):
        accounts = json.loads(client.get("/publishing/accounts").data)
    gone = next(a for a in accounts if a["id"] == "spc_gone")
    assert gone["available"] is False
    assert gone["allowed"] is True


def test_saving_the_allowlist_stores_ids_only(client, db_path):
    """Display data is hydrated live on every load, so storing a username
    would just be a second copy going stale."""
    _enable_publishing(db_path)
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS):
        r = client.post("/publishing/accounts", json={"account_ids": ["spc_ig"]})
    assert r.status_code == 200
    assert json.loads(_stored(db_path, "publishing_accounts")) == ["spc_ig"]


def test_saving_a_non_list_allowlist_is_rejected(client, db_path):
    _enable_publishing(db_path)
    r = client.post("/publishing/accounts", json={"account_ids": "spc_ig"})
    assert r.status_code == 400


def test_a_postforme_outage_is_a_502_not_a_500(client, db_path):
    _enable_publishing(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", side_effect=pfm.PostformeError("upstream down")):
        r = client.get("/publishing/accounts")
    assert r.status_code == 502
    assert "upstream down" in json.loads(r.data)["error"]


# ── connect ──

AUTH_URL = {"platform": "youtube",
            "url": "https://accounts.google.com/o/oauth2/v2/auth?state=single-use-state"
                   "&scope=youtube.upload%20yt-analytics.readonly"}


def test_connect_is_unavailable_while_publishing_is_off(client):
    with mock.patch("postforme.create_auth_url") as mint:
        r = client.post("/publishing/accounts/connect", json={"platform": "youtube"})
    assert r.status_code == 503
    mint.assert_not_called()


def test_connect_is_unavailable_without_a_key(client, db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings VALUES ('publishing_enabled', 'true')")
    con.commit()
    con.close()
    with mock.patch("postforme.create_auth_url") as mint:
        r = client.post("/publishing/accounts/connect", json={"platform": "youtube"})
    assert r.status_code == 503
    mint.assert_not_called()


@pytest.mark.parametrize("body", [{}, {"platform": ""}, {"platform": "myspace"},
                                  {"platform": ["youtube"]}, {"platform": "YouTube"}])
def test_connect_refuses_an_unknown_platform_before_calling_postforme(client, db_path, body):
    """postforme needs a platform (probed: omitted is now a 500 there), and a
    typo would spend a request to learn what we already know."""
    _enable_publishing(db_path)
    with mock.patch("postforme.create_auth_url") as mint:
        r = client.post("/publishing/accounts/connect", json=body)
    assert r.status_code == 400
    mint.assert_not_called()


def test_connect_always_asks_for_feeds_whatever_the_body_says(client, db_path):
    """The point of minting the URL here: postforme's own default is posts
    alone, which publishes fine and silently never yields a metric."""
    _enable_publishing(db_path, key="pfm-secret")
    with mock.patch("postforme.create_auth_url", return_value=AUTH_URL) as mint:
        r = client.post("/publishing/accounts/connect",
                        json={"platform": "youtube", "permissions": ["posts"]})
    assert r.status_code == 200
    assert json.loads(r.data) == {"platform": "youtube", "url": AUTH_URL["url"]}
    args, kwargs = mint.call_args
    assert args == ("pfm-secret",)
    assert kwargs["platform"] == "youtube"
    assert list(kwargs["permissions"]) == ["posts", "feeds"]


def test_a_disabled_platform_answers_with_postformes_message(client, db_path):
    """Probed: facebook is not enabled on the project, and postforme says how to
    fix that. A bare "failed" would hide the one actionable sentence."""
    _enable_publishing(db_path)
    import postforme as pfm
    msg = ("postforme returned HTTP 404: Social provider app credentials not found for "
           "facebook. Please set up or enable this platform in Project Setup.")
    with mock.patch("postforme.create_auth_url", side_effect=pfm.PostformeError(msg, 404)):
        r = client.post("/publishing/accounts/connect", json={"platform": "facebook"})
    assert r.status_code == 502
    assert json.loads(r.data)["error"] == msg


@pytest.mark.parametrize("minted", [{}, {"url": ""}, {"url": "javascript:alert(1)"}])
def test_a_reply_without_a_usable_url_is_a_502(client, db_path, minted):
    """The browser navigates a tab to whatever comes back, so only an https URL
    is handed on."""
    _enable_publishing(db_path)
    with mock.patch("postforme.create_auth_url", return_value=minted):
        r = client.post("/publishing/accounts/connect", json={"platform": "youtube"})
    assert r.status_code == 502


def test_the_minted_url_and_the_key_never_reach_a_log(client, db_path, caplog):
    """The URL carries a single-use `state` token: it goes to the browser and
    nowhere else."""
    _enable_publishing(db_path, key="pfm-secret")
    caplog.set_level("DEBUG")
    with mock.patch("postforme.create_auth_url", return_value=AUTH_URL):
        client.post("/publishing/accounts/connect", json={"platform": "youtube"})
    assert "single-use-state" not in caplog.text
    assert "pfm-secret" not in caplog.text


# ── publish ──

def test_publishing_requires_the_video_to_be_approved(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path, status="VIDEO_READY")
    r = client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 409


def test_publishing_rejects_an_account_outside_the_allowlist(client, db_path, rendered):
    """The allowlist is a real gate, not a UI convenience — this endpoint is
    reachable directly through the proxy."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    r = client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_ig"], "title": "T", "description": "D"})
    assert r.status_code == 400
    assert "spc_ig" in json.loads(r.data)["error"]


def _publish_ok(client, db_path, vid, accounts=("spc_yt",)):
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", return_value={"id": "sp_1", "status": "scheduled"}):
        return client.post(f"/videos/{vid}/publish",
                           json={"account_ids": list(accounts), "title": "T", "description": "D"})


def test_a_successful_publish_creates_a_row_per_target_and_moves_to_publishing(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt", "spc_ig"])
    vid = _approved_video(db_path)
    r = _publish_ok(client, db_path, vid, ("spc_yt", "spc_ig"))
    assert r.status_code == 201

    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT platform, social_account_id, postforme_post_id, status"
        " FROM video_publications WHERE video_id = ? ORDER BY platform", (vid,)).fetchall()
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    assert rows == [("instagram", "spc_ig", "sp_1", "PENDING"),
                    ("youtube", "spc_yt", "sp_1", "PENDING")]
    assert status == "PUBLISHING"


def test_publishing_twice_is_stopped_by_the_status_guard(client, db_path, rendered):
    """One guard, not two that can disagree: the first call has already left
    VIDEO_APPROVED, so the second cannot match."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    assert _publish_ok(client, db_path, vid).status_code == 201
    assert _publish_ok(client, db_path, vid).status_code == 409

    con = sqlite3.connect(db_path)
    count = con.execute(
        "SELECT COUNT(*) FROM video_publications WHERE video_id = ?", (vid,)).fetchone()[0]
    con.close()
    assert count == 1


def test_a_failed_publish_leaves_the_video_approved_and_writes_no_rows(client, db_path, rendered):
    """Half-publishing is worse than not publishing: the human must be able to
    hit the button again."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    side_effect=pfm.PostformeError("upload url refused")):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502

    con = sqlite3.connect(db_path)
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    rows = con.execute("SELECT COUNT(*) FROM video_publications").fetchone()[0]
    con.close()
    assert status == "VIDEO_APPROVED"
    assert rows == 0


def test_publishing_sends_the_ai_disclosure_and_the_right_per_platform_content(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt", "spc_ig"])
    vid = _approved_video(db_path)
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post",
                    return_value={"id": "sp_1"}) as create:
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt", "spc_ig"],
                          "title": "My Title", "description": "The body."})
    cfg = create.call_args.kwargs["platform_configurations"]
    assert cfg["youtube"]["title"] == "My Title"
    assert cfg["youtube"]["contains_synthetic_media"] is True
    assert cfg["instagram"]["caption"] == "My Title\n\nThe body."
    assert create.call_args.kwargs["external_id"] == vid


def test_publishing_is_unavailable_while_the_setting_is_off(client, db_path):
    vid = _approved_video(db_path)
    r = client.post(f"/videos/{vid}/publish", json={"account_ids": ["spc_yt"]})
    assert r.status_code == 503


def test_publishing_needs_a_rendered_file(client, db_path):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute("INSERT INTO videos (id, project_id, topic, strategy, status, created_at,"
                " updated_at) VALUES ('vid_nofile','p','T','manual','VIDEO_APPROVED','n','n')")
    con.commit()
    con.close()
    r = client.post("/videos/vid_nofile/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 400


# ── publications ──

def test_publications_are_listed_for_a_video(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    _publish_ok(client, db_path, vid)
    rows = json.loads(client.get(f"/videos/{vid}/publications").data)
    assert [r["platform"] for r in rows] == ["youtube"]
    assert rows[0]["status"] == "PENDING"


# ── prefill ──

def _set_publish_metadata(db_path, vid, title, description):
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET publish_title = ?, publish_description = ? WHERE id = ?",
                (title, description, vid))
    con.commit()
    con.close()


def _stored_publish_metadata(db_path, vid):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT publish_title, publish_description FROM videos WHERE id = ?",
                      (vid,)).fetchone()
    con.close()
    return row


def test_prefill_returns_what_the_agent_wrote_with_the_script(client, db_path):
    """TMDEV-132: the agent writes these alongside the script, so the dialog
    only reads them back."""
    _enable_publishing(db_path)
    vid = _approved_video(db_path)
    _set_publish_metadata(db_path, vid, "Agent Title", "Agent body.")
    body = json.loads(client.post(f"/videos/{vid}/publish-prefill").data)
    assert (body["title"], body["description"]) == ("Agent Title", "Agent body.")


def test_prefill_falls_back_to_the_title_and_topic_when_nothing_was_written(client, db_path):
    """A video scripted before the agent wrote these. The dialog must still
    open on something the human can edit — a publish blocked on a missing
    suggestion would be an absurd way to lose a finished video."""
    _enable_publishing(db_path)
    vid = _approved_video(db_path)
    r = client.post(f"/videos/{vid}/publish-prefill")
    assert r.status_code == 200
    body = json.loads(r.data)
    assert (body["title"], body["description"]) == ("A Title", "A topic")


def test_prefill_never_stores_its_fallback(client, db_path):
    """Storing it would make the fallback indistinguishable from what an
    agent wrote."""
    _enable_publishing(db_path)
    vid = _approved_video(db_path)
    client.post(f"/videos/{vid}/publish-prefill")
    assert _stored_publish_metadata(db_path, vid) == ("", "")


def test_prefill_calls_no_model(client, db_path):
    """The point of TMDEV-132: opening the dialog costs nothing and waits on
    nobody, even with a Gemini key stored."""
    _enable_publishing(db_path)
    _set_key(db_path, "gemini_api_key", "g-key")
    vid = _approved_video(db_path)
    with mock.patch("httpx.Client") as cls, mock.patch("httpx.post") as post:
        r = client.post(f"/videos/{vid}/publish-prefill")
    assert r.status_code == 200
    cls.assert_not_called()
    post.assert_not_called()
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 0
    con.close()


# ── TMDEV-132: the HTTP script write carries the publish pair too ──

PUBLISH = {"publish_title": "Agent Title", "publish_description": "Agent body."}


def test_patch_refuses_a_script_without_the_publish_pair(client, db_path):
    """One rule on both script write paths: the dialog only reads the pair, so
    a script written here without it would open on the bare topic, and a
    rewritten one would keep a pair that describes the old script."""
    vid = _approved_video(db_path)
    for body in ({"script": "New words."},
                 {"script": "New words.", "publish_title": "T"},
                 {"script": "New words.", "publish_description": "D"}):
        r = client.patch(f"/videos/{vid}", json=body)
        assert r.status_code == 400, body
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT script FROM videos WHERE id = ?", (vid,)).fetchone()[0] in ("", None)
    con.close()


def test_patch_stores_a_script_with_its_publish_pair_trimmed(client, db_path):
    vid = _approved_video(db_path)
    r = client.patch(f"/videos/{vid}", json={"script": "New words.",
                                              "publish_title": "  Agent Title ",
                                              "publish_description": "Agent body.\n"})
    assert r.status_code == 200
    assert _stored_publish_metadata(db_path, vid) == ("Agent Title", "Agent body.")


@pytest.mark.parametrize("field,value", [
    ("publish_title", ""), ("publish_title", "   "), ("publish_title", 7),
    ("publish_title", "t" * 101),
    ("publish_description", ""), ("publish_description", None),
    ("publish_description", "d" * 2001),
])
def test_patch_refuses_a_bad_publish_value(client, db_path, field, value):
    vid = _approved_video(db_path)
    r = client.patch(f"/videos/{vid}", json={**PUBLISH, field: value})
    assert r.status_code == 400
    assert field in r.get_json()["error"]
    assert _stored_publish_metadata(db_path, vid) == ("", "")


def test_patch_takes_the_publish_pair_without_a_script(client, db_path):
    vid = _approved_video(db_path)
    assert client.patch(f"/videos/{vid}", json=PUBLISH).status_code == 200
    assert _stored_publish_metadata(db_path, vid) == ("Agent Title", "Agent body.")


# ── TMDEV-83: analytics ──────────────────────────────────────────────────────

def _published_with_metrics(db_path, vid, platform, account, series):
    """A PUBLISHED video with one publication and a metrics time series."""
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR IGNORE INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.execute(
        "INSERT INTO videos (id, project_id, topic, title, strategy, status, created_at,"
        " updated_at) VALUES (?,'p','T',?, 'manual','PUBLISHED','now','now')",
        (vid, f"Title {vid}"))
    pub_id = f"pub-{vid}"
    con.execute(
        "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
        " postforme_post_id, status, post_url, published_at, created_at, updated_at)"
        " VALUES (?,?,?,?, 'sp_1', 'PUBLISHED', ?, 'now', 'now', 'now')",
        (pub_id, vid, platform, account, f"https://{platform}/{vid}"))
    for fetched_at, views in series:
        con.execute(
            "INSERT INTO video_metrics (publication_id, fetched_at, views, likes, comments,"
            " shares, raw_json) VALUES (?, ?, ?, 1, 2, 3, '{}')", (pub_id, fetched_at, views))
    con.commit()
    con.close()
    return pub_id


def test_analytics_reports_the_latest_snapshot_per_publication(client, db_path):
    """Not the sum of the series — each row is a cumulative reading, so adding
    two snapshots of the same post would double-count it."""
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt",
                            [("2026-01-01T00:00:00Z", 10), ("2026-02-01T00:00:00Z", 90)])
    data = json.loads(client.get("/analytics").data)
    assert data["totals"]["views"] == 90
    assert data["publications"][0]["views"] == 90


def test_analytics_aggregates_views_across_platforms(client, db_path):
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [("t", 100)])
    _published_with_metrics(db_path, "vid_b", "instagram", "spc_ig", [("t", 5)])
    data = json.loads(client.get("/analytics").data)
    assert data["totals"]["views"] == 105
    assert data["by_platform"]["youtube"]["views"] == 100
    assert data["by_platform"]["instagram"]["views"] == 5


def test_analytics_can_be_filtered_by_platform_and_account(client, db_path):
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [("t", 100)])
    _published_with_metrics(db_path, "vid_b", "instagram", "spc_ig", [("t", 5)])
    only_yt = json.loads(client.get("/analytics?platform=youtube").data)
    assert [p["video_id"] for p in only_yt["publications"]] == ["vid_a"]
    assert only_yt["totals"]["views"] == 100
    by_account = json.loads(client.get("/analytics?social_account_id=spc_ig").data)
    assert [p["video_id"] for p in by_account["publications"]] == ["vid_b"]


def test_a_publication_with_no_metrics_yet_still_appears(client, db_path):
    """Absent metrics are not zero — a post published minutes ago has simply
    not been polled, and hiding it would look like a failed publish."""
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [])
    data = json.loads(client.get("/analytics").data)
    assert len(data["publications"]) == 1
    assert data["publications"][0]["views"] is None
    assert data["totals"]["views"] == 0


def test_analytics_carries_the_video_title_so_the_page_needs_one_call(client, db_path):
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [("t", 3)])
    data = json.loads(client.get("/analytics").data)
    assert data["publications"][0]["title"] == "Title vid_a"
    assert data["publications"][0]["post_url"] == "https://youtube/vid_a"


def test_a_failed_publication_is_excluded_from_analytics(client, db_path):
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [("t", 3)])
    con = sqlite3.connect(db_path)
    con.execute("UPDATE video_publications SET status = 'FAILED'")
    con.commit()
    con.close()
    data = json.loads(client.get("/analytics").data)
    assert data["publications"] == []


# ── TMDEV-113: views gained per month ────────────────────────────────────────
# Months are the host's, like the Spend tab's days, and each snapshot is a
# cumulative reading — so a month's figure is a difference, never a sum.

def _ny_month(back):
    """("YYYY-MM", a mid-month UTC timestamp) for the New York month `back`
    months before the current one."""
    import zoneinfo
    today = datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
    y, m = today.year, today.month - back
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}", f"{y:04d}-{m:02d}-15T12:00:00Z"


def _by_month(client, query=""):
    body = client.get(f"/analytics{query}").get_json()
    return [(m["month"], m["views"]) for m in body["by_month"]]


@pytest.fixture
def new_york(monkeypatch):
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "America/New_York")


def test_by_month_is_the_views_gained_in_each_month(client, db_path, new_york):
    (m2, t2), (m1, t1), (m0, t0) = _ny_month(2), _ny_month(1), _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt",
                            [(t2, 100), (t1, 250), (t0, 300)])
    assert _by_month(client) == [(m2, 100), (m1, 150), (m0, 50)]
    assert client.get("/analytics").get_json()["timezone"] == "America/New_York"


def test_by_month_sums_every_post(client, db_path, new_york):
    (m1, t1), (m0, t0) = _ny_month(1), _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [(t1, 10), (t0, 30)])
    _published_with_metrics(db_path, "vid_b", "instagram", "spc_ig", [(t0, 5)])
    assert _by_month(client) == [(m1, 10), (m0, 25)]


def test_by_month_cuts_months_in_the_host_timezone(client, db_path, new_york):
    """02:00Z on the 1st is still the last evening of the month before in New
    York, so the reading taken then closes that month, not this one."""
    (m1, t1), (m0, t0) = _ny_month(1), _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt",
                            [(t1, 10), (f"{m0}-01T02:00:00Z", 40), (t0, 50)])
    assert _by_month(client) == [(m1, 40), (m0, 10)]


def test_by_month_follows_the_platform_and_account_filters(client, db_path, new_york):
    m0, t0 = _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [(t0, 100)])
    _published_with_metrics(db_path, "vid_b", "instagram", "spc_ig", [(t0, 5)])
    assert _by_month(client, "?platform=youtube") == [(m0, 100)]
    assert _by_month(client, "?social_account_id=spc_ig") == [(m0, 5)]


def test_by_month_skips_an_unreported_reading(client, db_path, new_york):
    """A null is "not reported", not "fell to zero" — the last real reading
    stands, rather than showing a drop of every view the post had."""
    (m1, t1), (m0, t0) = _ny_month(1), _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [(t1, 100), (t0, None)])
    assert _by_month(client) == [(m1, 100), (m0, 0)]


def test_by_month_keeps_a_drop_as_a_negative_month(client, db_path, new_york):
    """Platforms do remove views (spam filtering). The figure stays true; the
    chart is what decides how to draw it."""
    (m1, t1), (m0, t0) = _ny_month(1), _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [(t1, 100), (t0, 90)])
    assert _by_month(client) == [(m1, 100), (m0, -10)]


def test_by_month_starts_at_the_first_snapshot(client, db_path, new_york):
    """Months before anything was read are left out rather than shown as 0,
    and the views a post had before its first reading land in that reading's
    month — there is nothing to split them by."""
    m0, t0 = _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [(t0, 5000)])
    assert _by_month(client) == [(m0, 5000)]


def test_by_month_is_empty_with_no_snapshots(client, db_path, new_york):
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [])
    assert _by_month(client) == []


def test_by_month_covers_at_most_twelve_months(client, db_path, new_york):
    (_, t20), (m11, _), (m0, t0) = _ny_month(20), _ny_month(11), _ny_month(0)
    _published_with_metrics(db_path, "vid_a", "youtube", "spc_yt", [(t20, 1000), (t0, 1500)])
    months = _by_month(client)
    assert len(months) == 12
    assert months[0] == (m11, 0)
    assert months[-1] == (m0, 500)


def test_video_approved_is_not_agent_workable(client, db_path):
    """TMDEV-83 took publishing away from the agent — there is no MCP tool that
    can publish, by design. Leaving VIDEO_APPROVED in the workable set would
    have poll.py wake an agent every tick for a video it cannot act on, which
    is a cron loop that never terminates and burns a paid session each time.
    """
    from pipeline import WORKABLE_STATUSES
    assert "VIDEO_APPROVED" not in WORKABLE_STATUSES

    _approved_video(db_path)
    assert json.loads(client.get("/videos/workable").data) == []
    assert json.loads(client.get("/pipeline/status").data)["workable_count"] == 0


def test_the_mcp_workable_set_matches_this_one():
    """Two hand-maintained copies; the comment alone has never held them."""
    import pathlib
    from pipeline import WORKABLE_STATUSES
    mcp_src = (pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py").read_text()
    block = mcp_src.split("WORKABLE_STATUSES = [", 1)[1].split("]", 1)[0]
    assert sorted(s.strip().strip('",') for s in block.split() if s.strip().strip('",')) == \
        sorted(WORKABLE_STATUSES)


# ── TMDEV-83 review fixes ────────────────────────────────────────────────────

def test_the_video_is_claimed_before_any_postforme_side_effect(client, db_path, rendered):
    """The claim must precede create_post, not follow it.

    Two overlapping publishes for the same video would otherwise both pass the
    status read, both create a real post at postforme, and only then race on the
    UPDATE — the loser returning 409 while a live post exists with no
    video_publications rows to track or settle it. Nothing downstream could ever
    reconcile that: the worker polls by post id, and there is no row holding one.
    """
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    seen = {}

    def record_status(*args, **kwargs):
        con = sqlite3.connect(db_path)
        seen["at_create_post"] = con.execute(
            "SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
        con.close()
        return {"id": "sp_1"}

    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", side_effect=record_status):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 201
    assert seen["at_create_post"] == "PUBLISHING"


def test_a_second_overlapping_publish_never_reaches_postforme(client, db_path, rendered):
    """The loser of the race must be stopped before it can create a post."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    _publish_ok(client, db_path, vid)   # first one wins and leaves it PUBLISHING

    with mock.patch("postforme.create_upload_url") as slot, \
         mock.patch("postforme.create_post") as create:
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 409
    slot.assert_not_called()
    create.assert_not_called()


def test_a_failed_publish_releases_the_claim_so_it_can_be_retried(client, db_path, rendered):
    """Claiming first means a postforme failure now has something to undo — the
    video must go back to VIDEO_APPROVED rather than stranding in PUBLISHING."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    side_effect=pfm.PostformeError("upload url refused")):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502

    con = sqlite3.connect(db_path)
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    rows = con.execute("SELECT COUNT(*) FROM video_publications").fetchone()[0]
    con.close()
    assert status == "VIDEO_APPROVED"
    assert rows == 0

    # ...and the retry genuinely works.
    assert _publish_ok(client, db_path, vid).status_code == 201


def test_a_video_with_no_project_resolves_the_worker_s_default_directory(client, db_path,
                                                                        tmp_path, monkeypatch):
    """worker.py:_stage_and_render writes to OUTPUT_DIR/"default_proj" when a
    video has no project_id. Rebasing to OUTPUT_DIR/"" here would make every
    such video fail publishing with "No rendered video file to publish" despite
    having a perfectly good render."""
    out = tmp_path / "out2"
    (out / "default_proj").mkdir(parents=True)
    (out / "default_proj" / "vid_noproj.mp4").write_bytes(b"\x00mp4")
    monkeypatch.setattr(pipeline, "OUTPUT_DIR", out)

    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO videos (id, project_id, topic, title, strategy, status,"
                " video_path, created_at, updated_at) VALUES"
                " ('vid_noproj', NULL, 'T', 'A', 'manual', 'VIDEO_APPROVED',"
                " '/output_videos/default_proj/vid_noproj.mp4', 'n', 'n')")
    con.commit()
    con.close()

    assert _publish_ok(client, db_path, "vid_noproj").status_code == 201


def test_output_path_matches_the_workers_default_project_convention():
    assert pipeline._output_path("", "v").parent.name == "default_proj"
    assert pipeline._output_path(None, "v").parent.name == "default_proj"


def test_publishing_sends_the_requested_privacy_per_platform(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt", "spc_ig"])
    vid = _approved_video(db_path)
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", return_value={"id": "sp_1"}) as create:
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt", "spc_ig"], "title": "T", "description": "D",
                          "privacy": {"youtube": "unlisted"}})
    cfg = create.call_args.kwargs["platform_configurations"]
    assert cfg["youtube"]["privacy_status"] == "unlisted"
    # Instagram has no such field; asking for one must not invent it.
    assert "privacy_status" not in cfg["instagram"]


def test_privacy_defaults_to_public_when_none_is_given(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", return_value={"id": "sp_1"}) as create:
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert create.call_args.kwargs[
        "platform_configurations"]["youtube"]["privacy_status"] == "public"


def test_an_unsupported_privacy_value_is_a_400_that_changes_nothing(client, db_path, rendered):
    """It is the caller's mistake, so it must not move the video's status — and
    it must be caught here, since postforme would accept it and quietly post
    the video publicly instead."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    with mock.patch("postforme.create_upload_url") as slot:
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D",
                              "privacy": {"tiktok": "unlisted"}})
    assert r.status_code == 400
    slot.assert_not_called()

    con = sqlite3.connect(db_path)
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    assert status == "VIDEO_APPROVED"


def test_a_non_object_privacy_field_is_rejected(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    r = client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "privacy": "private"})
    assert r.status_code == 400


# ── TMDEV-83: YouTube Shorts eligibility ─────────────────────────────────────

@pytest.fixture
def jobs(tmp_path, monkeypatch):
    """JOBS_DIR in a temp tree: the timeline is read from JOBS_DIR/<id>/, never
    from videos.timeline_path (TMDEV-162)."""
    monkeypatch.setattr(pipeline, "JOBS_DIR", tmp_path / "jobs")
    (tmp_path / "jobs" / "vid_pub").mkdir(parents=True)
    return tmp_path / "jobs"


def _with_timeline(db_path, jobs, seconds):
    tl = jobs / "vid_pub" / "timeline.json"
    tl.write_text(json.dumps({"audioDurationSeconds": seconds,
                              "totalFrames": int(seconds * 30), "fps": 30}))
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET timeline_path = ? WHERE id = 'vid_pub'", (str(tl),))
    con.commit()
    con.close()


def test_a_short_video_is_reported_as_shorts_eligible(client, db_path, jobs):
    _enable_publishing(db_path)
    _approved_video(db_path)
    _with_timeline(db_path, jobs, 92.0)
    body = json.loads(client.post("/videos/vid_pub/publish-prefill").data)
    assert body["youtube_short"] is True
    assert body["duration_secs"] == 92.0


def test_a_video_over_three_minutes_is_reported_as_not_a_short(client, db_path, jobs):
    """TMDEV-81 measured real finished videos at 250s. Nothing enforces the word
    budget that would keep them under the ceiling, so without this the failure
    is invisible until someone looks at YouTube."""
    _enable_publishing(db_path)
    _approved_video(db_path)
    _with_timeline(db_path, jobs, 250.4)
    body = json.loads(client.post("/videos/vid_pub/publish-prefill").data)
    assert body["youtube_short"] is False


def test_exactly_three_minutes_still_counts_as_a_short(client, db_path, jobs):
    _enable_publishing(db_path)
    _approved_video(db_path)
    _with_timeline(db_path, jobs, 180.0)
    assert json.loads(client.post("/videos/vid_pub/publish-prefill").data)["youtube_short"] is True


def test_an_unknown_duration_is_null_not_a_guess(client, db_path):
    """No timeline means we do not know. Claiming either answer would be worse
    than saying nothing — the UI shows the warning only on a definite False."""
    _enable_publishing(db_path)
    _approved_video(db_path)
    body = json.loads(client.post("/videos/vid_pub/publish-prefill").data)
    assert body["duration_secs"] is None
    assert body["youtube_short"] is None


def test_the_duration_rides_along_with_stored_metadata(client, db_path, jobs):
    """It rides on the prefill response, so a video whose metadata the agent
    already wrote must not silently lose the warning."""
    _enable_publishing(db_path)
    _approved_video(db_path)
    _set_publish_metadata(db_path, "vid_pub", "Agent Title", "Agent body.")
    _with_timeline(db_path, jobs, 250.0)
    body = json.loads(client.post("/videos/vid_pub/publish-prefill").data)
    assert body["title"] == "Agent Title"
    assert body["youtube_short"] is False


def test_a_corrupt_timeline_reads_as_unknown_rather_than_erroring(client, db_path, jobs):
    _enable_publishing(db_path)
    _approved_video(db_path)
    bad = jobs / "vid_pub" / "timeline.json"
    bad.write_text("{not json")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET timeline_path = ? WHERE id = 'vid_pub'", (str(bad),))
    con.commit()
    con.close()
    r = client.post("/videos/vid_pub/publish-prefill")
    assert r.status_code == 200
    assert json.loads(r.data)["youtube_short"] is None


# ── TMDEV-83: publishing leaves a durable record ─────────────────────────────

def _comments(db_path, vid="vid_pub"):
    con = sqlite3.connect(db_path)
    rows = [r[0] for r in con.execute(
        "SELECT content FROM comments WHERE video_id = ? ORDER BY id", (vid,))]
    con.close()
    return rows


def test_a_failed_publish_is_recorded_as_a_comment(client, db_path, rendered):
    """Without this the only trace is a dialog message that vanishes when the
    dialog closes — pipeline.py has no logger, so nothing reaches the container
    log either."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    side_effect=pfm.PostformeError("postforme returned HTTP 502: upstream")):
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    notes = _comments(db_path)
    assert any("Publishing failed" in c and "nothing was posted" in c for c in notes)
    assert any("HTTP 502" in c for c in notes)


def test_a_successful_publish_records_where_it_went(client, db_path, rendered):
    """So the thread reads submitted -> published rather than starting at the
    worker's outcome with no record of what was asked for."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt", "spc_ig"])
    vid = _approved_video(db_path)
    _publish_ok(client, db_path, vid, ("spc_yt", "spc_ig"))
    joined = " ".join(_comments(db_path))
    assert "Publishing to 2 account(s)" in joined
    assert "youtube (spc_yt)" in joined
    assert "instagram (spc_ig)" in joined


def test_a_rejected_publish_leaves_no_comment(client, db_path, rendered):
    """Validation failures are reported in the dialog and are self-explanatory;
    commenting on every mis-click would bury the outcomes that matter."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    client.post(f"/videos/{vid}/publish",
                json={"account_ids": ["spc_ig"], "title": "T", "description": "D"})
    assert _comments(db_path) == []


def test_the_publish_comment_never_carries_a_credential(client, db_path, rendered):
    """postforme error bodies embed the connected channel's OAuth tokens, and
    this table is rendered in the dashboard. The message arrives already
    scrubbed; this pins that the route does not undo it."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    scrubbed = pfm._error_message(
        type("R", (), {"status_code": 400,
                       "json": lambda self: {"error": {"message": "bad"},
                                             "account": {"refresh_token": "1//LIVE"}}})(),
        "key")
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url", side_effect=pfm.PostformeError(scrubbed)):
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert "1//LIVE" not in " ".join(_comments(db_path))


def test_a_comment_failure_does_not_break_the_publish_response(client, db_path, rendered):
    """Losing the record of a failure must not also break the response that
    reports it. The table is dropped so the insert genuinely fails, rather than
    mocking the call away and testing nothing."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    con = sqlite3.connect(db_path)
    con.execute("DROP TABLE comments")
    con.commit()
    con.close()

    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url", side_effect=pfm.PostformeError("boom")):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502

    # ...and the claim was still released, so the button still works.
    con = sqlite3.connect(db_path)
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    assert status == "VIDEO_APPROVED"


def test_an_upload_failure_releases_the_claim_because_nothing_was_posted(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url", side_effect=pfm.PostformeError("no slot")):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502
    assert json.loads(r.data).get("reconciling") is None
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0] \
        == "VIDEO_APPROVED"
    con.close()


def test_a_create_post_failure_keeps_the_claim_because_it_is_ambiguous(client, db_path, rendered):
    """A timeout, a 5xx or a non-JSON body can all arrive *after* postforme
    accepted the post. Releasing the claim would invite a retry that publishes
    the same video twice for real, with no local row for the first one — and
    nothing downstream could ever reconcile that."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", side_effect=pfm.PostformeError("read timeout")):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502
    assert json.loads(r.data)["reconciling"] is True

    con = sqlite3.connect(db_path)
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    assert status == "PUBLISHING", "must stay claimed for the worker to reconcile"

    joined = " ".join(_comments(db_path))
    assert "unclear whether the post was created" in joined
    assert "Do not retry" in joined


def test_the_ambiguous_path_blocks_a_retry_rather_than_double_posting(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", side_effect=pfm.PostformeError("read timeout")):
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    # The status guard now does the work: PUBLISHING is not VIDEO_APPROVED.
    with mock.patch("postforme.create_post") as create:
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 409
    create.assert_not_called()


@pytest.mark.parametrize("status,expected", [
    (403, False),   # a durable rejection — the permission really is missing
    (401, False),
    (429, None),    # rate limited: entirely plausible at 5 req/s, says nothing
    (500, None),    # postforme having a bad day
    (503, None),
    (None, None),   # a transport failure carries no status at all
])
def test_a_transient_feed_error_is_not_reported_as_a_missing_permission(
        client, db_path, status, expected):
    """Telling someone to reconnect a working account because postforme
    hiccuped is worse than saying nothing."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.get_account_feed",
                    side_effect=pfm.PostformeError("nope", status)):
        accounts = json.loads(client.get("/publishing/accounts").data)
    assert next(a for a in accounts if a["id"] == "spc_yt")["analytics"] is expected


def test_a_working_feed_reports_analytics_available(client, db_path):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.get_account_feed", return_value={"data": [], "meta": {}}):
        accounts = json.loads(client.get("/publishing/accounts").data)
    assert next(a for a in accounts if a["id"] == "spc_yt")["analytics"] is True


def test_an_account_outside_the_allowlist_is_not_probed_at_all(client, db_path):
    """The probe costs a request each and the limit is 5/s — only accounts that
    will actually be published to are worth checking."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.get_account_feed",
                    return_value={"data": [], "meta": {}}) as feed:
        accounts = json.loads(client.get("/publishing/accounts").data)
    assert feed.call_count == 1
    assert next(a for a in accounts if a["id"] == "spc_ig")["analytics"] is None


def test_feeds_0_lists_accounts_without_probing_any_feed(client, db_path):
    """The Analytics page only needs names for its account filter. Probing
    every allowlisted feed on each page load would spend the 5/s limit for
    nothing, so it asks for the list alone."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.get_account_feed",
                    return_value={"data": [], "meta": {}}) as feed:
        accounts = json.loads(client.get("/publishing/accounts?feeds=0").data)
    assert feed.call_count == 0
    yt = next(a for a in accounts if a["id"] == "spc_yt")
    assert yt["analytics"] is None
    assert yt["allowed"] is True


# ── /logs ───────────────────────────────────────────────────────────────────

import tubematic_core.logging as tlog_module  # noqa: E402


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    d.mkdir()
    monkeypatch.setattr(pipeline, "LOG_DIR", d)
    return d


def _write_log(log_dir, service, records, day="2026-09-06"):
    with open(log_dir / f"{service}.{day}.jsonl", "a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _rec(ts, level="info", message="m", **extra):
    return {"ts": ts, "service": "api", "level": level, "message": message, **extra}


def test_get_logs_returns_newest_first_with_the_allowlist_echoed(client, log_dir):
    _write_log(log_dir, "api", [
        _rec("2026-09-06T01:00:00Z", message="older"),
        _rec("2026-09-06T02:00:00Z", message="newer"),
    ])
    body = json.loads(client.get("/logs").data)
    assert [r["message"] for r in body["records"]] == ["newer", "older"]
    assert body["count"] == 2
    # Echoed so the dashboard's filter list is not a second copy that can drift.
    assert body["services"] == list(tlog_module.SERVICES)
    assert body["levels"] == list(tlog_module.LEVELS)


def test_get_logs_is_uncacheable(client, log_dir):
    assert client.get("/logs").headers["Cache-Control"] == "no-store"


def test_get_logs_on_a_missing_directory_is_empty_not_an_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "LOG_DIR", tmp_path / "absent")
    r = client.get("/logs")
    assert r.status_code == 200
    assert json.loads(r.data)["records"] == []


def test_service_filter_is_optional_and_spans_every_service_when_omitted(client, log_dir):
    """A video's trail is cross-service: the renderer renders it, MCP voices and
    stages it, the API moves it between statuses. Requiring `service` would show
    a third of the story."""
    for i, svc in enumerate(("api", "mcp", "renderer")):
        _write_log(log_dir, svc, [
            _rec(f"2026-09-06T0{i}:00:00Z", message=svc, video_id="vid_1"),
        ])
    body = json.loads(client.get("/logs?video_id=vid_1").data)
    assert {r["message"] for r in body["records"]} == {"api", "mcp", "renderer"}

    only_mcp = json.loads(client.get("/logs?service=mcp&video_id=vid_1").data)
    assert [r["message"] for r in only_mcp["records"]] == ["mcp"]


@pytest.mark.parametrize("service", ["dashboard", "../../etc/passwd", "api/../mcp", "API"])
def test_an_unknown_service_is_rejected_before_anything_touches_the_filesystem(
    client, log_dir, service
):
    r = client.get(f"/logs?service={service}")
    assert r.status_code == 400
    assert "Unknown service" in json.loads(r.data)["error"]


def test_level_filter_is_a_minimum_not_an_exact_match(client, log_dir):
    _write_log(log_dir, "api", [
        _rec("2026-09-06T01:00:00Z", level="debug", message="d"),
        _rec("2026-09-06T02:00:00Z", level="info", message="i"),
        _rec("2026-09-06T03:00:00Z", level="warning", message="w"),
        _rec("2026-09-06T04:00:00Z", level="error", message="e"),
    ])
    got = json.loads(client.get("/logs?level=warning").data)["records"]
    assert {r["message"] for r in got} == {"w", "e"}


def test_an_unknown_level_is_rejected(client, log_dir):
    assert client.get("/logs?level=loud").status_code == 400


def test_search_and_profile_filters(client, log_dir):
    _write_log(log_dir, "api", [
        _rec("2026-09-06T01:00:00Z", message="render TIMED OUT"),
        _rec("2026-09-06T02:00:00Z", message="fine", profile_id="sp_1"),
    ])
    assert len(json.loads(client.get("/logs?q=timed+out").data)["records"]) == 1
    assert len(json.loads(client.get("/logs?profile_id=sp_1").data)["records"]) == 1


def test_limit_defaults_caps_and_rejects_junk(client, log_dir):
    _write_log(log_dir, "api", [
        _rec(f"2026-09-06T{h:02d}:00:00Z", message=str(h)) for h in range(1, 6)
    ])
    assert json.loads(client.get("/logs").data)["limit"] == pipeline.DEFAULT_LOG_LIMIT
    assert [r["message"] for r in json.loads(client.get("/logs?limit=2").data)["records"]] == ["5", "4"]
    for bad in ("abc", "0", "-1", str(pipeline.MAX_LOG_LIMIT + 1)):
        assert client.get(f"/logs?limit={bad}").status_code == 400, bad


def test_malformed_lines_do_not_blank_the_view(client, log_dir):
    """A half-written final line is normal in a file being appended to."""
    path = log_dir / "api.2026-09-06.jsonl"
    path.write_text(
        json.dumps(_rec("2026-09-06T01:00:00Z", message="good")) + "\n"
        "{ this is not json\n"
    )
    assert [r["message"] for r in json.loads(client.get("/logs").data)["records"]] == ["good"]


# ── log_retention_days ──────────────────────────────────────────────────────

def test_log_retention_days_defaults_to_14(client):
    assert json.loads(client.get("/settings").data)["log_retention_days"] == 14


def test_log_retention_days_round_trips(client):
    assert client.post("/settings", json={"log_retention_days": 30}).status_code == 200
    assert json.loads(client.get("/settings").data)["log_retention_days"] == 30


@pytest.mark.parametrize("value", [0, -1, 366, 10000])
def test_log_retention_days_outside_1_to_365_is_rejected(client, value):
    """0 would mean 'delete the file this service is writing right now'."""
    r = client.post("/settings", json={"log_retention_days": value})
    assert r.status_code == 400


def test_log_retention_days_is_not_masked_like_a_secret(client):
    """It is an int, not a credential — a mask here would break the dashboard
    round-trip that other int settings rely on."""
    assert json.loads(client.post("/settings", json={"log_retention_days": 7}).data)[
        "log_retention_days"] == 7


# ── request logging ─────────────────────────────────────────────────────────

def test_a_request_is_logged_with_a_request_id_and_status(client, log_dir, caplog):
    with caplog.at_level("INFO", logger="api"):
        client.get("/stats")
    rec = next(r for r in caplog.records if r.name == "api")
    assert rec.status == 200
    assert len(rec.request_id) == 8
    assert isinstance(rec.duration_ms, int)


def test_a_client_error_logs_at_warning(client, log_dir, caplog):
    """A 4xx is the caller's problem; an error-filtered view is for ours."""
    with caplog.at_level("INFO", logger="api"):
        client.get("/videos/does-not-exist")
    assert next(r for r in caplog.records if r.name == "api").levelname == "WARNING"


def test_a_server_error_logs_the_traceback_at_error_and_still_raises(log_dir, caplog):
    """The half that actually matters, and the half a 404 does not exercise.

    Also pins that the error handler re-raises: it exists to observe the
    failure, not to swallow it into a tidy 500 that this endpoint set never
    produced before.
    """
    from flask import Flask
    app = Flask(__name__)
    bp = create_pipeline_blueprint()

    @bp.get("/boom")
    def _boom():
        raise RuntimeError("kaboom")

    app.register_blueprint(bp)
    app.config["TESTING"] = True  # propagate, as the repo's own client fixture does
    with app.test_client() as c, caplog.at_level("INFO", logger="api"):
        with pytest.raises(RuntimeError, match="kaboom"):
            c.get("/boom")

    records = [r for r in caplog.records if r.name == "api"]
    assert any(r.levelname == "ERROR" and "kaboom" in (r.exc_text or "") for r in records)


def test_the_video_id_in_the_path_is_carried_onto_the_record(client, db_path, log_dir, caplog):
    """This is what makes the VideoModal's per-video tab show API activity and
    not just the renderer's."""
    _seed_video(db_path)
    with caplog.at_level("INFO", logger="api"):
        client.get("/videos/vid-1")
    assert next(r for r in caplog.records if r.name == "api").video_id == "vid-1"


def test_health_is_not_logged_because_the_hooks_are_on_the_blueprint(caplog):
    """The compose healthcheck runs every 15s — ~5,760 lines a day saying
    nothing. /health and /render/health live on the app in server.py, so
    blueprint hooks never see them; that is the mechanism, not a skip list."""
    from flask import Flask
    app = Flask(__name__)

    @app.get("/health")
    def _health():
        return {"status": "ok"}

    app.register_blueprint(create_pipeline_blueprint())
    with app.test_client() as c, caplog.at_level("INFO", logger="api"):
        c.get("/health")
    assert [r for r in caplog.records if r.name == "api"] == []


# ── TMDEV-97: rows at the claim, and Retry publishing ────────────────────────

def _pubs(db_path, vid="vid_pub"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM video_publications WHERE video_id = ? ORDER BY social_account_id", (vid,))]
    con.close()
    return rows


def _status(db_path, vid="vid_pub"):
    con = sqlite3.connect(db_path)
    status = con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0]
    con.close()
    return status


def test_the_rows_are_written_at_the_claim_with_no_post_id_yet(client, db_path, rendered):
    """An empty post id is what tells the worker a publish is in flight. Without
    rows the upload looked like a crashed publish and was failed mid-way."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt", "spc_ig"])
    vid = _approved_video(db_path)
    seen = {}

    def during_upload(*a, **k):
        seen["pubs"] = _pubs(db_path, vid)

    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media", side_effect=during_upload), \
         mock.patch("postforme.create_post", return_value={"id": "sp_1"}):
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt", "spc_ig"], "title": "T", "description": "D"})
    assert [(p["social_account_id"], p["platform"], p["postforme_post_id"], p["status"])
            for p in seen["pubs"]] == [("spc_ig", "instagram", "", "PENDING"),
                                       ("spc_yt", "youtube", "", "PENDING")]
    assert {p["postforme_post_id"] for p in _pubs(db_path, vid)} == {"sp_1"}


def test_an_account_lookup_failure_changes_nothing(client, db_path, rendered):
    """Resolved before the claim, so it is a clean failure with no rows."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", side_effect=pfm.PostformeError("down")), \
         mock.patch("postforme.create_upload_url") as slot:
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502
    slot.assert_not_called()
    assert _status(db_path, vid) == "VIDEO_APPROVED"
    assert _pubs(db_path, vid) == []


def test_an_upload_failure_after_the_worker_failed_the_video_keeps_its_rows(client, db_path,
                                                                           rendered):
    """The rows of a FAILED video are what offers Retry publishing. Deleting
    them when the release UPDATE did nothing would leave it deletable only."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm

    def worker_fails_it_then_upload_dies(*a, **k):
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET status = 'FAILED' WHERE id = ?", (vid,))
        con.execute("UPDATE video_publications SET status = 'FAILED' WHERE video_id = ?", (vid,))
        con.commit()
        con.close()
        raise pfm.PostformeError("upload died")

    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media", side_effect=worker_fails_it_then_upload_dies):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 502
    assert _status(db_path, vid) == "FAILED"
    assert len(_pubs(db_path, vid)) == 1


def test_the_post_id_fills_only_this_request_s_own_rows(client, db_path, rendered):
    """Rows are matched by the ids this request inserted, never by "any empty
    row of this video" — another attempt's in-flight rows must not receive
    this post. created_at is reset too, so the platforms get their full
    reporting window from the post's creation rather than from before the
    upload."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)

    def another_attempt_appears(*a, **k):
        con = sqlite3.connect(db_path)
        con.execute(
            "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
            " postforme_post_id, status, created_at, updated_at)"
            " VALUES ('other', ?, 'youtube', 'spc_other', '', 'PENDING', 'old', 'old')", (vid,))
        con.execute("UPDATE video_publications SET created_at = 'old' WHERE video_id = ?", (vid,))
        con.commit()
        con.close()

    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media", side_effect=another_attempt_appears), \
         mock.patch("postforme.create_post", return_value={"id": "sp_mine"}):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert r.status_code == 201
    rows = {p["social_account_id"]: p for p in _pubs(db_path, vid)}
    assert rows["spc_yt"]["postforme_post_id"] == "sp_mine"
    assert rows["spc_yt"]["created_at"] != "old", "the deadline restarts at the post"
    assert rows["spc_other"]["postforme_post_id"] == ""


# ── retry ──

def _failed_publish(db_path, vid="vid_pub", accounts=(("spc_yt", "youtube"),),
                    error="upload rejected"):
    _approved_video(db_path, vid=vid, status="FAILED")
    con = sqlite3.connect(db_path)
    for account, platform in accounts:
        con.execute(
            "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
            " postforme_post_id, status, error, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'sp_old', 'FAILED', ?, 'n', 'n')",
            (f"{vid}-{account}", vid, platform, account, error))
    con.commit()
    con.close()
    return vid


def _found(post_id="sp_live", accounts=("spc_yt", "spc_ig"), live=True):
    return {"id": post_id, "live": live, "results": [],
            "social_accounts": [{"id": a, "platform": "youtube" if a == "spc_yt" else "instagram"}
                                for a in accounts]}


def test_retry_adopts_a_live_post_instead_of_posting_again(client, db_path):
    """The observed case: FAILED locally, live on both accounts. Nothing is
    re-posted; the video goes back to PUBLISHING and the worker settles it."""
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    with mock.patch("postforme.find_post_by_external_id", return_value=_found()), \
         mock.patch("postforme.create_post") as create, \
         mock.patch("postforme.upload_media") as upload:
        r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 200
    assert json.loads(r.data)["outcome"] == "reconciling"
    create.assert_not_called()
    upload.assert_not_called()
    assert _status(db_path, vid) == "PUBLISHING"
    assert [(p["social_account_id"], p["postforme_post_id"], p["status"])
            for p in _pubs(db_path, vid)] == [("spc_ig", "sp_live", "PENDING"),
                                              ("spc_yt", "sp_live", "PENDING")]
    assert any("was not posted again" in c for c in _comments(db_path, vid))


def test_retry_with_no_post_returns_the_video_to_approved(client, db_path):
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    with mock.patch("postforme.find_post_by_external_id", return_value=None):
        r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 200
    assert json.loads(r.data)["outcome"] == "republish"
    assert _status(db_path, vid) == "VIDEO_APPROVED"
    assert _pubs(db_path, vid) == []
    # The rows are gone, so the comment is the only record of what failed.
    assert any("upload rejected" in c for c in _comments(db_path, vid))


def test_retry_treats_a_post_that_failed_everywhere_as_not_posted(client, db_path):
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    with mock.patch("postforme.find_post_by_external_id", return_value=_found(live=False)):
        r = client.post(f"/videos/{vid}/publish/retry")
    assert json.loads(r.data)["outcome"] == "republish"
    assert _status(db_path, vid) == "VIDEO_APPROVED"


def test_retry_then_publishes_again_through_the_normal_route(client, db_path, rendered):
    """Acceptance: a video that genuinely never posted is published once."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _failed_publish(db_path)
    with mock.patch("postforme.find_post_by_external_id", return_value=None):
        client.post(f"/videos/{vid}/publish/retry")
    r = _publish_ok(client, db_path, vid)
    assert r.status_code == 201
    assert _status(db_path, vid) == "PUBLISHING"
    assert [p["postforme_post_id"] for p in _pubs(db_path, vid)] == ["sp_1"]


@pytest.mark.parametrize("status", ["VIDEO_APPROVED", "PUBLISHED", "PUBLISHING"])
def test_retry_refuses_a_video_that_is_not_failed(client, db_path, status):
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = ? WHERE id = ?", (status, vid))
    con.commit()
    con.close()
    with mock.patch("postforme.find_post_by_external_id") as find:
        r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 409
    find.assert_not_called()


def test_retry_refuses_a_video_that_did_not_fail_while_publishing(client, db_path):
    """A render failure has no publication rows — there is nothing to retry."""
    _enable_publishing(db_path)
    _approved_video(db_path, status="FAILED")
    with mock.patch("postforme.find_post_by_external_id") as find:
        r = client.post("/videos/vid_pub/publish/retry")
    assert r.status_code == 409
    assert "failed while publishing" in json.loads(r.data)["error"]
    find.assert_not_called()


def test_retry_refuses_an_archived_video(client, db_path):
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET archived_at = 'n' WHERE id = ?", (vid,))
    con.commit()
    con.close()
    r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 409
    assert "archived" in json.loads(r.data)["error"]


def test_a_second_retry_is_refused_rather_than_acting_twice(client, db_path):
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    with mock.patch("postforme.find_post_by_external_id", return_value=_found()):
        assert client.post(f"/videos/{vid}/publish/retry").status_code == 200
        assert client.post(f"/videos/{vid}/publish/retry").status_code == 409
    assert len(_pubs(db_path, vid)) == 2


def test_a_retry_that_loses_the_claim_changes_nothing(client, db_path):
    """Two overlapping retries may both look up postforme; only one may act."""
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)

    def another_retry_wins(*a, **k):
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET status = 'VIDEO_APPROVED' WHERE id = ?", (vid,))
        con.commit()
        con.close()
        return _found()

    with mock.patch("postforme.find_post_by_external_id", side_effect=another_retry_wins):
        r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 409
    assert [p["postforme_post_id"] for p in _pubs(db_path, vid)] == ["sp_old"]


def test_a_retry_lookup_failure_is_a_502_that_changes_nothing(client, db_path):
    """An outage must not be read as "nothing was posted" — that would invite a
    second post of a video that may already be live."""
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    import postforme as pfm
    with mock.patch("postforme.find_post_by_external_id",
                    side_effect=pfm.PostformeError("503")):
        r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 502
    assert _status(db_path, vid) == "FAILED"
    assert len(_pubs(db_path, vid)) == 1


def test_retry_is_unavailable_while_publishing_is_off(client, db_path):
    vid = _failed_publish(db_path)
    r = client.post(f"/videos/{vid}/publish/retry")
    assert r.status_code == 503


# ── Agent effort (TMDEV-106) ─────────────────────────────────────────────────

def test_the_effort_levels_and_default_match_the_other_two_copies():
    """AGENT_EFFORTS is hand-duplicated across three processes and the
    dashboard, behind "Keep in sync" comments. A comment is not a check.

    Read as source text rather than imported: mcp/server.py starts an MCP
    server on import in some configurations, and dashboard/lib/agents.ts is
    TypeScript. The point is that all four literals agree, which text
    comparison proves without running any of them.
    """
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[3]

    def _levels(text, name):
        m = re.search(name + r"\s*[:=]?\s*[=(\[]([^)\]]*)[)\]]", text)
        assert m, f"could not find {name}"
        return tuple(re.findall(r'"([a-z]+)"', m.group(1)))

    mcp_src = (root / "mcp" / "server.py").read_text()
    adapter_src = (root / "scripts" / "agent_adapters.py").read_text()
    dash_src = (root / "dashboard" / "lib" / "agents.ts").read_text()

    assert _levels(mcp_src, "AGENT_EFFORTS") == pipeline.AGENT_EFFORTS
    assert _levels(adapter_src, "EFFORTS") == pipeline.AGENT_EFFORTS
    assert _levels(dash_src, "AGENT_EFFORTS") == pipeline.AGENT_EFFORTS
    assert pipeline.DEFAULT_AGENT_EFFORT == "high"
    assert pipeline.DEFAULT_AGENT_EFFORT in pipeline.AGENT_EFFORTS


def test_effort_is_not_a_settings_key(client):
    """TMDEV-90 removed agent_model from SETTINGS_SPEC deliberately; per-agent
    defaults live on the agents row. Effort must not reintroduce the pattern."""
    for key in ("effort", "agent_effort"):
        assert key not in pipeline.SETTINGS_SPEC
    assert client.post("/settings", json={"agent_effort": "high"}).status_code == 400


# ── PATCH /agents — the per-agent default ──

def test_patch_agent_effort_is_stored(client, db_path):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"effort": "max"})
    assert r.status_code == 200
    assert json.loads(r.data)["effort"] == "max"
    assert json.loads(client.get("/agents").data)[0]["effort"] == "max"


@pytest.mark.parametrize("value", ["HIGH", "extreme", "", " high ", None, 3, True])
def test_patch_agent_effort_rejects_anything_outside_the_set(client, db_path, value):
    _seed_agent(db_path)
    r = client.patch("/agents/claude", json={"effort": value})
    assert r.status_code == 400
    assert "effort" in json.loads(r.data)["error"]
    assert json.loads(client.get("/agents").data)[0]["effort"] == "high"


def test_patch_agent_effort_combines_with_the_default_model(client, db_path):
    _seed_agent(db_path)
    row = json.loads(client.patch(
        "/agents/claude", json={"effort": "low", "default_model": "opus"}).data)
    assert (row["effort"], row["models"][0]) == ("low", "opus")


def test_patch_agent_effort_on_an_uninstalled_agent_is_409(client, db_path):
    _seed_agent(db_path, archived_at="2026-01-02T00:00:00Z")
    assert client.patch("/agents/claude", json={"effort": "max"}).status_code == 409


def test_an_agent_row_defaults_to_high(client, db_path):
    """Rule 1: an install that never touches the setting runs at high."""
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO agents (id, name, binary, run_path, created_at, updated_at) "
        "VALUES ('claude', 'C', 'claude', '/tmp/a', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert json.loads(client.get("/agents").data)[0]["effort"] == "high"


# ── PATCH /videos — the per-video override ──

def test_agent_effort_column_defaults_to_blank(client, db_path):
    """Blank is the value that means "follow this video's agent"."""
    _seed_agent(db_path)
    vid = _new_video(client)
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_effort"] == ""


@pytest.mark.parametrize("value", ["low", "medium", "high", "xhigh", "max", ""])
def test_patch_video_accepts_every_documented_level_and_blank(client, db_path, value):
    _seed_agent(db_path)
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_effort": value})
    assert p.status_code == 200
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_effort"] == value


@pytest.mark.parametrize("value", ["HIGH", "extreme", "--effort", "two words", 3, True, None])
def test_patch_video_rejects_an_unknown_level(client, db_path, value):
    _seed_agent(db_path)
    vid = _new_video(client)
    p = client.patch(f"/videos/{vid}", json={"agent_effort": value})
    assert p.status_code == 400
    assert "agent_effort" in json.loads(p.data)["error"]
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_effort"] == ""


def test_patch_video_strips_the_effort(client, db_path):
    _seed_agent(db_path)
    vid = _new_video(client)
    assert client.patch(f"/videos/{vid}", json={"agent_effort": "  max  "}).status_code == 200
    assert json.loads(client.get(f"/videos/{vid}").data)["agent_effort"] == "max"


def test_the_effort_needs_no_installed_agent(client):
    """Unlike agent_model, which is checked against that agent's own list.

    The five levels are the same for every agent, so there is nothing to look
    up — and an install between agents must not lose a pick the human made.
    """
    vid = _new_video(client)
    assert client.patch(f"/videos/{vid}", json={"agent_effort": "max"}).status_code == 200


# ── Publish-metadata usage (TMDEV-107) ───────────────────────────────────────

# ── POST /usage/agent-session (TMDEV-107) ────────────────────────────────────

def test_agent_session_records_each_event_against_the_whole_batch(client, db_path):
    import sqlite3
    r = client.post("/usage/agent-session", json={
        "session_id": "s-1", "operation": "agent_pipeline", "agent": "claude",
        "videos": [{"video_id": "v1", "stage": "TOPIC_APPROVED"},
                   {"video_id": "v2", "stage": "VOICE_READY"}],
        "events": [{"service": "anthropic", "model": "claude-opus-5-5",
                    "units": {"input": 100, "output": 20}, "reported_cost_usd": 0.12},
                   {"service": "anthropic", "model": "claude-haiku-4-5",
                    "units": {"input": 5}, "reported_cost_usd": 0.001}],
    })
    assert r.status_code == 200 and r.get_json() == {"recorded": 2, "events": 2}
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT e.model, e.cost_basis, e.session_id, l.video_id, l.stage "
                       "FROM usage_events e JOIN usage_event_videos l ON l.event_id = e.id "
                       "ORDER BY e.id, l.video_id").fetchall()
    con.close()
    assert rows == [
        ("claude-opus-5-5", "reported", "s-1", "v1", "TOPIC_APPROVED"),
        ("claude-opus-5-5", "reported", "s-1", "v2", "VOICE_READY"),
        ("claude-haiku-4-5", "reported", "s-1", "v1", "TOPIC_APPROVED"),
        ("claude-haiku-4-5", "reported", "s-1", "v2", "VOICE_READY"),
    ]


def test_a_resent_agent_session_is_not_recorded_twice(client, db_path):
    """poll.py logs a payload for resending when its POST times out — possibly
    after the server committed. Resending must not double the session's spend."""
    import sqlite3
    payload = {"session_id": "s-9", "operation": "agent_research", "agent": "codex",
               "events": [{"service": "openai", "model": "gpt-5.5", "units": {"input": 10}},
                          {"service": "openai", "model": "gpt-5.5", "units": {"input": 20}}]}
    assert client.post("/usage/agent-session", json=payload).get_json() == \
        {"recorded": 2, "events": 2}
    assert client.post("/usage/agent-session", json=payload).get_json() == \
        {"recorded": 2, "events": 2}
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0] == 2
    con.close()


def test_agent_session_requires_a_session_id(client):
    assert client.post("/usage/agent-session", json={
        "operation": "agent_research",
        "events": [{"service": "openai", "units": {"input": 1}}]}).status_code == 400


def test_agent_session_rejects_an_unknown_operation_or_no_events(client):
    assert client.post("/usage/agent-session", json={
        "operation": "ai_review", "events": [{"service": "x"}]}).status_code == 400
    assert client.post("/usage/agent-session", json={
        "operation": "agent_research", "events": []}).status_code == 400


# ── Cost read routes and the price table (TMDEV-107) ─────────────────────────

def _seed_usage(db_path):
    from tubematic_core import usage as tusage
    tusage.record_usage(db_path, service="gemini", model="gemini-2.5-flash",
                        operation="ai_review", units={"input": 1_000_000}, videos=["v1"])
    tusage.record_usage(db_path, service="elevenlabs", model="eleven_multilingual_v2",
                        operation="voice", units={"credits": 1240}, videos=["v1"])
    tusage.record_usage(db_path, service="anthropic", model="claude-sonnet-5",
                        operation="agent_pipeline", reported_cost_usd=0.15, session_id="s1",
                        videos=[("v1", "TOPIC_APPROVED"), ("v2", "TOPIC_APPROVED"),
                                ("v3", "TOPIC_APPROVED")])
    tusage.record_usage(db_path, service="gemini", model="gemini-9-flash",
                        operation="mining", units={"input": 1000})


def test_video_costs_route_shows_lines_credits_and_the_agent_share(client, db_path):
    _seed_usage(db_path)
    body = client.get("/videos/v1/costs").get_json()
    assert body["has_usage"] is True
    assert body["credits"] == 1240
    assert body["agent"]["share_usd"] == pytest.approx(0.05)
    assert body["agent"]["session_total_usd"] == pytest.approx(0.15)
    assert body["total_usd"] == pytest.approx(0.30 + 0.05)


def test_usage_summary_counts_unpriced_calls_and_omits_a_pool_it_cannot_read(client, db_path):
    _seed_usage(db_path)
    body = client.get("/usage/summary?since=2000-01-01T00:00:00Z").get_json()
    assert body["unpriced_calls"] == 1
    assert body["voice_credits"] == 1240
    assert body["elevenlabs_pool"] is None  # no key in this test environment
    assert client.get("/usage/summary?since=yesterday").status_code == 400


def _usage_at(db_path, created_at, cost):
    from tubematic_core import usage as tusage
    eid = tusage.record_usage(db_path, service="anthropic", model="claude-sonnet-5",
                              operation="agent_research", reported_cost_usd=cost)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE usage_events SET created_at = ? WHERE id = ?", (created_at, eid))
    con.commit()
    con.close()


def test_usage_summary_dates_are_whole_days_in_the_host_timezone(client, db_path, monkeypatch):
    """The Spend tab picks calendar days, and a day is the host's day — the
    same zone every other date on the dashboard is shown in. 03:00Z on the 11th
    is still the 10th in New York, and `to` covers the whole of its day."""
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "America/New_York")
    _usage_at(db_path, "2026-09-10T03:59:59Z", 1.0)   # 9th, 23:59 local — outside
    _usage_at(db_path, "2026-09-10T04:00:00Z", 0.5)   # 10th, 00:00 local — inside
    _usage_at(db_path, "2026-09-11T03:00:00Z", 0.25)  # 10th, 23:00 local — inside
    _usage_at(db_path, "2026-09-11T04:00:00Z", 2.0)   # 11th, 00:00 local — outside
    body = client.get("/usage/summary?from=2026-09-10&to=2026-09-10").get_json()
    assert body["total_usd"] == pytest.approx(0.75)
    assert body["since"] == "2026-09-10T04:00:00Z"
    assert body["until"] == "2026-09-11T04:00:00Z"
    assert (body["from"], body["to"], body["timezone"]) == \
        ("2026-09-10", "2026-09-10", "America/New_York")


def test_usage_summary_day_boundaries_follow_dst(client, db_path, monkeypatch):
    """A range across the November switch ends at the local midnight after
    it, not a fixed UTC offset — an hour of spend would otherwise drift out."""
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "America/New_York")
    body = client.get("/usage/summary?from=2026-10-31&to=2026-11-01").get_json()
    assert body["since"] == "2026-10-31T04:00:00Z"  # EDT
    assert body["until"] == "2026-11-02T05:00:00Z"  # EST


def test_usage_summary_falls_back_to_utc_days_without_a_host_zone(client, db_path, monkeypatch):
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: None)
    body = client.get("/usage/summary?from=2026-09-10&to=2026-09-12").get_json()
    assert (body["since"], body["until"], body["timezone"]) == \
        ("2026-09-10T00:00:00Z", "2026-09-13T00:00:00Z", "UTC")


def test_usage_summary_falls_back_to_utc_for_a_zone_it_cannot_load(client, db_path, monkeypatch):
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "Not/AZone")
    body = client.get("/usage/summary?from=2026-09-10&to=2026-09-10").get_json()
    assert body["timezone"] == "UTC"
    assert body["since"] == "2026-09-10T00:00:00Z"


def test_usage_summary_presets_are_resolved_in_the_host_zone(client, db_path, monkeypatch):
    """The API decides which day "today" is, not the browser. The dashboard
    learns the host zone asynchronously and falls back to UTC, so a preset it
    derived itself could name the wrong day — and keep naming it if the zone
    lookup failed."""
    import zoneinfo
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "America/New_York")
    today = datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
    expected = {"today": today, "week": today - timedelta(days=today.weekday()),
                "month": today.replace(day=1)}
    for preset, first in expected.items():
        body = client.get(f"/usage/summary?preset={preset}").get_json()
        assert (body["from"], body["to"], body["timezone"]) == \
            (first.isoformat(), today.isoformat(), "America/New_York"), preset


@pytest.mark.parametrize("today,preset,first", [
    ("2026-09-10", "today", "2026-09-10"),
    ("2026-09-10", "week", "2026-09-07"),   # a Thursday: the week began on Monday
    ("2026-09-13", "week", "2026-09-07"),   # a Sunday belongs to the week before it
    ("2026-09-07", "week", "2026-09-07"),   # a Monday is its own week's first day
    ("2027-01-01", "week", "2026-12-28"),   # a week can start in the previous year
    ("2026-09-10", "month", "2026-09-01"),
])
def test_preset_first_days(today, preset, first):
    day = datetime.strptime(today, "%Y-%m-%d").date()
    assert pipeline._preset_first_day(preset, day).isoformat() == first


@pytest.mark.parametrize("query", [
    "to=9999-12-31&from=2026-09-10",   # the day after `to` is past date.max
    "from=0001-01-01&to=0001-01-02",   # midnight in Tokyo is before year 1 in UTC
])
def test_usage_summary_refuses_a_range_it_cannot_represent(client, db_path, monkeypatch, query):
    """Both are enterable in a date field; neither may surface as a 500."""
    monkeypatch.setattr("hosttz._resolve_iana_name", lambda: "Asia/Tokyo")
    r = client.get(f"/usage/summary?{query}")
    assert r.status_code == 400
    assert r.get_json()["error"]


@pytest.mark.parametrize("query", [
    "preset=year",                                    # not a preset
    "preset=today&from=2026-09-10&to=2026-09-10",     # two ways at once
    "preset=today&since=2026-09-01T00:00:00Z",
    "from=2026-09-10",                                # no `to`
    "to=2026-09-10",                                  # no `from`
    "from=2026-09-12&to=2026-09-10",                  # backwards
    "from=2026-9-1&to=2026-09-10",                    # not YYYY-MM-DD
    "from=2026-02-30&to=2026-03-01",                  # not a real day
    "from=2026-09-10&to=2026-09-10&since=2026-09-01T00:00:00Z",  # two ways at once
])
def test_usage_summary_refuses_a_malformed_range(client, db_path, query):
    r = client.get(f"/usage/summary?{query}")
    assert r.status_code == 400
    assert r.get_json()["error"]


def test_the_price_table_lists_models_with_their_source_and_unpriced_ones(client, db_path):
    _seed_usage(db_path)
    body = client.get("/prices").get_json()
    by_model = {(m["service"], m["model"]): m for m in body["models"]}
    assert by_model[("gemini", "gemini-2.5-flash")]["source"] == "built-in"
    assert by_model[("gemini", "gemini-9-flash")]["source"] is None
    assert body["unpriced"] == [{"service": "gemini", "model": "gemini-9-flash", "calls": 1}]
    assert "input" in body["unit_kinds"]


def test_a_manual_price_fills_in_unpriced_calls_and_can_be_reset(client, db_path):
    _seed_usage(db_path)
    r = client.post("/prices/override", json={"service": "gemini", "model": "gemini-9-flash",
                                              "rates": {"input": 1e-06}})
    assert r.get_json() == {"ok": True, "repriced": 1}
    models = {m["model"]: m for m in client.get("/prices").get_json()["models"]}
    assert models["gemini-9-flash"]["source"] == "manual"
    assert client.get("/prices").get_json()["unpriced"] == []
    assert client.delete("/prices/override?service=gemini&model=gemini-9-flash").status_code == 200
    models = {m["model"]: m for m in client.get("/prices").get_json()["models"]}
    assert models["gemini-9-flash"]["source"] is None


def test_manual_prices_are_validated(client):
    assert client.post("/prices/override", json={"service": "gemini", "model": "m",
                                                 "rates": {"input": -1}}).status_code == 400
    assert client.post("/prices/override", json={"service": "elevenlabs", "model": "m",
                                                 "rates": {"input": 1e-06}}).status_code == 400


def test_sync_now_reports_a_failure_without_raising(client, monkeypatch):
    from tubematic_core import prices as tprices

    def offline(url):
        raise OSError("network unreachable")
    monkeypatch.setattr(tprices, "_fetch_json", offline)
    body = client.post("/prices/sync").get_json()
    assert body["ok"] is False and "unreachable" in body["error"]
    assert "unreachable" in client.get("/prices").get_json()["last_sync_error"]


# ── The poller's no-progress count and stuck flag (TMDEV-129) ───────────────
# The cron poller loops now, so a video the agent cannot move forward would be
# re-dispatched every few minutes. After each session it reports the status
# the session started at; the API alone decides whether that was progress.

def _outcome(client, vid, start_status):
    return client.post(f"/videos/{vid}/agent-outcome", json={"start_status": start_status})


def _progress_row(db_path, vid):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT agent_no_progress_count, agent_stuck_at, updated_at FROM videos "
                      "WHERE id = ?", (vid,)).fetchone()
    con.close()
    return dict(row)


def test_an_unchanged_status_counts_as_no_progress(client, db_path):
    vid = _mk(client, "VOICE_READY")
    r = _outcome(client, vid, "VOICE_READY")
    assert r.status_code == 200
    assert r.get_json() == {"status": "VOICE_READY", "count": 1, "stuck": False,
                            "replayed": False}
    assert _progress_row(db_path, vid)["agent_no_progress_count"] == 1


def test_a_changed_status_is_progress_and_resets_the_count(client, db_path):
    """Changed by anyone — the agent, the render worker or a human — counts:
    the question is whether the video moved, not who moved it."""
    vid = _mk(client, "VOICE_READY")
    _outcome(client, vid, "VOICE_READY")
    _outcome(client, vid, "VOICE_READY")
    r = _outcome(client, vid, "VOICING")
    assert r.get_json() == {"status": "VOICE_READY", "count": 0, "stuck": False,
                            "replayed": False}


def test_the_third_no_progress_session_flags_the_video_stuck_with_a_comment(client, db_path):
    vid = _mk(client, "TOPIC_APPROVED")
    for _ in range(pipeline.AGENT_NO_PROGRESS_CAP - 1):
        assert _outcome(client, vid, "TOPIC_APPROVED").get_json()["stuck"] is False
    r = _outcome(client, vid, "TOPIC_APPROVED").get_json()
    assert r == {"status": "TOPIC_APPROVED", "count": 3, "stuck": True, "replayed": False}
    row = _progress_row(db_path, vid)
    assert row["agent_stuck_at"]
    comments = json.loads(client.get(f"/videos/{vid}").data)["comments"]
    assert len([c for c in comments if "Retry agent" in c["content"]]) == 1
    # Stays at its status: stuck is not FAILED.
    assert json.loads(client.get(f"/videos/{vid}").data)["status"] == "TOPIC_APPROVED"


def test_a_stuck_video_is_commented_on_once(client, db_path):
    vid = _mk(client, "TOPIC_APPROVED")
    for _ in range(5):
        _outcome(client, vid, "TOPIC_APPROVED")
    comments = json.loads(client.get(f"/videos/{vid}").data)["comments"]
    assert len([c for c in comments if "Retry agent" in c["content"]]) == 1


def test_an_outcome_never_touches_updated_at(client, db_path):
    """updated_at is the poller's FIFO key and the stalled-VOICING clock:
    bookkeeping must not reorder the queue or hide a stall."""
    vid = _mk(client, "VOICING")
    before = _progress_row(db_path, vid)["updated_at"]
    time.sleep(1.05)
    _outcome(client, vid, "VOICING")
    assert _progress_row(db_path, vid)["updated_at"] == before


def _keyed(client, vid, start_status, key):
    return client.post(f"/videos/{vid}/agent-outcome",
                       json={"start_status": start_status, "session_key": key}).get_json()


def test_a_replayed_outcome_is_not_counted_twice(client):
    """A successor supervisor finishing a dead one's session re-reports an
    outcome that may already have committed; the session key makes that a
    no-op instead of a second no-progress session."""
    vid = _mk(client, "VOICE_READY")
    assert _keyed(client, vid, "VOICE_READY", "sess-1")["count"] == 1
    again = _keyed(client, vid, "VOICE_READY", "sess-1")
    assert again["count"] == 1 and again["replayed"] is True
    assert _keyed(client, vid, "VOICE_READY", "sess-2")["count"] == 2


def test_a_replay_can_never_flag_a_video_stuck(client, db_path):
    vid = _mk(client, "TOPIC_APPROVED")
    _keyed(client, vid, "TOPIC_APPROVED", "a")
    _keyed(client, vid, "TOPIC_APPROVED", "b")
    for _ in range(3):
        assert _keyed(client, vid, "TOPIC_APPROVED", "b")["stuck"] is False
    assert _progress_row(db_path, vid)["agent_stuck_at"] is None


def test_an_outcome_without_a_key_is_counted_every_time(client):
    vid = _mk(client, "VOICE_READY")
    _keyed(client, vid, "VOICE_READY", "sess-1")
    for expected in (2, 3):
        assert _outcome(client, vid, "VOICE_READY").get_json()["count"] == expected


def test_agent_outcome_validates_its_session_key(client):
    vid = _mk(client, "VOICING")
    for bad in ("", 7, "x" * 101):
        assert client.post(f"/videos/{vid}/agent-outcome",
                           json={"start_status": "VOICING", "session_key": bad}).status_code == 400


def test_agent_outcome_validates_its_input(client):
    vid = _mk(client, "VOICING")
    assert client.post(f"/videos/{vid}/agent-outcome", json={}).status_code == 400
    assert _outcome(client, vid, "NOT_A_STATUS").status_code == 400
    assert _outcome(client, "vid_missing", "VOICING").status_code == 404


def test_workable_videos_leaves_out_a_stuck_video(client, db_path):
    stuck = _mk(client, "VOICE_READY")
    fine = _mk(client, "VOICE_READY")
    for _ in range(pipeline.AGENT_NO_PROGRESS_CAP):
        _outcome(client, stuck, "VOICE_READY")
    ids = [v["id"] for v in json.loads(client.get("/videos/workable").data)]
    assert ids == [fine]


def test_retry_agent_clears_the_flag_and_the_count(client, db_path):
    vid = _mk(client, "VOICE_READY")
    for _ in range(pipeline.AGENT_NO_PROGRESS_CAP):
        _outcome(client, vid, "VOICE_READY")
    r = client.post(f"/videos/{vid}/agent-retry")
    assert r.status_code == 200
    body = r.get_json()
    assert body["agent_stuck_at"] is None and body["agent_no_progress_count"] == 0
    assert vid in [v["id"] for v in json.loads(client.get("/videos/workable").data)]
    assert client.post("/videos/vid_missing/agent-retry").status_code == 404


def test_a_human_status_change_clears_the_flag(client, db_path):
    vid = _mk(client, "REVISION_REQUESTED")
    for _ in range(pipeline.AGENT_NO_PROGRESS_CAP):
        _outcome(client, vid, "REVISION_REQUESTED")
    assert client.patch(f"/videos/{vid}", json={"status": "TOPIC_PROPOSED"}).status_code == 200
    row = _progress_row(db_path, vid)
    assert row["agent_stuck_at"] is None and row["agent_no_progress_count"] == 0


def test_a_patch_without_a_status_leaves_the_flag_alone(client, db_path):
    vid = _mk(client, "VOICE_READY")
    for _ in range(pipeline.AGENT_NO_PROGRESS_CAP):
        _outcome(client, vid, "VOICE_READY")
    assert client.patch(f"/videos/{vid}", json={"title": "renamed"}).status_code == 200
    assert _progress_row(db_path, vid)["agent_stuck_at"] is not None


def test_the_concurrency_and_timeout_settings_have_their_defaults(client):
    s = json.loads(client.get("/settings").data)
    assert s["max_concurrent_agent_sessions"] == 3
    assert s["agent_session_timeout_secs"] == 5400


@pytest.mark.parametrize("key,bad", [
    ("max_concurrent_agent_sessions", 0),
    ("max_concurrent_agent_sessions", pipeline.MAX_CONCURRENT_AGENT_SESSIONS + 1),
    ("agent_session_timeout_secs", 59),
])
def test_the_concurrency_and_timeout_settings_are_bounded(client, key, bad):
    r = client.post("/settings", json={key: bad})
    assert r.status_code == 400
    assert key in json.loads(r.data)["error"]


def test_the_concurrency_and_timeout_settings_accept_their_bounds(client):
    r = client.post("/settings", json={
        "max_concurrent_agent_sessions": 1, "agent_session_timeout_secs": 60})
    assert r.status_code == 200


# ── TMDEV-133: scheduled publishing ──────────────────────────────────────────

from zoneinfo import ZoneInfo  # noqa: E402

_NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _local_in(zone, delta):
    """A wall time `delta` from now in `zone`, as the dialog sends it."""
    return (datetime.now(timezone.utc) + delta).astimezone(ZoneInfo(zone)).strftime(
        "%Y-%m-%dT%H:%M")


def _schedule_ok(client, vid, schedule, accounts=("spc_yt",), post=None):
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post",
                    return_value=post if post is not None else {"id": "sp_1"}) as create:
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": list(accounts), "title": "T", "description": "D",
                              "schedule": schedule})
    return r, create


def _schedule_cols(db_path, vid):
    con = sqlite3.connect(db_path)
    row = con.execute("SELECT scheduled_at, scheduled_timezone FROM videos WHERE id = ?",
                      (vid,)).fetchone()
    con.close()
    return row


# ── resolve_schedule ──

def test_resolve_schedule_converts_the_wall_time_in_the_chosen_zone():
    utc, tz = pipeline.resolve_schedule(
        {"local": "2026-10-01T09:00", "timezone": "Asia/Kolkata"}, _NOW)
    assert (utc, tz) == ("2026-10-01T03:30:00Z", "Asia/Kolkata")


def test_resolve_schedule_accepts_the_legacy_zone_names_browsers_list():
    """The dashboard's zone list comes from the browser, which uses CLDR's
    canonical names — Asia/Calcutta, not Asia/Kolkata."""
    utc, tz = pipeline.resolve_schedule(
        {"local": "2026-10-01T09:00", "timezone": "Asia/Calcutta"}, _NOW)
    assert (utc, tz) == ("2026-10-01T03:30:00Z", "Asia/Calcutta")


def test_resolve_schedule_follows_daylight_saving():
    """New York is UTC-4 in October and UTC-5 in December — a fixed offset
    taken from today would be an hour out on one of them."""
    oct_, _ = pipeline.resolve_schedule(
        {"local": "2026-10-10T09:00", "timezone": "America/New_York"}, _NOW)
    dec_, _ = pipeline.resolve_schedule(
        {"local": "2026-12-10T09:00", "timezone": "America/New_York"}, _NOW)
    assert oct_ == "2026-10-10T13:00:00Z"
    assert dec_ == "2026-12-10T14:00:00Z"


def test_resolve_schedule_refuses_a_time_the_clocks_skip():
    """2:30 on the spring-forward night does not exist in New York. zoneinfo
    still returns a datetime for it, so without the round trip this would
    silently post an hour off."""
    with pytest.raises(ValueError, match="does not exist"):
        pipeline.resolve_schedule(
            {"local": "2027-03-14T02:30", "timezone": "America/New_York"}, _NOW)


def test_resolve_schedule_takes_the_first_of_a_repeated_hour():
    utc, _ = pipeline.resolve_schedule(
        {"local": "2026-11-01T01:30", "timezone": "America/New_York"}, _NOW)
    assert utc == "2026-11-01T05:30:00Z"  # EDT, the first 1:30


def test_resolve_schedule_takes_the_second_of_a_repeated_hour_once_the_first_has_passed():
    """At 01:20 EDT on the fall-back night, "in one hour" is 01:20 EST — the
    same wall time. The first occurrence is now, so the second is the only one
    the human can mean; taking fold=0 regardless refused it as too soon."""
    now = datetime(2026, 11, 1, 5, 20, tzinfo=timezone.utc)   # 01:20 EDT
    utc, _ = pipeline.resolve_schedule(
        {"local": "2026-11-01T01:20", "timezone": "America/New_York"}, now)
    assert utc == "2026-11-01T06:20:00Z"  # 01:20 EST


def test_resolve_schedule_still_refuses_a_repeated_hour_when_both_are_too_soon():
    now = datetime(2026, 11, 1, 6, 18, tzinfo=timezone.utc)   # 01:18 EST
    with pytest.raises(ValueError, match="at least 5 minutes"):
        pipeline.resolve_schedule(
            {"local": "2026-11-01T01:20", "timezone": "America/New_York"}, now)


@pytest.mark.parametrize("schedule,message", [
    ({"local": "2026-10-01T09:00", "timezone": "Mars/Olympus"}, "Unknown timezone"),
    ({"local": "2026-10-01T09:00", "timezone": ""}, "timezone is required"),
    ({"local": "2026-10-01T09:00", "timezone": "../../etc/passwd"}, "Unknown timezone"),
    ({"local": "tomorrow 9am", "timezone": "UTC"}, "YYYY-MM-DDTHH:MM"),
    ({"local": None, "timezone": "UTC"}, "YYYY-MM-DDTHH:MM"),
    ({"local": "2026-09-28T12:04", "timezone": "UTC"}, "at least 5 minutes"),
    ({"local": "2026-09-27T12:00", "timezone": "UTC"}, "at least 5 minutes"),
    ({"local": "2027-09-29T12:00", "timezone": "UTC"}, "at most 365 days"),
    ({"local": "0001-01-01T00:00", "timezone": "Asia/Tokyo"}, "out of range"),
    ("2026-10-01T09:00", "must be an object"),
])
def test_resolve_schedule_refuses_bad_input(schedule, message):
    with pytest.raises(ValueError, match=message):
        pipeline.resolve_schedule(schedule, _NOW)


def test_resolve_schedule_accepts_exactly_the_floor():
    utc, _ = pipeline.resolve_schedule({"local": "2026-09-28T12:05", "timezone": "UTC"}, _NOW)
    assert utc == "2026-09-28T12:05:00Z"


# ── scheduling through the publish route ──

def test_scheduling_holds_the_post_and_moves_the_video_to_scheduled(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    local = _local_in("Asia/Kolkata", timedelta(days=2))
    r, create = _schedule_ok(client, vid, {"local": local, "timezone": "Asia/Kolkata"})
    assert r.status_code == 201
    body = json.loads(r.data)
    assert body["status"] == "SCHEDULED"
    assert body["scheduled_timezone"] == "Asia/Kolkata"

    expected = datetime.strptime(local, "%Y-%m-%dT%H:%M").replace(
        tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert create.call_args.kwargs["scheduled_at"] == expected
    assert body["scheduled_at"] == expected
    assert _status(db_path, vid) == "SCHEDULED"
    assert _schedule_cols(db_path, vid) == (expected, "Asia/Kolkata")
    assert [(p["postforme_post_id"], p["status"]) for p in _pubs(db_path, vid)] == \
        [("sp_1", "PENDING")]
    assert any("Scheduled to post" in c and "Asia/Kolkata" in c
               for c in _comments(db_path, vid))


def test_publish_now_sends_no_schedule(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    return_value={"upload_url": "https://u", "media_url": "https://m"}), \
         mock.patch("postforme.upload_media"), \
         mock.patch("postforme.create_post", return_value={"id": "sp_1"}) as create:
        client.post(f"/videos/{vid}/publish",
                    json={"account_ids": ["spc_yt"], "title": "T", "description": "D"})
    assert create.call_args.kwargs["scheduled_at"] is None
    assert _status(db_path, vid) == "PUBLISHING"
    assert _schedule_cols(db_path, vid) == ("", "")


def test_a_bad_schedule_is_a_400_that_changes_nothing(client, db_path, rendered):
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    r, create = _schedule_ok(client, vid, {"local": "2020-01-01T09:00", "timezone": "UTC"})
    assert r.status_code == 400
    assert "at least 5 minutes" in json.loads(r.data)["error"]
    create.assert_not_called()
    assert _status(db_path, vid) == "VIDEO_APPROVED"
    assert _pubs(db_path, vid) == []


def test_a_failed_upload_clears_the_schedule(client, db_path, rendered):
    """Released to VIDEO_APPROVED with no schedule left behind — a stale
    scheduled_at on an approved video would be shown as a time it is not
    going out at."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.list_accounts", return_value=PFM_ACCOUNTS), \
         mock.patch("postforme.create_upload_url",
                    side_effect=pfm.PostformeError("upload url refused")):
        r = client.post(f"/videos/{vid}/publish",
                        json={"account_ids": ["spc_yt"], "title": "T", "description": "D",
                              "schedule": {"local": _local_in("UTC", timedelta(days=1)),
                                           "timezone": "UTC"}})
    assert r.status_code == 502
    assert _status(db_path, vid) == "VIDEO_APPROVED"
    assert _schedule_cols(db_path, vid) == ("", "")


def test_a_schedule_that_arrives_during_the_upload_posts_now(client, db_path, rendered, monkeypatch):
    """postforme refuses a scheduled_at in the past, and the publish path
    would have to read that refusal as ambiguous. A time that has all but
    arrived is simply sent as a publish-now."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    monkeypatch.setattr(pipeline, "SCHEDULE_POST_NOW_SECS", 10 * 60)
    r, create = _schedule_ok(client, vid, {"local": _local_in("UTC", timedelta(minutes=8)),
                                           "timezone": "UTC"})
    assert r.status_code == 201
    assert create.call_args.kwargs["scheduled_at"] is None
    assert json.loads(r.data)["status"] == "PUBLISHING"
    assert _status(db_path, vid) == "PUBLISHING"


def test_a_scheduled_post_with_no_id_is_left_for_the_worker(client, db_path, rendered):
    """With no post id the rows stay in flight and the worker adopts the post
    by external_id — it is the worker that then moves the video to SCHEDULED."""
    _enable_publishing(db_path)
    _allow(db_path, ["spc_yt"])
    vid = _approved_video(db_path)
    r, _ = _schedule_ok(client, vid, {"local": _local_in("UTC", timedelta(days=1)),
                                      "timezone": "UTC"}, post={})
    assert r.status_code == 201
    assert _status(db_path, vid) == "PUBLISHING"
    assert _schedule_cols(db_path, vid)[0] != ""


def test_a_scheduled_video_cannot_be_deleted(client, db_path):
    vid = _approved_video(db_path, status="SCHEDULED")
    r = client.delete(f"/videos/{vid}")
    assert r.status_code == 409
    assert _status(db_path, vid) == "SCHEDULED"


def test_retry_republish_clears_a_stale_schedule(client, db_path):
    _enable_publishing(db_path)
    vid = _failed_publish(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET scheduled_at = '2026-01-01T00:00:00Z',"
                " scheduled_timezone = 'UTC' WHERE id = ?", (vid,))
    con.commit()
    con.close()
    with mock.patch("postforme.find_post_by_external_id", return_value=None):
        client.post(f"/videos/{vid}/publish/retry")
    assert _schedule_cols(db_path, vid) == ("", "")


# ── cancel ──

def _scheduled_video(db_path, vid="vid_pub", status="SCHEDULED", post_id="sp_1"):
    _approved_video(db_path, vid=vid, status=status)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET scheduled_at = '2026-10-01T03:30:00Z',"
                " scheduled_timezone = 'Asia/Kolkata' WHERE id = ?", (vid,))
    con.execute(
        "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
        " postforme_post_id, status, created_at, updated_at)"
        " VALUES (?, ?, 'youtube', 'spc_yt', ?, 'PENDING', 'n', 'n')",
        (f"{vid}-row", vid, post_id))
    con.commit()
    con.close()
    return vid


def test_cancel_deletes_the_post_and_returns_the_video_to_approved(client, db_path):
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path)
    with mock.patch("postforme.delete_post") as delete:
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 200
    assert delete.call_args.kwargs["post_id"] == "sp_1"
    assert _status(db_path, vid) == "VIDEO_APPROVED"
    assert _schedule_cols(db_path, vid) == ("", "")
    assert _pubs(db_path, vid) == []
    assert any("cancelled" in c for c in _comments(db_path, vid))


def test_cancel_needs_a_scheduled_video(client, db_path):
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path, status="PUBLISHING")
    with mock.patch("postforme.delete_post") as delete:
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 409
    delete.assert_not_called()


def test_cancel_is_unavailable_while_publishing_is_off(client, db_path):
    vid = _scheduled_video(db_path)
    assert client.post(f"/videos/{vid}/schedule/cancel").status_code == 503


def test_cancel_after_the_post_started_going_out_is_refused(client, db_path):
    """postforme's 400 means the post already left `scheduled`. The rows must
    stay — they are what settles it as published or failed."""
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.delete_post",
                    side_effect=pfm.PostformeError("Can only delete scheduled", 400)):
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 409
    assert "can no longer be cancelled" in json.loads(r.data)["error"]
    assert _status(db_path, vid) == "SCHEDULED"
    assert len(_pubs(db_path, vid)) == 1


def test_a_failed_cancel_leaves_the_schedule_to_try_again(client, db_path):
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.delete_post", side_effect=pfm.PostformeError("timeout")):
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 502
    assert _status(db_path, vid) == "SCHEDULED"
    assert _schedule_cols(db_path, vid)[0] != ""
    assert len(_pubs(db_path, vid)) == 1


def test_a_repeated_cancel_after_a_bad_answer_releases_the_video(client, db_path):
    """The first DELETE removed the post but answered 500 (postforme fires its
    webhook after deleting). The retry gets 404, the post is confirmed gone,
    and the video is released."""
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.delete_post",
                    side_effect=pfm.PostformeError("Post not found", 404)), \
         mock.patch("postforme.find_post_by_external_id", return_value=None):
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 200
    assert _status(db_path, vid) == "VIDEO_APPROVED"


def test_a_404_for_a_post_that_still_exists_does_not_release(client, db_path):
    """postforme also answers 404 when its own lookup fails. If the post is
    still listed, releasing would strand a post that will go out."""
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path)
    import postforme as pfm
    with mock.patch("postforme.delete_post",
                    side_effect=pfm.PostformeError("Post not found", 404)), \
         mock.patch("postforme.find_post_by_external_id",
                    return_value={"id": "sp_1", "live": True}):
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 502
    assert _status(db_path, vid) == "SCHEDULED"


def test_cancel_still_releases_a_video_the_worker_moved_on_meanwhile(client, db_path):
    """The worker moves a due video to PUBLISHING. If that lands while the
    DELETE is in flight and postforme still deleted the post, nothing will go
    out — the video must not be left PUBLISHING to fail at the deadline."""
    _enable_publishing(db_path)
    vid = _scheduled_video(db_path)

    def worker_flips(api_key, *, post_id, base_url=None):
        con = sqlite3.connect(db_path)
        con.execute("UPDATE videos SET status = 'PUBLISHING' WHERE id = ?", (vid,))
        con.commit()
        con.close()

    with mock.patch("postforme.delete_post", side_effect=worker_flips):
        r = client.post(f"/videos/{vid}/schedule/cancel")
    assert r.status_code == 200
    assert _status(db_path, vid) == "VIDEO_APPROVED"
    assert _pubs(db_path, vid) == []
