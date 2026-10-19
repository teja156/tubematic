#!/usr/bin/env python3
"""Install the Tubematic version picked on the Kasm launch form, then onboard.

Runs as the session user (uid 1000) inside the installer terminal that
kasm_post_run_root.sh opens, and again from the desktop launcher. Standard
library only: the image carries no Tubematic source and no virtualenv, so
nothing outside the stdlib is importable here.

The flow, every refusal of which downloads nothing:

1. Read the launch-form selections (version + install method). Anything
   unreadable, missing or malformed is refused -- a version is never guessed.
2. Look for an install this launcher already made. A persistent profile is
   relaunched, so finding one is the normal case, not an error: the same
   version is reported and left alone; a different version is refused with a
   pointer to the upgrade guide, because installing a second copy beside the
   first, or replacing it, is not something to do silently.
3. Fetch: a release tarball verified against the release's CHECKSUMS.txt
   before anything is extracted, or a clone of the version's tag.
4. Record the install, then hand over to ``python3 onboard.py`` in the same
   terminal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Keep in sync with tubematic_core/version.py::GITHUB_REPO (pinned by
# scripts/tests/test_kasm_workspace_bootstrap.py). Duplicated because this
# image has no Tubematic source to import it from.
GITHUB_REPO = "teja156/tubematic"

SELECTIONS_PATH = Path("/dockerstartup/tubematic_launch_selections.json")
VERSION_KEY = "tubematic_version"
METHOD_KEY = "install_method"
# The launch form's own validator_regex for the version field. A bare X.Y.Z:
# the form only ever lists published releases.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
METHODS = ("release", "source")

MARKER_NAME = ".tubematic-workspace.json"
DATA_DIR_NAME = ".tubematic-data"
LOG_NAME = ".tubematic-workspace.log"
UPGRADE_GUIDE = "https://docs.tubematic.ai/user-guide/upgrading"

HTTP_TIMEOUT_SECS = 60


class BootstrapError(Exception):
    """A refusal or failure, worded for the person watching the terminal."""


@dataclass(frozen=True)
class Selection:
    version: str
    method: str


@dataclass(frozen=True)
class Install:
    # All None for data found without a marker: an install this launcher did
    # not make, so nothing about it is known.
    version: str | None
    method: str | None
    path: str | None


# ── Reading what was asked for ────────────────────────────────────────────


def read_selections(path: Path = SELECTIONS_PATH) -> Selection:
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise BootstrapError(
            f"No launch-form selections at {path}. The workspace's launch form "
            "did not run, so there is no version to install."
        ) from None
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"Could not read the launch-form selections at {path}: {exc}") from None
    if not isinstance(data, dict):
        raise BootstrapError(f"The launch-form selections at {path} are not a JSON object.")

    version = str(data.get(VERSION_KEY, "")).strip()
    method = str(data.get(METHOD_KEY, "")).strip().lower()
    if not version:
        raise BootstrapError("The launch form did not say which Tubematic version to install.")
    if not VERSION_RE.match(version):
        raise BootstrapError(f"{version!r} is not a Tubematic release version (expected X.Y.Z).")
    if method not in METHODS:
        raise BootstrapError(
            f"{method or '<none>'!r} is not an install method; expected one of: {', '.join(METHODS)}."
        )
    return Selection(version=version, method=method)


def existing_install(home: Path) -> Install | None:
    marker = home / MARKER_NAME
    if marker.exists():
        try:
            data = json.loads(marker.read_text())
            return Install(version=data["version"], method=data["method"], path=data["path"])
        except (OSError, ValueError, KeyError, TypeError):
            # A marker exists but cannot be read: something was installed, and
            # what it was is unknown. Treat it like data with no marker.
            return Install(version=None, method=None, path=None)
    if (home / DATA_DIR_NAME).exists():
        return Install(version=None, method=None, path=None)
    return None


def install_dir(home: Path, version: str) -> Path:
    # The release tarball's own top-level directory, used for a clone too so
    # both methods land in the same place.
    return home / f"tubematic-v{version}"


# ── Deciding ──────────────────────────────────────────────────────────────


def decide(selection: Selection, existing: Install | None) -> tuple[str, str]:
    """Return ("install" | "present" | "refuse", message)."""
    if existing is None:
        return "install", f"Installing Tubematic v{selection.version} ({selection.method})."
    if existing.version is None:
        return "refuse", (
            f"Found an earlier Tubematic install in this profile (~/{DATA_DIR_NAME}, or an unreadable\n"
            f"~/{MARKER_NAME}), but not one this launcher can identify.\n"
            "This launcher only installs onto an empty profile, so it will not touch it.\n"
            f"To upgrade an existing install, follow {UPGRADE_GUIDE}\n"
            "Nothing was downloaded."
        )
    if existing.version == selection.version:
        return "present", (
            f"Tubematic v{existing.version} is already installed at {existing.path}.\n"
            f"To resume or re-run onboarding:  cd {existing.path} && python3 onboard.py\n"
            "To install an agent:            python3 onboard.py --install-agent <agent>"
        )
    return "refuse", (
        f"Tubematic v{existing.version} is installed at {existing.path}, but v{selection.version} "
        "was picked on the launch form.\n"
        "This launcher never installs a second copy beside an install, or replaces one.\n"
        f"To move to v{selection.version}, follow the upgrade guide: {UPGRADE_GUIDE}\n"
        f"(download the v{selection.version} release, then run its upgrade.py).\n"
        "Nothing was downloaded."
    )


# ── Fetching ──────────────────────────────────────────────────────────────


def release_url(version: str, name: str) -> str:
    return f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/{name}"


def download(url: str, dest: Path, urlopen=None) -> None:
    urlopen = urlopen or urllib.request.urlopen
    partial = dest.with_name(dest.name + ".part")
    try:
        with urlopen(url, timeout=HTTP_TIMEOUT_SECS) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 16):
                out.write(chunk)
    except urllib.error.HTTPError as exc:
        partial.unlink(missing_ok=True)
        if exc.code == 404:
            raise BootstrapError(f"Not found: {url}\nIs this version a published release?") from None
        raise BootstrapError(f"Download failed ({exc.code}): {url}") from None
    except (urllib.error.URLError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise BootstrapError(f"Download failed: {url}: {exc}") from None
    partial.replace(dest)


def expected_sha256(checksums: str, filename: str) -> str:
    # sha256sum's format: "<hex>  <name>", or "<hex> *<name>" in binary mode.
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == filename and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return parts[0]
    raise BootstrapError(f"CHECKSUMS.txt has no sha256 for {filename}.")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_release(version: str, home: Path, urlopen=None, say=print) -> Path:
    target = install_dir(home, version)
    if target.exists():
        raise BootstrapError(f"{target} already exists; refusing to extract over it.")
    tarball_name = f"tubematic-v{version}.tar.gz"
    cache = home / ".cache" / "tubematic-bootstrap" / f"v{version}"
    cache.mkdir(parents=True, exist_ok=True)
    checksums_path = cache / "CHECKSUMS.txt"
    tarball_path = cache / tarball_name

    say(f"Downloading {release_url(version, 'CHECKSUMS.txt')}")
    download(release_url(version, "CHECKSUMS.txt"), checksums_path, urlopen)
    want = expected_sha256(checksums_path.read_text(), tarball_name)
    say(f"Downloading {release_url(version, tarball_name)}")
    download(release_url(version, tarball_name), tarball_path, urlopen)

    # Verified BEFORE extraction: a downloaded archive is untrusted until its
    # checksum matches, and extracting first would already have written it out.
    got = sha256_of(tarball_path)
    if got != want:
        tarball_path.unlink(missing_ok=True)
        raise BootstrapError(
            f"Checksum mismatch for {tarball_name}:\n  expected {want}\n  got      {got}\n"
            "The download was discarded and nothing was extracted. Relaunch to try again."
        )
    say(f"Checksum verified ({got}).")

    prefix = f"tubematic-v{version}/"
    with tarfile.open(tarball_path, "r:gz") as archive:
        members = archive.getmembers()
        stray = [m.name for m in members if m.name != prefix.rstrip("/") and not m.name.startswith(prefix)]
        if stray:
            raise BootstrapError(f"{tarball_name} holds paths outside {prefix}: {stray[:3]}; refusing to extract.")
        archive.extractall(home, members=members, filter="data")
    if not (target / "onboard.py").is_file():
        raise BootstrapError(f"{tarball_name} extracted, but {target}/onboard.py is missing.")
    tarball_path.unlink(missing_ok=True)
    return target


def clone_source(version: str, home: Path, run=None, say=print) -> Path:
    run = run or subprocess.run
    target = install_dir(home, version)
    if target.exists():
        raise BootstrapError(f"{target} already exists; refusing to clone over it.")
    url = f"https://github.com/{GITHUB_REPO}.git"
    # The version's tag, never the default branch: "v1.2.3, source" means that tag.
    argv = ["git", "clone", "--depth", "1", "--branch", f"v{version}", url, str(target)]
    say("Running: " + " ".join(argv))
    if run(argv).returncode != 0:
        raise BootstrapError(f"git clone of tag v{version} failed. Is it a published release?")
    return target


def write_marker(home: Path, selection: Selection, path: Path) -> None:
    (home / MARKER_NAME).write_text(json.dumps({
        "version": selection.version,
        "method": selection.method,
        "path": str(path),
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2) + "\n")


# ── Entry point ───────────────────────────────────────────────────────────


def _sayer(home: Path):
    log_path = home / LOG_NAME

    def say(message: str = "") -> None:
        print(message, flush=True)
        try:
            with open(log_path, "a") as log:
                stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                for line in message.splitlines() or [""]:
                    log.write(f"[{stamp}] bootstrap: {line}\n")
        except OSError:
            pass

    return say


def main(argv: list[str] | None = None, home: Path | None = None,
         selections_path: Path = SELECTIONS_PATH) -> int:
    argv = sys.argv[1:] if argv is None else argv
    home = Path.home() if home is None else home

    if argv == ["--install-dir"]:
        # For tubematic-installer: where to leave the shell afterwards.
        found = existing_install(home)
        if found and found.path:
            print(found.path)
            return 0
        return 1

    say = _sayer(home)
    say("=== Tubematic workspace installer ===")
    try:
        selection = read_selections(selections_path)
        action, message = decide(selection, existing_install(home))
        say(message)
        if action == "refuse":
            return 1
        if action == "present":
            return 0

        if selection.method == "release":
            target = fetch_release(selection.version, home, say=say)
        else:
            target = clone_source(selection.version, home, say=say)
        write_marker(home, selection, target)
        say(f"Tubematic v{selection.version} is in {target}. Starting onboarding...")
    except BootstrapError as exc:
        say(f"ERROR: {exc}")
        return 1

    # Interactive, in this same terminal: the user finishes onboarding here.
    status = subprocess.run([sys.executable, "onboard.py"], cwd=target).returncode
    say(f"onboard.py exited with status {status}.")
    return status


if __name__ == "__main__":
    sys.exit(main())
