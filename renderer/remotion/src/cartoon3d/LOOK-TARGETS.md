# LOOK-TARGETS: numeric reference for a cartoon-3D narrated short

- Digest of a measured style study of "the reference" (20 vertical shorts, 1080x1920 source, studied at 720x1280, 30 fps).
- Units: **px@720** = pixels at 720x1280 (x1.5 for 1080x1920); **px@1080** = pixels at 1080x1920; **f** = frames at 30 fps;
- **W** = head width; **HH** = head height.
- Sources: STYLE_BIBLE.md, reports/{motion,depth,characters,lighting,outlines,grade,textures}.md,
  SKILL.md ("final bridge values" = what shipped after 4 verifier rounds). Where sources disagree both numbers are given.

## 1. Script formula

| Item | Target | Condition / source |
|---|---|---|
| Duration | 31-78 s, median ~60 s (reference); 55-70 s (SKILL.md) | whole video, no intro/logo/outro/CTA |
| Voice start | frame 1-4 | first word onset |
| Speech rate | 3.5-4.1 words/s, median 3.7 | one male narrator, steady |
| Pauses | word gaps > 0.25 s total < 1 s per video | whole video |
| Sentence length | median 13.5 words | plain spoken English, contractions |
| Hook | sentence 1, 10-16 words, paradox stated as fact, no setup | 20/20 videos |
| Setting | 1-2 lines, present tense, concrete numbers / time / named everyman | |
| Escalation | 3-6 beats (STYLE_BIBLE.md) / 3-4 beats (SKILL.md), each bigger, short in-character dialogue | |
| Exaggeration jokes | 1-2 per video, researched real facts | claim vs reality |
| Mystery beat | ~1 per video ("Wait, ...?") | |
| Pivot word | "You see," | 14 of 20 videos, opens the mechanism + everyday analogy |
| Payoff | last 1-2 sentences, ironic; video ends on the last word | |
| Example script | 218 words, 16 sentences, 13.6 words/sentence, 59 s at 3.7 words/s | templates/SCRIPT_example.md |

Beat order used by the shipped short (SKILL.md): hook, setting, action x3-4, snap, deadpan double line ("Luckily ... / Unluckily ..."),
explanation by analogy, consequence (the rule), callback twist.

Two narration modes: (a) story mode, third person "he", named everyman, present tense; (b) "Imagine you're ..." second person.
Every sentence is illustrated literally and props carry the joke; never narrate what is already on screen.

## 2. Timing to words

| Event | Lead / length | Source |
|---|---|---|
| Expression or action change | lands 0-3 f **before** word onset; use 2 f | motion.md (measured -1, -3, 0, 0 f) |
| Swap style | instant, 1 f; a blink covers every expression swap | |
| Jump anticipation | 2-3 f crouch | |
| Strike (spear) | 3 f lower, ~6 f held at top, 1 f thrust, contact on word onset, impact ring 4-5 f | |
| Hammer recipe | wind-up 4 f, hold 7 f, 1 f strike, burst 5 f | motion.md 5.3 |
| Mouth vs voice | mouth leads RMS by 0-1 f, correlation r 0.47 | talking characters only |
| Camera impact | push-in stops at the hit frame; kick starts there | |
| Hard cuts | 0-1 per video in 12/20 videos (STYLE_BIBLE.md); "cut on big jumps" is the shipped rule (SKILL.md) | most detected "cuts" are 4 f flash effects |
| Cut vs glide | cut when move > 360 px@720 (half frame width) or zoom > 40 %; else glide | motion.md 5.1 |
| Place/time change | 6-8 f crossfade dissolve, or whole-frame blur sigma 3.6-5 px@720 for 0.3-1 s at the cut | STYLE_BIBLE.md / depth.md |
| Holds | no static hold >= 4 f; frozen span >= 12 f is a QA failure | SKILL.md |

## 3. Camera grammar

Measured at 720x1280, caption band excluded; speed = translation combined with zoom x 734 px.

| Measure | Reference median (range over 20 videos) |
|---|---|
| Hold (< 0.3 px/f) | 10 % of frames (1-27 %) |
| Drift (0.3-2 px/f) | 24 % (4-38 %) |
| Move (>= 2 px/f) | 65 % (34-94 %) |
| Median speed | 3.6 px/f (1.3-12.9) |
| p90 speed | 16.9 px/f (9.7-29.4) |
| Moves per 10 s | 6.0 (2.9-8) |
| Move peak speed | 13.7 px/f (p25 5.9, p75 24.6, p90 36) |
| Attack / release (10 % to peak) | 10 f / 10 f (p25 6, p75 18-19); 62 % symmetric, 18 % ease-out, 20 % ease-in |
| Whole glide | ~23 f; speed still 0.6 of peak at +-10 f from peak |
| One move | 101 px translation, 23 % zoom |
| Strong moves (>= 25 px/f) | attack 8 f, release 7 f; e.g. 1 -> 38 px/f in 16 f, 12 f plateau, 13 f release |
| Hand-held float | none: high-frequency residual 0.08 px (0.05-0.29) |

Disagreement: STYLE_BIBLE.md says "ease-out bursts, peak on the first frame, decay over 8-10 f, holds ~80 % of frames";
motion.md (sub-pixel method) measures symmetric ease-in-out, peak 14-16 px/f, holds 10 %, and marks the STYLE_BIBLE grammar as wrong.

| Rule | Numbers |
|---|---|
| Glide curve | smootherstep; peak = 1.875 x distance / duration; keep duration >= 0.075 x distance (px@720) |
| Glide length | 18-40 f; start ~dur/2 before the word so the fastest frame lands on it (judgment call) |
| Hold creep (push-in) | active in 70 % of quiet frames, 83 % of those push in; rate median 0.14 %/f, p75 0.34, p90 0.70 |
| Hold creep, our setting | 0.15-0.35 %/f on every hold |
| Emphasis push | 0.6 %/f for ~35 f (+22 %) on punch words; push-in runs median 35 f |
| Rolls | 3.2 per 10 s, median 3.6 deg over 18 f (p75 8.1, p90 17.5); use 4-8 deg glided >= 18 f (SKILL final: 4-4.6 deg) |
| Dutch tilt | 2 % of frames (11 of 530, depth.md); STYLE_BIBLE.md says "frequent"; use on <= 2-3 shots, <= 0.05 rad |
| Kicks (impact) | image offset flips sign **every frame**, ~3 px@720 (~5 px/f), roll +-0.1-0.35 deg, gone in 6-8 f; decay (1 - n/7)^1.5 |
| Whip pans | 0.45 per minute; 45-93 px/f for 7-25 f, 2-3 f ramp each end, always directional motion blur; at most 1 per video |
| Crowds | formations stand still; the crane/truck move supplies the motion |
| Foreground props | 39 % of CU, 38 % of MS, 16 % of FS/WS, 5 % EWS carry a near object; place at 0.3-0.5 x focus distance covering 10-25 % of one frame edge; aim ~1/3 of shots |
| Lens height | median 0.79 x character height (IQR 0.67-1.00) = 1.4-2.0 m for a 2 m card; 82 % eye level, 11 % high (1.5-1.9 x), 3 % low, 3 % top-down; <= 15 % of shots below 0.5 x |
| Head-top y | CU 0.28, MS 0.35, FS 0.38, WS 0.50, EWS 0.51 (fraction of frame height) |
| Visible character height | CU 0.65, MS 0.50, FS 0.35 (0.27-0.45), WS 0.15, EWS 0.10 of frame height |
| Horizon y | 0.45 (IQR 0.39-0.50); keep 0.40-0.50 |
| Shot mix | CU 3 %, MS 27 %, FS 28 %, WS 12 %, EWS 8 %, inserts 22 % |
| Background distance | near wall 58 %, mid 23 %, far 20 % |
| FOV | 34-46 deg vertical (not measurable on the reference; keep) |
| Disagreement | STYLE_BIBLE.md: "low camera heights"; depth.md: 3 % labelled low, 10 % below 0.5 x height |

## 4. Depth of field

Blur = Gaussian sigma in px@720; disc radius R@1080 ~= 3 x sigma720. DOF is a per-shot choice, never a fixed lens.

| Shot type | n frames | Share with DOF on (bg sigma720 > 1.2) | bg sigma720 when on (IQR) | cInf px@1080 |
|---|---|---|---|---|
| CU | 12 | 42 % | 4.2 (2.8-4.4) | 12.5 |
| MS | 121 | 21 % | 4.0 (1.9-4.9) | 12 |
| FS | 131 | 18 % | 2.7 (2.0-3.4) | 8 |
| WS | 55 | 24 % | 1.9 (1.4-2.5) | 5.7 |
| Inserts | 117 | 46 % | 2.8 | 8.3 |
| All | 530 | 27 % > sigma 1.0 | above-head median 0.57 | - |

| Rule | Numbers |
|---|---|
| Share of screen time with DOF | ~1/3 (our table lands at 35 %) |
| Sharp baseline | edge sigma720 p10 = 0.33; "on" shots never below sigma 1.2 (~4 px radius@1080) |
| Focus | on the subject's eyes; no focus pulls inside shots; change DOF only at cuts or ramp with the camera move (same f/dur) |
| Thin-lens shape | CoC = cInf x abs(1 - F/d); saturates within ~3 x focus distance |
| Foreground objects | sigma720 3.7-7.8 -> 15-24 px@1080 (nearScale 1.2) |
| Shipped cInf (SKILL.md) | hook/river CU 15-16, close-ups 12-14, MS 10-12, park 7, golden sway 5, wides/aerials/establishing 0 |
| Fallback | if too soft, halve cInf before turning it off |
| Fog (aerial perspective) | colour = horizon colour; day 25 -> 420 m, golden 20 -> 360 m (depth.md); shipped day 25 -> 300 m (SKILL.md) |
| Fog effect | skyline objects 40 % toward horizon colour (dA 0.41 vs 0.69 near); far darks lifted to 15 % of horizon colour |
| Fog by distance (recipe) | 15 m 0, 57 m 0.08, 70 m 0.11, 100-140 m 0.19-0.29, 180 m 0.39, 250 m 0.57 |
| Far ink | fog-tint ink by 0.6 x fogK; ink fade 150 -> 450 m |
| Bloom | threshold 1.0, intensity 0.5, mipmap levels 6, radius 0.6 -> e-fold ~30 px@1080 (reference 14-21 px@720 = 21-31 px@1080) |
| Glow sources | emissives only (sun, lamp, fire, moon); excess 0.25-0.5 of (source - bg) at the edge, 0.15-0.4 at +20 px@720; HDR x3 big sources, x8 sparks |
| White surfaces | never bloom: hot edges sigma 0.38 vs normal 0.52; peak white p99.9 = 0.99, max 1.0 |

## 5. Ink

World lines (geometry edges; measured as equivalent full-ink width EW).

| Edge type | scans | with line | EW px@1080 median (IQR) | core luma 0-255 |
|---|---|---|---|---|
| Depth jump (object vs farther object) | 26 | 19 | 3.09 (2.38-4.46) | 19 |
| Silhouette vs sky | 8 | 6 | 3.04 (2.06-3.73) | 51 |
| Convex crease (same object) | 10 | 8 | 2.17 (1.85-3.16) | 34 |
| Contact (object on ground) | 5 | 3 | 2.42 (1.70-3.04) | 30 |
| Painted texture line (plank, grout) | 7 | 1 | 3.66 soft, FWHM 6.4 | 68 |
| Wall/floor join, baseboard, sea horizon | 3 | **0** | - | - |
| Character outline (drawn) | 5 | 4 | 4.57 (3.57-5.17) | 41 |

| Rule | Numbers |
|---|---|
| Coverage | 74 % of geometry edges carry a line (36/49); 45.1 % of strong edges inked frame-wide; ink = 2.6 % of pixels (day) |
| Width by distance | near / mid / far 3.09 / 2.82 / 3.04 px@1080; one receding series 3.36 -> 2.82 -> 2.15 px with core 7 -> 16 -> 50 |
| Recipe width | 3.4 px at 6 m -> 2.2 px at 90 m (log distance), opacity x0.75 at 90 m, fade 150-450 m (outlines.md) |
| Shipped width (SKILL.md) | 5.1 px near (6 m) -> 3.3 px far (90 m) @1080, creases x0.8 from 35 deg, depth jumps from 1 % |
| Softness | 10-90 % rise 1.45 px@720 (captions 1.58): anti-aliased only, blurred only by DOF |
| Colour | near-black, in-focus core luma 0-10; recipe #0b0a0c (outlines.md); shipped #030303 (SKILL.md); far lines lifted ~15 % by fog |
| Crease test | normal angle 50 deg start, 65 deg full; crease width 0.64 x silhouette; concave folds 0.7 strength (0 indoors) |
| Gets lines | silhouettes, depth jumps, convex creases, object-on-ground contacts, thin ropes/poles (solid line) |
| Never | concave room joins (wall/floor), baseboards, sea horizon, texture seams (painted instead), character cards (NOINK layer), doubles |
| Order | bloom -> ink -> DOF: ink before blur so lines blur with the background |
| Character ink colour | dark plum #201628-#2f1d28 (core rgb 47,29,40); warm #5d2c19-#6e3e30 under orange light; design INK #241726 |
| Character ink width | 5.0 % W median (IQR 4.8-6.9 %); thick/thin ratio 2.9-3.5 around a head; thickest at 64 deg (bottom-right, away from light, toward ground) |
| Width by direction | top-right 0.65, top-left 0.74, right-down 1.05, bottom-right 1.11, bottom-left 1.00 (x head median) |
| Inner lines | brows/mouth 0.6-0.9 x outline; clothing seams 0.4 x; hats/props 0.85 x |
| Painted texture lines | 0.7-0.9 x ink width, half its contrast; FWHM 3-5 px@1080; colour = local x 0.35-0.45, alpha 0.8-0.9; never along a geometry edge |

## 6. Colour and grade

Per-frame medians, Y' = Rec.709 luma on sRGB-encoded values, caption rows removed (grade.md, 2164 frames).

| Metric | Ref day (552) | Ref golden (162) | Ref night (352) | Ref interior (835) |
|---|---|---|---|---|
| Y' p1 / p5 / p25 | 0.134 / 0.205 / 0.417 | 0.124 / 0.180 / 0.356 | 0.068 / 0.087 / 0.150 | 0.084 / 0.121 / 0.257 |
| Y' p50 / p75 | 0.571 / 0.706 | 0.516 / 0.668 | 0.243 / 0.366 | 0.448 / 0.607 |
| Y' p95 / p99 | 0.895 / 0.967 | 0.828 / 0.912 | 0.669 / 0.817 | 0.870 / 0.942 |
| Y' mean / std | 0.558 / 0.202 | 0.508 / 0.182 | 0.295 / 0.176 | 0.460 / 0.221 |
| Non-ink Y' p5 | 0.234 | 0.211 | 0.088 | 0.129 |
| HSV S mean / p50 / p90 | 0.439 / 0.429 / 0.737 | 0.459 / 0.448 / 0.671 | 0.586 / 0.611 / 0.840 | 0.436 / 0.422 / 0.764 |
| Colourfulness (H-S) | 82.8 | 71.2 | 66.6 | 68.0 |
| C*ab lit p50 / p90 (L* 40-85) | 33.8 / 54.9 | 36.8 / 53.0 | 36.7 / 64.4 | 28.4 / 54.9 |
| Ink fraction | 0.026 | 0.019 | 0.018 | 0.025 |
| Vignette corner/centre | 0.856 | 0.754 | 0.461 | 0.671 |
| Black point RGB (darkest 0.5 %) | 35,19,20 | 48,16,22 | 9,10,38 | 23,12,20 |
| White point RGB | 254,251,246 | 254,240,220 | 242,230,236 | 253,246,239 |
| Shadow zone (Y'<0.3) a*/b* | +12.5 / -2.5 | +19.1 / -5.8 | +19.7 / -33.1 | +14.8 / -2.5 |
| Shadow share / mids / highlights | 0.17 / 0.55 / 0.28 | 0.20 / 0.54 / 0.26 | 0.61 / 0.34 / 0.05 | 0.36 / 0.39 / 0.24 |

Other luma sources: STYLE_BIBLE.md per-video lum mean 0.43-0.54, std 0.21-0.29, p2 0.03-0.11, p98 0.9-1.0, saturation 0.38-0.65;
lighting.md L* p2 15.5, p50 63.7, p98 95.3 (day), dark band hue 39 deg C* 12. Per-video day Y' p50 ranges 0.38-0.68.

| Item | Numbers |
|---|---|
| Vignette fit | day k 0.06 r0 0.50; golden k 0.11 r0 0.39 (radial bins: day 1.00 centre -> 0.86 corner; golden -> 0.75) |
| Day hue share (mids, S-weighted) | orange 40 %, azure 28 %, chartreuse 9 %, red 7 % |
| Golden hue share | red+rose ~20 %, blue+violet+magenta ~17 %, orange 47-77 % by zone |
| Lit albedo targets (day) | red #e85648 (L* 56, C* 69), orange/wood #e3b684 (77, 31), yellow #d3c677 (80, 44), chartreuse #7cbb48 (70, 66), green #58af47 (65, 66), azure #8fc4fa (77, 29), blue #6d76aa (51, 28) |
| Lit albedo targets (golden) | red #f09a93, orange #ffc590, yellow #fee792, blue #717be8, violet #8967b1, magenta #a065a0, rose #d588a5 |
| Dark materials | L* 16-22, never black: navy #262c51, aubergine #2e2439, plum #3d2530, oxblood #4d2725; iron darkest L* >= 19 |
| Day sky | upper #5e93d9 (L 0.53, S 0.54) at ~20 deg el, horizon #9fb6e6 (L 0.72, S 0.32), horizon/upper luminance 1.28 (depth.md); rows 0-10 % #5997e2 S 0.61 (grade.md); shipped top #3e7fd2 -> horizon #b8d0ec (SKILL.md); frame-top C* >= 45 (textures.md) |
| Golden sky | upper #9a7e7f mauve, horizon #ffd18a holding to ~3 deg el, ratio 1.55 (n = 3); 4-stop version #ffd08a 0 deg, #ffad7e 4 deg, #e9849a 14 deg, #8c78c4 32 deg; C* >= 40 on every stop, no grey mid-band |
| Golden vs day | golden Y' p50 0.516 vs 0.571; S p50 0.448 vs 0.429; shadows violet b* -5.8 (never brown b* +11) |
| Shadow tint, day | shade/lit linear Y 0.49-0.52 on wood (0.37-0.65 overall), per channel R 0.54-0.56 G 0.46-0.50 B 0.47-0.50, saturation +0.02-0.13, same hue (lighting.md) |
| Shadow tint, day (disagreement) | lit/shadow linear 2.8-4.4 (shade = 0.23-0.36 of lit), shadow L* 42-55, b* -20 to -30 blue-violet, e.g. #6a6d92 #7481b8 (grade.md, different patches) |
| Shadow tint, sunset | shade/lit Y 0.15-0.27; R 0.08-0.15, G 0.16-0.30, **B 1.35-3.04** (violet replacement #db9044 -> #5b5173) |
| Haze colours | day distance blue #94cefe / lavender #a7a3af; sunset pink #db9594 / peach #d1a57c; night violet #877aea |
| Grade curve (day) | knots x 0 .1 .25 .5 .75 .9 1 -> y 0.0345 0.1828 0.3812 0.6605 0.8814 0.9631 1; sat sh/mid/hi 0.98/1.27/1.46; shadow tint RGB (+16.5,-3.5,-13.8)/255; vignette k 0.10 r0 0.45 |
| Grade curve (golden) | y 0.0311 0.1877 0.4017 0.6754 0.8750 0.9582 1; sat 0.83/0.88/1.71; shadow tint (+0.2,-2.6,+25.0)/255; vignette k 0.16 r0 0.40; amount 0.8 |
| Grade position | after NEUTRAL tone map, display-referred; grain OFF |

## 7. Lighting

Azimuth convention (camera-relative, frozen per shot): 0 deg = sun straight ahead (backlight), 90 deg = screen right, 180 deg = behind camera; el = elevation.

| Item | Reference | Recipe (lighting.md) | Shipped (SKILL.md) |
|---|---|---|---|
| Day key | side-back az 50-70, el 40-60 (6/20 frames); frontal-soft 7/20; top 2 | az 75, el 48 | az 75, el 48 |
| Sunset key | backlit 10/15 frames, az 0-40, el 3-15; long shadows toward camera | az 15, el 9 | az 6, el 7 |
| Day lit / shade / lift (linear RGB mult.) | - | [1.54,1.47,1.35] / [0.80,0.71,0.83] / [0,0,0] | [1.58,1.5,1.33] / [0.30,0.29,0.36] / [0.05,0.06,0.11] |
| Golden lit / shade / lift | - | [1.42,0.79,0.48] / [0.176,0.206,0.72] / [0.035,0.03,0.075] | key toward #FFB36B x1.5, facade shade ~#444380 |

| Two-tone rule | Numbers |
|---|---|
| Day shadow | ~0.5 x lit, surface's own hue, slightly more saturated; bluish only on grey metal (B 0.81) |
| Sunset shadow | violet-blue replacement, B up to 3 x lit; hue 240-260 deg |
| Interiors | light patches are colour replacements |
| Shadow edge (in focus) | 10-90 % width 3-12 px@720 = 0.4-1.7 % of frame width; soft ones (16-124 px) are DOF only |
| AO | none; small props 25 % darkening gone in 8 px@720; no SSAO |
| Contact blob (day) | ellipse 0.7 x 1.1 m, offset 0.25 m away from sun, multiply Y ~0.59 (ref 0.52-0.74), rim outer 28 % of radius (3-12 px@720) |
| Card shadows | day: none (blob only); golden: real cast shadow ~13 m long at el 9 + light blob |
| Specular | metal only, one soft broad highlight; none on wood, ground, characters |
| Rim light | none on heads (1.02-1.04); golden rim = inner only, head/torso only |
| Sun glow | setting sun core 90 px@720, r50 188 px@720 (13-26 % of frame width); low sun core 58, r50 94, r10 164 |

Character cards under scene light:

| Measure | Reference (30 heads) | Rule |
|---|---|---|
| Head V (HSV) | 0.97 median, range 0.86-1.0, in every light | floor 0.86 day / 0.88 golden; luma >= 0.85 lit, ~0.75 shade |
| Head saturation | 0.03 day, 0.23 sunset, 0.21 night, 0.14 interior | tint = light colour: day #f8f1ef, sunset #fddeb6, lamp #fcdfbd, moon #b1ace7, window #d9b5e7 |
| Side gradient toward key | 0.142 median (0.05-0.36) of head mean | charGrad 0.07 head (~14 % at far edge), bodyGrad 0.20-0.25 torso |
| Top/bottom gradient | -0.109 (top brighter) | +5.5 % top |
| Shadow side tint | white heads x(0.92, 0.90, 0.96) lavender; skin x(0.96, 0.86, 0.84) | sideTint [0.92,0.90,0.96] day, [0.85,0.80,0.95] golden |
| Emissive | none (lit, not pasted) | emissive 0; receive shadows but dim only to 0.86-0.88 |

## 8. Characters

| Proportion | Reference adult median (range) | Kids | Ours spec |
|---|---|---|---|
| Total height | 3.5 HH (3.3-3.7) | 2.7-3.0 HH | adult 3.5, stout 3.47, kid 2.85 |
| Chin -> torso bottom | 1.1 HH (0.9-1.23) | 0.7-1.0 | 1.10 (stout 1.15, kid 0.85) |
| Torso bottom -> sole | 1.4 HH (1.2-1.54) | 1.0-1.15 | 1.40 (stout 1.32, kid 1.00) |
| Torso width | 0.80 W (0.58-0.97) | 0.47-0.84 | 0.80 (stout 0.92, kid 0.72) |
| Legs | single ink stroke 0.055 W (0.05-0.08), no knees, A-stance feet 0.45 W apart, hips 0.3 W | | 5.8 % W |
| Arms | stroke ~0.05 W, no shoulders/elbows, start inside torso sides | | 5.2 % W |
| Hands | filled ink dots 0.08-0.15 W (median 0.11), no fingers | | r 5.5 % W |
| Feet | strokes 0.15-0.25 W long x 0.07 W thick, outward (front) / forward (side) | | 16 % W x 7.5 % W |
| Neck | none; head overlaps torso top | | |
| Torso shape | bean/capsule, widest at 60-70 % of height, round bottom (r ~ half width) | | nTop 2.2, nBot 2.6, egg +0.12 |
| Torso lean / head tilt | 3-8 deg / +-5 deg (3/4 view up to 19 deg) | | |

| Head shape | Reference front (n 23) median (IQR) | 3/4 view (n 8) |
|---|---|---|
| H/W | 0.93 (0.83-1.01); reliable 10: 0.96 | 1.04 |
| Egg (chin taper) | -0.125 (-0.15 to -0.04) | 0 |
| Crown exponent n_top | 1.70 (1.40-1.97) | 2.31 |
| Jaw exponent n_bot | 2.26 (2.08-2.52) | 1.88 |
| Asymmetry (facing side bulge) | +0.10 (0.05-0.12) | +-0.1 |
| Tilt | -1 deg (-8.6 to +3.0), +-2.5 deg per character | +19 deg |
| Contour wobble RMS | 1.0 % W (0.5-1.5) | 0.7 % |

| Face | Reference (/W) | Rule |
|---|---|---|
| Eye spacing | 0.26 (0.19-0.28) centre to centre, at y 0.00 | shift +0.08 W (0.03-0.13) toward facing side |
| Default eye | lidded half-disc: lid 0.18 wide, dark half-disc 0.18 x 0.10-0.12 | dot eyes 0.09 x 0.13 vertical ovals |
| Shock eyes | white circles 0.21-0.24 diameter, gap 0.02, pupil 0.06 | |
| Brows | 0.17-0.18 x 0.045-0.055, tapered, y -0.20 (0.18-0.24 above eyes); often one higher | under a brim y -0.17 |
| Mouth | y +0.19 (0.17-0.31), shifted to facing side; neutral dash 0.09-0.14 x 0.04-0.06, tilted | O-mouth 0.19-0.21 x 0.24-0.29; interior #54212a |
| Nose / ears | none front; 3/4: small nose tick | no skin bump |
| Blush / catchlights | 0 of ~40 faces / 0 of ~40 | none |
| Face fill | white #fef9f6, cream #ffe0b4, #f6b988; median luma 0.93 (0.76-1.0) | skins #ffe2c2 #f5c9a0 #ecd0b6 #c99067 |
| Head shading | soft crescent, flat to 0.6 R, falls 0.6-0.8 R to 0.88-0.89 x lit, angular FWHM ~150 deg; not a hard cel edge | shift 0.30 R, blur 0.09 R |
| Torso shading | lit -> shadow side 1.0 -> 0.55-0.66 gradient; light rim 0.8-0.97 on ~half | shift 0.55 R, blur 0.18 R, SH_CLOTH [0.64,0.66,0.74] |
| Hats | cover top 25-40 % of head, base sag 0.05 W, brim out on facing side | shako base 0.25 HH below crown |
| Expression count | 14 (neutral, stern, grin, laugh, whistle, nervous, shock, relief, relief_open, dazed, pained, smile, smile_closed, lick) | |

| Motion | Reference | Rule |
|---|---|---|
| Drawing rate | on ones; static characters pixel-identical (0.15 grey levels) | no 2s/3s |
| Step | 9-12 f per step (2.5-3.3 steps/s) | 2.6 steps/s = 11.5 f |
| Body bob | 3-7 % of height peak-to-peak, lowest at contact (0.32 HH on one walker) | march 5 %, stroll 3 % |
| Lean | 1 deg at passing -> 5-7 deg at contact, in phase with bob | 4 + 3 cos |
| Feet | planted: stance foot <= 1.1 px/f while ground moves 7.2 px/f | slide within +-5 % |
| Idle in holds | none: 0.01-0.8 px over 32 f; acting idle: head loll 10-15 deg in 8-10 f, hold ~20 f, return | |
| Blinks | 4 f (half / shut / shut / half), gaps 0.5-2.3 s typical (0.2-2.3), 6-7 blinks per 4 s in talky shots; one on every expression swap | |
| Turns | 1-4 f; front -> back ~2 f; back -> front 1 f swap | pick view per key, not per frame |
| Squash/stretch, smears, line boil | none / none / 0 | keep 0 |

## 9. Textures

Everything at 1080x1920. Albedo-to-screen transfer measured on our pipeline: about -8 L* and +7 C*.

| Surface | Reference on-screen | Target |
|---|---|---|
| Sunlit deck planks | L* 61-74, C* 35-68, hue 70-78 deg; board-to-board L* std 1.2-4.2; within-board 1.3-2.6 | L* 72-80 on screen; fills L* 75-89 |
| Plank gaps | core 3.3 % of pitch, FWHM 4.6-5.5 %; FWHM 3.6-4.8 px near, 3.3-3.5 mid/far; dL* 40-48 sun, 17-37 shade; #571e00-#6b2903 | <= 5 % of pitch, FWHM 3.5-5 px |
| Board edges | sunlit lip +4..+7 L* one side, shaded lip -3..-6 other | |
| Edge ramp 10-90 % | 3.2-3.3 px near, 4.8 extreme close | magnification M <= 6 px/texel close, <= 3 working |
| Timber in shade | L* 27-35 (never L* 3-7 black bands) | deck shade L* ~45 |
| Stone blocks | L* 60-73, C* 5-16; bevel top +5 L*, bottom -3; speckles 2-4 px | C* ~10, L* ~75 in sun |
| Mortar | FWHM 2.8-4.5 px, edge 2.1-2.9, dL* 14-21, lighter than ours | FWHM <= 4 px |
| Terracotta roof | #dc8872 / #c87563 / #ec9c87, L* 64, joints 3.3 px dL* 10, no per-tile outline | |
| Grass | #71b038 / #7dbf3f, L* 66, C* 64; low-frequency variance 5.7-10, autocorrelation 16-40 px; sparse flowers | |
| Iron / metal | matcap look: blue-grey mids, bright band on 25-30 % of area, darkest L* 19 | darkest 10 % L* >= 18 |
| Fine noise (hf) | 0.5-0.8; no photographic grain | keep clean, grain off |

| Water / sky / clouds | Reference | Target |
|---|---|---|
| Water gradient | flat saturated vertical gradient, lighter cyan at horizon, 10-35 L* drop top to bottom | >= 10 L* drop |
| Water marks | aspect 2-7, angle within +-9 deg; area far 1.5-5 %, mid 0-1.6 %, near 0-0.9 %; 0.24-5.4 marks per 100x100 px | aspect 3-6 |
| Crest / trough | +8..+13 L* / -8..-9 L* right under the crest; glints 1-3 x 30-100 px; no mirrored reflections | |
| Water colours day | #0c5a8c near, #1679ad mid, #2a9cc8 far, crest #5fcfe6, trough #0a4774 | |
| Sky day C* | 35-89 per stop (e.g. #59abff #208cfb #3e9bff #66baff) | frame-top C* >= 45 |
| Sky golden | coral #d27472 -> #fda77d -> #ffca83 (C* 43); lilac-pink #c18dde -> #feb0c6 | C* >= 40 every stop |
| Clouds | 3 tones: crown L* 97, mid, lavender underside hue 250-280 deg (L* 79-86); edge ramp 8-20 px; 9/11 no outline; 100-640 px wide | #fbf8f1 / #e1e5f3 / #c3cbe9 day |

Texel density: px/m on screen = 2954 / D(m) at vfov 36 deg; deck 1024 texels/m, stone 512, cobble/grass/roof 256, facades 96, chain 512.
Saturation offsets that shipped (SKILL.md): stone -35 % saturation from "storybook", world uSat 1.08, ~15 % blue haze past 60 m; never lemon, never lavender lit faces.
Seams: painted into the texture as dark tints (local x 0.35-0.45), never black, 0.7-0.9 x ink width, half ink contrast; never along a geometry edge the ink pass already draws.

## 10. Readability traps (SKILL.md)

- One rope behind a kid on a swing reads as a hanging: two ropes to a wide plank, A-frame legs clear of the arc.
- Props or flotsam closer than ~2 m to a lens become cut-off blobs at the frame edge; re-check props after every camera move.
- A foreground bush cut by the frame edge reads as a green ball; a foreground prop is recognisable or gone.
- Red + yellow star/diamond flag reads as Vietnam's; use a period-correct flag.
- Painted signs lit by a side sun go grey-blue; give the sign face an unlit material.
- Golden rim as an offset outer copy turns hats into picture frames; inner rim only, head/torso only.
- Rails at chest height cross torsos; put the lens ~2.5 m up so rails cross legs.
- Flat holds read as freezes (frozen span >= 12 f); every hold needs a creeping push-in.

## 11. Final QA

| Check | Target |
|---|---|
| Frame checks (short_qa.py) | 0 black frames, 0 white frames, 0 frozen spans >= 12 f, 0 pop frames; sheets per shot |
| Loudness | -14 LUFS integrated, LRA ~2.4 LU (reference); voice starts frame 1-4; ends on the last word |
| Mix | reference bed 5-10 dB below voice (STYLE_BIBLE.md); house mix: music +3 dB, SFX -6 dB, voice unchanged (SKILL.md); mix.wav 48 kHz, exact length |
| Export | 1440x2560 (`--scale 1.3333`), h264 crf 16; mux `-map 0:v:0 -map 1:a:0`; ~4 fps render |
| Luma (day frame) | Y' p50 ~0.57, non-ink p5 ~0.23, p99 >= 0.94, white point ~254,251,246, black point ~35,19,20 |
| Chroma | lit C* p50 >= 32, p90 >= 55; day S p90 ~0.74; ink fraction 2-2.6 % |
| Shadows (day) | shade/lit Y 0.45-0.55, R >= G ~ B, saturation not below lit; dark-band C* >= 10, hue 20-60 deg |
| Shadows (golden) | ground lit V >= 0.75 hue 25-35 deg; shade B ratio >= 1.3 (aim 2-3), hue 240-260 deg; split_b >= +15 |
| Heads | V >= 0.86 everywhere; side gradient 0.10-0.17; top/bottom -0.05 to -0.13 |
| Peak white / bloom | p99.9 luminance 0.97-1.0; no bloom on faces or clouds (threshold 1.0) |
| DOF | on ~1/3 of screen time; CU/MS cInf 10-16 px@1080; wides 0; focus on eyes |
| Camera | move peak <= 25 px/f@720; glides 18-40 f; holds creep 0.15-0.35 %/f; kicks 7 f |
| Deck / stone / iron | boards L* 72-80 C* 35-55; mortar FWHM <= 4 px; iron darkest 10 % L* >= 18 |
| Water | >= 10 L* gradient; crest area far 1.5-5 %, mid <= 1.6 %, near <= 0.9 %; aspect 3-6 |
| Sky | day frame-top C* >= 45; golden C* >= 40 every stop; clouds 3 tones, ramp 8-20 px |
| Verifier | fresh Opus max agent, 1-3 side-by-side images, <= 200-word verdict, scores /10 per area with frame-numbered fixes |
