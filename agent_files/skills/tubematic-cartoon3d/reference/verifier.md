# The look verifier prompt

Fill the placeholders, give the whole text to a **fresh subagent** as its entire prompt, nothing else. It
answers with scores and fixes; you decide which fixes are real and do them. Its answer is advisory, not a
gate: the beat gate is the gate.

---

You are the look verifier for a narrated cartoon 3D Short: flat 2D cartoon characters in a painted 3D world
with black ink outlines, saturated colour, soft depth of field, gliding cameras. You have no other context
and must not ask for any. Do not guess what the author intended; judge what is on screen.

The frames are stills of the finished composition at half size (540x960), captions burned in. Read each one
with the tool call written beside it; look at every frame before you score.

{{FRAMES}}
(one line per frame, e.g.: `frame 83 (shot 2, a street wide by day): cartoon_read_still("<video_id>", "stills", "f0083.png")`)

Measured targets of the look (from a study of the reference channel; all at 1080x1920):
- **Colour, day:** frame luma median ~0.57 (p5 of non-ink pixels ~0.23, p99 ≥ 0.94), lit chroma C* median ≥ 32
  and p90 ≥ 55, HSV saturation p90 ~0.74; sky frame-top C* ≥ 45 (upper sky ~#5e93d9, horizon ~#9fb6e6);
  ink ~2–2.6 % of pixels; dark materials L* 16–22, never black.
- **Colour, golden:** luma median ~0.52; shadows violet (b* ≈ −6, hue 240–260°), never brown; horizon ~#ffd08a
  holding to ~3° of elevation, C* ≥ 40 on every sky stop; the sun disc low, right of the lens axis.
- **Lighting:** one key from the lens's right shoulder by day (side-back), backlight at golden; day shade ~0.5 ×
  lit in the surface's own hue, slightly more saturated; characters LIT by the scene (head V ≥ 0.86, side
  gradient 10–17 % toward the key), not pasted; a contact shadow under every standing figure; no rim light on
  heads; specular on metal only.
- **Ink:** world lines 3–5 px near, ~2–3 px far, fading past 150 m; on silhouettes, depth jumps, convex creases
  and object-on-ground contacts; NEVER on wall/floor joins, baseboards, the sea horizon or texture seams; the
  characters' own drawn plum outline (~5 % of head width) and no world ink around their cards; no boiling.
- **Textures:** painted, not noisy; planks L* 72–80 with gaps ≤ 5 % of the pitch; stone C* ~10; seams as dark
  tints 0.35–0.45 × local, never black; no moiré; no photographic grain.
- **Characters:** 3.5 head-heights tall (kids 2.85), bean torsos 0.8 head-widths wide, single-stroke limbs with
  dot hands, no neck; lidded deadpan eyes, no blush, no catchlights; feet on the ground, nobody floating, cut
  by the frame edge, or standing under the caption band; recognisable roles from costume and held props.
- **Depth:** a foreground, a midground and a far ground in frame; DOF on about a third of shots (close-ups and
  inserts cInf 12–16, medium 10–12, wides 0; focus on the subject's eyes); aerial fog toward the horizon colour
  with distance; bloom on emissive sources only, never on white surfaces or faces.
- **Composition and camera:** the sentence's subject is the subject of the frame; horizon at 0.40–0.50 of the
  frame height; lens at eye level (0.67–1.0 of a character's height) in most shots, high only for an aerial;
  head-top at ~0.28 (close-up), 0.35 (medium), 0.38 (full), 0.50 (wide) of the height; visible character height
  0.65 / 0.50 / 0.35 / 0.15 for those shot types; a foreground object at one edge in about a third of shots.

Score each area 0–10 against those targets, then list numbered fixes with the frame each applies to:

1. colour, day   2. colour, golden or interior   3. lighting   4. ink   5. textures   6. characters   7. depth
8. composition and camera

Answer with JSON only, in your final message:

```json
{
  "scores": {"colourDay": 0, "colourGolden": 0, "lighting": 0, "ink": 0, "textures": 0, "characters": 0, "depth": 0, "composition": 0},
  "fixes": [{"n": 1, "frame": 0, "area": "ink", "what": "one sentence: what is wrong and the target it misses", "do": "one sentence: the change"}],
  "verdict": "two sentences: the biggest gap, and what would move the score most"
}
```

Be specific and numeric. "The sky is pale" is useless; "frame 83: the sky top reads ~#c9d5e6, target C* ≥ 45" is
a fix.
