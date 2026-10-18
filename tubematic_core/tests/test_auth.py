"""Secrets and the admin password (TMDEV-152).

The secret files are read by three containers and two host processes, so the
rules that keep them readable -- and the in-place rotation that keeps a running
container's bind mount pointing at the new value -- are pinned here once.
"""
import os
import sqlite3
import stat

import pytest

from tubematic_core import auth


@pytest.fixture
def sdir(tmp_path):
    return tmp_path / "secrets"


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_ensure_creates_every_secret_with_the_documented_modes(sdir):
    created = auth.ensure_secrets(sdir)

    assert sorted(created) == sorted(auth.SECRET_NAMES)
    # The directory keeps other host users out; the files are 0644 because the
    # dashboard container runs as uid 1001 and reads them through a single-file
    # bind mount that bypasses the directory's permissions.
    assert _mode(sdir) == 0o700
    for name in auth.SECRET_NAMES:
        assert _mode(sdir / name) == 0o644
        assert len(auth.read_secret(name, sdir)) >= 40


def test_ensure_never_replaces_an_existing_secret(sdir):
    auth.ensure_secrets(sdir)
    before = {n: auth.read_secret(n, sdir) for n in auth.SECRET_NAMES}

    assert auth.ensure_secrets(sdir) == []
    assert {n: auth.read_secret(n, sdir) for n in auth.SECRET_NAMES} == before


def test_ensure_refills_an_empty_file_and_tightens_a_loose_directory(sdir):
    sdir.mkdir(mode=0o755)
    os.chmod(sdir, 0o755)
    (sdir / "api_token").write_text("")

    created = auth.ensure_secrets(sdir)

    assert "api_token" in created
    assert auth.read_secret("api_token", sdir)
    assert _mode(sdir) == 0o700


def test_rotate_rewrites_in_place_so_a_bind_mount_sees_it(sdir):
    auth.ensure_secrets(sdir)
    inode = os.stat(sdir / "mcp_token").st_ino
    old = auth.read_secret("mcp_token", sdir)

    auth.rotate_secrets(["mcp_token"], sdir)

    # A rename would leave a running container's bind mount on the old inode.
    assert os.stat(sdir / "mcp_token").st_ino == inode
    assert auth.read_secret("mcp_token", sdir) != old
    assert _mode(sdir / "mcp_token") == 0o644


def test_rotate_refuses_an_unknown_name(sdir):
    auth.ensure_secrets(sdir)
    with pytest.raises(ValueError):
        auth.rotate_secrets(["../etc/passwd"], sdir)


@pytest.mark.parametrize("content", [None, "", "   \n"])
def test_read_secret_fails_closed(sdir, content):
    sdir.mkdir()
    if content is not None:
        (sdir / "api_token").write_text(content)
    with pytest.raises(auth.SecretMissing):
        auth.read_secret("api_token", sdir)


def test_read_secret_strips_a_trailing_newline(sdir):
    sdir.mkdir()
    (sdir / "api_token").write_text("abc\n")
    assert auth.read_secret("api_token", sdir) == "abc"


def test_secrets_dir_honours_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path))
    assert auth.secrets_dir() == tmp_path
    monkeypatch.delenv("TUBEMATIC_SECRETS_DIR")
    assert auth.secrets_dir() == auth.HOST_SECRETS_DIR


def test_password_round_trip():
    stored = auth.hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert "correct horse" not in stored
    assert auth.verify_password("correct horse battery", stored)
    assert not auth.verify_password("correct horse batterY", stored)


def test_two_hashes_of_one_password_differ():
    assert auth.hash_password("correct horse battery") != auth.hash_password("correct horse battery")


@pytest.mark.parametrize("stored", ["", "plain", "scrypt$1$2", "scrypt$x$8$1$aa$bb", "md5$1$2$3$aa$bb"])
def test_a_malformed_stored_hash_never_verifies(stored):
    assert auth.verify_password("anything at all", stored) is False


def test_a_short_password_is_refused():
    with pytest.raises(ValueError):
        auth.check_password_strength("short")
    auth.check_password_strength("x" * auth.MIN_PASSWORD_LEN)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    return path


def test_set_admin_password_writes_one_row_outside_settings_spec(db):
    assert auth.has_admin_password(db) is False
    auth.set_admin_password(db, "first password!")
    auth.set_admin_password(db, "second password!")

    con = sqlite3.connect(db)
    rows = con.execute("SELECT key, value FROM settings").fetchall()
    con.close()
    assert [r[0] for r in rows] == [auth.PASSWORD_KEY]
    assert auth.has_admin_password(db) is True
    assert auth.verify_password("second password!", auth.admin_password_hash(db))


def test_set_admin_password_refuses_a_weak_one(db):
    with pytest.raises(ValueError):
        auth.set_admin_password(db, "short")
    assert auth.has_admin_password(db) is False


def test_has_admin_password_is_false_for_a_missing_database(tmp_path):
    assert auth.has_admin_password(tmp_path / "nope.db") is False
