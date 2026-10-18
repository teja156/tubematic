"""Unit tests for status.py's local-date formatting (TMDEV-35).

_local_date() replaced a raw (v.get("updated_at") or "")[:10] string slice of
a UTC ISO timestamp, which printed the wrong calendar day for any evening-local
timestamp. These tests pin TZ + call time.tzset() so datetime.astimezone()
(which reads glibc's cached zone) actually reflects the timezone under test.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from status import _local_date


@pytest.fixture
def tz_new_york():
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    yield
    if old_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = old_tz
    time.tzset()


def test_local_date_shifts_evening_utc_to_previous_local_day(tz_new_york):
    # Midnight UTC on Jan 1 is still Dec 31 evening in America/New_York (UTC-4/-5).
    assert _local_date("2026-01-01T00:00:00Z") == "2025-12-31"


def test_local_date_same_day_when_utc_is_already_local_morning(tz_new_york):
    assert _local_date("2026-01-01T18:00:00Z") == "2026-01-01"


def test_local_date_empty_string_returns_empty():
    assert _local_date("") == ""


def test_local_date_falls_back_to_raw_slice_on_unparseable_input():
    assert _local_date("not-a-timestamp") == "not-a-time"
