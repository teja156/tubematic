"""Capabilities removed from the MCP server stay removed.

`write_gif_script` executed agent-authored Python inside the MCP container,
which holds the credential database. It was deleted rather than sandboxed, so
nothing may bring it, or the toolkit it ran against, back by accident.
"""
import asyncio
import re
from pathlib import Path

import server

MCP_DIR = Path(__file__).resolve().parent.parent


def test_write_gif_script_is_not_offered_to_agents():
    from fastmcp import Client

    async def go():
        async with Client(server.mcp) as client:
            return [t.name for t in await client.list_tools()]

    names = asyncio.run(go())
    assert "write_gif_script" not in names
    assert "validate_job" in names   # the listing itself works


def test_nothing_in_mcp_imports_the_gif_toolkit_or_its_dependencies():
    pattern = re.compile(r"^\s*(?:from|import)\s+(gif_core|numpy|imageio)\b", re.M)
    offenders = [str(p.relative_to(MCP_DIR)) for p in MCP_DIR.rglob("*.py")
                 if ".venv" not in p.parts and pattern.search(p.read_text())]
    assert offenders == []
    assert not (MCP_DIR / "gif_core").exists()


def test_the_requirements_no_longer_pull_in_the_gif_dependencies():
    reqs = (MCP_DIR / "requirements.txt").read_text().lower()
    assert "imageio" not in reqs and "numpy" not in reqs
    assert "pillow" in reqs   # read_image and generate_character still need it
