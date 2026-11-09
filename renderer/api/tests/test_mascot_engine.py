"""The mascot engine under renderer/remotion/public/mascot/, read as text.

There is no JS test runner in renderer/remotion, so the engine's rules are
pinned by scanning its files: it ships no Anthropic mascot, loads nothing from
the network, never animates speech, and carries the licences of what it
bundles.

Run from renderer/api/: pytest tests/test_mascot_engine.py
"""
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "remotion" / "public" / "mascot"


def _files(*suffixes):
    return [p for p in sorted(ENGINE.rglob("*")) if p.is_file() and p.suffix in suffixes]


def _text(rel):
    return (ENGINE / rel).read_text(encoding="utf-8")


def test_engine_files_exist():
    for rel in ("frame.html", "driver.js", "sheet.js", "kit/core.js", "kit/expressions.js",
                "kit/timeline.js", "lib/p5.min.js", "lib/p5.brush.js"):
        assert (ENGINE / rel).is_file(), rel


def test_no_clawd_anywhere():
    # Clawd is Anthropic's mascot and must not ship in any form; the engine names no character.
    for p in _files(".js", ".html", ".md", ""):
        if p.name in ("p5.min.js", "p5.brush.js"):
            continue
        assert not re.search(r"clawd", p.read_text(encoding="utf-8"), re.I), p


def test_no_web_fonts():
    # A render may have no egress; a web font would stall it.
    for p in _files(".js", ".html"):
        if p.name in ("p5.min.js", "p5.brush.js"):
            continue
        text = p.read_text(encoding="utf-8")
        assert "googleapis" not in text, p
        assert "Permanent Marker" not in text, p


def test_driver_never_animates_speech():
    # The mascot reacts; it is never presented as the narrator.
    driver = _text("driver.js")
    assert "talk" not in driver
    assert "mouthAt" not in driver


def test_driver_calls_the_registered_mascot():
    assert "window.MASCOT(" in _text("driver.js")


def test_sheets_have_no_talking_mouth():
    sheet = _text("sheet.js")
    assert "talk" not in sheet
    assert "mouthAt" not in sheet


def test_licences_are_shipped():
    for rel in ("lib/LICENSE-p5.js", "lib/LICENSE-p5.brush", "kit/LICENSE-ClaudeAnimationBase"):
        assert (ENGINE / rel).is_file() and (ENGINE / rel).read_text(encoding="utf-8").strip(), rel


def test_licence_files_attribute_the_library_and_its_upstream():
    p5 = (ENGINE / "lib/LICENSE-p5.js").read_text(encoding="utf-8")
    assert p5.startswith("p5.js 2.3.1") and "Copyright (c) the p5.js contributors" in p5
    assert "github.com/processing/p5.js" in p5 and "GNU LESSER GENERAL PUBLIC LICENSE" in p5
    brush = (ENGINE / "lib/LICENSE-p5.brush").read_text(encoding="utf-8")
    assert "github.com/acamposuribe/p5.brush" in brush and "Copyright (c) 2023-2026 Alejandro Campos Uribe" in brush


def test_frame_loads_no_remote_url():
    frame = _text("frame.html")
    assert "http://" not in frame and "https://" not in frame
    # a protocol-relative src/href would also leave the machine
    assert not re.search(r"""(src|href)\s*=\s*["']//""", frame)


def test_frame_takes_the_mascot_code_from_the_query():
    frame = _text("frame.html")
    assert "code" in frame and "URLSearchParams" in frame
    assert "sheet" in frame


def test_driver_cues_include_on():
    # the cue schema: on walks the mascot on or off screen; the initial state is off screen
    driver = _text("driver.js")
    assert "'on'" in driver or '"on"' in driver
