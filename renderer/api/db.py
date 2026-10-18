"""Shared DB helpers for renderer/api.

Designed to be safe from background threads (no Flask app context required).
All functions accept db_path explicitly so they work with any DB location.
"""
import sqlite3
import time
from contextlib import contextmanager


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextmanager
def conn(db_path: str):
    """Connect to SQLite at db_path with WAL + foreign_keys, row_factory=sqlite3.Row.
    Commits on success, rolls back on exception, always closes.
    """
    import pathlib
    pathlib.Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def set_status(db_path: str, video_id: str, new_status: str, only_if: str | None = None) -> bool:
    """Atomically UPDATE videos.status, optionally guarded by only_if.

    If only_if is given, the guard is expressed in the UPDATE's own WHERE
    clause (not a separate SELECT-then-compare beforehand), so the
    check-and-set is a single atomic statement — closes the TOCTOU window a
    SELECT-then-UPDATE pattern would leave open. Returns True on a successful
    update (video exists, and — if only_if was given — its status matched),
    False if no-op.
    """
    with conn(db_path) as con:
        if only_if is not None:
            cur = con.execute(
                "UPDATE videos SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
                (new_status, _now(), video_id, only_if),
            )
        else:
            cur = con.execute(
                "UPDATE videos SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, _now(), video_id),
            )
    return cur.rowcount > 0


def update_fields(db_path: str, video_id: str, **kwargs) -> None:
    """UPDATE videos SET col=? for each kwarg, always setting updated_at=now()."""
    kwargs["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    with conn(db_path) as con:
        con.execute(
            f"UPDATE videos SET {set_clause} WHERE id = ?",
            list(kwargs.values()) + [video_id],
        )


def add_comment(db_path: str, video_id: str, author: str, text: str) -> None:
    """INSERT a comment row. author must be 'agent' for server-side writes."""
    with conn(db_path) as con:
        con.execute(
            "INSERT INTO comments (video_id, author, content, created_at) VALUES (?, ?, ?, ?)",
            (video_id, author, text, _now()),
        )
