"""The single dry-run choke point.

Every *mutating* operation an onboard action performs — running a command that
changes something, writing a file, creating a directory, copying a tree,
writing rows to SQLite, replacing the crontab — goes through an `Executor`
instance instead of calling `subprocess`/`shutil`/`sqlite3` directly.

Read-only operations (docker inspect, shutil.which, reading the DB)
are NOT routed through here — actions call them directly in both modes, so a
dry-run preview reflects the real current state of the machine.

In live mode (`dry_run=False`) each method performs the real action. In dry
mode (`dry_run=True`) each method records an "intent" (for the Review screen
and for tests to assert against) and returns a synthetic success — nothing on
disk, in Docker, or in cron is touched.
"""
import shutil
import sqlite3
import subprocess
from contextlib import nullcontext
from pathlib import Path
from typing import Callable, Sequence


class Intent:
    """A recorded would-be mutation, produced only in dry-run mode."""

    def __init__(self, kind: str, detail: str):
        self.kind = kind
        self.detail = detail

    def __repr__(self) -> str:
        return f"Intent({self.kind!r}, {self.detail!r})"


class Reporter:
    """Duck-typed output sink actions.py writes progress through — never
    printed to directly, so the same action code stays agnostic of exactly
    how progress is rendered (onboard/plain.py's PlainReporter is the only
    implementation, but actions.py doesn't import it or know it exists)."""

    def ok(self, msg: str) -> None:
        raise NotImplementedError

    def info(self, msg: str) -> None:
        raise NotImplementedError

    def warn(self, msg: str) -> None:
        raise NotImplementedError

    def fail(self, msg: str, hint: str = "") -> None:
        raise NotImplementedError

    def spinner(self, msg: str):
        """Context manager shown for the duration of a long-running call
        with no incremental progress of its own (e.g. a docker build) — an
        animated "msg..." indicator, not a log of the command's real output.
        Default no-op so NullReporter and any other minimal Reporter don't
        need to implement it."""
        return nullcontext()


class NullReporter(Reporter):
    """Discards ok/info/warn; fail raises. Used by tests that only care
    about the resulting state, not the narration."""

    def ok(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warn(self, msg: str) -> None:
        pass

    def fail(self, msg: str, hint: str = "") -> None:
        raise RuntimeError(f"{msg} {hint}".strip())


_VERBS = {
    "run": "run",
    "write_file": "write",
    "mkdir": "create directory",
    "touch": "create",
    "copy_file": "copy",
    "copytree": "copy tree",
    "rmtree": "remove",
    "unlink": "delete",
    "chown": "chown",
    "sqlite_write": "write to the database:",
    "crontab_write": "replace the crontab with",
    "ensure_secrets": "create any missing service token in",
    "rotate_secrets": "replace the service tokens",
}


class Executor:
    def __init__(self, dry_run: bool, reporter=None):
        self.dry_run = dry_run
        self.reporter = reporter
        self.intents: list[Intent] = []

    def _record(self, kind: str, detail: str) -> None:
        self.intents.append(Intent(kind, detail))
        if self.reporter is not None:
            verb = _VERBS.get(kind, kind)
            self.reporter.info(f"[dry-run] would {verb} {detail}")

    # ── Subprocess ────────────────────────────────────────────────────────

    def run(self, cmd: Sequence[str], cwd: Path | None = None, **kwargs) -> subprocess.CompletedProcess:
        """Run a command that mutates something (docker build/up, pip install,
        npx skills add, claude mcp add, crontab -, sudo chown, ...).

        Read-only subprocess calls (docker inspect, docker info, docker
        compose version) should call `subprocess.run` directly, not this.
        """
        if self.dry_run:
            self._record("run", " ".join(cmd))
            return subprocess.CompletedProcess(list(cmd), 0, stdout="", stderr="")
        return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, **kwargs)

    # ── Filesystem ────────────────────────────────────────────────────────

    def write_file(self, path: Path, content: str) -> None:
        if self.dry_run:
            self._record("write_file", str(path))
            return
        path.write_text(content)

    def mkdir(self, path: Path, parents: bool = True, exist_ok: bool = True) -> None:
        if self.dry_run:
            self._record("mkdir", str(path))
            return
        path.mkdir(parents=parents, exist_ok=exist_ok)

    def touch(self, path: Path) -> None:
        if self.dry_run:
            self._record("touch", str(path))
            return
        path.touch()

    def copy_file(self, src: Path, dst: Path) -> None:
        if self.dry_run:
            self._record("copy_file", f"{src} -> {dst}")
            return
        shutil.copy2(src, dst)

    def copytree(self, src: Path, dst: Path) -> None:
        if self.dry_run:
            self._record("copytree", f"{src} -> {dst}")
            return
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    def rmtree(self, path: Path) -> None:
        if self.dry_run:
            self._record("rmtree", str(path))
            return
        shutil.rmtree(path)

    def unlink(self, path: Path) -> None:
        if self.dry_run:
            self._record("unlink", str(path))
            return
        path.unlink(missing_ok=True)

    def chown(self, path: Path, uid: int, gid: int) -> None:
        if self.dry_run:
            self._record("chown", f"{path} -> {uid}:{gid}")
            return
        import os
        os.chown(path, uid, gid)

    # ── SQLite ────────────────────────────────────────────────────────────

    def sqlite_write(self, db_path: Path, fn: Callable[[sqlite3.Connection], None], detail: str) -> None:
        """Run `fn(connection)` (INSERT/UPDATE statements) inside a commit.
        `fn` must not be used for reads — callers read directly via a
        throwaway connection, outside the executor, in both modes."""
        if self.dry_run:
            self._record("sqlite_write", detail)
            return
        con = sqlite3.connect(str(db_path))
        try:
            fn(con)
            con.commit()
        finally:
            con.close()

    # ── Service tokens (TMDEV-152) ────────────────────────────────────────
    # The intent names the directory and the token names, never a value.

    def ensure_secrets(self, directory: Path | None = None) -> list:
        from tubematic_core import auth
        target = Path(directory or auth.secrets_dir())
        if self.dry_run:
            self._record("ensure_secrets", str(target))
            return []
        return auth.ensure_secrets(target)

    def rotate_secrets(self, names, directory: Path | None = None) -> None:
        from tubematic_core import auth
        target = Path(directory or auth.secrets_dir())
        if self.dry_run:
            self._record("rotate_secrets", f"{', '.join(names)} in {target}")
            return
        auth.rotate_secrets(names, target)

    # ── Crontab ───────────────────────────────────────────────────────────

    def crontab_write(self, content: str) -> subprocess.CompletedProcess:
        if self.dry_run:
            self._record("crontab_write", content.replace("\n", " \\n "))
            return subprocess.CompletedProcess(["crontab", "-"], 0, stdout="", stderr="")
        return subprocess.run(["crontab", "-"], input=content, text=True, check=False)
