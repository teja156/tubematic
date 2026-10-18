#!/usr/bin/env python3
"""Build the curated release tarball (TMDEV-91 Phase 2, spec section 5.1).

This is the artifact a user actually downloads and installs from --
`dist/tubematic-v<version>.tar.gz`. It is built from an explicit allowlist,
never a copy of the whole repo, because the repo also holds source trees
(`renderer/`, `dashboard/`, `mcp/`, `vqa/`), local state (`.onboard-state.json`,
`mounted/`), a dev-only compose file, and `.env`/`.env.example` -- none of
which belong on a public download page.

Two invariants make this trustworthy rather than merely convenient:

1. Reproducibility. Every archive entry gets a fixed mtime/uid/gid/uname/
   gname, and entries are written in sorted-path order. Building the same
   commit twice must produce byte-identical output, or a changed checksum
   stops meaning "the input changed" and starts meaning nothing.
2. Fail loud. If an allowlisted path is missing from the repo, or an
   excluded pattern somehow makes it into the staged tree, the build raises
   -- it does not warn and ship a hole, and it does not warn and ship a leak.

Run from the repo root:
    python scripts/build_release_tarball.py
    python scripts/build_release_tarball.py --owner someone --out-dir /tmp/out
"""
import argparse
import gzip
import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_REPO_ROOT_DEFAULT))

from tubematic_core.version import version as core_version  # noqa: E402

# gen_release_compose.py owns the PyYAML dependency check (it is the module
# that actually imports yaml) and exits with a clear message if it is
# missing -- that exit is a SystemExit, which a `except ModuleNotFoundError`
# here cannot catch, so a second guard around this import would be dead code
# pretending to handle a failure it can never see.
import gen_release_compose


class ReleaseBuildError(Exception):
    """An allowlisted path is missing, or an excluded pattern was found in
    the staged tree. Both are build-time failures, never warnings -- a
    silently incomplete or silently leaky release tarball is worse than a
    build that stops."""


# ── The allowlist (spec section 5.1) ────────────────────────────────────────

# Single files copied verbatim from the repo root.
_ROOT_FILES = [
    "VERSION",
    "onboard.py",
    "upgrade.py",
    "uninstall.py",
    "INSTALL.md",
    "USAGE.md",
    "UNINSTALL.md",
]

# scripts/ is NOT copied wholesale -- gen_release_compose.py itself, and the
# other host-only maintenance scripts (cleanup_jobs.py, clear_db.py, this
# script), have no role in a release install.
_SCRIPTS_FILES = [
    "poll.py",
    "status.py",
    "config.py",
    "agent_adapters.py",
    "requirements.txt",
    "migrate_db.py",
    "backup_db.py",
    "print_version.py",
    "mcp_auth_header.py",   # the agent CLIs run it on every MCP connection (TMDEV-152)
    "service.py",
    "collect_diagnostics.py",   # the troubleshooting skill asks the human to run it (TMDEV-167)
]

# The public documentation, copied by explicit path -- never a bare "docs/"
# tree. A maintainer's checkout also holds docs/superpowers/
# (gitignored, never public), so copying docs/ wholesale would need its own
# exclude list to keep it out -- exactly the kind of second, driftable list
# this allowlist exists to avoid. The two audience folders are copied whole
# (see _DIR_TREES) because the user guide links into the developer pages, and
# the dead-link guard resolves links against the archive's own contents -- a
# shipped page linking to an unshipped one fails the build.
_DOC_FILES = [
    "docs/README.md",
    "docs/quickstart.md",
    "docs/release-notes.md",
]

# Whole package trees, each with names to prune at any depth. onboard/ and
# tubematic_core/ drop their own test suites; every tree drops __pycache__.
# Per-tree names to prune at any depth. `.pytest_cache` is here alongside
# `__pycache__` for a reason worth stating: pytest writes one INSIDE each
# suite directory, so `onboard/.pytest_cache` and
# `tubematic_core/.pytest_cache` exist on the machine of anyone who has run
# the tests -- which is everyone about to cut a release. Both names are also
# in _FORBIDDEN_NAMES, so without pruning them here the backstop fires and
# the build fails with "excluded pattern found in staged tree" for a purely
# local reason, blocking check_release.py and the tarball until the
# maintainer works out what to delete. Pruned here, caught there: the
# backstop stays as defence against a future allowlist entry sweeping one
# in, it just stops being the first line of defence against ordinary
# developer droppings.
_DIR_TREES = {
    "onboard": {"tests", "__pycache__", ".pytest_cache"},
    "tubematic_core": {"tests", "__pycache__", ".pytest_cache"},
    "agent_files": {"__pycache__", ".pytest_cache"},
    "docs/user-guide": {"__pycache__", ".pytest_cache"},
    "docs/developer": {"__pycache__", ".pytest_cache"},
}

# Basenames that must never appear anywhere in the staged tree. Checked as a
# defense-in-depth invariant after staging -- the copy logic above is
# allowlist-driven and should never produce any of these, but a future
# allowlist entry (e.g. a bare "docs/") sweeping one of these in behind it
# is exactly the failure mode this guards against.
_FORBIDDEN_NAMES = {
    "renderer", "dashboard", "mcp", "vqa", "kasm_workspace", "remotion", "schemas",
    "node_modules", ".next", ".venv", ".git", ".worktrees", ".superpowers",
    "superpowers",
    "mounted", "dist", "__pycache__", ".pytest_cache", "plan", "code_review",
    ".env", ".env.example", "HANDOFF.md", ".onboard-state.json",
    # Generic, on top of each _DIR_TREES entry's own ignore set: a future
    # package added to the copy list without one would otherwise slip its
    # test suite in undetected.
    "tests",
}

# ── Reproducibility ──────────────────────────────────────────────────────────

_FIXED_MTIME = 0
_FIXED_UID = 0
_FIXED_GID = 0
_FIXED_UNAME = "tubematic"
_FIXED_GNAME = "tubematic"


def _reproducible_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo:
    tarinfo.mtime = _FIXED_MTIME
    tarinfo.uid = _FIXED_UID
    tarinfo.gid = _FIXED_GID
    tarinfo.uname = _FIXED_UNAME
    tarinfo.gname = _FIXED_GNAME
    if tarinfo.isdir():
        tarinfo.mode = 0o755
    else:
        tarinfo.mode = 0o755 if tarinfo.mode & 0o111 else 0o644
    return tarinfo


# ── Staging ──────────────────────────────────────────────────────────────────

def _require_file(src: Path, label: str) -> None:
    if not src.is_file():
        raise ReleaseBuildError(f"allowlisted file is missing from the repo: {label}")


def _require_dir(src: Path, label: str) -> None:
    if not src.is_dir():
        raise ReleaseBuildError(f"allowlisted directory is missing from the repo: {label}")


def _copytree_excluding(src: Path, dst: Path, excluded_names: set) -> None:
    def _ignore(_dir, names):
        return [n for n in names if n in excluded_names]

    shutil.copytree(src, dst, ignore=_ignore)


def _copy_allowlist(repo_root: Path, stage_root: Path, version: str, owner: str) -> None:
    for name in _ROOT_FILES:
        src = repo_root / name
        _require_file(src, name)
        shutil.copy2(src, stage_root / name)

    scripts_dst = stage_root / "scripts"
    scripts_dst.mkdir()
    for name in _SCRIPTS_FILES:
        src = repo_root / "scripts" / name
        _require_file(src, f"scripts/{name}")
        shutil.copy2(src, scripts_dst / name)

    for name, excluded in _DIR_TREES.items():
        src = repo_root / name
        _require_dir(src, name)
        _copytree_excluding(src, stage_root / name, excluded)

    for rel in _DOC_FILES:
        src = repo_root / rel
        _require_file(src, rel)
        dst = stage_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    compose_src = repo_root / "docker-compose.yml"
    _require_file(compose_src, "docker-compose.yml")
    compose_text = gen_release_compose.generate(compose_src, version, owner=owner)
    (stage_root / "docker-compose.yml").write_text(compose_text)


def _assert_no_forbidden_names(stage_root: Path) -> None:
    for path in stage_root.rglob("*"):
        if path.name in _FORBIDDEN_NAMES:
            raise ReleaseBuildError(
                f"excluded pattern found in staged tree: "
                f"{path.relative_to(stage_root)}"
            )


def _write_checksums(stage_root: Path) -> None:
    lines = []
    for path in sorted(p for p in stage_root.rglob("*") if p.is_file()):
        rel = path.relative_to(stage_root).as_posix()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    (stage_root / "CHECKSUMS.txt").write_text("\n".join(lines) + "\n")


def _write_tarball(stage_root: Path, archive_path: Path, top_name: str) -> None:
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        tar.add(stage_root, arcname=top_name, recursive=False, filter=_reproducible_filter)
        entries = sorted(
            stage_root.rglob("*"),
            key=lambda p: p.relative_to(stage_root).as_posix(),
        )
        for path in entries:
            arcname = f"{top_name}/{path.relative_to(stage_root).as_posix()}"
            tar.add(path, arcname=arcname, recursive=False, filter=_reproducible_filter)

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with open(archive_path, "wb") as f:
        # filename="" and mtime=0 keep the gzip header itself reproducible --
        # gzip otherwise embeds the output filename and the current time.
        with gzip.GzipFile(filename="", fileobj=f, mode="wb", mtime=0) as gz:
            gz.write(tar_buf.getvalue())


def build(version: str, *, repo_root, out_dir, owner: str = None) -> Path:
    """Build dist/tubematic-v<version>.tar.gz and return its path.

    `owner` defaults to gen_release_compose.DEFAULT_OWNER but is threaded
    through explicitly (never relying on generate()'s own default) so a
    release cannot silently pick up the wrong GHCR namespace.
    """
    if owner is None:
        owner = gen_release_compose.DEFAULT_OWNER

    repo_root = Path(repo_root).resolve()
    out_dir = Path(out_dir).resolve()
    top_name = f"tubematic-v{version}"

    with tempfile.TemporaryDirectory(prefix="tubematic-release-") as scratch:
        stage_root = Path(scratch) / top_name
        stage_root.mkdir()

        _copy_allowlist(repo_root, stage_root, version, owner)
        _assert_no_forbidden_names(stage_root)
        _write_checksums(stage_root)

        archive_path = out_dir / f"{top_name}.tar.gz"
        _write_tarball(stage_root, archive_path, top_name)

    return archive_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", default=str(_REPO_ROOT_DEFAULT),
        help="Repo root to build from (default: %(default)s)")
    parser.add_argument(
        "--out-dir", default=str(_REPO_ROOT_DEFAULT / "dist"),
        help="Directory to write the tarball into (default: %(default)s)")
    parser.add_argument(
        "--owner", default=gen_release_compose.DEFAULT_OWNER,
        help="GHCR owner/namespace baked into the release compose (default: %(default)s)")
    parser.add_argument(
        "--version", default=None,
        help="Version to build (default: tubematic_core.version.version())")
    args = parser.parse_args(argv)

    version = args.version or core_version()

    try:
        archive_path = build(
            version, repo_root=args.repo_root, out_dir=args.out_dir, owner=args.owner,
        )
    except ReleaseBuildError as exc:
        print(f"build_release_tarball: {exc}", file=sys.stderr)
        return 1

    print(archive_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
