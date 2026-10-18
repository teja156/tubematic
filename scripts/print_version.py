#!/usr/bin/env python3
"""Print the current Tubematic version.

Reads tubematic_core.version.version() — the single source of truth backed
by the VERSION file at the repo root — so this can never disagree with what
the running services report.

Run from the repo root:
    python scripts/print_version.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core.version import version  # noqa: E402


def main(argv=None) -> int:
    print(version())
    return 0


if __name__ == "__main__":
    sys.exit(main())
