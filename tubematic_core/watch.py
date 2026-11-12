"""What viewers did with a published video, and what an install learns from it.

The API process (the Analytics page, the metrics poll) and the MCP server
(formula routing) both read the figures, so the reader, the group rule and the
learning rule live here once and neither process holds a copy of its own.

Read from a snapshot's stored payload (`video_metrics.raw_json`), never from
columns: the payload is kept whole, so a corrected mapping applies to every
snapshot ever taken.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tubematic_core import formulas as tformulas


# ── Reading a payload ────────────────────────────────────────────────────────

# Per-platform metric names for the common subset stored as columns. Everything
# else lives in video_metrics.raw_json — aggregating "views" across platforms is
# defensible, summing platform-specific metrics is not.
#
# Facebook is the awkward one and the reason this is a table rather than a
# straight-through copy: it has no `likes` (reactions_total is the nearest
# equivalent) and no `views` (video_views, falling back to media_views).
_METRIC_FIELDS = {
    "youtube":   {"views": ("views",), "likes": ("likes",),
                  "comments": ("comments",), "shares": ("shares",)},
    "instagram": {"views": ("views",), "likes": ("likes",),
                  "comments": ("comments",), "shares": ("shares",)},
    "tiktok":    {"views": ("view_count",), "likes": ("like_count",),
                  "comments": ("comment_count",), "shares": ("share_count",)},
    "facebook":  {"views": ("video_views", "media_views"), "likes": ("reactions_total",),
                  "comments": ("comments",), "shares": ("shares",)},
}

METRIC_COLUMNS = ("views", "likes", "comments", "shares")


def extract_metrics(platform: str, metrics: dict | None) -> dict:
    """Map a platform's metrics payload onto the common subset.

    A metric that is absent comes back None, not 0 — "not reported" and
    "reported as zero" are different claims, and a chart that reads a missing
    value as a real zero is lying about the data.

    An unrecognised platform yields all-None rather than raising: a new
    platform appearing upstream must not break the metrics poll for every other
    publication in the same pass.
    """
    fields = _METRIC_FIELDS.get(platform, {})
    metrics = metrics or {}
    out = {}
    for column in METRIC_COLUMNS:
        value = None
        for name in fields.get(column, ()):
            if metrics.get(name) is not None:
                value = metrics[name]
                break
        out[column] = value
    return out


# How long people watched (TMDEV-212). Read from a snapshot's stored payload
# when a page asks, never copied into columns: the payload is already kept
# whole, so every snapshot ever taken is covered and a corrected mapping
# applies to all of them.
#
# Each entry is (payload key, divisor that turns it into the unit named).
# A measure a platform does not report has no entry and reads None. TikTok's
# consumer connection reports counts only, so it has none at all. Facebook's
# names are from postforme's API reference.
_RETENTION_FIELDS = {
    "youtube":   {"avg_watch_secs": ("averageViewDuration", 1),
                  "watched_pct": ("averageViewPercentage", 1),
                  "engaged_views": ("engagedViews", 1)},
    "instagram": {"avg_watch_secs": ("ig_reels_avg_watch_time", 1000),
                  "reach": ("reach", 1), "saves": ("saved", 1)},
    "facebook":  {"avg_watch_secs": ("video_avg_time_watched", 1000),
                  "length_secs": ("video_length", 1000),
                  "reach": ("reach", 1)},
    "tiktok":    {},
}

RETENTION_KEYS = ("avg_watch_secs", "watched_pct", "stayed_pct", "engaged_views", "reach", "saves")

# No platform counts this many of anything. Past it a value is damage, and an
# integer that large cannot be divided into a float at all.
_MAX_READING = 1e15


def _number(value):
    """A reported figure, or None. A bool is a number to Python, a negative
    count is not a reading and neither is an absurdly large one, so none of
    them passes."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value < 0 or value > _MAX_READING:
        return None
    return value


def extract_retention(platform: str, metrics: dict | None, duration_secs=None) -> dict:
    """Watch figures from one platform payload: seconds watched, the share of
    the video watched (percent), the share of views that stayed to watch
    (percent), engaged views, reach and saves.

    Same contract as extract_metrics: an absent figure is None, never 0, and
    an unknown platform is all None. Never raises, whatever the payload holds.

    A 0 share is None as well, and so is an average of 0 seconds that comes
    with no share of the platform's own. Nobody watches for no time: a
    platform sends 0 for a post it has not measured yet, and a 0 would count
    in a group's median as a video nobody stayed on. Both are judged as the
    page shows them, to one decimal, so 30 ms is no seconds whatever the
    video's length. YouTube reports whole seconds, so 0 seconds beside a real
    share is a view of under a second and is kept. Counts are
    different, since nobody saving a video is a reading, and so is stayed to
    watch: YouTube's views and engaged views come from one report, so 0
    engaged of some views was measured.

    `duration_secs` is the video's own length. It is used where the payload
    has seconds and neither a share (a 0 share counts as none) nor a length
    of its own, which is always the case on Instagram; without it that share
    is None. A share above 100
    is kept as it is, since a looping Short is watched more than once.
    """
    fields = _RETENTION_FIELDS.get(platform, {})
    metrics = metrics if isinstance(metrics, dict) else {}

    def read(name):
        key, divisor = fields.get(name, (None, 1))
        value = _number(metrics.get(key)) if key else None
        return None if value is None else value / divisor

    def shown(value):
        """A figure as the page shows it: one decimal, or None for one that
        is not a figure at all (a division by a vanishing number)."""
        return None if value is None or value > _MAX_READING else round(value, 1)

    out = dict.fromkeys(RETENTION_KEYS)
    out["engaged_views"] = read("engaged_views")
    out["reach"] = read("reach")
    out["saves"] = read("saves")

    seconds = read("avg_watch_secs")
    out["avg_watch_secs"] = shown(seconds)
    # The platform's own share, when it sent one that is not 0.
    out["watched_pct"] = shown(read("watched_pct")) or None
    if out["watched_pct"] is None:
        if not out["avg_watch_secs"]:
            # No share and no seconds once rounded: nothing was measured.
            out["avg_watch_secs"] = None
        else:
            length = read("length_secs") or _number(duration_secs)
            if length:
                out["watched_pct"] = shown(seconds / length * 100) or None

    views = _number(extract_metrics(platform, metrics)["views"])
    if out["engaged_views"] is not None and views:
        out["stayed_pct"] = shown(out["engaged_views"] / views * 100)

    for key in ("engaged_views", "reach", "saves"):
        if out[key] is not None:
            out[key] = int(out[key])
    return out




# ── Groups ───────────────────────────────────────────────────────────────────
# One account at a time: a platform counts a view and a watched second its own
# way and every account has its own audience, so a figure only compares with
# others from the same account.

# A group with fewer videos than this is too small to read: one video that did
# unusually well moves a small group's figure a lot. The Analytics page shows
# such a group with a mark; learned routing does not count it.
WATCH_MIN_GROUP = 20


def median(values: list) -> float:
    """Median of a sorted, non-empty list."""
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


# ── Learned routing (TMDEV-217) ──────────────────────────────────────────────
# Formula routing reads which formulas and openings hold this install's own
# viewers, domain by domain. Fit to the topic always comes first: the skill
# adds these points only to a formula that already fits.

# The share of the video watched. Seconds watched would favour the longer
# formulas for being longer.
LEARN_MEASURE = "watched_pct"

# A post published less recently than this has figures that are still moving.
LEARN_MIN_AGE_DAYS = 7

# How far a group's middle value must sit from the account's own middle value
# for the domain before it reads as better or worse.
LEARN_MARGIN = 0.10

# Every this-many-th pick in a domain with evidence is a trial pick: the figures
# are set aside and formulas the domain has too few videos of get the points.
# Without it the favoured formula is picked more, gathers more videos, and
# looks ever more certain.
EXPLORE_EVERY = 4

LEARNED_POINTS = {"better": 2, "worse": -1}
EXPLORE_POINTS = 2

# Standings, in the order the writer's list shows them.
STANDINGS = ("better", "even", "mixed", "worse")
THIN = "thin"

_LATEST_SNAPSHOT_SQL = """
    SELECT vp.platform, vp.social_account_id, vp.published_at, v.id AS video_id,
           v.formula_id, v.hook_type, v.duration_secs, m.raw_json
    FROM video_publications vp
    JOIN videos v ON v.id = vp.video_id
    LEFT JOIN video_metrics m ON m.id = (
        SELECT id FROM video_metrics WHERE publication_id = vp.id
        ORDER BY fetched_at DESC, id DESC LIMIT 1)
    WHERE vp.status = 'PUBLISHED' AND v.project_id = ?
"""


def _parse_utc(stamp):
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _standing(ratio: float) -> str:
    if ratio >= 1 + LEARN_MARGIN:
        return "better"
    if ratio <= 1 - LEARN_MARGIN:
        return "worse"
    return "even"


def _combined(standings: list) -> str:
    """One standing from an account each. Better on one account and worse on
    none is better; the mirror is worse; any disagreement reads as no evidence."""
    better, worse = "better" in standings, "worse" in standings
    if better and worse:
        return "mixed"
    if better:
        return "better"
    if worse:
        return "worse"
    return "even" if standings else THIN


def domain_evidence(con, project_id: str, now: datetime | None = None) -> dict:
    """What this domain's published videos say about its formulas and openings.

    Each published post's latest snapshot gives one share watched. Posts
    younger than LEARN_MIN_AGE_DAYS and posts whose platform reports no share
    are left out. Per account, the baseline is the median of the domain's posts
    there (at least WATCH_MIN_GROUP, or the account gives no evidence), and a
    formula or opening type with at least WATCH_MIN_GROUP posts on it reads as
    better, even or worse by its median against that baseline. Medians, so one
    outlier cannot carry a group.

    Returns {active, accounts, formulas: {id: {standing, videos, figures}},
    openings: [{type, label, standing, videos}]}. `figures` is the most posts
    with a figure the formula has on any one account; `videos` counts the
    distinct videos behind its counted groups. `active` is true when any
    formula has a counted group.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=LEARN_MIN_AGE_DAYS)
    by_account: dict = {}
    for row in con.execute(_LATEST_SNAPSHOT_SQL, (project_id,)):
        published = _parse_utc(row["published_at"])
        if published is None or published > cutoff:
            continue
        try:
            raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
        except (TypeError, ValueError):
            raw = {}
        share = extract_retention(row["platform"], raw, row["duration_secs"]).get(LEARN_MEASURE)
        if share is None:
            continue
        by_account.setdefault(row["social_account_id"], []).append(
            (row["formula_id"] or "", row["hook_type"] or "", row["video_id"], share))

    groups = {"formula": {}, "hook": {}}  # key -> {"standings": [], "videos": set(), "figures": 0}
    accounts = 0
    for posts in by_account.values():
        per = {"formula": {}, "hook": {}}
        for formula, hook, video, share in posts:
            for dim, key in (("formula", formula), ("hook", hook)):
                if key:
                    per[dim].setdefault(key, []).append((video, share))
        for dim in per:
            for key, items in per[dim].items():
                entry = groups[dim].setdefault(key, {"standings": [], "videos": set(), "figures": 0})
                entry["figures"] = max(entry["figures"], len(items))
        if len(posts) < WATCH_MIN_GROUP:
            continue
        accounts += 1
        baseline = median(sorted(share for *_rest, share in posts))
        for dim in per:
            for key, items in per[dim].items():
                if len(items) < WATCH_MIN_GROUP:
                    continue
                entry = groups[dim][key]
                entry["standings"].append(_standing(median(sorted(s for _v, s in items)) / baseline))
                entry["videos"].update(v for v, _s in items)

    def summary(entry):
        return {"standing": _combined(entry["standings"]), "videos": len(entry["videos"]),
                "figures": entry["figures"]}

    formulas = {key: summary(entry) for key, entry in groups["formula"].items()}
    openings = [
        {"type": key, "label": tformulas.HOOK_TYPES.get(key, key), **summary(entry)}
        for key, entry in groups["hook"].items() if entry["standings"]]
    openings.sort(key=lambda o: (STANDINGS.index(o["standing"]), -o["videos"], o["type"]))
    for opening in openings:
        del opening["figures"]
    return {"active": any(f["standing"] != THIN for f in formulas.values()),
            "accounts": accounts, "formulas": formulas, "openings": openings}


def learning_mode(con, project_id: str, video_id: str) -> str:
    """"explore" for every EXPLORE_EVERY-th pick in the domain that was made
    with evidence (counted from the picks that recorded it), else "learned"."""
    made = con.execute(
        "SELECT COUNT(*) FROM videos WHERE project_id = ? AND id != ? "
        "AND COALESCE(formula_evidence, '') != ''", (project_id, video_id)).fetchone()[0]
    return "explore" if made % EXPLORE_EVERY == EXPLORE_EVERY - 1 else "learned"


def points(standing: str, mode: str) -> int:
    """A formula's learned points: what the figures add to a formula that
    already fits the topic."""
    if mode == "explore":
        return EXPLORE_POINTS if standing == THIN else 0
    return LEARNED_POINTS.get(standing, 0)


def routing_learning(con, project_id: str, video_id: str, enabled: bool,
                     now: datetime | None = None) -> dict:
    """get_video's formula_routing.learned, before the candidates take their
    points: {active, mode, measure, min_group, openings, formulas}.

    enabled: the setting learned_routing and publishing both on. Off, or a
    domain with no counted group, is {"active": False, ...} with no formulas:
    every candidate then gets 0 points and routing is as it was before.
    """
    off = {"active": False, "mode": "", "measure": LEARN_MEASURE,
           "min_group": WATCH_MIN_GROUP, "openings": [], "formulas": {}}
    if not enabled or not project_id:
        return off
    evidence = domain_evidence(con, project_id, now)
    if not evidence["active"]:
        return off
    mode = learning_mode(con, project_id, video_id)
    formulas = {}
    for fid in tformulas.FORMULAS:
        entry = evidence["formulas"].get(fid, {"standing": THIN, "videos": 0, "figures": 0})
        formulas[fid] = {"points": points(entry["standing"], mode),
                         "standing": entry["standing"], "videos": entry["videos"]}
    return {"active": True, "mode": mode, "measure": LEARN_MEASURE,
            "min_group": WATCH_MIN_GROUP, "accounts": evidence["accounts"],
            "openings": evidence["openings"], "formulas": formulas}


def candidate_learning(learning: dict, formula_id: str) -> dict:
    """One candidate's `learned`: {points, standing, videos}."""
    entry = learning.get("formulas", {}).get(formula_id)
    return dict(entry) if entry else {"points": 0, "standing": "", "videos": 0}


def evidence_record(learning: dict, formula_id: str) -> str:
    """videos.formula_evidence for a pick: the JSON the dashboard's "Why this
    formula" row reads, or "" when the pick was made with no evidence."""
    if not learning.get("active"):
        return ""
    entry = candidate_learning(learning, formula_id)
    return json.dumps({"formula": formula_id, "mode": learning["mode"],
                       "measure": learning["measure"], "standing": entry["standing"],
                       "points": entry["points"], "videos": entry["videos"],
                       "accounts": learning.get("accounts", 0)}, sort_keys=True)
