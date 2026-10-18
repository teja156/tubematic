"""Metric snapshot capture for published videos (TMDEV-83).

Shared by the render worker (hourly pass) and the Flask API (the dashboard's
Refresh buttons), which live in different containers — so this takes `db_path`
and `api_key` as arguments the way db.py does, rather than reaching for either.

**Per account, not per publication.** The obvious shape is one
`get_account_feed` call per publication, filtered to its post id, and that is
what this did first. It does not survive contact with the rate limit: postforme
allows 5 requests/second, so a library with more than a handful of published
targets fires 429s that get caught and skipped, losing snapshots permanently —
`video_metrics` is a time series and a missed reading cannot be backfilled.

One account's feed carries every post on that account with metrics attached, so
walking it costs `N_accounts` calls plus pagination regardless of how many
videos have been published. Two accounts stays two calls whether the library
holds ten videos or ten thousand.
"""
import json

import db
import postforme

# Feed pages are capped by postforme per platform, so this is a request rather
# than a guarantee — pagination below does not assume it was honoured.
_PAGE_SIZE = 100
# A runaway cursor (a feed that never reports has_more=False) would otherwise
# spin forever inside a worker loop that also has renders to claim.
_MAX_PAGES = 20


def _publications(con):
    return [dict(r) for r in con.execute(
        "SELECT * FROM video_publications WHERE status = 'PUBLISHED'"
        " AND postforme_post_id != ''")]


def _match(entry: dict, pubs: list) -> dict | None:
    """Find the publication an account-feed entry belongs to.

    Matched on postforme's own post id rather than the platform URL: one
    `POST /social-posts` spans every target of a publish, so all of a video's
    publications share that id, and the caller has already narrowed `pubs` to a
    single account. URL matching would be fragile — platforms rewrite them.
    """
    post_id = entry.get("social_post_id") or entry.get("external_post_id")
    if not post_id:
        return None
    for pub in pubs:
        if pub["postforme_post_id"] == post_id:
            return pub
    return None


def poll(db_path: str, api_key: str) -> dict:
    """Walk each relevant account's feed and append a snapshot per match.

    Returns {"accounts": n, "snapshots": n, "errors": n}. Never raises: one
    unreachable account must not blind every other account's metrics, and this
    runs both inside a worker loop that has renders to get back to and behind a
    dashboard button that should report partial success rather than fail.
    """
    with db.conn(db_path) as con:
        pubs = _publications(con)
    if not pubs:
        return {"accounts": 0, "snapshots": 0, "errors": 0}

    by_account: dict = {}
    for pub in pubs:
        by_account.setdefault(pub["social_account_id"], []).append(pub)

    snapshots = errors = 0
    for account_id, account_pubs in by_account.items():
        cursor = None
        for _ in range(_MAX_PAGES):
            try:
                feed = postforme.get_account_feed(
                    api_key, social_account_id=account_id,
                    limit=_PAGE_SIZE, cursor=cursor)
            except Exception:
                errors += 1
                break

            for entry in feed.get("data") or []:
                pub = _match(entry, account_pubs)
                if pub is None:
                    continue    # someone else's post on the same account
                snapshots += _write(db_path, pub, entry.get("metrics") or {})

            meta = feed.get("meta") or {}
            # The live response carries `next` + `has_more`; the swagger
            # describes `cursor`. Accept either rather than betting on one.
            cursor = meta.get("next") or meta.get("cursor")
            if not cursor or meta.get("has_more") is False:
                break

    return {"accounts": len(by_account), "snapshots": snapshots, "errors": errors}


def _write(db_path: str, pub: dict, raw: dict) -> int:
    """Append one snapshot. Returns 1 so callers can total them."""
    common = postforme.extract_metrics(pub["platform"], raw)
    with db.conn(db_path) as con:
        con.execute(
            "INSERT INTO video_metrics (publication_id, fetched_at, views, likes,"
            " comments, shares, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pub["id"], db._now(), common["views"], common["likes"],
             common["comments"], common["shares"], json.dumps(raw)))
    return 1
