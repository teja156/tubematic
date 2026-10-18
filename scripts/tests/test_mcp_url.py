"""MCP_URL is the server base, not the MCP endpoint.

status.py probes `{MCP_URL}/health`. The MCP server's /health is a FastMCP
custom route served at the server root, *beside* /mcp rather than under it —
so an MCP_URL carrying the endpoint suffix would build /mcp/health, get a 404,
and report a perfectly healthy MCP container as unreachable.

That is not a hypothetical override: `claude mcp add` takes the endpoint form,
every doc quotes it, and .env.example shipped `MCP_URL=http://localhost:4100/mcp`
verbatim, so the endpoint form is the value someone would actually paste here.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import _mcp_base


@pytest.mark.parametrize("given", [
    "http://localhost:4100",
    "http://localhost:4100/",
    "http://localhost:4100/mcp",
    "http://localhost:4100/mcp/",
])
def test_every_spelling_normalises_to_the_server_root(given):
    assert _mcp_base(given) == "http://localhost:4100"


def test_a_non_default_host_is_preserved():
    assert _mcp_base("http://box.local:9000/mcp") == "http://box.local:9000"


def test_only_a_whole_trailing_segment_is_stripped():
    """`/mcp` is stripped as a path segment, not as a suffix — a path that
    merely ends in those letters is left alone."""
    assert _mcp_base("http://localhost:4100/mcpx") == "http://localhost:4100/mcpx"


def test_a_path_prefix_survives():
    """Someone behind a reverse proxy may mount the server under a prefix.
    Only the endpoint segment goes."""
    assert _mcp_base("http://gateway/tubematic/mcp") == "http://gateway/tubematic"


def test_the_probe_url_lands_on_the_root_health_route():
    """The assembled URL is what status.py actually requests, and what the
    compose healthcheck curls."""
    assert _mcp_base("http://localhost:4100/mcp") + "/health" == "http://localhost:4100/health"
