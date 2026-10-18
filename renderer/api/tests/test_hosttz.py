"""Unit tests for hosttz.host_timezone() (TMDEV-35).

timezone_label is computed from datetime.now().astimezone(), which reads
glibc's *cached* zone — every test that changes TZ must pair
monkeypatch.setenv("TZ", ...) with time.tzset(), and the fixture below
restores + re-calls tzset() on teardown so tests don't leak zone state into
each other.
"""
import time

import pytest

import hosttz


@pytest.fixture
def tz(monkeypatch):
    """Yields a setter: tz("America/New_York") sets TZ + calls tzset()."""
    def _set(name: str | None):
        if name is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", name)
        time.tzset()
    yield _set
    time.tzset()


def test_resolves_iana_name_from_tz_env(tz):
    tz("America/New_York")
    result = hosttz.host_timezone()
    assert result["timezone"] == "America/New_York"


def test_label_reflects_the_zone_set_via_tz_env(tz):
    tz("America/New_York")
    result = hosttz.host_timezone()
    assert "EDT" in result["timezone_label"] or "EST" in result["timezone_label"]


def test_rejects_a_human_label_in_tz_env_falls_through_to_next_source(tz):
    tz("EDT (UTC-04:00)")  # not a real IANA name — must not be returned as-is
    result = hosttz.host_timezone()
    assert result["timezone"] != "EDT (UTC-04:00)"


def _patched_open(real_open, only_path, contents):
    """A builtins.open replacement that serves `contents` for exactly
    `only_path` and delegates every other path to the real open — avoids both
    infinite recursion (captures real_open before patching) and collateral
    breakage of unrelated file access during the test."""
    def _open(path, *a, **k):
        if path == only_path:
            import io
            return io.StringIO(contents)
        return real_open(path, *a, **k)
    return _open


def test_falls_back_to_etc_timezone_when_tz_env_unset(tz, monkeypatch):
    tz(None)
    monkeypatch.setattr("builtins.open", _patched_open(open, "/etc/timezone", "Europe/Berlin\n"))
    assert hosttz._resolve_iana_name() == "Europe/Berlin"


def test_falls_back_to_etc_localtime_symlink_when_etc_timezone_missing(tz, monkeypatch):
    tz(None)

    def _raise_open(path, *a, **k):
        raise OSError("no such file")
    monkeypatch.setattr("builtins.open", _raise_open)
    monkeypatch.setattr("os.readlink", lambda p: "/usr/share/zoneinfo/Asia/Tokyo" if p == "/etc/localtime" else (_ for _ in ()).throw(OSError()))
    assert hosttz._resolve_iana_name() == "Asia/Tokyo"


def test_returns_none_when_nothing_resolves(tz, monkeypatch):
    tz(None)

    def _raise_open(path, *a, **k):
        raise OSError("no such file")
    monkeypatch.setattr("builtins.open", _raise_open)
    monkeypatch.setattr("os.readlink", lambda p: (_ for _ in ()).throw(OSError()))
    assert hosttz._resolve_iana_name() is None


def test_iana_regex_accepts_valid_names():
    assert hosttz._IANA_RE.match("America/New_York")
    assert hosttz._IANA_RE.match("UTC")
    assert hosttz._IANA_RE.match("Etc/GMT+5")


def test_iana_regex_rejects_a_human_label():
    assert not hosttz._IANA_RE.match("EDT (UTC-04:00)")
    assert not hosttz._IANA_RE.match("EDT (UTC-04:00")


def test_host_timezone_always_returns_both_keys(tz):
    tz("America/New_York")
    result = hosttz.host_timezone()
    assert set(result.keys()) == {"timezone", "timezone_label"}
    assert isinstance(result["timezone_label"], str) and result["timezone_label"]
