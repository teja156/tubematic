#!/usr/bin/env python3
"""Write MANIFEST.json for a style package folder: the sha256 of every other file.

    python3 manifest.py <package folder>

Standard library only. Refuses a symlink or any entry that is not a plain file,
as Tubematic's loader does (tubematic_core/external_styles.py).
"""
import hashlib
import json
import os
import pathlib
import stat
import sys


def files(d: pathlib.Path) -> dict:
    out = {}
    for top, dirs, names in os.walk(d):
        dirs.sort()
        for name in sorted(names + [x for x in dirs if os.path.islink(os.path.join(top, x))]):
            p = pathlib.Path(top) / name
            mode = os.lstat(p).st_mode
            rel = p.relative_to(d).as_posix()
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                sys.exit(f"{rel}: a style package holds plain files only (no symlinks)")
            if rel != "MANIFEST.json":
                out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not pathlib.Path(argv[0]).is_dir():
        print(__doc__, file=sys.stderr)
        return 2
    d = pathlib.Path(argv[0])
    listed = files(d)
    (d / "MANIFEST.json").write_text(json.dumps({"files": listed}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"MANIFEST.json lists {len(listed)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
