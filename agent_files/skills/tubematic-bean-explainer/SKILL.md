---
name: tubematic-bean-explainer
description: Author a Bean Explainer narrated Short as data — split the narration into list sections and shots, cast the house bean, pose it on the narrator's words, build each shot from the prop library (drawing a prop of your own, modelled on the library, when it lacks one) with labels, marks and red strikes — then write it with write_scene_config, preview your props, validate and submit it
---

# Tubematic Bean Explainer authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-bean-explainer` (its `visual_style` is `bean_explainer`). Also take it, on **Revising**, for
a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short in the cartoon-bean listicle look: a bald, big-headed cream character with a
thick black outline (the **bean**) stands on a flat, saturated colour field and reacts to the
narration pose by pose, while props pop in beside it one at a time and short handwritten labels name
them. A rounded capital **header** and a coloured **badge** name the current section; in a list video
a strip of badges slides sideways between sections. Captions sit on the grey floor below, with the
key word of a line on a red box.

The look is **snap, then hold**: a pose swaps in two frames on a word and then stays still; a prop pops
in and stays until the next cut. The motion comes from many small changes, so plan something new at
least every 1.5 to 3 seconds.

**You write data, never code.** The whole video is one installed scene, `BeanExplainer`, and
everything about this video is its `props.beanExplainer`: the cast, the sections, and the shots with
their events timed to the narration. The bean, every prop, the layout of the header and the captions
are drawn by the renderer. There are no images in this style: never call `generate_image` or
`generate_character`. Props come from the library in `reference/contract.md`; when it has nothing
for a thing the viewer must recognise, you draw that one prop yourself, modelled on the library
(**Step 2b**).

The full field reference and the prop catalogue are in `reference/contract.md`; the worked example is
`reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three
before you write.

## Rules the tools enforce

`write_scene_config` refuses a Bean Explainer config that breaks any of these, and says which shot or
event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "BeanExplainer", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"beanExplainer":
  {...}}}`.
- **Shots** are cuts: the first starts at frame 0, the others on a word (within 2 frames of a word's
  `startFrame`), each at least 1.5 seconds long, at most 40 shots.
- **Sections** start where a shot starts, each at least 2 seconds long, at most 12. A list video
  (`"list": true`) has at least two sections; every section after the first opens with the badge
  carousel, and that shot's events start 30 frames after the section does.
- **Poses** land on a word (within 2 frames of its start), and one bean's poses are at least 8 frames
  apart. `at` goes only on a `point`, `present` or `lean` pose: no other pose reaches for anything.
- **A shot holds** at most 6 props and labels together (the beans do not count), at most 24 events,
  listed in frame order. An event ends at least 6 frames before the next cut.
- **Layout:** everything stays on the stage (between the header and the floor, inside the side
  margins). A label may not overlap a prop, a bean or another label; a prop may not overlap a bean,
  where the bean stands while the prop is on stage. A bean that changes `x` hops there, and the hop
  covers the ground between its two spots, so do not hop across a prop. Props may overlap each other
  (a cursor on a phone, a magnifier on an address bar).
- **Labels** are at most 2 lines of 22 characters, and never repeat 4 or more narration words in a
  row: the captions already say them.
- **Props, poses, faces, marks, accessories, tints and acts** come from the catalogue or your
  `customProps`; a prop's text stays within its slot's limit; an act starts once its prop has landed
  (10 frames after it appears).
- **Your own props:** at most 8 per video, each a `prop-<name>` file of this video that exists before
  the config is written, with a box of 60 to 700 px a side, a text slot of at most 40 characters and at
  most 4 acts. The file default-exports the drawing, imports only `react`, `remotion` and
  `../../installed/beanExplainer/props/common` (or `bean`, `contract`), and uses no filter, gradient,
  pattern, dashed stroke, image, fetch, randomness or clock.
- **Never still:** something new (an event or a cut) at least every 3 seconds.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments, and
   `mascot`.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here, and a word's index in this list is
   what `subtitles.emphasis` uses.

## Step 1 — sections and shots

**Sections.** If the script is a list ("First…", "Next…", every port, every habit), each item is a
section and `list` is `true`: its `header` is the item's name in capitals (at most 18 characters), its
`color` one of the section colours (vary them), its `badge` the prop that stands for it. A script that
is not a list has one section, or none for a short intro, and `list` is `false`. An intro before the
first item is a shot with no section (it shows only the `title`, the series line at the top, at most
40 characters).

**Shots.** Inside a section, cut to a new shot when the narration moves to a new picture: a new
example, a before and after, the consequence. One shot is one small scene on the stage; two to four
shots per section is usual. A shot starts empty.

## Step 2 — the cast

`cast` is the narrator (`{"id": "narrator"}`) and, only when the story needs a second person (the
scammer, the boss, a friend), one other (`{"id": "other"}`). Give each an `accessory` that says who
they are (the narrator usually `none`; the other `glasses`, `cap`, `tie`, `headset`, `hardhat` or
`beanie`) and give the other a `tint` different from the narrator's (`cream` is the default). With two
beans on stage both are drawn smaller; keep them apart (x 0.2 and 0.8).

## Step 2b — a prop the library does not have

Use a library prop whenever one fits; use a text-carrying prop (`sign`, `note`, `document`, `speech`)
when the thing is really a word or a name. Draw your own only for an object the viewer must recognise
that the library lacks: a rocket, a car, a tooth. Keep it to a few per video.

1. Read the closest library props and the helpers they use: `read_scene_file` with
   `source="installed"` and `scene_name` `beanExplainer/props/thingProps` (tech, time and feeling),
   `beanExplainer/props/lifeProps` (money, health and the body), `beanExplainer/props/textProps` (the
   text-carrying ones) and `beanExplainer/props/common` (the palette, the `ink` line, `FitText`,
   `actRamp`). `reference/example-prop-rocket.tsx` is a finished one.
2. Draw it the same way: one component, centred on (0, 0) inside a `w` x `h` box at scale 1 (in
   pixels, outline included); the bean's line (`{...ink}`); flat fills from the palette; big simple
   shapes that read at phone size (a library prop is 150 to 600 px wide). It receives `frame`, `actT`
   (frames since its act started, -1 before), `text`, `round` and `hand`. If it has a text slot, draw
   `text` with `FitText`. An act named `shake`, `swing`, `wobble`, `spin`, `beat` or `buzz` moves the
   whole prop for you; any other act name you declare is yours to draw from `actT`, and must end in a
   resting state within 60 frames.
3. Write it with `write_scene_file(video_id, "prop-<name>", tsx)` and list it in `customProps`:
   `{"id": "rocket", "src": "<the src write_scene_file returned>", "w": 220, "h": 530, "acts":
   ["launch"]}` (add `"text": 20` for a text slot). Its `id` is then used like a library prop's.
4. After `write_scene_config`, call `render_bean_props(video_id)` and look at the picture. Ink outside
   the red box means the box is too small: raise `w` and `h` (the layout checks use them) or shrink the
   drawing. A drawing that does not read as the thing at a glance, a line thinner than the library's,
   or colours outside the palette: redraw it. Rewrite the file and call `render_bean_props` again; three
   looks at most. `validate_job` typechecks the file and checks it against the rules above again, so a
redraw is held to them too.

## Step 3 — events, timed to the words

| Event | When | Fields |
|---|---|---|
| `pose` | the bean reacts: a new pose or face on the word that causes it | `who`, `pose`, `face`, optional `look`, `x` (required on the bean's first pose in a shot), `at` |
| `prop` | the word that names the thing | `prop`, `x`, `y`, optional `id`, `scale`, `enter`, `text` |
| `act` | the prop does its thing (the phone buzzes, the clock rings) | `target`, `act` |
| `label` | a short name for what is on stage, near it | `text`, `x`, `y`, optional `tone` (`red` for the warning) |
| `mark` | a reaction beside the bean's head; it clears at the bean's next pose | `who`, `mark` |
| `impact` | a hit: a slammed prop, a realisation; a short camera shake | optional `strength` 1 to 3 |
| `strike` | a red X over a prop: wrong, fake, don't | `target` |
| `arrow` | a red arrow from one thing to another: cause and effect, this one not that one | `from`, `to` |

**Poses carry the meaning.** Match the pose and face to the line: `panic` + `shocked` on the scare,
`point` at the prop being talked about (`at` names it, and the arm reaches it), `shrug` on "nobody
knows", `facepalm` on the mistake, `cheer` + `happy` on the win, `think` + `squint` on the question.
`look` turns the eyes toward what matters (`left`, `right`, `front`). A pose that contradicts the line
is a defect the review reports.

**Props.** Place them by their centre: `x` and `y` are fractions of the frame (the stage runs from
y 0.24 to 0.68). Keep them clear of the bean: a bean at x 0.28 is about 0.27 of the frame wide, so a
prop beside it sits at x 0.65 or more. `scale` (0.5 to 1.4) sizes it; `enter` is `pop` (the default),
`drop` (falls in; pair it with an `impact`), `slide` (from the nearer edge) or `rise`. A prop with a
text slot shows the words you give it (a message on the phone, an address in the browser bar, a price
on the tag): keep it short. When the topic names something the library does not have, show it with a
text-carrying prop (a `sign`, a `note`, a `document`, a `speech` bubble) rather than a wrong object.
Give a prop an `id` when the shot has two of the same (`"id": "fake"`, `"id": "real"`); `at`,
`target`, `from` and `to` name props by `id` (or by prop name when it has none) and beans by cast id.

**Pacing.** Aim for a change every 1.5 to 3 seconds; the tool refuses a stretch longer than 3. Build a
shot up: the bean, then the prop, then a label, then the reaction. Do not put things on stage the
narration does not mention.

## Step 4 — captions and mascot

Leave the caption look to the style: either leave `subtitles` out, or set only `emphasis`, the indexes
of the key words in the timeline's word list (the word the line turns on: `panic`, `not`, `letter`).
At most one word in 5, and usually one per sentence or fewer. The style fills in the rest of the
caption look; any other key you set overrides it, so leave them alone.

If `get_video` has a `mascot`, add its cue track as the mascot skill describes. Keep the mascot small
and to one side, away from the bean and the props, and bring it on only for a few reactions: two
characters reacting at once is busy.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out) and the one scene. Fix every problem it reports. If the video has props
   of your own, look at them now with `render_bean_props` (Step 2b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   header, the labels and the prop texts in a browser; an overlap is a measurement, so move or shorten
   the text.
3. `submit_render(video_id)`.

In the handback, say how many sections and shots you made, which props you used, which props you
drew yourself and why the library could not show them, and any subject you showed with a text prop.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong prop, a pose that does not fit,
a crowded shot, a label in the way) is fixed in `props.beanExplainer`: edit the shots and events, then
write, validate and submit again as above. Never change the video's style. If the voice was redone,
the word frames have changed: re-time every cut and event from the new timeline, and recount the
`emphasis` indexes.
