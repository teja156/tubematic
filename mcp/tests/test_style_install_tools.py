"""The agent's half of installing an external style (TMDEV-253): stage a package
and record an audit. Neither installs anything; the install screen does, with
the dashboard password, and no MCP tool can confirm one.
"""
import pytest

import server
from tubematic_core import external_styles as ext
from tubematic_core import style_install as si
from tubematic_core.tests.test_external_styles import make_package


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("styles", "pending", "incoming"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(ext, "STYLES_DIR", tmp_path / "styles")
    monkeypatch.setattr(si, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(si, "INCOMING_DIR", tmp_path / "incoming")
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    return tmp_path


def test_an_incoming_folder_is_staged_and_nothing_is_installed(env):
    make_package(env / "incoming", sid="ext_test", approve=False)
    got = server.stage_style_install("incoming:ext_test")
    assert got["style_id"] == "ext_test" and got["check"]["ok"] and got["refusals"] == []
    assert got["host_path"] == f"~/.tubematic-data/styles-pending/{got['pending_id']}/package"
    assert got["dashboard_link"] == f"/styles/install/{got['pending_id']}"
    assert "components/Main.tsx" in got["files"]
    assert not (env / "styles" / "ext_test").exists()


def test_the_link_uses_the_dashboard_address_when_it_is_set(env):
    with server._conn() as con:
        con.execute("INSERT INTO settings (key, value) VALUES ('dashboard_base_url', 'http://box:3000')")
    make_package(env / "incoming", sid="ext_test", approve=False)
    got = server.stage_style_install("incoming:ext_test")
    assert got["dashboard_link"] == f"http://box:3000/styles/install/{got['pending_id']}"


def test_a_bad_source_is_refused_with_the_forms(env):
    assert "incoming:<name>" in server.stage_style_install("ftp://x")["error"]
    assert "commit or a tag" in server.stage_style_install("git:https://github.com/a/b")["error"]
    assert "does not exist" in server.stage_style_install("incoming:nothing")["error"]
    with server._conn() as con:
        con.execute("INSERT INTO settings (key, value) VALUES ('style_gallery_url', '')")
    assert "no gallery address" in server.stage_style_install("gallery:ext_x")["error"]


def test_the_audit_is_recorded_on_the_pending_install(env):
    make_package(env / "incoming", sid="ext_test", approve=False)
    pid = server.stage_style_install("incoming:ext_test")["pending_id"]
    got = server.audit_style_install(pid, "no_concerns", "Read every file; it only draws.")
    assert got["audit"]["verdict"] == "no_concerns"
    assert si.get(pid)["audit"]["notes"] == "Read every file; it only draws."
    assert "verdict" in server.audit_style_install(pid, "fine", "")["error"]
    assert "no such pending" in server.audit_style_install("0" * 16, "concerns", "")["error"]


def test_no_tool_can_confirm_or_remove_an_install():
    """The human yes is the dashboard's: an MCP tool for it would let the
    agent approve its own audit."""
    tools = set(server.mcp._tool_manager._tools) if hasattr(server.mcp, "_tool_manager") else set()
    src = server.__file__ and open(server.__file__, encoding="utf-8").read()
    assert "_style_install.confirm" not in src and "_style_install.remove" not in src
    assert not any("confirm" in t and "style" in t for t in tools)


def test_the_gallery_source_uses_the_curated_gallery_when_the_setting_was_never_written(env, monkeypatch):
    """A fresh install has no style_gallery_url row; the API reads the spec's
    default, and the agent's tool must reach the same gallery."""
    seen = []
    monkeypatch.setattr(si, "gallery_index", lambda url: seen.append(url) or [])
    assert "no style" in server.stage_style_install("gallery:ext_x")["error"]
    assert seen == [si.OFFICIAL_GALLERY_URL]
    with server._conn() as con:
        con.execute("INSERT INTO settings (key, value) VALUES ('style_gallery_url', '')")
    assert "no gallery address" in server.stage_style_install("gallery:ext_x")["error"]
