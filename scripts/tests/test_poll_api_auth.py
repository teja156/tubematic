"""poll.py's API token (TMDEV-152): one opener adds it to every API call.

The supervisor outlives a token rotation, so the file is read per request; and
the header goes to the API only, never to any other URL poll.py might fetch.
"""
import os
import urllib.request

import pytest

import poll
from tubematic_core import auth


def _header(url):
    req = urllib.request.Request(url)
    poll._ApiAuth().http_request(req)
    return req.unredirected_hdrs.get("Authorization")


def test_api_requests_carry_the_token():
    token = auth.read_secret("api_token")
    assert _header(f"{poll.RENDERER_URL}/settings") == f"Bearer {token}"


@pytest.mark.parametrize("url", ["https://openrouter.ai/api/v1/models",
                                 "http://localhost:40001/settings",
                                 "http://evil.example/?u=http://localhost:4000/"])
def test_other_urls_never_see_it(url, monkeypatch):
    monkeypatch.setattr(poll, "RENDERER_URL", "http://localhost:4000")
    assert _header(url) is None


def test_a_rotated_token_is_used_without_a_restart():
    auth.rotate_secrets(["api_token"])
    assert _header(f"{poll.RENDERER_URL}/agents") == f"Bearer {auth.read_secret('api_token')}"


def test_main_refuses_to_run_without_a_token(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "none"))
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll.sys, "argv", ["poll.py"])
    monkeypatch.setattr(poll, "_Supervisor",
                        lambda *a: pytest.fail("ran without a token"))
    with pytest.raises(SystemExit) as e:
        poll.main()
    assert e.value.code == 1


def test_install_api_auth_installs_the_opener(monkeypatch):
    installed = []
    monkeypatch.setattr(urllib.request, "install_opener", installed.append)
    assert poll.install_api_auth() is True
    assert any(isinstance(h, poll._ApiAuth) for h in installed[0].handlers)
