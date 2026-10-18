#!/usr/bin/env python3
"""Extract one version's section from docs/release-notes.md.

That page is the single source for release notes. This is what lets it stay
single: `release.yml` runs this to produce the body of the GitHub Release, and
`check_release.py` runs it as a pre-flight check so a version with missing or
still-empty notes fails *before* a tag is pushed rather than publishing a
Release with an empty body.

Nothing here writes the notes or invents them. A skeleton with every bullet
left blank is treated as absent, because that is what it is -- the failure this
guards against is not "the maintainer forgot the file", it is "the maintainer
pasted the skeleton and moved on".

Run from the repo root:
    python scripts/release_notes.py 1.2.3
    python scripts/release_notes.py v1.2.3 --notes-file docs/release-notes.md
"""
import argparse
import pathlib
import re
import sys

_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPTS_DIR.parent

DEFAULT_NOTES_FILE = "docs/release-notes.md"

# A version heading: "## v1.2.3", optionally followed by anything on the same
# line (a date, a codename). Matched at the start of a line only, so a "## v..."
# inside a fenced code block in prose above cannot be mistaken for one.
_HEADING_RE = re.compile(r"^##\s+v(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\s*.*$")


class ReleaseNotesError(Exception):
    """The notes for a version are missing, empty, or the file cannot be read.

    A hard failure, never a warning: a Release published with an empty body is
    not fixable after the fact in any way that reaches someone who already
    downloaded it.
    """


def _normalise(version: str) -> str:
    """Accept "1.2.3" or "v1.2.3" -- the git tag carries the v, the VERSION
    file does not, and both spellings reach this script from different
    callers."""
    return version[1:] if version.startswith("v") else version


def _is_meaningful(body: str) -> bool:
    """True if the section says anything a reader would gain from.

    An unfilled skeleton is every bullet still empty ("- " with nothing after
    it) under headings. Strip the headings, the empty bullets and the blank
    lines; if nothing survives, the section was never written.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):          # a subsection heading
            continue
        if stripped in ("-", "*", "- ", "* "):  # an empty bullet
            continue
        return True
    return False


def _base_version(version: str) -> str:
    """"1.2.3-rc.1" -> "1.2.3". Unchanged for a version with no prerelease."""
    return version.split("-", 1)[0]


def extract(version: str, notes_path) -> str:
    """The body of `version`'s section, without its own heading.

    A prerelease with no section of its own falls back to its base version:
    `1.2.3-rc.1` is a candidate FOR `1.2.3`, so its notes are that version's
    notes. Requiring a separate section per release candidate would mean
    writing throwaway notes for every rehearsal, which is how a check ends up
    being worked around instead of satisfied. A prerelease that *does* have its
    own section still wins -- the fallback only fills a gap.

    Raises ReleaseNotesError if the file is missing, neither the version nor
    its base has a section, or the section found is present but unfilled.
    """
    path = pathlib.Path(notes_path)
    wanted = _normalise(version)
    try:
        text = path.read_text()
    except OSError as e:
        raise ReleaseNotesError(f"cannot read {path}: {e}") from e

    lines = text.splitlines()

    def _find(v):
        for i, line in enumerate(lines):
            m = _HEADING_RE.match(line)
            if m and m.group("version") == v:
                return i + 1
        return None

    start = _find(wanted)
    if start is None:
        base = _base_version(wanted)
        if base != wanted:
            start = _find(base)
        if start is None:
            extra = f" (nor `## v{base}`)" if base != wanted else ""
            raise ReleaseNotesError(
                f"{path} has no `## v{wanted}` section{extra}. Add one before "
                f"releasing {wanted} -- see the page's own 'How to write an entry'."
            )

    # Runs to the next version heading, or a horizontal rule, or EOF.
    end = len(lines)
    for j in range(start, len(lines)):
        if _HEADING_RE.match(lines[j]) or lines[j].strip() == "---":
            end = j
            break

    body = "\n".join(lines[start:end]).strip()
    if not _is_meaningful(body):
        raise ReleaseNotesError(
            f"{path}'s `## v{wanted}` section is empty or still the unfilled "
            "skeleton. Write it before releasing -- a Release body cannot be "
            "fixed for anyone who already downloaded the release."
        )
    return body


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", help='Version to extract, e.g. "1.2.3" or "v1.2.3"')
    ap.add_argument("--notes-file", default=None,
                    help=f"Path to the notes page (default: {DEFAULT_NOTES_FILE})")
    ap.add_argument("--repo-root", default=str(_REPO_ROOT_DEFAULT),
                    help="Repo root the default notes path resolves against")
    args = ap.parse_args(argv)

    notes = args.notes_file or (pathlib.Path(args.repo_root) / DEFAULT_NOTES_FILE)
    try:
        sys.stdout.write(extract(args.version, notes) + "\n")
    except ReleaseNotesError as e:
        sys.stderr.write(f"error: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
