"""The validator's port of the walk model (tubematic_core.mascots) against the engine's real driver.

mascots.py re-implements driver.js `compile`/`where` so a track can be checked without a browser.
The constants are pinned by text tests; this runs the actual driver under Node on a few tracks and
compares where the feet stand, so a change to either side that the text pins miss still fails."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tubematic_core import mascots

TOOL = Path(__file__).resolve().parents[2] / "renderer/remotion/mascot-tools/driver-agreement.mjs"
ON = {"frame": 0, "on": True, "x": 0.5, "y": 0.5}
TRACKS = {
    "walk-on, rest, walk-off": [{**ON, "frame": 30}, {"frame": 300, "on": False}],
    "mid-walk retarget": [ON, {"frame": 20, "x": 0.8, "y": 0.4}, {"frame": 35, "x": 0.2, "y": 0.6}],
    "walk off mid-walk": [ON, {"frame": 100, "x": 0.9}, {"frame": 115, "on": False}],
    "scale change": [ON, {"frame": 120, "scale": 0.6}, {"frame": 150, "x": 0.3, "scale": 1.1}],
    "off, then on from the other side": [{**ON, "x": 0.8}, {"frame": 150, "on": False}, {"frame": 260, "on": True, "x": 0.2, "y": 0.4}],
}
FRAMES = list(range(0, 420, 7)) + [29, 30, 31, 114, 115, 116]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not on PATH, so the engine's driver cannot run")
def test_the_python_walk_model_places_the_mascot_where_the_engine_driver_does():
    payload = {"tracks": [{"cues": cues, "frames": FRAMES} for cues in TRACKS.values()]}
    run = subprocess.run(["node", str(TOOL)], input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    engine = json.loads(run.stdout)
    for (name, cues), placed in zip(TRACKS.items(), engine):
        boxes = mascots.boxes_at_frames(cues, FRAMES)
        for row in placed:
            box = boxes[row["frame"]]
            if row["feet"] is None or box is None:
                assert row["feet"] is None and box is None, f"{name}: frame {row['frame']} on/off disagrees"
                continue
            scale = (box[2] - box[0]) / mascots.BOX_W
            feet = ((box[0] + box[2]) / 2, box[1] + mascots.FEET_Y * scale)
            assert feet == pytest.approx(row["feet"], abs=1.0), f"{name}: frame {row['frame']}"
