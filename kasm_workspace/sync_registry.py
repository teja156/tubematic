#!/usr/bin/env python3
"""Write the Tubematic entry for the Kasm workspace registry.

Run by release.yml's publish-kasm-registry job (through
.github/actions/sync-kasm-registry), and by hand to recover from a failed run.
It copies registry/Tubematic/ into a registry checkout's workspaces/Tubematic/
and rewrites one thing: the launch form's version list, which becomes the
versions given on the command line, newest first and the default.

Every other key comes verbatim from the entry, so the entry in this repo is the
source of truth for everything but the list, and its own list is only a seed.

Usage:
  sync_registry.py --entry <dir> --out <dir> <version>...
  sync_registry.py --entry <dir> --print-images
  sync_registry.py --print-newest <version>...

Standard library only: the release job runs it with the runner's own python3.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

VERSION_KEY = "tubematic_version"
# A published release only: a prerelease (2.1.0-rc.1) is never offered on the form.
RELEASE_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def release_versions(raw: list[str]) -> list[str]:
    """X.Y.Z versions from tags or bare versions, deduped, newest first."""
    keyed = {}
    for item in raw:
        match = RELEASE_RE.match(item.strip())
        if match:
            key = tuple(int(part) for part in match.groups())
            keyed[key] = ".".join(match.groups())
    return [keyed[key] for key in sorted(keyed, reverse=True)]


def with_versions(entry: dict, versions: list[str]) -> dict:
    if not versions:
        raise ValueError("no published release versions; refusing to write an empty version list")
    out = json.loads(json.dumps(entry))
    [field] = [f for f in out["launch_config"]["launch_form"] if f["key"] == VERSION_KEY]
    field["options"] = [
        {"value": v, "label": f"{v} (latest)" if i == 0 else v} for i, v in enumerate(versions)
    ]
    field["value"] = versions[0]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entry", type=Path,
                        help="the entry directory (workspace.json + its icon)")
    parser.add_argument("--out", type=Path, help="where to write it: <registry>/workspaces/Tubematic")
    parser.add_argument("--print-images", action="store_true",
                        help="print the entry's compatibility images, one per line, and exit")
    parser.add_argument("--print-newest", action="store_true",
                        help="print the newest of the given versions and exit")
    parser.add_argument("versions", nargs="*", help="release tags or versions, any order")
    args = parser.parse_args(argv)

    versions = release_versions(args.versions)
    if args.print_newest:
        if not versions:
            print("error: no published release versions", file=sys.stderr)
            return 1
        print(versions[0])
        return 0
    if args.entry is None:
        parser.error("--entry is required")
    entry = json.loads((args.entry / "workspace.json").read_text())
    if args.print_images:
        for compat in entry["compatibility"]:
            print(compat["image"])
        return 0
    if args.out is None:
        parser.error("--out is required unless --print-images is given")

    try:
        written = with_versions(entry, versions)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "workspace.json").write_text(json.dumps(written, indent=2) + "\n")
    shutil.copyfile(args.entry / entry["image_src"], args.out / entry["image_src"])
    print(f"Wrote {args.out / 'workspace.json'}: {', '.join(versions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
