# Soundtrack as data (spike)

Every sound in a Cartoon 3D short is synthesized: no samples, no licensing. The authoring agent writes one
`audio-spec.json` beside its `world.json`; `mix.py` turns it, the voice-over and `timeline.json` into `mix.wav`
(48 kHz stereo, exactly the video's length, −14 LUFS, true peak ≤ −1.2 dBTP), three stems and `cues.md`.

The synthesis library (`dsp.py`, `instruments.py`, `sfx_gen.py`) is ported verbatim from
mromidev/claude-animated-shorts (MIT). `band.py`, `score.py`, `cues.py` and `mix.py` are its bridge-specific music,
cue list and mix generalised into spec-driven code.

```
python mix.py --voice voice.wav --timeline timeline.json --spec audio-spec.json --out mix/ [--lufs -14]
```
`voice.wav` is the pipeline's `audio.mp3` resampled to 48 kHz (`ffmpeg -i audio.mp3 -ar 48000 -ac 1 voice.wav`).
Needs numpy and scipy.

## The spec

```jsonc
{
  "music": {
    "tempo": 116, "key": "F", "seed": 1870,
    "theme":  [[1, 0, 1, 82], [1, 1, 0.75, 82], ...],   // optional: own tune, (bar, beat, quarters, midi) in Bb
    "chords": {"1": ["Bb","Bb","Bb","Bb"], "2": ["F","F","Bb","Bb"], ...},   // optional, per bar, in Bb
    "sections": [                                       // the score, one entry per mood, times in seconds
      {"name": "hook",  "start": 0,     "end": 5.57,  "style": "tutti", "level": -9.5},
      {"name": "story", "start": 5.57,  "end": 11.53, "style": "light", "level": -10.5},
      {"name": "fog",   "start": 21.63, "end": 25.43, "style": "sway",  "level": -12}
    ],
    "hits": [25.73],                                    // brass stab + timpani (a hammer blow, a landing)
    "dips": [[5.0, 5.6, -3.0]]                          // music rides under quiet sentence-final words
  },
  "sfx": {
    "seed": 1870,
    "cues": [
      {"t": 0,    "gen": "bed_day",       "args": {"dur": 21.6, "river": 0.7}, "naive": -30, "kind": "bed", "desc": "river air"},
      {"f": 24,   "gen": "steam_whistle", "args": {"dur": 1.4, "notes": [53, 57, 60]}, "naive": -5, "pan": 0.3, "dist": 20, "desc": "the Lee"},
      {"t": 11.8, "gen": "telegraph_key", "args": {"dur": 2.2, "wpm": 20}, "naive": -10, "desc": "the operator keys the bulletin"}
    ]
  }
}
```

**Styles** (`score.py`): `tutti` full band with a whistling crowd, `march`, `light`, `vamp` (no melody), `whistle`
(one whistler, then the crowd joins), `tension` (dominant pedal, chromatic climb, roll, dead stop at the end),
`silence`, `sway` (warm pad, soft brass, vibes), `waltz` (music box, 3/4), `soft` (golden, quiet), `swing`
(lazy, vibes and brushes), `pad`. `level` = the music's loudness in LU under the voice in that section (−9 loud,
−12 quiet); the music is also ducked 3 dB under every spoken word.

**Cues** (`cues.py`): `naive` = the event's loudness in LU relative to the voice stem (0 = as loud as the voice;
events are then placed 6 dB lower, the standard rule; beds are not reduced). `dist` in metres adds the camera-distance
loss, low-pass and reverb. Generators: beds `bed_day`, `bed_golden`, `bed_night`, `bed_water`, `bed_town`; crowds
`murmur`, `cheer`, `oofs`, `whoas`, `groans`, `scuffle`, `footsteps`; things `steam_whistle`, `bell`, `paddle_churn`,
`engine_chuff`, `telegraph_key`, `whoosh`, `creak`, `splashes`, `debris`, `bounces`, `flash`; and the raw library:
`clink`, `rattle`, `boot`, `column_stomp`, `deck_flex`, `chain_groan`, `bolt_snap`, `chain_whip`, `timber_tear`,
`wood_crack`, `splash_big`, `water_bed`, `oof`, `whoa`, `hurrah`, `applause`, `bird_chirps`, `crickets`, `breeze`,
`flag_flutter`, `hammer_hit`, `stroll_step`, `push_thump`, `swing_squeak`. Each takes its `args` as keyword arguments
(`dur` in seconds where it applies). A missing sound is a new function in `cues.py`, composed from `sfx_gen` parts.

`cues.md` is the proof: per-section voice-over-bed margins, the music map and every event with its level in the mix.
Every generator is seeded from the spec, so the same spec renders the same mix.

## Chicago (this copy)

`bash renderer/remotion/src/videos/chicago/audio/run.sh [out_dir]` regenerates everything: `gen_spec.py` reads the
locked frames from `../story.ts` (SHOTS, WHISTLES, TURNS, TURN_LEN, FLASH_AT) and writes `audio-spec.json`, the voice
is resampled to 48 kHz, `mix.py` writes mix.wav, stems, cues.md and loudness.json. Seeded: same inputs, same mix.

Additions over the engine above:
- `sfx_chicago.py` (registered into `cues.GENERATORS`): `mud_step`, `squelch`, `boot_suck`, `hooves` (mud/stone),
  `whinny`, `snort`, `wagon_creak`, `screw_ratchet`, `screw_turn` (hundreds of detuned screws a few ms apart, beam
  groan), `screw_crew`, `pea_whistle`, `timber_groan`, `shoveling`, `dirt_dump`, `tamp`, `pipe_land`, `rope_creak`,
  `masonry`, `trowel`, `brick_set`, `laughs`, `coughs`, `flies`, `drips`, `puddle_splash`, `paper_rustle`,
  `teacup_rattle`, `china_clink`, `cutlery`, `shop_bell`, `stair_steps`, `lamp_light`, `oar_strokes`; beds
  `bed_street`, `bed_crawl`, `bed_dining`, `bed_dusk`, `bed_under`.
- `score.py`: style `creep` (low drone + pizzicato tick, nearly silent); hits may be `{"t", "kind"}` with kind
  `stab`, `button`, `rise` (+`dur`), `turn` (+`step`), `reveal`, `chime`; `silence` sections are gated to silence.
- `mix.py`: a `silence` section keeps the previous section's gain (its reverb tails are never boosted).
