"""collect_diagnostics.py: the report must be safe to post (TMDEV-167).

Every secret and personal value the collector can be handed is planted in every
source it reads — the structured logs, poll.log and container output — and the
finished report is searched for each one. The residual scan is shown to fail
closed by breaking the redactor on purpose.
"""
import datetime as dt
import hashlib
import json
import os
import sqlite3

import pytest

import collect_diagnostics as cd
from tubematic_core import auth as tauth
from tubematic_core import db as tdb

NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

SETTINGS_SECRETS = {
    "discord_webhook_url": "https://discord.com/api/webhooks/123456789012345678/hookTOKENabc123def456",
    "elevenlabs_api_key": "sk_storedeleven0123456789abcdef0123456789abcdef",
    "gemini_api_key": "AIzaStoredGeminiKey0123456789abcdefg",
    "openai_api_key": "sk-proj-storedOpenAIkey0123456789",
    "youtube_transcript_api_key": "ytt-bareTranscriptKey-91x7",
    "postforme_api_key": "pfm_bare_postforme_key_7731",
}
PASSWORD_HASH = "scrypt$32768$8$1$c2FsdHNhbHRzYWx0$ZGlnZXN0ZGlnZXN0ZGlnZXN0"
UNSTORED = {
    "eleven": "sk_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
    "openai": "sk-live-unstoredOpenAI1234567890",
    "google": "AIzaUnstoredGoogleKey0123456789abcd",
    "bearer": "eyJhbGciOiJIUzI1NiJ9unstoredbearer",
    "basic": "dXNlcjpodW50ZXIyLWJhc2ljLWF1dGg=",
    "cookie": "tmsessionvalue.signature.99",
}
EMAIL = "creator.person@example.org"
PUBLIC_IP4, PUBLIC_IP6 = "203.0.113.77", "2001:db8:85a3::8a2e:370:7334"
USER, HOST = "tmuser", "tmhost-workstation"
ACCOUNT, VOICE, HANDLE = "spc_privateaccount42", "VoIcEiD0123456789", "secret_channel_handle"
TITLE = "How my private side project works"
TOPIC = "A topic brief about the user's unannounced product launch"
DOMAIN = "Unannounced Product Domain"
DOMAIN_ID = "unannounced-product"   # the agent names a domain with a slug of its subject
PREFERENCE = "Always mention my employer Initech by name"
SCRIPT_SENTENCE = "Initech's new router ships with a hidden admin page."
HUMAN_COMMENT = "Please mention the Initech launch date in the intro"
REVIEW = "The narrator mispronounces Initech in segment three"
PUBLISH_DESCRIPTION = "Everything about the Initech router nobody tells you"
OLD_VOICE = "RemovedVoiceId98765"   # off the roster, still on a video
WORKER_ERROR = "Render failed: remotion exited with code 137"
LEXICON_TERM, LEXICON_RESPELL = "Zorblax", "Zorb-lacks"   # short: matched as whole words
DOMAIN_VOICE = "DomainDefaultVoice42"   # off the roster, still a domain's default
POLL_TS = "%Y-%m-%dT%H:%M:%S%z"


@pytest.fixture
def install(tmp_path, monkeypatch):
    home = tmp_path / "home" / USER
    data = home / ".tubematic-data"
    db = data / "data" / "tubematic.db"
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    tdb.migrate(db)
    con = sqlite3.connect(db)
    rows = dict(SETTINGS_SECRETS)
    rows.update({
        tauth.PASSWORD_KEY: PASSWORD_HASH,
        "elevenlabs_voice_id": VOICE,
        "elevenlabs_voices": json.dumps([{"voice_id": VOICE, "name": "Narrator",
                                          "model_id": "eleven_multilingual_v2"}]),
        "auto_pilot_config": json.dumps({"projects": {DOMAIN_ID: [ACCOUNT]}}),
        "user_preferences": PREFERENCE,
        "pronunciation_lexicon": json.dumps([{"term": LEXICON_TERM, "respell": LEXICON_RESPELL}]),
        "pipeline_paused": "false",
    })
    con.executemany("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", rows.items())
    con.execute("INSERT INTO projects(id, name, default_voice_id, created_at) VALUES (?, ?, ?, ?)",
                (DOMAIN_ID, DOMAIN, DOMAIN_VOICE, NOW))
    con.execute("INSERT INTO videos(id, project_id, topic, title, status, script, gemini_feedback, "
                "publish_description, voice_id, created_at, updated_at) "
                "VALUES ('vid_1', ?, ?, ?, 'FAILED', ?, ?, ?, ?, ?, ?)",
                (DOMAIN_ID, TOPIC, TITLE, f"Welcome back. {SCRIPT_SENTENCE} Let's open it.",
                 REVIEW, PUBLISH_DESCRIPTION, OLD_VOICE, NOW, NOW))
    con.execute("INSERT INTO comments(video_id, author, content, created_at) "
                "VALUES ('vid_1', 'agent', ?, ?)", (f"Render crashed for {TITLE}", NOW))
    con.execute("INSERT INTO comments(video_id, author, content, created_at) "
                "VALUES ('vid_1', 'agent', ?, ?)", (WORKER_ERROR, NOW))
    con.execute("INSERT INTO comments(video_id, author, content, created_at) "
                "VALUES ('vid_1', 'human', ?, ?)", (f"Looks good.\n{HUMAN_COMMENT}", NOW))
    con.execute("INSERT INTO video_publications(id, video_id, platform, social_account_id, "
                "created_at, updated_at) VALUES ('pub_1', 'vid_1', 'youtube', ?, ?, ?)",
                (ACCOUNT, NOW, NOW))
    con.commit()
    con.close()

    token = tauth.read_secret("api_token")
    planted = " | ".join([
        *SETTINGS_SECRETS.values(), PASSWORD_HASH, token,
        f"voice failed {UNSTORED['eleven']}", f"auth {UNSTORED['openai']}",
        f"GET https://x/y?key={UNSTORED['google']}",
        f"Authorization: Bearer {UNSTORED['bearer']}",
        f"Authorization: Basic {UNSTORED['basic']}",
        # Mid-line on purpose: a rule that ran to the end of the line once
        # erased everything after it, and the placeholder test catches that.
        f"Cookie: tm_session={UNSTORED['cookie']}; theme=dark",
        f"mailed {EMAIL} from {PUBLIC_IP4} and {PUBLIC_IP6}; local 127.0.0.1",
        f"path {home}/tubematic/scripts/poll.py on {HOST} as {USER}",
        f"title {TITLE}; topic {TOPIC}; domain {DOMAIN}; pref {PREFERENCE}",
        f"account {ACCOUNT} voice {VOICE} domain id {DOMAIN_ID}",
        json.dumps({"username": HANDLE}),
        f"agent said: {SCRIPT_SENTENCE}", f"human asked: {HUMAN_COMMENT}",
        f"review: {REVIEW}", f"description: {PUBLISH_DESCRIPTION}",
        f"voice {OLD_VOICE} is no longer in the roster", f"worker: {WORKER_ERROR}",
        f"say {LEXICON_TERM} as {LEXICON_RESPELL}", f"domain voice {DOMAIN_VOICE} missing",
    ])
    logs = data / "logs"
    logs.mkdir(parents=True)
    (logs / f"api.{NOW[:10]}.jsonl").write_text(json.dumps(
        {"ts": NOW, "service": "api", "level": "error", "message": planted, "video_id": "vid_1"}) + "\n")
    poll_dir = home / ".tubematic-agent" / "logs"
    poll_dir.mkdir(parents=True)
    stamp = dt.datetime.now().astimezone().strftime(POLL_TS)
    (poll_dir / "poll.log").write_text(f"{stamp} ERROR   [vid_1] {planted}\n")

    for name, value in {"DATA_ROOT": data, "DB_PATH": db, "LOG_DIR": logs,
                        "POLL_LOG": poll_dir / "poll.log",
                        "HEARTBEAT": tmp_path / "poll.heartbeat"}.items():
        monkeypatch.setattr(cd, name, value)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USER", USER)
    monkeypatch.setenv("LOGNAME", USER)   # getpass reads it before USER
    monkeypatch.setattr(cd.socket, "gethostname", lambda: HOST)
    monkeypatch.setattr(cd, "_http_status", lambda url: "200")
    monkeypatch.setattr(cd.stack, "_container_state", lambda name: ("running", "healthy"))
    monkeypatch.setattr(cd.stack, "read_crontab",
                        lambda: f"*/30 * * * * /usr/bin/python3 {home}/tubematic/scripts/poll.py\n")

    def fake_run(argv, timeout=10):
        if argv[:2] == ["docker", "logs"]:
            return f"container says: {planted}"
        return "1.0-test"
    monkeypatch.setattr(cd, "_run", fake_run)
    return {"home": home, "data": data, "db": db, "token": token, "out": tmp_path / "out"}


def _collect(install, *extra, out=None):
    out = out or install["out"]
    assert cd.main(["--out", str(out), *extra]) == 0
    return (out / "report.md").read_text()


def test_no_planted_secret_or_personal_value_survives(install):
    report = _collect(install)
    planted = [*SETTINGS_SECRETS.values(), PASSWORD_HASH, install["token"], *UNSTORED.values(),
               EMAIL, PUBLIC_IP4, PUBLIC_IP6, str(install["home"]), HOST, ACCOUNT, VOICE, HANDLE,
               TITLE, TOPIC, DOMAIN, DOMAIN_ID, PREFERENCE, SCRIPT_SENTENCE, HUMAN_COMMENT,
               REVIEW, PUBLISH_DESCRIPTION, OLD_VOICE, LEXICON_TERM, LEXICON_RESPELL, DOMAIN_VOICE]
    survivors = [v for v in planted if v in report]
    assert not survivors
    assert f" {USER} " not in report and f"as {USER}" not in report


def test_placeholders_replace_values_and_harmless_text_is_kept(install):
    report = _collect(install)
    for placeholder in ("***REDACTED***", "<email>", "<ip>", "<host>", "<user>",
                        "<title vid_1>", "<topic vid_1>", "<preferences>", "<script vid_1>",
                        "<comment vid_1>", "<review vid_1>", "<publish description vid_1>",
                        "say <lexicon> as <lexicon>",
                        f"<domain {cd._domain_label(DOMAIN_ID)}>", f"domain id {cd._domain_label(DOMAIN_ID)}",
                        "~/tubematic/scripts/poll.py"):
        assert placeholder in report, placeholder
    assert "127.0.0.1" in report, "loopback carries no personal information"
    # The worker files its errors as agent comments; they are the evidence.
    assert WORKER_ERROR in report
    assert "## Redaction summary" in report and "## Before you post" in report
    # Secret settings are reported as present, never shown.
    assert "| openai_api_key | `set` |" in report


def test_ids_become_stable_short_hashes(install):
    report = _collect(install)
    acct = "acct-" + hashlib.sha256(ACCOUNT.encode()).hexdigest()[:6]
    voice = "voice-" + hashlib.sha256(VOICE.encode()).hexdigest()[:6]
    # The same account in the logs, the container output and Auto Pilot config
    # gets the same label, so the lines still line up.
    assert report.count(acct) >= 3
    assert voice in report
    assert "handle-" + hashlib.sha256(HANDLE.encode()).hexdigest()[:6] in report


def test_content_is_left_out_unless_asked_for(install):
    default = _collect(install, "--video", "vid_1")
    assert "Topic:" not in default
    assert f"| user_preferences | `<{len(PREFERENCE)} chars, omitted>` |" in default
    assert "Render crashed" not in default, "comment text is content"

    included = _collect(install, "--video", "vid_1", "--include-content",
                        out=install["out"].with_name("included"))
    assert TOPIC in included and PREFERENCE in included
    # Content opt-in never lets a secret through.
    assert SETTINGS_SECRETS["openai_api_key"] not in included


def test_short_content_is_replaced_as_whole_words_only(install):
    """Short content is matched as a whole word: substring matching would cut
    into ordinary words, and no matching at all let a short comment through."""
    con = sqlite3.connect(install["db"])
    con.executemany("INSERT INTO comments(video_id, author, content, created_at) "
                    "VALUES ('vid_1', 'human', ?, ?)",
                    [("Project X", NOW), ("comment", NOW), ("API", NOW)])
    con.commit()
    con.close()
    with open(cd.POLL_LOG, "a") as f:
        f.write(f"{dt.datetime.now().astimezone().strftime(POLL_TS)} INFO    "
                "asked for Project X, not Project Xylophone or SubProject X\n")
    report = _collect(install)
    assert "Project X," not in report
    assert "asked for <comment vid_1>, not Project Xylophone or SubProject X" in report
    # A whole-word literal never matches inside a placeholder already written.
    assert "<<" not in report and f"human asked: <comment vid_1>" in report
    # Under four characters says nothing private and is left alone.
    assert "- API `/health`: 200" in report


def test_the_residual_scan_fails_closed(install, monkeypatch, capsys):
    """Break the redactor: nothing may be written, and the value is not echoed."""
    monkeypatch.setattr(cd.tlog, "redact", lambda text, secrets=(): text)
    assert cd.main(["--out", str(install["out"])]) == 2
    assert not install["out"].exists()
    err = capsys.readouterr().err
    assert "Nothing was written" in err
    assert SETTINGS_SECRETS["openai_api_key"] not in err


def test_it_refuses_to_write_inside_the_data_directory(install):
    assert cd.main(["--out", str(install["data"] / "diag")]) == 1
    assert not (install["data"] / "diag").exists()


def test_the_report_is_private_to_its_owner(install):
    _collect(install)
    assert (install["out"].stat().st_mode & 0o777) == 0o700
    assert ((install["out"] / "report.md").stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads a mode-000 file anyway")
def test_an_unreadable_token_stops_the_report(install):
    """A token we cannot read is a value we cannot match."""
    path = tauth.secrets_dir() / "mcp_token"
    path.chmod(0)
    try:
        assert cd.main(["--out", str(install["out"])]) == 2
    finally:
        path.chmod(0o644)
    assert not install["out"].exists()


def test_the_database_is_never_written(install):
    before = install["db"].read_bytes()
    _collect(install, "--video", "vid_1")
    assert install["db"].read_bytes() == before


def test_the_user_name_is_found_without_the_user_variable(install, monkeypatch):
    """cron and `docker exec` often leave $USER unset."""
    monkeypatch.delenv("USER")
    monkeypatch.delenv("LOGNAME", raising=False)
    monkeypatch.setattr(cd.getpass, "getuser", lambda: USER)
    report = _collect(install)
    assert f"as {USER}" not in report and "as <user>" in report


def test_timestamps_and_version_numbers_are_not_mistaken_for_addresses():
    r = cd.Redactor(secrets=[])
    text = "2026-10-17T12:30:45Z ran 2.0.0 with dead:beef in a message"
    assert r.apply(text) == text


def test_the_database_connection_is_read_only(install):
    con = cd._connect_ro(install["db"])
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            con.execute("INSERT INTO settings(key, value) VALUES ('x', 'y')")
    finally:
        con.close()


def test_the_residual_scan_catches_a_stored_value_with_no_recognisable_shape():
    """Shape rules cannot see a bare postforme or transcript key; only the
    literal check can, so it must stand on its own."""
    r = cd.Redactor(secrets=["pfm_bare_postforme_key_7731"])
    assert r.residual("upstream said pfm_bare_postforme_key_7731") == ["a stored secret or service token"]
    assert r.residual("upstream said ***REDACTED***") == []


def test_a_secret_cut_by_the_line_limit_is_still_redacted(install):
    """The cut once came first, leaving a prefix the stored value no longer matched."""
    secret = SETTINGS_SECRETS["youtube_transcript_api_key"]
    line = "x" * (cd.LINE_MAX - 6) + secret + " tail"
    (cd.LOG_DIR / f"mcp.{NOW[:10]}.jsonl").write_text(json.dumps(
        {"ts": NOW, "service": "mcp", "level": "error", "message": line}) + "\n")
    report = _collect(install)
    assert secret[:6] not in report.replace("***REDACTED***", "")
    assert "…(cut)" in report


def test_an_existing_report_is_never_overwritten_or_followed(install, tmp_path):
    install["out"].mkdir()
    target = tmp_path / "someone-elses-file"
    target.write_text("keep me")
    (install["out"] / "report.md").symlink_to(target)
    assert cd.main(["--out", str(install["out"])]) == 1
    assert target.read_text() == "keep me"

    other = tmp_path / "other"
    other.mkdir()
    (other / "report.md").write_text("old")
    (other / "report.md").chmod(0o644)
    assert cd.main(["--out", str(other)]) == 1
    assert (other / "report.md").read_text() == "old"


def test_since_bounds_the_poll_log_and_reaches_its_rotations(install):
    now = dt.datetime.now().astimezone()
    old, recent = now - dt.timedelta(hours=30), now - dt.timedelta(hours=2)
    rotated = cd.POLL_LOG.with_name("poll.log." + old.date().isoformat())
    rotated.write_text(f"{old.strftime(POLL_TS)} INFO    [x] a line from yesterday\n")
    cd.POLL_LOG.write_text(f"{recent.strftime(POLL_TS)} INFO    [x] two hours ago\n"
                           "  continued on a second line\n"
                           f"{now.strftime(POLL_TS)} INFO    [x] just now\n")

    narrow = _collect(install, "--since", "1", out=install["out"].with_name("narrow"))
    assert "just now" in narrow
    assert "two hours ago" not in narrow and "continued on a second line" not in narrow

    wide = _collect(install, "--since", "48", out=install["out"].with_name("wide"))
    for text in ("a line from yesterday", "two hours ago", "continued on a second line", "just now"):
        assert text in wide, text


@pytest.mark.parametrize("flag,value", [("--lines", "0"), ("--lines", "-5"),
                                        ("--since", "0"), ("--since", "-1")])
def test_non_positive_windows_are_refused(install, flag, value):
    """--lines 0 once meant lines[-0:], the whole of poll.log."""
    with pytest.raises(SystemExit) as e:
        cd.main(["--out", str(install["out"]), flag, value])
    assert e.value.code == 2
    assert not install["out"].exists()


def test_the_filing_command_quotes_the_report_path(install):
    out = install["home"] / "diag reports; rm -rf x"
    report = _collect(install, out=out)
    assert "--body-file ~/'diag reports; rm -rf x/issue.md'" in report


def test_a_link_planted_while_the_report_is_built_is_not_followed(install, tmp_path, monkeypatch):
    """The up-front check is only a courtesy; opening with O_EXCL is the guarantee."""
    target = tmp_path / "someone-elses-file"
    target.write_text("keep me")
    build = cd.build_raw_report

    def build_then_plant(args):
        install["out"].mkdir()
        (install["out"] / "report.md").symlink_to(target)
        return build(args)
    monkeypatch.setattr(cd, "build_raw_report", build_then_plant)
    assert cd.main(["--out", str(install["out"])]) == 1
    assert target.read_text() == "keep me"
