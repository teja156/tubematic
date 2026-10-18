"""Tests for vqa/edit_settings.py — the VQA settings read/write utility."""
import json
import shutil
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "vqa"))

from edit_settings import (  # noqa: E402
    RESTARTABLE_SERVICES,
    _effective_warnings,
    _http_json,
    _settings_catalog,
    apply_settings,
    fetch_settings,
    main,
    parse_assignments,
    restart_service,
)

_ROSTER = [{"name": "Rachel", "voice_id": "21m00Tcm4TlvDq8ikWAM",
            "model_id": "eleven_multilingual_v2"}]

# A response shaped like GET /settings — every SETTINGS_SPEC key coerced to its
# python type.
_SETTINGS = {
    "pipeline_paused": False,
    "gemini_review_enabled": False,
    "max_render_retries": 1,
    "max_curriculum_per_run": 2,
    "max_trending_per_run": 2,
    "max_mining_per_run": 2,
    "research_pending_cap": 15,
    "max_research_runs_per_day": 8,
    "trending_sources": ["GitHub Trending", "Hacker News"],
    "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",
    "elevenlabs_voices": _ROSTER,
    "pronunciation_lexicon": [],
    "image_model": "gpt-image-2.5-flare",
    "render_timeout_secs": 2700,
}


def _fake_http(status=200, body=None, calls=None, get_status=200, get_body=None):
    """A stand-in for _http_json.

    GET and POST are answered separately because apply_settings reads the
    effective settings before writing: `status`/`body` shape the POST reply
    (including error cases), and `get_status`/`get_body` the GET.
    """
    def _call(method, url, payload=None, timeout=30):
        if calls is not None:
            calls.append((method, url, payload))
        if method == "GET":
            return get_status, dict(_SETTINGS) if get_body is None else get_body
        return status, dict(_SETTINGS) if body is None else body
    return _call


class TestParseAssignments:
    def test_splits_key_and_value(self):
        assert parse_assignments(["image_model=gpt-image-2.5-flare"]) == {"image_model": "gpt-image-2.5-flare"}

    def test_splits_on_the_first_equals_only(self):
        """JSON values legitimately contain "=" (base64 padding, query strings
        inside a URL list) — splitting greedily would corrupt them."""
        raw = '{"a":"b=c"}'
        assert parse_assignments([f"trending_sources={raw}"]) == {"trending_sources": raw}

    def test_empty_value_is_allowed(self):
        """Blanking the default voice is a legitimate write."""
        assert parse_assignments(["elevenlabs_voice_id="]) == {"elevenlabs_voice_id": ""}

    def test_missing_equals_is_an_error(self):
        with pytest.raises(SystemExit, match="KEY=VALUE"):
            parse_assignments(["image_model"])

    def test_empty_key_is_an_error(self):
        with pytest.raises(SystemExit, match="KEY=VALUE"):
            parse_assignments(["=value"])

    def test_duplicate_key_is_an_error(self):
        with pytest.raises(SystemExit, match="more than once"):
            parse_assignments(["max_render_retries=1", "max_render_retries=2"])


class TestFetchSettings:
    def test_returns_the_response_body(self):
        assert fetch_settings("http://api", http=_fake_http()) == _SETTINGS

    def test_hits_the_settings_endpoint(self):
        calls = []
        fetch_settings("http://api", http=_fake_http(calls=calls))
        assert calls == [("GET", "http://api/settings", None)]

    def test_non_200_raises_with_the_server_error(self):
        http = _fake_http(get_status=500, get_body={"error": "database is locked"})
        with pytest.raises(SystemExit, match="database is locked"):
            fetch_settings("http://api", http=http)


class TestApplySettings:
    def test_posts_the_updates_verbatim_after_reading_the_current_values(self):
        calls = []
        apply_settings({"render_timeout_secs": "2700"}, "http://api", http=_fake_http(calls=calls))
        assert calls == [
            ("GET", "http://api/settings", None),
            ("POST", "http://api/settings", {"render_timeout_secs": "2700"}),
        ]

    def test_returns_the_effective_settings(self):
        effective, _ = apply_settings({"max_render_retries": "2"}, "http://api", http=_fake_http())
        assert effective == _SETTINGS

    def test_rejection_surfaces_the_endpoints_own_error(self):
        """A violation is caught server-side; this script must not swallow or
        reword the reason."""
        http = _fake_http(
            status=400,
            body={"error": "image_model must be one of ['gpt-image-2.5-flare', "
                           "'gpt-image-2.5-sunburst'], got 'gemini-2.5-flash-image'"},
        )
        with pytest.raises(SystemExit, match="image_model must be one of"):
            apply_settings({"image_model": "gemini-2.5-flash-image"}, "http://api", http=http)

    def test_non_json_error_body_still_surfaces(self):
        http = _fake_http(status=502, body={"error": "<html>Bad Gateway</html>"})
        with pytest.raises(SystemExit, match="Bad Gateway"):
            apply_settings({"image_model": "gpt-image-2.5-flare"}, "http://api", http=http)


class TestEffectiveWarnings:
    """The requested-vs-effective diff. Comparison goes through
    pipeline._coerce_setting, so string input and typed output compare equal
    without this script owning a second type table."""

    def test_string_bool_matching_typed_response_is_not_a_warning(self):
        assert _effective_warnings({"pipeline_paused": "false"}, _SETTINGS) == []

    def test_string_int_matching_typed_response_is_not_a_warning(self):
        assert _effective_warnings({"render_timeout_secs": "2700"}, _SETTINGS) == []

    def test_json_list_matching_parsed_response_is_not_a_warning(self):
        assert _effective_warnings({"elevenlabs_voices": json.dumps(_ROSTER)}, _SETTINGS) == []

    def test_plain_string_match_is_not_a_warning(self):
        assert _effective_warnings({"image_model": "gemini-2.5-flash-image"}, _SETTINGS) == []

    def test_off_roster_default_voice_warns(self):
        """The load-bearing case: POST /settings returns 200 and stores the
        value, but _read_all_settings blanks a default voice that names no
        roster entry (TMDEV-51), so the write silently does not take."""
        effective = dict(_SETTINGS, elevenlabs_voice_id="")
        warnings = _effective_warnings({"elevenlabs_voice_id": "not_in_roster"}, effective)
        assert len(warnings) == 1
        assert "elevenlabs_voice_id" in warnings[0]
        assert "not_in_roster" in warnings[0]
        assert "No default voice set" in warnings[0]

    def test_mismatch_on_any_other_key_still_warns_without_the_voice_hint(self):
        effective = dict(_SETTINGS, max_render_retries=2)
        warnings = _effective_warnings({"max_render_retries": "9"}, effective)
        assert len(warnings) == 1
        assert "requested 9" in warnings[0]
        assert "No default voice set" not in warnings[0]

    def test_uncoercible_request_is_skipped_not_reported(self):
        """The server already accepted the write, so a local coercion failure
        means this script's view of the spec is stale, not that anything is
        wrong with the value."""
        assert _effective_warnings({"not_a_real_key": "x"}, _SETTINGS) == []

    def test_several_keys_each_get_their_own_warning(self):
        effective = dict(_SETTINGS, elevenlabs_voice_id="", max_render_retries=2)
        warnings = _effective_warnings(
            {"elevenlabs_voice_id": "nope", "max_render_retries": "9"}, effective
        )
        assert len(warnings) == 2

    def test_replacing_the_roster_warns_about_the_orphaned_default_voice(self):
        """The same footgun through the other door, and the likelier one:
        swapping the roster orphans a default voice that was never named in
        the request, so the requested-keys pass structurally cannot see it."""
        new_roster = [{"name": "Antoni", "voice_id": "ErXwobaYiN019PkySvjV", "model_id": "eleven_v3"}]
        effective = dict(_SETTINGS, elevenlabs_voices=new_roster, elevenlabs_voice_id="")
        warnings = _effective_warnings(
            {"elevenlabs_voices": json.dumps(new_roster)}, effective, _SETTINGS
        )
        assert len(warnings) == 1
        assert "elevenlabs_voice_id" in warnings[0]
        assert "not requested" in warnings[0]
        assert "No default voice set" in warnings[0]

    def test_roster_swap_that_keeps_the_default_voice_is_silent(self):
        """The negative control — a roster edit that preserves the default
        must not warn, or the warning becomes noise on every roster edit."""
        grown = _ROSTER + [{"name": "Antoni", "voice_id": "ErXwobaYiN019PkySvjV", "model_id": "eleven_v3"}]
        effective = dict(_SETTINGS, elevenlabs_voices=grown)
        assert _effective_warnings(
            {"elevenlabs_voices": json.dumps(grown)}, effective, _SETTINGS
        ) == []

    def test_changing_a_voices_model_is_not_a_warning(self):
        """The model lives on the voice now; a roster edit that changes it
        keeps the default voice, so there is nothing to warn about."""
        remodelled = [dict(_ROSTER[0], model_id="eleven_v3")]
        effective = dict(_SETTINGS, elevenlabs_voices=remodelled)
        assert _effective_warnings(
            {"elevenlabs_voices": json.dumps(remodelled)}, effective, _SETTINGS
        ) == []

    def test_no_before_snapshot_skips_the_collateral_pass(self):
        effective = dict(_SETTINGS, elevenlabs_voice_id="")
        assert _effective_warnings({"max_render_retries": "1"}, effective) == []

    def test_unimportable_pipeline_says_so_instead_of_reporting_all_clear(self, monkeypatch, capsys):
        """A silent [] would make "no warnings" indistinguishable from
        "the check never ran"."""
        monkeypatch.setitem(sys.modules, "pipeline", None)  # makes `from pipeline import` raise
        effective = dict(_SETTINGS, elevenlabs_voice_id="")

        assert _effective_warnings({"elevenlabs_voice_id": "nope"}, effective, _SETTINGS) == []
        assert "was skipped, not passed" in capsys.readouterr().err


class TestHttpJson:
    @pytest.fixture(autouse=True)
    def _token(self, tmp_path, monkeypatch):
        (tmp_path / "api_token").write_text("vqa-token")
        monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path))

    def test_every_call_carries_the_api_token(self, monkeypatch):
        seen = []

        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"{}"

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=None: seen.append(req) or _Resp())
        _http_json("GET", "http://localhost:4000/settings")
        assert seen[0].get_header("Authorization") == "Bearer vqa-token"

    def test_a_missing_token_says_how_to_create_it(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "none"))
        with pytest.raises(SystemExit) as exc:
            _http_json("GET", "http://localhost:4000/settings")
        assert "tubematic_core.auth ensure" in str(exc.value)

    def test_unreachable_api_raises_an_actionable_error(self, monkeypatch):
        def _boom(*a, **kw):
            raise urllib.error.URLError("Connection refused")
        monkeypatch.setattr("urllib.request.urlopen", _boom)

        with pytest.raises(SystemExit) as exc:
            _http_json("GET", "http://localhost:4000/settings")
        assert "Could not reach the pipeline API" in str(exc.value)
        assert "docker compose ps" in str(exc.value)

    def test_http_error_body_is_returned_not_raised(self, monkeypatch):
        """A 400 from post_settings carries the reason the write was rejected;
        raising on it would throw that away."""
        class _FakeHTTPError(urllib.error.HTTPError):
            def __init__(self):
                self.code = 400
                self._payload = json.dumps({"error": "Unknown settings: ['nope']"}).encode()

            def read(self):
                return self._payload

        def _raise(*a, **kw):
            raise _FakeHTTPError()
        monkeypatch.setattr("urllib.request.urlopen", _raise)

        status, body = _http_json("GET", "http://localhost:4000/settings")
        assert status == 400
        assert body == {"error": "Unknown settings: ['nope']"}


class _FakeCompleted:
    def __init__(self, returncode=0):
        self.returncode = returncode


class TestRestartService:
    def test_runs_compose_restart_from_the_working_tree(self, tmp_path):
        calls = []

        def _run(cmd, cwd=None):
            calls.append((cmd, cwd))
            return _FakeCompleted()

        restart_service("renderer", tmp_path, run=_run)
        assert calls == [(["docker", "compose", "restart", "tubematic-renderer"], str(tmp_path))]

    def test_nonzero_exit_raises(self, tmp_path):
        with pytest.raises(SystemExit, match="failed"):
            restart_service("renderer", tmp_path, run=lambda cmd, cwd=None: _FakeCompleted(1))

    def test_dashboard_is_not_restartable(self):
        """The VQA environment never starts tubematic-dashboard."""
        assert set(RESTARTABLE_SERVICES) == {"renderer", "api", "mcp"}

    def test_mcp_is_its_own_service(self):
        """Flask and the MCP server are separate containers, so bouncing a
        wedged MCP server must not also bounce the API the dashboard and
        poller depend on."""
        assert RESTARTABLE_SERVICES["mcp"] == "tubematic-mcp"
        assert RESTARTABLE_SERVICES["api"] == "tubematic-api"


class TestMain:
    def test_bare_invocation_lists_every_setting(self, monkeypatch, capsys):
        monkeypatch.setattr("edit_settings.fetch_settings", lambda url: dict(_SETTINGS))
        main(["--api-url", "http://api"])
        out = capsys.readouterr().out
        assert "image_model" in out
        assert '"gpt-image-2.5-flare"' in out
        assert "render_timeout_secs" in out

    def test_list_filters_to_the_named_keys(self, monkeypatch, capsys):
        monkeypatch.setattr("edit_settings.fetch_settings", lambda url: dict(_SETTINGS))
        main(["--list", "image_model", "--api-url", "http://api"])
        out = capsys.readouterr().out
        assert "image_model" in out
        assert "render_timeout_secs" not in out

    def test_list_rejects_an_unknown_key(self, monkeypatch):
        monkeypatch.setattr("edit_settings.fetch_settings", lambda url: dict(_SETTINGS))
        with pytest.raises(SystemExit, match="Unknown setting"):
            main(["--list", "nope", "--api-url", "http://api"])

    def test_set_prints_the_effective_value_and_does_not_list_everything(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "edit_settings.apply_settings",
            lambda updates, url: (dict(_SETTINGS, render_timeout_secs=2700), []),
        )
        main(["--set", "render_timeout_secs=2700", "--api-url", "http://api"])
        captured = capsys.readouterr()
        assert "render_timeout_secs  2700" in captured.out
        assert "image_model" not in captured.out
        assert "No restart needed" in captured.err

    def test_set_prints_warnings_to_stderr(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "edit_settings.apply_settings",
            lambda updates, url: (dict(_SETTINGS), ["elevenlabs_voice_id: requested ..."]),
        )
        main(["--set", "elevenlabs_voice_id=nope", "--api-url", "http://api"])
        assert "WARNING" in capsys.readouterr().err

    def test_restart_mcp_without_yes_refuses(self, monkeypatch):
        """The confirmation follows the MCP server, not the API container.
        Restarting tubematic-mcp is what severs a live Claude Code session."""
        called = []
        monkeypatch.setattr("edit_settings.restart_service", lambda s, r: called.append(s))
        with pytest.raises(SystemExit, match="MCP server"):
            main(["--restart", "mcp"])
        assert called == []

    def test_restart_mcp_with_yes_proceeds(self, monkeypatch):
        called = []
        monkeypatch.setattr("edit_settings.restart_service", lambda s, r: called.append(s))
        main(["--restart", "mcp", "--yes"])
        assert called == ["mcp"]

    def test_restart_api_needs_no_confirmation(self, monkeypatch):
        """Since the split, bouncing Flask leaves the agent's tools alone —
        so the guard that used to sit here would now be a false alarm."""
        called = []
        monkeypatch.setattr("edit_settings.restart_service", lambda s, r: called.append(s))
        main(["--restart", "api"])
        assert called == ["api"]

    def test_restart_renderer_needs_no_confirmation(self, monkeypatch):
        called = []
        monkeypatch.setattr("edit_settings.restart_service", lambda s, r: called.append(s))
        main(["--restart", "renderer"])
        assert called == ["renderer"]

    def test_restart_alone_does_not_fetch_settings(self, monkeypatch):
        """--restart is not a read command; it must not require a reachable API."""
        monkeypatch.setattr("edit_settings.restart_service", lambda s, r: None)
        monkeypatch.setattr(
            "edit_settings.fetch_settings",
            lambda url: pytest.fail("fetch_settings should not have been called"),
        )
        main(["--restart", "renderer"])


class TestHelpCatalog:
    """--help has to answer "what can I change, and to what" — the reason to
    reach for it at all. Everything concrete in it is read off
    renderer/api/pipeline.py so it cannot drift from what POST /settings
    accepts."""

    def _help_text(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        return capsys.readouterr().out

    def test_lists_every_settable_key(self, capsys):
        sys.path.insert(0, str(REPO_ROOT / "renderer" / "api"))
        import pipeline

        text = self._help_text(capsys)
        missing = [k for k in pipeline.SETTINGS_SPEC if k not in text]
        assert missing == []

    def test_model_catalogs_come_from_pipeline_not_a_local_copy(self, capsys):
        """The drift guard: adding a model to pipeline.py must show up here
        with no edit to this script."""
        sys.path.insert(0, str(REPO_ROOT / "renderer" / "api"))
        import pipeline

        text = self._help_text(capsys)
        for model in pipeline.OPENAI_IMAGE_MODELS:
            assert model in text
        for model in pipeline.DICTIONARY_COMPATIBLE_MODELS:
            assert model in text
        assert str(pipeline.MAX_VOICES) in text

    def test_says_defaults_are_not_the_live_values(self, capsys):
        """The shown defaults are SETTINGS_SPEC's, which vqa/make_seed_db.py
        seeds over — claiming them as current would misinform."""
        text = self._help_text(capsys)
        assert "shipped defaults" in text
        assert "values actually in effect" in text

    def test_flags_the_settings_that_do_nothing_here(self, capsys):
        text = self._help_text(capsys)
        assert "no cron, no topic research" in text

    def test_says_the_model_lives_on_each_voice(self, capsys):
        """There is no install-wide model to set any more (TMDEV-121); a
        reader looking for one must be told where it went."""
        text = self._help_text(capsys)
        assert "each voice in elevenlabs_voices" in text
        assert "elevenlabs_model_id" not in text

    def test_help_does_not_call_the_api(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "edit_settings.fetch_settings",
            lambda url: pytest.fail("--help must work with no stack running"),
        )
        self._help_text(capsys)

    def test_catalog_says_so_when_pipeline_cannot_be_imported(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "pipeline", None)
        text = _settings_catalog()
        assert "catalog unavailable" in text.lower()
        assert "--set" not in text  # no half-built list implying completeness


class TestResolvesItsOwnTree:
    """Same guarantee vqa/reset_db.py, review_video.py and stage_script.py each
    carry: the copy running under the persisted ~/tubematic working tree must
    operate on *that* tree, not on wherever the process was launched from."""

    def test_restart_runs_compose_in_the_scripts_own_tree(self, tmp_path):
        isolated = tmp_path / "isolated_tree"
        (isolated / "vqa").mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "vqa" / "edit_settings.py", isolated / "vqa" / "edit_settings.py")

        # A `docker` shim that records the cwd it was invoked from.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        record = tmp_path / "cwd.txt"
        shim = bin_dir / "docker"
        shim.write_text(f'#!/bin/sh\npwd > "{record}"\n')
        shim.chmod(0o755)

        result = subprocess.run(
            [sys.executable, str(isolated / "vqa" / "edit_settings.py"), "--restart", "renderer"],
            cwd="/",  # deliberately not `isolated` — proves resolution isn't cwd-based
            capture_output=True,
            text=True,
            env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        )

        assert result.returncode == 0, result.stderr
        assert record.read_text().strip() == str(isolated)
