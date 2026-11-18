#!/usr/bin/env python3
"""Zip a style package folder for sharing: <out dir>/<id>-<version>.zip.

    python3 zip_package.py <package folder> <out dir>

The zip holds the folder itself (one top folder named after the style id),
which Tubematic's Install from file accepts. Standard library only.
"""
import json
import pathlib
import sys
import zipfile


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    d, out = pathlib.Path(argv[0]), pathlib.Path(argv[1])
    pack = json.loads((d / "style.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{pack['id']}-{pack['external']['version']}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(d.rglob("*")):
            if p.is_symlink():
                sys.exit(f"{p}: a style package holds plain files only")
            if p.is_file():
                zf.write(p, f"{pack['id']}/{p.relative_to(d).as_posix()}")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
