"""GET /health — the tubematic-mcp container's readiness probe (TMDEV-87).

The MCP server moved out of the combined tubematic-api container into its own
service, which needs a healthcheck that probes MCP and nothing else. The old
combined check POSTed an empty body to /mcp and accepted any HTTP response;
that could not distinguish a live server from one erroring, and could not be
asserted anywhere. These tests pin the route so a refactor cannot silently
remove the thing docker-compose.yml's healthcheck depends on.

Requires the mcp/ package deps — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import asyncio
import json

import pytest
from starlette.testclient import TestClient

import server


def _routes():
    return {r.path: r for r in server.mcp._additional_http_routes}


def test_health_route_is_registered_at_slash_health():
    """docker-compose.yml probes exactly this path. FastMCP serves custom
    routes at the server root, beside /mcp — not under it."""
    assert "/health" in _routes()


@pytest.fixture(scope="module")
def client():
    """The real ASGI app, built with the same `path` the entry point passes.

    Registration is not the same claim as *serving*: the healthcheck curls
    http://localhost:4100/health, and whether the route lands there depends on
    where FastMCP mounts custom routes relative to `path="/mcp"`. Asserting on
    _additional_http_routes alone would pass even if the real mount point were
    /mcp/health — and the container would then never reach `healthy`, which
    aborts onboarding's renderer step. In-process, so no port is bound.
    """
    return TestClient(server.mcp.http_app(path="/mcp"))


def test_the_served_app_answers_at_slash_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_is_not_nested_under_the_mcp_path(client):
    """Pins the mount point, so a FastMCP change that moved custom routes
    under `path` fails here rather than in a Kasm session."""
    assert client.get("/mcp/health").status_code == 404


def test_health_route_is_a_get():
    assert "GET" in _routes()["/health"].methods


def test_health_returns_200_and_the_flask_shaped_body():
    """Mirrors renderer/api/server.py's GET /health so both containers'
    probes read identically."""
    response = asyncio.run(server.health(None))
    assert response.status_code == 200
    assert json.loads(response.body) == {"status": "ok"}


def test_health_does_not_touch_the_database(monkeypatch):
    """A readiness probe runs every 15s forever. It reports that the server
    process is accepting connections, nothing more — pointing DB_FILE at a
    path that does not exist must not make it fail."""
    monkeypatch.setattr(server, "DB_FILE", "/nonexistent/tubematic.db")
    response = asyncio.run(server.health(None))
    assert response.status_code == 200
