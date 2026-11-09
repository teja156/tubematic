# `renderer/remotion/cartoon-tools/audio/tests`

Covers the soundtrack engine of a Cartoon 3D video: the Python code under
`renderer/remotion/cartoon-tools/audio/` that synthesises music and sound effects from a spec and
mixes them under the voice. The MCP tool
[`cartoon_soundtrack`](../06-mcp-server.md#cartoon_soundtrack) runs it, and
[The Cartoon 3D kit](../09-remotion-project.md#the-cartoon-3d-kit) says where it sits in the
Remotion project. The suite needs numpy and scipy, which `mcp/requirements.txt` installs. Without
them every test is skipped.

```bash
python -m pytest renderer/remotion/cartoon-tools/audio/tests
```

## The mixer

### `test_mix_rules.py`

Covers `cues.py::Cue`, and `mix.py` run as a command on a synthetic voice, a timeline and a spec.

- An event is placed at the level its `naive` value asks for, measured against the voice.
  `cues.SFX_DB` is 0 and a bed keeps its level too.
- The music is ducked under an event for the event's length. The test renders one score with and
  without a loud hit and compares the music stem at that moment.
- The cue sheet (`cues.md`) gives every event its level over the music, and `loudness.json` counts
  the events that sit under the music (`events_under_music`).
- An event in the last 200 ms of the mix is measured like any other.

Trap: `SFX_DB` is a fixed offset added to every event, and it must stay 0. A negative offset puts
every effect below the level the spec asks for and under the band. The author reads the spec and
the cue sheet and cannot see such an offset.

Needs: numpy and scipy. The second test runs `mix.py` twice as a subprocess and synthesises real
audio.
