#!/usr/bin/env python3
"""Cut a Tubematic release (TMDEV-91 Phase 2, spec section 5.3).

Deliberately thin: run the pre-flight checks, build the tarball, print a
release-notes skeleton, and print -- never run -- the git commands for the
tag and release branch. GitHub Actions owns the actual publish (pushing the
tag, building and pushing images, creating the GitHub Release); a script
that tags and pushes on its own is exactly the kind of magic the design
spec warns against.

Note: unlike the spec's own prose, this script does NOT bump VERSION. By
the time it is run, check_release's "VERSION matches the requested version"
check must already pass -- bumping VERSION is a separate, earlier step (a
manual edit + commit), not something this script does on your behalf.

Run from the repo root:
    python scripts/release.py 1.2.3
    python scripts/release.py v1.2.3
"""
import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT_DEFAULT = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_SCRIPTS_DIR))
sys.path.insert(0, str(_REPO_ROOT_DEFAULT))

import check_release  # noqa: E402

# gen_release_compose.py owns the PyYAML dependency check and exits with a
# clear message if it is missing -- that exit is a SystemExit, which a
# `except ModuleNotFoundError` here cannot catch (and by this point
# `import check_release` above has already imported gen_release_compose
# once, successfully, so this guard could never fire anyway).
import build_release_tarball  # noqa: E402
import gen_release_compose  # noqa: E402

from tubematic_core.version import release_line as core_release_line  # noqa: E402


def _release_notes_skeleton(version: str) -> str:
    return (
        f"## v{version}\n\n"
        "### Added\n"
        "- \n\n"
        "### Changed\n"
        "- \n\n"
        "### Fixed\n"
        "- \n\n"
        "### Upgrade notes\n"
        "- \n"
    )


def _git_commands(tag: str) -> list:
    """The commands a maintainer runs by hand to actually publish this
    release. Printed, never executed -- see the module docstring.

    Two shapes, because a release line is created once and tagged many
    times:

    - The first release of a MAJOR.MINOR creates the line and tags it.
    - Every later patch on that line is committed to it and tagged; the
      branch already exists, so creating it again is wrong.

    This prints both and says which applies, rather than guessing from
    whether the branch exists locally -- a maintainer on a fresh clone has
    no local branches at all, and a script that guessed would confidently
    print the wrong one.

    Tag last in both cases. On a first release the branch and tag land on
    the same commit so the order does not matter; on a patch it does, since
    the fix and the VERSION bump have to be committed to the line before
    there is anything correct to tag.
    """
    version = tag[1:] if tag.startswith("v") else tag
    line = core_release_line(version)
    return [
        f"# If {line} does not exist yet (the first release of this MAJOR.MINOR):",
        f"git checkout -b {line}",
        f"git push -u origin {line}",
        "",
        f"# If {line} already exists (a patch on an existing line):",
        f"git checkout {line}",
        "#   cherry-pick the fix from the development branch, then commit the",
        "#   VERSION bump -- never merge the development branch into a line",
        "git cherry-pick -x <fix-sha>",
        f"git push origin {line}",
        "",
        "# Either way, tag last:",
        f'git tag -a {tag} -m "Tubematic {tag}"',
        f"git push origin {tag}",
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help='Version to release, e.g. "1.2.3" or "v1.2.3"')
    parser.add_argument(
        "--repo-root", default=str(_REPO_ROOT_DEFAULT),
        help="Repo root to release from (default: %(default)s)")
    parser.add_argument(
        "--out-dir", default=str(_REPO_ROOT_DEFAULT / "dist"),
        help="Directory to write the release tarball into (default: %(default)s)")
    parser.add_argument(
        "--owner", default=gen_release_compose.DEFAULT_OWNER,
        help="GHCR owner/namespace baked into the release compose (default: %(default)s)")
    args = parser.parse_args(argv)

    version = check_release.normalize_version(args.version)
    repo_root = Path(args.repo_root).resolve()

    checks = check_release.run_checks(repo_root, version, owner=args.owner)
    print(check_release.format_report(checks))
    if any(c.status == "fail" for c in checks):
        print("\nrelease aborted: pre-flight checks failed", file=sys.stderr)
        return 1

    try:
        archive_path = build_release_tarball.build(
            version, repo_root=repo_root, out_dir=args.out_dir, owner=args.owner)
    except build_release_tarball.ReleaseBuildError as e:
        print(f"\nrelease aborted: {e}", file=sys.stderr)
        return 1

    tag = f"v{version}"
    print(f"\nBuilt: {archive_path}")
    print("\n" + _release_notes_skeleton(version))
    print("Next steps (run these yourself -- this script does not):")
    print("  # Every release is a tag on its release line, release/MAJOR.MINOR.x.")
    for cmd in _git_commands(tag):
        print(f"  {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
