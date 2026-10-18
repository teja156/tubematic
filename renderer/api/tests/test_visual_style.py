"""Visual register — the HTTP freeze, the project default, and the review
prompt's style contract (TMDEV-101).

The AI-review half matters more than it looks. The review prompt states no
intended visual style at all, so a line-art-on-white video is judged against an
unstated default: `animation_defect` is worded around polished vector diagrams
("unclean, misplaced, or misaligned") and the prompt's own escalation clause
invites the model to invent a type of its own. Under the "any finding routes to
REVISION_REQUESTED" rule that is not cosmetic — every round is a paid re-voice,
so a systematically mis-judged register wedges the video rather than merely
grading it harshly.

Run from repo root: pytest renderer/api/tests/
"""
import json
import os
import sqlite3

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import ai_review
import pipeline
from pipeline import create_pipeline_blueprint


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """A fully migrated database, unlike test_pipeline.py's hand-rolled old
    schema — these tests are about columns 0002 adds, so the migration running
    is the point rather than something to work around.

    OPENAI_API_KEY is cleared because the key gate falls back to it: a
    developer shell that exports one would otherwise pass every "no key" test
    for the wrong reason."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = str(tmp_path / "test.db")
    os.environ["TUBEMATIC_DB"] = p
    pipeline._init_db(p)
    return p


@pytest.fixture
def client(db_path):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(create_pipeline_blueprint())
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _mcp_block():
    """The hand-copied visual-register block from mcp/server.py, executed in
    isolation so the two copies can be compared as behaviour, not as text."""
    import pathlib as _pathlib

    mcp_path = _pathlib.Path(__file__).resolve().parents[3] / "mcp" / "server.py"
    src = mcp_path.read_text()
    start = src.index("VISUAL_STYLES = (")
    end = src.index("# Canonical set of every valid videos.status value", start)
    ns: dict = {}
    exec(compile(src[start:end], str(mcp_path), "exec"), ns)
    return ns


# ── the cross-copy agreement (the two hand-duplicated copies) ────────────────

def test_the_visual_style_constants_match_the_mcp_copy():
    """Separate processes, separate trees, no shared sys.path — so these are
    hand-copied and can drift silently. A mismatch means the dashboard and the
    agent disagree about what a video is."""
    ns = _mcp_block()
    assert ns["VISUAL_STYLES"] == pipeline.VISUAL_STYLES
    assert ns["RESOLVED_VISUAL_STYLES"] == pipeline.RESOLVED_VISUAL_STYLES
    assert ns["CANVAS_BY_STYLE"] == pipeline.CANVAS_BY_STYLE
    assert ns["VALID_CANVASES"] == pipeline.VALID_CANVASES
    assert ns["DEFAULT_CANVAS"] == pipeline.DEFAULT_CANVAS
    assert ns["DEFAULT_VISUAL_STYLE"] == pipeline.DEFAULT_VISUAL_STYLE
    # The dashboard and the agent hit different write paths; a refusal that
    # reads differently on each looks like two different problems.
    assert ns["ILLUSTRATED_NEEDS_OPENAI_KEY"] == pipeline.ILLUSTRATED_NEEDS_OPENAI_KEY
    # The resolved column holds a CANVAS, not a register name. If these ever
    # drift back to ("motion_graphics", "stick") the value stops describing
    # what it stores, and auto-on-dark-with-figures becomes unrepresentable.
    assert pipeline.RESOLVED_VISUAL_STYLES == ("dark", "light")


def test_effective_canvas_matches_the_mcp_copy():
    """The constants agreeing is not enough — the helpers are duplicated too,
    and a constants-only test gives false confidence (the lesson the title
    truncator's cross-copy test already learned)."""
    ns = _mcp_block()
    cases = [
        ("auto", ""), ("auto", "light"), ("auto", "dark"),
        ("stick", ""), ("stick", "dark"),
        ("motion_graphics", "light"), ("", ""), ("  auto  ", " light "),
    ]
    for chosen, resolved in cases:
        assert ns["effective_canvas"](chosen, resolved) == \
            pipeline.effective_canvas(chosen, resolved), (chosen, resolved)
    for style in ("stick", "illustrated", "motion_graphics", "auto", "", "nonsense"):
        assert ns["figures_allowed"](style) == pipeline.figures_allowed(style), style
        assert ns["line_art_allowed"](style) == pipeline.line_art_allowed(style), style


def test_line_art_is_narrower_than_figures():
    """"illustrated" HAS figures — generated character artwork — but no line
    art. Collapsing the two tells the reviewer that simple line art is intended
    on an illustrated video, which licenses the one mistake that register
    forbids."""
    assert pipeline.figures_allowed("illustrated") is True
    assert pipeline.line_art_allowed("illustrated") is False
    # Where line art IS the register, or where anything is permitted.
    assert pipeline.line_art_allowed("stick") is True
    assert pipeline.line_art_allowed("auto") is True
    # No figures at all, so no line art either.
    assert pipeline.line_art_allowed("motion_graphics") is False


def test_the_canvas_and_the_figures_are_independent():
    """The coupling this replaced forced a whole image-led video onto a white
    canvas because one beat happened to be about "an attacker". Under auto the
    two are decided separately, which is what lets a dark video carry figures."""
    assert pipeline.effective_canvas("auto", "dark") == "dark"
    assert pipeline.figures_allowed("auto") is True


# ── PATCH /videos/<id> ───────────────────────────────────────────────────────

def _video(client, status="TOPIC_PROPOSED", **extra):
    body = {"topic": "a topic", "strategy": "manual", "producibility_score": 7, **extra}
    vid = json.loads(client.post("/videos", json=body).data)["id"]
    if status != "TOPIC_PROPOSED":
        client.patch(f"/videos/{vid}", json={"status": status})
    return vid


def test_visual_style_is_settable_at_the_topic_checkpoint(client):
    vid = _video(client)
    resp = client.patch(f"/videos/{vid}", json={"visual_style": "stick"})
    assert resp.status_code == 200
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "stick"


def test_the_approving_patch_carries_the_choice(client):
    """The freeze reads the CURRENT status, so the one request that both picks
    the style and approves the topic must still work — that is the only moment
    a human gets to choose."""
    vid = _video(client)
    resp = client.patch(f"/videos/{vid}", json={
        "visual_style": "stick", "status": "TOPIC_APPROVED",
        "onlyIfCurrentStatus": "TOPIC_PROPOSED",
    })
    assert resp.status_code == 200
    body = json.loads(client.get(f"/videos/{vid}").data)
    assert body["visual_style"] == "stick"
    assert body["status"] == "TOPIC_APPROVED"


def test_visual_style_is_frozen_after_the_topic_checkpoint(client):
    vid = _video(client, status="SCRIPT_READY")
    resp = client.patch(f"/videos/{vid}", json={"visual_style": "stick"})
    assert resp.status_code == 409
    assert "TOPIC_PROPOSED" in json.loads(resp.data)["error"]


def test_an_unknown_visual_style_is_rejected(client):
    vid = _video(client)
    resp = client.patch(f"/videos/{vid}", json={"visual_style": "whiteboard"})
    assert resp.status_code == 400
    assert "Invalid visual_style" in json.loads(resp.data)["error"]


def test_resolved_visual_style_is_not_writable_over_http(client):
    """It records what the agent settled on at scene-config time; the dashboard
    has no business overwriting that. Unlisted keys are silently dropped, so
    this asserts the value, not the status code."""
    vid = _video(client)
    client.patch(f"/videos/{vid}", json={"resolved_visual_style": "stick"})
    assert json.loads(client.get(f"/videos/{vid}").data)["resolved_visual_style"] == ""


def test_a_new_video_starts_on_auto(client):
    vid = _video(client)
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "auto"


# ── the project default ──────────────────────────────────────────────────────

def test_a_project_stores_a_default_style(client):
    resp = client.post("/projects", json={
        "id": "dom1", "name": "Domain", "default_visual_style": "stick"})
    assert resp.status_code == 201
    assert json.loads(resp.data)["default_visual_style"] == "stick"


def test_an_unknown_project_default_is_rejected(client):
    resp = client.post("/projects", json={
        "id": "dom2", "name": "Domain", "default_visual_style": "doodle"})
    assert resp.status_code == 400


def test_a_curriculum_video_inherits_the_domain_default(client):
    client.post("/projects", json={
        "id": "dom3", "name": "Domain", "default_visual_style": "stick"})
    vid = _video(client, project_id="dom3", strategy="curriculum")
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "stick"


def test_a_mining_video_in_the_same_domain_does_not_inherit(client):
    client.post("/projects", json={
        "id": "dom4", "name": "Domain", "default_visual_style": "stick"})
    vid = _video(client, project_id="dom4", strategy="mining")
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "auto"


def test_an_explicit_style_beats_the_domain_default(client):
    client.post("/projects", json={
        "id": "dom5", "name": "Domain", "default_visual_style": "stick"})
    vid = _video(client, project_id="dom5", strategy="curriculum",
                 visual_style="motion_graphics")
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "motion_graphics"


# ── illustrated needs an OpenAI key ──────────────────────────────────────────
# The key used to be consulted only by generate_character — after voicing, on a
# video whose style was already frozen — so a missing key surfaced as a stuck
# video with ElevenLabs already paid. These pin the refusal to where the style
# is CHOSEN, and pin that nothing already stored is rewritten.

def _set_openai_key(db_path, value):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('openai_api_key', ?)",
                (value,))
    con.commit()
    con.close()


def _error(resp):
    return json.loads(resp.data)["error"]


def test_illustrated_is_refused_on_patch_without_a_key(client):
    vid = _video(client)
    resp = client.patch(f"/videos/{vid}", json={"visual_style": "illustrated"})
    assert resp.status_code == 400
    assert _error(resp) == pipeline.ILLUSTRATED_NEEDS_OPENAI_KEY
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "auto"


def test_the_refusal_names_the_fix():
    msg = pipeline.ILLUSTRATED_NEEDS_OPENAI_KEY
    assert "OpenAI" in msg and "Settings" in msg and "another visual style" in msg


def test_illustrated_is_refused_on_create_without_a_key(client):
    resp = client.post("/videos", json={"topic": "t", "strategy": "manual",
                                        "producibility_score": 7,
                                        "visual_style": "illustrated"})
    assert resp.status_code == 400
    assert _error(resp) == pipeline.ILLUSTRATED_NEEDS_OPENAI_KEY
    assert json.loads(client.get("/videos").data) == []


def test_illustrated_is_refused_as_a_project_default_without_a_key(client):
    resp = client.post("/projects", json={
        "id": "domk", "name": "Domain", "default_visual_style": "illustrated"})
    assert resp.status_code == 400
    assert _error(resp) == pipeline.ILLUSTRATED_NEEDS_OPENAI_KEY


def test_the_other_styles_need_no_key(client):
    vid = _video(client)
    for style in ("auto", "motion_graphics", "stick"):
        assert client.patch(f"/videos/{vid}", json={"visual_style": style}).status_code == 200


def test_with_a_stored_key_illustrated_is_accepted_everywhere(client, db_path):
    _set_openai_key(db_path, "sk-test")
    vid = _video(client)
    assert client.patch(f"/videos/{vid}", json={"visual_style": "illustrated"}).status_code == 200
    assert client.post("/videos", json={"topic": "t", "strategy": "manual",
                                        "producibility_score": 7,
                                        "visual_style": "illustrated"}).status_code == 201
    assert client.post("/projects", json={
        "id": "domk", "name": "Domain",
        "default_visual_style": "illustrated"}).status_code == 201


def test_a_key_from_the_environment_counts(client, monkeypatch):
    """Same fallback as the MCP server's _openai_key, so the two write paths
    agree on whether a key is stored."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    vid = _video(client)
    assert client.patch(f"/videos/{vid}", json={"visual_style": "illustrated"}).status_code == 200


def test_a_seeded_default_is_kept_but_its_approval_is_refused(client, db_path):
    """The key was there when the domain's default was set and has gone since.
    The seeded value is not rewritten — silently downgrading a deliberate
    choice is how a video ends up not looking like what was asked for — and
    the dashboard's approval, which always carries visual_style, is where it is
    caught: at the topic checkpoint, before any spend."""
    _set_openai_key(db_path, "sk-test")
    client.post("/projects", json={
        "id": "doms", "name": "Domain", "default_visual_style": "illustrated"})
    _set_openai_key(db_path, "")
    vid = _video(client, project_id="doms", strategy="curriculum")
    assert json.loads(client.get(f"/videos/{vid}").data)["visual_style"] == "illustrated"
    resp = client.patch(f"/videos/{vid}", json={
        "visual_style": "illustrated", "status": "TOPIC_APPROVED",
        "onlyIfCurrentStatus": "TOPIC_PROPOSED"})
    assert resp.status_code == 400
    assert json.loads(client.get(f"/videos/{vid}").data)["status"] == "TOPIC_PROPOSED"


def test_resending_a_kept_project_default_is_not_refused(client, db_path):
    """POST /projects is a full replace, so every edit to a domain re-sends its
    stored default. Refusing an unchanged one would block every unrelated edit
    to that domain once the key is removed."""
    _set_openai_key(db_path, "sk-test")
    client.post("/projects", json={
        "id": "domr", "name": "Domain", "default_visual_style": "illustrated"})
    _set_openai_key(db_path, "")
    resp = client.post("/projects", json={
        "id": "domr", "name": "Renamed", "default_visual_style": "illustrated"})
    assert resp.status_code == 201
    assert json.loads(resp.data)["name"] == "Renamed"


# ── the review prompt's style contract ───────────────────────────────────────

def test_the_light_canvas_is_declared_to_the_reviewer():
    block = ai_review._register_block("light")
    assert "white" in block.lower()
    assert "intended" in block.lower()


def test_the_contract_forbids_the_three_false_positives():
    """Each is a real way the unmodified prompt faults this work: flat art as
    low quality, a held pose as broken animation, a white frame as a blank
    frame."""
    block = ai_review._register_block("light", figures=True).lower()
    assert "low quality" in block
    assert "held pose is correct" in block
    assert "blank_frames means black frames" in block


def test_the_figure_clause_is_independent_of_the_canvas():
    """The reason the two are separate arguments: an auto video can be dark AND
    full of held, discretely posed figures. Folding them into one register name
    would either license a defect or flag an intended look."""
    dark_with = ai_review._register_block("dark", figures=True).lower()
    dark_without = ai_review._register_block("dark", figures=False).lower()
    assert "held pose is correct" in dark_with
    assert "held pose is correct" not in dark_without
    assert "deliberately dark" in dark_with and "deliberately dark" in dark_without


def test_the_contract_still_demands_a_real_review():
    """A style contract that excused everything would be worse than none."""
    block = ai_review._register_block("light", figures=True).lower()
    for still_judged in ("legibility", "safe zone", "sync"):
        assert still_judged in block


def test_an_unresolved_canvas_states_no_contract():
    """Guessing is the one unsafe direction: a wrong contract tells the
    reviewer to accept defects the video has no licence to contain. A video
    still on auto that never settled has no canvas to declare."""
    assert ai_review._register_block("") == ""
    assert ai_review._register_block("", figures=True) == ""
    assert ai_review._register_block("stick") == ""
    assert ai_review._register_block(None) == ""


def test_the_register_block_reaches_the_prompt():
    """The block existing is not the same as it being templated in. A prompt
    slot that is never filled fails silently — the review still runs, just
    without the contract."""
    prompt = ai_review._REVIEW_PROMPT.format(
        sampled_fps=10, top=150, bottom=170,
        register_block=ai_review._register_block("light", figures=True),
        scene_config_json="{}",
        reference_text_block="",
    )
    assert "INTENDED VISUAL STYLE" in prompt
    # Ahead of the scene config, so the reviewer has the contract before it
    # has anything to judge against it.
    assert prompt.index("INTENDED VISUAL STYLE") < prompt.index("Current scene-config")


def test_a_dark_canvas_gets_its_own_contract():
    block = ai_review._register_block("dark").lower()
    assert "deliberately dark" in block
    assert "should be moving" in block
