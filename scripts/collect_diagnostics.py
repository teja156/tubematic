#!/usr/bin/env python3
"""Collect a redacted diagnostics report for a Tubematic bug report (TMDEV-167).

    python3 scripts/collect_diagnostics.py [--video vid_…] [--since 24] [--lines 200]
                                           [--include-content] [--out DIR]

Writes one Markdown file, report.md, to ~/tubematic-diagnostics-<UTC time>/ —
outside ~/.tubematic-data on purpose, so an agent helping with the report can
read it without being let into the data directory, where every API key lives.

Redaction is done here, deterministically, rather than left to the agent: a
model asked to "remove the secrets" does it probabilistically, and one miss
publishes a live key. This script can read the real stored values and match
them literally, which a model is never allowed to see. Four layers, in order:

1. values   — every stored secret, the service tokens, the password hash;
2. patterns — tubematic_core.logging.redact, the same rules the services use;
3. publish  — emails, IPs, host/user names, home paths, password-hash shapes,
              and postforme account / ElevenLabs voice ids (hashed, so lines
              about the same account still match up). These live here and not
              in the service logs, where they are useful for debugging;
4. content  — every video's title, topic, script, review feedback, publish text
              and human comments, domain names, mining sources, the user's
              preferences and pronunciation lexicon, unless --include-content.
              Matched line by line and sentence by sentence, so a log quoting
              part of one is caught too; a piece under 12 characters only as a
              whole word, and one under 4 not at all.

Then a residual scan re-checks the finished text for every value from layer 1
and for raw key shapes. Any hit and nothing is written (exit 2), and only the
*kind* of value that survived is named — never the value. Long log lines are
cut to length only after all of that: a cut made first could split a stored
secret, and the remaining prefix would no longer match it.

Read-only throughout: the database is opened with mode=ro, and nothing is sent
anywhere. Filing the issue is left to the human.
"""
import argparse
import datetime as dt
import getpass
import hashlib
import ipaddress
import json
import os
import platform
import re
import shlex
import socket
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from onboard import stack  # noqa: E402
from onboard.config import DATA_ROOT, DB_PATH, POLL_LOG_DIR  # noqa: E402
from tubematic_core import auth as tauth  # noqa: E402
from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import logging as tlog  # noqa: E402
from tubematic_core.version import GITHUB_REPO, version  # noqa: E402

LOG_DIR = DATA_ROOT / "logs"
POLL_LOG = POLL_LOG_DIR / "poll.log"
HEARTBEAT = POLL_LOG_DIR.parent / "poll.heartbeat"
API_URL = "http://localhost:4000"
MCP_URL = "http://localhost:4100"

# Keep in sync: renderer/api/pipeline.py SETTINGS_SPEC secret-typed keys
# (pinned by renderer/api/tests/test_secret_key_copies.py). Copied rather than
# imported: pipeline.py pulls in Flask, and renderer/ is not in the release tarball.
SECRET_SETTING_KEYS = (
    "discord_webhook_url", "elevenlabs_api_key", "gemini_api_key", "openai_api_key",
    "youtube_transcript_api_key", "postforme_api_key",
)
PASSWORD_KEY = tauth.PASSWORD_KEY

# Settings whose values are the user's own material rather than configuration.
CONTENT_SETTING_KEYS = ("user_preferences", "mining_youtube_urls", "pronunciation_lexicon",
                        "mining_url_cursor")

# A value longer than this, or any JSON, is shown as its size: the report is for
# configuration, and long values are where private material hides.
SETTING_VALUE_MAX = 80
LINE_MAX = 2000
# Content at least this long is replaced wherever it appears. Shorter content
# is replaced only as a whole word, or a short title would cut into ordinary
# words; content shorter than CONTENT_WORD_MIN says nothing private and is left.
CONTENT_MIN = 12
CONTENT_WORD_MIN = 4
# The domain every dashboard submission files into, created by Tubematic itself:
# its id says nothing about the user, and "manual" is also an ordinary word.
BUILTIN_DOMAIN_IDS = ("manual",)
SECRET_MIN = 8        # same floor as tlog.redact

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")
_HASH_RE = re.compile(r"\b(?:scrypt|argon2(?:id|i|d)?|pbkdf2[\w:-]*|bcrypt)\$[^\s\"']+")
_HANDLE_RE = re.compile(r'(?i)("(?:username|handle|display_name)"\s*:\s*")([^"]+)(")')
# Raw key shapes the residual scan refuses to let through.
_RESIDUAL_SHAPES = {
    "an OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    "an ElevenLabs-style key": re.compile(r"\bsk_[A-Za-z0-9]{20,}"),
    "a Google API key": re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"),
    "a bearer token": re.compile(r"(?i)\bbearer\s+(?!\*\*\*REDACTED)[A-Za-z0-9._~+/=-]{12,}"),
}


# Private-use characters bracketing a content placeholder while redaction runs.
_PH_OPEN, _PH_CLOSE = "\ue000", "\ue001"


def _wordish(c: str) -> bool:
    """Part of a word, for whole-word matching: the same set as the domain-id rule."""
    return c.isalnum() or c in "_-"


def _short_hash(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha256(value.encode()).hexdigest()[:6]}"


def _domain_label(domain_id: str) -> str:
    return _short_hash("domain", domain_id)


class Redactor:
    """Every rule applied to the report, plus the residual check.

    Built once from what is on disk, then applied to the whole text, so no
    section can forget to call it.
    """

    def __init__(self, *, secrets, account_ids=(), voice_ids=(), content=(), domain_ids=(),
                 home="", user="", host=""):
        self.secrets = sorted({s for s in secrets if s and len(s) >= SECRET_MIN},
                              key=len, reverse=True)
        self.ids = sorted(
            [(v, _short_hash("acct", v)) for v in set(account_ids) if v and len(v) >= 4]
            + [(v, _short_hash("voice", v)) for v in set(voice_ids) if v and len(v) >= 4],
            key=lambda p: len(p[0]), reverse=True)
        self.content = sorted(((lit, label) for lit, label in content if lit and len(lit) >= CONTENT_MIN),
                              key=lambda p: len(p[0]), reverse=True)
        self.short_content = {}
        for lit, label in content:
            if lit and CONTENT_WORD_MIN <= len(lit) < CONTENT_MIN:
                self.short_content.setdefault(lit, label)
        # Matched as whole words: a domain id is a short slug such as
        # "linux-internals", and a substring match would cut into other words.
        self.domain_ids = [(re.compile(r"(?<![\w-])" + re.escape(d) + r"(?![\w-])"), _domain_label(d))
                           for d in sorted(set(domain_ids), key=len, reverse=True)
                           if d and len(d) >= 3 and d not in BUILTIN_DOMAIN_IDS]
        self.home = home.rstrip("/") if home and home != "/" else ""
        self.user = user if user and len(user) >= 3 else ""
        self.host = host if host and len(host) >= 3 else ""
        self.counts = {}

    def _count(self, rule, n):
        if n:
            self.counts[rule] = self.counts.get(rule, 0) + n

    def _sub(self, rule, pattern, repl, text):
        text, n = pattern.subn(repl, text)
        self._count(rule, n)
        return text

    def apply(self, text: str) -> str:
        before = text.count(tlog._REDACTED)
        text = tlog.redact(text, self.secrets)
        self._count("keys and tokens", text.count(tlog._REDACTED) - before)
        text = self._sub("password hashes", _HASH_RE, "<password-hash>", text)
        text = self._sub("emails", _EMAIL_RE, "<email>", text)
        text = _IPV4_RE.sub(self._ip, text)
        text = _IPV6_RE.sub(self._ip, text)
        for value, label in self.ids:
            self._count("account and voice ids", text.count(value))
            text = text.replace(value, label)
        text = self._sub("handles", _HANDLE_RE,
                         lambda m: m.group(1) + _short_hash("handle", m.group(2)) + m.group(3), text)
        # Fenced so the whole-word pass below cannot match inside a placeholder
        # ("<comment vid_1>" holds the word "comment"); the fences go after it.
        for literal, label in self.content:
            self._count("private content", text.count(literal))
            text = text.replace(literal, _PH_OPEN + label + _PH_CLOSE)
        text = self._replace_short_content(text).replace(_PH_OPEN, "").replace(_PH_CLOSE, "")
        for pattern, label in self.domain_ids:
            text = self._sub("private content", pattern, label, text)
        if self.home:
            text = self._sub("home paths", re.compile(re.escape(self.home) + r"(?![\w.-])"), "~", text)
        if self.host:
            text = self._sub("host name", re.compile(r"(?<![\w.-])" + re.escape(self.host) + r"(?![\w-])"),
                             "<host>", text)
        if self.user:
            text = self._sub("user name", re.compile(r"(?<![\w.-])" + re.escape(self.user) + r"(?![\w-])"),
                             "<user>", text)
        return text

    def _replace_short_content(self, text: str) -> str:
        """Replace each short content literal where it stands as a whole word.

        A scan rather than one regex alternation: an install can hold thousands
        of short pieces, and an alternation tries every one at every position.
        """
        if not self.short_content:
            return text
        lengths = sorted({len(k) for k in self.short_content}, reverse=True)
        firsts = {k[0] for k in self.short_content}
        out, last, i, n = [], 0, 0, len(text)
        while i < n:
            c = text[i]
            if c == _PH_OPEN:
                close = text.find(_PH_CLOSE, i)
                i = n if close < 0 else close + 1
                continue
            if c in firsts and (i == 0 or not _wordish(text[i - 1])):
                for length in lengths:
                    end = i + length
                    label = self.short_content.get(text[i:end]) if end <= n else None
                    if label and (end == n or not _wordish(text[end])):
                        out += [text[last:i], label]
                        self._count("private content", 1)
                        last = i = end
                        break
                else:
                    i += 1
                continue
            i += 1
        out.append(text[last:])
        return "".join(out)

    def _ip(self, m):
        raw = m.group(0)
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return raw   # a timestamp or a type annotation, not an address
        if addr.is_loopback or addr.is_unspecified:
            return raw
        self._count("IP addresses", 1)
        return "<ip>"

    def residual(self, text: str) -> list:
        """The kinds of value still present. Never the values themselves."""
        found = []
        if any(s in text for s in self.secrets):
            found.append("a stored secret or service token")
        found += [kind for kind, rx in _RESIDUAL_SHAPES.items() if rx.search(text)]
        return found


# ── Reading the install ──────────────────────────────────────────────────────

def _connect_ro(db_path: Path):
    """Read-only, so collecting a report can never change the install."""
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)


def _run(argv, timeout=10) -> str:
    """stdout+stderr of a command, or a one-line reason it could not run."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return f"(not installed: {argv[0]})"
    except subprocess.TimeoutExpired:
        return f"(timed out after {timeout}s)"
    return (r.stdout + r.stderr).strip()


def _http_status(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:   # noqa: S310 - fixed localhost URL
            return str(r.status)
    except Exception as e:  # noqa: BLE001 - reported, never raised
        return f"unreachable ({type(e).__name__})"


def _settings(db_path: Path) -> dict:
    con = _connect_ro(db_path)
    try:
        return dict(con.execute("SELECT key, value FROM settings").fetchall())
    finally:
        con.close()


def _secret_values(settings: dict) -> list:
    values = [settings.get(k, "") for k in SECRET_SETTING_KEYS]
    values += [os.environ.get(k.upper(), "") for k in SECRET_SETTING_KEYS]
    values.append(settings.get(PASSWORD_KEY, ""))
    for name in tauth.SECRET_NAMES:
        try:
            values.append(tauth.read_secret(name))
        except tauth.SecretMissing:
            # Absent or empty is nothing to redact. Present but unreadable is
            # a value we cannot match, so the report must not be written.
            path = tauth.secrets_dir() / name
            if path.exists() and not os.access(path, os.R_OK):
                raise OSError(f"cannot read the {name} file") from None
    return [v for v in values if v]


def _account_ids(db_path: Path, settings: dict) -> list:
    ids = []
    con = _connect_ro(db_path)
    try:
        ids += [r[0] for r in con.execute(
            "SELECT DISTINCT social_account_id FROM video_publications")]
    except sqlite3.Error:
        pass
    finally:
        con.close()

    def leaves(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for v in node.values():
                yield from leaves(v)
        elif isinstance(node, list):
            for v in node:
                yield from leaves(v)
    try:
        cfg = json.loads(settings.get("auto_pilot_config") or "{}")
        ids += list(leaves(cfg.get("projects", {})))
    except (ValueError, AttributeError):
        pass
    return ids


def _voice_ids(db_path: Path, settings: dict) -> list:
    """The roster's ids and every id a video or domain still holds: a voice
    removed from the roster stays on the videos voiced with it and the domains
    defaulting to it, and errors name it."""
    ids = [settings.get("elevenlabs_voice_id", "")]
    try:
        ids += [v.get("voice_id", "") for v in json.loads(settings.get("elevenlabs_voices") or "[]")]
    except (ValueError, AttributeError):
        pass
    if db_path.exists():
        con = _connect_ro(db_path)
        try:
            for query in ("SELECT DISTINCT voice_id FROM videos",
                          "SELECT DISTINCT default_voice_id FROM projects"):
                try:
                    ids += [r[0] for r in con.execute(query)]
                except sqlite3.Error:
                    pass
        finally:
            con.close()
    return ids


def _content_literals(db_path: Path, settings: dict) -> tuple:
    """(literal, placeholder) pairs, and the domain ids to hash.

    A domain id is content too, not an opaque key: the agent names a domain
    with a slug of its subject ("linux-internals"), so printing it would
    publish the domain's name under another spelling. Video ids are random.
    """
    out, domain_ids = [], []
    con = _connect_ro(db_path)
    con.row_factory = sqlite3.Row
    try:
        for v in con.execute("SELECT * FROM videos"):
            v, vid = dict(v), v["id"]
            for col, label in _VIDEO_CONTENT:
                out += _pieces(v.get(col), f"<{label} {vid}>")
            try:
                for seg in json.loads(v.get("script_segments") or "[]") or []:
                    for field in ("voice", "visual"):
                        out += _pieces(seg.get(field) if isinstance(seg, dict) else None,
                                       f"<script {vid}>")
            except ValueError:
                pass
        # Human comments only. Agent-authored ones are mostly Tubematic's own
        # messages — the worker files every render error and review outcome as
        # one — and that error text is what the report exists to carry. Any
        # script or topic an agent comment quotes is caught by those literals.
        for c in con.execute("SELECT video_id, content FROM comments WHERE author = 'human'"):
            out += _pieces(c["content"], f"<comment {c['video_id']}>")
        for p in con.execute("SELECT id, name, description FROM projects"):
            pid = p["id"]
            label = _domain_label(pid) if pid not in BUILTIN_DOMAIN_IDS else pid
            out += _pieces(p["name"], f"<domain {label}>")
            out += _pieces(p["description"], f"<domain description {label}>")
            domain_ids.append(pid)
    except sqlite3.Error:
        pass
    finally:
        con.close()
    out += _pieces(settings.get("user_preferences"), "<preferences>")
    try:
        for entry in json.loads(settings.get("pronunciation_lexicon") or "[]") or []:
            if isinstance(entry, dict):
                out += [(entry.get(k), "<lexicon>") for k in ("term", "respell")
                        if isinstance(entry.get(k), str)]
    except ValueError:
        pass
    try:
        urls = json.loads(settings.get("mining_youtube_urls") or "[]")
        out += [(u, "<mining source>") for u in urls if isinstance(u, str)]
    except ValueError:
        pass
    return out, domain_ids


# Video columns written by the human or the agent about the video's subject.
_VIDEO_CONTENT = (("title", "title"), ("topic", "topic"), ("script", "script"),
                  ("tts_text", "script"), ("gemini_feedback", "review"),
                  ("publish_title", "publish title"), ("publish_description", "publish description"))
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _pieces(text, label) -> list:
    """The whole value, each line and each sentence, as (literal, label) pairs.

    A log rarely quotes a whole script or comment; it quotes a line or a
    sentence of one. Longest-first replacement in Redactor means a whole match
    still wins over its parts.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    pieces = {text.strip()}
    for line in text.splitlines():
        pieces.add(line.strip())
        pieces.update(s.strip() for s in _SENTENCE_END.split(line))
    return [(p, label) for p in pieces if p]


# ── Sections ─────────────────────────────────────────────────────────────────

def _fence(lines) -> str:
    # Not cut to LINE_MAX here: that happens after redaction (_clip_log_lines).
    body = "\n".join(str(ln).replace("~~~", "~ ~ ~") for ln in lines)
    return "~~~text\n" + (body or "(empty)") + "\n~~~"


def _clip_log_lines(text: str) -> str:
    """Cut each line inside a log fence to LINE_MAX. Runs on redacted text only."""
    out, in_fence = [], False
    for line in text.split("\n"):
        if line in ("~~~text", "~~~"):
            in_fence = line == "~~~text"
        elif in_fence and len(line) > LINE_MAX:
            line = line[:LINE_MAX] + " …(cut)"
        out.append(line)
    return "\n".join(out)


def section_install(db_path: Path) -> str:
    from onboard.config import resolve_install_mode
    from onboard.state import load_state
    mode = resolve_install_mode(None, recorded=load_state().get("install_mode"))
    lines = [f"- Version: `{version()}`",
             f"- Install type: {'release tarball' if mode == 'release' else 'source checkout'}"]
    if (REPO_ROOT / ".git").exists():
        branch = _run(["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"])
        sha = _run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"])
        lines.append(f"- Git: `{branch}` @ `{sha}`")
    lines.append(f"- Install directory: `{REPO_ROOT}`")
    shipped = max((m.version for m in tdb.discover()), default=0)
    try:
        applied = tdb.current_schema_version(db_path) if db_path.exists() else None
    except sqlite3.Error as e:
        applied = f"unreadable ({e})"
    lines.append(f"- Database schema: {applied if applied is not None else 'no database'}"
                 f" (this version ships {shipped})")
    try:
        os_name = platform.freedesktop_os_release().get("PRETTY_NAME", "")
    except (OSError, AttributeError):
        os_name = ""
    lines += [f"- OS: {os_name or platform.system()} — kernel {platform.release()} ({platform.machine()})",
              f"- Python: {platform.python_version()}",
              f"- Docker: {_run(['docker', 'version', '--format', '{{.Server.Version}}'])}",
              f"- Compose: {_run(['docker', 'compose', 'version', '--short'])}",
              f"- Node: {_run(['node', '--version'])}"]
    return "\n".join(lines)


def section_stack() -> str:
    rows = ["| Container | State | Health |", "|---|---|---|"]
    for name in stack.SERVICES:
        try:
            state, health = stack._container_state(name)
        except FileNotFoundError:
            state, health = "docker not installed", ""
        rows.append(f"| {name} | {state or 'missing'} | {health or '—'} |")
    line = stack.poll_cron_line(stack.read_crontab())
    target = stack.install_dir_of(line) if line else None
    beat = "never"
    if HEARTBEAT.exists():
        age = dt.datetime.now().timestamp() - HEARTBEAT.stat().st_mtime
        beat = f"{int(age // 60)} min ago"
    rows += ["",
             f"- API `/health`: {_http_status(API_URL + '/health')}",
             f"- MCP `/health`: {_http_status(MCP_URL + '/health')}",
             f"- Cron entry: {'present, runs ' + str(target) if line else 'missing'}",
             f"- Poller heartbeat: {beat}"]
    return "\n".join(rows)


def section_agents(db_path: Path) -> str:
    con = _connect_ro(db_path)
    con.row_factory = sqlite3.Row
    try:
        agents = con.execute("SELECT * FROM agents ORDER BY id").fetchall()
    finally:
        con.close()
    if not agents:
        return "No agents installed."
    rows = ["| Agent | CLI version | Scope | Models | Effort | Default | Archived |",
            "|---|---|---|---|---|---|---|"]
    for a in agents:
        a = dict(a)
        cli = _run([a.get("binary") or a["name"], "--version"], timeout=5).splitlines()
        rows.append(f"| {a['name']} | {(cli or ['?'])[0][:60]} | {a.get('install_scope', '')} | "
                    f"{a.get('models', '')} | {a.get('effort', '')} | "
                    f"{'yes' if a.get('is_default') else ''} | {'yes' if a.get('archived_at') else ''} |")
    return "\n".join(rows)


def section_settings(settings: dict, include_content: bool) -> str:
    rows = ["| Setting | Value |", "|---|---|"]
    for key in sorted(settings):
        value = settings[key] or ""
        if key in SECRET_SETTING_KEYS or key == PASSWORD_KEY:
            shown = "set" if value else "unset"
        elif key == "elevenlabs_voices":
            try:
                voices = json.loads(value or "[]")
                shown = "; ".join(f"{v.get('voice_id', '')} ({v.get('model_id', '')})" for v in voices) \
                    or "none"
            except (ValueError, AttributeError):
                shown = f"<{len(value)} chars>"
        elif key in CONTENT_SETTING_KEYS and not include_content:
            shown = f"<{len(value)} chars, omitted>"
        elif len(value) > SETTING_VALUE_MAX or value.lstrip()[:1] in ("{", "["):
            shown = f"<{len(value)} chars>" if not include_content else value
        else:
            shown = value
        rows.append(f"| {key} | `{shown}` |" if shown else f"| {key} | |")
    return "\n".join(rows)


def section_pipeline(db_path: Path, video_id: str, include_content: bool) -> str:
    con = _connect_ro(db_path)
    con.row_factory = sqlite3.Row
    try:
        counts = con.execute(
            "SELECT status, COUNT(*) AS n FROM videos GROUP BY status ORDER BY status").fetchall()
        out = ["| Status | Videos |", "|---|---|"] + [f"| {r['status']} | {r['n']} |" for r in counts]
        if video_id:
            v = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
            if v is None:
                out += ["", f"No video `{video_id}`."]
            else:
                v = dict(v)
                out += ["", f"### Video `{video_id}`", "",
                        f"- Status: {v.get('status')}", f"- Created: {v.get('created_at')}",
                        f"- Updated: {v.get('updated_at')}", f"- Strategy: {v.get('strategy')}",
                        f"- Agent: {v.get('agent_id')} {v.get('agent_model')} {v.get('agent_effort')}",
                        f"- Visual style: {v.get('visual_style')}"]
                if include_content:
                    out += [f"- Topic: {v.get('topic')}", "", "AI review feedback:",
                            _fence((v.get("gemini_feedback") or "").splitlines())]
                comments = con.execute(
                    "SELECT created_at, author, content FROM comments WHERE video_id = ? ORDER BY id",
                    (video_id,)).fetchall()
                out += ["", "Comments:", _fence(
                    f"{c['created_at']} {c['author']}" + (f": {c['content']}" if include_content else "")
                    for c in comments)]
        return "\n".join(out)
    finally:
        con.close()


def section_jsonl(video_id: str, since_hours: float, limit: int) -> str:
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=since_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    records = [r for r in tlog.read_logs(LOG_DIR, min_level="warning", video_id=video_id or None,
                                         limit=limit)
               if str(r.get("ts", "")) >= cutoff]
    records.sort(key=lambda r: str(r.get("ts", "")))
    return _fence(f"{r.get('ts')} {r.get('service')} {r.get('level')}"
                  + (f" [{r['video_id']}]" if r.get("video_id") else "")
                  + f" {r.get('message', '')}" for r in records[-limit:])


_ROTATED_SUFFIX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _poll_line_time(line: str):
    """The aware timestamp poll.py's formatter starts each line with, or None."""
    try:
        return dt.datetime.strptime(line.split(" ", 1)[0], "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def section_poll_log(video_id: str, since_hours: float, limit: int) -> str:
    """poll.log and its dated rotations (poll.py rotates at local midnight),
    cut to --since. A line with no timestamp continues a multi-line message
    and takes the time of the line it belongs to."""
    if not POLL_LOG.exists():
        return "No poll.log."
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=since_hours)
    first_day = cutoff.astimezone().date().isoformat()
    rotated = sorted(f for f in POLL_LOG.parent.glob(POLL_LOG.name + ".*")
                     if _ROTATED_SUFFIX.match(f.suffix[1:]) and f.suffix[1:] >= first_day)
    lines, when = [], None
    for f in [*rotated, POLL_LOG]:
        for line in f.read_text(errors="replace").splitlines():
            when = _poll_line_time(line) or when
            if when is not None and when >= cutoff:
                lines.append(line)
    if video_id:
        lines = [ln for ln in lines if video_id in ln]
    return _fence(lines[-limit:])


def section_container(name: str, since_hours: float, limit: int) -> str:
    return _fence(_run(["docker", "logs", "--tail", str(limit), "--since", f"{since_hours}h", name],
                       timeout=20).splitlines())


# ── Assembly ─────────────────────────────────────────────────────────────────

def _safe(fn, *args) -> str:
    """One broken source must not lose the rest of the report."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - the reason goes into the report
        return f"Unavailable: {type(e).__name__}: {e}"


def build_raw_report(args) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        settings = _settings(DB_PATH) if DB_PATH.exists() else {}
    except sqlite3.Error:
        settings = {}
    parts = [
        "# Tubematic diagnostics report", "",
        f"Generated {now} by `scripts/collect_diagnostics.py`."
        + (f" Scoped to video `{args.video}`." if args.video else "")
        + f" Logs cover the last {args.since:g} hours.", "",
        "## Install", "", _safe(section_install, DB_PATH), "",
        "## Stack", "", _safe(section_stack), "",
        "## Agents", "", _safe(section_agents, DB_PATH) if DB_PATH.exists() else "No database.", "",
        "## Settings", "", _safe(section_settings, settings, args.include_content), "",
        "## Pipeline", "",
        _safe(section_pipeline, DB_PATH, args.video, args.include_content) if DB_PATH.exists()
        else "No database.", "",
        "## Warnings and errors (structured logs)", "", _safe(section_jsonl, args.video, args.since, args.lines), "",
        "## poll.log", "", _safe(section_poll_log, args.video, args.since, args.lines), "",
    ]
    for name in stack.SERVICES:
        parts += [f"## Container output: {name}", "", _safe(section_container, name, args.since, args.lines), ""]
    return "\n".join(parts)


def build_redactor(include_content: bool) -> Redactor:
    settings, accounts, content, domain_ids = {}, [], [], []
    if DB_PATH.exists():
        settings = _settings(DB_PATH)
        accounts = _account_ids(DB_PATH, settings)
        if not include_content:
            content, domain_ids = _content_literals(DB_PATH, settings)
    return Redactor(secrets=_secret_values(settings), account_ids=accounts,
                    voice_ids=_voice_ids(DB_PATH, settings), content=content, domain_ids=domain_ids,
                    home=str(Path.home()), user=_user_name(), host=socket.gethostname())


def _user_name() -> str:
    """$USER is often unset (cron, docker exec, some sudo setups); getpass
    falls back to the password database, so the rule never silently switches off."""
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - no name to redact is not a reason to fail
        return ""


def _shell_path(path: str) -> str:
    """Quoted for a shell, keeping a leading ~/ outside the quotes so it still expands."""
    if path.startswith("~/"):
        return "~/" + shlex.quote(path[2:])
    return shlex.quote(path)


def footer(redactor: Redactor, include_content: bool, out_dir: str) -> str:
    summary = ", ".join(f"{rule}: {n}" for rule, n in sorted(redactor.counts.items())) or "nothing matched"
    return "\n".join([
        "## Redaction summary", "",
        f"Replaced — {summary}. Content {'INCLUDED (--include-content)' if include_content else 'excluded'}.",
        "",
        "## Before you post", "",
        "This report was redacted by code, but code only removes what it can recognise. Read it once "
        "yourself and remove anything else you would not publish, in particular:", "",
        "- a key, token or password in a shape nothing here knows",
        "- a topic, script line or comment quoted in other words (only exact quotes are replaced)",
        "- names of people, channels or companies",
        "- anything inside a log line you do not recognise", "",
        "## Filing", "",
        f"Open a new issue at https://github.com/{GITHUB_REPO}/issues/new?template=bug_report.yml, or with "
        "the GitHub CLI, after writing the issue text to issue.md next to this report:", "",
        "~~~bash",
        f'gh issue create --repo {GITHUB_REPO} --title "<one-line summary>" --body-file {_shell_path(out_dir + "/issue.md")}',
        "~~~", ""])


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _positive(kind):
    def parse(text):
        value = kind(text)
        if not value > 0:
            raise argparse.ArgumentTypeError(f"must be greater than 0, got {text}")
        return value
    return parse


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Collect a redacted Tubematic diagnostics report.")
    p.add_argument("--video", default="", help="scope logs and details to one video id")
    p.add_argument("--since", type=_positive(float), default=24, help="hours of logs to include (default 24)")
    p.add_argument("--lines", type=_positive(int), default=200, help="lines per log section (default 200)")
    p.add_argument("--include-content", action="store_true",
                   help="include topics, scripts, comments, preferences and lexicon (omitted by default)")
    p.add_argument("--out", default="", help="directory to write into "
                   "(default ~/tubematic-diagnostics-<time>)")
    args = p.parse_args(argv)

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out).expanduser() if args.out else Path.home() / f"tubematic-diagnostics-{stamp}"
    if _inside(out_dir, DATA_ROOT):
        print(f"Refusing to write inside {DATA_ROOT}: an agent reading the report would need "
              "access to the directory that holds every API key. Pick another --out.", file=sys.stderr)
        return 1

    try:
        redactor = build_redactor(args.include_content)
    except (sqlite3.Error, OSError) as e:
        print(f"Cannot read what needs redacting ({e}); no report written.", file=sys.stderr)
        return 2
    report = out_dir / "report.md"
    if report.exists() or report.is_symlink():
        print(f"{report} already exists; pick another --out.", file=sys.stderr)
        return 1

    text = redactor.apply(build_raw_report(args))
    text += "\n" + footer(redactor, args.include_content, redactor.apply(str(out_dir)))
    # Checked on the whole text, then cut: a cut only removes characters, so it
    # cannot bring back anything the check passed.
    leaks = redactor.residual(text)
    if leaks:
        print("Redaction check failed — the report still contained " + "; ".join(leaks)
              + ". Nothing was written. Please report this (without the report).", file=sys.stderr)
        return 2
    text = _clip_log_lines(text)

    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    # O_EXCL: never follow a planted link or reuse an existing file's mode.
    try:
        fd = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print(f"{report} already exists; pick another --out.", file=sys.stderr)
        return 1
    with os.fdopen(fd, "w") as f:
        f.write(text)
    print(f"Wrote {report}")
    print("Read it before sharing it — see 'Before you post' at the end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
