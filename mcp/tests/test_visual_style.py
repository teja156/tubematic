"""Per-video visual register — the freeze, the write-once resolution, and the
canvas key (TMDEV-101).

Three invariants are worth more than the rest of this file:

  * visual_style is frozen after TOPIC_PROPOSED, like script_profile_id and
    agent_model. It is read by the scripting skill before it writes a single
    visual brief, so changing it later invalidates every brief and means a
    rewrite, not a re-render.
  * resolved_visual_style is write-once. That, and nothing else, is what makes
    "a revision round renders at the register the video already uses" true —
    no code on the revision path knows this field exists.
  * write_scene_config rejects a canvas that contradicts the video's register,
    but never rejects an absent one. The asymmetry is deliberate; see the test
    that pins it.

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

from datetime import datetime, timezone

import pytest

import server


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path, monkeypatch):
    # No OpenAI key unless a test stores one: _openai_key falls back to the
    # environment, and a developer shell exporting it would otherwise make
    # every "no key" test pass for the wrong reason.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    server._init_db()
    return tmp_path / "test.db"


def _video(video_id="vid_1", status="TOPIC_PROPOSED", style="auto", resolved=""):
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, project_id, topic, status, visual_style, "
            "resolved_visual_style, created_at, updated_at) "
            "VALUES (?, NULL, 'a topic', ?, ?, ?, ?, ?)",
            (video_id, status, style, resolved, _now(), _now()),
        )
    return video_id


def _project(pid="proj_1", default_style=""):
    with server._conn() as con:
        con.execute(
            "INSERT INTO projects (id, name, default_visual_style, created_at) "
            "VALUES (?, 'Domain', ?, ?)",
            (pid, default_style, _now()),
        )
    return pid


def _read(video_id, column):
    with server._conn() as con:
        return con.execute(
            f"SELECT {column} FROM videos WHERE id = ?", (video_id,)).fetchone()[0]


def _config(total_frames=300, **extra):
    return {
        "totalFrames": total_frames,
        "fps": 30,
        "scenes": [
            {"type": "generated", "src": "intro", "startFrame": 0,
             "durationInFrames": total_frames},
        ],
        "sfx": [],
        **extra,
    }


# ── the freeze ───────────────────────────────────────────────────────────────

def test_visual_style_is_settable_at_the_topic_checkpoint(db):
    _video("vid_a", status="TOPIC_PROPOSED")
    result = server.update_video("vid_a", visual_style="stick")
    assert "error" not in result
    assert _read("vid_a", "visual_style") == "stick"


def test_visual_style_is_frozen_after_the_topic_checkpoint(db):
    """The scripting skill reads it before writing any visual brief, so a
    later change would invalidate every brief the video already carries."""
    _video("vid_b", status="SCRIPT_READY", style="motion_graphics")
    result = server.update_video("vid_b", visual_style="stick")
    assert "TOPIC_PROPOSED" in result["error"]
    assert _read("vid_b", "visual_style") == "motion_graphics"


def test_an_unknown_visual_style_is_refused(db):
    _video("vid_c")
    result = server.update_video("vid_c", visual_style="whiteboard")
    assert "Invalid visual_style" in result["error"]
    assert _read("vid_c", "visual_style") == "auto"


def test_illustrated_is_a_value(db):
    """generate_character can produce the assets, so the option is real."""
    server._set_setting("openai_api_key", "sk-test")
    _video("vid_d")
    assert "error" not in server.update_video("vid_d", visual_style="illustrated")


def test_illustrated_is_refused_without_an_openai_key(db):
    """The key used to be consulted only by generate_character — after voicing,
    on a video whose style was already frozen. The refusal belongs where the
    style is chosen, before any spend."""
    _video("vid_k")
    result = server.update_video("vid_k", visual_style="illustrated")
    assert result == {"error": server.ILLUSTRATED_NEEDS_OPENAI_KEY}
    assert _read("vid_k", "visual_style") == "auto"


def test_a_key_from_the_environment_counts(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    _video("vid_e")
    assert "error" not in server.update_video("vid_e", visual_style="illustrated")


def test_the_other_styles_need_no_key(db):
    _video("vid_n")
    for style in ("auto", "motion_graphics", "stick"):
        assert "error" not in server.update_video("vid_n", visual_style=style), style


def test_illustrated_does_not_fix_a_canvas(db):
    """It fixes only that characters are generated illustrated assets. The
    drawing style and the canvas are both the agent's, chosen from the topic —
    a playful explainer and a serious documentary want different grounds, and
    forcing one would be the coupling this design already removed once.

    So the settled-yet test is membership in CANVAS_BY_STYLE, never equality
    with "auto": "illustrated" is the second style that has to resolve one.
    """
    assert "illustrated" not in server.CANVAS_BY_STYLE
    assert server.effective_canvas("illustrated", "") == ""
    assert server.effective_canvas("illustrated", "dark") == "dark"
    assert server.effective_canvas("illustrated", "light") == "light"


def test_a_canvas_fixing_style_has_nothing_to_resolve(db):
    """The mirror of the test above: the two styles that DO fix a canvas must
    still refuse a resolution, or a forced choice could be overwritten."""
    _video("vid_d2", status="VOICE_READY", style="stick")
    assert "nothing to resolve" in server.update_video(
        "vid_d2", resolved_visual_style="dark")["error"]


def test_illustrated_may_record_its_canvas(db):
    _video("vid_d3", status="VOICE_READY", style="illustrated")
    assert "error" not in server.update_video("vid_d3", resolved_visual_style="dark")
    assert _read("vid_d3", "resolved_visual_style") == "dark"


def test_only_auto_and_illustrated_may_generate_characters(db):
    """The narrower of the two permissions. Plain "stick" means hand-drawn line
    art — that IS the difference between it and the illustrated option, so
    letting it reach for generated art would erase the human's choice."""
    assert server.characters_allowed("auto") is True
    assert server.characters_allowed("illustrated") is True
    assert server.characters_allowed("stick") is False
    assert server.characters_allowed("motion_graphics") is False


def test_freezing_visual_style_does_not_freeze_other_fields(db):
    """The freeze must stay scoped: a video past the checkpoint still takes
    a script, feedback — everything the pipeline writes downstream."""
    _video("vid_e", status="VOICE_READY")
    result = server.update_video("vid_e", gemini_feedback="looks fine")
    assert "error" not in result


# ── the write-once resolution ────────────────────────────────────────────────

def test_auto_can_record_what_it_resolved(db):
    _video("vid_f", status="VOICE_READY", style="auto")
    result = server.update_video("vid_f", resolved_visual_style="light")
    assert "error" not in result
    assert _read("vid_f", "resolved_visual_style") == "light"


def test_recording_a_resolution_is_not_blocked_by_the_status_freeze(db):
    """It is written at scene-config time, long past TOPIC_PROPOSED — a status
    freeze here would make the field unwritable in practice."""
    _video("vid_g", status="REVISION_REQUESTED", style="auto")
    assert "error" not in server.update_video("vid_g", resolved_visual_style="dark")


def test_a_recorded_resolution_cannot_be_changed(db):
    """The regression that makes a video look broken rather than different:
    re-rolling the register mid-video mixes two registers' assets in one
    render. A revision round must reuse what is already recorded."""
    _video("vid_h", status="REVISION_REQUESTED", style="auto", resolved="light")
    result = server.update_video("vid_h", resolved_visual_style="dark")
    assert "written once" in result["error"]
    assert _read("vid_h", "resolved_visual_style") == "light"


def test_rewriting_the_same_resolution_is_allowed(db):
    """A retried call is not an error — only a *change* is."""
    _video("vid_i", status="VOICE_READY", style="auto", resolved="light")
    assert "error" not in server.update_video("vid_i", resolved_visual_style="light")


def test_a_forced_style_has_nothing_to_resolve(db):
    _video("vid_j", status="VOICE_READY", style="stick")
    result = server.update_video("vid_j", resolved_visual_style="dark")
    assert "nothing to resolve" in result["error"]


def test_auto_is_not_a_resolution(db):
    """resolved_visual_style records which concrete register was chosen, so
    'auto' and '' are not values it can hold."""
    _video("vid_k", style="auto")
    assert "Invalid resolved_visual_style" in server.update_video(
        "vid_k", resolved_visual_style="auto")["error"]
    assert "Invalid resolved_visual_style" in server.update_video(
        "vid_k", resolved_visual_style="")["error"]
    # A register name is not a canvas — the column holds the canvas, and only
    # the canvas, because that is the one thing "auto" must fix for the life
    # of the video.
    assert "Invalid resolved_visual_style" in server.update_video(
        "vid_k", resolved_visual_style="stick")["error"]


def test_effective_canvas_prefers_the_forced_choice(db):
    """A video switched off auto is not held to an older automatic decision."""
    assert server.effective_canvas("stick", "dark") == "light"
    assert server.effective_canvas("motion_graphics", "light") == "dark"
    assert server.effective_canvas("auto", "light") == "light"
    assert server.effective_canvas("auto", "") == ""


def test_only_a_forced_motion_graphics_excludes_figures(db):
    """auto permits everything — that is the whole point of it. A dark canvas
    reached via auto may still carry figures, drawn as white line art."""
    assert server.figures_allowed("auto") is True
    assert server.figures_allowed("stick") is True
    assert server.figures_allowed("motion_graphics") is False


# ── the project default ──────────────────────────────────────────────────────

def test_a_curriculum_video_inherits_its_domains_default(db):
    _project("proj_seed", default_style="stick")
    result = server.create_video("proj_seed", "A topic", "curriculum", 7)
    assert result["visual_style"] == "stick"
    assert _read(result["video_id"], "visual_style") == "stick"


def test_a_trending_video_in_the_same_domain_does_not_inherit(db):
    """The register reads as a series identity, and curriculum is the one
    strategy that produces a series. A one-off filed into the same domain
    starts at auto like any other."""
    _project("proj_seed2", default_style="stick")
    result = server.create_video("proj_seed2", "A topic", "trending", 7)
    assert result["visual_style"] == "auto"


def test_a_domain_with_no_default_leaves_curriculum_videos_on_auto(db):
    _project("proj_plain", default_style="")
    result = server.create_video("proj_plain", "A topic", "curriculum", 7)
    assert result["visual_style"] == "auto"


def test_a_corrupt_stored_default_falls_back_to_auto(db):
    """A hand-edited or downgraded row must not be able to make create_video
    write a style nothing understands."""
    _project("proj_bad", default_style="whiteboard")
    result = server.create_video("proj_bad", "A topic", "curriculum", 7)
    assert result["visual_style"] == "auto"


def test_upsert_project_stores_a_default(db):
    row = server.upsert_project("proj_x", "Domain", default_visual_style="motion_graphics")
    assert row["default_visual_style"] == "motion_graphics"


def test_upsert_project_refuses_an_unknown_default(db):
    result = server.upsert_project("proj_y", "Domain", default_visual_style="doodle")
    assert "Invalid default_visual_style" in result["error"]


# ── upsert_project preserves what a partial call leaves out ──────────────────
#
# Its own documented callers are partial: one command converts an existing
# domain into a curriculum seed and names only that; another files a video into
# a domain and names only its slug. A full-replace upsert therefore silently
# blanked whatever those calls did not mention — which is how a domain's
# visual register could be reset by an unrelated command.

def test_omitting_the_style_keeps_the_stored_one(db):
    server.upsert_project("proj_keep", "Domain", default_visual_style="stick")
    row = server.upsert_project("proj_keep", "Domain", is_curriculum_seed=True)
    assert row["default_visual_style"] == "stick"
    assert row["is_curriculum_seed"] == 1


def test_omitting_the_description_and_seed_keeps_them(db):
    """The wider case: the file-a-video command passes only id and name."""
    server.upsert_project("proj_p", "Domain", description="A real description",
                          is_curriculum_seed=True, status="paused")
    row = server.upsert_project("proj_p", "Domain")
    assert row["description"] == "A real description"
    assert row["is_curriculum_seed"] == 1
    assert row["status"] == "paused"


def test_an_empty_string_still_clears_a_default(db):
    """Preserving on omission must not remove the ability to clear a value."""
    server.upsert_project("proj_c", "Domain", default_visual_style="stick")
    row = server.upsert_project("proj_c", "Domain", default_visual_style="")
    assert row["default_visual_style"] == ""


def test_a_new_project_still_gets_the_creation_defaults(db):
    """Omission means 'leave alone' only for a row that exists; a fresh one
    must still land on the documented defaults rather than on NULL."""
    row = server.upsert_project("proj_new", "Domain")
    assert row["description"] == ""
    assert row["is_curriculum_seed"] == 0
    assert row["status"] == "active"
    assert row["default_visual_style"] == ""


def test_a_supplied_value_still_overwrites(db):
    server._set_setting("openai_api_key", "sk-test")
    server.upsert_project("proj_o", "Domain", default_visual_style="stick",
                          is_curriculum_seed=True, status="paused")
    row = server.upsert_project("proj_o", "Renamed", default_visual_style="illustrated",
                                status="active")
    assert row["name"] == "Renamed"
    assert row["default_visual_style"] == "illustrated"
    assert row["status"] == "active"


def test_an_illustrated_project_default_is_refused_without_a_key(db):
    result = server.upsert_project("proj_k", "Domain", default_visual_style="illustrated")
    assert result == {"error": server.ILLUSTRATED_NEEDS_OPENAI_KEY}
    with server._conn() as con:
        assert con.execute("SELECT 1 FROM projects WHERE id = 'proj_k'").fetchone() is None


def test_resending_a_kept_illustrated_default_is_not_refused(db):
    """A default set while a key existed is left alone, and re-sending it with
    another change must still work — refusing it would block every edit to the
    domain once the key is removed. Seeding never rewrites it; the dashboard's
    approval is where a video that inherits it is caught."""
    _project("proj_r", default_style="illustrated")
    row = server.upsert_project("proj_r", "Renamed", default_visual_style="illustrated")
    assert row["name"] == "Renamed"
    assert row["default_visual_style"] == "illustrated"


# ── the canvas key ───────────────────────────────────────────────────────────

def test_a_canvas_contradicting_the_style_is_refused(db):
    """One video, one canvas. Alternating white and dark scenes flashes, so
    this is rejected rather than reconciled."""
    _video("vid_l", status="VOICE_READY", style="stick")
    result = server.write_scene_config("vid_l", _config(canvas="dark"))
    assert "cannot mix canvases" in result["error"]
    assert not (server.JOBS_DIR / "vid_l" / "scene-config.json").exists()


def test_an_unknown_canvas_is_refused(db):
    _video("vid_m", status="VOICE_READY")
    assert "config.canvas must be one of" in server.write_scene_config(
        "vid_m", _config(canvas="beige"))["error"]


def test_an_absent_canvas_is_filled_in_from_the_style(db):
    """Absence is never an error, on purpose.

    An agent running a skill from before this feature omits the key on every
    video. Requiring it would break write_scene_config pipeline-wide the moment
    the backend is rebuilt ahead of the skill push — the whole pipeline failing
    validation at once, rather than one video looking wrong.
    """
    _video("vid_n", status="VOICE_READY", style="stick")
    result = server.write_scene_config("vid_n", _config())
    assert result["canvas"] == "light"
    import json
    written = json.loads((server.JOBS_DIR / "vid_n" / "scene-config.json").read_text())
    assert written["canvas"] == "light"


def test_a_matching_canvas_is_accepted(db):
    _video("vid_o", status="VOICE_READY", style="stick")
    assert server.write_scene_config("vid_o", _config(canvas="light"))["canvas"] == "light"


def test_the_canvas_records_what_auto_resolved_to(db):
    """The backstop for "auto must resolve once and record it": if the agent
    picked a canvas but never called update_video, the canvas IS the choice."""
    _video("vid_p", status="VOICE_READY", style="auto")
    result = server.write_scene_config("vid_p", _config(canvas="light"))
    assert result["canvas"] == "light"
    assert _read("vid_p", "resolved_visual_style") == "light"


def test_the_backstop_never_overwrites_an_explicit_resolution(db):
    """Write-once holds here too — otherwise a revision's second config write
    could quietly move the video to the other register."""
    _video("vid_q", status="REVISION_REQUESTED", style="auto", resolved="light")
    result = server.write_scene_config("vid_q", _config())
    assert result["canvas"] == "light"
    assert _read("vid_q", "resolved_visual_style") == "light"


def test_a_revision_cannot_flip_the_canvas_after_auto_resolved(db):
    _video("vid_r", status="REVISION_REQUESTED", style="auto", resolved="light")
    result = server.write_scene_config("vid_r", _config(canvas="dark"))
    assert "cannot mix canvases" in result["error"]


def test_a_legacy_video_still_writes_a_dark_canvas(db):
    """0002 backfills existing rows to motion_graphics, so this is what every
    video that predates the feature does."""
    _video("vid_s", status="VOICE_READY", style="motion_graphics")
    assert server.write_scene_config("vid_s", _config())["canvas"] == "dark"
