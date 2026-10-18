"""Tests for scripts/check_release.py (TMDEV-91 Phase 2).

Each check is exercised in isolation against a real git repository built in
tmp_path with a real `git init` and real commits -- these checks exist to
catch real git conditions (a dirty tree, an existing tag, a modified
committed file), and mocking git would only prove this file's idea of git's
behaviour matches itself.

A separate "all clear" test drives run_checks()/main() end to end against a
minimal-but-complete fixture repo satisfying every check at once, so the
aggregate report and exit code are pinned too, not just the individual
checks.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # scripts/

import pytest

REPO_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, str(REPO_ROOT))

import build_release_tarball  # noqa: E402
from tubematic_core.version import DEV_VERSION, release_line as core_release_line  # noqa: E402
import check_release  # noqa: E402
import gen_release_compose  # noqa: E402

REAL_COMPOSE = REPO_ROOT / "docker-compose.yml"


# ── git test-fixture helpers ─────────────────────────────────────────────────

def _git(repo_root, *args):
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test",
         *args],
        cwd=repo_root, check=True, capture_output=True, text=True,
    )


def _run_git_capture(repo_root, *args) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def _init_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init", "-q")


def _commit_all(repo_root: Path, message: str) -> None:
    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", message)


def _write(path: Path, content: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ── fixture: a complete, all-clear release tree ─────────────────────────────

def _build_all_clear_repo(repo_root: Path, version: str = "1.0.0") -> None:
    """A minimal repo satisfying every check_release check at once: every
    allowlisted path present, a valid compose file, one clean migration,
    committed with nothing left dirty."""
    _init_repo(repo_root)

    _write(repo_root / "VERSION", f"{version}\n")
    for name in build_release_tarball._ROOT_FILES:
        if name != "VERSION":
            _write(repo_root / name)
    for name in build_release_tarball._SCRIPTS_FILES:
        _write(repo_root / "scripts" / name)
    for dirname in build_release_tarball._DIR_TREES:
        _write(repo_root / dirname / "__init__.py")
    for filename in build_release_tarball._DOC_FILES:
        # The release-notes page needs a real section for this version, not
        # the generic placeholder: check_release asserts the notes exist and
        # are actually written, because the workflow publishes them as the
        # GitHub Release body.
        if filename.endswith("release-notes.md"):
            _write(repo_root / filename,
                   f"# Release Notes\n\n## v{version}\n\n### Added\n\n- A thing.\n")
        else:
            _write(repo_root / filename)
    shutil.copy(REAL_COMPOSE, repo_root / "docker-compose.yml")
    _write(repo_root / "tubematic_core" / "migrations" / "__init__.py")
    _write(
        repo_root / "tubematic_core" / "migrations" / "0001_baseline.sql",
        "CREATE TABLE placeholder (id INTEGER);\n",
    )

    _commit_all(repo_root, "initial commit")

    # The release line this version belongs to. An "all clear" repo has one:
    # releases are tagged on release/X.Y.x, and check_head_is_on_the_release_line
    # warns when HEAD is not contained in it. Creating it here keeps that check
    # exercising its pass path rather than its first-release warning.
    _git(repo_root, "branch", core_release_line(version))


# ── normalize_version ────────────────────────────────────────────────────────

def test_normalize_version_leaves_plain_form_untouched():
    assert check_release.normalize_version("1.2.3") == "1.2.3"


def test_normalize_version_strips_leading_v():
    assert check_release.normalize_version("v1.2.3") == "1.2.3"


# ── check_clean_working_tree ─────────────────────────────────────────────────

def test_clean_working_tree_passes_on_a_freshly_committed_repo(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "a.txt")
    _commit_all(repo, "init")

    result = check_release.check_clean_working_tree(repo)

    assert result.status == "pass"


def test_clean_working_tree_fails_on_an_uncommitted_change(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "a.txt")
    _commit_all(repo, "init")
    (repo / "a.txt").write_text("changed\n")

    result = check_release.check_clean_working_tree(repo)

    assert result.status == "fail"
    assert "a.txt" in result.detail


# ── check_version_matches ────────────────────────────────────────────────────

def test_version_matches_passes_when_file_and_requested_version_agree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "VERSION", "1.0.0\n")

    result = check_release.check_version_matches(repo, "1.0.0")

    assert result.status == "pass"


def test_version_mismatch_fails_for_the_plain_form(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "VERSION", "1.0.0\n")

    result = check_release.check_version_matches(
        repo, check_release.normalize_version("9.9.9"))

    assert result.status == "fail"
    assert "1.0.0" in result.detail and "9.9.9" in result.detail


def test_version_mismatch_fails_for_the_v_prefixed_form(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "VERSION", "1.0.0\n")

    result = check_release.check_version_matches(
        repo, check_release.normalize_version("v9.9.9"))

    assert result.status == "fail"
    assert "1.0.0" in result.detail and "9.9.9" in result.detail


def test_v_prefixed_request_matches_once_normalized(tmp_path):
    """The whole point of accepting "v1.2.3": normalizing it must actually
    let it match a VERSION file that has no "v"."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "VERSION", "1.0.0\n")

    result = check_release.check_version_matches(
        repo, check_release.normalize_version("v1.0.0"))

    assert result.status == "pass"


def test_version_matches_fails_when_version_file_is_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    result = check_release.check_version_matches(repo, "1.0.0")

    assert result.status == "fail"


# ── check_version_format ─────────────────────────────────────────────────────

def test_version_format_passes_on_a_plain_semver():
    assert check_release.check_version_format("1.2.3").status == "pass"


def test_version_format_passes_with_a_tag_safe_prerelease_suffix():
    assert check_release.check_version_format("1.2.3-rc.1").status == "pass"


def test_version_format_fails_on_build_metadata():
    """The reproduction from the finding: a legal SemVer version that is an
    illegal Docker tag. `docker compose pull` would fail on every service
    with "invalid reference format" -- this must be caught before a tarball
    is ever built."""
    result = check_release.check_version_format("1.0.0+build meta")

    assert result.status == "fail"
    assert "+" in result.detail
    assert "' '" in result.detail or '" "' in result.detail  # the space is reported too


def test_version_format_reports_every_offending_character_once():
    result = check_release.check_version_format("1.0.0+build meta!!")

    assert result.status == "fail"
    for char in ("+", " ", "!"):
        assert repr(char) in result.detail, result.detail


def test_version_format_fails_on_a_non_numeric_core():
    result = check_release.check_version_format("v1.2.3")  # "v" must already be stripped by the caller
    assert result.status == "fail"


def test_version_format_refuses_to_release_the_development_branch_marker():
    """`develop` is a valid version everywhere a version is used, and the
    compose check accepts it -- so this check is the one thing standing
    between the development branch and a `vdevelop` tag."""
    result = check_release.check_version_format(DEV_VERSION)
    assert result.status == "fail"
    assert "development-branch marker" in result.detail


def test_release_line_check_is_skipped_for_the_development_branch_marker(tmp_path):
    """It must not crash the whole report: release_line() raises for a
    non-release version, and every check runs even after one fails."""
    result = check_release.check_head_is_on_the_release_line(tmp_path, DEV_VERSION)
    assert result.status == "warn"


# ── check_tag_not_exists ─────────────────────────────────────────────────────
#
# Three cases, matching the three git states the two real callers (a
# maintainer at a terminal, and the Phase 3 release workflow running this
# after actions/checkout has already fetched the triggering tag) can put the
# repo in. Each creates the tag for real with `git tag` rather than mocking
# the lookup -- the middle case in particular is the one that proves the CI
# path (tag already resolves locally, pointing at HEAD) actually passes.

def test_tag_not_exists_passes_when_no_such_tag(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "a.txt")
    _commit_all(repo, "init")

    result = check_release.check_tag_not_exists(repo, "v1.0.0")

    assert result.status == "pass"


def test_tag_check_passes_when_the_tag_already_points_at_head(tmp_path):
    """The CI case: the release workflow runs this after actions/checkout
    has already fetched the tag that triggered the run, so the tag exists
    and points at exactly the commit being checked out. That is the release
    being built, not a conflict -- it must pass, not fail unconditionally
    the way an earlier version of this check did."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "a.txt")
    _commit_all(repo, "init")
    _git(repo, "tag", "v1.0.0")  # tags current HEAD for real

    result = check_release.check_tag_not_exists(repo, "v1.0.0")

    assert result.status == "pass"

    # A different, nonexistent tag must be unaffected either way.
    other = check_release.check_tag_not_exists(repo, "v1.0.1")
    assert other.status == "pass"


def test_tag_check_fails_when_the_tag_points_at_a_different_commit(tmp_path):
    """The real danger this check exists for: the version was already
    tagged against different code. Must fail and name both commits so a
    maintainer can see exactly what would be overwritten."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "a.txt")
    _commit_all(repo, "init")
    _git(repo, "tag", "v1.0.0")
    tagged_sha = _run_git_capture(repo, "rev-parse", "v1.0.0")

    _write(repo / "b.txt")
    _commit_all(repo, "second commit")  # HEAD moves past the tag
    head_sha = _run_git_capture(repo, "rev-parse", "HEAD")

    result = check_release.check_tag_not_exists(repo, "v1.0.0")

    assert result.status == "fail"
    assert tagged_sha in result.detail
    assert head_sha in result.detail


# ── check_migrations_ordered (reuses tubematic_core.db.discover) ────────────

def test_migrations_ordered_passes_for_a_valid_set(tmp_path):
    migrations = tmp_path / "migrations"
    _write(migrations / "0001_first.sql", "SELECT 1;\n")
    _write(migrations / "0002_second.sql", "SELECT 1;\n")

    result = check_release.check_migrations_ordered(migrations)

    assert result.status == "pass"


def test_migrations_ordered_fails_on_a_duplicate_version_number(tmp_path):
    migrations = tmp_path / "migrations"
    _write(migrations / "0001_first.sql", "SELECT 1;\n")
    _write(migrations / "0001_also_first.sql", "SELECT 1;\n")

    result = check_release.check_migrations_ordered(migrations)

    assert result.status == "fail"
    assert "duplicate" in result.detail.lower()


# ── check_migration_immutability ─────────────────────────────────────────────

def test_migration_immutability_passes_when_nothing_changed(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "tubematic_core" / "migrations" / "0001_first.sql", "SELECT 1;\n")
    _commit_all(repo, "init")

    result = check_release.check_migration_immutability(
        repo, repo / "tubematic_core" / "migrations")

    assert result.status == "pass"


def test_migration_immutability_fails_when_a_committed_migration_is_modified(tmp_path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    mig = repo / "tubematic_core" / "migrations" / "0001_first.sql"
    _write(mig, "SELECT 1;\n")
    _commit_all(repo, "init")

    mig.write_text("SELECT 2; -- edited a shipped migration\n")

    result = check_release.check_migration_immutability(
        repo, repo / "tubematic_core" / "migrations")

    assert result.status == "fail"
    assert "0001_first.sql" in result.detail


def test_migration_immutability_ignores_an_uncommitted_new_migration(tmp_path):
    """A migration file that is new and not yet committed is legitimate
    in-progress work, not a violation -- see the docstring in
    check_migration_immutability for why."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "tubematic_core" / "migrations" / "0001_first.sql", "SELECT 1;\n")
    _commit_all(repo, "init")

    # A brand-new, never-committed migration file (untracked).
    _write(repo / "tubematic_core" / "migrations" / "0002_second.sql", "SELECT 1;\n")

    result = check_release.check_migration_immutability(
        repo, repo / "tubematic_core" / "migrations")

    assert result.status == "pass"


def test_migration_immutability_ignores_a_staged_but_uncommitted_new_migration(tmp_path):
    """Same as above, but `git add`ed (staged) rather than merely sitting on
    disk -- git reports this as "A", not "M", and only "M" is a violation."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _write(repo / "tubematic_core" / "migrations" / "0001_first.sql", "SELECT 1;\n")
    _commit_all(repo, "init")

    _write(repo / "tubematic_core" / "migrations" / "0002_second.sql", "SELECT 1;\n")
    _git(repo, "add", "-A")

    result = check_release.check_migration_immutability(
        repo, repo / "tubematic_core" / "migrations")

    assert result.status == "pass"


# ── check_release_compose ────────────────────────────────────────────────────

def test_release_compose_passes_on_the_real_compose_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copy(REAL_COMPOSE, repo / "docker-compose.yml")

    result = check_release.check_release_compose(repo, "9.9.9", "some-owner")

    assert result.status == "pass"


def test_release_compose_fails_when_the_compose_file_is_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    result = check_release.check_release_compose(repo, "9.9.9", "some-owner")

    assert result.status == "fail"


def test_release_compose_fails_when_an_unmapped_service_has_a_build_key(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo / "docker-compose.yml", """\
services:
  some-new-service:
    build: .
""")

    result = check_release.check_release_compose(repo, "9.9.9", "some-owner")

    assert result.status == "fail"


# ── check_tarball_allowlist ──────────────────────────────────────────────────

def test_tarball_allowlist_passes_when_every_path_exists(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in build_release_tarball._ROOT_FILES:
        _write(repo / name)
    for name in build_release_tarball._SCRIPTS_FILES:
        _write(repo / "scripts" / name)
    for dirname in build_release_tarball._DIR_TREES:
        _write(repo / dirname / "__init__.py")
    for filename in build_release_tarball._DOC_FILES:
        _write(repo / filename)
    _write(repo / "docker-compose.yml")

    result = check_release.check_tarball_allowlist(repo)

    assert result.status == "pass"


def test_tarball_allowlist_fails_and_names_every_missing_path(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Deliberately leave everything out.

    result = check_release.check_tarball_allowlist(repo)

    assert result.status == "fail"
    assert "VERSION" in result.detail
    assert "scripts/poll.py" in result.detail
    assert "onboard" in result.detail


# ── check_tarball_exclusions ─────────────────────────────────────────────────

def test_tarball_exclusions_passes_on_the_all_clear_repo(tmp_path):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo, version="1.0.0")

    result = check_release.check_tarball_exclusions(repo, "1.0.0", owner="some-owner")

    assert result.status == "pass"


def test_tarball_exclusions_fails_when_a_forbidden_name_rides_along(tmp_path):
    """The half check_tarball_allowlist cannot see: a forbidden path that
    still gets swept into an allowlisted directory tree. `onboard`'s own
    ignore set only excludes "tests"/"__pycache__", so a "mounted" directory
    planted inside it is copied straight through and must be caught by the
    builder's own `_assert_no_forbidden_names` backstop."""
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo, version="1.0.0")
    _write(repo / "onboard" / "mounted" / "leaked.txt")

    result = check_release.check_tarball_exclusions(repo, "1.0.0", owner="some-owner")

    assert result.status == "fail"
    assert "mounted" in result.detail


# ── check_workflow_files ─────────────────────────────────────────────────────

def test_workflow_files_warns_when_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    result = check_release.check_workflow_files(repo)

    assert result.status == "warn"


def test_workflow_files_passes_when_present(tmp_path):
    repo = tmp_path / "repo"
    _write(repo / ".github" / "workflows" / "ci.yml")
    _write(repo / ".github" / "workflows" / "release.yml")

    result = check_release.check_workflow_files(repo)

    assert result.status == "pass"


# ── run_checks() / main() — the all-clear path and overall exit codes ───────

def test_all_clear_repo_passes_every_check_except_the_workflow_warning(tmp_path):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo, version="1.0.0")

    checks = check_release.run_checks(repo, "1.0.0")

    statuses = {c.name: c.status for c in checks}
    for name, status in statuses.items():
        if name == "Phase 3 workflow files present":
            assert status == "warn"
        else:
            assert status == "pass", f"{name} unexpectedly {status}"


def test_main_exits_0_on_the_all_clear_repo_despite_the_warning(tmp_path, capsys):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo, version="1.0.0")

    rc = check_release.main(["1.0.0", "--repo-root", str(repo)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "[WARN]" in out
    assert "[FAIL]" not in out


def test_main_accepts_the_v_prefixed_form_on_the_all_clear_repo(tmp_path, capsys):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo, version="1.0.0")

    rc = check_release.main(["v1.0.0", "--repo-root", str(repo)])

    assert rc == 0


def test_main_exits_1_and_reports_every_failure_when_the_tree_is_dirty_and_version_mismatched(tmp_path, capsys):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo, version="1.0.0")
    (repo / "VERSION").write_text("1.0.0\n")  # sanity: matches the request below
    # Make the tree dirty AFTER the initial commit.
    (repo / "scripts" / "poll.py").write_text("dirty\n")

    rc = check_release.main(["2.0.0", "--repo-root", str(repo)])
    out = capsys.readouterr().out

    assert rc == 1
    # Both independent problems must be visible in one run.
    assert "[FAIL] git working tree is clean" in out
    assert "[FAIL] VERSION matches the requested version" in out
