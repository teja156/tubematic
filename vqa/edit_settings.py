#!/usr/bin/env python3
"""Read and change pipeline settings from inside the VQA environment.

The VQA environment deliberately runs no dashboard container and no
onboard.py wizard (see vqa/README.md), so this is the only way to change a
setting here short of hand-writing SQL against mounted/data/tubematic.db or
rebuilding the image with an edited vqa/make_seed_db.py.

Writes go over HTTP to the pipeline API's POST /settings rather than
straight to SQLite. That endpoint is the canonical write path: some checks
live *only* there (renderer/api/pipeline.py::post_settings — the live
webhook check, and keeping a re-sent masked secret from overwriting the real
one), so a direct-SQL script reusing _coerce_setting would skip them. Going
over HTTP duplicates no validation logic at all.

Values are passed through as raw strings — _coerce_setting already accepts
"true"/"1800" and JSON text for the list-valued keys (elevenlabs_voices,
pronunciation_lexicon, trending_sources), so this script carries no type
table of its own to drift out of sync with SETTINGS_SPEC.

No setting needs a restart to take effect. Every reader queries the DB live
at use time — renderer/api/worker.py::_setting, mcp/server.py::_get_setting
and renderer/api/pipeline.py::_read_all_settings are all called per-use, with
no module-level reads and no in-process cache — so a write here applies to
the very next read. --restart exists only for the unrelated case of a wedged
container, and is never implicit.

Usage:
  edit_settings.py                                  # print every effective setting
  edit_settings.py --list image_model               # print selected settings
  edit_settings.py --set render_timeout_secs=2700
  edit_settings.py --set elevenlabs_voices='[{"name":"Rachel","voice_id":"21m00Tcm4TlvDq8ikWAM","model_id":"eleven_v3"}]'
  edit_settings.py --restart renderer               # bounce a wedged render worker
"""
import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_API_URL = "http://localhost:4000"

# CLI name -> compose service. tubematic-dashboard is deliberately absent:
# the VQA environment never starts it (vqa/kasm_post_run_user.sh brings up
# tubematic-api, tubematic-mcp and tubematic-renderer).
RESTARTABLE_SERVICES = {
    "renderer": "tubematic-renderer",
    "api": "tubematic-api",
    "mcp": "tubematic-mcp",
}


_HELP_INTRO = """\
Read and change pipeline settings from inside the VQA environment, which has
no dashboard and no onboard.py wizard.

  edit_settings.py                                  print every effective setting
  edit_settings.py --list image_model               print selected settings
  edit_settings.py --set render_timeout_secs=2700   change one
  edit_settings.py --set image_model=gpt-image-2.5-sunburst
  edit_settings.py --restart renderer               bounce a wedged render worker

A change takes effect immediately — every reader queries the database live, so
--restart is never needed to apply one. Setting a list-valued key REPLACES the
whole list, so read the current value first and pass the full new one.
"""


def _repo_root() -> Path:
    """This script's own location determines the working tree whose
    docker-compose.yml --restart operates on — resolving from __file__ rather
    than cwd means it works the same whether invoked directly or via the
    /vqa-settings slash command's absolute path."""
    return Path(__file__).resolve().parent.parent


# Settings that exist in SETTINGS_SPEC but do nothing here: the VQA
# environment runs no cron and no topic research, so nothing ever reads them
# (vqa/README.md). Flagged in --help rather than hidden — they are still real
# settings, and hiding them would make --help disagree with --list.
_INERT_HERE = {
    "max_curriculum_per_run",
    "max_mining_per_run",
    "max_research_runs_per_day",
    "max_trending_per_run",
    "research_pending_cap",
    "trending_sources",
}


def _describe_setting(key: str, typ: str, default: str, pipeline) -> list:
    """One or more help lines for a single setting.

    Every concrete value — model catalogs, roster cap, the
    render-timeout floor — is read off renderer/api/pipeline.py rather than
    written out here, so --help cannot drift from what POST /settings will
    actually accept. Only the prose is local.
    """
    if typ == "secret":
        # Write-only from here: GET /settings masks every credential, so --list
        # can show that one is set but never what it is (TMDEV-73).
        return ["API key — write-only; --list shows a mask, never the value"]
    if key in ("image_model", "character_model"):
        return [f"one of: {' | '.join(pipeline.OPENAI_IMAGE_MODELS)}"]
    if key == "elevenlabs_voices":
        phoneme = sorted(pipeline.PHONEME_COMPATIBLE_MODELS)
        return [
            'JSON: [{"name": "Rachel", "voice_id": "21m00Tcm4TlvDq8ikWAM",',
            '        "model_id": "eleven_multilingual_v2"}]',
            f"the voice roster; at most {pipeline.MAX_VOICES} entries, each with its own model",
            f"model_id one of: {', '.join(sorted(pipeline.DICTIONARY_COMPATIBLE_MODELS))}",
            f"also enables <phoneme> tags: {', '.join(phoneme)}",
            f"also enables <ipa> tags: {', '.join(sorted(pipeline.IPA_COMPATIBLE_MODELS))}",
        ]
    if key == "elevenlabs_voice_id":
        return ["the default voice — must be a voice_id already in elevenlabs_voices"]
    if key == "pronunciation_lexicon":
        # A sound is one plain word — ElevenLabs does not speak a hyphenated
        # respelling correctly. An acronym spelled out letter by letter keeps
        # its hyphens, so this must not say "no hyphens" flatly. See
        # docs/developer/08-scripting-and-voice.md.
        return ['JSON: [{"term": "Vhagar", "respell": "Vaygar"}]',
                'respell: a sound is one plain word ("Vaygar", never "Vah-gar");',
                '         an acronym spelled out keeps hyphens ("S-Y-N"); never whitespace']
    if key == "render_timeout_secs":
        return ["seconds; minimum 60"]
    if typ == "bool":
        return ["true | false"]
    if typ == "int":
        return ["a non-negative integer"]
    if typ == "json_list":
        return ['JSON list of strings: ["GitHub Trending", "Hacker News"]']
    return ["free text"]


def _settings_catalog() -> str:
    """The --help epilog: what can actually be changed, and to what."""
    try:
        sys.path.insert(0, str(_repo_root() / "renderer" / "api"))
        import pipeline  # noqa: E402
    except Exception as exc:
        return (
            f"Settings catalog unavailable — could not import "
            f"renderer/api/pipeline.py ({exc}).\n"
            f"Run with no arguments to list the live settings instead."
        )

    lines = [
        "settings (--set KEY=VALUE, repeatable):",
        "",
        "  Defaults below are the pipeline's shipped defaults, which this environment",
        "  seeds over in places (vqa/make_seed_db.py). Run with no arguments for the",
        "  values actually in effect.",
        "",
    ]
    for key in sorted(pipeline.SETTINGS_SPEC):
        typ, default = pipeline.SETTINGS_SPEC[key]
        described = _describe_setting(key, typ, default, pipeline)
        if key in _INERT_HERE:
            described.append("unused in this environment — no cron, no topic research")
        lines.append(f"  {key}   [default: {default or 'unset'}]")
        lines.extend(f"      {line}" for line in described)
        lines.append("")
    lines.append(
        "There is no install-wide ElevenLabs model: each voice in elevenlabs_voices\n"
        "carries its own, and a video's pronunciation mode follows its voice's model."
    )
    return "\n".join(lines)


def _api_token() -> str:
    """The API's bearer token (TMDEV-152), from ~/.tubematic-data/secrets.
    tubematic_core is stdlib-only, so this keeps the util venv-independent."""
    sys.path.insert(0, str(_repo_root()))
    from tubematic_core.auth import SecretMissing, read_secret
    try:
        return read_secret("api_token")
    except SecretMissing as exc:
        raise SystemExit(f"The pipeline API needs its token: {exc}.\n"
                         f"Create it: PYTHONPATH={_repo_root()} python3 -m tubematic_core.auth ensure")


def _http_json(method: str, url: str, body=None, timeout: int = 30) -> tuple[int, dict]:
    """Minimal stdlib JSON call. Returns (status, parsed_body).

    urllib rather than httpx deliberately: this needs one localhost JSON
    round-trip, and a stdlib-only util can't be broken by a venv that didn't
    install renderer/api/requirements.txt. A non-2xx is returned like any
    other response (the caller surfaces the endpoint's own error text); only
    an unreachable API raises.
    """
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_api_token()}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"error": raw.strip()}
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Could not reach the pipeline API at {url} ({exc.reason}).\n"
            f"Is the stack up?  cd {_repo_root()} && docker compose ps"
        )


def _error_text(body: dict) -> str:
    return body.get("error") if isinstance(body, dict) and "error" in body else json.dumps(body)


def fetch_settings(api_url: str = DEFAULT_API_URL, http=_http_json) -> dict:
    """Every effective setting, as GET /settings reports it. `http` is
    injectable for testing."""
    status, body = http("GET", f"{api_url}/settings")
    if status != 200:
        raise SystemExit(f"GET /settings failed ({status}): {_error_text(body)}")
    return body


def apply_settings(updates: dict, api_url: str = DEFAULT_API_URL, http=_http_json) -> tuple[dict, list]:
    """POST updates. Returns (effective_settings, warnings).

    Reads the effective settings first so the warning pass can see collateral
    changes, not just the requested ones — see _effective_warnings.
    post_settings responds with _read_all_settings(con) — the *effective*
    values, after read-time normalization — so the response is what actually
    took, not an echo of the request.
    """
    before = fetch_settings(api_url, http=http)
    status, body = http("POST", f"{api_url}/settings", updates)
    if status != 200:
        raise SystemExit(f"POST /settings rejected ({status}): {_error_text(body)}")
    return body, _effective_warnings(updates, body, before)


def _read_time_detail(key: str, got) -> str:
    """The one read-time normalization worth explaining in place."""
    if key == "elevenlabs_voice_id" and got == "":
        return (
            ' — the default voice must be a voice_id present in elevenlabs_voices. '
            'It is blanked on read otherwise, and generate_voice will fail with '
            '"No default voice set".'
        )
    return ""


def _effective_warnings(requested: dict, effective: dict, before: dict = None) -> list:
    """Values the pipeline does not actually end up using.

    A 200 from POST /settings does not mean every value took. The
    default-voice invariant in particular is enforced on *read*, not by
    rejecting the write (TMDEV-51): an elevenlabs_voice_id that names no
    entry in elevenlabs_voices is stored happily and then blanked by
    _read_all_settings, so the write looks successful and the next
    generate_voice dies with "No default voice set".

    Two passes, because that invariant can be broken from either side:
      - requested keys whose effective value isn't what was asked for
        (--set elevenlabs_voice_id=<not in roster>)
      - *unrequested* keys whose effective value moved anyway — replacing
        elevenlabs_voices orphans a default voice that was never mentioned in
        the request, which the first pass structurally cannot see. Swapping a
        voice is the most likely roster edit there is, so this is not the
        exotic case.

    Comparison reuses pipeline._coerce_setting — the same function
    _read_all_settings coerces through — so "true"/True and "1800"/1800
    compare equal without this script owning a second type table. The import
    is lazy and failure-tolerant (--list and --restart must keep working in a
    venv where renderer/api's dependencies aren't importable) but says so on
    stderr: a silent empty list would make "no warnings" indistinguishable
    from "warnings unavailable".
    """
    try:
        sys.path.insert(0, str(_repo_root() / "renderer" / "api"))
        from pipeline import _coerce_setting  # noqa: E402
    except Exception as exc:
        print(
            f"NOTE  Could not import renderer/api/pipeline.py ({exc}) — the "
            f"requested-vs-effective check was skipped, not passed.",
            file=sys.stderr,
        )
        return []

    warnings = []
    for key, raw in requested.items():
        try:
            want, _ = _coerce_setting(key, raw)
        except (ValueError, KeyError):
            # The server accepted this write, so a coercion failure here means
            # only that this script's view of the spec is stale. Nothing to say.
            continue
        got = effective.get(key)
        if got == want:
            continue
        warnings.append(
            f"{key}: requested {json.dumps(want)}, but the effective value is "
            f"{json.dumps(got)}{_read_time_detail(key, got)}"
        )

    for key, was in (before or {}).items():
        if key in requested:
            continue
        got = effective.get(key)
        if got == was:
            continue
        warnings.append(
            f"{key}: not requested, but changed from {json.dumps(was)} to "
            f"{json.dumps(got)} as a side effect{_read_time_detail(key, got)}"
        )
    return warnings


def parse_assignments(raw_pairs) -> dict:
    """Turn ["key=value", ...] into {key: value}. Splits on the first "=" only,
    so a JSON value containing "=" survives intact."""
    updates = {}
    for pair in raw_pairs:
        if "=" not in pair:
            raise SystemExit(f"--set expects KEY=VALUE, got {pair!r}")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--set expects KEY=VALUE, got {pair!r}")
        if key in updates:
            raise SystemExit(f"--set {key} given more than once")
        updates[key] = value
    return updates


def restart_service(service: str, root: Path, run=subprocess.run) -> None:
    """docker compose restart, from the working tree this script lives in.
    `run` is injectable for testing."""
    container = RESTARTABLE_SERVICES[service]
    print(f"Restarting {container}...", file=sys.stderr)
    result = run(["docker", "compose", "restart", container], cwd=str(root))
    if result.returncode != 0:
        raise SystemExit(f"docker compose restart {container} failed (exit {result.returncode})")
    print(f"Restarted {container}.", file=sys.stderr)


def _print_settings(settings: dict, keys=None) -> None:
    if keys:
        unknown = [k for k in keys if k not in settings]
        if unknown:
            raise SystemExit(
                f"Unknown setting(s): {unknown}. Valid: {sorted(settings)}"
            )
        shown = keys
    else:
        shown = sorted(settings)
    width = max(len(k) for k in shown)
    for key in shown:
        print(f"{key.ljust(width)}  {json.dumps(settings[key])}")
    if not keys:
        print(
            "\nEach voice in elevenlabs_voices carries its own ElevenLabs model — "
            "there is no install-wide one.",
            file=sys.stderr,
        )


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    # The catalog needs renderer/api/pipeline.py, an import worth a good
    # fraction of this script's runtime. Only --help ever shows it.
    wants_help = "-h" in argv or "--help" in argv
    parser = argparse.ArgumentParser(
        description=_HELP_INTRO,
        epilog=_settings_catalog() if wants_help else None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", nargs="*", metavar="KEY", default=None,
        help="print effective settings (all of them, or just the named keys)",
    )
    parser.add_argument(
        "--set", action="append", dest="assignments", default=[], metavar="KEY=VALUE",
        help="set a setting; repeatable. List-valued keys take JSON text.",
    )
    parser.add_argument(
        "--restart", choices=sorted(RESTARTABLE_SERVICES),
        help="bounce a container. Never needed to apply a setting — for a wedged worker only.",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="confirm --restart mcp, which drops a live Claude Code session's tools",
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    updates = parse_assignments(args.assignments)

    if updates:
        effective, warnings = apply_settings(updates, args.api_url)
        width = max(len(k) for k in updates)
        for key in updates:
            print(f"{key.ljust(width)}  {json.dumps(effective.get(key))}")
        for warning in warnings:
            print(f"WARNING  {warning}", file=sys.stderr)
        print(
            f"\nApplied to {args.api_url}. No restart needed — every reader queries "
            f"the database live.",
            file=sys.stderr,
        )

    if args.restart:
        # The guard follows the MCP server, not the API container. It used to
        # sit on --restart api because the two shared a container; since the
        # split, restarting the API leaves a Claude Code session untouched and
        # restarting tubematic-mcp is what severs it.
        if args.restart == "mcp" and not args.yes:
            raise SystemExit(
                "Restarting tubematic-mcp restarts the MCP server on port 4100 — "
                "if you are running this from a Claude Code session, that drops its "
                "connection and every Tubematic tool disappears until it reconnects.\n"
                "A settings change never needs this. Re-run with --yes if you meant it."
            )
        restart_service(args.restart, _repo_root())

    if args.list is not None or (not updates and not args.restart):
        _print_settings(fetch_settings(args.api_url), args.list or None)


if __name__ == "__main__":
    main()
