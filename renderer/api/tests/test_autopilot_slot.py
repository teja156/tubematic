"""autopilot.next_slot — when Auto Pilot may post next (TMDEV-139).

The slot rule is the only thing standing between a full queue of approved
videos and an account flooded with posts, so each half of it (the gap and the
daily number) is pinned here on its own and together.
"""
import datetime as dt
import pathlib
import sys
import zoneinfo

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import autopilot  # noqa: E402

UTC = dt.timezone.utc
NY = zoneinfo.ZoneInfo("America/New_York")
HOUR = dt.timedelta(hours=1)


def _t(day, hour, minute=0, month=6):
    return dt.datetime(2026, month, day, hour, minute, tzinfo=UTC)


def _acct(limit, *posts):
    return {"limit": limit, "posts": list(posts)}


def test_an_idle_account_posts_now():
    now = _t(10, 12)
    assert autopilot.next_slot(now, UTC, 4 * HOUR, [_acct(1)]) == now


def test_a_recent_post_pushes_the_slot_out_by_the_gap():
    now = _t(10, 12)
    slot = autopilot.next_slot(now, UTC, 4 * HOUR, [_acct(5, _t(10, 10))])
    assert slot == _t(10, 14)


def test_the_gap_also_holds_against_a_post_already_scheduled_ahead():
    # A human scheduled something for 13:00. Posting now, an hour before it,
    # would break the gap just as surely as posting an hour after it.
    now = _t(10, 12)
    slot = autopilot.next_slot(now, UTC, 4 * HOUR, [_acct(5, _t(10, 13))])
    assert slot == _t(10, 17)


def test_a_full_day_rolls_to_the_next_local_midnight():
    now = _t(10, 12)
    slot = autopilot.next_slot(now, UTC, dt.timedelta(0), [_acct(1, _t(10, 1))])
    assert slot == _t(11, 0)


def test_the_gap_can_push_past_midnight_on_its_own():
    now = _t(10, 12)
    slot = autopilot.next_slot(now, UTC, 4 * HOUR, [_acct(1, _t(10, 22))])
    assert slot == _t(11, 2)


def test_days_are_cut_in_the_host_zone_not_utc():
    # 03:00 UTC on the 11th is still the evening of the 10th in New York, so a
    # post then uses up the 10th's number there, and the 11th is still free.
    now = _t(11, 14)
    slot = autopilot.next_slot(now, NY, dt.timedelta(0), [_acct(1, _t(11, 3))])
    assert slot == now


def test_midnight_is_the_local_one_across_a_dst_change():
    # New York springs forward on 2026-03-08: that local day is 23 hours long,
    # and the following midnight is 04:00 UTC, not 05:00.
    now = dt.datetime(2026, 3, 8, 15, tzinfo=UTC)
    posted = dt.datetime(2026, 3, 8, 12, tzinfo=UTC)
    slot = autopilot.next_slot(now, NY, dt.timedelta(0), [_acct(1, posted)])
    assert slot == dt.datetime(2026, 3, 9, 4, tzinfo=UTC)


def test_one_post_waits_for_the_busiest_account():
    now = _t(10, 12)
    free = _acct(5)
    busy = _acct(5, _t(10, 11))
    assert autopilot.next_slot(now, UTC, 4 * HOUR, [free, busy]) == _t(10, 15)


def test_a_slot_that_frees_one_account_is_rechecked_against_the_other():
    # Clearing account A's gap lands on a day account B has already used up.
    now = _t(10, 12)
    a = _acct(5, _t(10, 11))
    b = _acct(1, _t(10, 2))
    assert autopilot.next_slot(now, UTC, 4 * HOUR, [a, b]) == _t(11, 0)


def test_several_days_already_full_are_skipped():
    now = _t(10, 12)
    posts = [_t(10, 1), _t(11, 1), _t(12, 1)]
    slot = autopilot.next_slot(now, UTC, dt.timedelta(0), [_acct(1, *posts)])
    assert slot == _t(13, 0)


def test_two_a_day_fills_the_day_before_moving_on():
    now = _t(10, 12)
    slot = autopilot.next_slot(now, UTC, HOUR, [_acct(2, _t(10, 9))])
    assert slot == now
    slot = autopilot.next_slot(now, UTC, HOUR, [_acct(2, _t(10, 9), _t(10, 10))])
    assert slot == _t(11, 0)


def test_nothing_free_inside_the_horizon_gives_up():
    now = _t(10, 12)
    assert autopilot.next_slot(now, UTC, HOUR, [_acct(0)]) is None
