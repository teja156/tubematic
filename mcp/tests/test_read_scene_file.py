"""Tests for read_scene_file (VQA-10): the read half of the scene TSX pair.

write_scene_file has existed since the start; nothing ever read a scene back.
Two docstrings (list_scene_files, write_scene_file) and the scene-config skill
already instructed "read its TSX" with no tool behind it, so both same-video
revision and the documented cross-video copy path were impossible.

Name handling is the load-bearing detail here. list_scene_files and a
scene-config `src` both hand the agent the composed "{video_id}/{scene_name}",
but _VALID_SCENE_NAME forbids "/" and "_" — so a tool taking only the bare
stem would reject the only name the agent was ever shown. Both forms are
accepted; _check_scene_src (already used by validate_job) validates the
composed one.

Requires the mcp/ package deps (fastmcp) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

from datetime import datetime, timezone

import pytest

import server

TSX = "export const Intro = () => <div>hi</div>;\n"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def clear_claims():
    server._scene_claims.clear()
    yield
    server._scene_claims.clear()


@pytest.fixture
def job_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(server, "DB_FILE", db_path)
    server._init_db()

    def make_video(video_id):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, created_at, updated_at) "
                "VALUES (?, NULL, ?, ?, ?, ?)",
                (video_id, "test topic", "REVISION_REQUESTED", _now(), _now()),
            )

    return make_video


@pytest.fixture
def scene_dirs(tmp_path, monkeypatch):
    generated = tmp_path / "generated"
    installed = tmp_path / "installed"
    generated.mkdir()
    installed.mkdir()
    monkeypatch.setattr(server, "SCENES_DIR", generated)
    monkeypatch.setattr(server, "INSTALLED_DIR", installed)
    return generated, installed


def _write_generated(scene_dirs, video_id, scene_name, content=TSX):
    generated, _ = scene_dirs
    d = generated / video_id if video_id else generated
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{scene_name}.tsx").write_text(content, encoding="utf-8")


# ── Name resolution: both forms ───────────────────────────────────────────

def test_composed_name_resolves(job_db, scene_dirs):
    """The form list_scene_files and scene-config's `src` actually hand back."""
    job_db("vid_abc")
    _write_generated(scene_dirs, "vid_abc", "intro-hook")

    result = server.read_scene_file("vid_abc/intro-hook")

    assert result["tsx_content"] == TSX
    assert result["scene_name"] == "intro-hook"
    assert result["video_id"] == "vid_abc"
    assert result["src"] == "vid_abc/intro-hook"
    assert result["source"] == "generated"
    assert result["size_bytes"] == len(TSX.encode())


def test_bare_stem_with_video_id_resolves(job_db, scene_dirs):
    """The form write_scene_file and delete_scene_file take."""
    job_db("vid_abc")
    _write_generated(scene_dirs, "vid_abc", "intro-hook")

    result = server.read_scene_file("intro-hook", video_id="vid_abc")

    assert result["tsx_content"] == TSX
    assert result["src"] == "vid_abc/intro-hook"


def test_composed_name_with_matching_video_id_is_accepted(job_db, scene_dirs):
    job_db("vid_abc")
    _write_generated(scene_dirs, "vid_abc", "intro-hook")

    result = server.read_scene_file("vid_abc/intro-hook", video_id="vid_abc")

    assert result["tsx_content"] == TSX


def test_composed_name_with_conflicting_video_id_errors(job_db, scene_dirs):
    """An explicit error, never a silent precedence rule — the two disagreeing
    is a caller bug, and picking a winner would read the wrong video's scene."""
    job_db("vid_abc")
    job_db("vid_other")
    _write_generated(scene_dirs, "vid_abc", "intro-hook")

    result = server.read_scene_file("vid_abc/intro-hook", video_id="vid_other")

    assert "error" in result
    assert "vid_abc" in result["error"] and "vid_other" in result["error"]


def test_installed_source_resolves(job_db, scene_dirs):
    """installed/ is a shared library scoped to no video — no videos row needed."""
    _, installed = scene_dirs
    (installed / "StepFlowDiagram.tsx").write_text(TSX, encoding="utf-8")

    result = server.read_scene_file("StepFlowDiagram", source="installed")

    assert result["tsx_content"] == TSX
    assert result["source"] == "installed"
    assert result["src"] == "StepFlowDiagram"
    assert result["video_id"] == ""


def test_legacy_flat_generated_file_resolves(job_db, scene_dirs):
    """Pre-namespacing files live directly under generated/ — the same
    allowance delete_scene_file makes with an omitted video_id."""
    _write_generated(scene_dirs, "", "legacy-scene")

    result = server.read_scene_file("legacy-scene")

    assert result["tsx_content"] == TSX
    assert result["src"] == "legacy-scene"


def test_source_is_authoritative_with_no_fallback_between_libraries(job_db, scene_dirs):
    """generated/ and installed/ are searched independently — a name present
    in one is never served from the other.

    This is why a scene-config entry's `src` and `source` must travel
    together. An installed entry's `src` is a bare name, so passing it with
    the default source="generated" reads a legacy flat generated file of the
    same name if one exists — a *different* video's scene, silently, with no
    error to notice. Adding a cross-library fallback would turn that from a
    name-collision edge case into the everyday behavior."""
    _, installed = scene_dirs
    (installed / "StepFlowDiagram.tsx").write_text("INSTALLED", encoding="utf-8")
    _write_generated(scene_dirs, "", "StepFlowDiagram", content="A LEGACY FLAT FILE")

    assert server.read_scene_file(
        "StepFlowDiagram", source="installed")["tsx_content"] == "INSTALLED"
    assert server.read_scene_file(
        "StepFlowDiagram")["tsx_content"] == "A LEGACY FLAT FILE"


def test_installed_src_without_its_source_does_not_fall_back(job_db, scene_dirs):
    """The common shape of the same mistake: no generated file exists, so the
    caller gets a clear error naming the source it actually searched, rather
    than the installed scene it meant."""
    _, installed = scene_dirs
    (installed / "StepFlowDiagram.tsx").write_text("INSTALLED", encoding="utf-8")

    result = server.read_scene_file("StepFlowDiagram")

    assert "not found" in result["error"]
    assert "source=generated" in result["error"]


def test_installed_rejects_a_composed_name(job_db, scene_dirs):
    """installed/ names are flat; a composed one means the caller confused
    the two libraries."""
    result = server.read_scene_file("vid_abc/intro-hook", source="installed")

    assert "error" in result
    assert "installed" in result["error"]


# ── Errors ────────────────────────────────────────────────────────────────

def test_unknown_video_id_errors(job_db, scene_dirs):
    result = server.read_scene_file("vid_nope/intro-hook")
    assert "not found" in result["error"].lower()


def test_missing_scene_errors(job_db, scene_dirs):
    job_db("vid_abc")
    result = server.read_scene_file("vid_abc/nope")
    assert "error" in result
    assert "nope" in result["error"]


def test_invalid_source_errors(job_db, scene_dirs):
    result = server.read_scene_file("intro-hook", source="elsewhere")
    assert "error" in result
    assert "elsewhere" in result["error"]


@pytest.mark.parametrize("name", [
    "../secret",
    "../../etc/passwd",
    "/etc/passwd",
    "vid_abc/../../etc/passwd",
    "a/b/c",
    "",
    ".",
])
def test_traversal_and_malformed_names_are_rejected(job_db, scene_dirs, name):
    job_db("vid_abc")
    result = server.read_scene_file(name)
    assert "error" in result, f"{name!r} was not rejected"


def test_path_shaped_video_id_is_rejected_by_its_shape(job_db, scene_dirs):
    """On the bare-stem path the video_id's shape is checked before any path
    is built (TMDEV-158), the same check every path-building tool makes. A
    row lookup alone used to be the guard; it held only as long as no tool
    skipped it, and delete_scene_file did."""
    result = server.read_scene_file("intro-hook", video_id="../../etc")
    assert "not a valid video id" in result["error"]


# ── Claim exemption ───────────────────────────────────────────────────────

def test_not_guarded_by_the_scene_work_claim(job_db, scene_dirs, monkeypatch):
    job_db("vid_abc")
    _write_generated(scene_dirs, "vid_abc", "intro-hook")
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._try_claim_scene_work("vid_abc", "session:other")

    result = server.read_scene_file("vid_abc/intro-hook")

    assert "error" not in result
    assert result["tsx_content"] == TSX


def test_reading_does_not_take_a_claim(job_db, scene_dirs, monkeypatch):
    job_db("vid_abc")
    _write_generated(scene_dirs, "vid_abc", "intro-hook")
    monkeypatch.setattr(server, "_session_owner", lambda: "session:reader")

    server.read_scene_file("vid_abc/intro-hook")

    assert server._try_claim_scene_work("vid_abc", "session:writer") is None


# ── Round-trip with write_scene_file ──────────────────────────────────────

def test_read_returns_exactly_what_write_wrote(job_db, scene_dirs):
    """The src write_scene_file returns is the src read_scene_file accepts and
    echoes back — so a scene-config entry round-trips without the agent ever
    composing or splitting a name by hand."""
    job_db("vid_abc")
    written = server.write_scene_file("vid_abc", "intro-hook", TSX)

    result = server.read_scene_file(written["src"])

    assert result["tsx_content"] == TSX
    assert result["src"] == written["src"]
    assert result["path"] == written["path"]


def test_cross_video_copy_path_works(job_db, scene_dirs):
    """The reuse workflow both docstrings already described but nothing could
    execute: read a donor video's scene, write it under your own video_id."""
    job_db("vid_donor")
    job_db("vid_mine")
    server.write_scene_file("vid_donor", "orbit-diagram", TSX)

    donor = server.read_scene_file("vid_donor/orbit-diagram")
    mine = server.write_scene_file("vid_mine", "orbit-diagram", donor["tsx_content"])

    assert mine["src"] == "vid_mine/orbit-diagram"
    assert server.read_scene_file(mine["src"])["tsx_content"] == TSX
