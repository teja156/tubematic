"""Tests for metrics.py — the per-account snapshot pass (TMDEV-83).

The shape being defended: one feed call per ACCOUNT, not per publication.
postforme allows 5 requests/second (measured — it appears only in a response
header, never in the swagger), so a per-publication pass over a real library
fires 429s that get caught and skipped. Because video_metrics is a time series,
a skipped reading is not retried later, it is simply never recorded.

Run from renderer/api/: pytest tests/test_metrics.py
"""
import json
import os
import sqlite3
import unittest.mock as mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import metrics
import pipeline as pipeline_module
import postforme


@pytest.fixture
def db_path(tmp_path):
    p = str(tmp_path / "metrics.db")
    pipeline_module._init_db(p)
    con = sqlite3.connect(p)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('p','P','now')")
    con.commit()
    con.close()
    return p


def _publish(db_path, *, video_id, account, post_id="sp_1", platform="youtube",
             status="PUBLISHED"):
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT OR IGNORE INTO videos (id, project_id, topic, strategy, status,"
        " created_at, updated_at) VALUES (?, 'p', 'T', 'manual', 'PUBLISHED', 'n', 'n')",
        (video_id,))
    con.execute(
        "INSERT INTO video_publications (id, video_id, platform, social_account_id,"
        " postforme_post_id, status, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'n', 'n')",
        (f"{video_id}-{account}", video_id, platform, account, post_id, status))
    con.commit()
    con.close()


def _rows(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out = [dict(r) for r in con.execute("SELECT * FROM video_metrics ORDER BY id")]
    con.close()
    return out


def _entry(post_id="sp_1", platform="youtube", **m):
    return {"platform": platform, "social_post_id": post_id,
            "metrics": m or {"views": 1}}


def _feed(entries, *, has_more=False, nxt=None):
    return {"data": entries, "meta": {"has_more": has_more, "next": nxt}}


# ── the per-account shape ────────────────────────────────────────────────────

def test_one_call_per_account_regardless_of_how_many_videos(db_path):
    for i in range(6):
        _publish(db_path, video_id=f"vid-{i}", account="spc_yt", post_id=f"sp_{i}")
    entries = [_entry(post_id=f"sp_{i}", views=i) for i in range(6)]
    with mock.patch("postforme.get_account_feed", return_value=_feed(entries)) as call:
        result = metrics.poll(db_path, "key")
    assert call.call_count == 1
    assert result == {"accounts": 1, "snapshots": 6, "errors": 0}


def test_each_account_is_walked_separately(db_path):
    _publish(db_path, video_id="vid-a", account="spc_a")
    _publish(db_path, video_id="vid-b", account="spc_b")
    with mock.patch("postforme.get_account_feed",
                    return_value=_feed([_entry()])) as call:
        metrics.poll(db_path, "key")
    assert call.call_count == 2


def test_nothing_published_means_no_calls_at_all(db_path):
    with mock.patch("postforme.get_account_feed") as call:
        assert metrics.poll(db_path, "key") == {"accounts": 0, "snapshots": 0, "errors": 0}
    call.assert_not_called()


def test_a_pending_or_failed_target_is_not_polled(db_path):
    _publish(db_path, video_id="vid-a", account="spc_a", status="PENDING")
    _publish(db_path, video_id="vid-b", account="spc_b", status="FAILED")
    with mock.patch("postforme.get_account_feed") as call:
        metrics.poll(db_path, "key")
    call.assert_not_called()


# ── matching ────────────────────────────────────────────────────────────────

def test_someone_elses_post_on_the_same_account_is_ignored(db_path):
    """The feed carries every post on the account, not only ours — that is the
    cost of the per-account shape and it must not become a data bug."""
    _publish(db_path, video_id="vid-a", account="spc_yt", post_id="sp_ours")
    feed = _feed([_entry(post_id="sp_theirs", views=999), _entry(post_id="sp_ours", views=7)])
    with mock.patch("postforme.get_account_feed", return_value=feed):
        metrics.poll(db_path, "key")
    rows = _rows(db_path)
    assert len(rows) == 1
    assert rows[0]["views"] == 7


def test_an_entry_with_no_post_id_is_skipped_rather_than_guessed_at(db_path):
    _publish(db_path, video_id="vid-a", account="spc_yt")
    with mock.patch("postforme.get_account_feed",
                    return_value=_feed([{"platform": "youtube", "metrics": {"views": 3}}])):
        metrics.poll(db_path, "key")
    assert _rows(db_path) == []


def test_external_post_id_is_accepted_as_a_fallback_identifier(db_path):
    _publish(db_path, video_id="vid-a", account="spc_yt", post_id="sp_1")
    entry = {"platform": "youtube", "external_post_id": "sp_1", "metrics": {"views": 4}}
    with mock.patch("postforme.get_account_feed", return_value=_feed([entry])):
        metrics.poll(db_path, "key")
    assert _rows(db_path)[0]["views"] == 4


# ── pagination ──────────────────────────────────────────────────────────────

def test_pagination_follows_the_cursor_until_the_feed_says_stop(db_path):
    _publish(db_path, video_id="vid-a", account="spc_yt", post_id="sp_1")
    _publish(db_path, video_id="vid-b", account="spc_yt", post_id="sp_2")
    pages = [
        _feed([_entry(post_id="sp_1", views=1)], has_more=True, nxt="page2"),
        _feed([_entry(post_id="sp_2", views=2)]),
    ]
    with mock.patch("postforme.get_account_feed", side_effect=pages) as call:
        metrics.poll(db_path, "key")
    assert call.call_count == 2
    assert call.call_args_list[1].kwargs["cursor"] == "page2"
    assert sorted(r["views"] for r in _rows(db_path)) == [1, 2]


def test_pagination_is_bounded_so_a_runaway_cursor_cannot_spin_forever(db_path):
    """This runs inside the worker loop, which has renders to get back to."""
    _publish(db_path, video_id="vid-a", account="spc_yt")
    endless = _feed([], has_more=True, nxt="always-another")
    with mock.patch("postforme.get_account_feed", return_value=endless) as call:
        metrics.poll(db_path, "key")
    assert call.call_count == metrics._MAX_PAGES


def test_a_page_that_reports_no_more_stops_even_with_a_cursor_present(db_path):
    _publish(db_path, video_id="vid-a", account="spc_yt")
    with mock.patch("postforme.get_account_feed",
                    return_value=_feed([_entry()], has_more=False, nxt="ignored")) as call:
        metrics.poll(db_path, "key")
    assert call.call_count == 1


# ── failure isolation ───────────────────────────────────────────────────────

def test_one_unreachable_account_does_not_stop_the_others(db_path):
    _publish(db_path, video_id="vid-a", account="spc_a")
    _publish(db_path, video_id="vid-b", account="spc_b")
    with mock.patch("postforme.get_account_feed",
                    side_effect=[postforme.PostformeError("boom"), _feed([_entry()])]):
        result = metrics.poll(db_path, "key")
    assert result["errors"] == 1
    assert result["snapshots"] == 1


def test_poll_never_raises_even_when_everything_fails(db_path):
    """It runs both inside a worker loop and behind a dashboard button; neither
    wants an exception, both want a count."""
    _publish(db_path, video_id="vid-a", account="spc_a")
    with mock.patch("postforme.get_account_feed", side_effect=RuntimeError("unexpected")):
        assert metrics.poll(db_path, "key")["errors"] == 1


def test_snapshots_append_rather_than_replace(db_path):
    _publish(db_path, video_id="vid-a", account="spc_yt")
    with mock.patch("postforme.get_account_feed",
                    return_value=_feed([_entry(views=1)])):
        metrics.poll(db_path, "key")
        metrics.poll(db_path, "key")
    assert len(_rows(db_path)) == 2


def test_the_whole_platform_payload_is_kept_not_just_the_columns(db_path):
    """raw_json is what makes a metric we did not model recoverable later —
    unlike the readings themselves, which cannot be backfilled."""
    _publish(db_path, video_id="vid-a", account="spc_yt")
    entry = _entry(views=10, estimatedMinutesWatched=42)
    with mock.patch("postforme.get_account_feed", return_value=_feed([entry])):
        metrics.poll(db_path, "key")
    assert json.loads(_rows(db_path)[0]["raw_json"])["estimatedMinutesWatched"] == 42
