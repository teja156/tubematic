#!/usr/bin/env python3
"""Claude Code statusline for the VQA environment.

Shows context-window usage, the rolling 5-hour rate-limit window, and the
rolling 7-day rate-limit window, each as a color-coded progress bar — so a
long-running VQA session can see at a glance how much room is left before
hitting a limit. Wired in by kasm_post_run_user.sh via ~/.claude/settings.json's
`statusLine` config; the JSON schema piped to this script via stdin is
documented at https://code.claude.com/docs/en/statusline.

rate_limits is null/absent for non-subscription accounts, and
context_window.used_percentage is null before the first API call in a
session (or after /compact, until the next call) — every bar is simply
omitted in those cases rather than shown as 0%, which would misrepresent
"no data yet" as "just started."
"""
import json
import sys
from datetime import datetime, timezone

RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BAR_WIDTH = 10


def render_bar(pct: float) -> str:
    """A 10-cell filled/empty bar, color-coded green/yellow/red by threshold."""
    pct = max(0.0, min(100.0, pct))
    filled = round(pct / 100 * BAR_WIDTH)
    color = RED if pct >= 90 else YELLOW if pct >= 70 else GREEN
    return f"{color}{'█' * filled}{'░' * (BAR_WIDTH - filled)}{RESET} {pct:.0f}%"


def format_resets_in(unix_ts, now=None) -> str:
    """' (resets in Xh Ym)' / ' (resets in Xd)', or '' if unix_ts is falsy.

    now is injectable for testing — defaults to the real current time.
    """
    if not unix_ts:
        return ""
    now = now or datetime.now(timezone.utc)
    resets_at = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    secs = max(0, int((resets_at - now).total_seconds()))
    hours, rem = divmod(secs, 3600)
    if hours >= 24:
        return f" (resets in {hours // 24}d)"
    return f" (resets in {hours}h{rem // 60}m)"


def format_statusline(data: dict, now=None) -> str:
    model = (data.get("model") or {}).get("display_name", "Claude")
    parts = [f"[{model}]"]

    ctx_pct = (data.get("context_window") or {}).get("used_percentage")
    if ctx_pct is not None:
        parts.append(f"ctx {render_bar(ctx_pct)}")

    rate = data.get("rate_limits") or {}
    five_h = rate.get("five_hour") or {}
    seven_d = rate.get("seven_day") or {}

    if five_h.get("used_percentage") is not None:
        parts.append(
            f"5h {render_bar(five_h['used_percentage'])}"
            f"{format_resets_in(five_h.get('resets_at'), now)}"
        )
    if seven_d.get("used_percentage") is not None:
        parts.append(
            f"7d {render_bar(seven_d['used_percentage'])}"
            f"{format_resets_in(seven_d.get('resets_at'), now)}"
        )

    return " | ".join(parts)


def main() -> None:
    data = json.load(sys.stdin)
    print(format_statusline(data))


if __name__ == "__main__":
    main()
