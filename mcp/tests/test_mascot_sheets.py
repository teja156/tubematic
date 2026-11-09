"""mcp/mascot_sheets.py::render_sheet: the subprocess around the sheet renderer.

The renderer itself is a Node script (renderer/remotion/mascot-tools/render-sheet.mjs);
these tests stand a fake `node` on PATH so the Python side is exercised for real:
the argv it builds, success judged by exit code AND the PNG being written, the
stderr tail in the error, and the timeout killing the whole process group.
"""
import os
import stat

import pytest

import mascot_sheets


@pytest.fixture
def fake_node(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()

    def install(body: str):
        node = bindir / "node"
        node.write_text("#!/bin/sh\n" + body)
        node.chmod(node.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    return install


@pytest.fixture
def remotion(tmp_path):
    d = tmp_path / "remotion"
    (d / "mascot-tools").mkdir(parents=True)
    (d / "mascot-tools" / "render-sheet.mjs").write_text("// stub")
    return d


def test_success_passes_the_script_code_sheet_and_out_path_and_the_browser_env(fake_node, remotion, tmp_path, monkeypatch):
    monkeypatch.setenv("PUPPETEER_EXECUTABLE_PATH", "/opt/chrome")
    fake_node('echo "$@" > "$0.args"; echo "$PUPPETEER_EXECUTABLE_PATH" > "$0.env"; printf PNG > "$4"')
    code, out = tmp_path / "mascot.js", tmp_path / "out" / "turn.png"
    code.write_text("// code")
    out.parent.mkdir()
    mascot_sheets.render_sheet(remotion, code, "turn", out)
    assert out.read_bytes() == b"PNG"
    args = (tmp_path / "bin" / "node.args").read_text().split()
    assert args == [str(remotion / "mascot-tools" / "render-sheet.mjs"), str(code), "turn", str(out)]
    assert (tmp_path / "bin" / "node.env").read_text().strip() == "/opt/chrome"


def test_a_failing_renderer_raises_with_the_stderr_tail(fake_node, remotion, tmp_path):
    fake_node('echo "noise" >&2; echo "ReferenceError: boom is not defined" >&2; exit 3')
    with pytest.raises(mascot_sheets.MascotSheetError) as e:
        mascot_sheets.render_sheet(remotion, tmp_path / "c.js", "feels", tmp_path / "o.png")
    assert "boom is not defined" in str(e.value)


def test_exit_zero_without_a_png_is_a_failure(fake_node, remotion, tmp_path):
    fake_node("exit 0")
    with pytest.raises(mascot_sheets.MascotSheetError, match="no image"):
        mascot_sheets.render_sheet(remotion, tmp_path / "c.js", "act", tmp_path / "o.png")


def test_a_timeout_kills_the_whole_process_group(fake_node, remotion, tmp_path):
    marker = tmp_path / "grandchild.pid"
    fake_node(f'sleep 30 &\necho $! > {marker}\nwait')
    with pytest.raises(mascot_sheets.MascotSheetError, match="did not finish"):
        mascot_sheets.render_sheet(remotion, tmp_path / "c.js", "turn", tmp_path / "o.png", timeout=1)
    pid = int(marker.read_text())
    with pytest.raises(ProcessLookupError):
        for _ in range(50):          # the kill is synchronous; allow the reaper a moment
            os.kill(pid, 0)
            import time; time.sleep(0.05)


def test_a_missing_script_is_reported_not_run(remotion, tmp_path):
    (remotion / "mascot-tools" / "render-sheet.mjs").unlink()
    with pytest.raises(mascot_sheets.MascotSheetError, match="render-sheet.mjs"):
        mascot_sheets.render_sheet(remotion, tmp_path / "c.js", "turn", tmp_path / "o.png")


def test_a_stale_png_does_not_pass_for_a_new_render(fake_node, remotion, tmp_path):
    fake_node("exit 0")
    out = tmp_path / "o.png"
    out.write_bytes(b"OLD")
    with pytest.raises(mascot_sheets.MascotSheetError):
        mascot_sheets.render_sheet(remotion, tmp_path / "c.js", "turn", out)
    assert not out.exists()
