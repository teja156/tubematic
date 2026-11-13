"""Code Scenes (TMDEV-239): the insert validator in mcp/code_scenes.py.

Code Scenes is an insert style: a code card that morphs between versions, a
highlight, an error callout and a small output pane, timed on the video's
frames. These tests pin the shared contract with the renderer (the fixture
both sides run) and every refusal an unattended agent can hit: code too large
for the card, steps too close or off the narration's words, a still stretch,
an error that names characters the line does not have, and output that is
really a shell session (a command typed at a terminal is Terminal Doc's).
"""
import copy
import json
import pathlib

import pytest

import code_scenes as cs
from tubematic_core import visual_styles as tvs

FIXTURE = json.loads((pathlib.Path(__file__).parent / "fixtures" / "code_scenes_contract.json").read_text())
FPS = 30

VULN = 'name = input("Name: ")\nsql = ("SELECT * FROM users "\n       f"WHERE name = \'{name}\'")\ncur = db.execute(sql)'
FIXED = 'name = input("Name: ")\nsql = ("SELECT * FROM users "\n       "WHERE name = ?")\ncur = db.execute(sql, (name,))'
WORDS = [600, 640, 690, 700, 735, 780, 800, 820]


def _entry(**over):
    data = {
        "lang": "python", "file": "users.py", "tag": "SQL injection",
        "steps": [
            {"at": 600, "code": VULN, "label": "the bug", "focus": [3]},
            {"at": 690, "focus": [3], "error": {"line": 3, "match": "{name}", "text": "Input is pasted into the SQL"}},
            {"at": 780, "code": FIXED, "label": "the fix", "focus": [3, 4],
             "output": {"lines": [], "label": "0 rows"}},
        ],
    }
    data.update(over)
    return {"style": "code_scenes", "startFrame": 600, "durationInFrames": 240, "props": {"codeScenes": data}}


def _check(entry, words=WORDS):
    return cs.check_insert(entry, FPS, words, [])


def _step(entry, i, **over):
    entry["props"]["codeScenes"]["steps"][i].update(over)
    return entry


# ── the shared contract ─────────────────────────────────────────────────────

def test_the_constants_match_the_fixture():
    assert list(cs.LANGS) == FIXTURE["langs"]
    assert cs.LIMITS == FIXTURE["limits"]
    assert cs.TIMING == FIXTURE["timing"]
    assert list(cs.BAND) == FIXTURE["band"]


def test_the_pack_draws_in_the_contract_band():
    assert tvs.pack("code_scenes")["insert"]["block"] == list(cs.BAND)
    assert tvs.pack("code_scenes")["insert"]["props_key"] == cs.PROPS_KEY
    assert tvs.pack("code_scenes")["insert"]["component"] == cs.SCENE_SRC


@pytest.mark.parametrize("case", FIXTURE["font_sizes"])
def test_font_sizes_match_the_fixture(case):
    assert cs.font_size_for(case["lines"], case["cols"]) == case["size"]


def test_the_limits_never_need_a_font_under_32():
    for lines in range(1, cs.LIMITS["maxLines"] + 1):
        assert cs.font_size_for(lines, cs.LIMITS["maxCols"]) >= 32


@pytest.mark.parametrize("case", FIXTURE["type_frames"])
def test_type_frames_match_the_fixture(case):
    assert cs.type_frames(case["code"]) == case["frames"]


@pytest.mark.parametrize("case", FIXTURE["output_at"])
def test_each_step_shows_the_fixture_output_pane(case):
    assert [cs.output_from(case["steps"], i) for i in range(len(case["steps"]))] == case["from"]


# ── a good insert ───────────────────────────────────────────────────────────

def test_a_good_insert_passes():
    assert _check(_entry()) == []


def test_a_typed_first_step_passes():
    e = _entry(steps=[{"at": 600, "code": "x = [1, 2, 3]\nprint(x[3])", "reveal": "type"},
                      {"at": 690, "error": {"line": 2, "match": "x[3]", "text": "IndexError: list index out of range"}},
                      {"at": 780, "focus": [2], "output": {"lines": ["IndexError: list index out of range"]}}])
    assert _check(e) == []


def test_steps_without_word_starts_are_not_snapped():
    e = _step(_step(_entry(), 1, at=685), 2, at=771)
    assert _check(e, words=[]) == []


# ── refusals ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change, fragment", [
    (lambda e: e["props"]["codeScenes"].update(lang="bash"), "Terminal Doc insert"),
    (lambda e: e["props"]["codeScenes"].update(steps=[]), "1 to 4 steps"),
    (lambda e: e["props"]["codeScenes"].update(colour="red"), "unknown keys"),
    (lambda e: e["props"]["codeScenes"].update(tag="X" * 25), "codeScenes.tag"),
    (lambda e: _step(e, 0, at=610), "starts with the insert"),
    (lambda e: _step(e, 0, code=None), "Step 1 must hold the code"),
    (lambda e: _step(e, 1, at=630), "at least 45"),
    (lambda e: _step(e, 2, at=820), "too close to the insert's end"),
    (lambda e: _step(e, 1, at=670), "not on a word"),
    (lambda e: _step(e, 2, code=VULN), "the same as before"),
    (lambda e: _step(e, 0, code="if x:\n\treturn 1"), "tab"),
    (lambda e: _step(e, 0, code="\n".join(f"x{i} = {i}" for i in range(15))), "at most 14"),
    (lambda e: _step(e, 0, code="total = compute_the_whole_total(items, tax)"), "at most 40"),
    (lambda e: _step(e, 0, focus=[9]), "does not have"),
    (lambda e: _step(e, 0, focus=[1, 1]), "each once"),
    (lambda e: _step(e, 1, error={"line": 3, "match": "{nam3}", "text": "x"}), "characters on line 3"),
    (lambda e: _step(e, 1, error={"line": 3, "match": "{name}", "text": "x" * 49}), "error.text"),
    (lambda e: _step(e, 1, error={"line": 3, "match": "{name}"}), "error is {line"),
    (lambda e: _step(e, 2, output={"lines": ["a", "b", "c", "d"]}), "at most 3"),
    (lambda e: _step(e, 2, output={"lines": ["$ python users.py"]}), "shell prompt"),
    (lambda e: _step(e, 2, output={"lines": []}), "needs a label"),
    (lambda e: _step(e, 2, output={"lines": ["x" * 41]}), "at most 40 characters"),
    (lambda e: _step(e, 1, reveal="type"), "first step"),
])
def test_a_bad_insert_is_refused(change, fragment):
    e = _entry()
    change(e)
    errors = _check(e)
    assert any(fragment in m for m in errors), errors


def test_typing_too_much_is_refused():
    long = "\n".join(f"total_{i} = price_{i} * count_{i}" for i in range(6))
    e = _step(_entry(), 0, reveal="type", code=long)
    errors = _check(e)
    assert any("typing is for a line or two" in m for m in errors), errors


def test_typing_that_runs_into_the_next_step_is_refused():
    code = "values = [1, 2, 3]\nprint(sum(values))\nprint(max(values))"
    e = _entry(steps=[{"at": 600, "code": code, "reveal": "type"}, {"at": 640, "focus": [2]},
                      {"at": 735, "focus": [3]}])
    errors = _check(e)
    assert any("still typing" in m for m in errors), errors


def test_a_still_stretch_is_refused():
    e = _entry(steps=[{"at": 600, "code": VULN}, {"at": 800, "focus": [1]}])
    errors = _check(e)
    assert any("Nothing changes for 6.7 s" in m for m in errors), errors


def test_a_still_ending_is_refused():
    e = _entry(steps=[{"at": 600, "code": VULN}])
    e["durationInFrames"] = 240
    errors = _check(e)
    assert any("last" in m and "Nothing changes" in m for m in errors), errors


def test_errors_are_capped():
    e = _entry(steps=[{"at": "x", "code": 3}] * 4)
    assert len(_check(e)) <= cs.MAX_ERRORS


def test_props_must_hold_the_data():
    assert "props must hold" in _check({"startFrame": 0, "durationInFrames": 90, "props": {}})[0]


def test_the_output_check_hook_is_empty_until_code_can_run():
    assert cs.output_check(_entry()) == []


def test_step_windows_cover_the_insert():
    assert cs.insert_step_windows(_entry()) == [(600, 690), (690, 780), (780, 840)]


def test_the_component_is_never_a_scene():
    assert "insert style" in cs.check_scene_use([{"type": "generated", "src": "CodeScenes"}])
    assert cs.check_scene_use([{"type": "generated", "src": "Other"}]) == ""


def test_the_example_does_not_change_under_the_check():
    e = _entry()
    before = copy.deepcopy(e)
    _check(e)
    assert e == before


# ── through write_scene_config ──────────────────────────────────────────────

from test_inserts import _config, video  # noqa: E402,F401  (the shared video fixture)


def test_write_scene_config_writes_a_code_scenes_insert(video):  # noqa: F811
    import server
    vid = video(marks={"s3": "code_scenes"}, allowed='["code_scenes"]')
    result = server.write_scene_config(vid, copy.deepcopy(_config(_entry())))
    assert "error" not in result, result
    written = json.loads(pathlib.Path(result["path"]).read_text())
    assert written["inserts"][0]["src"] == "CodeScenes"
    assert written["inserts"][0]["palette"] == "light"
    assert written["inserts"][0]["shift"] == 0


def test_write_scene_config_names_the_code_scenes_problem(video):  # noqa: F811
    import server
    vid = video(marks={"s3": "code_scenes"}, allowed='["code_scenes"]')
    result = server.write_scene_config(vid, copy.deepcopy(_config(_step(_entry(), 1, at=630))))
    assert "The insert scenes have problems" in result["error"]
    assert "at least 45" in result["error"]


def test_the_code_scenes_component_is_refused_as_a_scene(video):  # noqa: F811
    import server
    vid = video(marks={})
    cfg = _config()
    cfg["scenes"] = [{"type": "generated", "source": "installed", "src": "CodeScenes", "startFrame": 0,
                      "durationInFrames": 1500, "props": {"codeScenes": _entry()["props"]["codeScenes"]}}]
    assert "Code Scenes is an insert style" in server.write_scene_config(vid, cfg)["error"]


def test_the_text_audit_samples_each_code_step():
    import text_audit
    passes, _ = text_audit.plan_passes(_config(_entry()))
    steps = [p for p in passes if p["scene"] == 1]
    assert steps and all(600 <= p["first"] < 840 for p in steps)
    assert text_audit._unit_label(_config(_entry()), 1) == "insert 1 (code_scenes)"
