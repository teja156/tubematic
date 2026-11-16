import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "sandbox"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
