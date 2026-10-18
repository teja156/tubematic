import sys
from pathlib import Path

import pytest

# Import mcp/server.py as a top-level `server` module (not as part of a `mcp`
# package) so it doesn't collide with the `mcp` package fastmcp depends on.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Repo root too, for the shared `tubematic_core` package. Inside the container
# that comes from PYTHONPATH=/app/lib (renderer/Dockerfile); on the host nothing
# puts the root on the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def through_mcp(caplog, monkeypatch):
    """Call a tool the way an agent does: over a real FastMCP client, so the
    call passes through the server's middleware and the tool's return value is
    wrapped exactly as it is in production. Returns (structured result, the
    `mcp` logger's records for that one call).

    Each call is a new client session, i.e. a new scene-work owner, so the
    module-level claim table is emptied first — otherwise a claim left by an
    earlier test or call refuses this one as `scene_work_claimed`."""
    import asyncio
    import logging

    from fastmcp import Client

    import server

    caplog.set_level(logging.INFO, logger="mcp")
    monkeypatch.setattr(server, "_scene_claims", {})

    def call(tool, **arguments):
        caplog.clear()
        server._scene_claims.clear()

        async def go():
            async with Client(server.mcp) as client:
                return await client.call_tool(tool, arguments, raise_on_error=False)

        result = asyncio.run(go())
        return result.structured_content, [r for r in caplog.records if r.name == "mcp"]

    return call
