"""Tests for scripts/build_release_tarball.py (TMDEV-91 Phase 2).

Builds the real release tarball from this actual repo checkout, not a
fixture tree -- a fixture would let the real allowlist drift away from what
the builder is actually tested on. Every test in this file shares one
module-scoped build (see the `archive` fixture) so the (cheap but not free)
tar+gzip pass only happens once per test session.

Two tests are the ones that actually matter and must not be weakened:

- test_the_archive_excludes_every_forbidden_pattern asserts ABSENCE of every
  excluded path explicitly. The failure mode this guards is a release
  tarball, published on a public download page, silently carrying a
  developer's local state or a secret.
- test_the_extracted_tree_can_import_onboard_and_tubematic_core is the real
  test of the allowlist: it extracts the archive and imports the packages a
  release install actually needs, in a subprocess (so an already-imported
  module in the test session can't mask a copy-list gap). This exact trap
  --  a module joining the import graph but not a copy list -- has bitten
  this repo three times before (transcripts.py, postforme.py,
  discord_notify.py, all via vqa/tests/test_reset_db.py).
"""
import hashlib
import os
import posixpath
import re
import subprocess
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # scripts/

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, REPO_ROOT)

from tubematic_core.version import version as core_version  # noqa: E402

import build_release_tarball  # noqa: E402

TEST_VERSION = "9.9.9"  # distinguishable from whatever VERSION currently holds
OWNER = "some-owner"

# Internal ticket references. Fine in Python "#" comments and private-helper
# docstrings (CLAUDE.md's Conventions section keeps those deliberately, for
# dev traceability) but not in prose a customer reads -- and this archive is
# a public download, so any non-.py text file it ships is that prose.
_TICKET_ID_RE = re.compile(r"\b(?:TMDEV|VQA|EXQA)-\d+\b")

# A markdown link whose target is a relative path ending in ".md" (an
# optional "#anchor" is captured separately and dropped) -- covers both
# shapes real offenders have taken: an explicit "docs/" prefix (root guides
# linking into docs/) and a bare filename (docs/19 linking to a sibling
# page the way every file inside docs/ addresses another). A pure in-page
# anchor like "(#rollback-policy)" has no ".md" in it and never matches.
_MD_LINK_RE = re.compile(r"\]\(([^)\s]+\.md)(?:#[^)\s]*)?\)")
_EXTERNAL_LINK_PREFIXES = ("http://", "https://", "mailto:")

# Every path the brief's allowlist requires to be present, spelled as the
# archive-relative path under the versioned top directory.
ALLOWLISTED_PATHS = [
    "VERSION",
    "docker-compose.yml",
    "onboard.py",
    "onboard/config.py",
    "onboard/actions.py",
    "onboard/steps.py",
    "onboard/bootstrap.py",
    "onboard/stack.py",
    "upgrade.py",
    "tubematic_core/__init__.py",
    "tubematic_core/db.py",
    "tubematic_core/migrations/0001_baseline.py",
    "scripts/poll.py",
    "scripts/status.py",
    "scripts/config.py",
    "scripts/agent_adapters.py",
    "scripts/requirements.txt",
    "scripts/migrate_db.py",
    "scripts/backup_db.py",
    "scripts/print_version.py",
    "scripts/mcp_auth_header.py",
    "tubematic_core/auth.py",
    "scripts/service.py",
    "scripts/collect_diagnostics.py",
    "docs/README.md",
    "docs/quickstart.md",
    "docs/release-notes.md",
    "docs/user-guide/07-upgrading.md",
    "docs/developer/01-architecture.md",
    "agent_files/skills",
    "agent_files/claude/commands",
    "uninstall.py",
    "INSTALL.md",
    "USAGE.md",
    "UNINSTALL.md",
    "CHECKSUMS.txt",
]

# Fragments that must never appear anywhere in the archive's member list.
# Spelled loosely (substrings) on purpose -- a fragment like "renderer/"
# must not show up as a nested path either, not just at the top level.
FORBIDDEN_FRAGMENTS = [
    "renderer/", "dashboard/", "mcp/", "vqa/", "kasm_workspace/",
    "remotion/", "schemas/",
    "node_modules/", ".next/", ".venv/", ".git/", ".worktrees/",
    ".superpowers/",
    "mounted/", "dist/", "__pycache__", ".pytest_cache",
    "plan/", "code_review/",
    "docs/superpowers",
    ".env", ".env.example",
    "HANDOFF.md", ".onboard-state.json",
    # A different trap: onboard/'s and tubematic_core/'s own test suites
    # must not ship either.
    "onboard/tests/", "tubematic_core/tests/",
]


def _top_name(version):
    return f"tubematic-v{version}"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("dist")
    path = build_release_tarball.build(
        TEST_VERSION, repo_root=REPO_ROOT, out_dir=out_dir, owner=OWNER,
    )
    return path


@pytest.fixture(scope="module")
def names(built):
    with tarfile.open(built, "r:gz") as tar:
        return tar.getnames()


@pytest.fixture(scope="module")
def tar_members(built):
    with tarfile.open(built, "r:gz") as tar:
        return {m.name: m for m in tar.getmembers()}


def test_the_archive_contains_every_allowlisted_path(names):
    top = _top_name(TEST_VERSION)
    for rel in ALLOWLISTED_PATHS:
        expected = f"{top}/{rel}"
        assert any(n == expected or n.startswith(expected + "/") for n in names), (
            f"missing from archive: {expected}"
        )


def test_the_archive_excludes_every_forbidden_pattern(names):
    """Asserting absence explicitly, because the failure mode is shipping a
    developer's local state or a secret to a public release page."""
    for fragment in FORBIDDEN_FRAGMENTS:
        offenders = [n for n in names if fragment in n]
        assert offenders == [], (fragment, offenders)


def test_no_ticket_ids_leak_into_the_files_the_archive_ships(built):
    """The archive is a public download; a prose file that mentions
    TMDEV-/VQA-/EXQA- is referencing a ticket its reader cannot look up.
    Source files are exempt -- internal comments and private-helper
    docstrings keep ticket IDs deliberately, by repo convention -- so this
    guards the public-prose surface (root guides, skills, commands,
    READMEs), which is exactly what INSTALL.md/USAGE.md are, and exactly
    what a future edit to them will not be thinking about this archive.

    .sql is exempt for the same reason .py is, and the pair has to move
    together: the only .sql files the archive ships are migrations, sitting
    beside 0001_baseline.py, which keeps its ticket IDs. Exempting one and
    not the other makes the rule depend on which language a migration
    happened to be written in -- and the next author to write a SQL
    migration would hit this failure with nothing explaining why."""
    offenders = []
    with tarfile.open(built, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or member.name.endswith((".py", ".sql")):
                continue
            data = tar.extractfile(member).read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if _TICKET_ID_RE.search(text):
                offenders.append(member.name)
    assert offenders == []


def test_no_relative_docs_links_point_outside_the_archive(built):
    """TMDEV-91 Phase 4, widened by TMDEV-166: the tarball ships the public
    docs (docs/README.md, the release notes, docs/user-guide/ and
    docs/developer/) but never the whole docs/ tree, which also holds the
    gitignored docs/superpowers/. A root guide that links a page outside that
    set reads perfectly well to a git-
    checkout reader and 404s for exactly the audience the archive is built
    for: someone who has only ever extracted the tarball. INSTALL.md:201 and
    UNINSTALL.md:11 shipped that way once with nothing catching it, because
    the link was correct everywhere the person adding it could see it --
    their own checkout.

    Round 2 of the same gap, caught by review rather than by this test the
    first time: docs/19 itself cross-links four sibling pages by BARE
    filename (`](05-database.md#migrations)`, no "docs/" prefix) -- the
    normal way a file inside docs/ addresses another file inside docs/. The
    first version of this test matched only the explicit-"docs/"-prefix
    shape and walked straight past all 13 of those, in the one page a
    tarball reader actually opens. Resolving every ".md" link target
    relative to the *linking file's own directory in the archive* (not
    always the top level) catches both shapes in one pass: a root guide's
    "docs/X.md" resolves against the archive root; docs/19's own "X.md"
    resolves against docs/ -- exactly mirroring how a browser or GitHub
    would resolve the same relative link, which is why this is the correct
    general rule rather than two special cases."""
    offenders = []
    with tarfile.open(built, "r:gz") as tar:
        members = tar.getmembers()
        archived = {m.name for m in members}
        for member in members:
            if not member.isfile() or member.name.endswith(".py"):
                continue
            data = tar.extractfile(member).read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            member_dir = posixpath.dirname(member.name)
            for target in _MD_LINK_RE.findall(text):
                if target.startswith(_EXTERNAL_LINK_PREFIXES) or target.startswith("/"):
                    continue
                resolved = posixpath.normpath(posixpath.join(member_dir, target))
                if resolved not in archived:
                    offenders.append((member.name, target))
    assert offenders == []


def test_the_compose_file_inside_is_the_generated_release_one(built):
    """Named docker-compose.yml, not docker-compose.release.yml: the tarball
    carries no other compose file, so the suffix only ever avoided a
    collision that does not happen here -- and a release user should be
    able to run a bare `docker compose up -d` with no -f flag."""
    top = _top_name(TEST_VERSION)
    with tarfile.open(built, "r:gz") as tar:
        names_ = tar.getnames()
        # By name, not every .yml: a skill may carry agent config such as
        # agents/openai.yaml, which is not a compose file.
        compose_names = [n for n in names_ if "compose" in n.rsplit("/", 1)[-1]
                         and (n.endswith(".yml") or n.endswith(".yaml"))]
        assert compose_names == [f"{top}/docker-compose.yml"]


def test_the_compose_file_inside_references_ghcr_and_has_no_build_key(built):
    top = _top_name(TEST_VERSION)
    with tarfile.open(built, "r:gz") as tar:
        text = tar.extractfile(f"{top}/docker-compose.yml").read().decode()
    assert "build:" not in text
    assert f"ghcr.io/{OWNER}/tubematic-" in text
    assert TEST_VERSION in text


def test_migrations_are_included(names):
    """A release install runs migrate() during onboarding. A tarball without
    tubematic_core/migrations/ produces a database with no schema at all."""
    top = _top_name(TEST_VERSION)
    assert f"{top}/tubematic_core/migrations/0001_baseline.py" in names


def test_building_twice_produces_identical_bytes(tmp_path):
    """Reproducibility is what makes a changed checksum mean a changed
    input."""
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    path1 = build_release_tarball.build(
        TEST_VERSION, repo_root=REPO_ROOT, out_dir=out1, owner=OWNER,
    )
    path2 = build_release_tarball.build(
        TEST_VERSION, repo_root=REPO_ROOT, out_dir=out2, owner=OWNER,
    )
    assert path1.read_bytes() == path2.read_bytes()


def test_checksums_cover_every_file_except_itself(built):
    top = _top_name(TEST_VERSION)
    with tarfile.open(built, "r:gz") as tar:
        members = tar.getmembers()
        checksums_text = tar.extractfile(f"{top}/CHECKSUMS.txt").read().decode()
        file_members = [m for m in members if m.isfile()]

        checksummed_paths = set()
        for line in checksums_text.strip().splitlines():
            digest, _, rel = line.partition("  ")
            assert len(digest) == 64, line
            checksummed_paths.add(rel)

        expected_paths = {
            m.name[len(top) + 1:] for m in file_members
            if m.name != f"{top}/CHECKSUMS.txt"
        }
        assert checksummed_paths == expected_paths
        assert "CHECKSUMS.txt" not in checksummed_paths

        # Spot-check one digest actually matches the file's real content.
        vf = tar.extractfile(f"{top}/VERSION").read()
        expected_digest = hashlib.sha256(vf).hexdigest()
        for line in checksums_text.strip().splitlines():
            digest, _, rel = line.partition("  ")
            if rel == "VERSION":
                assert digest == expected_digest
                break
        else:
            pytest.fail("VERSION not found in CHECKSUMS.txt")


def test_a_missing_allowlisted_path_fails_the_build(tmp_path, monkeypatch):
    # A repo root missing an allowlisted file (INSTALL.md) must fail loudly,
    # not silently ship a tarball with a hole in it.
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    for name in ["VERSION", "onboard.py", "uninstall.py", "USAGE.md", "UNINSTALL.md",
                 "docker-compose.yml"]:
        (fake_repo / name).write_text("placeholder\n")
    # deliberately omit INSTALL.md

    with pytest.raises(build_release_tarball.ReleaseBuildError):
        build_release_tarball.build(
            TEST_VERSION, repo_root=fake_repo, out_dir=tmp_path / "out", owner=OWNER,
        )


def _complete_fake_repo(root: Path) -> None:
    """A minimal repo satisfying every allowlist requirement build() has --
    unlike test_a_missing_allowlisted_path_fails_the_build's fixture (which
    is deliberately incomplete and fails before staging even reaches the
    directory trees), this one is complete, so a test using it exercises
    whatever build() does *after* staging succeeds."""
    for name in build_release_tarball._ROOT_FILES:
        (root / name).write_text("placeholder\n")
    scripts_dir = root / "scripts"
    scripts_dir.mkdir()
    for name in build_release_tarball._SCRIPTS_FILES:
        (scripts_dir / name).write_text("placeholder\n")
    for dirname in build_release_tarball._DIR_TREES:
        (root / dirname).mkdir(parents=True)
        (root / dirname / "__init__.py").write_text("")
    for rel in build_release_tarball._DOC_FILES:
        doc_path = root / rel
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text("placeholder\n")
    (root / "docker-compose.yml").write_text("services: {}\n")


def test_a_developers_pytest_cache_does_not_break_the_build(tmp_path):
    """pytest writes a .pytest_cache INSIDE each suite directory, so
    onboard/.pytest_cache and tubematic_core/.pytest_cache exist on the
    machine of anyone who has run the tests -- which is everyone about to cut
    a release. `.pytest_cache` is also in _FORBIDDEN_NAMES, so before it was
    added to each tree's prune set the backstop fired and the build died with
    "excluded pattern found in staged tree" for a purely local reason,
    blocking check_release.py until the maintainer worked out what to delete.

    Git hides this: pytest drops a .gitignore containing `*` into each cache,
    so `git status` shows nothing and the directories are invisible until a
    tool walks the filesystem directly, as this one does.

    The build must succeed and the cache must not appear in the archive.
    """
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    _complete_fake_repo(fake_repo)
    for tree in build_release_tarball._DIR_TREES:
        cache = fake_repo / tree / ".pytest_cache" / "v" / "cache"
        cache.mkdir(parents=True)
        (cache / "lastfailed").write_text("{}\n")

    out = build_release_tarball.build(
        TEST_VERSION, repo_root=fake_repo, out_dir=tmp_path / "out", owner=OWNER,
    )

    import tarfile
    with tarfile.open(out) as tf:
        names = tf.getnames()
    assert not [n for n in names if ".pytest_cache" in n], (
        "a developer's pytest cache was staged into the release archive")


def test_forbidden_name_guard_raises_when_one_is_staged(tmp_path):
    """The fail-loud path itself, never exercised until now --
    test_the_archive_excludes_every_forbidden_pattern only asserts absence
    in the real repo's own (clean) output, which proves the guard has never
    fired, not that it works. `onboard`'s own ignore set only excludes
    "tests"/"__pycache__", so a "mounted" directory planted inside it rides
    straight through `_copytree_excluding` and must be caught by the
    whole-tree `_assert_no_forbidden_names` sweep instead."""
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    _complete_fake_repo(fake_repo)
    (fake_repo / "onboard" / "mounted").mkdir()
    (fake_repo / "onboard" / "mounted" / "leaked.txt").write_text("oops\n")

    with pytest.raises(build_release_tarball.ReleaseBuildError, match="mounted"):
        build_release_tarball.build(
            TEST_VERSION, repo_root=fake_repo, out_dir=tmp_path / "out", owner=OWNER,
        )


def test_a_clean_fake_repo_builds_without_the_forbidden_name_guard_firing(tmp_path):
    """Sanity check for the fixture itself: _complete_fake_repo alone must
    not trip the guard, so the failure above is caused by the planted
    "mounted" directory and nothing else about the fixture."""
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    _complete_fake_repo(fake_repo)

    build_release_tarball.build(
        TEST_VERSION, repo_root=fake_repo, out_dir=tmp_path / "out", owner=OWNER,
    )


def test_the_top_level_directory_is_versioned(names):
    top = _top_name(TEST_VERSION)
    assert all(n == top or n.startswith(top + "/") for n in names)
    assert top in names


def test_the_extracted_tree_can_import_onboard_and_tubematic_core(built, tmp_path):
    """The real test of the allowlist: extract to a temp dir and, in a
    subprocess rooted there, import onboard.actions, onboard.steps,
    onboard.config and tubematic_core.db. This is the same trap
    vqa/tests/test_reset_db.py sprang three times -- a module added to the
    import graph but not to a copy list fails only at install time."""
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    with tarfile.open(built, "r:gz") as tar:
        tar.extractall(extract_dir, filter="data")

    top = _top_name(TEST_VERSION)
    install_root = extract_dir / top

    result = subprocess.run(
        [sys.executable, "-c",
         "import onboard.actions, onboard.steps, onboard.config, tubematic_core.db"],
        cwd=str(install_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_reproducible_tar_metadata(tar_members):
    """Every entry carries fixed mtime/uid/gid/uname/gname -- if the same
    commit produced different metadata on different runs, a changed
    checksum would stop meaning "the input changed"."""
    for member in tar_members.values():
        assert member.mtime == 0
        assert member.uid == 0
        assert member.gid == 0
        assert member.uname != ""
        assert member.gname != ""


def test_default_version_comes_from_tubematic_core(tmp_path):
    """main() with no --version must use tubematic_core.version.version(),
    never a literal."""
    rc = build_release_tarball.main([
        "--repo-root", REPO_ROOT,
        "--out-dir", str(tmp_path),
        "--owner", OWNER,
    ])
    assert rc == 0
    expected = tmp_path / f"tubematic-v{core_version()}.tar.gz"
    assert expected.exists()
