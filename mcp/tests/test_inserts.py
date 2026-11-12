"""Insert scenes (TMDEV-224): the checks a config's `inserts` must pass, what
write_scene_config fills into them, and the tools around the decision
(choose_inserts, get_video's insert_routing, update_video's insert marks).

The limits are the user's: an insert lasts about 8 seconds at most, never
comes back to back, is never the first or the last scene, and inserts take at
most a third of the video. Every refusal below is one that would otherwise
reach a render: an insert over the opening or the payoff takes the main
style's job, and an insert over words the script never marked shows a diagram
or a string the narration is not about.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest

import inserts as ins
import server
from tubematic_core import inserts as tinserts
from tubematic_core import visual_styles as tvs

FPS = 30
TOTAL = 1500
# Five segments of 10 s, one word every 10 frames.
SEGMENTS = [{"id": f"s{i + 1}", "startFrame": i * 300, "endFrame": i * 300 + 290} for i in range(5)]
WORDS = [{"word": f"w{k}", "startFrame": k * 10, "endFrame": k * 10 + 8} for k in range(150)]
WORD_STARTS = [w["startFrame"] for w in WORDS]
ICONS = tvs.pack("system_flow")["extra"]["icons"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _board(start=600):
    return {"startFrame": start, "headline": "A request travels", "pill": "STEP 1",
            "nodes": [{"id": "client", "label": "Browser", "icon": "browser"},
                      {"id": "app", "label": "Server", "icon": "server"}],
            "edges": [{"from": "client", "to": "app"}],
            "events": [{"type": "node", "node": "client", "at": start},
                       {"type": "node", "node": "app", "at": start + 40},
                       {"type": "edge", "edge": "client>app", "at": start + 60},
                       {"type": "packet", "edge": "client>app", "at": start + 80},
                       {"type": "focus", "node": "app", "at": start + 140},
                       {"type": "chip", "edge": "client>app", "at": start + 190, "text": "200 OK"}]}


def _sf_insert(start=600, dur=240):
    return {"style": "system_flow", "startFrame": start, "durationInFrames": dur,
            "props": {"systemFlow": {"boards": [_board(start)]}}}


def _td_insert(start=600, dur=240):
    return {"style": "terminal_doc", "startFrame": start, "durationInFrames": dur,
            "props": {"terminalDoc": {"beats": [{"start": start, "events": [
                {"type": "word", "at": start, "id": "ctx", "slot": "context", "text": "WHAT IS STORED",
                 "tone": "grey"},
                {"type": "word", "at": start + 20, "id": "pw", "slot": "a", "text": "SUNSHINE", "size": "l"},
                {"type": "glow", "at": start + 90, "target": "pw", "tone": "red"},
                {"type": "word", "at": start + 150, "id": "h", "slot": "c", "text": "A941A4C4", "size": "m"},
            ]}]}}}


def _config(*entries, scenes=None):
    return {"totalFrames": TOTAL, "fps": FPS, "canvas": "light",
            "scenes": scenes or [{"type": "generated", "src": "vid/Main", "startFrame": 0,
                                  "durationInFrames": TOTAL}],
            "inserts": list(entries)}


def _sf_check(e):
    import system_flow
    return system_flow.check_insert(e, FPS, WORD_STARTS, ICONS)


def _td_check(e):
    import terminal_doc
    return terminal_doc.check_insert(e, FPS, WORD_STARTS, [w["word"] for w in WORDS])


def _check(config, marks=None, mode="auto", allowed=("system_flow", "terminal_doc"), segments=None,
           host=None):
    return ins.check(config, fps=FPS, word_starts=WORD_STARTS, segments=segments or SEGMENTS,
                     marks={"s3": "system_flow"} if marks is None else marks, insert_mode=mode,
                     allowed=None if allowed is None else list(allowed),
                     host=host or {"host": True, "transition": "wipe"}, host_message="no inserts here",
                     style_checks={"system_flow": _sf_check, "terminal_doc": _td_check})


# ── the window rules ─────────────────────────────────────────────────────────

def test_a_sound_insert_passes():
    assert _check(_config(_sf_insert())) == []
    assert _check(_config(_td_insert()), marks={"s3": "terminal_doc"}) == []


def test_no_inserts_and_no_marks_pass():
    assert _check(_config(), marks={}) == []


@pytest.mark.parametrize("entry, fragment", [
    (_sf_insert(dur=300), "at most 9 s"),
    (_sf_insert(dur=45), "at least 2 s"),
    (_sf_insert(start=605), "not on a word"),
    ({**_sf_insert(), "style": "whiteboard"}, "not an insert style"),
    ({**_sf_insert(), "extra": 1}, "unknown keys"),
    (_sf_insert(start=1450, dur=60), "video (0-1500)"),
])
def test_a_bad_window_is_refused(entry, fragment):
    errors = _check(_config(entry))
    assert any(fragment in e for e in errors), errors


def test_an_insert_must_sit_in_a_segment_marked_with_its_style():
    errors = _check(_config(_sf_insert()), marks={"s3": "terminal_doc"})
    assert any("not one of this video's insert styles" in e or "marked as a system_flow" in e
               for e in errors), errors
    errors = _check(_config(_sf_insert(start=900)))
    assert any("does not start inside a segment the script marked" in e for e in errors)


def test_a_marked_segment_needs_an_insert():
    errors = _check(_config(), marks={"s3": "system_flow"})
    assert any("no insert covers it" in e for e in errors)


def test_an_insert_never_runs_into_the_next_segment():
    errors = _check(_config(_sf_insert(start=700, dur=240)))
    assert any("runs past its segment" in e for e in errors)


def test_the_first_and_last_segments_belong_to_the_main_style():
    errors = _check(_config(_sf_insert(start=0)), marks={"s1": "system_flow"})
    assert any("first segment" in e for e in errors)
    errors = _check(_config(_sf_insert(start=1200)), marks={"s5": "system_flow"})
    assert any("last segment" in e for e in errors)


def test_an_insert_never_covers_the_payoffs_first_word():
    segments = [dict(s) for s in SEGMENTS]
    segments[2]["role"] = "payoff"
    errors = _check(_config(_sf_insert()), segments=segments)
    assert any("payoff" in e for e in errors)
    segments[2]["role"] = ""
    segments[3]["role"] = "payoff"
    assert _check(_config(_sf_insert()), segments=segments) == []


def test_inserts_come_with_main_style_between_them():
    segments = [{"id": "a", "startFrame": 0, "endFrame": 290}, {"id": "b", "startFrame": 300, "endFrame": 590},
                {"id": "c", "startFrame": 600, "endFrame": 890}, {"id": "d", "startFrame": 900, "endFrame": 1190},
                {"id": "e", "startFrame": 1200, "endFrame": 1490}]
    two = _config(_sf_insert(start=300, dur=240), _sf_insert(start=560, dur=240))
    errors = _check(two, marks={"b": "system_flow", "c": "system_flow"}, segments=segments)
    assert any("overlap" in e or "back to back" in e for e in errors), errors


def test_inserts_take_at_most_a_third_of_the_video():
    short = {**_config(_sf_insert(start=300, dur=240), _sf_insert(start=900, dur=240)), "totalFrames": 1200}
    segments = [{"id": "a", "startFrame": 0, "endFrame": 290}, {"id": "b", "startFrame": 300, "endFrame": 590},
                {"id": "c", "startFrame": 600, "endFrame": 890}, {"id": "d", "startFrame": 900, "endFrame": 1140},
                {"id": "e", "startFrame": 1150, "endFrame": 1199}]
    errors = _check(short, marks={"b": "system_flow", "d": "system_flow"}, segments=segments)
    assert any("a third" in e for e in errors), errors


def test_a_main_scene_never_starts_under_an_insert():
    scenes = [{"type": "generated", "src": "vid/A", "startFrame": 0, "durationInFrames": 700},
              {"type": "generated", "src": "vid/B", "startFrame": 700, "durationInFrames": 800}]
    errors = _check(_config(_sf_insert(), scenes=scenes))
    assert any("Scene 2 starts at frame 700, inside insert 1" in e for e in errors)


def test_the_settings_and_the_host_can_forbid_inserts():
    assert "None" in _check(_config(_sf_insert()), mode="none")[0]
    assert _check(_config(_sf_insert()), host={"host": False}) == ["no inserts here"]
    errors = _check(_config(_sf_insert()), allowed=("terminal_doc",))
    assert any("not one of this video's insert styles (terminal_doc)" in e for e in errors)


def test_the_insert_styles_own_checks_run_over_the_window():
    bad = _sf_insert()
    bad["props"]["systemFlow"]["boards"][0]["startFrame"] = 630
    errors = _check(_config(bad))
    assert any("first board must start at the insert's first frame (600)" in e for e in errors), errors
    td = _td_insert()
    td["props"]["terminalDoc"]["customMoves"] = [{"id": "x", "src": "vid/move-x", "frames": 30}]
    td["props"]["terminalDoc"]["skin"] = "crt"
    errors = _check(_config(td), marks={"s3": "terminal_doc"})
    assert any("only the shipped moves" in e for e in errors)
    assert any("Leave skin out" in e for e in errors)


def test_an_insert_holds_few_boards():
    e = _sf_insert()
    e["props"]["systemFlow"]["boards"] = [_board(600), _board(660), _board(720), _board(780)]
    assert any("at most 3 boards" in x for x in _check(_config(e)))


# ── the caption shift, the fill and the mascot ───────────────────────────────

def test_captions_low_in_the_frame_leave_the_insert_where_it_is_or_lift_it_a_little():
    assert ins.shift_for("system_flow", {"position": 0.78, "fontSize": 62}) == 0
    lifted = ins.shift_for("terminal_doc", {"position": 0.72, "fontSize": 72})
    assert -110 <= lifted < 0


def test_captions_at_the_top_push_the_insert_down_and_it_stays_in_the_frame():
    sh = ins.shift_for("terminal_doc", {"position": 0.19, "fontSize": 64})
    top, bottom = ins.BLOCKS["terminal_doc"]
    cap_top, cap_bottom = ins.caption_box({"position": 0.19, "fontSize": 64})
    assert top + sh >= cap_bottom + ins.CAPTION_GAP
    assert bottom + sh <= ins.H - ins.EDGE


def test_no_captions_no_shift():
    assert ins.shift_for("system_flow", {"enabled": False, "position": 0.19}) == 0


def test_fill_names_the_scene_the_palette_and_the_transition():
    cfg = ins.fill(_config(_sf_insert()), canvas="light", transition="wipe")
    entry = cfg["inserts"][0]
    assert (entry["src"], entry["palette"], cfg["insertTransition"]) == ("SystemFlow", "light", "wipe")
    assert "shift" in entry
    empty = ins.fill({**_config(), "insertTransition": "dip"}, canvas="dark", transition="dip")
    assert "inserts" not in empty and "insertTransition" not in empty


def test_a_mascot_cue_never_lands_under_an_insert():
    assert ins.cue_errors([{"frame": 650}], [(600, 840)])
    assert ins.cue_errors([{"frame": 840}, {"frame": 10}], [(600, 840)]) == []


def test_the_blocks_match_the_renderers_layout():
    camera = (pathlib.Path(__file__).resolve().parents[2]
              / "renderer/remotion/src/scenes/installed/systemFlow/camera.ts").read_text()
    assert "y1: 0.69 * H" in camera and round(0.69 * 1920) == ins.BLOCKS["system_flow"][1]


# ── write_scene_config ───────────────────────────────────────────────────────

@pytest.fixture
def video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "_scene_claims", {})
    server._init_db()

    def make(vid="vid_ins", style="stick", marks=None, mode="auto", allowed='["system_flow"]',
             status="VOICE_READY"):
        marks = {"s3": "system_flow"} if marks is None else marks
        segs = [{"id": s["id"], "voice": " ".join(f"w{k}" for k in range(i * 30, i * 30 + 30)),
                 "visual": "v", **({"insert": marks[s["id"]]} if s["id"] in marks else {})}
                for i, s in enumerate(SEGMENTS)]
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, topic, status, visual_style, script_segments, insert_mode, "
                "insert_styles, created_at, updated_at) VALUES (?, 't', ?, ?, ?, ?, ?, ?, ?)",
                (vid, status, style, json.dumps(segs), mode, allowed, _now(), _now()))
        d = tmp_path / "jobs" / vid
        d.mkdir(parents=True, exist_ok=True)
        (d / "timeline.json").write_text(json.dumps(
            {"totalFrames": TOTAL, "fps": FPS, "words": WORDS, "segments": SEGMENTS}))
        return vid

    return make


def test_write_scene_config_fills_the_insert_and_writes_it(video):
    vid = video()
    result = server.write_scene_config(vid, copy.deepcopy(_config(_sf_insert())))
    assert "error" not in result, result
    assert result["insert_count"] == 1
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["insertTransition"] == tvs.pack("stick")["inserts"]["transition"]
    assert written["inserts"][0]["src"] == "SystemFlow"
    assert written["inserts"][0]["palette"] == "light"  # Stick's canvas


def test_write_scene_config_refuses_bad_inserts_with_their_reasons(video):
    vid = video()
    result = server.write_scene_config(vid, copy.deepcopy(_config(_sf_insert(dur=300))))
    assert "The insert scenes have problems" in result["error"]


def test_a_marked_segment_left_without_its_insert_is_refused(video):
    vid = video()
    result = server.write_scene_config(vid, copy.deepcopy(_config()))
    assert "no insert covers it" in result["error"]


def _row(vid):
    with server._conn() as con:
        return con.execute("SELECT * FROM videos WHERE id = ?", (vid,)).fetchone()


def test_cartoon_3d_takes_no_inserts(video):
    vid = video(style="cartoon_3d", marks={})
    errors = server._insert_errors(vid, _row(vid), _config(_sf_insert()))
    assert errors == [tvs.PACKS["cartoon_3d"]["messages"]["inserts"]]


def test_a_legacy_whole_video_system_flow_video_takes_no_inserts(video):
    vid = video(style="system_flow", marks={}, allowed="[]")
    errors = server._insert_errors(vid, _row(vid), _config(_sf_insert()))
    assert errors and "made before System Flow became an insert style" in errors[0]


def test_a_scene_component_of_an_insert_style_is_refused_in_scenes(video):
    vid = video(marks={})
    cfg = _config()
    cfg["scenes"] = [{"type": "generated", "source": "installed", "src": "SystemFlow", "startFrame": 0,
                      "durationInFrames": TOTAL, "props": {"systemFlow": {"boards": [_board(0)]}}}]
    assert "System Flow is an insert style" in server.write_scene_config(vid, cfg)["error"]


# ── choose_inserts and get_video ─────────────────────────────────────────────

def test_choose_inserts_records_the_styles_once(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={}, allowed="")
    assert server.get_video(vid)["insert_routing"]["decided"] is False
    out = server.choose_inserts(vid, ["system_flow"], "The request's path is a diagram beat.")
    assert out["insert_styles"] == ["system_flow"]
    video_ = server.get_video(vid)
    assert video_["insert_styles"] == ["system_flow"]
    assert video_["insert_routing"]["decided"] is True
    assert "already chosen" in server.choose_inserts(vid, [], "None help.")["error"]


def test_choose_inserts_accepts_none(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={}, allowed="")
    assert server.choose_inserts(vid, [], "Nothing in this topic is a diagram or a string.")["insert_styles"] == []


@pytest.mark.parametrize("kw, fragment", [
    (dict(style="auto"), "Pick the main style first"),
    (dict(mode="none"), "Inserts setting is None"),
    (dict(style="cartoon_3d"), "Cartoon 3D video takes no insert scenes"),
    (dict(status="SCRIPT_READY"), "at TOPIC_APPROVED"),
])
def test_choose_inserts_refuses_when_there_is_nothing_to_choose(video, kw, fragment):
    vid = video(**{"status": "TOPIC_APPROVED", "style": "whiteboard", "marks": {}, "allowed": "", **kw})
    assert fragment in server.choose_inserts(vid, [], "reason")["error"]


@pytest.mark.parametrize("styles, fragment", [
    (["whiteboard"], "not an insert style"),
    (["system_flow", "terminal_doc", "x"], "not an insert style"),
])
def test_choose_inserts_refuses_unknown_styles(video, styles, fragment):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={}, allowed="")
    assert fragment in server.choose_inserts(vid, styles, "reason")["error"]


def test_routing_is_decided_when_there_is_nothing_to_decide(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={}, allowed="", mode="none")
    assert server.get_video(vid)["insert_routing"]["decided"] is True
    vid2 = video("vid_c3", status="TOPIC_APPROVED", style="cartoon_3d", marks={}, allowed="")
    routing = server.get_video(vid2)["insert_routing"]
    assert routing["decided"] is True and routing["host"] is False and routing["unavailable_reason"]


def test_insert_routing_lists_every_insert_style(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={}, allowed="")
    routing = server.get_video(vid)["insert_routing"]
    assert [c["id"] for c in routing["candidates"]] == list(tvs.INSERT_STYLES)
    assert routing["transition"] == "push" and routing["limits"]["max_seconds"] == tinserts.MAX_SECONDS


# ── update_video: marks, styles, the domain default ──────────────────────────

def _segs(*marks):
    return [{"id": f"s{i}", "voice": "Words spoken here.", "visual": "v",
             **({"insert": m} if m else {})} for i, m in enumerate(marks)]


def test_update_video_refuses_marks_the_limits_forbid(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={})
    out = server.update_video(vid, script_segments=_segs("system_flow", "", ""),
                              publish_title="t", publish_description="d")
    assert "first segment" in out["error"]


def test_update_video_refuses_marks_when_inserts_are_none(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={}, mode="none", allowed="[]")
    out = server.update_video(vid, script_segments=_segs("", "system_flow", ""),
                              publish_title="t", publish_description="d")
    assert "None" in out["error"]


def test_update_video_warns_about_a_long_insert_segment(video):
    vid = video(status="TOPIC_APPROVED", style="whiteboard", marks={})
    segs = _segs("", "system_flow", "")
    segs[1]["voice"] = " ".join(["word"] * 40) + "."
    out = server.update_video(vid, script_segments=segs, publish_title="t", publish_description="d")
    assert "error" not in out, out
    assert "insert_long" in [w["id"] for w in out["warnings"]]


def test_an_insert_style_cannot_become_a_videos_style(video):
    vid = video(status="TOPIC_PROPOSED", style="auto", marks={}, allowed="")
    assert "insert style" in server.update_video(vid, visual_style="system_flow")["error"]
    legacy = video("vid_legacy", status="TOPIC_PROPOSED", style="terminal_doc", marks={}, allowed="")
    assert "error" not in server.update_video(legacy, visual_style="terminal_doc")


def test_a_domain_cannot_default_to_an_insert_style_and_seeds_its_insert_mode(video):
    video("vid_x", marks={})  # sets up the database
    assert "insert style" in server.upsert_project("dom", "Dom", default_visual_style="system_flow")["error"]
    out = server.upsert_project("dom", "Dom", default_insert_mode="none")
    assert out["default_insert_mode"] == "none"
    assert "default_insert_mode must be one of" in server.upsert_project("dom", "Dom",
                                                                         default_insert_mode="some")["error"]
    created = server.create_video("dom", "a topic", "manual", 7, title="A topic")
    assert created["insert_mode"] == "none"


# ── the text-layout audit ────────────────────────────────────────────────────

def test_the_text_audit_samples_each_insert_and_names_it():
    import text_audit
    cfg = _config(_sf_insert(), _td_insert(start=1000, dur=200))
    passes, _ = text_audit.plan_passes(cfg)
    insert_passes = [p for p in passes if p["scene"] >= 1]
    assert {p["scene"] for p in insert_passes} == {1, 2}
    assert all(600 <= p["first"] < 840 for p in insert_passes if p["scene"] == 1)
    assert text_audit._unit_label(cfg, 1) == "insert 1 (system_flow)"
    assert text_audit._unit_label(cfg, 0) == "scene 0 (vid/Main)"


def test_get_timeline_names_each_segments_insert(video):
    vid = video()
    segs = server.get_timeline(vid)["segments"]
    assert [s["insert"] for s in segs] == ["", "", "system_flow", "", ""]


def test_the_inserts_skills_worked_example_passes():
    """The example in agent_files/skills/tubematic-inserts is what agents copy;
    it must pass the insert style's own check over its window."""
    import re
    import system_flow
    skill = (pathlib.Path(__file__).resolve().parents[2]
             / "agent_files/skills/tubematic-inserts/SKILL.md").read_text()
    block = re.findall(r"```json\n(\"inserts\": \[.*?\])\n```", skill, re.S)[-1]
    entry = json.loads("{" + block + "}")["inserts"][0]
    words = list(range(600, 900, 10))
    assert system_flow.check_insert(entry, FPS, words, ICONS) == []
    assert entry["durationInFrames"] <= tinserts.TARGET_SECONDS * FPS
