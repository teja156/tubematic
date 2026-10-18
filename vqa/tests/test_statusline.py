"""Tests for vqa/statusline.py — the Claude Code statusline showing context
window usage and the 5-hour/7-day rate-limit windows."""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "vqa"))

from statusline import format_resets_in, format_statusline, render_bar  # noqa: E402


class TestRenderBar:
    def test_zero_percent_all_empty(self):
        assert "░░░░░░░░░░" in render_bar(0)
        assert "0%" in render_bar(0)

    def test_hundred_percent_all_filled(self):
        assert "██████████" in render_bar(100)
        assert "100%" in render_bar(100)

    def test_half_filled(self):
        bar = render_bar(50)
        assert bar.count("█") == 5
        assert bar.count("░") == 5

    def test_clamps_above_100(self):
        assert render_bar(150).count("█") == 10

    def test_clamps_below_0(self):
        assert render_bar(-10).count("░") == 10

    def test_color_thresholds(self):
        assert "\033[32m" in render_bar(50)   # green below 70
        assert "\033[33m" in render_bar(75)   # yellow 70-89
        assert "\033[31m" in render_bar(95)   # red 90+


class TestFormatResetsIn:
    def test_falsy_timestamp_is_empty(self):
        assert format_resets_in(None) == ""
        assert format_resets_in(0) == ""

    def test_hours_and_minutes(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        resets_at = now + timedelta(hours=2, minutes=30)
        assert format_resets_in(resets_at.timestamp(), now=now) == " (resets in 2h30m)"

    def test_days_when_24h_or_more(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        resets_at = now + timedelta(days=3, hours=5)
        assert format_resets_in(resets_at.timestamp(), now=now) == " (resets in 3d)"

    def test_past_timestamp_clamps_to_zero(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        resets_at = now - timedelta(hours=1)
        assert format_resets_in(resets_at.timestamp(), now=now) == " (resets in 0h0m)"


class TestFormatStatusline:
    def test_full_data_shows_all_three_bars(self):
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        data = {
            "model": {"display_name": "Opus"},
            "context_window": {"used_percentage": 42},
            "rate_limits": {
                "five_hour": {"used_percentage": 23.5, "resets_at": (now + timedelta(hours=1)).timestamp()},
                "seven_day": {"used_percentage": 61.2, "resets_at": (now + timedelta(days=2)).timestamp()},
            },
        }
        result = format_statusline(data, now=now)
        assert "[Opus]" in result
        assert "ctx" in result and "42%" in result
        assert "5h" in result and "24%" in result  # 23.5 rounds to 24
        assert "7d" in result and "61%" in result

    def test_missing_rate_limits_omits_those_bars(self):
        data = {"model": {"display_name": "Sonnet"}, "context_window": {"used_percentage": 5}}
        result = format_statusline(data)
        assert "[Sonnet]" in result
        assert "ctx" in result
        assert "5h" not in result
        assert "7d" not in result

    def test_before_first_api_call_shows_only_model(self):
        data = {"model": {"display_name": "Sonnet"}}
        result = format_statusline(data)
        assert result == "[Sonnet]"

    def test_missing_model_defaults_to_claude(self):
        data = {}
        result = format_statusline(data)
        assert "[Claude]" in result

    def test_only_five_hour_present(self):
        data = {
            "model": {"display_name": "Opus"},
            "rate_limits": {"five_hour": {"used_percentage": 10}},
        }
        result = format_statusline(data)
        assert "5h" in result
        assert "7d" not in result


class TestCliEndToEnd:
    """Subprocess-based test proving the actual stdin-JSON -> stdout-string
    contract works, not just the internal functions — this is what Claude
    Code itself will invoke."""

    def test_reads_stdin_writes_stdout(self):
        payload = (
            '{"model": {"display_name": "Opus"}, '
            '"context_window": {"used_percentage": 10}}'
        )
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "vqa" / "statusline.py")],
            input=payload,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "[Opus]" in result.stdout
        assert "10%" in result.stdout
