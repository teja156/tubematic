"""Tests for the short display name (videos.title) and its length cap.

A video carries two text fields: `topic`, the full descriptive brief the
producibility score is about, and `title`, a short headline capped at
VIDEO_TITLE_MAX_LEN that dashboard cards render. The two write paths treat an
over-length title differently on purpose — create clips, update rejects — so
a research run is never lost to a cosmetic field while a deliberate edit still
gets told it was wrong.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

from datetime import datetime, timezone

import pytest

import server


CAP = server.VIDEO_TITLE_MAX_LEN


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    with server._conn() as con:
        con.execute(
            "INSERT INTO projects (id, name, status, created_at) "
            "VALUES ('proj-1', 'Domain', 'active', ?)",
            (_now(),),
        )
    return tmp_path / "test.db"


def _create(**kw):
    args = {
        "project_id": "proj-1",
        "topic": "The full descriptive brief, at whatever length the idea needs.",
        "strategy": "manual",
        "producibility_score": 7,
    }
    args.update(kw)
    return server.create_video(**args)


def _stored_title(video_id: str) -> str:
    with server._conn() as con:
        return con.execute(
            "SELECT title FROM videos WHERE id = ?", (video_id,)
        ).fetchone()["title"]


def _set_status(video_id: str, status: str) -> None:
    with server._conn() as con:
        con.execute("UPDATE videos SET status = ? WHERE id = ?", (status, video_id))


# ── _truncate_title ───────────────────────────────────────────────────────────

def test_a_title_within_the_cap_is_returned_untouched():
    title = "How a TLS handshake negotiates an encrypted connection"
    assert server._truncate_title(title) == (title, "")


def test_a_title_exactly_at_the_cap_is_not_clipped():
    title = "x" * CAP
    assert server._truncate_title(title) == (title, "")


def test_an_over_length_title_is_cut_at_a_word_boundary():
    title = "How Chromium's renderer sandbox keeps untrusted JavaScript away from your filesystem"
    cut, warning = server._truncate_title(title)
    assert len(cut) <= CAP
    assert warning
    # Cut on whitespace, so the result never ends mid-word.
    assert title.startswith(cut)
    assert title[len(cut)] == " "


def test_a_single_long_token_is_hard_cut_rather_than_emptied():
    title = "x" * (CAP + 40)
    cut, warning = server._truncate_title(title)
    assert cut == "x" * CAP
    assert warning


def test_no_ellipsis_is_appended():
    """A clipped name must not look like corrupted data — the full text is in topic."""
    cut, _ = server._truncate_title("word " * 40)
    assert "…" not in cut and "..." not in cut


# ── create_video: clip, don't reject ─────────────────────────────────────────

def test_create_video_stores_a_short_title_unchanged(db):
    out = _create(title="How TLS negotiates a session key")
    assert "error" not in out
    assert "warning" not in out
    assert _stored_title(out["video_id"]) == "How TLS negotiates a session key"


def test_create_video_clips_an_over_length_title_and_warns(db):
    long_title = "How Chromium's renderer sandbox keeps untrusted JavaScript away from your filesystem"
    out = _create(title=long_title)
    assert "error" not in out, "create must not fail on a cosmetic field mid-research-run"
    assert len(_stored_title(out["video_id"])) <= CAP
    assert "warning" in out
    assert str(CAP) in out["warning"]


def test_create_video_leaves_the_topic_whole_when_the_title_is_clipped(db):
    topic = "A brief that runs well past seventy characters. " * 20
    out = _create(topic=topic, title="x" * (CAP + 10))
    with server._conn() as con:
        assert con.execute(
            "SELECT topic FROM videos WHERE id = ?", (out["video_id"],)
        ).fetchone()["topic"] == topic


def test_create_video_defaults_the_title_to_blank(db):
    """Left blank the dashboard falls back to the topic — no title is not an error."""
    out = _create()
    assert "warning" not in out
    assert _stored_title(out["video_id"]) == ""


# ── update_video: reject, don't clip ─────────────────────────────────────────

def test_update_video_accepts_a_title_within_the_cap(db):
    out = _create()
    assert "error" not in server.update_video(out["video_id"], title="A short name")
    assert _stored_title(out["video_id"]) == "A short name"


def test_update_video_rejects_an_over_length_title(db):
    out = _create()
    res = server.update_video(out["video_id"], title="x" * (CAP + 1))
    assert "error" in res
    assert str(CAP) in res["error"]


def test_a_rejected_update_writes_nothing(db):
    out = _create(title="Original name")
    server.update_video(out["video_id"], title="x" * (CAP + 1))
    assert _stored_title(out["video_id"]) == "Original name"


def test_the_title_is_not_frozen_after_the_topic_checkpoint(db):
    """Unlike script_profile_id and agent_model, a title is cosmetic and stays editable.

    Those two are locked once the video leaves TOPIC_PROPOSED because they change
    what gets produced and paid for. A display name changes neither.
    """
    out = _create()
    for status in ("TOPIC_APPROVED", "VOICE_READY", "VIDEO_READY"):
        _set_status(out["video_id"], status)
        res = server.update_video(out["video_id"], title=f"Renamed at {status}")
        assert "error" not in res, f"title write rejected at {status}: {res}"
        assert _stored_title(out["video_id"]) == f"Renamed at {status}"


def test_the_cap_matches_the_flask_copy():
    """Both processes carry their own constant behind a 'Keep in sync' comment."""
    import pathlib
    import re

    src = (pathlib.Path(__file__).resolve().parents[2]
           / "renderer" / "api" / "pipeline.py").read_text()
    match = re.search(r"^VIDEO_TITLE_MAX_LEN = (\d+)$", src, re.M)
    assert match, "renderer/api/pipeline.py no longer defines VIDEO_TITLE_MAX_LEN"
    assert int(match.group(1)) == CAP
