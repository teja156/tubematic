"""Put the repo root on sys.path so `import tubematic_core` resolves.

Inside the container the shared package is on PYTHONPATH (/app/lib, see
renderer/Dockerfile); on the host nothing puts the repo root anywhere, and this
directory's own `tests/__init__.py` means pytest prepends `renderer/api` rather
than the root.

Deliberately per-suite rather than a conftest.py at the repo root:
renderer/api/tests, onboard/tests and scripts/tests all carry an __init__.py and
so all resolve to the top-level package name `tests`, which is why they have to
be run in separate pytest invocations (docs/developer/17-development.md). A root conftest
would encourage collecting them together, which does not work.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
