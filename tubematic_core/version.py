"""The canonical Tubematic version (TMDEV-91).

One source, read at runtime rather than baked into a constant, so the release
scripts and the running services cannot disagree about what version this is.

The VERSION file sits *beside* the package directory. On the host that is the
repo root; in the container the Dockerfile does `COPY VERSION /app/lib/VERSION`
next to `/app/lib/tubematic_core/`, so one rule resolves in both places with no
candidate-path list and no per-context special case.
"""
import os
import pathlib
import re

_PACKAGE_DIR = pathlib.Path(__file__).resolve().parent

_FALLBACK = "0.0.0"

# This project's GitHub repo, as owner/name. The only place it is spelled: bug
# reports are filed against it (scripts/collect_diagnostics.py prints the
# filing command, and the troubleshooting skill takes it from that report
# rather than naming a repo itself, TMDEV-167), release images default to its
# owner's GHCR namespace (gen_release_compose.DEFAULT_OWNER), and anything that
# later reads its releases should import it from here too (TMDEV-171).
GITHUB_REPO = "teja156/tubematic"

# The one definition of what a Tubematic version may look like: SemVer's
# MAJOR.MINOR.PATCH with an optional prerelease suffix, restricted to
# SemVer's own prerelease alphabet (dot-separated runs of ASCII letters,
# digits and hyphens) -- which also happens to be Docker-tag-safe, so this
# is not narrower than SemVer, just a subset that fits inside an image tag.
# Notably it excludes "+build metadata": legal SemVer, illegal in a Docker
# tag, and gen_release_compose.py interpolates the version straight into one.
#
# It lives here rather than in a release script because more than one caller
# needs it and a second hand-rolled copy is exactly how this went wrong once:
# tubematic_core's own test asserted every dot-separated part was a digit,
# which silently forbade the prereleases the release tooling documents and
# accepts. CI failed on a prerelease VERSION the rest of the system allowed.
VERSION_RE = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


# What VERSION holds on the development branch. The branch is not a release, so
# it carries no number: every release number is chosen when its release line
# is cut, never guessed ahead of time on the development branch. It is valid wherever a
# version is *used* (a Docker tag, a backup name, the dashboard badge) and
# refused only where a version is *released* -- see is_release().
DEV_VERSION = "develop"


def is_valid(version: str) -> bool:
    """True if `version` is a usable Tubematic version. Never raises."""
    return version == DEV_VERSION or is_release(version)


def is_release(version: str) -> bool:
    """True if `version` can be released: SemVer, never the DEV_VERSION marker."""
    return bool(VERSION_RE.match(version or ""))


def release_line(version: str) -> str:
    """The maintenance branch a version belongs to: "1.0.2" -> "release/1.0.x".

    One branch per MAJOR.MINOR, not one per release: 1.0.1 and 1.0.2 are both
    later TAGS on release/1.0.x rather than branches of their own. The ".x" is
    deliberate -- a branch named for a point release stops describing its own
    contents the moment a patch lands on it.

    Lives here rather than in a release script because two of them need it and
    they cannot import each other: release.py imports check_release.py, so the
    rule cannot live in release.py without a cycle.

    Raises ValueError for anything that is not a release version, DEV_VERSION
    included: the development branch belongs to no release line.
    """
    if not is_release(version):
        raise ValueError(f"{version!r} is not a release version, so it has no release line")
    major, minor = version.split("-", 1)[0].split(".")[:2]
    return f"release/{major}.{minor}.x"



def version() -> str:
    """The current version, e.g. "1.0.0". Never raises.

    TUBEMATIC_VERSION overrides the file, for a release script that needs to
    render a version it has not yet written. A blank or whitespace-only value is
    ignored rather than honoured — an exported-but-unset shell variable is the
    common way that happens, and it must not blank the version.
    """
    env = os.environ.get("TUBEMATIC_VERSION", "").strip()
    if env:
        return env
    try:
        return (_PACKAGE_DIR.parent / "VERSION").read_text().strip() or _FALLBACK
    except OSError:
        return _FALLBACK
