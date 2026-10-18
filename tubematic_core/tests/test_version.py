"""The canonical version source (TMDEV-91)."""
import pathlib
import re
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import version as tv  # noqa: E402


def test_version_reads_the_version_file():
    assert tv.version() == (REPO_ROOT / "VERSION").read_text().strip()


def test_version_is_semver():
    """Checked against tubematic_core.version.VERSION_RE, the same definition
    the release tooling validates against -- never a second, hand-rolled rule.

    This previously asserted every dot-separated part was a digit, which
    rejected the "1.0.0-rc.1" prereleases check_release.py documents and
    accepts. Setting VERSION to a prerelease therefore broke CI on exactly
    the rehearsal release the tooling was built to support.
    """
    assert tv.is_valid(tv.version()), tv.version()


def test_the_version_rule_accepts_prereleases_and_rejects_build_metadata():
    """Pins both edges of the shared rule, so a future tightening that would
    re-break prereleases fails here rather than in a release run."""
    for ok in ["1.0.0", "1.0.0-rc.1", "1.0.0-pretest1", "0.0.1-alpha", "1.0.0-RC1"]:
        assert tv.is_valid(ok), ok
    for bad in ["1.0", "1.0.0.1", "1.0.0+build", "v1.0.0", "1.0.0_rc1", "", "Develop", "dev"]:
        assert not tv.is_valid(bad), bad


def test_the_development_branch_marker_is_valid_but_never_a_release():
    """The development branch's VERSION holds DEV_VERSION rather than a number.
    It must pass wherever a version is used, and fail wherever one is released
    -- is_release() is the gate the release tooling checks."""
    assert tv.DEV_VERSION == "develop"
    assert tv.is_valid(tv.DEV_VERSION)
    assert not tv.is_release(tv.DEV_VERSION)
    assert tv.is_release("1.0.0") and tv.is_release("1.0.0-rc.1")


def test_version_file_has_no_v_prefix():
    """Git tags carry the `v`; the file does not. check_release.py compares them."""
    assert not (REPO_ROOT / "VERSION").read_text().strip().startswith("v")


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("TUBEMATIC_VERSION", "9.9.9")
    assert tv.version() == "9.9.9"


def test_blank_env_override_is_ignored(monkeypatch):
    """An unset-but-exported shell variable must not blank the version."""
    monkeypatch.setenv("TUBEMATIC_VERSION", "   ")
    assert tv.version() == (REPO_ROOT / "VERSION").read_text().strip()


def test_version_file_sits_beside_the_package(monkeypatch, tmp_path):
    """The lookup rule is 'beside the package directory', which is what makes the
    Dockerfile's `COPY VERSION /app/lib/VERSION` resolve identically in-container."""
    pkg = tmp_path / "tubematic_core"
    pkg.mkdir()
    (tmp_path / "VERSION").write_text("2.3.4\n")
    monkeypatch.setattr(tv, "_PACKAGE_DIR", pkg)
    monkeypatch.delenv("TUBEMATIC_VERSION", raising=False)
    assert tv.version() == "2.3.4"


def test_github_repo_is_a_bare_lowercase_owner_and_name():
    """GITHUB_REPO is pasted into github.com URLs and `gh --repo`, and its owner
    is the default GHCR namespace, which Docker refuses in upper case. So it must
    be exactly `owner/name`: no scheme, no host, no `.git`, no capitals."""
    assert re.fullmatch(r"[a-z0-9-]+/[a-z0-9._-]+", tv.GITHUB_REPO), tv.GITHUB_REPO
    assert not tv.GITHUB_REPO.endswith(".git")
