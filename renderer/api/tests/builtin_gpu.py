"""Test helper: the built-in renderer's GPU probe, stored the way the render
gateway stores one from a heartbeat (TMDEV-189).

The single-renderer settings row gpu_probe_result is retired; every GPU gate
reads the renderers table. A probe lands in renderers.gpu_probe (the same JSON
shape the probe always had) with gpu_verified = probe["ok"] is True.
"""
import json
import sqlite3


def store_builtin_probe(db_path, probe, requested_at=None):
    """Write `probe` (a dict, or None for "never probed") on the built-in
    renderer's row; `requested_at` also stamps a Test request."""
    con = sqlite3.connect(db_path)
    con.execute("UPDATE renderers SET gpu_probe = ?, gpu_verified = ? WHERE id = 'builtin'",
                (json.dumps(probe) if probe is not None else "",
                 int(isinstance(probe, dict) and probe.get("ok") is True)))
    if requested_at is not None:
        con.execute("UPDATE renderers SET gpu_probe_requested_at = ? WHERE id = 'builtin'",
                    (requested_at,))
    con.commit()
    con.close()
