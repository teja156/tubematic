"""scripts/mcp_auth_header.py, the helper Claude and Codex run per MCP connection.

Run for real as a subprocess, the way the CLIs run it: the contract is its
stdout (one JSON object) and its exit status, nothing else.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "mcp_auth_header.py"


def _run(secrets_dir):
    env = dict(os.environ, TUBEMATIC_SECRETS_DIR=str(secrets_dir))
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                          env=env, cwd="/")


def test_prints_the_bearer_header(tmp_path):
    (tmp_path / "mcp_token").write_text("tok-123\n")
    r = _run(tmp_path)
    assert r.returncode == 0
    assert json.loads(r.stdout) == {"Authorization": "Bearer tok-123"}


def test_a_missing_token_fails_loudly_and_prints_no_header(tmp_path):
    r = _run(tmp_path)
    assert r.returncode == 1
    assert r.stdout == ""
    assert "mcp_token" in r.stderr


def test_it_never_reads_the_api_token(tmp_path):
    """The agent gets the MCP token only; the API token is a different credential."""
    (tmp_path / "mcp_token").write_text("mcp")
    (tmp_path / "api_token").write_text("api")
    assert "api" not in _run(tmp_path).stdout
