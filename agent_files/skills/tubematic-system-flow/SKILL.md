---
name: tubematic-system-flow
description: Author a System Flow narrated Short as data — split the narration into boards, lay out each board's components and connectors, time nodes, packets, focus and value chips to the narration's words — then write it with write_scene_config, validate and submit it
---

# Tubematic System Flow authoring skill

**Invoke this skill when:** a video is at `VOICE_READY` and `get_video` says `style.authoring_skill` is
`tubematic-system-flow` (its `visual_style` is `system_flow`). Also take it, on **Revising**, for a
`REVISION_REQUESTED` video at that style. Every other video takes the skill its `style.authoring_skill` names.

---

## What you are making

A vertical 1080x1920 Short where a diagram builds itself while the narrator explains a system: line
icons in thin cyan boxes appear one by one, dotted connectors draw from one box to the next, points of
light (packets) travel along them, the part being talked about glows while the rest dims, and small
value chips (an address, `200 OK`, a port) sit beside the connector they describe. A pill tag and a
short headline sit at the top; outlined captions sit in the lower part of the frame. The camera keeps
whatever is visible framed by itself, and the picture cuts to a new diagram (a **board**) when the
subject changes.

**You write data, never code.** The whole video is one installed scene, `SystemFlow`, and everything
about this video is its `props.systemFlow`: the boards, their nodes and edges, and events timed to the
narration. The renderer does the layout, the camera, the look and the captions. There are no images
in this style (never call `generate_image` or `generate_character`) and no people: a role ("the
user", "an attacker") is a component with an icon.

The full field reference and the worked example's narration are in `reference/contract.md`; the
worked example itself is `reference/example-config.json`. Read both before you write.

## Rules the tools enforce

`write_scene_config` refuses a System Flow config that breaks any of these, and says which board,
node or event is wrong. Fix every problem it lists, then write again.

- **One scene.** `scenes` is exactly one entry: `{"type": "generated", "source": "installed", "src":
  "SystemFlow", "startFrame": 0, "durationInFrames": <totalFrames>, "props": {"systemFlow": {...}}}`.
- **Boards** start at frame 0 and then on a word (within 2 frames of a word's `startFrame`), each at
  least 2 seconds long, at most 12 boards.
- **A board's diagram:** at most 9 nodes, at most 3 side by side in a row, at most 3 rows deep, every
  node connected to the rest, no cycle.
- **Labels** fit 2 lines of 14 characters (two or three short words). Headlines at most 40
  characters; pills at most 24; chip texts at most 24.
- **Icons** come from the list below.
- **Order:** an edge draws at least 8 frames after its source enters, and its target enters within
  30 frames of the edge starting; a packet or chip waits until its edge has finished drawing (15
  frames); a packet travels 20 frames; focus and fault come after their node has entered.
- **Seen before the cut:** a board that is not the last fades out over its final 6 frames, and every
  event must have finished before that (on the last board, by its final frame), with time to be
  read: a node 31 frames, or longer while its label types on (6 frames, then 2 per character, then
  15), an edge 30, a chip 30, a packet 20, a focus or fault 15. The tool tells you the latest frame
  that works.
- **One at a time:** a chip shows until the next chip and a focus lasts until the next focus, so
  keep chips at least 30 frames apart and focuses at least 15.
- **Never still:** something new (an event or a cut) at least every 3.5 seconds.

## Step 0 — read

1. `get_video(video_id)`: the topic, the script segments and their `visual` briefs, the comments, and
   `mascot`.
2. `get_timeline(video_id, include_words=True)`: `totalFrames`, `fps` and every word's
   `startFrame`/`endFrame`. Every frame you write comes from here.

## Step 1 — split the narration into boards

A board is one subject: the request path, the defence, the cache, the failure. Start a new board where
the narration changes subject, on the first word of that sentence. Most Shorts need two to five. A
board that needs more than 9 components, a fourth one side by side, or a chain longer than three is
two subjects: split it.

## Step 2 — the diagram of each board

**Rows** are worked out from the edges: a node nothing points to is on the top row; any other node is
one row below the lowest of the nodes pointing to it. So a chain A→B→C is three rows deep, and three
nodes fed by one are one row of three. Within a row, nodes sit left to right **in the order you list
them** in `nodes`, so list the left one first.

- `id`: lowercase letters, digits, underscores (`load_balancer`, `web1`).
- `label`: what the narration calls it, short: `DNS Resolver`, `Load Balancer`, `Web Server 1`.
- `icon`, one of: `api`, `app`, `attacker`, `browser`, `bug`, `cache`, `cdn`, `chart`, `clock`,
  `cloud`, `container`, `cpu`, `database`, `disk`, `dns`, `email`, `file`, `firewall`, `function`,
  `globe`, `key`, `load_balancer`, `lock`, `memory`, `phone`, `queue`, `router`, `server`, `shield`,
  `user`. Pick the nearest meaning; a label carries the rest.

**Edges** point the way things first travel (`{"from": "browser", "to": "dns"}`). A reply is not a
second edge back (that is a cycle): it is a packet on the same edge with `"reverse": true`.

## Step 3 — events, timed to the words

Every node needs one `node` event and every edge one `edge` event; the rest are what makes the video
move. Edges are named `"from>to"` in events.

| Event | When | Fields |
|---|---|---|
| `node` | the word that first names the component | `node`, `at` |
| `edge` | as the narration moves from one component to the next | `edge`, `at` |
| `packet` | something travels: a request, a reply, a signal | `edge`, `at`, optional `reverse`, `tone` |
| `focus` | the narration dwells on one component; the rest dims until the next focus | `node`, `at` |
| `chip` | a value worth reading appears on a connector (one chip at a time, about 2.5 s each) | `edge`, `at`, `text`, optional `tone` |
| `fault` | the component that fails, or the attacker; it turns red for the rest of the board (once per node) | `node`, `at` |

**Tones** carry meaning, never decoration: `structure` (cyan, the default), `relation` (violet, a link
between parts), `ok` (green, a success or a verified result), `fault` (red, the one failure or attack
in view).

**Pacing.** Aim for a change every 1.5 to 3 seconds; the tool refuses a stretch longer than 3.5. A
packet on a sentence that says something travels, a focus on the component being explained and a chip
for the number the narration names are what keep a diagram from reading as a still slide. Do not fire
events the narration does not say: a packet on a connector nobody is talking about is a defect the
review reports.

**Headline and pill.** One headline per board, the board's question or claim in at most 40 characters
(its last word is coloured for you). The pill is an optional tag such as `Step 1 · the request`.

## Step 4 — captions and mascot

Leave `subtitles` out: the style fills in its own captions. If `get_video` has a `mascot`, add its cue
track as the mascot skill describes and keep the mascot out of the diagram band (27% to 69% of the
height): the bottom band or beside the headline.

## The opening and the beats

`get_timeline` gives each segment a `beat` and a `role`, and the result a `first_frame` (the formula's line on what the first frame shows, `""` when the video has no formula). The first segment's role is `opening`. A `turn` or `reopen` segment needs a visible change on its first word, the `payoff` segment the video's strongest picture, and a segment with role `""` only its own brief. `get_video`'s `style.picture` says how this style does each; in short:

- Opening: board 1 has a `node` event at frame 0 for the component the first sentence names. A node at frame 0 is drawn half grown on the first frame, so the video never opens on the headline alone.
- Turn or re-opening: a new board on its first word, or a `focus` with a `packet` or `fault` on that word.
- Payoff: the board that shows the whole answer, the path lit end to end, the focus on the component the answer names. Nothing after it but that board.

`validate_job` returns warnings (advisory, never blocking) when board 1 has no node by frame 3 or when a `turn`, `reopen` or `payoff` segment has no board, node, edge, packet, focus or fault (a chip alone does not count) starting within about 0.4 s of its first word. Fix what is a real miss; say in the handback why any warning stands.

## Step 5 — write, validate, submit

1. `write_scene_config(video_id, config)` with `totalFrames` and `fps` from the timeline, `"canvas":
   "dark"` (or leave it out) and the one scene. Fix every problem it reports.
2. `validate_job(video_id)`: fix its errors, then read its `warnings`. The text audit measures each
   board's labels and chips in a browser; an overlap is a measurement, so move or shorten the text.
3. `submit_render(video_id)`.

In the handback, say how many boards you made, the subject of each, and anything you left out to stay
within the limits.

## Revising

Read the comments on `get_video`. A comment about the diagram (a wrong component, a missing step, a
crowded board, a packet at the wrong moment) is fixed in `props.systemFlow`: edit the boards and
events, then write, validate and submit again as above. Never change the video's style. If the voice
was redone, the word frames have changed: re-time every event from the new timeline.
