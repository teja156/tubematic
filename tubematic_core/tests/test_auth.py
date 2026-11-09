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

    assert sorted(created) == sorted(auth.SECRET_NAMES + auth.TLS_NAMES)
    assert "builtin_renderer_token" in auth.SECRET_NAMES
    # The directory keeps other host users out; the files are 0644 because the
    # dashboard container runs as uid 1001 and reads them through a single-file
    # bind mount that bypasses the directory's permissions.
    assert _mode(sdir) == 0o700
    for name in auth.SECRET_NAMES + auth.TLS_NAMES:
        assert _mode(sdir / name) == 0o644
        assert len(auth.read_secret(name, sdir)) >= 40


def test_ensure_never_replaces_an_existing_secret(sdir):
    auth.ensure_secrets(sdir)
    names = auth.SECRET_NAMES + auth.TLS_NAMES
    before = {n: auth.read_secret(n, sdir) for n in names}

    assert auth.ensure_secrets(sdir) == []
    assert {n: auth.read_secret(n, sdir) for n in names} == before


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


# ── The render gateway's TLS pair ─────────────────────────────────────────────
#
# Renderers trust exactly this certificate, pinned by the sha256 of its DER, so
# the pair must be a working TLS identity for a stdlib client with no host name
# check, and must never change once made: a new certificate is a new pin, which
# would cut off every enrolled renderer.

import socket  # noqa: E402
import ssl  # noqa: E402
import threading  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from tubematic_core import renderers  # noqa: E402


def _cert(sdir):
    return x509.load_pem_x509_certificate((sdir / auth.TLS_CERT_NAME).read_bytes())


def _key(sdir):
    return serialization.load_pem_private_key((sdir / auth.TLS_KEY_NAME).read_bytes(), password=None)


def test_the_certificate_is_the_documented_self_signed_p256_ca(sdir):
    auth.ensure_secrets(sdir)
    cert, key = _cert(sdir), _key(sdir)

    assert isinstance(key, ec.EllipticCurvePrivateKey) and key.curve.name == "secp256r1"
    assert cert.subject == cert.issuer
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "tubematic-render-gateway"
    bc = cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert bc.critical and bc.value.ca is True
    ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
    assert ku.digital_signature and ku.key_cert_sign
    # No host name: renderers reach the gateway by any address, so nothing is
    # checked against one.
    with pytest.raises(x509.ExtensionNotFound):
        cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    life = cert.not_valid_after_utc - datetime.now(timezone.utc)
    assert timedelta(days=365 * 30 - 2) < life < timedelta(days=365 * 30 + 1)


def test_the_key_matches_the_certificate(sdir):
    auth.ensure_secrets(sdir)
    pub = serialization.PublicFormat.SubjectPublicKeyInfo
    assert (_key(sdir).public_key().public_bytes(serialization.Encoding.DER, pub)
            == _cert(sdir).public_key().public_bytes(serialization.Encoding.DER, pub))


@pytest.mark.parametrize("damage", ["delete_key", "delete_cert", "empty_cert"])
def test_an_incomplete_pair_is_made_again_as_a_pair(sdir, damage):
    auth.ensure_secrets(sdir)
    old_cert = (sdir / auth.TLS_CERT_NAME).read_text()
    target = sdir / (auth.TLS_KEY_NAME if damage == "delete_key" else auth.TLS_CERT_NAME)
    if damage.startswith("delete"):
        target.unlink()
    else:
        target.write_text("")

    assert sorted(auth.ensure_secrets(sdir)) == sorted(auth.TLS_NAMES)
    assert (sdir / auth.TLS_CERT_NAME).read_text() != old_cert
    pub = serialization.PublicFormat.SubjectPublicKeyInfo
    assert (_key(sdir).public_key().public_bytes(serialization.Encoding.DER, pub)
            == _cert(sdir).public_key().public_bytes(serialization.Encoding.DER, pub))


@pytest.mark.parametrize("missing", [auth.TLS_KEY_NAME, auth.TLS_CERT_NAME])
def test_an_interrupted_repair_never_leaves_a_pair_that_looks_whole(sdir, monkeypatch, missing):
    """The repair renames the half still present first, so stopping between
    the two renames leaves the missing name missing: the next ensure makes
    the pair again, rather than a new half beside an old one that nothing
    would ever repair."""
    auth.ensure_secrets(sdir)
    (sdir / missing).unlink()
    real = os.replace
    done = []

    def stop_after_one(src, dst):
        if done:
            raise OSError("interrupted")
        done.append(dst)
        real(src, dst)
    monkeypatch.setattr(os, "replace", stop_after_one)
    with pytest.raises(OSError):
        auth.ensure_secrets(sdir)
    with pytest.raises(auth.SecretMissing):
        auth.read_secret(missing, sdir)
    monkeypatch.setattr(os, "replace", real)

    assert sorted(auth.ensure_secrets(sdir)) == sorted(auth.TLS_NAMES)
    pub = serialization.PublicFormat.SubjectPublicKeyInfo
    assert (_key(sdir).public_key().public_bytes(serialization.Encoding.DER, pub)
            == _cert(sdir).public_key().public_bytes(serialization.Encoding.DER, pub))
    assert sorted(p.name for p in sdir.iterdir()) == sorted(auth.SECRET_NAMES + auth.TLS_NAMES)   # no temp left
    for name in auth.TLS_NAMES:
        assert _mode(sdir / name) == 0o644


def test_a_whole_pair_that_does_not_load_is_never_replaced(sdir, tmp_path):
    """Two non-empty files are left alone even when they are not a pair: a
    new certificate is a new pin, so it is never made silently (the gateway
    refuses to start and says how to recover)."""
    auth.ensure_secrets(sdir)
    other = tmp_path / "other"
    auth.ensure_secrets(other)
    (sdir / auth.TLS_CERT_NAME).write_text((other / auth.TLS_CERT_NAME).read_text())
    before = {n: (sdir / n).read_text() for n in auth.TLS_NAMES}
    assert auth.ensure_secrets(sdir) == []
    assert {n: (sdir / n).read_text() for n in auth.TLS_NAMES} == before


def test_the_tls_pair_is_never_rotated(sdir):
    auth.ensure_secrets(sdir)
    before = {n: (sdir / n).read_text() for n in auth.TLS_NAMES}
    for name in auth.TLS_NAMES:
        with pytest.raises(ValueError):
            auth.rotate_secrets([name], sdir)
    # --rotate-tokens rotates SECRET_NAMES, the built-in renderer's token among
    # them, and leaves the pair alone.
    old_builtin = auth.read_secret("builtin_renderer_token", sdir)
    auth.rotate_secrets(auth.SECRET_NAMES, sdir)
    assert auth.read_secret("builtin_renderer_token", sdir) != old_builtin
    assert {n: (sdir / n).read_text() for n in auth.TLS_NAMES} == before


def test_gateway_pin_is_the_sha256_of_the_certificate_der(sdir):
    auth.ensure_secrets(sdir)
    der = _cert(sdir).public_bytes(serialization.Encoding.DER)
    assert auth.gateway_pin(sdir) == renderers.cert_pin(der)
    assert auth.gateway_pin(sdir).startswith("sha256:") and len(auth.gateway_pin(sdir)) == 71


def test_gateway_pin_fails_closed_without_a_certificate(sdir):
    sdir.mkdir()
    with pytest.raises(auth.SecretMissing):
        auth.gateway_pin(sdir)


def test_gateway_pin_reads_the_secrets_dir_override(sdir, monkeypatch):
    auth.ensure_secrets(sdir)
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(sdir))
    assert auth.gateway_pin() == auth.gateway_pin(sdir)


def _serve_once(sdir):
    """A localhost TLS server presenting the pair in `sdir`, for one handshake."""
    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(sdir / auth.TLS_CERT_NAME, sdir / auth.TLS_KEY_NAME)
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]

    def run():
        try:
            conn, _ = listener.accept()
            with server_ctx.wrap_socket(conn, server_side=True) as tls:
                tls.sendall(b"ok")
        except (ssl.SSLError, OSError):
            pass   # the client refused us, which some tests expect
        finally:
            listener.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return port, thread


def _pinned_client(pem: str) -> ssl.SSLContext:
    """Exactly the client a renderer builds: trust this one certificate, no
    host name check, verification required."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=pem)
    return ctx


def test_a_client_pinned_to_the_certificate_completes_a_handshake(sdir):
    auth.ensure_secrets(sdir)
    port, thread = _serve_once(sdir)
    ctx = _pinned_client((sdir / auth.TLS_CERT_NAME).read_text())
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with ctx.wrap_socket(raw) as tls:
            assert tls.recv(2) == b"ok"
            assert renderers.cert_pin(tls.getpeercert(binary_form=True)) == auth.gateway_pin(sdir)
    thread.join(5)


def test_a_client_pinned_to_another_certificate_refuses_the_server(sdir, tmp_path):
    auth.ensure_secrets(sdir)
    other = tmp_path / "other"
    auth.ensure_secrets(other)
    port, thread = _serve_once(sdir)
    ctx = _pinned_client((other / auth.TLS_CERT_NAME).read_text())
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with pytest.raises(ssl.SSLCertVerificationError):
            ctx.wrap_socket(raw)
    thread.join(5)
