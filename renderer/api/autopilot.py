"""When Auto Pilot may post next (TMDEV-139).

Pure and DB-free, like postforme.py: the worker gathers each account's existing
post times and its daily number, and this decides the slot. Only worker.py
imports it — pipeline.py must not, because several tools copy pipeline.py in
isolation.
"""
import datetime as dt

# The same horizon a human schedule is held to (pipeline.SCHEDULE_MAX_LEAD_DAYS).
# Duplicated rather than imported so this module stays free of Flask.
MAX_LEAD_DAYS = 365

# Each pass moves the candidate strictly later, past one post or one day, so
# the loop always ends at the horizon. The cap only bounds a pathological input.
_MAX_STEPS = 10_000


def _next_midnight(moment: dt.datetime, zone) -> dt.datetime:
    """The first local midnight after `moment`, as UTC.

    Built from the local date, not by adding 24 hours: a DST day is 23 or 25
    hours long.
    """
    local_day = moment.astimezone(zone).date() + dt.timedelta(days=1)
    midnight = dt.datetime.combine(local_day, dt.time.min, tzinfo=zone)
    return midnight.astimezone(dt.timezone.utc)


def _same_day_count(moment: dt.datetime, posts: list, zone) -> int:
    day = moment.astimezone(zone).date()
    return sum(1 for p in posts if p.astimezone(zone).date() == day)


def next_slot(now: dt.datetime, zone, gap: dt.timedelta, accounts: list):
    """The earliest UTC time one post may go to every account in `accounts`.

    `accounts` is a list of `{"limit": int, "posts": [aware datetimes]}`. A slot
    is free for an account when no existing post of its is closer than `gap`,
    before or after, and it has fewer than `limit` posts on that day in `zone`.
    Returns `now` itself when it is already free, or None if nothing is free
    within MAX_LEAD_DAYS.
    """
    horizon = now + dt.timedelta(days=MAX_LEAD_DAYS)
    candidate = now
    for _ in range(_MAX_STEPS):
        if candidate > horizon:
            return None
        moved = False
        for account in accounts:
            for post in account["posts"]:
                if abs(candidate - post) < gap:
                    candidate = post + gap
                    moved = True
            if _same_day_count(candidate, account["posts"], zone) >= account["limit"]:
                candidate = _next_midnight(candidate, zone)
                moved = True
        if not moved:
            return candidate
    return None
