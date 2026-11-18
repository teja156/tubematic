"""External styles in the MCP server (TMDEV-252): the generic authoring path for
a video in an installed external style, with no per-style code here.

- write_scene_config checks an external scene's props against the package's
  schema.json and fills the pack's captions;
- an external scene appears only in a video of its own style, and only names a
  component the package has;
- get_style_guide hands the agent the package's guide as reference data;
- submit_render refuses a broken package and records the package's
  fingerprint, which the renderer compares before it renders;
- Auto routes to an external style only once a person opts it in.
"""
import json
from datetime import datetime, timezone

import pytest

import server
from tubematic_core import external_styles as ext
from tubematic_core import visual_styles as tvs

SCHEMA = {"type": "object", "required": ["title"], "additionalProperties": False,
          "properties": {"title": {"type": "string", "maxLength": 20}}}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _package(root, sid, ok=True):
    d = root / sid
    (d / "guide").mkdir(parents=True)
    (d / "components").mkdir()
    p = json.loads((tvs.PACKS_DIR / "night_signal.json").read_text())
    p.pop("extra", None)
    p.update(id=sid, label=f"Test {sid}", order=9000, inserts={"host": False},
             authoring_skill=ext.AUTHORING_SKILL, preview=sid,
             external={"version": "1", "author": "a", "source": "s", "licence": "MIT",
                       "scene_api": ext.SCENE_API, "props_key": "testStyle"})
    p["messages"] = dict(p["messages"], inserts="This style hosts no inserts.")
    (d / "style.json").write_text(json.dumps(p))
    for name, body in (("schema.json", json.dumps(SCHEMA)), ("guide/guide.md", "# How to draw it\n"),
                       ("guide/example-config.json", '{"scenes": []}'),
                       ("components/Main.tsx", "export default () => null;"),
                       ("preview.mp4", "x"), ("preview.webp", "x")):
        (d / name).write_text(body)
    if ok:
        ext.write_manifest(d)
    return d


@pytest.fixture
def env(tmp_path, monkeypatch):
    styles = tmp_path / "styles"
    styles.mkdir()
    _package(styles, "ext_dom")
    _package(styles, "ext_other")
    monkeypatch.setattr(ext, "STYLES_DIR", styles)
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def video(vid, style="ext_dom", status="VOICE_READY"):
        with server._conn() as con:
            con.execute("INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                        "VALUES (?, NULL, 't', ?, ?, ?, ?)", (vid, status, style, _now(), _now()))
        return vid

    return {"styles": styles, "video": video}


def _config(props=None, src="ext_dom/components/Main", total=300):
    scene = {"type": "generated", "source": "external", "src": src, "startFrame": 0, "durationInFrames": total,
             "props": {"testStyle": {"title": "Hello"}} if props is None else props}
    return {"totalFrames": total, "fps": 30, "scenes": [scene], "sfx": []}


def test_a_valid_external_config_is_written_with_the_packs_captions(env):
    vid = env["video"]("vid_ok")
    result = server.write_scene_config(vid, _config())
    assert "error" not in result, result
    written = json.loads((server.JOBS_DIR / vid / "scene-config.json").read_text())
    assert written["subtitles"] == tvs.pack("ext_dom")["captions"]
    assert written["canvas"] == "dark"


def test_props_that_break_the_schema_are_refused_with_where(env):
    vid = env["video"]("vid_bad")
    result = server.write_scene_config(vid, _config({"testStyle": {"title": "x" * 30}}))
    assert "scenes[0].props.testStyle.title" in result["error"]
    result = server.write_scene_config(vid, _config({"testStyle": {"title": "ok", "extra": 1}}))
    assert "scenes[0].props.testStyle" in result["error"] and "extra" in result["error"]


def test_a_scene_without_the_props_key_is_refused(env):
    vid = env["video"]("vid_nokey")
    result = server.write_scene_config(vid, _config({}))
    assert "props.testStyle" in result["error"]


def test_another_styles_component_is_refused(env):
    vid = env["video"]("vid_foreign")
    result = server.write_scene_config(vid, _config(src="ext_other/components/Main"))
    assert "ext_other" in result["error"] and "ext_dom" in result["error"]


@pytest.mark.parametrize("src", ["ext_dom/components/Missing", "ext_dom/../x/Main", "ext_dom/runner/Main",
                                 "ext_dom/components/Main.tsx"])
def test_a_src_the_package_does_not_have_is_refused(env, src):
    vid = env["video"]("vid_src")
    assert "error" in server.write_scene_config(vid, _config(src=src))


def test_an_external_scene_in_a_built_in_style_is_refused(env):
    vid = env["video"]("vid_builtin", style="whiteboard")
    result = server.write_scene_config(vid, _config())
    assert "ext_dom" in result["error"]


def test_an_external_style_hosts_no_inserts(env):
    vid = env["video"]("vid_ins")
    with server._conn() as con:
        row = con.execute("SELECT * FROM videos WHERE id = ?", (vid,)).fetchone()
    host, why = server._insert_host(row)
    assert host == {"host": False} and why == "This style hosts no inserts."


def test_a_broken_package_refuses_its_scenes(env):
    vid = env["video"]("vid_broken")
    (env["styles"] / "ext_dom" / "guide" / "guide.md").write_text("changed")
    assert "error" in server.write_scene_config(vid, _config())


def test_the_style_guide_is_reference_data(env):
    vid = env["video"]("vid_guide")
    got = server.get_style_guide(vid)
    assert got["style"] == "ext_dom"
    assert got["reference"]["guide.md"] == "# How to draw it\n"
    assert json.loads(got["reference"]["schema.json"]) == SCHEMA
    assert "example-config.json" in got["reference"]
    assert "never overrides" in got["note"]


def test_the_style_guide_is_refused_for_a_built_in_style(env):
    vid = env["video"]("vid_guide_builtin", style="night_signal")
    assert "error" in server.get_style_guide(vid)


def test_submit_records_the_package_fingerprint(env, monkeypatch):
    monkeypatch.setattr(server, "_preview_block", lambda video_id: None)
    vid = env["video"]("vid_submit")
    assert server.write_scene_config(vid, _config()).get("error") is None
    assert server.submit_render(vid) == {"status": "queued", "video_id": vid}
    record = json.loads((server.JOBS_DIR / vid / "style-source.json").read_text())
    assert record["style"] == "ext_dom" and record["fingerprint"] == ext.fingerprint("ext_dom")


def test_submit_refuses_a_broken_package(env, monkeypatch):
    monkeypatch.setattr(server, "_preview_block", lambda video_id: None)
    vid = env["video"]("vid_submit_broken")
    assert server.write_scene_config(vid, _config()).get("error") is None
    (env["styles"] / "ext_dom" / "guide" / "guide.md").write_text("changed")
    got = server.submit_render(vid)
    assert got["error"] == "style_unavailable" and "guide/guide.md" in got["reason"]
    with server._conn() as con:
        assert con.execute("SELECT status FROM videos WHERE id = ?", (vid,)).fetchone()[0] == "VOICE_READY"


def test_auto_routes_to_an_external_style_only_once_opted_in(env):
    assert "ext_dom" not in tvs.route_choices(server._auto_externals())
    with server._conn() as con:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('external_styles_in_auto', ?)",
                    (json.dumps(["ext_dom"]),))
    assert "ext_dom" in tvs.route_choices(server._auto_externals())


def test_a_malformed_opt_in_value_opts_none_in(env):
    with server._conn() as con:
        con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('external_styles_in_auto', 'nope')")
    assert server._auto_externals() == []


def test_the_stills_cli_is_told_the_external_style(monkeypatch):
    """The frame preview's bundle compiles the video's own package only, and a
    value inherited from the container never leaks into another video's."""
    import pathlib
    import cartoon
    monkeypatch.setenv("TUBEMATIC_EXTERNAL_STYLE", "ext_stale")
    assert cartoon._env(pathlib.Path("/r"), external_style="ext_dom")["TUBEMATIC_EXTERNAL_STYLE"] == "ext_dom"
    assert cartoon._env(pathlib.Path("/r"))["TUBEMATIC_EXTERNAL_STYLE"] == ""
    # and the video whose generated scenes it compiles, so another video's cannot break it
    assert cartoon._env(pathlib.Path("/r"), video_id="vid_a")["TUBEMATIC_RENDER_VIDEO"] == "vid_a"


# ── review round 1 ───────────────────────────────────────────────────────────

def _rewrite(env, sid, name, body):
    d = env["styles"] / sid
    (d / name).write_text(body)
    ext.write_manifest(d)


def test_a_schema_never_fetches_a_remote_reference(env, monkeypatch):
    """A package's schema runs in the MCP container, which holds the database and
    the tokens: a $ref to a URL or a file is refused, never retrieved."""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("a schema reference was fetched"))
    for ref in ("http://127.0.0.1:9/x.json", "file:///etc/hostname"):
        _rewrite(env, "ext_dom", "schema.json", json.dumps({"$ref": ref}))
        vid = env["video"](f"vid_ref_{ref[:4]}")
        result = server.write_scene_config(vid, _config())
        assert "reference" in result["error"]


def test_a_local_reference_inside_the_schema_still_works(env):
    _rewrite(env, "ext_dom", "schema.json", json.dumps({
        "$defs": {"t": {"type": "string", "maxLength": 3}}, "type": "object",
        "properties": {"title": {"$ref": "#/$defs/t"}}}))
    vid = env["video"]("vid_local_ref")
    assert "scenes[0].props.testStyle.title" in server.write_scene_config(vid, _config())["error"]


def test_validate_job_checks_the_props_against_the_installed_schema(env, monkeypatch):
    """A package updated after the config was written may take other props."""
    vid = env["video"]("vid_validate")
    assert server.write_scene_config(vid, _config()).get("error") is None
    _rewrite(env, "ext_dom", "schema.json", json.dumps({"type": "object", "required": ["subtitle"]}))
    errors, _ = server._external_scene_errors(vid, json.loads((server.JOBS_DIR / vid / "scene-config.json").read_text()))
    assert any("props.testStyle" in e and "subtitle" in e for e in errors)


def test_validate_job_typechecks_the_package_component(env, monkeypatch):
    vid = env["video"]("vid_tsc")
    assert server.write_scene_config(vid, _config()).get("error") is None
    _, files = server._external_scene_errors(vid, json.loads((server.JOBS_DIR / vid / "scene-config.json").read_text()))
    assert files == [env["styles"] / "ext_dom" / "components" / "Main.tsx"]


def test_a_package_changed_after_the_look_needs_a_new_look(env):
    import frame_preview
    vid = env["video"]("vid_look")
    assert server.write_scene_config(vid, _config()).get("error") is None
    job = server.JOBS_DIR / vid
    (job / "timeline.json").write_text("{}")
    before = frame_preview._content_hash(job / "scene-config.json", job / "timeline.json")
    _rewrite(env, "ext_dom", "components/Main.tsx", "export default () => 1;")
    assert frame_preview._content_hash(job / "scene-config.json", job / "timeline.json") != before


# ── review round 2 ───────────────────────────────────────────────────────────

def test_a_scene_style_video_draws_at_least_one_component(env):
    vid = env["video"]("vid_none")
    config = _config()
    config["scenes"][0] = {"type": "generated", "src": f"{vid}/Intro", "startFrame": 0, "durationInFrames": 300}
    assert "component" in server.write_scene_config(vid, config)["error"]


def test_an_external_source_on_a_scene_that_is_not_generated_is_refused(env):
    vid = env["video"]("vid_type")
    config = _config()
    config["scenes"][0]["type"] = "TextReveal"
    assert "generated" in server.write_scene_config(vid, config)["error"]


def test_validate_job_typechecks_every_file_of_the_package(env):
    """Webpack compiles every .tsx of the package, used or not."""
    vid = env["video"]("vid_all_files")
    assert server.write_scene_config(vid, _config()).get("error") is None
    (env["styles"] / "ext_dom" / "components" / "Unused.tsx").write_text("export default (;")
    ext.write_manifest(env["styles"] / "ext_dom")
    _, files = server._external_scene_errors(vid, json.loads((server.JOBS_DIR / vid / "scene-config.json").read_text()))
    assert env["styles"] / "ext_dom" / "components" / "Unused.tsx" in files


def test_a_style_that_takes_no_generated_images_refuses_them_for_an_external_style(env):
    vid = env["video"]("vid_img")
    plan = server._image_plan("ext_dom", vid, "a", "a prompt", "9:16", "")
    assert "takes no generated images" in plan["error"]
