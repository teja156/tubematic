# The soundtrack spec

Every sound in a Cartoon 3D Short is synthesised by the renderer's engine
(`renderer/remotion/cartoon-tools/audio/`, ported from mromidev/claude-animated-shorts, MIT): no samples, no
licensing. You write one spec object and call `cartoon_soundtrack(video_id, spec)`. The engine resamples
the voice, plays a score from `music`, renders every `sfx` cue, ducks the music 3 dB under every spoken word and 5 dB under every sound-effect event,
and masters the mix to −14 LUFS at exactly the video's length (true peak under −1.5 dBTP). It returns the
cue sheet (`cues`) with every event's level in the mix, and `loudness`. The render muxes the mix.

```jsonc
{
  "music": {
    "tempo": 116, "key": "F", "seed": 1870,
    "theme":  [[1, 0, 1, 82], [1, 1, 0.75, 82], ...],   // optional: own tune, (bar, beat, lengthInQuarters, midi) in Bb
    "chords": {"1": ["Bb","Bb","Bb","Bb"], "2": ["F","F","Bb","Bb"]},   // optional: chords per bar, in Bb
    "sections": [                                        // the score: one entry per mood, times in SECONDS, contiguous
      {"name": "hook",  "start": 0,     "end": 5.57,  "style": "tutti", "level": -9.5},
      {"name": "story", "start": 5.57,  "end": 11.53, "style": "light", "level": -10.5},
      {"name": "fog",   "start": 21.63, "end": 25.43, "style": "sway",  "level": -12}
    ],
    "hits": [25.73, {"t": 40.2, "kind": "rise", "dur": 1.2}],   // brass stab + timpani at a time, or a kind
    "dips": [[5.0, 5.6, -3.0]],                          // the music rides under quiet sentence-final words (start, end, dB)
    "end_fade": 0.4                                      // optional: seconds of fade before the end
  },
  "sfx": {
    "seed": 1870,
    "cues": [
      {"t": 0,   "gen": "bed_day",   "args": {"dur": 21.6, "river": 0.7}, "naive": -30, "kind": "bed", "desc": "river air"},
      {"f": 24,  "gen": "bell",      "args": {"strikes": 3, "gap": 0.9}, "naive": -5, "pan": 0.3, "dist": 20, "desc": "the church bell"},
      {"t": 11.8, "gen": "footsteps", "args": {"dur": 2.2, "people": 3}, "naive": -10, "desc": "the crowd arrives"}
    ]
  }
}
```

## Music

`sections` are the score. `style` is how the band plays the tune between two times; `level` is the music's
loudness in LU relative to the voice in that section. **Always set it, between −14 (loud: the hook, the payoff)
and −18 (quiet: under explanation);** the dense styles (`tutti`, `march`, `stabs`) go at the quiet end of that
range, because a full band at −10 covers every effect and tires the ear under narration. Make a section for
each change of mood, matched to the shot plan; a `silence` section is gated to true silence.

| style | what it is |
|---|---|
| `tutti` | the full band, a whistling crowd on top: the hook, the payoff |
| `march` | drums and brass in step: work, crews, a procession |
| `light` | a light arrangement for the telling of the story |
| `vamp` | the chords without the melody, under speech that needs room |
| `whistle` | one whistler, then the crowd joins |
| `tension` | dominant pedal, chromatic climb, a roll, a dead stop at the end |
| `silence` | nothing, gated |
| `sway` | a warm pad, soft brass, vibes: fog, water, dusk |
| `waltz` | a music box in 3/4 |
| `soft` | golden, quiet |
| `swing` | lazy: vibes and brushes |
| `pad` | a pad alone |
| `stabs` | brass stabs on the section's hits |
| `creep` | a low drone with a pizzicato tick, nearly silent: suspense |

`hits` land a brass stab and a timpani roll on a time (the whistle, the hammer blow, the landing). A hit may
be an object with a `kind`: `stab` (default), `button` (a dry chord with a clash, no roll: a sentence that
ends a thought), `rise` (a brass and glockenspiel climb over `dur` seconds, a stab on top: something lifting),
`turn` (a low dry knock; `step` semitones up), `reveal` (a soft timpani, a vibes chord, a cymbal swell),
`chime` (the final chord: vibes, glock, soft brass, rings). `dips` ride the music down under the quiet last
words of a sentence that should land.

## Sound effects

Each cue: a time (`t` in seconds or `f` in frames), a generator `gen`, its `args` (keyword arguments; `dur`
in seconds where the generator takes one), `naive` = the event's loudness in LU relative to the voice stem
(0 = as loud as the voice; an event is placed at exactly that level, and the music ducks 5 dB under it for its
length; beds are not reduced),
`kind` `"event"` (default) or `"bed"`, `pan` −1..1, `dist` in metres from the lens (adds the camera-distance
loss, a low-pass and more reverb), optional `db` (extra), `lpf` (Hz), `send` (0..1 reverb), `cut` (hard end
at seconds), `fade` ([in, out] seconds), `desc` (for the cue sheet). A bed per place, under every section, at
−28 to −32; an event on the frame its picture happens, **0 to −6** (a hammer blow or a splash 0 to −2, a
footstep or a creak −4 to −6). Use `dist` only for things genuinely far from the lens (a bell across the water,
a boat on the horizon); foley a few metres away takes none, since every metre of distance also takes level
away. An unknown generator is refused by name.

**Check the mix, as you check the frames.** The cue sheet (`cues`) has an `over music` column for every event:
its level against the music at that moment. **An event below 0 is a fix**, the same way a failed beat is: raise
its `naive` level, or lower that section's `level`, and call `cartoon_soundtrack` again. The count is also in
`loudness.events_under_music`; hand the video over with it at 0.

**Beds:** `bed_day` (dur, river, flags, birds, wind), `bed_golden` (dur, crickets, birds), `bed_night` (dur,
crickets, wind), `bed_water` (dur, close, slosh), `bed_town` (dur, voices, wind), `bed_street` (dur, hooves,
birds, murmur, wind, surface "mud"|"stone", carts), `bed_crawl` (dur, drips_, above), `bed_dining` (dur,
voices, clatter), `bed_dusk` (dur, water, crickets), `bed_under` (dur).

**Crowds and people:** `murmur` (dur, voices), `cheer` (dur, people, applause), `oofs` (count), `whoas`
(count), `groans`, `scuffle` (count), `footsteps` (dur, rate, scuff, people, pan_width), `stroll_step`,
`laughs` (count), `coughs` (count, people), `hurrah`, `applause` (dur, people), `oof`, `whoa`.

**Things:** `steam_whistle` (dur, notes [midi], hoarse), `bell` (f Hz, strikes, gap, dur), `paddle_churn`
(dur, rpm, close), `engine_chuff` (dur, rate, depth), `telegraph_key` (dur, wpm), `whoosh` (dur), `creak`
(dur), `splashes` (count), `splash_big`, `water_bed` (dur), `debris` (count), `bounces`, `flash` (dur),
`clink`, `rattle` (dur), `boot`, `column_stomp`, `deck_flex`, `chain_groan` (dur), `bolt_snap`, `chain_whip`,
`timber_tear`, `wood_crack`, `hammer_hit`, `push_thump`, `swing_squeak`, `bird_chirps` (dur), `crickets`
(dur), `breeze` (dur), `flag_flutter` (dur).

**Streets, work, interiors:** `squelch`, `boot_suck`, `mud_step`, `hooves` (dur, rate, surface, gait
"walk"|"trot"), `whinny`, `snort`, `wagon_creak` (dur, creaks), `screw_ratchet`, `screw_turn` (dur, screws,
spread_ms, close, beam), `screw_crew` (dur, men, period), `pea_whistle` (blasts), `timber_groan` (dur,
intensity, settle), `shoveling` (dur, diggers, period), `dirt_dump`, `tamp` (count, gap), `pipe_land` (big),
`rope_creak` (dur, creaks), `masonry` (dur, masons, period), `trowel` (taps), `brick_set`, `flies` (dur, n),
`drips` (dur, rate), `puddle_splash` (size), `paper_rustle` (dur, snap), `teacup_rattle` (dur, intensity),
`china_clink` (count), `cutlery` (dur, rate), `shop_bell` (rings), `stair_steps` (steps, rate, creak),
`lamp_light` (hiss), `oar_strokes` (dur, period).

There is no generator you can add: a sound the list lacks is made from the nearest ones (a `whoosh` and a
`debris` make a collapse; `bell` with a low `f` is a gong; `hooves` on `"stone"` is a cart). Every generator
is seeded from the spec, so the same spec renders the same mix.
