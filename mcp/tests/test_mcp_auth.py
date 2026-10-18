"""The MCP server's bearer token (TMDEV-152).

Built on the real ASGI app, the way the entry point serves it, because the
claims that matter are about HTTP: /mcp refuses a request without the token,
/health stays open for the compose healthcheck, and nothing advertises OAuth.
A client that sees OAuth discovery after a 401 tries a browser login, which an
unattended agent run can never finish.

The in-memory `through_mcp` fixture never passes through HTTP, so the rest of
the suite is unaffected by the token.
"""
import asyncio

import pytest
from starlette.testclient import TestClient

import server

TOKEN = "test-mcp-token-0123456789"
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}}}
HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture
def client():
    previous = server.mcp.auth
    server.enable_auth(TOKEN)
    try:
        with TestClient(server.mcp.http_app(path="/mcp")) as c:
            yield c
    finally:
        server.mcp.auth = previous


@pytest.mark.parametrize("auth", [None, "Bearer wrong", f"Basic {TOKEN}", f"Bearer {TOKEN}x"])
def test_mcp_refuses_a_missing_or_wrong_token(client, auth):
    headers = dict(HEADERS, **({"Authorization": auth} if auth else {}))
    r = client.post("/mcp", json=INIT, headers=headers)
    assert r.status_code == 401


def test_mcp_accepts_the_right_token(client):
    r = client.post("/mcp", json=INIT, headers=dict(HEADERS, Authorization=f"Bearer {TOKEN}"))
    assert r.status_code == 200


def test_health_stays_open(client):
    assert client.get("/health").status_code == 200


def test_a_401_does_not_advertise_oauth(client):
    r = client.post("/mcp", json=INIT, headers=HEADERS)
    assert r.headers.get("www-authenticate", "").strip() == "Bearer"
    for path in ("/.well-known/oauth-protected-resource",
                 "/.well-known/oauth-protected-resource/mcp",
                 "/.well-known/oauth-authorization-server"):
        assert client.get(path).status_code == 404, path


def test_the_verifier_compares_the_whole_token():
    verifier = server._BearerToken(TOKEN)

    async def check(t):
        return await verifier.verify_token(t)

    assert asyncio.run(check(TOKEN)) is not None
    for wrong in ("", TOKEN[:-1], TOKEN + "x", TOKEN.upper()):
        assert asyncio.run(check(wrong)) is None


def test_importing_the_server_needs_no_secret():
    """Tests and vqa/stage_script.py import the module; only the entry point reads the token."""
    assert "read_secret(" not in server.__loader__.get_source("server").split('if __name__ == "__main__":')[0]


def test_the_entry_point_enables_auth_from_the_token_file():
    source = server.__loader__.get_source("server").split('if __name__ == "__main__":')[1]
    assert 'enable_auth(read_secret("mcp_token"))' in source
    assert source.index("enable_auth(") < source.index("mcp.run(")
