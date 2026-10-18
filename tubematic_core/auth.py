"""Service tokens and the admin password (TMDEV-152).

Three random secrets live as one file each in a secrets directory:

  api_token       the API's bearer token (dashboard, poll.py, host scripts)
  mcp_token       the MCP server's bearer token (agent CLIs, via a helper)
  session_secret  the key the dashboard signs its session cookie with

On the host the directory is ~/.tubematic-data/secrets; inside a container
Compose mounts each file at /run/secrets/<name> and sets TUBEMATIC_SECRETS_DIR.

Two rules here look odd and are load-bearing:

* The directory is 0700 but the files are 0644. Compose mounts each file on
  its own (a single-file bind mount), which bypasses the directory's
  permissions inside the container -- and the dashboard runs as uid 1001, not
  the host user, so a 0600 file would be unreadable there. The 0700 directory
  is what keeps other users on the host out.
* Rotation rewrites a file in place. A bind mount pins the inode it was given
  at start, so an atomic rename would leave every running container reading
  the old value until it was recreated.

The admin password is not a file: its scrypt hash is a bare `settings` row
outside SETTINGS_SPEC, so `GET /settings` can never return it and
`POST /settings` refuses to write it.

Run as a module for the two jobs that have no Python caller of their own:
  python3 -m tubematic_core.auth ensure [--dir DIR]
  python3 -m tubematic_core.auth set-password --db PATH   (password on stdin)
"""
import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import sys
from pathlib import Path

SECRET_NAMES = ("api_token", "mcp_token", "session_secret")
HOST_SECRETS_DIR = Path.home() / ".tubematic-data" / "secrets"
PASSWORD_KEY = "admin_password_hash"
MIN_PASSWORD_LEN = 12

# scrypt at N=2**15, r=8 needs 32 MiB, exactly hashlib's default ceiling, so the
# ceiling is raised rather than the cost lowered.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 15, 8, 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


class SecretMissing(RuntimeError):
    """A secret file is absent or empty. Callers fail closed on this."""


def secrets_dir() -> Path:
    override = os.environ.get("TUBEMATIC_SECRETS_DIR")
    return Path(override) if override else HOST_SECRETS_DIR


def read_secret(name: str, directory: Path | None = None) -> str:
    path = Path(directory or secrets_dir()) / name
    try:
        value = path.read_text().strip()
    except OSError as e:
        raise SecretMissing(f"cannot read {path}: {e.strerror}") from None
    if not value:
        raise SecretMissing(f"{path} is empty")
    return value


def _write_in_place(path: Path, value: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(path, 0o644)


def ensure_secrets(directory: Path | None = None) -> list[str]:
    """Create any missing or empty secret. Never replaces one. Returns the names created."""
    d = Path(directory or secrets_dir())
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    created = []
    for name in SECRET_NAMES:
        try:
            read_secret(name, d)
        except SecretMissing:
            _write_in_place(d / name, secrets.token_urlsafe(32))
            created.append(name)
    return created


def rotate_secrets(names, directory: Path | None = None) -> None:
    d = Path(directory or secrets_dir())
    for name in names:
        if name not in SECRET_NAMES:
            raise ValueError(f"unknown secret {name!r}")
        _write_in_place(d / name, secrets.token_urlsafe(32))


def check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"the password must be at least {MIN_PASSWORD_LEN} characters")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                            p=_SCRYPT_P, maxmem=_SCRYPT_MAXMEM)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check. A malformed stored value never verifies, never raises."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest, validate=True)
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt, validate=True),
                                n=int(n), r=int(r), p=int(p), maxmem=_SCRYPT_MAXMEM,
                                dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def admin_password_hash(db_path) -> str | None:
    if not Path(db_path).exists():
        return None
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (PASSWORD_KEY,)).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()
    return row[0] if row and row[0] else None


def has_admin_password(db_path) -> bool:
    return admin_password_hash(db_path) is not None


def set_admin_password(db_path, password: str) -> None:
    check_password_strength(password)
    con = sqlite3.connect(db_path)
    try:
        con.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (PASSWORD_KEY, hash_password(password)))
        con.commit()
    finally:
        con.close()


def _main(argv: list[str]) -> int:
    def opt(flag):
        return argv[argv.index(flag) + 1] if flag in argv else None

    if argv[:1] == ["ensure"]:
        created = ensure_secrets(Path(opt("--dir")) if opt("--dir") else None)
        print("created: " + (", ".join(created) or "nothing"))
        return 0
    if argv[:1] == ["set-password"] and opt("--db"):
        try:
            set_admin_password(opt("--db"), sys.stdin.readline().rstrip("\n"))
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print("admin password set")
        return 0
    print(__doc__.split("Run as a module")[1].strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
