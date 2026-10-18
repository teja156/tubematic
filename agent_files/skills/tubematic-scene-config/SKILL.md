---
name: tubematic-scene-config
description: Generate scene-config.json and all generated scene TSX files for a Tubematic video
---

# Tubematic Scene-Config Generation Skill

**Invoke this skill when:** a video is in `VOICE_READY` status and `timeline.json` has been produced by `generate_voice`.

---

## Step 0 — Load references before writing any code

Before writing a single line of TSX:

1. **Invoke the `remotion-best-practices` skill** (Skill tool) and follow its guidance on timing
   (springs, Bézier easing, interpolate patterns — mandatory), transitions (`TransitionSeries`, for
   sub-scene transitions inside a generated scene), and text-reveal animations. Consult its 3D
   guidance only if the video topic benefits from 3D (see § Available Packages). Do not assume a
   fixed file layout inside that skill's directory — it's installed from an external repo
   (`remotion-dev/skills`) and its internal structure has changed before; let the skill's own
   `SKILL.md` guide you to the right reference files.

2. **Read every file in `examples/`** (in this skill's directory) before writing any scene component.
   These are the quality bar. Your scenes must match or exceed them.
   - `examples/ex-spring-stagger.tsx` — spring entrance + staggered list reveal
   - `examples/ex-path-draw.tsx` — self-drawing diagram with `evolvePath`
   - `examples/ex-noise-background.tsx` — organic noise background + stat card + number ticker
   - `examples/ex-three-intro.tsx` — 3D scene with ThreeCanvas (opt-in; see package guidance)
   - `examples/ex-ken-burns.tsx` — AI-generated image with a Ken Burns move + overlay text; the
     template for a PHOTO beat that needs custom content on top, and the usual answer for any
     beat built around a generated image
   - `examples/ex-hybrid-anchored.tsx` — the **exception** path: an arrow anchored to a feature
     *in* the image, staying on it through the whole camera move. Only for a beat that passes the
     HYBRID test in **Images** — most image beats do not

---

## Workflow

**Run the entry test in *Revising an Existing Video* below first.** The numbered steps here are the
first authoring pass for a video that has no scene config yet, and a full re-derivation after a
re-voice. A video coming back from `REVISION_REQUESTED` with its audio unchanged takes the
revision branch instead — running these steps on it throws away every scene that was already
correct and re-spends `generate_image` on every image beat.

1. **Settle the visual register first** — read `visual_style` and `resolved_visual_style` from
   `get_video`, and follow **Visual Registers** below. Everything after this branches on the
   answer: which treatments a beat may take, which rules bind, what canvas you write, and which
   components you reach for. Settling it late means re-authoring scenes you have already written.
2. Call `get_timeline(video_id)` — **never** read `timeline.json` directly; `timeline_path` (from
   `get_video`) is container-absolute and unreadable from the agent sandbox or the host. Returns
   `total_frames`, `fps`, and `segments` (empty for pre-segment videos — see the legacy fallback
   below, which needs `get_timeline(video_id, include_words=True)` instead)
3. Call `list_scene_files(source="all")` — see **Reusing Existing Scenes** below before planning
   layout. Pass `video_id=<a prior video>` to browse that video's own generated scenes; with no
   `video_id` filter, the generated half of the list is capped at the 50 most recently modified.
4. Plan scene layout — see **Anchoring Scenes to the Narration** below for how boundaries are decided (segment-anchored primary path if `script_segments`/`timeline.segments` exist, keyword-anchored legacy fallback otherwise); for each planned scene, reuse an installed or a fitting prior generated scene if one exists, otherwise author a fresh one
5. Classify every planned scene's **visual treatment** — PHOTO, HYBRID, or DIAGRAM — from the
   *subject* of its beat, not from the wording of its `visual` brief. PHOTO is the default for
   anything photographic; HYBRID is the exception and has to pass its own test. Call
   `generate_image` for every PHOTO and HYBRID scene before authoring it; the scene needs the
   `public_path` it returns. See **Images** below for the classification test, the per-video image
   floor, and the treatment list you must report on handback.
6. Call `read_image(video_id, image_name)` for **every** image you just generated, and look at it,
   before authoring the scene that uses it. Two things you are deciding: whether the image is
   usable at all (right subject? mangled hands or faces? garbled text baked into the picture?
   regenerate now — after a render it costs a full revision loop), and, for a HYBRID beat, where
   the subject actually sits in the frame. See **Anchoring overlays to the image** below.
7. Call `write_scene_file(video_id, scene_name, tsx_content)` for each newly-authored scene
   component — **never** write `.tsx` files with your own file tools. Paste the returned
   `src` value verbatim into the scene-config entry below — do not build it yourself.
8. Call `write_scene_config(video_id, config)` — **never** write `scene-config.json` with your own file tools. This writes the file and saves `scene_config_path` in one call.
9. Hand back to the operator to call `validate_job`

Never generate `scene-config.json` before `timeline.json` exists — `totalFrames` must be copied exactly from `timeline.totalFrames`.

If any MCP call in this workflow returns `{"error": "scene_work_claimed", ...}`, another agent
session is already doing scene work on this video — stop and hand back to the operator immediately
(see its **Error Handling** section) rather than retrying or working around it.

---

## Revising an Existing Video

Feedback is given against the scenes that exist. A revision is an **edit to those scenes**, not a
new video on the same topic. Re-running the authoring workflow would produce something topically
correct but visually unrecognizable, discarding every frame span, chosen `src`, image and prop the
previous round already got right — and re-charging for images that were never the problem.

### Entry test — run this before Workflow step 1

1. `get_video(video_id)` → `scene_config_path` is **empty** ⇒ first authoring pass. Run Workflow
   steps 1–8.
2. Otherwise call `get_scene_config(video_id)` and `get_timeline(video_id)` and compare:
   - `config.totalFrames` **≠** `timeline.total_frames` ⇒ **the audio was re-voiced.** Every frame
     span in the old config is measured against audio that no longer exists, so nothing in it can
     be carried forward. Run Workflow steps 1–8 in full and overwrite everything.
   - `config.totalFrames` **=** `timeline.total_frames` ⇒ take the **revision branch** below.

Do not substitute "was a revision requested?" for this test. A pronunciation revision re-voices and
comes back with `scene_config_path` still populated from the previous round — the frame counts are
what actually tell you whether the old spans still mean anything.

### Revision branch

1. **Read the feedback and name the scenes.** `get_video`'s `gemini_feedback` carries the full
   review; each must-fix names a scene, a timestamp and a suggested fix. Add anything the human
   comment names. Write down that list — it is the *only* set of scenes you are allowed to touch.
2. **Map each finding to its config entry.** A finding that names a scene maps by `src`. A finding
   that gives only a timestamp maps by frame: `frame = seconds × config.fps`, then the entry whose
   `startFrame ≤ frame < startFrame + durationInFrames` covers it.
3. **Read only those scenes — and only the ones you can edit.** `src` and `source` are a **pair**;
   never pass one without the other.
   - A faulted entry with `"source": "installed"` has **no TSX for you to edit** — that library is
     read-only at runtime. Skip the read entirely and fix it in step 4 through its `props`.
     `read_scene_file(src)` on it would default to `source="generated"` and, at best, error with
     `scene file not found`; if a legacy flat `generated/{name}.tsx` happens to share the name, it
     would silently hand you a **different video's file** and you would "fix" the wrong scene.
     Pass `source="installed"` explicitly, and only if you actually need to see the template's
     props before rewriting them.
   - Every other faulted entry is yours: `read_scene_file(src)` — the config's `src` goes straight
     through, since it is exactly the composed form the tool takes.

   Do not read the video's other scenes: you are not editing them, and a long video's full TSX is
   far larger than the part you need.
4. **Fix and write back those scenes only.** `write_scene_file(video_id, scene_name, tsx_content)`
   with the **same** `scene_name`, so the file is overwritten in place and its `src` doesn't move.
   An `installed/` scene has no TSX to edit — fix it through its `props` in the config instead, or
   replace that one entry with a generated scene of your own.
5. **Write the config back whole, with everything else unchanged.** Take the object
   `get_scene_config` returned, change only the entries from step 2, and pass it to
   `write_scene_config`. Every other entry must be carried through **exactly as read** — same
   `startFrame`, `durationInFrames`, `src`, `source`, `props`, image paths. Do not renumber, re-sort,
   re-pretty or "tidy" anything you weren't asked to fix; an untouched entry should survive
   byte-identically.
6. **Hand back to the operator to call `validate_job`.** Same as the authoring path.

### What may change, and what must not

| | |
|---|---|
| **May change** | The TSX of the scenes the feedback named; those scenes' `props`; an image that was *itself* reported as the defect |
| **Must not change** | `totalFrames`; any other entry's `startFrame`/`durationInFrames`/`src`/`source`/`props`; the scene count; images that were not the defect |

**Do not call `generate_image` for a beat whose image was not the reported defect.** It costs money
and replaces a picture that was already approved. When the image *is* the defect (wrong subject,
mangled anatomy, garbled baked-in text), regenerate it under the **same `image_name`** so the
config's `public_path` stays valid, then `read_image` it before re-authoring the scene — exactly as
Workflow step 5 does.

If the feedback is genuinely structural — the scene *boundaries* are wrong, not the scenes — you may
re-plan spans, but re-derive from the config you read rather than from a blank page, and still keep
every image and every scene the feedback didn't fault.

---

## Reusing Existing Scenes

There are two libraries to check before authoring anything new — both returned by
`list_scene_files(source="all")`:

- **`installed/`** — a curated, committed library of generic, prop-driven scenes (see its
  `README.md` for the current catalog and each scene's props). E.g. any linear process with
  discrete, nameable stages fits `StepFlowDiagram`.
- **`generated/`** — agent-authored scenes, namespaced one subfolder per video
  (`generated/{video_id}/`, bind-mounted to `~/.tubematic-data/scenes/generated/` on the host).
  Every scene any prior video's agent run authored is discoverable (`list_scene_files(source="generated", video_id=<that video>)`)
  and may fit this video's beat too.

To reference an installed scene instead of authoring one, set `"source": "installed"` on
the scene entry (omit `source`, or set it to `"generated"`, for scenes you author yourself):

```json
{
  "type":             "generated",
  "src":              "StepFlowDiagram",
  "source":           "installed",
  "startFrame":       150,
  "durationInFrames": 300,
  "props": { "steps": [...], "connections": [...], "activeStages": [...] }
}
```

Do **not** call `write_scene_file` for installed scenes — they are baked into the image and
read-only at runtime. If you author a scene that turns out generic enough to be reusable
across topics, say so in your `add_comment` — a human can promote it into `installed/` later.

To reuse a `generated/` scene from a prior video, first **read its TSX** with
`read_scene_file(name)` — pass the composed `"{video_id}/{scene_name}"` that `list_scene_files`
returned, verbatim. **Never** try to open it as a file: the scene directories are container-absolute
and unreachable from the agent sandbox or the host. Unlike `installed/` scenes, generated
ones were authored for one specific video and may hardcode that video's topic, copy, or values
into props rather than exposing them as configurable props. Only reuse it if its props are
genuinely generic for your beat's content; otherwise author a fresh scene rather than force a
mismatched fit. **Unlike `installed/`, this is copy, not reference:** call
`write_scene_file(video_id, scene_name, tsx_content)` with the TSX you just read and **your own**
`video_id` — do not reference another video's `generated/` scene by path. Every video's folder is
self-contained, so deleting or overwriting one video's scenes can never change what another video
renders. Reference the result the same way as a freshly-authored scene (`source` omitted or
`"generated"`), using the `src` `write_scene_file` returns for *your* copy.

---

## Visual Registers

`visual_style` on the video is a **permission set**, not a look. It says which vocabularies you
may draw from, and which canvas the video is painted on. It does *not* decide any beat's
treatment — that still follows the beat's subject, exactly as it always has.

Read `visual_style` from `get_video`:

| `visual_style` | Canvas | You may use |
|---|---|---|
| `motion_graphics` | Dark | Vector animation, full-bleed generated imagery. **No figures.** |
| `stick` | Light | **Hand-drawn** `StickFigure` line art, line-art diagrams, generated imagery **in panels**. |
| `illustrated` | **You choose** | Characters are **generated illustrated assets** (`generate_character`) rather than line art. You pick the drawing style *and* the canvas from the topic. |
| `auto` | **You choose** | Any of them — line art, generated characters, vector animation, imagery. |

The two named options are restrictions. `auto` is the absence of one.

### A permission is not an instruction

**This is the most important rule in this section, and the easiest to get wrong.**

`auto` tells you what you *may* use. It does not tell you to use it. **Every beat's treatment is
still decided by that beat's subject, exactly as it always has been** — the register only decides
what is available when the subject calls for something.

**A video that uses every vocabulary because it was allowed to is a defect, not a rich video.**
Variety for its own sake does not read as production value; it reads as a video that could not
decide what it was. Three vocabularies competing across nine beats look like three half-finished
videos spliced together. Two that are used *because each beat needed them* look deliberate.

So:

- **Default to the fewest vocabularies that carry the video.** Most topics need one or two. A pure
  mechanism explainer is all diagrams and should stay all diagrams. A walkthrough is figures and
  diagrams. Reaching past that is a choice you must be able to justify beat by beat.
- **Never add a treatment for variety, pacing or visual interest.** Those are reasons to make the
  scene you already have better, not reasons to change vocabulary. If a diagram beat feels flat,
  the fix is a better diagram, not a stick figure standing next to it.
- **Never introduce a generated character, or a photograph, for a single beat** unless that beat's
  subject genuinely demands it. One photograph in an otherwise drawn video is a jarring cut, not a
  highlight — the bar for it is the same PHOTO test as everywhere else, and a beat that merely
  *could* be shown is not a beat that *must* be.
- **If you cannot say in one sentence why this beat needs this vocabulary and not the one the
  video is already using, use the one it is already using.**

This applies to `auto` above all, because `auto` is the only setting where nothing stops you.

### The one rule that cannot bend

**One video, one canvas.** Alternating light and dark scenes flashes, and a viewer reads it as a
broken render rather than a style. The canvas is therefore a single top-level `canvas` key in
`scene-config.json`, never a per-scene choice, and `write_scene_config` **rejects** a canvas that
contradicts the one the video has already settled on.

**The figure vocabulary is not tied to the canvas.** A stick figure is line art: black on light,
white on dark, same geometry either way. Pass `theme="dark"` or `theme="light"` to `StickFigure`
and `StickScene` to match the canvas. Getting this wrong is invisible in the code and obvious in
the render — a black figure on a dark canvas is a silhouette of nothing.

### Resolving `auto`

Under `auto` you choose **the canvas**, once, and record it. Nothing else is fixed: every beat
still picks its own treatment.

1. Classify every segment by subject as usual (see **Images**), allowing STICK for role beats.
2. Choose the canvas by asking **what carries this video**:
   - **Image-led → `dark`.** The video's spine is real, specific subjects the viewer came to see —
     roughly a third or more of the beats are PHOTO/HYBRID, or the single thing the video is about
     is one of them. A dark canvas lets those images run full-bleed, which is how they land.
   - **Animation-led → `light`.** The video is carried by roles, processes and diagrams, with
     imagery incidental or absent.
   - When it is genuinely a coin toss, pick `dark`: a full-bleed image degrades worse into a panel
     than a diagram does into line art.
3. Call `update_video(video_id, resolved_visual_style="dark" | "light")` **before** you author any
   scene, so your handback can report it.
4. Write the matching `canvas` in the scene config.

**If the video has character beats, also decide the fidelity — once, video-wide.** Hand-drawn
`StickFigure` line art, or generated character art via `generate_character`? The test is whether a
character has to be *recognised*:

| The video's characters are | Use |
|---|---|
| Generic roles doing one thing each — a walkthrough, a process, a hypothetical | **Line art.** Nobody needs to recognise "the user" from one scene to the next |
| Recurring, carrying a narrative across scenes — the viewer must know this is the same person again | **Generated art** (see *The illustrated register* below). Recognition is what it buys, and it is what makes it worth the image calls. The drawing style — cartoon or rendered — is a separate choice, made from the topic |

That test and the cost line up: what makes generated art expensive is exactly what makes it worth
paying for. Say which you chose in the handback, and **never mix them** — see *The illustrated tier*
below.

**Under `auto`, generated art needs an OpenAI key, so check before you choose it.** Read
`illustrated_available` from the `get_video` result you already have. When it is `false`, the
fidelity is **line art** whatever the test above says, and you never call `generate_character` —
it would only refuse, after you had planned the whole video around it. Say in the handback that
recognisable characters were wanted but no key is stored, so a human can add one if the next video
needs them. This check is for `auto` only: under a forced `illustrated` there is nothing to decide
(see *The illustrated register* below).

**Never re-decide.** On a revision round, read `resolved_visual_style` and use it. It is
write-once server-side, so a second, different value is rejected — but the reason matters more
than the guard: re-rolling the canvas mid-video means re-authoring every scene, and a half-done
job is a video that flashes.

If you write a `canvas` without having recorded one, `write_scene_config` records it for you. Rely
on that as a backstop, not a workflow: it happens too late for your handback to say what the video
is.

### What each beat becomes

The subject test in **Images** is unchanged. What the register changes is only how the answer is
built:

| Treatment | On a **dark** canvas | On a **light** canvas |
|---|---|---|
| **STICK** — a generic role: "the user", "an attacker", anyone in a hypothetical or walkthrough | `StickFigure theme="dark"` — white line art | `StickFigure theme="light"` — black line art |
| **PHOTO / HYBRID** — a specific, named person, creature or place | `generate_image`, then `ImageFX` or `KenBurnsImage`, **full-bleed** | `generate_image`, then `PanelImage` — framed on the canvas, never full-bleed |
| **DIAGRAM** — a relation with no appearance | Vector scene, dark palette; `StepFlowDiagram` default | Vector scene, black line on white; `StepFlowDiagram theme="light"` |

**STICK is available under `auto` and `stick`, never under a forced `motion_graphics`** — excluding
figures is that option's entire purpose. There, a role beat is a DIAGRAM or, if the beat genuinely
needs a person shown, a PHOTO.

**The silhouette rule in *Images* still stands, word for word.** A named character, creature or real
place is never reduced to an icon, silhouette or marker — and a stick figure is exactly such a
marker. STICK is a carve-out for **generic roles only**, which is not what that rule protects:
nobody came to see a particular "the user". The moment the subject has a name, the beat is PHOTO.

Two more things that stop a video drifting into that defect:

- **Group by narrative section, not by beat.** Do not alternate treatments every scene; a stretch
  of walkthrough beats is a stretch of stick beats.
- **Report the split on handback** (see *Report your classification*), so a wrong call is visible
  before a render is spent rather than after.

### The illustrated register — generated characters

Under `illustrated` (or `auto`, where everything is permitted) a character is **generated art**
rather than hand-drawn `StickFigure` line art. It costs an image call per pose, and it buys a
character the viewer can *recognise* from scene to scene.

**Under a forced `illustrated`, the style is the permission.** A human chose it, and it can only be
chosen while an OpenAI key is stored, so do not check for a key first and do not weigh line art
against generated art: every character is generated with `generate_character`. If that call
refuses because the key has since been removed, do not fall back to line art — `add_comment` on the
video saying the illustrated style needs an OpenAI key, and end the session.

**`illustrated` does not fix a drawing style, and it does not fix a canvas.** Both are yours,
chosen from the topic and then held for the whole video.

#### Choose the drawing style from the topic's register

| The topic is | Draw the characters as |
|---|---|
| Playful, light, comic — a walkthrough, a gag, a "what if" | **Simple cartoon figures**: blank or minimal faces, thin limbs, flat colour, bold outlines. The hand-drawn tier with more costume and colour than SVG can carry |
| Serious, historical, documentary, emotional | **Properly rendered illustration**: real faces, drawn fabric, weight and shading. A period story deserves to look like one |

There is no right answer in the abstract — a rendered oil-painting figure in a joke about
misconfigured DNS is as wrong as a googly-eyed cartoon telling a story about someone's life.
Pick the one the subject earns, say which in your handback, and **hold it for every character in
the video**. Two drawing styles in one video is the failure this register has to avoid.

#### Choose the canvas the same way

Follow *Resolving `auto`* above: image-led → `dark`, animation-led → `light`. A dark canvas lets
generated scene imagery run full-bleed beside your characters; a light one frames it in panels.
Record it with `update_video(video_id, resolved_visual_style="dark" | "light")` before authoring,
exactly as `auto` does.

#### The character sheet, and why every pose references it

1. **Generate the sheet once, per character.** A plain front-on standing pose, no reference:

   `generate_character(video_id, "ana-base", "<full description>", size="portrait")`

   This one call decides what the character looks like for the rest of the video — including the
   drawing style. **State the style explicitly in this prompt**: "flat vector cartoon, bold
   outlines, blank face" or "detailed period illustration, realistic face, drawn fabric". Whatever
   you write here is what every later pose copies.

2. **Every later pose references THAT sheet**, never the pose before it:

   `generate_character(video_id, "ana-pointing", "<the same character, now …>", reference="ana-base")`

   Chaining pose-to-pose compounds drift: each edit is a small departure, and by the fifth the
   character is visibly someone else. Referencing one canonical sheet keeps every pose the same
   distance from the original instead of accumulating.

3. **Open every prompt with the invariants.** "The exact same character from the reference image,
   unchanged: same <garment>, same <hair>, same <footwear>." Naming them is what holds them; a
   prompt that only describes the new action lets the rest drift. This is not belt-and-braces:
   none of the character models accepts a fidelity setting, so the reference image and the
   invariants you name are the **only** things keeping a pose the same character.

4. **Always say "no shadow, no ground, no scenery."** A transparent background does not by itself
   stop the model drawing a cast shadow, and a baked-in shadow cannot be removed afterwards — it
   will sit on your canvas as a grey smear under a figure that is otherwise floating correctly.

#### Look at every character asset

`read_image(video_id, character_name)` on each one, as you would a scene image — but the judgement
is different and harder. For a scene image you are asking *is this usable*. Here you are asking
**is this still the same character**: same garment, same colours, same build, same face, same
drawing style. A pose that is beautiful and belongs to someone else is a defect, and it is the one
defect that makes an illustrated video look broken rather than merely uneven.

If a pose has drifted, regenerate it from the sheet with the invariants stated more explicitly.
Do not accept it and move on — the viewer notices a changing character long before they notice a
clumsy one.

#### Framing an image in a panel without cropping the subject out of it

A panel crops. `ImageFX` fills its box with `objectFit: cover`, and **CSS crops from the centre by
default** — so a tall portrait dropped into a squarer panel loses nearly half its height, trimmed
equally top and bottom, and takes the subject's head with it. This has already happened in a real
video.

Two levers, in this order:

1. **Size the panel to the image, so nothing is cropped at all.** `generate_image` and
   `generate_character` both return the file's real `width` and `height` — not the aspect you asked
   for, the aspect you got. Give `PanelImage` a `width`/`height` in that ratio and the crop
   disappears. A 1088x1920 image wants a panel like 620x1095, not 900x1000. **This is the default
   and it is free** — the panel's shape is yours to choose.

2. **If the composition fixes the panel's shape**, pass `focus={[u, v]}` — the point of the *source
   image* that must survive. Call `read_image` and read the subject off its UV grid, exactly as a
   HYBRID overlay position is read. A head in the upper third is roughly `focus={[0.5, 0.25]}`.

**Do not reach for `anchor` for this.** `anchor` is the zoom origin; at scale 1 the pan clamp
collapses to zero, so it cannot move what the crop keeps. `focus` is the only thing that can, and
the two are easy to confuse.

Never let the default centre-crop decide what survives. Look at the image, then choose.

#### Placing them

A character asset is a transparent PNG at 1088x1920, referenced by the `public_path` the tool
returns. Place it with an `<Img>` inside your scene, positioned and scaled like any other element —
it is **not** a background, so never hand it to `ImageFX` or `KenBurnsImage`, both of which fill
the frame and would blow a character up to full-bleed.

The alpha is real and soft-edged, so it composites cleanly on either canvas with no keying.

**Never mix generated characters with hand-drawn `StickFigure` line art in one video.** A line
drawing standing next to a rendered figure reads as an asset that failed to load, not as a style.
The tool enforces the obvious half — `generate_character` refuses under a forced `stick` — but
under `auto` it is yours to hold.

### Authoring on either canvas

The canvas is painted for you by the renderer, from the `canvas` key. So:

- **Leave your scene's background transparent** whenever the canvas is meant to show through. Do
  not set `backgroundColor` on your root `AbsoluteFill` for a figure or line-art scene. A scene
  painting its own near-match is one stray hex away from a visible seam between scenes. (This is
  the one place the *Scene Component Requirements* rule about always setting a background does not
  apply.) A full-bleed image scene is the exception — it covers the canvas by design.
- **Palette on light:** black `#000000` line art at 4–6px, flat fills in neutral greys and whites,
  and a saturated accent (`#e53935`, `#0066ff`, `#ffcc00`) reserved for the thing the beat is
  about. On dark: white `#ffffff` line art, the same accents, same weights. An accent used
  decoratively stops reading as an accent.
- **Motion where figures are involved is discrete, and that is the point.** The continuous-motion
  rule in *Animation Philosophy* applies to animation and imagery. A figure holds a pose while the
  narration runs and changes in a single frame, **2 to 5 state changes per 10 seconds of audio**.
  Do **not** tween a figure between poses — swap the `pose` prop on a frame threshold. Props and
  text arrive by `PopIn` (6 frames) or `SlideIn` (8 frames) and then hold.
- Key those arrivals to what is being said. `get_timeline(video_id, include_words=True)` gives
  word-level timings, so an icon can pop on its own noun.

Components, all under `renderer/remotion/src/scenes/installed/` and imported two levels up
(`../../installed/…`) because your scene lives in `generated/{video_id}/`:

| Component | Use |
|---|---|
| `StickFigure` | The figure. `pose`, `expression`, `attire`, `attireColor`, `headwear`, `theme`, `x`, `y`, `scale`, `flip`. Read the file for the pose and expression lists. |
| `StickScene` | Canvas scaffold: optional comic banner title, optional panel frame. Takes `theme`. Wraps your content. |
| `Entrances` | `PopIn`, `SlideIn`, `Swap` — the only three arrivals, at the spec's durations. **`PopIn`/`SlideIn` apply a CSS transform, which makes them the containing block for any `position: absolute` descendant** — so a `StickFigure` or `PanelImage` nested inside one is re-based onto the wrapper instead of the frame and lands somewhere else. It typechecks and renders; it is just wrong. Read the file's header before nesting anything positioned. |
| `PanelImage` | A generated image contained in a panel. **The light canvas's image treatment.** Referenced from scene-config like `KenBurnsImage`, or imported. |
| `ImageFX` / `KenBurnsImage` | Full-bleed imagery. **Dark canvas only** — on light they replace the canvas and the video cuts between two different-looking worlds. |
| `StepFlowDiagram` | Pass `theme: "light"` on a light canvas. Without it, it paints its own near-black slab. |

---

## Animation Philosophy

**This section describes animation and imagery.** Wherever a **figure** is involved, continuous
motion is replaced by discrete state changes — see *Authoring on either canvas* in **Visual
Registers**. Everything else here (the 4-scene floor, scene frequency, no fake motion via
prop-remounting, drive everything from `useCurrentFrame()`) applies everywhere.

Every video must be **visually rich and constantly moving**. Think motion-graphics explainer, not a
slide deck. "Constantly moving" means motion *within* a scene — it is not a statement about how
often you cut.

- **Minimum 4 generated scenes** per video — a hard floor, not a target to beat
- **Every scene must have continuous motion**: elements must move, scale, draw, or transition on every frame — never hold static for more than ~10 frames
- **More scenes is not better, and over-cutting is a defect.** A scene that holds one idea for its
  whole narration beat with continuous internal motion is better than the same idea chopped into
  three. Constant scene changes read as frantic and distract from what is being said — a viewer
  cannot follow an idea that is replaced before it lands.
- **Motion must span the scene, not just open it.** An entrance animation that finishes in the
  first 20–40 frames leaves the rest of the scene static, which is what the rule above forbids.
  Use motion that runs the full length: a Ken Burns move via `ImageFX` (its pan/zoom ramps are
  keyed to `durationInFrames`, so they drift across whatever span you give it), a diagram that
  builds progressively, a number ticking up, a state animating through thresholds. Key these to
  the scene's `durationInFrames`, never to fixed frame constants — a constant that looks right in
  a short scene stops moving early in a long one.
- Drive ALL animation from `useCurrentFrame()` — never CSS transitions, `@keyframes`, or Tailwind `animate-*`
- **No TextReveal scene** — focus entirely on visual storytelling
- All scenes must cover frame 0 → `totalFrames` with no gaps
- **Images are a co-equal capability, not a fallback** — a PHOTO or HYBRID beat (see **Images**)
  that gets drawn in SVG instead is a defect, not a stylistic choice

### Mandatory: the narration is captioned — do not write it on screen too

**The video carries burned-in subtitles.** Every word of the narration is already on screen, in
sync, drawn above your scenes by the renderer. You do not author them, you cannot collide with
them, and you must not duplicate them.

So: **text in a scene is the exception, and you must be able to say what it is doing that the
motion and the subtitles are not.** The default is no text at all.

This is a reversal of how these videos used to be built, and it is the rule most likely to be
broken by habit. Headlines that restate the sentence being spoken, a lower third naming the thing
already visible, a caption under a photograph of the subject the voice just named — every one of
those used to be the house style. They are now clutter: the viewer reads the same words twice,
the screen gets busier, and the animation you actually made is competing with it.

**Text earns its place only when the text IS the content.** The complete list:

| Justified | Why it survives |
|---|---|
| A number the viewer must read | "2.3 million", "0.04%" — a spoken figure is not retained; a ticking counter is the content |
| A label pinned to a part of a diagram or image | It identifies *which* thing. The subtitles cannot point |
| A term being defined, shown once as it is introduced | Spelling is information for a technical term the viewer may search |
| Code, a command, a filename, an error string | Literal strings the viewer would have to see to use |
| An axis, a legend, a unit on a chart | Without it the chart is unreadable |

Everything else is not justified. In particular, **none of these are**: a headline restating the
narration; a title card announcing the topic; a "lower third" of any kind; a caption describing a
picture; a pull-quote of the sentence being spoken; a closing "thanks for watching" slate; a
bulleted list of what the voice is saying.

**The test, applied per string, before you type it:** *remove this text — is any information lost
that the motion, the image and the subtitles do not already carry?* If the answer is no, delete it.
If you find yourself writing a sentence, it is narration and it is already handled.

**Let the motion do the talking.** A beat that would have been a headline over a drifting image
is a beat that needs a better visual, not a caption: show the thing changing, build the diagram a
step at a time, move the figure. That is the work the text was standing in for.

One consequence worth stating: the layout checks in `validate_job` measure *your* text against the
subtitles. The less you put on screen, the less there is to collide.

### Mandatory: image floor for photographic subjects

**Dark-canvas videos only.** On a light canvas the floor does not apply: a role beat is a figure
by design, not a photograph withheld, and imagery there is panel-framed rather than full-bleed.
What survives to either canvas is the floor's *reason* — a named, specific subject the viewer came
to see still gets a real generated image. See **Visual Registers**.

Animation has a hard floor (4 scenes). Images have a conditional one, and it is just as binding.

Count the segments whose subject is a named character or real person, a creature or animal, a real
place or structure, or one specific dramatic/historical moment (the PHOTO/HYBRID test in **Images**):

| PHOTO/HYBRID segments | Minimum scenes that must use a generated image |
|---|---|
| 0 | 0 — an image here is the defect. A pure mechanism/process/code topic gets no photograph. |
| 1 | 1 |
| 2 or more | 2 |

"Uses a generated image" means a scene you authored around `ImageFX`, or an installed
`KenBurnsImage` entry — in both cases with a `public_path` returned by `generate_image`.

Every `type: "generated"` scene-config entry counts toward the 4-scene minimum whatever its
`source`, so a `KenBurnsImage` entry is a real scene, not a freebie. But **at most half the
video's scenes** may be bare `KenBurnsImage` entries with no authored scene — this is a
motion-graphics explainer, not a slideshow of photographs. A PHOTO beat past that share is not a
reason to skip its image: author a scene around `ImageFX` for it instead and give it **motion** the
bare entry does not have — a longer, more deliberate camera move, a slow reframe onto the detail
that matters, something entering or resolving in step with the beat (`examples/ex-ken-burns.tsx`).
Authoring a scene is **not** a reason to put a headline or a caption over the picture; see *the
narration is captioned* above. If a number or a pinned label is genuinely the content, that is the
one case where text belongs here. Authoring a scene is also not a licence to draw *on* the
photograph: that is the HYBRID test below, and it has to be passed on its own terms.

Nothing in `validate_job` can check this floor: it only verifies that image paths which *are*
referenced resolve, so zero images passes it vacuously. The floor is self-enforced, exactly like
the 4-scene minimum above.

### Mandatory: spring() and Easing.bezier for motion

Linear `interpolate` looks robotic and cheap. **Every entrance, exit, or state change must use either:**

```tsx
// spring() — for organic, physics-based motion
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
const { fps } = useVideoConfig();
const y = spring({ frame, fps, config: { damping: 14, stiffness: 120 }, from: 80, to: 0 });

// Easing.bezier inside interpolate — for precise custom curves
import { Easing, interpolate } from "remotion";
const x = interpolate(frame, [0, 30], [0, 500], {
  easing: Easing.bezier(0.16, 1, 0.3, 1), // ease-out expo — snappy entrance
  extrapolateRight: "clamp",
});
```

**Forbidden:** bare `interpolate(frame, [0, N], [a, b])` with no easing for anything visible to the viewer (reveals, slides, fades). Reserve plain linear interpolate only for things like progress bar fill where linear is intentional.

### Forbidden: fake motion via prop-remounting

Do **not** fake animation by mounting the same component at multiple `startFrame` positions with different discrete props:

```json
// ❌ WRONG — produces hard jumps between static states
{ "src": "flow-diagram", "startFrame": 0,   "props": { "step": 1 } },
{ "src": "flow-diagram", "startFrame": 180, "props": { "step": 2 } },
{ "src": "flow-diagram", "startFrame": 360, "props": { "step": 3 } }
```

Instead, write one scene that **animates continuously** through all states using `useCurrentFrame()`:

```tsx
// ✅ CORRECT — continuous frame-driven animation through all states
const step = Math.floor(interpolate(frame, [0, durationInFrames], [0, 3], { extrapolateRight: "clamp" }));
// or: use frame thresholds with spring transitions between states
```

Props are for genuinely distinct **content** (e.g. `props: { title: "…", items: […] }`), not to substitute for animation.

---

## Scene Frequency

**There is no target scene count and no target scene length.** Cut when the visual idea changes,
not on a timer.

The default is **one segment → one scene** (see **Anchoring Scenes to the Narration** below). A
segment is one narration beat with one visual idea, so it is normally one scene, however long that
beat runs. Split a segment only when there is a reason to — see reconciliation rule 2 — never to
reach a number.

A scene that carries one idea for its whole beat, moving continuously the entire time, is better
than the same idea chopped into pieces. Judge the plan by whether each cut marks a genuine change
of visual idea, not by how many cuts it produces.

The only hard number here is the **minimum of 4 generated scenes** per video, which exists solely
to stop a video becoming a slideshow of two or three held frames.

---

## Available Packages

All of the following are installed in the renderer. Import freely.

| Import | When to use |
|---|---|
| `import { spring, Easing, interpolate, interpolateColors } from "remotion"` | All animations — spring for motion, Easing.bezier for easing, interpolateColors for color morphing |
| `import { evolvePath } from "@remotion/paths"` | Draw SVG lines/arrows progressively (replaces static stroke-dashoffset math) |
| `import { noise2D, noise3D } from "@remotion/noise"` | Organic background motion, particle drift, anything that should feel natural not mechanical |
| `import { makeCircle, makeRect, makePolygon, makeStar } from "@remotion/shapes"` | Ready-made SVG shape paths — use as `<path d={makeCircle({radius:50}).path} …/>` |
| `import { loadFont } from "@remotion/google-fonts/Inter"` | Real fonts — Inter, Roboto, Oswald, etc. Replace `fontFamily: "sans-serif"` with loaded fonts |
| `import { TransitionSeries } from "@remotion/transitions"` | Scene transitions *within a generated scene* (sub-scene panels). Do not use at the CompositionBuilder level — that layer already applies crossfades. |
| `import { Img } from "remotion"` | Displaying a generated image. Always `<Img>`, never a raw `<img>` — `<Img>` holds the frame until the image has decoded, a raw one renders black. Usually you want `ImageFX` (below) rather than `<Img>` directly. |
| `import ImageFX from "../../installed/ImageFX"` | **Use whenever the beat's subject is a named character, creature, real person, real place or one specific dramatic/historical moment** — the PHOTO/HYBRID test in **Images**, not optional styling. Ken Burns wrapper for a full-bleed image (pan/zoom/scale/anchor/vignette) that takes your own content as children. Those children are normally **nothing at all** — the picture and its move are the beat, and the narration is already captioned (see *the narration is captioned*). Pass children only for a justified string: a number, or a label pinned to a feature. Only for a beat that passes the HYBRID test in **Images** (the exception, not the norm) write them as a **function** instead, to receive `{ project, scale }` and pin an arrow or label to a feature *in* the picture; see **Anchoring overlays to the image**. Two levels up (your scene lives in `generated/{video_id}/`) and extensionless — either mistake fails `validate_job`. See `examples/ex-ken-burns.tsx` and `examples/ex-hybrid-anchored.tsx`. |
| `import { ThreeCanvas } from "@remotion/three"` | 3D with React Three Fiber. **Opt-in only** — use when 3D clearly elevates the topic (globe, rotating model, 3D diagram). Adds render time. See `examples/ex-three-intro.tsx` for correct usage. |

### Google Fonts usage

```tsx
import { loadFont } from "@remotion/google-fonts/Inter";
// Call at module level, not inside a component:
const { fontFamily } = loadFont("normal", { weights: ["400", "700"], subsets: ["latin"] });

export default function MyScene() {
  return <div style={{ fontFamily }}>…</div>;
}
```

### 3D usage rules (ThreeCanvas)

- ALL animation must use `useCurrentFrame()` — **never** `useFrame` from `@react-three/fiber` (breaks render-time determinism)
- Pass `frame` and `fps` as props into 3D mesh components and drive rotation/scale from them
- `remotion.config.ts` already sets `Config.setChromiumOpenGlRenderer("swangle")` for WebGL support — the renderer container has no GPU, and `swangle` (software ANGLE/SwiftShader) is the renderer that works on GPU-less machines
- See `examples/ex-three-intro.tsx` for the exact pattern

---

## Animation Patterns

| Pattern | API | When to use |
|---|---|---|
| Spring entrance (slide/scale) | `spring({ frame, fps, config: {damping, stiffness} })` | Every intro — never use linear for reveals |
| Eased slide | `interpolate` + `Easing.bezier(0.16,1,0.3,1)` | Fast-in/slow-out lateral movement |
| Staggered list | `spring` per item, `frame - (start + idx * delay)` | Enumerating items one-by-one |
| Continuous state animation | `interpolate(frame, thresholds, states)` + spring between | Multi-step diagrams — replaces prop-remounting |
| Path drawing | `evolvePath(spring(...), pathD)` → `strokeDasharray/strokeDashoffset` | Flow arrows, network diagrams, timelines |
| Organic background | `noise2D("seed", frame/80, 0) * amplitude` | Particles, waving grids, anything ambient |
| Shape animation | `makeCircle/makeRect/makeStar` path → `<path transform="scale(...)">` | Animated icons, charts, callouts |
| Color morph | `interpolateColors(frame, [f0,f1], ["#hex","#hex"])` | Before/after comparison, state changes |
| Number ticker | `Math.round(interpolate(frame, [start,end], [0,target], {easing:…}))` | Statistics, counters, capacities |
| Scale pulse | `1 + 0.06 * Math.sin(frame * 0.15)` | Subtle "alive" micro-motion on a holding element |
| Ken Burns over a real subject | `ImageFX` with `scaleFrom`/`scaleTo` + `panFrom`/`panTo` | Any beat whose subject is a person, creature, place or one specific event — normally the image with type over it (PHOTO), and only where the beat turns on *where* or *in what order* with an SVG structure overlay anchored to it (HYBRID). See **Images** |

---

## scene-config.json Structure

```json
{
  "totalFrames": <copy from timeline.totalFrames>,
  "fps": 30,
  "canvas": "dark",
  "subtitles": { "maxWords": 4 },
  "scenes": [
    {
      "type": "generated",
      "src": "intro-hook",
      "startFrame": 0,
      "durationInFrames": 150
    },
    {
      "type": "generated",
      "src": "flow-diagram",
      "startFrame": 150,
      "durationInFrames": 600
    }
  ],
  "sfx": [],
  "music": { "src": "/public/{job_id}/music.mp3", "volume": 0.12, "startFrame": 0, "fadeOutFrames": 45 }
}
```

Rules:
- `totalFrames` = `timeline.totalFrames` — never guess, copy exactly
- `fps` = 30 always
- `canvas` = `"dark"` under `motion_graphics`, `"light"` under `stick`, your recorded choice under
  `auto`. One value for the whole video — there is no per-scene canvas, because scenes that
  disagree flash. A value contradicting the canvas the video has already settled on is rejected;
  omitting it is filled in for you, but write it anyway so the file says what the video is
- `subtitles` is optional and **on when omitted** — see **Subtitles** below
- `music` is optional — omit if not used
- No `TextReveal` scene type
- `startFrame + durationInFrames` must not exceed `totalFrames`

### Subtitles

The narration is captioned automatically, above every scene, from its own word timings. **This is
on by default.** You do not author the captions and you do not place them; you only choose how
they look, and the defaults are already reasonable, so most videos should leave the key out
entirely.

```json
"subtitles": { "maxWords": 4, "fontSize": 62, "background": "pill", "position": 0.78 }
```

| Key | Default | Notes |
|---|---|---|
| `enabled` | `true` | See below before setting `false` |
| `maxWords` | `4` | **1–7.** How many words are on screen at once. The spoken word is at full strength and its neighbours are dimmed, so the line reads as it is said. Lower is punchier and moves more; higher is calmer. Past 7 the viewer is reading a paragraph instead of following the voice, and the call is rejected |
| `fontFamily` | container default | A CSS family, or one of `Inter`, `Oswald`, `Roboto`, `Montserrat` |
| `fontSize` | `62` | 28–120 |
| `color` | `null` | `null` follows the canvas — black on light, white on dark. Set one only for a real reason |
| `background` | `"pill"` | `"pill"`, `"shadow"` or `"none"`. `"pill"` is the safe choice over busy imagery |
| `position` | `0.78` | Vertical centre as a fraction of frame height |
| `uppercase` | `false` | |

Match them to the video: a playful topic can take a tighter `maxWords` and `uppercase`; a serious
one is better at the defaults. On a light canvas check the contrast — `"pill"` handles it.

**Turning them off.** You may set `"enabled": false`, but only when you can say why this specific
video is better without captions, and you must state that reason in your handback. "The scenes
already have text" is not a reason — it is the problem; remove the text instead. Silence about it
is treated as a mistake, not a choice.

**This is what makes on-screen text unnecessary.** Read *the narration is captioned* in
**Animation Philosophy** before you write a single string into a scene.

### Optional: `transitionToNext`

Add `transitionToNext: { durationInFrames: N }` to a scene to control the crossfade OUT of it into the next. Default (when omitted) is 8 frames. Set `durationInFrames: 0` to hard-cut.

```json
{ "type": "generated", "src": "intro-hook", "startFrame": 0, "durationInFrames": 150,
  "transitionToNext": { "durationInFrames": 12 } }
```

---

## Anchoring Scenes to the Narration

### Primary path — segment-anchored planning (use whenever available)

Check `get_video`'s `script_segments` (an ordered list of `{id, voice, visual}` beat objects)
and `get_timeline`'s `segments` array (an ordered list of `{id, startFrame, endFrame}`, written
by `generate_voice` only when the video has `script_segments`). **If both are present, this is
the only planning method to use — do not fall back to keyword-guessing.**

Match each entry in `script_segments` to its frame span by `id` in `get_timeline`'s `segments`. That
segment's `[startFrame, endFrame]` is the exact frame range the sentence it corresponds to is
spoken over — use it as the scene-boundary anchor. Use the segment's `visual` text as the
authoring brief for what to actually build/show across that span (broll, animation, diagram,
whatever it describes). Do not source scene content from anywhere else — `visual` is the brief,
by design (see `tubematic-create-script-writing-skill`'s Segmented Output Format item, which
produces it for exactly this purpose).

**Reconciliation rule — segment spans vs. the min-4-scenes floor below.**
Default: one segment → one scene, with `startFrame`/`durationInFrames` taken directly from the
segment's span. This is the real default, not a nominal one — most segments in most videos should
come through as exactly one scene each. Deviate from it only in these cases:

1. **A very short segment.** First try merging it with the adjacent segment (before or
   after — whichever is the better narrative fit) into one scene, but *only* if the two segments'
   `visual` briefs describe content that can genuinely share a single continuous scene (e.g. one
   extends or continues the other's broll/animation idea). A merged scene's span is the union of
   the two segments' frame ranges — its far boundary (the side facing the segment *not* merged
   in) is still a segment boundary, so this never violates rule 3 below. If the two `visual`
   briefs are unrelated and don't compose into one scene, do **not** force the merge — leave the
   short segment as its own scene. A brief scene is preferable to blurring two unrelated visual
   ideas into one.
2. **A segment whose visual idea genuinely needs more than one scene — the exception, not the
   rule.** Length alone is never the reason. Split a segment only when one of these holds:
   - the `visual` brief itself names **distinct sub-beats** (e.g. it describes a command being
     typed *and then* its output being highlighted — two visual states, not one), or
   - a single visual idea genuinely cannot carry the whole span, judged on the content itself.

   When neither holds, leave the segment as one scene however long it runs. A long span is not a
   problem to be solved by cutting: **continuous internal motion carries a long scene without a
   cut** — a Ken Burns move that drifts across the full `durationInFrames`, a diagram that keeps
   building, a counter still climbing. That is what the **Animation Philosophy** continuous-motion
   rule asks for, and splitting is not how you satisfy it. Splitting to fill time produces a cut
   with no idea behind it, which is exactly the over-cutting that rule forbids.

   When you *do* split, keep every sub-scene inside that one segment's span (rule 3), keep all of
   them faithful to the same `visual` brief (introduce no new content), split at the sub-beats the
   brief names, and set `transitionToNext: {"durationInFrames": 0}` between them. A crossfade
   signals "new idea"; sub-scenes of one segment are the same idea progressing, so they should
   hard-cut. This is consistent with
   `tubematic-create-script-writing-skill`'s "one segment drives one downstream scene" framing —
   that is the default on both sides; multiple entries are the documented exception when the
   brief's own content calls for them.
3. **Never let one generated scene span part of one segment plus part of the next.** Merging
   (case 1) and splitting (case 2) both keep every scene boundary aligned to a segment boundary —
   a scene may cover multiple whole segments (merge) or a fraction of one segment (split), but
   never a fraction of two different segments. Crossing a segment boundary without a clear
   content reason is exactly the failure mode this feature exists to prevent: it desyncs the
   visual from the sentence being spoken over it.
4. **Fewer than 4 scenes after the above (minimum-scene floor).** The 4-scene minimum is a hard
   rule and wins over the segment-per-scene default. If planning (after any merges) still produces
   fewer than 4 scenes — e.g. a short script with only 2–3 segments — split the longest remaining
   segment(s) until the minimum is met, even without distinct sub-beats stated in `visual`. This
   is the one case where splitting to reach a number is correct; it exists to keep a very short
   script from being three held frames, and it is the *only* count-driven split in this skill.
   Split at the most natural content boundary you can find in the brief, and give the resulting
   sub-scenes hard cuts between them as in case 2.
5. **Exact 0 → `totalFrames` coverage at the edges.** ElevenLabs word alignment is not always
   frame-perfect at the very start/end of the audio, so a segment's own `startFrame`/`endFrame`
   may be off by a few frames from 0/`totalFrames`. Clamp the first scene's `startFrame` to `0`
   and the last scene's end (`startFrame + durationInFrames`) to `totalFrames` regardless of what
   the segment span says.
6. **No-gap coverage between segments.** `timeline.segments` may have a small natural gap between
   one segment's `endFrame` and the next segment's `startFrame` (a TTS pause at a sentence
   boundary) — this is expected in `timeline.json` and is not itself an error. `scene-config.json`
   must still have zero gaps regardless: extend each scene's `durationInFrames` so it runs up to
   the next scene's `startFrame` exactly (i.e. anchor scene boundaries to `startFrame` values, not
   strictly to `endFrame - startFrame`), so the pause frames land inside whichever adjacent scene
   makes more sense to hold on, rather than opening a gap in `scene-config.json`.

### Legacy fallback — keyword anchoring (only when `script_segments`/`timeline.segments` are absent)

For old jobs that predate segments (no `script_segments` on the video, or `get_timeline`'s
`segments` array is empty), fall back to the original keyword-guessing approach: call
`get_timeline(video_id, include_words=True)` for the per-word alignment, then prefer placing scene
transitions at the frame where a keyword is spoken.

```python
def frame_of_word(words, keyword):
    for w in words:
        if keyword.lower() in w["word"].lower():
            return w["startFrame"]
    return None

start = frame_of_word(timeline["words"], "packet") or total_frames // 4
```

Fall back further to equal proportional splits when no clear keyword anchor exists. This path has
no visibility into segment/visual structure, so scene content must be inferred from the flat
`script` field and the keywords themselves — it remains strictly worse than the primary path
above and should only be used because no better information exists for that video.

---

## Images

**Read *Visual Registers* first.** The subject test below is unchanged — it still decides which
beats get a generated image — but a fourth treatment (STICK) is available for generic roles under
`auto` and `stick`, and on a light canvas an image beat is framed in a `PanelImage` rather than
going full-bleed. The silhouette rule below applies on either canvas, word for word.

Some beats want a photograph or illustration, not a diagram. Decide from the beat's **subject**, not
from whether its `visual` brief happens to use the word "photograph" — briefs are written before any
scene exists and routinely say "map", "diagram" or "stat card" out of habit for beats whose subject
is a person, a creature or a place. Reclassify freely: the brief tells you what the beat is *about*,
you decide how it is *shown*.

**The test — what is this beat's subject, and does the viewer want to see it or track it?**

| Treatment | The beat's subject is | Do this |
|---|---|---|
| **PHOTO** | A named character or real person (Aemond Targaryen, Grace Hopper); a creature or animal; a specific real place or structure (the Dragonpit dome, a data-centre hall); one specific dramatic or historical moment (an ambush, a launch, a signing); a physical object with a distinctive look; or a mood/establishing beat | `generate_image`, then an installed `KenBurnsImage` entry (if the image and its move are all the beat needs, which is the usual case) or a scene wrapping `ImageFX` |
| **HYBRID** | Any of the above, *plus* structure the viewer must track **and cannot get from the narration** — who moved where, in what order, from which direction, how many. The exception, not the peer of PHOTO: it has to pass the test below | `generate_image` for the subject, `read_image` to see where it landed, then author a scene that draws that one piece of structure over `ImageFX` — anchored to the image via its render-prop, never at hardcoded screen positions. See **Anchoring overlays to the image** |
| **DIAGRAM** | A relation, not a thing: a process with stages, a before/after comparison, a mechanism or dataflow, counts and quantities, timing, cause and effect, code or terminal output | SVG/vector scene, no image |

**"Structural or explanatory" does not mean DIAGRAM.** If the actors inside the structure are named
characters, creatures or real places, never substitute an abstract silhouette, icon or marker for
the subject itself — generate the image. A battle, ambush, siege, duel, expedition or assassination
has stages *and* has subjects the viewer came to see: those are **never DIAGRAM**. They are PHOTO by
default, and HYBRID only where the beat turns on *where* or *in what order*. DIAGRAM is for topics
whose subject genuinely has no appearance: a protocol handshake, a memory allocator, a scheduler.

**PHOTO is the default for anything photographic; HYBRID has to earn the overlay.** Before drawing
anything on an image, name in one sentence the specific thing the overlay tells the viewer that the
narration and the picture do not — *which* of the three moved, in *what order*, from *which*
direction, *how many*. If you cannot name it, the beat is PHOTO: generate the image, give it a Ken
Burns move, and let the narration carry the rest.

These are **not** reasons to go HYBRID:

- To make the beat feel animated. The `ImageFX` camera move already animates every frame.
- To restate visually what the narration just said in words.
- The beat felt bare. A photograph of the subject with a slow drift is a finished scene, not a
  placeholder. (It used to be "with a caption" — it is not, any more; see *the narration is
  captioned*.)
- It is a battle / a chase / a dramatic moment. Drama is a PHOTO signal, not a structure signal.

Arrows, markers and labels the viewer did not need are the most common way an image beat is made
*worse*: they cover the subject the image was generated for and read as clip-art pasted on a
photograph. When in doubt, leave the picture alone.

| Brief as written upstream | Subject | Treatment |
|---|---|---|
| "Overhead tactical map, army icon crawls toward Rook's Rest" | A real army marching on a real castle | **HYBRID** — generated image of the castle and coast, march-route arrow animated over it. The beat turns on *which way they came*, which the words alone don't give |
| "Split diagram: troops besieging the castle, dragon in the sky above" | A dragon, in one specific ambush | **PHOTO** — generated image of the dragon over the burning field, Ken Burns move, no text. The viewer came to see the dragon; an arrow pointing at it tells them nothing, and so does a caption naming it |
| "Establishing shot of the Dragonpit dome at night" | A real structure, mood | **PHOTO** — a bare `KenBurnsImage`. Nothing to label; the narration is captioned |
| *(the same brief as the row above)* — built as a reticle on the dragon, a "VHAGAR" badge, a stage counter and a connector line | A dragon | **The defect this section exists to prevent.** Every mark restates the narration and covers the subject. Not a richer treatment than the row above — a worse one |
| "Stat cards fade in: small garrison, minor holding, PERFECT BAIT" | The relative worth of a holding | **DIAGRAM** — no image |
| "Cut to terminal showing whoami output" | Command output | **DIAGRAM** — no image |
| "Memory-allocation diagram, 4 boxes filled of 8" | An allocator's behaviour | **DIAGRAM** — no image |

For every PHOTO/HYBRID beat:

1. Call `generate_image(video_id, image_name, prompt)`. The provider and model come from settings —
   you don't choose them. Write a detailed prompt: subject, composition, lighting, style.
   Images come back portrait, matching the 9:16 frame almost exactly — so compose for the full
   vertical frame, and describe placement in it ("subject centre-left, horizon low"). Leave
   `aspect_ratio` at its default; any other value gets cropped hard to fit the frame.
   **For a HYBRID beat, ask for the trackable subject CENTRALLY** — "the castle centred, filling
   the middle third". The camera move shows only part of the image at a time, so a subject near an
   edge leaves the frame partway through the scene, taking your arrow with it. The prompt is the
   only lever you have over this.
2. Call `read_image(video_id, image_name)` and look at what came back. Reject and regenerate a bad
   image here — wrong subject, mangled anatomy, garbled text baked into the picture — rather than
   discovering it in AI review with a whole render already spent. For a HYBRID beat this is also
   where the overlay coordinates come from; see **Anchoring overlays to the image**.
3. Copy the returned `public_path` **verbatim** into your scene's props. Do not build the string
   yourself — the file extension follows whatever the model returned and isn't knowable in advance.
   Do not wrap it in `staticFile()`, which throws on an already-prefixed path.
4. Display it through `ImageFX` (or the ready-made `KenBurnsImage` installed scene), never as a
   bare static image — a motionless photo violates the continuous-motion rule.

A still image with no camera move is the single most common way these scenes look cheap. Always
give it a slow drift: `ImageFX` clamps the pan to whatever overhang the zoom leaves, so you cannot
accidentally expose an image edge no matter what values you pass.

If the image is all the beat needs, skip authoring a scene entirely and reference the installed
`KenBurnsImage` from scene-config.json:

```json
{
  "type": "generated", "src": "KenBurnsImage", "source": "installed",
  "startFrame": 150, "durationInFrames": 120,
  "props": {
    "src": "/public/{video_id}/images/harbour.png",
    "scaleFrom": 1.25, "panFrom": [-0.05, 0], "panTo": [0.05, 0],
    "vignette": 0.4
  }
}
```

Author your own scene wrapping `ImageFX` only when you need custom content over the image —
`examples/ex-ken-burns.tsx` is the template.

### Anchoring overlays to the image

Once a beat has passed the HYBRID test above, this is what makes it work.
`examples/ex-hybrid-anchored.tsx` is the worked template. If the beat did not pass that test, none
of this section applies — go back and build it as PHOTO.

**Overlay coordinates come from the image, never from the prompt you wrote.** You asked for a
castle on the lower-left headland; the model may have put it centre-right. Call `read_image` and
read the position off the grid it draws — u left-to-right, v top-to-bottom, both 0 → 1.

**Then anchor it, because the image moves.** `ImageFX` pans and zooms the photograph every frame,
but overlay content is a *sibling* of the image, not a child of it — so an arrow at a fixed screen
position is right for one instant and sliding off-target for the rest of the scene. Write
`children` as a **function** to opt into the anchor API:

```tsx
<ImageFX src={imageSrc} durationInFrames={durationInFrames} scaleFrom={1.22} scaleTo={1.05}>
  {({ project, scale }) => {
    const tip = project(0.46, 0.38);   // [u, v] read off read_image's grid
    return <svg width={1080} height={1920}>{/* draw to tip.x / tip.y */}</svg>;
  }}
</ImageFX>
```

`project(u, v)` returns `{ x, y, visible }` for the current frame. Plain elements still work
unchanged for content that doesn't depend on the picture — on the rare beat that has any.

Four rules:

- **Draw the minimum that carries the information.** One anchored element, plus a label if the thing
  it points at needs naming. Not reticles, corner brackets, stage badges, counters, connector
  lattices or frame furniture. Every mark that isn't carrying the sentence you named in the HYBRID
  test is competing with the subject the image was generated for — and a beat that needs several
  such marks is usually two beats, or a DIAGRAM one.
- **Keep the target central — roughly `u, v` between 0.22 and 0.78.** At a peak zoom of 1.22–1.28
  only about 80% of the image is on screen at once, and the pan slides that window around, so a
  subject nearer an edge genuinely leaves the frame partway through. This is the same reason the
  `generate_image` prompt has to ask for a central subject.
- **The arrow tip goes on the subject; the label goes in the safe zone.** A projected point can
  legitimately land at y = 1850, under the platform UI. Pin the text inside x 60–1020, y 150–1750
  and connect it to the tip with a leader line.
- **Fade, don't pop.** Use `visible` (or a soft margin around the frame edge, as the example does)
  so an annotation retreats gracefully instead of pointing at nothing.

**Report your classification.** If the video used more than one vocabulary, **say in one sentence
why each was required** — that sentence is the check against reaching for variety, and an entry you
cannot justify is one to rebuild rather than report. Your handback to the operator must open with
the video's `visual_style` and the canvas — and for `auto`, why you chose that canvas (image-led or
animation-led) — then list every segment id with its treatment and what you built for it:

    seg-1 HYBRID → image castle-approach + march-route overlay scene
                   (overlay says: the army came from the north headland, not the harbour)
    seg-2 DIAGRAM → stat-card scene, no image
    seg-3 PHOTO  → image meleys-descent, KenBurnsImage entry

Then one line on text: either **"no on-screen text"**, or each string you kept with the reason it
survived the test in *the narration is captioned* (a number, a pinned label, a term, a literal, a
chart axis). And, only if you turned subtitles off, why this video is better without them.

Both labels are claims you are making on the record, and each has its own failure mode:

- **DIAGRAM** — an all-DIAGRAM list for a topic full of named characters, creatures or real places is
  precisely the failure this section exists to prevent. If the list holds any PHOTO or HYBRID entry
  and no scene carries an image prop, you are not finished — go back and generate those images.
- **HYBRID** — every HYBRID line must carry the sentence from the test above, saying what its overlay
  tells the viewer. If you can't write that sentence, the entry is PHOTO. A list where most image
  beats are HYBRID is the other failure: it produces a video whose photographs are buried under
  marks nobody needed.

**A missing image fails the render.** Remotion's `<Img>` retries twice and then aborts, so the
video lands in `REVISION_REQUESTED` with a wasted render behind it. `validate_job` catches a bad
path first — that's why it runs before `submit_render`.

---

## Scene Component Requirements

Every generated `.tsx` file must:
1. Accept `durationInFrames: number` and `words?: TimelineWord[]` as props
2. Use `const frame = useCurrentFrame()` as the sole source of animation state
3. Set `backgroundColor` on its root `AbsoluteFill` (full-screen — no transparent backgrounds).
   **The one exception is the `stick` register**, where the renderer paints the white canvas for
   the whole video and your scene must leave its background alone; see **Visual Registers**
4. Contain at least **two independently animated elements using spring or Easing**
5. Keep all content inside the YouTube Shorts safe zone: x 60–1020, y 150–1750 (canvas 1080×1920).
   **Measured, not eyeballed:** `validate_job` renders settled frames of your scene in a real
   browser and reports any text crossing that box, with the frame number and the text itself
6. Never print text over other text. Two text elements whose boxes materially overlap are a defect,
   not a layering effect — the same audit reports these as an overlap percentage. Stacked lines are
   fine; what fails is two absolutely-positioned blocks whose
   spans collide once both have finished animating in
7. Never hold a static frame for more than ~10 frames — there must be visible motion at all times
   (a continuous `ImageFX` pan/zoom satisfies this on its own — it moves every frame).
   **Motion-graphics register only**: the `stick` register holds deliberately and changes state in
   single frames, 2–5 times per 10 seconds of audio
8. Import `ImageFX` **without** the `.tsx` extension — a suffixed import fails `tsc --noEmit`,
   which fails `validate_job`

---

## File Locations

| File | How to write / read |
|---|---|
| timeline.json | `get_timeline(video_id, include_words=False)` MCP tool → reads `/jobs/{video_id}/timeline.json`. **Never** read this file directly — the path is container-absolute and unreachable from the agent sandbox or the host. |
| Scene TSX files (authored) | `write_scene_file(video_id, scene_name, tsx_content)` MCP tool → `/app/remotion/src/scenes/generated/{video_id}/{scene_name}.tsx` (persists to `~/.tubematic-data/scenes/generated/{video_id}/` on the host). Returns `src` — paste it verbatim into scene-config. |
| Scene TSX files (reused from `installed/`) | Not written — reference an existing file in `/app/remotion/src/scenes/installed/` via `"source": "installed"` |
| Scene TSX files (reused from `generated/`) | **Written** — `read_scene_file` the prior video's TSX, then call `write_scene_file` again with your own `video_id` to copy it into your own folder (`source` omitted or `"generated"` either way; see **Reusing Existing Scenes** above) |
| Reading any scene TSX | `read_scene_file(scene_name, video_id="", source="generated")` MCP tool. Takes either the composed `"{video_id}/{scene_name}"` (what `list_scene_files` and a scene-config `src` hand you — paste it through) or the bare stem plus `video_id`. `source="installed"` reads the curated library. A scene-config entry's `src` and `source` are a **pair** — passing an installed entry's bare `src` without `source="installed"` searches `generated/` instead, and reads a different video's legacy flat file if one shares the name. **Never** open a `.tsx` with your own file tools — the directories are container-absolute and unreachable from the agent sandbox or the host. |
| Generated images | `generate_image(video_id, image_name, prompt)` MCP tool → `/jobs/{video_id}/images/{name}.{ext}`. Use the `public_path` it returns as the scene prop; never construct that string yourself. |
| Looking at a generated image | `read_image(video_id, image_name)` MCP tool — returns the picture itself with a labelled `[u, v]` grid. The only way to see one: the files are container-absolute and unreachable from the agent sandbox or the host, so your own file tools cannot open them. |
| scene-config.json | `write_scene_config(video_id, config)` MCP tool → `/jobs/{video_id}/scene-config.json` (persists to `~/.tubematic-data/jobs/{video_id}/` on the host); also saves `scene_config_path` on the video record |
| Reading scene-config.json | `get_scene_config(video_id)` MCP tool → `{video_id, config, path}`. The only way to read it — `scene_config_path` is container-absolute and unreachable from the agent sandbox or the host. Required by the revision branch; also the entry test's `totalFrames` source. |

For `source: "generated"`, the `src` field in scene-config.json is the composed
`"{video_id}/{scene_name}"` that `write_scene_file` returns — paste it verbatim, do not build it
yourself. (For `source: "installed"`, `src` stays a bare filename stem.) Call `write_scene_file`
for every scene you author or copy (`source` omitted or `"generated"`) before the operator calls
`validate_job` — the renderer will fail if a referenced scene file is missing from the directory
its `source` points at.

---

## Validation Checklist

Before handing back to the operator:
- [ ] Canvas settled and reported: `visual_style` read from `get_video`, and under `auto` a
      `resolved_visual_style` (`"dark"` or `"light"`) written with `update_video` **before** any
      scene was authored
- [ ] `canvas` in the config matches it — `"light"` for `stick`, `"dark"` for `motion_graphics`,
      your recorded choice under `auto`
- [ ] Every `StickFigure` / `StickScene` passes the `theme` matching the canvas. A black figure on
      a dark canvas is a silhouette of nothing, and it typechecks
- [ ] On a light canvas: no scene sets its own background; no bare `KenBurnsImage` or full-bleed
      `ImageFX`; any `StepFlowDiagram` entry passes `theme: "light"`
- [ ] No named, specific person, creature or place drawn as a stick figure — that is still a
      generated image, full-bleed on dark or panel-framed on light
- [ ] Under a forced `motion_graphics`: no figures anywhere
- [ ] **Every vocabulary used is one a beat's subject required.** Nothing was added for variety,
      pacing or visual interest; no treatment appears in exactly one beat without a reason you
      could state in one sentence. Under `auto` especially — a permission is not an instruction
- [ ] Under `auto`, generated characters only if `get_video` reports
      `illustrated_available: true`; otherwise line art, and the handback says why
- [ ] Under `illustrated`, every character was generated with `generate_character` — no key
      pre-check, no line-art fallback
- [ ] Characters are all one kind — every one hand-drawn, or every one generated. A line-art figure
      beside a rendered one reads as a broken asset, not a style
- [ ] Generated characters share **one drawing style**, chosen from the topic and stated in the
      handback — cartoon throughout, or rendered throughout, never both
- [ ] Under `illustrated` or a character-bearing `auto`: every pose was generated with
      `reference=` pointing at the SAME canonical sheet, never chained pose-to-pose
- [ ] Every character asset was opened with `read_image` and judged on **"is this still the same
      character"**, not merely "is this usable"
- [ ] Every panelled image either has a panel sized to the image's real `width`/`height` ratio, or
      an explicit `focus` read off `read_image`'s grid. No panel left to the default centre-crop
- [ ] Ran the entry test in **Revising an Existing Video** — a video with an existing config whose
      `totalFrames` still matches `timeline.total_frames` was revised, not re-derived
- [ ] Checked `list_scene_files(source="all")` before authoring — reused an installed or generated fit if one existed
- [ ] `scene-config.json` written via `write_scene_config(video_id, config)` — never with your own file tools
- [ ] `totalFrames` matches `timeline.totalFrames` exactly
- [ ] No scene exceeds `totalFrames`
- [ ] Scenes cover frame 0 → `totalFrames` with no gaps
- [ ] Every newly-authored or copied `src` value written via `write_scene_file(video_id, ...)` —
      confirm with `list_scene_files(source="generated", video_id=video_id)`; every `installed/`
      reuse has `"source": "installed"` set
- [ ] No `TextReveal` scene type present
- [ ] **Every string of on-screen text passes the test in *the narration is captioned*** — for each
      one, removing it would lose information the motion, the image and the subtitles don't already
      carry. No headlines, no title cards, no lower thirds, no captions under pictures, no
      pull-quotes of the narration
- [ ] Subtitles left on, or `"enabled": false` set **with the reason stated in the handback**
- [ ] Scene count driven by the narration's visual beats, not by a cadence target — one segment →
      one scene by default, and any segment realized as multiple scenes had a reason (its `visual`
      brief named sub-beats, one idea couldn't carry the span, or the 4-scene floor required it)
- [ ] Every scene animates across its **whole** span, not only at its entrance — motion keyed to
      `durationInFrames`, not to fixed frame constants
- [ ] Every TSX uses `useCurrentFrame()` — no CSS animations
- [ ] Every entrance/exit uses `spring()` or `Easing.bezier` — no bare linear interpolate for visible motion
- [ ] No prop-remounting anti-pattern — multi-step diagrams animate continuously within one scene
- [ ] Every segment id classified PHOTO / HYBRID / DIAGRAM **by subject**, and the list reported in the handback
- [ ] Image floor met: ≥1 image scene if one segment is PHOTO/HYBRID, ≥2 if two or more are — and no images at all if every segment is DIAGRAM
- [ ] No PHOTO/HYBRID subject drawn as an abstract SVG stand-in (silhouette, icon, marker) in place of a generated image
- [ ] Every segment classified HYBRID names, in the handback, the one thing its overlay tells the
      viewer that the narration and the picture don't — anything that can't is PHOTO
- [ ] No image beat carries marks it didn't need — no reticles, badges, counters or connector
      furniture on a PHOTO scene, and nothing beyond the anchored element and its label on a HYBRID one
- [ ] Every generated image looked at via `read_image` before the scene using it was authored — and any unusable one regenerated, not shipped
- [ ] Every HYBRID overlay position read off `read_image`'s grid and passed through `ImageFX`'s `project(u, v)` — no hardcoded screen coordinates for anything that points at the picture
- [ ] Every image prop is a `public_path` returned by `generate_image`, copied verbatim — not hand-built, not wrapped in `staticFile()`

On the revision branch, additionally:
- [ ] Only the scenes named in `gemini_feedback` or the human comment were read and rewritten
- [ ] Every other config entry carried through exactly as `get_scene_config` returned it — same
      `startFrame`, `durationInFrames`, `src`, `source`, `props`, image paths — and `totalFrames`
      is unchanged
- [ ] No `generate_image` call was made for a beat whose image was not the reported defect; any
      image that *was* the defect was regenerated under its **same** `image_name`
- [ ] Rewritten scenes reused their original `scene_name`, so no `src` moved
