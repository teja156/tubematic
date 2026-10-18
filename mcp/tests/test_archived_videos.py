"""Archived videos (TMDEV-84) are invisible to the agent.

Their files are gone, so there is nothing to work on; and the counts feed the
same decisions poll.py makes over HTTP from the Flask copies of these queries.
"""
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()

    def make(video_id, status, archived_at=None):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, topic, status, archived_at, created_at, updated_at)"
                " VALUES (?, 'topic', ?, ?, ?, ?)",
                (video_id, status, archived_at, _now(), _now()))

    return make


def test_list_videos_omits_archived_rows(make_video):
    make_video("live", "TOPIC_APPROVED")
    make_video("gone", "TOPIC_APPROVED", archived_at=_now())
    assert [v["id"] for v in server.list_videos()] == ["live"]
    assert [v["id"] for v in server.list_videos(status="TOPIC_APPROVED")] == ["live"]


def test_pipeline_status_counts_omit_archived_rows(make_video):
    make_video("live", "TOPIC_PROPOSED")
    make_video("gone", "TOPIC_PROPOSED", archived_at=_now())
    make_video("gone2", "VOICE_READY", archived_at=_now())
    status = server.get_pipeline_status()
    assert status["video_counts"] == {"TOPIC_PROPOSED": 1}
    assert status["workable_count"] == 0


def test_an_archived_video_is_still_readable_by_id(make_video):
    make_video("gone", "PUBLISHED", archived_at=_now())
    assert server.get_video("gone")["archived_at"]


# ── writes: an archived row is frozen ────────────────────────────────────────
# The stale-id window: poll.py fetched /videos/workable, then a human deleted
# the video before the agent acted on it. Listing filters cannot help there —
# the agent already holds the id — so the write tools have to refuse.

def _status(video_id):
    with server._conn() as con:
        return con.execute("SELECT status FROM videos WHERE id = ?", (video_id,)).fetchone()["status"]


@pytest.mark.parametrize("only_if", [None, "TOPIC_APPROVED"])
def test_set_video_status_refuses_an_archived_video(make_video, only_if):
    make_video("gone", "TOPIC_APPROVED", archived_at=_now())
    out = server.set_video_status("gone", "SCRIPT_READY", only_if_current_status=only_if)
    assert out["error"] == "video_archived"
    assert _status("gone") == "TOPIC_APPROVED"


@pytest.mark.parametrize("target", ["VOICING", "RENDER_QUEUED"])
def test_an_archived_video_cannot_be_pushed_to_a_spend_status(make_video, target):
    """VOICING unlocks generate_voice; RENDER_QUEUED makes the worker render
    files that were deleted."""
    make_video("gone", "SCRIPT_READY", archived_at=_now())
    assert server.set_video_status("gone", target)["error"] == "video_archived"
    assert _status("gone") == "SCRIPT_READY"


def test_update_video_refuses_an_archived_video(make_video):
    make_video("gone", "TOPIC_APPROVED", archived_at=_now())
    out = server.update_video("gone", title="new name")
    assert out["error"] == "video_archived"
    with server._conn() as con:
        assert con.execute("SELECT title FROM videos WHERE id = 'gone'").fetchone()["title"] == ""


def test_live_videos_are_still_writable(make_video):
    make_video("live", "TOPIC_APPROVED")
    assert server.set_video_status("live", "SCRIPT_READY", "TOPIC_APPROVED")["status"] == "SCRIPT_READY"
    assert server.update_video("live", title="ok")["updated_fields"] == ["title"]
