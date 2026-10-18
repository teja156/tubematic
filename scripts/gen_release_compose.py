#!/usr/bin/env python3
"""Generate the release docker-compose.yml from the development one (TMDEV-91
Phase 2, spec section 4.1).

The release compose that ships inside a release tarball must never be
hand-maintained as a second copy of docker-compose.yml -- that is exactly how
the two would silently drift. Instead this reads the real dev compose file
and applies exactly two mechanical transformations:

1. `build:` -> `image: ghcr.io/<owner>/tubematic-<role>:<version>`. A release
   install has no source tree, so a `build:` key pointing at
   renderer/Dockerfile would reference a path that does not exist. A service
   that already reuses the locally-built image under the `tubematic-renderer-
   image` tag (tubematic-mcp, tubematic-renderer) is repointed at the same
   backend image for the same reason -- a release install builds nothing, so
   that local tag would never resolve.
2. Every published port is forced onto a `127.0.0.1:` binding. An entry that
   already carries a `127.0.0.1:` prefix (tubematic-api, tubematic-mcp) is
   left alone.

Everything else -- volumes, environment, healthchecks, depends_on, shm_size,
restart, container_name, and the top-level `name:` -- passes through
untouched. That is the whole point: one source of truth for the topology,
not two.

PyYAML does not preserve comments, so the generated file loses the dev
file's inline commentary -- accepted, since this is a generated artifact,
not source to read. A header comment marks it as generated instead.

Run from the repo root:
    python scripts/gen_release_compose.py --print
    python scripts/gen_release_compose.py --out /path/to/release-compose.yml
"""
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core.version import GITHUB_REPO, is_valid  # noqa: E402
from tubematic_core.version import version as core_version  # noqa: E402

try:
    import yaml
except ModuleNotFoundError:
    sys.exit(
        "This script needs PyYAML: pip install pyyaml\n"
        "(a maintainer/test-only dependency, deliberately not in "
        "scripts/requirements.txt -- it is not needed at runtime)"
    )

# The GHCR namespace release images are published under: the repo's owner.
# A keyword default, not a runtime secret -- overridable via --owner / the
# `owner` kwarg, and release.yml always passes github.repository_owner.
DEFAULT_OWNER = GITHUB_REPO.split("/")[0]

# The local tag tubematic-mcp and tubematic-renderer carry today because they
# reuse what tubematic-api builds, rather than building a second time.
_LOCAL_BACKEND_IMAGE = "tubematic-renderer-image"

# The single definition of "a valid release version" for the whole release
# toolchain -- scripts/check_release.py imports and reuses this rather than
# restating the rule, the same way it already reuses build_release_tarball's
# allowlist instead of hand-copying it.
#
# The version is interpolated straight into `image: ...:<version>` below with
# no escaping, so it must double as the trailing component of a Docker image
# tag: `[A-Za-z0-9_][A-Za-z0-9._-]*`. Plain SemVer's optional "+build
# metadata" suffix is legal SemVer and illegal in a tag ('+' is not a tag
# character), so it is rejected outright here rather than accepted and left
# to fail later inside `docker` with "invalid reference format" -- a failure
# a maintainer would have to reproduce by hand to even see. A "-prerelease"
# suffix is kept, but restricted to SemVer's own prerelease alphabet
# (dot-separated runs of ASCII letters, digits and hyphens), which is also
# already tag-safe, so this is not a narrower rule than SemVer -- just one
# that also happens to fit inside a tag. The development-branch marker
# (tubematic_core.version.DEV_VERSION) is accepted too: it is tag-safe, and a
# compose generated on that branch is legitimate. Releasing it is what is
# refused, by check_release.py's check_version_format.
_TAG_SAFE_CHAR_RE = re.compile(r"[A-Za-z0-9._-]")


def invalid_version_chars(version: str) -> list:
    """Every character in `version` that cannot appear in a Docker image
    tag, in encounter order with duplicates removed -- used to build a
    specific, actionable error message instead of a bare "invalid version"."""
    seen = []
    for c in version:
        if not _TAG_SAFE_CHAR_RE.match(c) and c not in seen:
            seen.append(c)
    return seen


def check_version_is_tag_safe(version: str) -> None:
    """Raise ValueError if `version` cannot be used as a Docker image tag
    component. Called by generate() itself, so a maintainer invoking this
    script directly (not through check_release.py) still gets a hard
    failure instead of a broken compose file, and by
    scripts/check_release.py's own pre-flight check, which calls this
    rather than re-deriving the rule -- one definition, one place."""
    if is_valid(version):
        return
    detail = f"{version!r} is not a valid MAJOR.MINOR.PATCH[-prerelease] version"
    offending = invalid_version_chars(version)
    if offending:
        detail += "; invalid character(s): " + ", ".join(repr(c) for c in offending)
    raise ValueError(detail)

# Which ghcr.io role each service carrying a `build:` key maps to. A service
# is listed here, not inferred from its name, so an unexpected new `build:`
# key in the dev file fails loudly instead of silently getting the wrong role
# or being skipped.
_ROLE_BY_SERVICE = {
    "tubematic-api": "backend",
    "tubematic-dashboard": "dashboard",
}

_HEADER = """\
# GENERATED FILE -- do not edit by hand.
#
# Produced by scripts/gen_release_compose.py from docker-compose.yml for
# Tubematic v{version}. Re-run the generator to pick up changes to the
# development compose file; edits made directly to this file are silently
# overwritten by the next release build.
"""


def _backend_image(owner: str, version: str) -> str:
    return f"ghcr.io/{owner}/tubematic-backend:{version}"


def _pin_port_to_loopback(port: str) -> str:
    if port.startswith("127.0.0.1:"):
        return port
    return f"127.0.0.1:{port}"


def generate(compose_path, version, *, owner: str = DEFAULT_OWNER) -> str:
    """Read the compose file at `compose_path` and return the release compose
    text, with `build:` sections pinned to ghcr.io images at `version` and
    every published port forced onto a loopback binding.

    `version` is required and should come from `tubematic_core.version.version()`
    at the call site -- never a literal -- so the release compose cannot
    disagree with what the running services report.

    Raises ValueError if `version` cannot be used as a Docker image tag --
    see check_version_is_tag_safe(). Checked here, not just by
    check_release.py, because this function is also reachable directly (a
    maintainer running this script by hand, or build_release_tarball.py
    calling it): refusing an unusable version is better than emitting a
    compose file every service in it fails to pull with "invalid reference
    format".
    """
    check_version_is_tag_safe(version)
    compose_path = Path(compose_path)
    data = yaml.safe_load(compose_path.read_text())

    for name, service in data.get("services", {}).items():
        if "build" in service:
            try:
                role = _ROLE_BY_SERVICE[name]
            except KeyError:
                raise ValueError(
                    f"service {name!r} has a build: key but no known ghcr.io "
                    "role -- add it to _ROLE_BY_SERVICE in gen_release_compose.py"
                ) from None
            del service["build"]
            service["image"] = f"ghcr.io/{owner}/tubematic-{role}:{version}"
        elif service.get("image") == _LOCAL_BACKEND_IMAGE:
            service["image"] = _backend_image(owner, version)

        if "ports" in service:
            service["ports"] = [_pin_port_to_loopback(p) for p in service["ports"]]

    body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    return _HEADER.format(version=version) + "\n" + body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose", default=str(REPO_ROOT / "docker-compose.yml"),
        help="Path to the development compose file (default: %(default)s)")
    parser.add_argument(
        "--owner", default=DEFAULT_OWNER,
        help="GHCR owner/namespace to publish images under (default: %(default)s)")
    parser.add_argument(
        "--version", default=None,
        help="Version to pin images to (default: tubematic_core.version.version())")
    parser.add_argument(
        "--out", default=None,
        help="Write the release compose to this path")
    parser.add_argument(
        "--print", action="store_true", dest="do_print",
        help="Print the release compose to stdout (implied when --out is not given)")
    args = parser.parse_args(argv)

    version = args.version or core_version()
    output = generate(args.compose, version, owner=args.owner)

    if args.out:
        Path(args.out).write_text(output)
    if args.do_print or not args.out:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
