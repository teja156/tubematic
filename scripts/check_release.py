#!/usr/bin/env python3
"""Maintainer pre-flight checks before cutting a Tubematic release (TMDEV-91
Phase 2, spec section 5.3).

Reports every failure in one pass rather than stopping at the first --
a maintainer fixing up a release wants the whole list, not five separate
runs. Exits 0 only when every non-warning check passes.

Checks:
  - the git working tree is clean
  - VERSION matches the requested version (accepts "1.2.3" or "v1.2.3" on
    the command line -- the git tag carries the "v", the file does not)
  - the version is a valid, tag-safe MAJOR.MINOR.PATCH[-prerelease] (a
    legal SemVer "+build metadata" suffix is illegal in a Docker tag, and
    gen_release_compose.py interpolates the version straight into one)
  - the tag for that version does not already point at a different commit
    than HEAD (an already-existing tag pointing at HEAD is expected when
    this runs in CI after actions/checkout has fetched the pushed tag, and
    passes; pointing anywhere else means reusing a version for different
    code, and fails)
  - migrations are ordered, parseable and free of duplicate version numbers
    (reuses tubematic_core.db.discover(), never re-implemented here)
  - no migration file has been modified relative to its last committed
    state (the mechanical enforcement of migration immutability)
  - the release compose generates cleanly and carries no build: key
  - the release tarball's allowlist is satisfiable (every path it needs
    actually exists) and every excluded pattern is actually excluded
  - Phase 3's workflow files exist -- reported as a WARNING, not a
    failure, since Phase 3 has not landed yet and this script must not be
    permanently red until it does

Run from the repo root:
    python scripts/check_release.py 1.2.3
    python scripts/check_release.py v1.2.3
"""
import argparse
import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_REPO_ROOT_DEFAULT))

from tubematic_core.db import MigrationError, discover  # noqa: E402
from tubematic_core.version import is_release, release_line  # noqa: E402

# gen_release_compose.py owns the PyYAML dependency check and exits with a
# clear message if it is missing -- that exit is a SystemExit, which a
# `except ModuleNotFoundError` here cannot catch, so a second guard around
# this import would be dead code pretending to handle a failure it can
# never see.
import gen_release_compose
import release_notes  # noqa: E402
import build_release_tarball  # noqa: E402

# Phase 3 lands these; until then their absence is expected, not a defect.
_WORKFLOW_FILES = (".github/workflows/ci.yml", ".github/workflows/release.yml")


@dataclasses.dataclass(frozen=True)
class Check:
    name: str
    status: str  # "pass" | "fail" | "warn"
    detail: str = ""


def _pass(name: str, detail: str = "") -> Check:
    return Check(name, "pass", detail)


def _fail(name: str, detail: str) -> Check:
    return Check(name, "fail", detail)


def _warn(name: str, detail: str) -> Check:
    return Check(name, "warn", detail)


def normalize_version(raw: str) -> str:
    """Accept both "1.2.3" and "v1.2.3" -- the git tag carries the "v",
    VERSION does not. Case-insensitive on the single leading letter only,
    so a plain version starting with an actual "v" word is not possible
    here (SemVer versions never do)."""
    return raw[1:] if raw[:1] in ("v", "V") else raw


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True,
    )


# ── Individual checks ────────────────────────────────────────────────────────

def check_clean_working_tree(repo_root: Path) -> Check:
    name = "git working tree is clean"
    result = _run_git(repo_root, "status", "--porcelain")
    if result.returncode != 0:
        return _fail(name, f"git status failed: {result.stderr.strip()}")
    if result.stdout.strip():
        return _fail(name, "uncommitted changes present:\n" + result.stdout.rstrip())
    return _pass(name)


def check_version_matches(repo_root: Path, version: str) -> Check:
    name = "VERSION matches the requested version"
    version_file = repo_root / "VERSION"
    if not version_file.is_file():
        return _fail(name, f"{version_file} not found")
    file_version = version_file.read_text().strip()
    if file_version != version:
        return _fail(
            name, f"VERSION file has {file_version!r}, requested {version!r}")
    return _pass(name)


def check_version_format(version: str) -> Check:
    """The version must double as a Docker image tag component -- reuses
    gen_release_compose's canonical definition rather than restating it, the
    same way check_tarball_allowlist() below reuses build_release_tarball's
    lists instead of hand-copying them. See
    gen_release_compose.check_version_is_tag_safe for the rule and why a
    legal-SemVer "+build metadata" suffix is rejected here."""
    name = "version is a valid, tag-safe MAJOR.MINOR.PATCH[-prerelease]"
    try:
        gen_release_compose.check_version_is_tag_safe(version)
    except ValueError as e:
        return _fail(name, str(e))
    if not is_release(version):
        return _fail(name, f"{version!r} is the development-branch marker, not a release "
                           f"version -- set VERSION to the version being released")
    return _pass(name)


def check_tag_not_exists(repo_root: Path, tag: str) -> Check:
    """The tag must not already point at a commit OTHER than HEAD.

    This check has two genuinely different callers, and both are covered by
    that one rule rather than by two code paths:

      - A maintainer running this pre-flight at a terminal, before ever
        creating the tag. `refs/tags/<tag>` does not resolve at all, so
        this passes -- the ordinary case.
      - TMDEV-91 Phase 3's release workflow, which runs `check_release.py`
        in CI *after* `actions/checkout` has already fetched the tag that
        triggered the run (the workflow only runs on a tag push, and
        checkout fetches the pushed ref, so `refs/tags/<tag>` already
        resolves locally by the time this runs). That tag points at
        exactly the commit being checked out -- HEAD -- so this must also
        pass, or every real release run fails here, unconditionally,
        forever. An earlier version of this check did not account for this
        caller and failed exactly that way.

    What must still fail is the actual danger this check exists for: the
    tag exists and points somewhere else -- reusing a version number for
    different code. That is unambiguously wrong regardless of caller, so it
    fails and names both commits.

    Deliberately not a `--allow-existing-tag`-style bypass flag: a flag can
    be passed in the one case that actually matters (tag exists, points
    elsewhere), which would turn a safety property into a convention. The
    commit comparison has no such escape hatch -- it is either the release
    being built, or it isn't.
    """
    name = f"tag {tag} does not point at a different commit than HEAD"

    head = _run_git(repo_root, "rev-parse", "-q", "--verify", "HEAD")
    if head.returncode != 0:
        return _fail(name, f"could not resolve HEAD: {head.stderr.strip()}")
    head_sha = head.stdout.strip()

    # `^{commit}` peels an annotated tag to the commit it points at, so this
    # compares commits either way rather than an annotated tag's own object
    # id (which would never equal a bare commit sha).
    tag_result = _run_git(
        repo_root, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}")
    if tag_result.returncode != 0:
        return _pass(name)
    tag_sha = tag_result.stdout.strip()

    if tag_sha == head_sha:
        return _pass(name)

    return _fail(
        name,
        f"tag {tag} already exists at {tag_sha}, but HEAD is {head_sha} -- "
        f"reusing this version number for different code")


def check_migrations_ordered(migrations_dir: Path) -> Check:
    name = "migrations are ordered, parseable and duplicate-free"
    try:
        discover(migrations_dir)
    except MigrationError as e:
        return _fail(name, str(e))
    except OSError as e:
        return _fail(name, f"could not read {migrations_dir}: {e}")
    return _pass(name)


def check_migration_immutability(repo_root: Path, migrations_dir: Path) -> Check:
    """No migration file may be modified relative to its last committed
    state -- the mechanical enforcement of the immutability rule (a shipped
    migration must never be edited, since editing one silently diverges
    every database that already applied it from every database that has
    not).

    Decision: a migration file that is new and not yet committed is NOT a
    violation -- that is the ordinary, legitimate state while a maintainer
    is actively developing a migration that has not shipped. `git diff
    HEAD` only ever reports "M" for a path git already has a committed
    version of; a brand-new file is either invisible to it (untracked) or
    reported as "A" (staged but never committed), and this check only
    treats "M" as a violation. So only a change to a migration git already
    has history for counts.
    """
    name = "no migration file modified relative to its last committed state"
    try:
        rel = migrations_dir.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return _fail(name, f"{migrations_dir} is not inside {repo_root}")

    result = _run_git(repo_root, "diff", "--name-status", "HEAD", "--", str(rel))
    if result.returncode != 0:
        return _fail(name, f"git diff failed: {result.stderr.strip()}")

    modified = [
        line.split("\t", 1)[1]
        for line in result.stdout.splitlines()
        if line.startswith("M\t")
    ]
    if modified:
        return _fail(name, "modified relative to HEAD: " + ", ".join(modified))
    return _pass(name)


def check_release_compose(repo_root: Path, version: str, owner: str) -> Check:
    name = "release compose generates cleanly with no build: key"
    compose_path = repo_root / "docker-compose.yml"
    if not compose_path.is_file():
        return _fail(name, f"{compose_path} not found")
    try:
        output = gen_release_compose.generate(compose_path, version, owner=owner)
    except Exception as e:  # noqa: BLE001 -- any generation failure blocks a release
        return _fail(name, f"generation failed: {e}")
    if "build:" in output:
        return _fail(name, "generated compose still contains a build: key")
    return _pass(name)


def check_tarball_allowlist(repo_root: Path) -> Check:
    """Every path build_release_tarball.py's allowlist requires must exist.

    Reuses that module's own canonical lists rather than hand-copying a
    second list here -- duplicating that list is exactly the kind of
    duplicated truth this whole ticket exists to remove.
    """
    name = "release tarball allowlist is satisfiable"
    missing = []
    for filename in build_release_tarball._ROOT_FILES:
        if not (repo_root / filename).is_file():
            missing.append(filename)
    for filename in build_release_tarball._SCRIPTS_FILES:
        if not (repo_root / "scripts" / filename).is_file():
            missing.append(f"scripts/{filename}")
    for dirname in build_release_tarball._DIR_TREES:
        if not (repo_root / dirname).is_dir():
            missing.append(dirname)
    for filename in build_release_tarball._DOC_FILES:
        if not (repo_root / filename).is_file():
            missing.append(filename)
    if not (repo_root / "docker-compose.yml").is_file():
        missing.append("docker-compose.yml")

    if missing:
        return _fail(name, "missing: " + ", ".join(missing))
    return _pass(name)


def check_tarball_exclusions(repo_root: Path, version: str, owner: str) -> Check:
    """The allowlist being satisfiable (check_tarball_allowlist above) is
    only half the rule -- it says nothing about whether a forbidden path
    (a source tree, `.env`, `.git`, a package's own test suite) actually
    gets swept into the staged output alongside an allowlisted entry. That
    enforcement -- the per-tree ignore filters plus the whole-tree
    `_assert_no_forbidden_names` backstop -- lives only in
    build_release_tarball.py and its own tests, so a maintainer running
    this pre-flight got no signal about it at all.

    Rather than restating `_FORBIDDEN_NAMES` or the per-tree exclusion sets
    here (exactly the duplicated-truth problem this whole tool exists to
    avoid), this runs the real builder end to end against a scratch
    directory and lets its own exclusion logic answer the question.
    """
    name = "release tarball build stages no forbidden path (exclusions hold)"
    with tempfile.TemporaryDirectory(prefix="check-release-tarball-") as scratch:
        try:
            build_release_tarball.build(
                version, repo_root=repo_root, out_dir=scratch, owner=owner)
        except build_release_tarball.ReleaseBuildError as e:
            return _fail(name, str(e))
        except Exception as e:  # noqa: BLE001 -- any build failure blocks a release
            return _fail(name, f"tarball build failed: {e}")
    return _pass(name)


def check_head_is_on_the_release_line(repo_root: Path, version: str) -> Check:
    """HEAD should be on, or reachable from, this version's release line.

    Releases are tagged on a line branch -- one per MAJOR.MINOR, named
    `release/X.Y.x`, with every patch of that minor as a later tag on the
    same branch. Tagging from the development branch instead is the mistake
    this model makes *easier* than the old one did: the line branch and the
    development branch both look taggable from a terminal, and the resulting
    release would carry every feature merged since the line was cut -- a
    minor release wearing a patch's version number.

    A WARNING rather than a failure, deliberately, because there are honest
    reasons for the line to be absent:

      - The first release of a MAJOR.MINOR, run *before* the line is created.
        The maintainer checklist prints the branch command and the tag
        command together, and a pre-flight run before either is the normal
        order, not a mistake.
      - CI, where `actions/checkout` fetches the tag as a detached HEAD and
        may have fetched no branches at all.

    Failing on those would make the check permanently red in exactly the two
    situations it is most likely to be run, which is how a check gets
    ignored. It reports what it found and lets the maintainer judge.
    """
    name = "HEAD is on this version's release line"
    if not is_release(version):
        return Check(name, "warn", f"skipped -- {version!r} is not a release version, "
                                   f"so it has no release line")
    line = release_line(version)

    exists = _run_git(repo_root, "rev-parse", "-q", "--verify", f"refs/heads/{line}")
    if exists.returncode != 0:
        remote = _run_git(repo_root, "rev-parse", "-q", "--verify",
                          f"refs/remotes/origin/{line}")
        if remote.returncode != 0:
            return Check(name, "warn",
                         f"{line} does not exist locally or on origin -- expected "
                         f"for the first release of this MAJOR.MINOR, which creates it")
        ref = f"origin/{line}"
    else:
        ref = line

    head = _run_git(repo_root, "rev-parse", "-q", "--verify", "HEAD")
    if head.returncode != 0:
        return Check(name, "warn", "no HEAD to check")
    merge_base = _run_git(repo_root, "merge-base", "--is-ancestor", "HEAD", ref)
    if merge_base.returncode == 0:
        return Check(name, "pass", f"HEAD is contained in {ref}")
    return Check(
        name, "warn",
        f"HEAD is not contained in {ref}. If you are tagging {version} from a "
        f"development branch rather than the release line, the release will "
        f"carry everything merged since {line} was cut."
    )


def check_release_notes(repo_root: Path, version: str) -> Check:
    """docs/release-notes.md must carry a written section for this version.

    A hard failure rather than a warning. The release workflow publishes that
    section as the GitHub Release body, so a missing one means a Release with
    no notes at all -- and unlike almost everything else here, that cannot be
    repaired for anyone who already downloaded the release. An unfilled
    skeleton counts as missing; a prerelease falls back to its base version.
    """
    name = "release notes exist for this version"
    notes = repo_root / release_notes.DEFAULT_NOTES_FILE
    try:
        body = release_notes.extract(version, notes)
    except release_notes.ReleaseNotesError as e:
        return Check(name, "fail", str(e))
    first = next((ln for ln in body.splitlines() if ln.strip()), "")
    return Check(name, "pass", f"{len(body.splitlines())} lines, starting {first[:48]!r}")


def check_workflow_files(repo_root: Path) -> Check:
    name = "Phase 3 workflow files present"
    missing = [p for p in _WORKFLOW_FILES if not (repo_root / p).is_file()]
    if missing:
        return _warn(
            name, "missing (Phase 3 has not landed yet): " + ", ".join(missing))
    return _pass(name)


def run_checks(repo_root: Path, version: str, *,
                owner: str = None) -> list:
    """Run every check and return the list of results, in report order.

    `version` must already be normalized (no leading "v") -- see
    normalize_version().
    """
    if owner is None:
        owner = gen_release_compose.DEFAULT_OWNER
    tag = f"v{version}"
    migrations_dir = repo_root / "tubematic_core" / "migrations"

    return [
        check_clean_working_tree(repo_root),
        check_version_matches(repo_root, version),
        check_version_format(version),
        check_tag_not_exists(repo_root, tag),
        check_migrations_ordered(migrations_dir),
        check_migration_immutability(repo_root, migrations_dir),
        check_release_compose(repo_root, version, owner),
        check_tarball_allowlist(repo_root),
        check_tarball_exclusions(repo_root, version, owner),
        check_head_is_on_the_release_line(repo_root, version),
        check_release_notes(repo_root, version),
        check_workflow_files(repo_root),
    ]


def format_report(checks: list) -> str:
    marker = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}
    lines = []
    for c in checks:
        line = f"[{marker[c.status]}] {c.name}"
        if c.detail:
            line += f"\n       {c.detail}"
        lines.append(line)

    n_pass = sum(1 for c in checks if c.status == "pass")
    n_fail = sum(1 for c in checks if c.status == "fail")
    n_warn = sum(1 for c in checks if c.status == "warn")
    lines.append("")
    lines.append(f"{n_pass} passed, {n_fail} failed, {n_warn} warning(s)")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help='Version to check, e.g. "1.2.3" or "v1.2.3"')
    parser.add_argument(
        "--repo-root", default=str(_REPO_ROOT_DEFAULT),
        help="Repo root to check (default: %(default)s)")
    parser.add_argument(
        "--owner", default=gen_release_compose.DEFAULT_OWNER,
        help="GHCR owner/namespace used when generating the release compose "
             "(default: %(default)s)")
    args = parser.parse_args(argv)

    version = normalize_version(args.version)
    repo_root = Path(args.repo_root).resolve()

    checks = run_checks(repo_root, version, owner=args.owner)
    print(format_report(checks))

    return 1 if any(c.status == "fail" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
