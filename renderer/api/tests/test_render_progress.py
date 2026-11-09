"""The render watcher (TMDEV-179): Remotion's progress counters decide whether a
render is alive.

A timeout here is a crash detector, not a budget: a render whose counter
stops advancing is killed in minutes whatever its length, and one that
advances is left alone for hours. The watcher is driven against real child
processes, since what it guards against (a pipe that fills, a line that
repeats) is process behaviour.

Which renderer a GPU-only video (Cartoon 3D, a mascot) goes to, and what
happens to it when no GPU works, is the render gateway's and the worker's now
(test_render_gateway.py, test_worker_render.py); the renderer's side of it is
in test_render_agent.py.

Requires the renderer/api deps (flask) — see renderer/api/requirements.txt.
Run from repo root: pytest renderer/api/tests/
"""
import subprocess
import sys

import pytest

import render_agent


# ── The counter ──────────────────────────────────────────────────────────────

def test_progress_reads_remotion_counters_and_nothing_else():
    assert render_agent._progress_of("Bundling 6%") == (0, 6)
    assert render_agent._progress_of("Bundling 100%") == (0, 100)
    assert render_agent._progress_of("Rendered 8/60") == (1, 8)
    assert render_agent._progress_of("[Tab 0] Encoded 17/60") == (2, 17)
    assert render_agent._progress_of("Getting composition") is None
    assert render_agent._progress_of("") is None


def test_phases_order_so_the_first_encoded_counts_as_progress():
    assert render_agent._progress_of("Encoded 0/60") > render_agent._progress_of("Rendered 60/60")
    assert render_agent._progress_of("Rendered 0/60") > render_agent._progress_of("Bundling 100%")


# ── The watcher, against real processes ────────────────────────────────────────

def _child(script: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-u", "-c", script], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


@pytest.fixture
def quick(monkeypatch):
    monkeypatch.setattr(render_agent, "_POLL_SECS", 0.05)


def test_a_render_that_advances_is_left_alone(quick):
    proc = _child("import sys, time\n"
                  "for i in range(1, 6):\n"
                  "    print(f'Rendered {i}/5'); sys.stderr.write('chatter\\n'); time.sleep(0.15)\n"
                  "print('Encoded 5/5')")
    out, err, outcome = render_agent._wait_for_render(proc, timeout_secs=30, stall_secs=0.5)
    assert outcome == "exited" and proc.returncode == 0
    assert "Rendered 5/5" in out and "Encoded 5/5" in out
    assert err.count("chatter") == 5          # the second pipe was drained too


def test_a_render_whose_counter_stops_is_a_stall_even_if_it_keeps_printing(quick):
    proc = _child("import time\n"
                  "print('Rendered 8/60')\n"
                  "while True:\n"
                  "    print('Rendered 8/60'); time.sleep(0.1)")      # the real logs repeat a line
    out, _, outcome = render_agent._wait_for_render(proc, timeout_secs=30, stall_secs=0.6)
    assert outcome == "stall"
    assert out.count("Rendered 8/60") >= 2
    proc.kill(); proc.wait()


def test_the_ceiling_still_catches_a_render_that_crawls(quick):
    proc = _child("import time, itertools\n"
                  "for i in itertools.count(1):\n"
                  "    print(f'Rendered {i}/100000'); time.sleep(0.1)")
    _, _, outcome = render_agent._wait_for_render(proc, timeout_secs=0.7, stall_secs=30)
    assert outcome == "timeout"
    proc.kill(); proc.wait()


def test_a_big_stderr_cannot_deadlock_the_watcher(quick):
    proc = _child("import sys\n"
                  "sys.stderr.write('x' * 300000)\n"           # past any pipe buffer
                  "print('Rendered 1/1'); print('Encoded 1/1')")
    out, err, outcome = render_agent._wait_for_render(proc, timeout_secs=30, stall_secs=5)
    assert outcome == "exited" and len(err) == 300000 and "Encoded 1/1" in out


# ── The AI review's contract ───────────────────────────────────────────────────

def test_the_review_is_told_what_cartoon_3d_looks_like():
    import ai_review
    block = ai_review._register_block("dark", figures=True, line_art=False, cartoon_3d=True)
    assert "Cartoon 3D" in block and "ink outlines" in block and "depth-of-field" in block
    assert "DISCRETE" not in block           # the DOM figure clauses do not apply
    assert ai_review._register_block("dark", figures=True) == ai_review._register_block("dark", figures=True, cartoon_3d=False)
