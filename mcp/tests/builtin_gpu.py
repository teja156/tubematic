"""Test helper: the built-in renderer's GPU probe, stored the way the render
gateway stores one from a heartbeat (TMDEV-189).

The single-renderer settings row gpu_probe_result is retired; the MCP gates
read the renderers table (tubematic_core.renderers.gpu_status). A probe lands
in renderers.gpu_probe with gpu_verified = probe["ok"] is True.
"""
import json

import server


def store_builtin_probe(probe):
    """Write `probe` (a dict, or None for "never probed") on the built-in
    renderer's row of the database server.DB_FILE points at."""
    with server._conn() as con:
        con.execute("UPDATE renderers SET gpu_probe = ?, gpu_verified = ? WHERE id = 'builtin'",
                    (json.dumps(probe) if probe is not None else "",
                     int(isinstance(probe, dict) and probe.get("ok") is True)))
