"""Advisory picture checks (TMDEV-215): the first frame shows a subject, and a
turn, re-opening or payoff gets something new on screen near its first word.

They are warnings, never errors: a picture is a judgement, and a check that
blocked a render on a false positive would cost more than the defect. So the
negative controls matter as much as the positives: each style's worked
example (the config its skill tells the agent to copy) must be quiet, and a
video with no formula must get no beat warnings at all.
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import picture_checks as pc
import whiteboard
import server

REPO = pathlib.Path(__file__).resolve().parents[2]
SKILLS = REPO / "agent_files" / "skills"
EXAMPLES = {
    "system_flow": "tubematic-system-flow", "whiteboard": "tubematic-whiteboard",
    "bean_explainer": "tubematic-bean-explainer", "terminal_doc": "tubematic-terminal-doc",
    "storybook_atlas": "tubematic-storybook-atlas", "under_the_hood": "tubematic-under-the-hood",
    "case_file_story": "tubematic-case-file-story",
}


def _example(style: str) -> dict:
    return json.loads((SKILLS / EXAMPLES[style] / "reference" / "example-config.json").read_text())


def _props(config: dict) -> dict:
    return next(iter(config["scenes"][0]["props"].values()))


# ── which style drew a config ─────────────────────────────────────────────────

@pytest.mark.parametrize("style", sorted(EXAMPLES))
def test_each_example_is_read_as_its_own_style(style):
    assert pc.style_of(_example(style)) == style


def test_generated_scenes_are_mixed_and_a_cartoon_is_not_read():
    mixed = {"scenes": [{"type": "generated", "src": "vid/hero", "startFrame": 0}]}
    assert pc.style_of(mixed) == pc.MIXED
    assert pc.style_of({"scenes": [{"src": "CartoonShort"}]}) is None
    assert pc.style_of({}) is None and pc.style_of({"scenes": []}) is None


# ── the first frame ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("style", sorted(EXAMPLES))
def test_every_worked_example_opens_on_a_subject(style):
    # The agent copies these; one that opened on an empty frame would teach it to.
    assert pc.first_frame_warnings(_example(style)) == []


def _sf_late(c):
    _props(c)["boards"][0]["events"][0]["at"] = 20


def _wb_text_first(c):
    items = _props(c)["regions"][0]["items"]
    items[0]["at"], items[1]["at"] = 43, 6
    items[0], items[1] = items[1], items[0]


def _bean_late(c):
    for e in _props(c)["shots"][0]["events"]:
        if e["type"] in ("pose", "prop") and e["frame"] <= 3:
            e["frame"] = 6


def _td_late(c):
    for e in _props(c)["beats"][0]["events"]:
        if e["at"] <= 3:
            e["at"] = 6


def _sb_still(c):
    ch = _props(c)["chapters"][0]
    ch["events"] = [e for e in ch["events"] if e["at"] > 3]


def _uth_no_photo(c):
    _props(c)["plates"][0].pop("image", None)


@pytest.mark.parametrize("style, mutate, fragment", [
    ("system_flow", _sf_late, "headline alone"),
    ("whiteboard", _wb_text_first, "blank board or on words alone"),
    ("bean_explainer", _bean_late, "empty field"),
    ("terminal_doc", _td_late, "empty screen"),
    ("storybook_atlas", _sb_still, "still stage"),
    ("under_the_hood", _uth_no_photo, "dark panel"),
])
def test_a_first_frame_with_no_subject_is_warned(style, mutate, fragment):
    config = _example(style)
    mutate(config)
    warnings = pc.first_frame_warnings(config)
    assert len(warnings) == 1 and fragment in warnings[0] and warnings[0].startswith("First frame:")


def test_a_mixed_video_is_left_to_the_text_audit():
    mixed = {"scenes": [{"type": "generated", "src": "vid/title-card", "startFrame": 0}]}
    assert pc.first_frame_warnings(mixed) == []


# ── segment roles ─────────────────────────────────────────────────────────────

ROLES = {"Wrong suspect 1": "reopen", "Turn": "turn", "Root cause": "payoff"}


def _segments(beats, step=100):
    tl = [{"id": f"seg-{i}", "startFrame": i * step, "endFrame": (i + 1) * step} for i in range(len(beats))]
    script = [{"id": f"seg-{i}", "voice": f"Sentence {i} has <respell as=\"x\">six</respell> or more words "
               "in it.", "visual": "v", "beat": b} for i, b in enumerate(beats)]
    return tl, script


def test_a_beat_owes_its_change_once_where_it_starts():
    tl, script = _segments(["Symptom", "Wrong suspect 1", "Turn", "Mechanism", "Mechanism", "Root cause",
                            "Root cause"])
    out = pc.annotate_segments(tl, script, ROLES)
    assert [s["role"] for s in out] == ["opening", "reopen", "turn", "", "", "payoff", ""]
    assert out[1]["beat"] == "Wrong suspect 1" and out[1]["startFrame"] == 100
    assert "role" not in tl[0]  # the inputs are not changed


def test_segments_without_beats_or_without_a_formula_owe_nothing_past_the_opening():
    tl, script = _segments(["", "", ""])
    assert [s["role"] for s in pc.annotate_segments(tl, script, ROLES)] == ["opening", "", ""]
    tl, script = _segments(["Symptom", "Turn", "Root cause"])
    assert [s["role"] for s in pc.annotate_segments(tl, script, {})] == ["opening", "", ""]
    assert pc.annotate_segments([], script, ROLES) == []


# ── a visible change on each turn, re-opening and payoff ──────────────────────

def _mixed(starts, total=700):
    return {"totalFrames": total, "scenes": [
        {"type": "generated", "src": f"vid/s{i}", "startFrame": s,
         "durationInFrames": (starts[i + 1] if i + 1 < len(starts) else total) - s}
        for i, s in enumerate(starts)]}


def test_a_mixed_video_that_cuts_on_every_beat_is_quiet():
    tl, script = _segments(["Symptom", "Wrong suspect 1", "Turn", "Mechanism", "Root cause"])
    assert pc.check(_mixed([0, 100, 200, 300, 400]), tl, script, ROLES, 30) == []


def test_a_turn_inside_a_running_scene_is_warned_with_where_and_what():
    tl, script = _segments(["Symptom", "Wrong suspect 1", "Turn", "Mechanism", "Root cause"])
    # the turn (frame 200) and the payoff (frame 400) were merged into the scenes before them
    warnings = pc.check(_mixed([0, 100, 300]), tl, script, ROLES, 30)
    assert len(warnings) == 2
    turn, payoff = warnings
    assert turn.startswith("The turn at 0:06 (segment seg-2, beat \"Turn\"")
    assert "\"Sentence 2 has six or more...\"" in turn  # markup stripped, quote clipped
    assert "frame 200" in turn and "new scene" in turn
    assert payoff.startswith("The payoff at 0:13")


def test_a_cut_just_before_the_word_or_shortly_after_it_counts():
    tl, script = _segments(["Symptom", "Turn", "Root cause"])
    roles = {"Turn": "turn", "Root cause": "payoff"}
    lead, late = 100 - pc.CHANGE_LEAD, 200 + pc.CHANGE_WINDOW
    assert pc.check(_mixed([0, lead, late]), tl, script, roles, 30) == []
    too_early, too_late = 100 - pc.CHANGE_LEAD - 1, 200 + pc.CHANGE_WINDOW + 1
    assert len(pc.check(_mixed([0, too_early, too_late]), tl, script, roles, 30)) == 2


def test_no_formula_means_no_beat_warnings():
    tl, script = _segments(["Symptom", "Wrong suspect 1", "Turn", "Mechanism", "Root cause"])
    assert pc.check(_mixed([0, 600]), tl, script, {}, 30) == []


def test_a_data_driven_change_is_read_from_the_style_data():
    config = _example("system_flow")
    frames = set(pc.change_frames("system_flow", config))
    boards = _props(config)["boards"]
    assert {b["startFrame"] for b in boards} <= frames
    chips = {e["at"] for b in boards for e in b["events"] if e["type"] == "chip"}
    others = {e["at"] for b in boards for e in b["events"] if e["type"] != "chip"}
    assert not (chips - others) & frames  # a chip alone changes too little to count
    quiet = max(frames) + 200
    tl = [{"id": "seg-0", "startFrame": 0, "endFrame": 10},
          {"id": "seg-1", "startFrame": sorted(frames)[3], "endFrame": quiet},
          {"id": "seg-2", "startFrame": quiet, "endFrame": quiet + 50}]
    script = [{"id": f"seg-{i}", "voice": "w", "visual": "v", "beat": b}
              for i, b in enumerate(["Symptom", "Turn", "Root cause"])]
    warnings = pc.check(config, tl, script, {"Turn": "turn", "Root cause": "payoff"}, 30)
    assert len(warnings) == 1 and warnings[0].startswith("The payoff") and "new board" in warnings[0]


@pytest.mark.parametrize("style", sorted(EXAMPLES))
def test_every_style_reports_its_cuts_as_changes(style):
    config = _example(style)
    frames = pc.change_frames(style, config)
    assert frames and 0 in frames, style
    assert pc._CHANGE_FIX[style]


def test_a_whiteboard_doodle_counts_when_the_marker_starts_it():
    config = _example("whiteboard")
    regions = _props(config)["regions"]
    frames = pc.change_frames("whiteboard", config)
    assert -whiteboard.TIMING["openLead"] in frames  # the opening doodle is already being drawn at frame 0
    doodle = next(it for r in regions[1:] for it in r["items"] if it["kind"] == "doodle")
    assert doodle["at"] + 12 in frames  # its word is not the change; the marker starting it is


def test_malformed_data_is_skipped_not_raised():
    assert pc.change_frames("whiteboard", {"scenes": [{"src": "Whiteboard", "props": {"whiteboard": 3}}]}) == []
    assert pc.first_frame_warnings({"scenes": [{"src": "SystemFlow", "props": {}}]})


# ── through validate_job ──────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_validate_job_adds_the_picture_warnings_after_the_audit(tmp_path, monkeypatch):
    import text_audit
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "t.db")
    server._init_db()
    jobs = tmp_path / "jobs"
    monkeypatch.setattr(server, "JOBS_DIR", jobs)
    monkeypatch.setattr(text_audit, "audit_text_layout", lambda *a, **k: ["measured"])
    monkeypatch.setattr("shutil.which", lambda name: None)   # no npx: the typecheck is skipped
    repo = tmp_path / "repo"
    monkeypatch.setattr(server, "REPO_ROOT", repo)
    monkeypatch.setattr(server, "SCENES_DIR", repo / "remotion" / "src" / "scenes" / "generated")
    monkeypatch.setattr(server, "INSTALLED_DIR", repo / "remotion" / "src" / "scenes" / "installed")
    (repo / "remotion" / "src" / "scenes" / "installed").mkdir(parents=True)
    vid = "vid_pic"
    gen = repo / "remotion" / "src" / "scenes" / "generated" / vid
    gen.mkdir(parents=True)
    for name in ("a", "b"):
        (gen / f"{name}.tsx").write_text("export default () => null;")
    segments = [{"id": "seg-1", "voice": "One two three.", "visual": "x", "beat": "The symptom"},
                {"id": "seg-2", "voice": "Four five six.", "visual": "y", "beat": "Wrong suspect 1"},
                {"id": "seg-3", "voice": "Seven eight nine.", "visual": "z", "beat": "Root cause"}]
    with server._conn() as con:
        con.execute("INSERT INTO videos (id, project_id, topic, status, created_at, updated_at, "
                    "script_segments, formula_id, voice_file_path, timeline_path, scene_config_path) "
                    "VALUES (?, NULL, 't', 'VOICE_READY', ?, ?, ?, ?, 'set', 'set', 'set')",
                    (vid, _now(), _now(), json.dumps(segments), "broken-expectation"))
    (jobs / vid).mkdir(parents=True)
    timeline = {"totalFrames": 300, "fps": 30, "audioDurationSeconds": 10, "words": [],
                "segments": [{"id": "seg-1", "startFrame": 0, "endFrame": 100},
                             {"id": "seg-2", "startFrame": 100, "endFrame": 200},
                             {"id": "seg-3", "startFrame": 200, "endFrame": 300}]}
    config = {"totalFrames": 300, "fps": 30, "scenes": [
        {"type": "generated", "src": f"{vid}/a", "startFrame": 0, "durationInFrames": 200},
        {"type": "generated", "src": f"{vid}/b", "startFrame": 200, "durationInFrames": 100}]}
    (jobs / vid / "scene-config.json").write_text(json.dumps(config))
    (jobs / vid / "timeline.json").write_text(json.dumps(timeline))
    (jobs / vid / "audio.mp3").write_bytes(b"\x00" * (60 * 1024))

    result = server.validate_job(vid)

    assert result["passed"] is True, result["errors"]
    assert result["warnings"][0] == "measured"
    assert len(result["warnings"]) == 2 and result["warnings"][1].startswith("The re-opening at 0:03")
