"""Where the mascot enters a render, read as text, plus the sheet renderer's
argument checks.

renderer/remotion has no JS test runner, so, as for the watermark and the
captions, what matters is pinned from the source: the mascot layer sits over
the scenes and under the captions, it is drawn only when the worker staged
code AND the config has cues, the text audit can never boot it, and nothing in
it reads word timings (the mascot never talks). The sheet renderer is run for
real only as far as its argument checks, which happen before Remotion loads.

Run from renderer/api/: pytest tests/test_mascot_layer.py
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REMOTION = Path(__file__).resolve().parents[2] / "remotion"
SRC = REMOTION / "src"
SHEET_CLI = REMOTION / "mascot-tools" / "render-sheet.mjs"


def _read(rel):
    return (SRC / rel).read_text(encoding="utf-8")


def test_the_layer_is_drawn_over_the_scenes_and_under_the_captions():
    src = _read("CompositionBuilder.tsx")
    layer = src.index("<MascotLayer")
    assert src.index("sceneConfig.scenes.map") < layer < src.index("<Subtitles")
    assert src.count("<MascotLayer") == 1


def test_the_layer_needs_both_the_staged_code_and_cues():
    """mascotPath comes only from the worker (only for a mascot video); the
    cues come from the agent. Either alone draws nothing."""
    src = _read("CompositionBuilder.tsx")
    assert re.search(r"\{mascotPath && Array\.isArray\(sceneConfig\.mascot\) && sceneConfig\.mascot\.length > 0 && \(\s*<MascotLayer", src)
    assert "sceneConfig.mascotPath" not in src   # the code path is a render prop, never the agent's file


def test_the_text_audit_never_passes_a_mascot_path():
    """The audit composition names its props: a spread would forward a
    mascotPath and boot p5 inside a text measurement."""
    root = _read("Root.tsx")
    audit = root[root.index("const TextLayoutAudit"):root.index("const durationFromTimeline")]
    assert "{...props}" not in audit and "mascotPath" not in audit.split("=>", 1)[1]


def test_the_layer_never_reads_word_timings():
    layer = _read("mascot/MascotLayer.tsx")
    for banned in ("timeline", "words", "talk", "mouth"):
        assert banned not in layer.lower().replace("never talks", ""), banned


def test_the_sheet_sizes_match_what_sheet_js_draws():
    """act is a contact sheet of 8 cells, 4 x 480 wide, cropped 960 x 540 each."""
    sheet = _read("mascot/MascotSheet.tsx")
    assert 'act: { width: 1920, height: 540 }' in sheet
    assert 'turn: { width: 1920, height: 1080 }' in sheet and 'feels: { width: 1920, height: 1080 }' in sheet
    js = (REMOTION / "public" / "mascot" / "sheet.js").read_text(encoding="utf-8")
    assert "renderContact(ACT_TIMES, 4, 480, [240, 420, 960, 540])" in js
    assert "ACT_TIMES = [.5, 1.0, 2.2, 3.3, 4.2, 4.8, 5.9, 6.5]" in js   # 8 cells -> 2 rows of 270


def test_the_sheet_renderer_has_its_own_entry_point_and_software_gl():
    cli = SHEET_CLI.read_text(encoding="utf-8")
    assert 'path.join(REMOTION_ROOT, "src", "mascot", "sheet-index.ts")' in cli
    assert 'gl: "swangle"' in cli and "angle-egl" not in cli
    assert "process.env.PUPPETEER_EXECUTABLE_PATH" in cli
    assert "MascotSheetComposition" in _read("mascot/sheet-index.ts")


def test_the_sheet_timeout_is_kept_in_sync():
    cli = SHEET_CLI.read_text(encoding="utf-8")
    tsx = _read("mascot/MascotSheet.tsx")
    n = re.search(r"SHEET_TIMEOUT_MS = ([\d_]+);", tsx).group(1)
    assert f"SHEET_TIMEOUT_MS = {n};" in cli
    assert int(n.replace("_", "")) < 1200 * 1000    # under mcp/mascot_sheets.py's whole-command timeout


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
@pytest.mark.parametrize("args, message", [
    ([], "usage:"),
    (["{code}", "nope", "{out}"], 'unknown sheet "nope"'),
    (["{missing}", "turn", "{out}"], "cannot read the mascot code"),
    (["{empty}", "turn", "{out}"], "is empty"),
    (["{code}", "turn", "{nodir}"], "output directory"),
])
def test_the_sheet_renderer_refuses_bad_arguments_before_loading_remotion(tmp_path, args, message):
    (tmp_path / "code.js").write_text("window.MASCOT = () => {};")
    (tmp_path / "empty.js").write_text("  \n")
    paths = {"code": tmp_path / "code.js", "empty": tmp_path / "empty.js", "missing": tmp_path / "missing.js",
             "out": tmp_path / "out.png", "nodir": tmp_path / "no" / "out.png"}
    argv = [str(paths[a[1:-1]]) if a.startswith("{") else a for a in args]
    run = subprocess.run(["node", str(SHEET_CLI), *argv], capture_output=True, text=True, timeout=30)
    assert run.returncode == 2
    assert message in run.stderr and run.stdout == ""
    assert not (tmp_path / "out.png").exists()
