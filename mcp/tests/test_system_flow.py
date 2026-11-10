"""System Flow (TMDEV-196): the scene-config checks that keep an unattended
agent from shipping an overcrowded or mistimed diagram, their agreement with
the renderer's contract.ts, and their place in write_scene_config and the text
audit.

Every refusal below is one the renderer cannot survive gracefully: a fourth
node in a row makes labels unreadable at the pull-back, a cycle has no rows at
all, an edge drawn before its source lands points out of nothing, and a long
stretch with no change is the static frame viewers scroll past.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import server
import system_flow as sf
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_TS = REPO / "renderer/remotion/src/scenes/installed/systemFlow/contract.ts"
ICONS_TS = REPO / "renderer/remotion/src/scenes/installed/systemFlow/icons.ts"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/system_flow_contract.json").read_text())
EXAMPLE = json.loads((REPO / "agent_files/skills/tubematic-system-flow/reference/example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REPO / "agent_files/skills/tubematic-system-flow/reference/example-timeline.json").read_text())
# The example's narration: every word's start frame.
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
ICONS = tvs.pack("system_flow")["extra"]["icons"]


def _ts_block(name: str) -> dict:
    src = CONTRACT_TS.read_text()
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", src, re.S).group(1)
    return {k: float(v) if "." in v else int(v)
            for k, v in re.findall(r"^\s*(\w+):\s*([\d.]+),", body, re.M)}


# ── agreement with the renderer ──────────────────────────────────────────────

def test_the_limits_and_timings_match_the_renderer():
    assert _ts_block("LIMITS") == sf.LIMITS
    assert _ts_block("TIMING") == sf.TIMING


def test_the_tones_and_event_types_match_the_renderer():
    src = CONTRACT_TS.read_text()
    for name, values in (("TONES", sf.TONES), ("EVENT_TYPES", sf.EVENT_TYPES)):
        body = re.search(rf"export const {name} = \[(.*?)\] as const;", src).group(1)
        assert tuple(re.findall(r'"(\w+)"', body)) == values, name


def test_labels_wrap_the_same_way():
    for case in CASES["wrap_label"]:
        assert sf.wrap_label(case["label"]) == case["lines"], case["label"]


def test_rows_are_counted_the_same_way():
    for case in CASES["rows"]:
        assert sf.compute_rows(case["nodes"], [tuple(e) for e in case["edges"]]) == case["rows"]


def test_the_pack_lists_exactly_the_icons_the_renderer_draws():
    drawn = set(re.findall(r"^  (\w+): \[", ICONS_TS.read_text(), re.M))
    assert drawn == set(ICONS)


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None):
    return sf.check(config or EXAMPLE, 30, WORD_STARTS, ICONS)


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(cfg["scenes"][0]["props"]["systemFlow"]["boards"])
    return cfg


def test_the_skills_worked_example_passes():
    """The skill teaches from this file; a skill example the validator refuses
    teaches the agent to be refused."""
    assert sf.check_scene_use("system_flow", EXAMPLE["scenes"]) == ""
    assert _check() == []


def test_only_a_system_flow_video_may_use_the_scene():
    assert "visual_style is system_flow" in sf.check_scene_use("stick", EXAMPLE["scenes"])
    assert sf.check_scene_use("stick", [{"src": "intro", "source": "generated"}]) == ""


def test_a_system_flow_video_is_one_scene():
    two = EXAMPLE["scenes"] + [{"type": "generated", "src": "x", "startFrame": 0, "durationInFrames": 10}]
    assert "exactly one scene" in sf.check_scene_use("system_flow", two)
    other = [{"type": "generated", "src": "intro", "startFrame": 0, "durationInFrames": 600}]
    assert "exactly one scene" in sf.check_scene_use("system_flow", other)


@pytest.mark.parametrize("mutate, fragment", [
    # four side by side: the labels no longer fit the frame at the pull-back
    (lambda b: (b[0]["nodes"].append({"id": "web3", "label": "Web 3", "icon": "server"}),
                b[0]["edges"].append({"from": "lb", "to": "web3"}),
                b[0]["events"].append({"type": "node", "node": "web3", "at": 210}),
                b[0]["edges"].append({"from": "lb", "to": "cache"}),
                b[0]["nodes"].append({"id": "cache", "label": "Cache", "icon": "cache"}),
                b[0]["events"].append({"type": "node", "node": "cache", "at": 212})), "at most 3 side by side"),
    (lambda b: (b[1]["nodes"].append({"id": "db", "label": "Database", "icon": "database"}),
                b[1]["edges"].append({"from": "server", "to": "db"}),
                b[1]["events"].append({"type": "node", "node": "db", "at": 520})), "rows deep"),
    (lambda b: b[1]["edges"].append({"from": "server", "to": "attacker"}), "cycle"),
    (lambda b: b[0]["nodes"][0].update(icon="rocket"), "is not one of"),
    (lambda b: b[0]["nodes"][1].update(label="Recursive DNS Resolver Pool Cache"), "does not fit"),
    (lambda b: b[0]["nodes"][1].update(id="DNS"), "lowercase"),
    (lambda b: b[0]["events"].__setitem__(1, {"type": "edge", "edge": "browser>dns", "at": 14}), "before 'browser' has landed"),
    (lambda b: b[0]["events"].__setitem__(3, {"type": "packet", "edge": "browser>dns", "at": 35}), "before the edge has finished"),
    (lambda b: b[0]["events"].append({"type": "focus", "node": "web2", "at": 100}), "before it enters"),
    (lambda b: b[0]["events"].append({"type": "chip", "edge": "lb>web2", "at": 260, "text": "x" * 30}), "chip at 260 text"),
    (lambda b: b[0]["events"].append({"type": "packet", "edge": "lb>web2", "at": 260, "tone": "loud"}), "tone"),
    (lambda b: b[0]["events"].append({"type": "packet", "edge": "lb>web2", "at": 305}), "packet event at 305 needs 20 frames"),
    (lambda b: b[0]["events"].append({"type": "wave", "at": 100}), "needs a type"),
    (lambda b: b[0]["events"].append({"type": "node", "node": "dns", "at": 60}), "enters twice"),
    (lambda b: b[0]["events"].pop(4), None),  # dropping one focus keeps it valid
    (lambda b: b[1]["events"].__setitem__(0, {"type": "node", "node": "attacker", "at": 900}), "inside the board"),
    (lambda b: b[1].update(startFrame=333), "not on a word"),
    (lambda b: b[1].update(headline="A" * 41), "headline is 41"),
    (lambda b: b[1]["nodes"].append({"id": "lonely", "label": "Lonely", "icon": "user"}), "connected"),
])
def test_a_bad_diagram_is_refused_with_a_reason(mutate, fragment):
    errs = _check(_with(mutate))
    if fragment is None:
        assert errs == []
    else:
        assert any(fragment in e for e in errs), errs


def test_a_node_that_never_enters_is_refused():
    errs = _check(_with(lambda b: b[0]["events"].pop(0)))
    assert any("'browser' never enters" in e for e in errs), errs


def test_a_long_still_stretch_is_refused():
    """Nothing new for more than 3.5 s reads as a frozen frame."""
    def thin(b):
        b[1]["events"] = [e for e in b[1]["events"] if e["at"] <= 420 or e["type"] in ("node", "edge")]
        for e in b[1]["events"]:
            if e.get("edge") == "firewall>server" and e["type"] == "edge":
                e["at"] = 425
            if e.get("node") == "server":
                e["at"] = 430  # then nothing from 430 to the end at 536: 106 frames
    errs = _check(_with(thin))
    assert any("nothing changes on screen" in e for e in errs), errs


def test_errors_are_capped_so_the_message_stays_readable():
    def wreck(b):
        for board in b:
            for n in board["nodes"]:
                n["icon"] = "nope"
    assert len(_check(_with(wreck))) <= sf.MAX_ERRORS


def test_board_windows():
    assert sf.board_windows(EXAMPLE) == [(0, 326), (326, 536)]
    assert sf.board_windows({"scenes": []}) == []


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make(video_id, style="system_flow", with_timeline=True):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'how a request travels', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        if with_timeline:
            d = tmp_path / "jobs" / video_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_system_flow_config_is_written_with_the_styles_captions(make_video):
    vid = make_video("vid_sf1")
    cfg = copy.deepcopy(EXAMPLE)
    assert "subtitles" not in cfg  # the skill tells the agent to leave it out
    result = server.write_scene_config(vid, cfg)
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == tvs.pack("system_flow")["captions"]
    assert written["canvas"] == "dark"


def test_an_overcrowded_diagram_is_refused_before_anything_is_written(make_video):
    vid = make_video("vid_sf2")
    cfg = _with(lambda b: b[0]["nodes"][0].update(icon="rocket"))
    result = server.write_scene_config(vid, cfg)
    assert "System Flow diagram has problems" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_system_flow_scene(make_video):
    vid = make_video("vid_sf3", style="stick")
    cfg = copy.deepcopy(EXAMPLE)
    del cfg["canvas"]  # so the scene rule refuses it, not the canvas rule
    result = server.write_scene_config(vid, cfg)
    assert "visual_style is system_flow" in result["error"]


def test_a_system_flow_video_cannot_be_built_from_other_scenes(make_video):
    vid = make_video("vid_sf4")
    cfg = {"totalFrames": 600, "fps": 30, "sfx": [],
           "scenes": [{"type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 600}]}
    assert "exactly one scene" in server.write_scene_config(vid, cfg)["error"]


def test_the_word_check_is_skipped_without_a_timeline(make_video):
    vid = make_video("vid_sf5", with_timeline=False)
    cfg = _with(lambda b: b[1].update(startFrame=333))
    for e in cfg["scenes"][0]["props"]["systemFlow"]["boards"][1]["events"]:
        e["at"] = max(e["at"], 336)
    assert "error" not in server.write_scene_config(vid, cfg)


# ── the text audit samples every board ───────────────────────────────────────

def test_the_text_audit_samples_each_board():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    assert len(passes) == 2
    assert passes[0]["first"] == text_audit.ENTRANCE_ALLOWANCE_FRAMES
    assert passes[1]["first"] == 326 + text_audit.ENTRANCE_ALLOWANCE_FRAMES
    for p, (start, end) in zip(passes, sf.board_windows(EXAMPLE)):
        assert p["count"] == text_audit.SAMPLES_PER_SCENE
        assert start <= p["first"] and p["first"] + p["step"] * (p["count"] - 1) < end


def test_a_system_flow_scene_of_another_type_is_refused():
    """The renderer loads SystemFlow only as a generated-type entry; any other
    type would render nothing and still pass the diagram checks."""
    scenes = copy.deepcopy(EXAMPLE["scenes"])
    scenes[0]["type"] = "TextReveal"
    assert "exactly one scene" in sf.check_scene_use("system_flow", scenes)
    scenes[0]["type"] = "generated"
    scenes[0]["source"] = "generated"
    assert "exactly one scene" in sf.check_scene_use("system_flow", scenes)
    assert "visual_style is system_flow" in sf.check_scene_use("stick", scenes)


@pytest.mark.parametrize("event, fragment", [
    ({"type": "node", "node": "web2", "at": 310}, "node event at 310 needs 31 frames"),
    ({"type": "edge", "edge": "lb>web2", "at": 300}, "edge event at 300 needs 30 frames"),
    ({"type": "chip", "edge": "lb>web2", "at": 300, "text": "200 OK"}, "chip event at 300 needs 30 frames"),
])
def test_an_event_that_cannot_be_seen_before_the_board_fades_is_refused(event, fragment):
    """The board fades out over its last 6 frames (frame 320 on in the
    example's first board); an entrance finishing at the cut is never seen."""
    def late(b):
        b[0]["events"] = [e for e in b[0]["events"] if e.get("node") != event.get("node")
                          and e.get("edge") != event.get("edge")] + [event]
    errs = _check(_with(late))
    assert any(fragment in e for e in errs), errs


def test_the_stillness_rule_uses_the_narrations_fps_not_the_configs(make_video):
    """A config claiming 300 fps would make 3.5 s ten times longer."""
    vid = make_video("vid_sf6")
    cfg = copy.deepcopy(EXAMPLE)
    cfg["fps"] = 300
    boards = cfg["scenes"][0]["props"]["systemFlow"]["boards"]
    boards[1]["events"] = [e for e in boards[1]["events"] if e["at"] <= 420 or e["type"] in ("node", "edge")]
    for e in boards[1]["events"]:
        if e.get("edge") == "firewall>server" and e["type"] == "edge":
            e["at"] = 425
        if e.get("node") == "server":
            e["at"] = 430
    assert "nothing changes on screen" in server.write_scene_config(vid, cfg)["error"]


def test_the_last_board_has_no_fade_out():
    """Nothing follows the last board, so an event may run to the final frame."""
    def late(b):
        b[1]["events"].append({"type": "focus", "node": "server", "at": 536 - 15})
    assert _check(_with(late)) == []
