"""Host timezone detection.

Keep in sync with: scripts/config.py host_timezone(), onboard.py host_timezone().
Duplicated (not shared) because mcp/, renderer/api/, and scripts/ are separate
processes/images — same convention as DICTIONARY_COMPATIBLE_MODELS
(renderer/api/pipeline.py, mcp/server.py). There is a shared package now
(tubematic_core/), but it is deliberately scoped to structured logging; this is
a dozen lines with no security surface and stays a copy.
"""
import os
import re
from datetime import datetime

# IANA zone names are Area/Location (optionally nested), ASCII, no whitespace or
# parens. This guard keeps a human label (e.g. "EDT (UTC-04:00)") from ever being
# passed to a caller that will hand it to JS Intl.DateTimeFormat, which throws
# RangeError on anything that isn't a real zone name.
_IANA_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+_-]*(?:/[A-Za-z0-9+_.-]+)*$")


def _resolve_iana_name() -> str | None:
    tz_env = os.environ.get("TZ", "").strip()
    if tz_env and _IANA_RE.match(tz_env):
        return tz_env

    try:
        with open("/etc/timezone") as f:
            for line in f:
                line = line.strip()
                if line and _IANA_RE.match(line):
                    return line
    except OSError:
        pass

    try:
        link = os.readlink("/etc/localtime")
        if "/zoneinfo/" in link:
            name = link.split("/zoneinfo/", 1)[1]
            if _IANA_RE.match(name):
                return name
    except OSError:
        pass

    return None


def _label() -> str:
    """e.g. 'EDT (UTC-04:00)'. Computed from astimezone(), which reads /etc/localtime
    via glibc and needs no tzdata — stays correct even when name resolution above
    fails. Never pass this to Intl.DateTimeFormat; it is display-only."""
    now = datetime.now().astimezone()
    tzname = now.tzname() or "local"
    offset = now.strftime("%z")  # e.g. -0400
    if offset:
        return f"{tzname} (UTC{offset[:3]}:{offset[3:]})"
    return tzname


def host_timezone() -> dict:
    """-> {"timezone": str | None, "timezone_label": str}

    timezone       — IANA name, e.g. "America/New_York", or None if undetectable.
                     NEVER a fabricated/abbreviated string: this value is passed
                     straight into JS Intl.DateTimeFormat, which throws RangeError
                     on anything that isn't a real zone name.
    timezone_label — human display only, e.g. "EDT (UTC-04:00)". Never passed to Intl.
    """
    return {
        "timezone": _resolve_iana_name(),
        "timezone_label": _label(),
    }
