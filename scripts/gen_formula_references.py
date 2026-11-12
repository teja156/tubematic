#!/usr/bin/env python3
"""Write the script-writing skill's formula files from the formula data.

The formulas live in tubematic_core/formulas/<id>.json. The skill needs them
as text an agent reads: one reference file per formula under the skill's
formulas/ folder. This script renders them from the data, so there is one
place to edit a formula. (What a router needs to choose a formula reaches the
agent as data, in get_video's formula_routing, and is not rendered here.)

    python3 scripts/gen_formula_references.py           # rewrite the files
    python3 scripts/gen_formula_references.py --check    # exit 1 if any is out of date

Run it after changing anything under tubematic_core/formulas/. A test runs the
same comparison, so a formula edited without it fails the suite.
"""
import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tubematic_core import formulas as tformulas  # noqa: E402

SKILL_DIR = REPO / "agent_files" / "skills" / "tubematic-script-writing-skill"
REFERENCE_DIR = SKILL_DIR / "formulas"


def expected() -> dict:
    """Every generated file as {path: text}."""
    return {REFERENCE_DIR / f"{fid}.md": tformulas.reference_markdown(formula)
            for fid, formula in tformulas.FORMULAS.items()}


def stale() -> list:
    """Paths whose content differs from what the data renders, plus reference
    files that no formula has any more."""
    files = expected()
    out = [p for p, text in files.items()
           if not p.is_file() or p.read_text(encoding="utf-8") != text]
    out += [p for p in sorted(REFERENCE_DIR.glob("*.md")) if p not in files]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report stale files and change nothing")
    args = ap.parse_args(argv)
    if args.check:
        out = stale()
        for path in out:
            print(f"out of date: {path.relative_to(REPO)}")
        return 1 if out else 0
    files = expected()
    REFERENCE_DIR.mkdir(exist_ok=True)
    for path in sorted(REFERENCE_DIR.glob("*.md")):
        if path not in files:
            path.unlink()
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(files)} formula files in {REFERENCE_DIR.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
