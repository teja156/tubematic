"""Terminal Doc (TMDEV-199): the scene-config checks that keep an unattended
agent from shipping a crowded, mistimed, overflowing or still typographic
video, their agreement with the renderer's contract.ts and the style pack, the
agent's own moves, and their place in write_scene_config, validate_job and the
text audit.

Each refusal guards something the renderer cannot fix: a string wider than the
frame runs off it, two elements in one slot draw over each other, a move that
starts too close to its cut is never seen, stage text that repeats the
narration duplicates the captions, a full frame is the opposite of the look,
and a custom move with a filter or a stray import costs every render or breaks
every video's bundle.

Run from repo root: pytest mcp/tests/
"""
import copy
import json
import pathlib
import re
from datetime import datetime, timezone

import pytest

import server
import terminal_doc as td
import text_audit
from tubematic_core import visual_styles as tvs

REPO = pathlib.Path(__file__).resolve().parents[2]
CONTRACT_TS = REPO / "renderer/remotion/src/scenes/installed/terminalDoc/contract.ts"
SUBTITLES_TSX = REPO / "renderer/remotion/src/scenes/installed/Subtitles.tsx"
CASES = json.loads((pathlib.Path(__file__).parent / "fixtures/terminal_doc_contract.json").read_text())
REF = REPO / "agent_files/skills/tubematic-terminal-doc/reference"
EXAMPLE = json.loads((REF / "example-config.json").read_text())
EXAMPLE_TIMELINE = json.loads((REF / "example-timeline.json").read_text())
WORD_STARTS = [w["startFrame"] for w in EXAMPLE_TIMELINE["words"]]
WORDS = [w["word"] for w in EXAMPLE_TIMELINE["words"]]
PACK = tvs.pack("terminal_doc")
CAESAR = (REF / "example-move-caesar.tsx").read_text()


def _ts_block(name: str) -> dict:
    body = re.search(rf"export const {name} = \{{(.*?)\}} as const;", CONTRACT_TS.read_text(), re.S).group(1)
    return {k: float(v) if "." in v else int(v) for k, v in re.findall(r"^\s*(\w+):\s*([\d.]+),", body, re.M)}


def _ts_array(name: str) -> tuple:
    body = re.search(rf"export const {name} = \[(.*?)\] as const;", CONTRACT_TS.read_text(), re.S).group(1)
    return tuple(re.findall(r'"([\w-]+)"', body))


# ── agreement with the renderer and the pack ─────────────────────────────────

def test_the_limits_and_timings_match_the_renderer():
    assert _ts_block("LIMITS") == td.LIMITS
    assert _ts_block("TIMING") == td.TIMING
    assert _ts_block("GEOMETRY") == td.GEOMETRY


def test_the_sizes_slots_and_custom_limits_match_the_renderer():
    src = CONTRACT_TS.read_text()
    sizes = re.search(r"export const SIZES = \{ (.*?) \} as const;", src).group(1)
    assert {k: int(v) for k, v in re.findall(r"(\w+): (\d+)", sizes)} == td.SIZES
    custom = re.search(r"export const CUSTOM = \{ (.*?) \} as const;", src).group(1)
    assert {k: int(v) for k, v in re.findall(r"(\w+): (\d+)", custom)} == td.CUSTOM
    assert float(re.search(r"export const CELL = ([\d.]+);", src).group(1)) == td.CELL
    slots = re.search(r"export const SLOTS = \{(.*?)\} as const;", src, re.S).group(1)
    for m in re.finditer(r"(\w+): \{ y: (\d+), top: (\d+), bottom: (\d+), sizes: \[(.*?)\] \}", slots):
        name, y, top, bottom, sizes = m.groups()
        assert td.SLOTS[name] == {"y": int(y), "top": int(top), "bottom": int(bottom),
                                  "sizes": tuple(re.findall(r'"(\w+)"', sizes))}, name
    assert len(re.findall(r"^\s*\w+: \{ y:", slots, re.M)) == len(td.SLOTS)


@pytest.mark.parametrize("ts, py", [
    ("MOVES", td.MOVES), ("TONES", td.TONES), ("GLOW_TONES", td.GLOW_TONES), ("REVEALS", td.REVEALS),
    ("SKINS", td.SKINS), ("CUTS", td.CUTS), ("STAGE_BANDS", td.STAGE_BANDS),
])
def test_the_catalogues_match_the_renderer(ts, py):
    assert _ts_array(ts) == py


def test_the_pack_lists_what_the_renderer_draws():
    extra = PACK["extra"]
    assert tuple(extra["moves"]) == td.MOVES
    assert tuple(extra["slots"]) == tuple(td.SLOTS)
    assert extra["sizes"] == td.SIZES
    assert tuple(extra["tones"]) == td.TONES
    assert tuple(extra["reveals"]) == td.REVEALS
    assert tuple(extra["cuts"]) == td.CUTS
    assert tuple(extra["skins"]) == td.SKINS


def test_the_shared_cases_agree():
    assert {k: td.max_chars(k) for k in td.SIZES} == CASES["max_chars"]
    for c in CASES["number_cells"]:
        assert td.number_cells(c["value"]) == c["cells"], c["value"]
    for c in CASES["wrap_note"]:
        assert td.wrap_note(c["text"]) == c["lines"], c["text"]
    for c in CASES["move_frames"]:
        assert td.move_frames(c["event"], c.get("custom"), c.get("from", "")) == c["frames"], c["event"]


def test_the_log_caption_look_is_one_the_server_accepts():
    """The pack's captions use the "log" look and an accent; the server's list
    of subtitle backgrounds and keys must match Subtitles.tsx, or write_scene_config
    refuses the style's own captions."""
    src = SUBTITLES_TSX.read_text()
    backgrounds = re.search(r"export type SubtitleBackground = (.*?);", src).group(1)
    assert tuple(re.findall(r'"(\w+)"', backgrounds)) == server.SUBTITLE_BACKGROUNDS
    config = re.search(r"export interface SubtitleConfig \{(.*?)\n\}", src, re.S).group(1)
    assert set(re.findall(r"^\s*(\w+)\?:", config, re.M)) == set(server.SUBTITLE_KEYS)
    assert server._validate_subtitles(PACK["captions"]) == ""
    for skin in td.SKINS:
        assert server._validate_subtitles(td.captions_for(PACK, skin)) == ""
    assert td.captions_for(PACK, "crt")["fontFamily"].startswith("VT323")


# ── the checks ───────────────────────────────────────────────────────────────

def _check(config=None, sources=None, video_id=""):
    return td.check(config or EXAMPLE, 30, WORD_STARTS, WORDS, video_id, sources)


def _data(cfg):
    return cfg["scenes"][0]["props"]["terminalDoc"]


def _with(mutate):
    cfg = copy.deepcopy(EXAMPLE)
    mutate(_data(cfg))
    return cfg


def _ev(beat, i):
    return lambda d: d["beats"][beat]["events"][i]


def test_the_example_passes():
    assert _check() == []


def _set(beat, i, **kw):
    """Change one event, keeping the beat's events in frame order."""
    def change(d):
        events = d["beats"][beat]["events"]
        events[i].update(**kw)
        if "at" in kw:
            events.sort(key=lambda e: e["at"] if isinstance(e.get("at"), int) else 0)
    return change


@pytest.mark.parametrize("mutate, fragment", [
    (lambda d: d.update(skin="green"), "skin must be one of"),
    (lambda d: d["beats"][0].update(start=4), "first beat must start at frame 0"),
    (lambda d: d["beats"][2].update(start=465), "not on a word"),
    (lambda d: d["beats"][2].update(cut="fade"), "cut must be one of"),
    (_set(0, 1, type="explode"), "type must be one of"),
    (_set(0, 1, slot="top"), "slot must be one of"),
    (_set(0, 1, text="SUNSHINE IS TOO LONG"), "wider than the frame at size l"),
    (_set(0, 0, size="xl"), "slot context takes the sizes"),
    (_set(0, 0, accent="NOPE"), "accent must be part of the text"),
    (_set(0, 3, slot="a"), "an encode goes from slot a to c"),
    (_set(0, 3, label="SHA256HASHFUNCTION"), "label (the box's operation"),
    (_set(0, 3, at=20), "still playing its own move"),
    (_set(0, 4, at=200), "still playing its move until frame"),
    (_set(0, 4, target="ghost"), "is not on stage"),
    (_set(1, 2, value="~208"), "value is the number as text"),
    (_set(5, 2, count=60), "counts a whole number up from 0"),
    (_set(1, 3, label="A LABEL TOO LONG TO FIT"), "label is 1 to 16"),
    (_set(1, 2, slot="context"), "slot context takes the sizes"),
    (_set(2, 3, frames=10), "frames is how long the race runs"),
    (_set(2, 3, size="xl"), "a stream is size m or l"),
    (_set(3, 2, note="A NOTE THAT GOES ON AND ON FAR PAST WHAT TWO LINES OF THIRTY SIX CHARACTERS CAN HOLD"),
     "note wraps to more than 2 lines"),
    (_set(3, 2, cite=0), "cite is a whole number"),
    (_set(4, 2, output=["A", "B", "C"]), "taller than the slot"),
    (_set(4, 2, text="x" * 30), "the command is wider than the frame"),
    (_set(5, 1, scale=1.4), "a slow push, not a zoom"),
    (_set(5, 1, frames=500), "frames is 45 to 450"),
    (_set(0, 1, slot="context", size="m"), "already holds 'ctx'"),
    (_set(0, 1, id="ctx"), "already used in this beat"),
    (_set(0, 1, text="NEVER STORED THE WAY", size="m"), "repeats four or more narration words"),
    (_set(5, 4, at=1180), "start it at least 15 frames before the cut"),
])
def test_a_broken_config_is_refused(mutate, fragment):
    problems = _check(_with(mutate))
    assert any(fragment in p for p in problems), problems


def test_a_long_stretch_with_nothing_new_is_refused():
    cfg = _with(lambda d: d["beats"][0]["events"].pop(2))   # the glow at "typed"
    problems = _check(cfg)
    assert any("Nothing changes on stage from frame" in p for p in problems), problems


def test_a_full_frame_is_refused():
    def crowd(d):
        ev = d["beats"][2]["events"]          # the stored hash in a, the guesses in b
        start = d["beats"][2]["start"]
        ev += [{"type": "word", "at": start + 2, "id": "ctx", "slot": "context", "text": "OFFLINE ATTACK", "tone": "grey"},
               {"type": "word", "at": start + 4, "id": "rate", "slot": "c", "text": "10 BN / S", "size": "m"}]
        ev.sort(key=lambda e: e["at"])
        next(e for e in ev if e["type"] == "bracket").update(note="HASHCAT, ONE RTX 4090", cite=1)
    problems = _check(_with(crowd))
    assert any("elements are on screen" in p for p in problems), problems


def test_an_encode_needs_the_middle_slot_free():
    def block(d):
        d["beats"][0]["events"].insert(2, {"type": "word", "at": 60, "id": "mid", "slot": "b", "text": "SALT", "size": "m"})
    problems = _check(_with(block))
    assert any("slot b must be empty while the box is on screen" in p for p in problems), problems


def test_a_rearrange_needs_its_source_on_stage():
    problems = _check(_with(_set(4, 1, **{"from": "gone"})))
    assert any("from 'gone' is not on stage" in p for p in problems), problems


def test_a_cleared_slot_can_be_used_again():
    def reuse(d):
        ev = d["beats"][1]["events"]          # the context line, then the keyspace number
        start = d["beats"][1]["start"]
        ev += [{"type": "clear", "at": start + 30, "targets": ["ctx2"]},
               {"type": "word", "at": start + 40, "id": "again", "slot": "context", "text": "BRUTE FORCE", "tone": "grey"}]
        ev.sort(key=lambda e: e["at"])
    assert _check(_with(reuse)) == []


def test_a_bracket_that_reaches_the_next_slot_needs_it_empty():
    def crowd_below(d):
        ev = d["beats"][3]["events"]
        ev.insert(1, {"type": "word", "at": ev[0]["at"] + 2, "id": "under", "slot": "c", "text": "SECONDS", "size": "m"})
    problems = _check(_with(crowd_below))
    assert any("reaches into slot c" in p for p in problems), problems


def test_the_scene_use_rule():
    scene = EXAMPLE["scenes"][0]
    assert td.check_scene_use("terminal_doc", [scene]) == ""
    assert "used only when the video's visual_style is terminal_doc" in td.check_scene_use("stick", [scene])
    assert "exactly one scene" in td.check_scene_use("terminal_doc", [scene, scene])
    assert "exactly one scene" in td.check_scene_use("terminal_doc", [{**scene, "type": "installed"}])
    assert td.check_scene_use("stick", [{"src": "Other"}]) == ""


def test_beat_windows():
    starts = [b["start"] for b in _data(EXAMPLE)["beats"]]
    assert td.beat_windows(EXAMPLE) == list(zip(starts, starts[1:] + [EXAMPLE["totalFrames"]]))
    assert td.beat_windows({"scenes": []}) == []


@pytest.mark.parametrize("mutate", [
    _set(0, 1, text=["SUN"]),
    _set(0, 3, **{"from": 7}),
    _set(1, 2, value=208),
    _set(2, 3, guesses="ABC"),
    _set(3, 2, note=["x"]),
    _set(0, 4, target={"a": 1}),
    lambda d: d["beats"][0]["events"].append("not an event"),
])
def test_a_value_of_the_wrong_type_is_a_sentence_not_a_crash(mutate):
    problems = _check(_with(mutate))
    assert problems and all(isinstance(p, str) for p in problems)


def test_scene_props_that_are_not_an_object_are_refused():
    cfg = copy.deepcopy(EXAMPLE)
    cfg["scenes"][0]["props"] = {"terminalDoc": []}
    assert "must hold 'terminalDoc'" in _check(cfg)[0]


# ── write_scene_config ───────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def make_video(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")

    def make(video_id, style="terminal_doc", with_timeline=True):
        with server._conn() as con:
            con.execute(
                "INSERT INTO videos (id, project_id, topic, status, visual_style, created_at, updated_at) "
                "VALUES (?, NULL, 'why an 8-character password falls', 'VOICE_READY', ?, ?, ?)",
                (video_id, style, _now(), _now()))
        if with_timeline:
            d = tmp_path / "jobs" / video_id
            d.mkdir(parents=True, exist_ok=True)
            (d / "timeline.json").write_text(json.dumps(EXAMPLE_TIMELINE))
        return video_id

    return make


def test_a_sound_config_is_written_with_the_styles_log_captions(make_video):
    vid = make_video("vid_td1")
    result = server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["subtitles"] == PACK["captions"]
    assert written["subtitles"]["background"] == "log"
    assert written["canvas"] == "dark"


def test_the_crt_skin_gets_amber_captions_under_what_the_config_sets(make_video):
    vid = make_video("vid_td2")
    cfg = _with(lambda d: d.update(skin="crt"))
    cfg["subtitles"] = {"maxWords": 3}
    result = server.write_scene_config(vid, cfg)
    assert "error" not in result, result
    sub = json.loads(pathlib.Path(result["path"]).read_text())["subtitles"]
    assert sub == {**td.captions_for(PACK, "crt"), "maxWords": 3}
    assert sub["color"] == "#ffb000"


def test_a_broken_config_is_refused_before_anything_is_written(make_video):
    vid = make_video("vid_td3")
    result = server.write_scene_config(vid, _with(_set(0, 1, slot="top")))
    assert "Terminal Doc video has problems" in result["error"]
    assert not (server.JOBS_DIR / vid / "scene-config.json").exists()


def test_another_style_cannot_use_the_terminal_scene(make_video):
    vid = make_video("vid_td4", style="motion_graphics")
    assert "visual_style is terminal_doc" in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))["error"]


def test_a_terminal_doc_video_cannot_be_built_from_other_scenes(make_video):
    vid = make_video("vid_td5")
    cfg = copy.deepcopy(EXAMPLE)
    cfg["scenes"] = [{"type": "installed", "src": "TitleCard", "startFrame": 0, "durationInFrames": cfg["totalFrames"],
                      "props": {}}]
    assert "A Terminal Doc video is exactly one scene" in server.write_scene_config(vid, cfg)["error"]


def test_a_bad_accent_is_refused():
    assert "accent must be a CSS colour" in server._validate_subtitles({"accent": 5})
    assert server._validate_subtitles({"accent": None, "background": "log"}) == ""


def test_the_text_audit_samples_each_beat():
    passes, _ = text_audit.plan_passes(EXAMPLE)
    windows = td.beat_windows(EXAMPLE)
    assert len(passes) == len(windows)
    for p, (start, end) in zip(passes, windows):
        assert start <= p["first"] and p["first"] + p["step"] * (p["count"] - 1) < end


# ── moves the agent writes ───────────────────────────────────────────────────

CAESAR_SPEC = {"id": "caesar", "src": "vid_td1/move-caesar", "frames": 45, "text": 12}


def _with_caesar(spec=None, text="ATTACK"):
    def add(d):
        d["customMoves"] = [dict(spec or CAESAR_SPEC)]
        ev = d["beats"][2]["events"]                       # the stream beat leaves slot c free
        ev.append({"type": "custom", "at": 520, "id": "shift", "move": "caesar", "slot": "c", "text": text})
        ev.sort(key=lambda e: e["at"])
    return _with(add)


def _check_custom(cfg, sources=None):
    return _check(cfg, {"vid_td1/move-caesar": CAESAR} if sources is None else sources, "vid_td1")


def test_the_example_custom_move_passes():
    assert _check_custom(_with_caesar()) == []


@pytest.mark.parametrize("change, fragment", [
    ({"id": "word"}, "not a shipped move's"),
    ({"src": "vid_other/move-caesar"}, "this video's move-<name> file"),
    ({"src": "vid_td1/caesar"}, "this video's move-<name> file"),
    ({"frames": 900}, "frames is how long the move plays"),
    ({"text": 80}, "0 to 40"),
])
def test_a_bad_custom_move_entry_is_refused(change, fragment):
    problems = _check_custom(_with_caesar({**CAESAR_SPEC, **change}))
    assert any(fragment in p for p in problems), problems


def test_a_custom_move_text_longer_than_it_takes_is_refused():
    problems = _check_custom(_with_caesar(text="A" * 20))
    assert any("at most 12 characters" in p for p in problems), problems


@pytest.mark.parametrize("body, fragment", [
    (None, "write it with write_scene_file first"),
    (CAESAR.replace("<Glyph", '<Glyph filter="url(#f)"', 1), "an SVG filter"),
    (CAESAR.replace("const SHIFT = 3;", "const SHIFT = Math.random();"), "randomness"),
    (CAESAR.replace("const SHIFT = 3;", "const SHIFT = 3; const f = useCurrentFrame();"), "useCurrentFrame"),
    ('import x from "lodash";\n' + CAESAR, "it imports lodash"),
    ('import { Wall } from "../../installed/terminalDoc/backdrop";\n' + CAESAR, "it imports ../../installed/terminalDoc/backdrop"),
    (CAESAR.replace("export default function", "export function"), "default-export"),
])
def test_a_custom_move_file_that_breaks_the_rules_is_refused(body, fragment):
    sources = {} if body is None else {"vid_td1/move-caesar": body}
    problems = _check_custom(_with_caesar(), sources)
    assert any(fragment in p for p in problems), problems


def test_write_scene_config_reads_the_move_files_it_names(make_video, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")
    vid = make_video("vid_td1")
    cfg = _with_caesar()
    assert "write it with write_scene_file first" in server.write_scene_config(vid, copy.deepcopy(cfg))["error"]
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "move-caesar.tsx").write_text(CAESAR)
    assert "error" not in server.write_scene_config(vid, copy.deepcopy(cfg))


def test_validate_job_rechecks_a_move_rewritten_after_the_config(make_video, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")
    vid = make_video("vid_td1")
    folder = tmp_path / "generated" / vid
    folder.mkdir(parents=True)
    (folder / "move-caesar.tsx").write_text(CAESAR)
    cfg = _with_caesar()
    assert "error" not in server.write_scene_config(vid, copy.deepcopy(cfg))
    assert server._td_custom_move_errors(vid, cfg) == []
    (folder / "move-caesar.tsx").write_text(CAESAR.replace("const SHIFT = 3;", "const SHIFT = Date.now();"))
    assert any("randomness or the clock" in e for e in server._td_custom_move_errors(vid, cfg))
    (folder / "move-caesar.tsx").unlink()
    assert any("write it with write_scene_file first" in e for e in server._td_custom_move_errors(vid, cfg))
    assert "_td_custom_move_errors(video_id, scene_config)" in pathlib.Path(server.__file__).read_text()


# ── preview_terminal_moves ───────────────────────────────────────────────────

def test_preview_terminal_moves_refuses_what_it_cannot_preview(make_video):
    assert "for Terminal Doc videos" in server.preview_terminal_moves(make_video("vid_pm1", style="stick"))["error"]
    vid = make_video("vid_pm2")
    assert "no Terminal Doc scene-config yet" in server.preview_terminal_moves(vid)["error"]
    assert "error" not in server.write_scene_config(vid, copy.deepcopy(EXAMPLE))
    assert "lists no customMoves" in server.preview_terminal_moves(vid)["error"]


def test_preview_terminal_moves_returns_the_picture(make_video, tmp_path, monkeypatch):
    from PIL import Image as PILImage
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")
    vid = make_video("vid_td1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "move-caesar.tsx").write_text(CAESAR)
    assert "error" not in server.write_scene_config(vid, _with_caesar())
    seen = {}

    def fake_render(remotion_dir, spec, out_png, timeout=0):
        seen["spec"] = spec
        PILImage.new("RGB", (1080, 1200), (12, 12, 12)).save(out_png)

    monkeypatch.setattr(server.terminal_preview, "render_preview", fake_render)
    result = server.preview_terminal_moves(vid)
    assert isinstance(result, list) and json.loads(result[0])["moves"] == ["caesar"]
    move = seen["spec"]["moves"][0]
    assert (move["src"], move["slot"], move["text"], move["frames"]) == ("vid_td1/move-caesar", "c", "ATTACK", 45)
    assert seen["spec"]["skin"] == "house"


def test_preview_terminal_moves_waits_its_turn_behind_heavy_checks(make_video, tmp_path, monkeypatch):
    monkeypatch.setattr(server, "SCENES_DIR", tmp_path / "generated")
    vid = make_video("vid_td1")
    (tmp_path / "generated" / vid).mkdir(parents=True)
    (tmp_path / "generated" / vid / "move-caesar.tsx").write_text(CAESAR)
    assert "error" not in server.write_scene_config(vid, _with_caesar())
    monkeypatch.setattr(server, "HEAVY_CHECK_WAIT_SECS", 0.05)
    assert server._heavy_checks_lock.acquire(timeout=1)
    try:
        assert "call preview_terminal_moves again" in server.preview_terminal_moves(vid)["error"]
    finally:
        server._heavy_checks_lock.release()


def test_a_uuid_video_id_works_for_custom_moves_and_the_preview_script():
    vid = "3f1c2a9e-7b4d-4e21-9c3a-5d6e7f8a9b0c"
    spec = {**CAESAR_SPEC, "src": f"{vid}/move-caesar"}
    problems = td.check(_with_caesar(spec), 30, WORD_STARTS, WORDS, vid, {f"{vid}/move-caesar": CAESAR})
    assert problems == []
    script = (REPO / "renderer/remotion/terminal-tools/render-moves.mjs").read_text()
    pattern = re.search(r"const SRC = /(.*?)/;", script).group(1)
    assert re.match(pattern, spec["src"])


# ── review round 1 ───────────────────────────────────────────────────────────

def _beat0_with(*extra):
    """Beat 1 of the example (the password and its hash) with events added."""
    def add(d):
        d["beats"][0]["events"] += list(extra)
        d["beats"][0]["events"].sort(key=lambda e: e["at"])
    return _with(add)


def test_the_encode_box_holds_slot_b_against_later_elements():
    # the encode runs 161 to 218; a word put in b while the box is up is drawn over by it
    problems = _check(_beat0_with({"type": "word", "at": 180, "id": "salt", "slot": "b", "text": "SALT", "size": "m"}))
    assert any("holds 'the HASH box'" in p for p in problems), problems


def test_a_brackets_note_holds_the_note_slot_to_the_cut():
    def add(d):
        ev = d["beats"][3]["events"]                       # the "20.9 S" beat, whose bracket has a note
        ev.append({"type": "word", "at": ev[-1]["at"] + 30, "id": "src", "slot": "note", "text": "SOURCE"})
    problems = _check(_with(add))
    assert any("holds \"a bracket's note\"" in p for p in problems), problems


def test_a_typed_command_cannot_glow():
    def add(d):
        ev = d["beats"][4]["events"]                       # the passphrase beat ends with a typed command
        ev.append({"type": "glow", "at": ev[-1]["at"] + 20, "target": "cmd", "tone": "red"})
    problems = _check(_with(add))
    assert any("cannot glow" in p for p in problems), problems


def test_span_cannot_pick_out_part_of_a_number_with_an_exponent():
    problems = _check(_with(_set(5, 3, span=[0, 3])))
    assert any("number with an exponent" in p for p in problems), problems


def test_a_stream_or_command_cannot_take_the_whole_stage():
    problems = _check(_with(_set(2, 3, slot="stage")))
    assert any("a stream races in slot a, b or c" in p for p in problems), problems


def test_a_rearrange_checks_the_size_of_the_slot_it_inherits():
    def add(d):
        ev = d["beats"][1]["events"]                       # rearrange the context line without naming a slot
        ev.append({"type": "rearrange", "at": ev[1]["at"] + 20, "id": "re", "from": "ctx2", "text": "8 PLACES"})
        ev.sort(key=lambda e: e["at"])
    problems = _check(_with(add))
    assert any("lands in slot context" in p for p in problems), problems


def test_the_push_counts_in_the_fit():
    def add(d):
        ev = d["beats"][5]["events"]
        ev[1].update(scale=1.15)
        ev.append({"type": "word", "at": ev[-1]["at"] + 4, "id": "wide", "slot": "a", "text": "A" * 16, "size": "l"})
        ev.sort(key=lambda e: e["at"])
    problems = _check(_with(add))
    assert any("push scales it by 1.15" in p for p in problems), problems
    # without the push the same word fits
    def no_push(d):
        add(d)
        d["beats"][5]["events"] = [e for e in d["beats"][5]["events"] if e["type"] != "push"]
    assert not any("wider than the frame" in p for p in _check(_with(no_push)))


def test_a_push_and_a_move_of_your_own_cannot_share_a_beat():
    cfg = _with_caesar()
    problems = _check_custom(cfg)
    assert problems == []
    _data(cfg)["beats"][2]["events"].append({"type": "push", "at": 600, "frames": 45, "scale": 1.05})
    _data(cfg)["beats"][2]["events"].sort(key=lambda e: e["at"])
    assert any("a push and a move of your own" in p for p in _check_custom(cfg))


@pytest.mark.parametrize("line, fragment", [
    ('const s = { background: "linear-gradient(red, blue)" };', "a CSS gradient"),
    ('const s = { backdropFilter: "blur(30px)" };', "backdrop filter"),
    ('const s = { mixBlendMode: "screen" };', "blend mode"),
    ('const m = import ("fs");', "a dynamic import"),
    ('const n = performance.now();', "performance.now()"),
    ('import { Img } from "remotion";', "a Remotion media or render-control part"),
    ('import { staticFile } from "remotion";', "a Remotion media or render-control part"),
    ('const h = delayRender("x");', "a Remotion media or render-control part"),
])
def test_a_move_that_reaches_past_glyphs_or_costs_renders_is_refused(line, fragment):
    problems = _check_custom(_with_caesar(), {"vid_td1/move-caesar": line + "\n" + CAESAR})
    assert any(fragment in p for p in problems), problems
