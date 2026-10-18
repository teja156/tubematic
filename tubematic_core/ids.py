"""Ids that become path segments, and the containment check they need.

A video id names a job directory (`<jobs>/<id>/`), a generated-scenes
directory and an output file; a project id names an output directory
(`<output>/<id>/`). Both used to arrive unchecked from POST /videos,
POST /projects and MCP `upsert_project`, so `../x` or an absolute path walked
straight out of the data tree (TMDEV-158).

Two different strengths, on purpose:

- `check_segment` is the shape a NEW id must have. It is applied only where an
  id is created, so an existing row with an odd id (an agent once filed a
  domain called `node.js-internals`) can still be edited.
- `is_component` is what an id must be before it is joined onto a directory:
  one path component, never `.` or `..`. Together with containment (`inside`,
  and jobfiles' symlink walk), that is the check at every filesystem use, for
  video ids and project ids alike. It is what keeps an existing
  odd-but-harmless id (`a.b`, `Spaced Name`, one longer than 128 characters)
  rendering: refusing it there would strand an upgraded row in FAILED.

Every process that builds a path from an id imports this, rather than keeping
a copy: a copy that drifted would be a traversal, not a cosmetic difference.
"""
import re
from pathlib import Path

# The same character class mcp/server.py has always used for the video half of
# a composed scene src ("<video_id>/<scene>"), which is where it now comes from.
SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")
MAX_SEGMENT_LEN = 128
# NAME_MAX on every filesystem the data tree lives on (ext4, xfs, btrfs,
# overlayfs), counted in bytes. A component longer than this cannot exist, so
# no row with such an id ever had a job directory: refusing it at use strands
# nothing that worked, and refuses cleanly instead of failing with
# ENAMETOOLONG halfway through a render.
MAX_COMPONENT_BYTES = 255

# For error messages, so every refusal names the same rule.
SEGMENT_RULE = (f"letters, digits, '_' and '-' only, not starting with '-', "
                f"at most {MAX_SEGMENT_LEN} characters")


def check_segment(value) -> bool:
    """True when `value` is a well-formed id for a new row.

    fullmatch, never match: `$` also matches before a trailing newline, so
    `re.match` would accept "abc\\n".
    """
    return (isinstance(value, str) and 0 < len(value) <= MAX_SEGMENT_LEN
            and SEGMENT_RE.fullmatch(value) is not None)


def is_component(value) -> bool:
    """True when `value` is safe to join onto a directory as ONE component.

    Looser than check_segment so a legacy id with a dot or a space still
    works; strict about everything that changes which directory the join
    lands in. Control characters (NUL, a newline) are refused too: no real id
    ever held one, and a name with one is only good for confusing a log.

    The 128-character cap is NOT applied here: it is the creation rule, and
    ids filed before it were never capped (TMDEV-157 round 2). The only length
    bound is the filesystem's own, MAX_COMPONENT_BYTES.
    """
    if not isinstance(value, str) or value in ("", ".", ".."):
        return False
    if any(c in "/\\" or ord(c) < 32 or ord(c) == 127 for c in value):
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_COMPONENT_BYTES
    except UnicodeEncodeError:  # a lone surrogate names no file
        return False


def inside(base, path) -> bool:
    """True when `path` resolves to somewhere under `base` (or `base` itself).

    Both sides are resolved, so a symlinked directory on the way out is caught
    as well as a `..`.
    """
    try:
        return Path(path).resolve().is_relative_to(Path(base).resolve())
    except (OSError, RuntimeError, ValueError):
        return False
