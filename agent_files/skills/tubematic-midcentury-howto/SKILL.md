---
name: tubematic-midcentury-howto
description: Author a Mid-century How-To narrated Short as data — a title card, numbered steps each on its own ground colour, the house presenter posed on the narrator's words, objects from the library (drawing one of your own, modelled on the library, when it lacks one) pressed, checked and called out, and a summary card — then write it with write_scene_config, preview your objects, validate and submit it
---

# Tubematic Mid-century How-To authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-midcentury-howto` (its `visual_style` is `midcentury_howto`). Also take it, on **Revising**,
for a `REVISION_REQUESTED` video at that style. Every other video takes the skill its
`style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short in the look of a 1950s classroom film: warm paper, one flat **ground
colour** per step, a geometric **presenter** with a big nose and white four-finger gloves, flat
cartoon **objects** (a phone, a laptop, a keypad, a lock) printed a few pixels off a broken ink line,
numbered **step medallions** with slab-serif titles, a gloved hand that **presses** on a word with a
ring burst, teal **check** and coral **cross** medallions, circular **insets** with a short number,
and at the end a **summary card** listing every step. The fills jitter gently on twos: that is the
look, not a defect.

The presenter's body holds still; his hand, eye and brow act on the narrator's words. He never moves
his mouth to talk (the narrator is off screen), so never time anything to make him look as if he
speaks.

**You write data, never code**, except an object the library lacks (**Step 3b**). The whole video is
one installed scene, `MidcenturyHowTo`, and everything about this video is its
`props.midcenturyHowTo`: the title, the steps, an optional summary, and the shots with their events
timed to the narration. There are no images in this style: never call `generate_image` or
`generate_character`. Nothing here runs code or a shell.

The full field reference and the object catalogue are in `reference/contract.md`; the worked example
is `reference/example-config.json` (narration in `reference/example-timeline.json`). Read all three
before you write.

## Rules the tools enforce

`write_scene_config` refuses a Mid-century How-To config that breaks any of these, and says which
shot or event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "MidcenturyHowTo", "startFrame": 0, "durationInFrames": <totalFrames>, "props":
  {"midcenturyHowTo": {...}}}`. Insert scenes go in the config's own `inserts` list (**Inserts**).
- **Title card first.** The video opens on the title card: the first step starts at least 1.5 s in.
- **Steps:** 2 to 6, each starting where a shot starts, on a word, each at least 3 seconds long.
- **Summary** (optional): a frame after the last step's start where a shot starts, at least 2 seconds
  before the end. Its shot holds only the presenter's poses (he stands on the right).
- **Shots** are cuts: the first at frame 0, the others on a word (within 2 frames of a word's
  `startFrame`), each at least 1.5 seconds long, at most 30. A shot starts empty.
- **Events** are listed in frame order, start inside their shot, and end at least 6 frames before the
  next cut; at most 20 a shot. At most 4 objects, labels and insets on stage at once.
- **Poses** land on a word, at least 8 frames apart; `at` only on a `point` or `present` pose. A shot
  with `"presenter": "none"` has no poses.
- **Presses** land on a word, at least 16 frames apart, and the first one at least 6 frames into its
  shot (the hand pulls back first). Acts, presses, checks, crosses and insets start once their
  object has landed (8 frames after it appears).
- **Layout:** objects, labels and insets stay on the stage (from y 0.31, or 0.45 on the title card,
  down to the floor, inside the side margins), clear of the presenter's body. A label or an inset may
  not overlap an object or another label or inset. Objects may overlap each other (a phone on a table).
- **Text:** title up to 30 characters, kicker 22, a step header 18, a tag 26, a label 22, an inset 10.
  A label never repeats 4 or more narration words in a row.
- **Your own objects:** at most 8, each a `prop-<name>` file of this video written before the config,
  with a box of 60 to 700 px a side, a text slot of at most 80 characters and at most 4 acts. It
  imports only `react`, `remotion` and `../../installed/midcenturyHowTo/cel` (or `contract`), uses no
  hook, filter, gradient, pattern, image, media part, fetch, randomness, clock, timer or page access
  (`reference/contract.md` lists them all), and default-exports the drawing.
- **Never still:** something new (an event or a cut) at least every 3 seconds.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps`, every word's frames, and each
   segment's `beat`, `role` and `insert`. Every frame you write comes from here.

## Step 1 — title, steps and summary

- `title`: the task, as the running title (`"Turn on 2FA"`). `kicker`: an optional short line for the
  title card (`"Meet your second lock."`).
- The narration before "Step one" is the **title card**: the first step's `start` is the first word
  of step one.
- Each numbered step is a `step`: `start` on its number's word, `header` the action in a few words
  (`"Open Settings"`), an optional `tag` naming where or what (`"Settings > Security"`), and a
  `ground` (`mustard`, `blue`, `olive`, `rose`, `sea`; never the same twice in a row). The title card
  and the summary are always mustard with sunburst rays.
- If the narration ends on a line that recounts the steps (`"Three steps, one minute."`), set
  `summary` to that line's first word. Otherwise leave it out and hold on the last step's result.
- `presenter`: optional `outfit` (`coral`, `teal`, `mustard`, `blue`) and `hair` (`dark`, `red`,
  `blond`, `grey`). Pick once for the video.

## Step 2 — shots

Each step is one shot, or two when it has a close-up: cut to a second shot with `"presenter":
"none"` when one object needs the whole stage (a keypad being typed on, a long settings screen). In a
shot without the presenter, a press comes from a long rubber-hose arm reaching in from the edge.
`"presenter": "right"` stands him on the right when the objects need the left. On the title card he
usually waves, then presents the object the video is about.

## Step 3 — events, timed to the words

| Event | When | Fields |
|---|---|---|
| `object` | the word that names the thing | `object`, `x`, `y`, optional `id`, `scale` (0.5 to 1.5), `enter` (`pop`, `drop`, `slide`, `rise`), `text` |
| `pose` | the presenter reacts or gestures | `pose`, `face`, optional `at` (an object, for `point` and `present`) |
| `press` | the word for tapping or pressing it | `target` |
| `act` | the object does its thing (a row lights, the code types in, the screen turns to done) | `target`, `act` |
| `check` | it worked: a teal check medallion on the object | `target` |
| `cross` | don't do this: a coral cross medallion on the object | `target` |
| `inset` | the one number worth circling | `target`, `text`, `x`, `y` |
| `label` | a short name for what is on stage | `text`, `x`, `y` |

**Objects.** `x` and `y` are the object's centre as fractions of the frame. With the presenter on the
left, objects go right of x 0.5 (his body reaches to about x 0.33). An object standing on the floor
sits with its bottom on y 0.72 (its centre at 0.72 minus half its height in frame units). A screen
object (`phone`, `laptop`, `window`) takes `text` as `"Title|row|row|row"`: up to three rows, named
exactly as the real screen names them. Its acts `row1` to `row3` light that row; `done` turns the
screen teal with a check. A `keypad` types its `text` (the code) on `type`; a `password` field types
on `type`. Pair a `press` and the act it causes on the same word: the hand lands on that row or key.

**Poses.** `stand`, `present` (an open hand toward the object), `point`, `thumbsup`, `wave`, `think`
(hand at chin), `shrug`, `hips`. Faces: `neutral`, `smile`, `grin`, `worried`, `surprised`, `proud`.
Match the line: `worried` on the risk, `point` at the thing being named, `thumbsup` + `grin` on done.

**Pacing.** Something new every 1.5 to 3 seconds; the tool refuses a stretch longer than 3. Build a
step up: the object, the presenter's gesture, the press and its act, the check.

## Step 3b — an object the library does not have

Use a library object whenever one fits; use a `sign`, `document` or `checklist` when the thing is
really words. Draw your own only for an object the viewer must recognise that the library lacks (a
smoke alarm, a car key fob, a thermostat). Keep it to a few per video.

1. Read the library and its helpers: `read_scene_file` with `source="installed"` and `scene_name`
   `midcenturyHowTo/objects/screens` and `midcenturyHowTo/objects/things`, and
   `midcenturyHowTo/cel` (the palette, `Cel`, `fitFont`, `actProgress`).
   `reference/example-prop-alarm.tsx` is a finished one.
2. Draw it the same way: one component, centred on (0, 0) inside a `w` x `h` box at scale 1, every
   filled shape a `Cel` (it prints the fill off the ink line), flat palette colours, big simple shapes
   that read at phone size. It receives `phase`, `act`, `actT` (frames since the act started, -1
   before) and `text`, and nothing else: draw from them alone. An act plays within 20 frames and then
   holds its end state.
3. Write it with `write_scene_file(video_id, "prop-<name>", tsx)` and list it in `customProps`:
   `{"id": "alarm", "src": "<the src write_scene_file returned>", "w": 260, "h": 260, "acts":
   ["beep"]}` (add `"text": 12` for a text slot). Its `id` is then used like a library object's.
4. After `write_scene_config`, call `render_style_props(video_id)` and look at the picture. Ink
   outside the red box means the box is too small: raise `w` and `h` or shrink the drawing. A drawing
   that does not read as the thing at a glance, or looks unlike the library beside it: redraw it.
   Three looks at most. `validate_job` typechecks the file and checks it against the rules again.

## Step 4 — captions

Leave the caption look to the style: leave `subtitles` out, or set only `emphasis` (the indexes of the
key words in the timeline's word list, at most one word in 5). The style fills in the rest.

This style takes no mascot.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`; `get_video`'s `style.picture` says how this
style does each:

- Opening: the title card with the presenter posed and the object the video is about on stage from
  frame 0.
- Turn or re-opening: a new step or shot on its first word, or a press, check, inset, act or new
  object on that word.
- Payoff: the step's result, the press that finishes the task, the screen turning teal, the check.

`validate_job` returns advisory warnings when the title card has no object by frame 3 or when a
`turn`, `reopen` or `payoff` segment has nothing new starting within about 0.4 s of its first word (a
label alone does not count). Fix what is a real miss; say in the handback why any warning stands.

## Inserts

If `get_timeline` shows a segment whose `insert` is not `""`, invoke the **tubematic-inserts** skill
and follow it. The stage is hidden while an insert plays, so inside each insert's window no shot,
step or summary starts and no event has its `frame`. Put the next shot's cut on the window's end (its
last frame + 1), or time the shot's next event after the window. The "never still" rule does not
count a window. With no marked segment, write no `inserts`.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "light"` (or leave it out), the one scene and any `inserts`. Fix every problem it reports. If the
   video has objects of your own, look at them now with `render_style_props` (Step 3b).
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures the
   titles, tags, labels and insets in a browser; an overlap is a measurement, so move or shorten the
   text.
3. **Look before you submit.** (Reserved: a later tool lets you look at chosen frames of the composed
   video here. Until it exists, go straight on.)
4. `submit_render(video_id)`.

In the handback, say how many steps and shots you made, which objects you used, which objects you drew
yourself and why the library could not show them.

## Revising

Read the comments on `get_video`. A comment about the picture (a wrong object, a press on the wrong
row, a crowded stage, a label in the way) is fixed in `props.midcenturyHowTo`: edit the shots and
events, then write, validate and submit again as above. Never change the video's style. If the voice
was redone, the word frames have changed: re-time every step, cut and event from the new timeline,
and recount the `emphasis` indexes.
