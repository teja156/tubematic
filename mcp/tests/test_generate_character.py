"""Transparent character assets for the illustrated register (TMDEV-101).

Everything here is about the shape of the request and the guards around it —
the network call itself is stubbed. What the stubs encode was PROBED against
the real API, and two of the ticket's stated premises turned out wrong:

  * Arbitrary sizes are accepted, not just the documented trio. The constraint
    is that both dimensions are divisible by 16 — which is why the canvas's own
    1080 width cannot be asked for (67.5 x 16) and 1088 is used instead.
  * gpt-image-2 REFUSES `input_fidelity`, the parameter the ticket named as the
    decisive character-drift control. It does not need it: a plain reference
    image carried the character through a pose change intact, while the model
    that does accept the parameter baked in a ground shadow.

The model is the character_model setting (TMDEV-148): gpt-image-2 lost its
transparency in October 2026 and left the catalog. A stored model that cannot
draw a transparent background is refused before any request goes out, and a
key whose OpenAI project lacks the model gets a message saying so.

Run from repo root: pytest mcp/tests/
"""
import ast
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, created_at, updated_at) "
            "VALUES ('vid_c', NULL, 't', 'VOICE_READY', ?, ?)", (_now(), _now()))
    monkeypatch.setattr(server, "_openai_key", lambda: "sk-test")
    return tmp_path


class _Resp:
    status_code = 200
    text = ""

    @staticmethod
    def json():
        # 1x1 transparent PNG
        return {"data": [{"b64_json":
                          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="}],
                "usage": {"input_tokens": 30, "output_tokens": 6240}}


@pytest.fixture
def capture(monkeypatch):
    """Record the outgoing request instead of making it."""
    seen = {}

    def fake_post(url, **kw):
        seen["url"] = url
        seen.update(kw)
        return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_the_first_asset_goes_to_generations(db, capture):
    r = server.generate_character("vid_c", "ana-base", "a character, no shadow")
    assert "error" not in r
    assert capture["url"] == server.OPENAI_IMAGES_URL
    assert capture["json"]["background"] == "transparent"
    assert capture["json"]["model"] == "gpt-image-2.5-flare"


@pytest.mark.parametrize("model", ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
def test_the_character_model_setting_chooses_the_model(db, capture, model):
    server._set_setting("character_model", model)
    r = server.generate_character("vid_c", "ana-base", "a character, no shadow")
    assert r["model"] == model
    assert capture["json"]["model"] == model
    server.generate_character("vid_c", "ana-point", "pointing", reference="ana-base")
    assert capture["data"]["model"] == model, "the edits path follows the setting too"


@pytest.mark.parametrize("stored", ["gpt-image-2", "gemini-2.5-flash-image", ""])
def test_a_model_that_cannot_do_transparency_is_refused_before_spending(db, capture, stored):
    """gpt-image-2 is still a real model that 400s on a transparent background.
    A stale or hand-edited row must be refused here, by name, not by the vendor."""
    server._set_setting("character_model", stored)
    r = server.generate_character("vid_c", "ana-base", "a character, no shadow")
    assert "cannot produce transparent cut-outs" in r["error"]
    assert repr(stored) in r["error"]
    assert "Settings → Images" in r["error"]
    assert capture == {}, "no request should have been made"


def test_every_offered_model_is_a_character_model():
    """The single catalog doubles as the transparency allowlist."""
    assert server.DEFAULT_CHARACTER_MODEL in server.OPENAI_IMAGE_MODELS
    assert "gpt-image-2" not in server.OPENAI_IMAGE_MODELS


_REPO = pathlib.Path(__file__).resolve().parents[2]


def _list_literal(relpath: str, pattern: str) -> list:
    text = (_REPO / relpath).read_text()
    match = re.search(pattern, text)
    assert match, f"{pattern!r} not found in {relpath}"
    return ast.literal_eval(match.group(1))


def test_the_four_openai_catalog_copies_agree():
    """Four processes, four hand-kept copies. One left behind offers a model
    another refuses — the dashboard saving a value the API 400s, or onboarding
    seeding one the MCP tool rejects at render time."""
    copies = {
        "renderer/api/pipeline.py": r"OPENAI_IMAGE_MODELS = (\[[^\]]*\])",
        "onboard/config.py": r"OPENAI_IMAGE_MODELS = (\[[^\]]*\])",
        "dashboard/app/settings/page.tsx": r"const OPENAI_IMAGE_MODELS = (\[[^\]]*\]);",
        "scripts/probe_openai_images.py": r"CATALOG = (\[[^\]]*\])",
    }
    for relpath, pattern in copies.items():
        assert _list_literal(relpath, pattern) == server.OPENAI_IMAGE_MODELS, relpath


def test_the_character_model_default_matches_the_settings_spec():
    text = (_REPO / "renderer/api/pipeline.py").read_text()
    match = re.search(r'"character_model":\s*\("str",\s*"([^"]+)"\)', text)
    assert match and match.group(1) == server.DEFAULT_CHARACTER_MODEL


def test_the_image_model_default_matches_the_settings_spec():
    """The MCP default applies when no row is stored; the spec default is what
    the dashboard shows. Two different models would mean the dashboard names one
    model while scene images come from another."""
    text = (_REPO / "renderer/api/pipeline.py").read_text()
    match = re.search(r'"image_model":\s*\("str",\s*"([^"]+)"\)', text)
    assert match and match.group(1) == server.DEFAULT_IMAGE_MODEL


def test_every_openai_image_model_has_a_built_in_price():
    """A model missing from the shipped snapshot is unpriced on every fresh
    install until the first weekly sync."""
    snapshot = json.loads((_REPO / "tubematic_core/prices_snapshot.json").read_text())
    for model in server.OPENAI_IMAGE_MODELS:
        assert f"openai/{model}" in snapshot["models"], model


def test_every_character_call_is_recorded_against_the_video(db, capture):
    """One row per pose — a regenerated pose overwrites the file but was paid for."""
    server.generate_character("vid_c", "ana-base", "a character, no shadow")
    server.generate_character("vid_c", "ana-base", "a character, no shadow")
    with server._conn() as con:
        rows = con.execute(
            "SELECT e.model, e.operation, e.units, l.video_id FROM usage_events e "
            "JOIN usage_event_videos l ON l.event_id = e.id").fetchall()
    assert [(r["model"], r["operation"], r["video_id"]) for r in rows] == \
        [("gpt-image-2.5-flare", "character", "vid_c")] * 2
    assert json.loads(rows[0]["units"]) == {"input": 30, "output_image": 6240}


def test_a_pose_with_a_reference_goes_to_edits(db, capture):
    """The reference is the whole mechanism — without it every pose is a
    different character, which is what makes an illustrated video look broken
    rather than merely inconsistent."""
    server.generate_character("vid_c", "ana-base", "a character, no shadow")
    r = server.generate_character("vid_c", "ana-point", "same character pointing",
                                  reference="ana-base")
    assert "error" not in r
    assert capture["url"] == server.OPENAI_IMAGE_EDITS_URL
    assert "image[]" in capture["files"]
    assert capture["data"]["background"] == "transparent"


def test_input_fidelity_is_never_sent(db, capture):
    """gpt-image-2, gpt-image-2.5-flare and gpt-image-2.5-sunburst all return
    400 for it (probed). Adding it back breaks every character call."""
    server.generate_character("vid_c", "ana-base", "a character, no shadow")
    server.generate_character("vid_c", "ana-point", "pointing", reference="ana-base")
    assert "input_fidelity" not in capture.get("data", {})
    assert "input_fidelity" not in capture.get("json", {})


def test_every_offered_size_is_divisible_by_sixteen(db):
    """The real 400 is 'Width and height must both be divisible by 16'. The
    canvas is 1080 wide, which is NOT — so a size table that looks like it
    should contain 1080x1920 is exactly the mistake to guard against."""
    for name, size in server.CHARACTER_SIZES.items():
        w, h = (int(v) for v in size.split("x"))
        assert w % 16 == 0 and h % 16 == 0, f"{name}={size} is not 16-divisible"
    assert "1080x1920" not in server.CHARACTER_SIZES.values()


def test_a_missing_reference_is_refused_before_spending(db, capture):
    r = server.generate_character("vid_c", "ana-point", "pointing", reference="nope")
    assert "not found" in r["error"]
    assert capture == {}, "no request should have been made"


def test_without_an_openai_key_it_refuses_rather_than_degrading(db, monkeypatch, capture):
    """Gemini has no transparency option at all. Silently falling back would
    produce an opaque rectangle where a cut-out was asked for."""
    monkeypatch.setattr(server, "_openai_key", lambda: "")
    r = server.generate_character("vid_c", "ana-base", "a character")
    assert "OpenAI API key not set" in r["error"]
    assert "no fallback" in r["error"]
    assert capture == {}


def test_an_unknown_size_is_refused(db, capture):
    assert "must be one of" in server.generate_character(
        "vid_c", "ana-base", "x", size="9:16")["error"]
    assert capture == {}


def test_a_bad_character_name_is_refused(db, capture):
    """character_name is a path component; the guard is the same one
    generate_image uses for image_name."""
    r = server.generate_character("vid_c", "../escape", "x")
    assert "character_name" in r["error"]
    assert capture == {}


def test_a_character_name_reserves_room_for_png_only(db, capture):
    """A character is always `<name>.png`, so 251 characters is a 255-byte
    file name and fits; generate_image's longer `.webp` reservation does not
    apply here."""
    assert "character_name" in server.generate_character("vid_c", "x" * 252, "x")["error"]
    assert capture == {}
    r = server.generate_character("vid_c", "x" * 251, "a character")
    assert "error" not in r
    assert (server.JOBS_DIR / "vid_c" / "images" / f"{'x' * 251}.png").exists()


def test_a_reference_reserves_room_for_png_only(db, capture):
    """The reference is read as `<reference>.png`, so an existing 251-character
    asset can still be posed."""
    server.generate_character("vid_c", "x" * 251, "a character")
    capture.clear()
    r = server.generate_character("vid_c", "x-point", "pointing", reference="x" * 252)
    assert "reference" in r["error"]
    assert capture == {}
    r = server.generate_character("vid_c", "x-point", "pointing", reference="x" * 251)
    assert "error" not in r
    assert capture["url"] == server.OPENAI_IMAGE_EDITS_URL


def test_it_writes_beside_the_scene_images(db, capture):
    """Same directory generate_image uses, so the render worker's whole-dir
    copytree stages it for free, with no staging change needed."""
    r = server.generate_character("vid_c", "ana-base", "a character")
    assert r["public_path"] == "/public/vid_c/images/ana-base.png"
    assert (server.JOBS_DIR / "vid_c" / "images" / "ana-base.png").exists()


def test_a_plain_stick_video_may_not_generate_characters(db, capture):
    """Plain 'stick' is the hand-drawn tier. Honouring this call there would
    quietly turn it into the illustrated one, which the human did not pick —
    and would bill them for it."""
    with server._conn() as con:
        con.execute("UPDATE videos SET visual_style = 'stick' WHERE id = 'vid_c'")
    r = server.generate_character("vid_c", "ana-base", "a character")
    assert "does not use generated character art" in r["error"]
    assert "StickFigure" in r["error"]
    assert capture == {}, "no request should have been made"


def test_a_motion_graphics_video_may_not_generate_characters(db, capture):
    with server._conn() as con:
        con.execute("UPDATE videos SET visual_style = 'motion_graphics' WHERE id = 'vid_c'")
    assert "error" in server.generate_character("vid_c", "ana-base", "a character")
    assert capture == {}


def test_an_illustrated_video_may(db, capture):
    with server._conn() as con:
        con.execute("UPDATE videos SET visual_style = 'illustrated' WHERE id = 'vid_c'")
    assert "error" not in server.generate_character("vid_c", "ana-base", "a character")
    assert capture["url"] == server.OPENAI_IMAGES_URL


def test_it_reports_the_files_real_pixel_dimensions(db, capture, monkeypatch):
    """The panel that frames a character has to be sized to the real image, or
    cover-cropping trims the subject out of it. The REQUESTED size is not good
    enough — a provider answers with its own nearest bucket, which is how this
    repo once shipped five weeks of square images against a 9:16 request."""
    r = server.generate_character("vid_c", "ana-base", "a character")
    # The stub returns a 1x1 PNG, so these are the file's dimensions, not the
    # "portrait" size that was asked for.
    assert (r["width"], r["height"]) == (1, 1)
    assert r["size"] == "1088x1920", "the requested size is reported separately"


def test_unreadable_bytes_report_zero_rather_than_raising(db, capture, monkeypatch):
    """A dimension probe must never be the thing that fails a paid generation —
    the image is already written and billed by this point."""
    assert server._image_pixel_size("/nonexistent/nope.png") == (0, 0)


# ── Failures reach the log (TMDEV-126) ────────────────────────────────────────

def test_an_openai_error_is_one_error_line_naming_the_provider(db, monkeypatch, through_mcp):
    class _Failed:
        status_code = 400
        text = '{"error": {"message": "Billing hard limit has been reached"}}'

    import httpx
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Failed())
    out, (rec,) = through_mcp("generate_character", video_id="vid_c", character_name="ana-base",
                              prompt="a character, no shadow")
    assert out == {"error": f"OpenAI 400: {_Failed.text}"}
    assert (rec.levelname, rec.outcome) == ("ERROR", "error")
    assert (rec.provider_service, rec.provider_status, rec.provider_model,
            rec.provider_operation) == ("openai", 400, server.DEFAULT_CHARACTER_MODEL, "character")
    assert "Billing hard limit" in rec.provider_body


class _NoAccess:
    """The 403 a key gets when its OpenAI project has not been granted the model.
    The catalog (GET /v1/models) can list the model while this still happens."""
    status_code = 403
    text = ('{"error": {"message": "Project `proj_A3rQx9` does not have access to model '
            'gpt-image-2.5-flare", "type": "invalid_request_error", "code": "model_not_found"}}')

    @classmethod
    def json(cls):
        return json.loads(cls.text)


def test_a_project_without_access_gets_an_actionable_error(db, monkeypatch, through_mcp):
    import httpx
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _NoAccess())
    out, (rec,) = through_mcp("generate_character", video_id="vid_c", character_name="ana-base",
                              prompt="a character, no shadow")
    assert "project proj_A3rQx9 has no access to gpt-image-2.5-flare" in out["error"]
    assert "Settings → API Keys" in out["error"] and "Settings → Images" in out["error"]
    # Still loud in the log: a 403 is a provider failure, not a refusal.
    assert (rec.levelname, rec.provider_status) == ("ERROR", 403)


def test_any_other_403_keeps_the_generic_error(db, monkeypatch):
    class _Forbidden(_NoAccess):
        text = '{"error": {"message": "Country, region, or territory not supported"}}'

    import httpx
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _Forbidden())
    r = server.generate_character("vid_c", "ana-base", "a character, no shadow")
    assert r["error"] == f"OpenAI 403: {_Forbidden.text}"


def test_a_malformed_character_200_is_reported_as_http_200(db, monkeypatch, through_mcp):
    class _BadJson:
        status_code = 200
        text = "<html>gateway</html>"

        @staticmethod
        def json():
            raise ValueError("Expecting value: line 1 column 1")

    import httpx
    monkeypatch.setattr(httpx, "post", lambda url, **kw: _BadJson())
    out, (rec,) = through_mcp("generate_character", video_id="vid_c", character_name="ana-base",
                              prompt="a character, no shadow")
    assert out["error"].startswith("Character generation failed:")
    assert (rec.levelname, rec.provider_status) == ("ERROR", 200)
