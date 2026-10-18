"""Tests for scripts/release.py (TMDEV-91 Phase 2).

release.py itself has no logic of its own to speak of -- it is a thin
orchestrator over check_release.run_checks() and
build_release_tarball.build() -- but that thinness is exactly what had no
test coverage: nothing pinned that it actually runs the checks before
building, that a failing check stops it before a tarball is built, or the
single most important property in the module's own docstring: it prints the
git tag/push commands and never runs them. A real git repo is used for that
last one specifically so "never executes them" is verified by absence of a
real tag/branch, not by mocking subprocess and hoping the mock covers every
call site.
"""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # scripts/

import pytest

REPO_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, str(REPO_ROOT))

import build_release_tarball  # noqa: E402
from tubematic_core.version import release_line as core_release_line  # noqa: E402
import check_release  # noqa: E402
import release  # noqa: E402

REAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
TEST_VERSION = "1.0.0"


def _git(repo_root, *args):
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", *args],
        cwd=repo_root, check=True, capture_output=True, text=True,
    )


def _write(path: Path, content: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _build_all_clear_repo(repo_root: Path, version: str = TEST_VERSION) -> None:
    """A minimal repo satisfying every check_release check at once -- same
    shape as test_check_release.py's own fixture helper, duplicated here
    rather than imported across test modules (the existing convention in
    this test suite: each file's fixtures stand alone)."""
    repo_root.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "init", "-q")

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
    import shutil
    shutil.copy(REAL_COMPOSE, repo_root / "docker-compose.yml")
    _write(repo_root / "tubematic_core" / "migrations" / "__init__.py")
    _write(
        repo_root / "tubematic_core" / "migrations" / "0001_baseline.sql",
        "CREATE TABLE placeholder (id INTEGER);\n",
    )

    _git(repo_root, "add", "-A")
    _git(repo_root, "commit", "-q", "-m", "initial commit")

    # The release line this version belongs to. An "all clear" repo has one:
    # releases are tagged on release/X.Y.x, and check_head_is_on_the_release_line
    # warns when HEAD is not contained in it. Creating it here keeps that check
    # exercising its pass path rather than its first-release warning.
    _git(repo_root, "branch", core_release_line(version))


def _tags(repo_root: Path) -> list:
    result = subprocess.run(
        ["git", "tag"], cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return [t for t in result.stdout.splitlines() if t]


def _branches(repo_root: Path) -> list:
    result = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=repo_root, capture_output=True, text=True, check=True,
    )
    return [b for b in result.stdout.splitlines() if b]


# ── The failing-checks path ──────────────────────────────────────────────────

def test_a_failing_check_aborts_before_any_build_and_returns_1(tmp_path, capsys):
    """A dirty working tree is the cheapest way to fail a check without
    touching the tarball allowlist at all."""
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo)
    (repo / "dirty.txt").write_text("uncommitted\n")  # untracked -> dirty tree

    rc = release.main([TEST_VERSION, "--repo-root", str(repo),
                        "--out-dir", str(tmp_path / "dist")])
    out = capsys.readouterr()

    assert rc == 1
    assert "pre-flight checks failed" in out.err
    assert not (tmp_path / "dist").exists() or not any((tmp_path / "dist").iterdir())
    assert "Built:" not in out.out


def test_checks_run_before_the_build_is_attempted(tmp_path, monkeypatch, capsys):
    """run_checks() must be consulted, not skipped -- monkeypatch it to
    report a failure that the fixture repo would not otherwise produce, and
    confirm build_release_tarball.build is never reached."""
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo)

    called = {"build": False}

    def _fake_build(*a, **k):
        called["build"] = True
        raise AssertionError("build must not run when pre-flight checks fail")

    monkeypatch.setattr(release.build_release_tarball, "build", _fake_build)
    monkeypatch.setattr(
        release.check_release, "run_checks",
        lambda *a, **k: [release.check_release._fail("fake check", "forced failure")],
    )

    rc = release.main([TEST_VERSION, "--repo-root", str(repo),
                        "--out-dir", str(tmp_path / "dist")])

    assert rc == 1
    assert called["build"] is False


# ── The all-clear path ───────────────────────────────────────────────────────

def test_the_all_clear_path_builds_and_prints_next_steps_without_running_them(tmp_path, capsys):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo)
    out_dir = tmp_path / "dist"

    before_tags = _tags(repo)
    before_branches = _branches(repo)

    rc = release.main([TEST_VERSION, "--repo-root", str(repo), "--out-dir", str(out_dir)])
    out = capsys.readouterr()

    assert rc == 0
    assert "Built:" in out.out
    built = list(out_dir.glob("*.tar.gz"))
    assert len(built) == 1, built

    # The release-notes skeleton and the git commands are printed...
    # The skeleton heading is the shape release_notes.py extracts (`## vX.Y.Z`).
    assert f"## v{TEST_VERSION}\n" in out.out
    assert f"git tag -a v{TEST_VERSION}" in out.out
    assert f"git push origin v{TEST_VERSION}" in out.out
    # The release LINE, not a branch per release: 1.0.1 and 1.0.2 are both
    # tags on release/1.0.x, so the branch name carries `.x` and no version
    # patch component.
    major, minor, _ = TEST_VERSION.split(".", 2)
    assert f"git checkout -b release/{major}.{minor}.x" in out.out
    assert f"release/v{TEST_VERSION}" not in out.out, (
        "a branch named for a point release stops describing its own contents "
        "as soon as a patch lands on it"
    )
    # Both shapes are printed -- creating the line, and patching an existing
    # one -- because a script cannot tell which applies on a fresh clone.
    assert f"git checkout release/{major}.{minor}.x" in out.out
    assert "git cherry-pick -x" in out.out
    assert "Next steps (run these yourself" in out.out

    # ...but never actually run: no new tag, no new branch, in the real repo.
    assert _tags(repo) == before_tags
    assert _branches(repo) == before_branches


def test_a_tarball_build_failure_aborts_after_checks_pass(tmp_path, monkeypatch, capsys):
    """check_release.run_checks() itself calls build_release_tarball.build()
    (check_tarball_exclusions, into its own scratch tempdir) -- the same
    module object release.py imports -- so the fake below only fails the
    call aimed at this test's own --out-dir, and lets every other build
    (the pre-flight one included) run for real."""
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo)
    target_out_dir = tmp_path / "dist"
    real_build = build_release_tarball.build

    def _raise(version, *, repo_root, out_dir, owner=None):
        if Path(out_dir) == target_out_dir:
            raise build_release_tarball.ReleaseBuildError("simulated build failure")
        return real_build(version, repo_root=repo_root, out_dir=out_dir, owner=owner)

    monkeypatch.setattr(release.build_release_tarball, "build", _raise)

    rc = release.main([TEST_VERSION, "--repo-root", str(repo),
                        "--out-dir", str(tmp_path / "dist")])
    out = capsys.readouterr()

    assert rc == 1
    assert "simulated build failure" in out.err
    assert "Built:" not in out.out
    assert "Next steps" not in out.out


def test_accepts_the_v_prefixed_form(tmp_path, capsys):
    repo = tmp_path / "repo"
    _build_all_clear_repo(repo)

    rc = release.main([f"v{TEST_VERSION}", "--repo-root", str(repo),
                        "--out-dir", str(tmp_path / "dist")])

    assert rc == 0
