---
name: tubematic-style-routing
description: Pick a video's visual style before its script is written, when the person left it on Auto — read the candidate styles from get_video's style_routing, describe the topic on fixed axes, rule candidates out, score the rest, break ties, and record the choice with choose_visual_style
---

# Tubematic style routing skill

**Invoke this skill when:** a video is at `TOPIC_APPROVED` and `get_video(video_id)` says
`style_routing.decided` is `false` (its `visual_style` is `"auto"`). Run it once, before the script
is written, then go back to the operator skill and write the script for the style you picked.

When `style_routing.decided` is `true`, do not run this skill: either Auto has already picked, or a
person chose the style. Never change a style a person chose.

---

## Why this matters

The style decides how the script is written (a walk through a system, a story with a protagonist, a
list of items, a chain of reasoning) and what every frame looks like. The right style for a topic
makes a clearly better video than a good style applied to the wrong topic. A person sees your choice
and your reason at the script checkpoint and can switch to your runner-up, but a switch throws the
script away, so get it right the first time.

## The candidates are data

`get_video(video_id).style_routing.candidates` lists every style you may pick, in a fixed order.
Each entry is:

| Field | Meaning |
|---|---|
| `id`, `label` | What you pass to `choose_visual_style`, and its name |
| `routing.best_for` | The kinds of topic the style is made for. The strongest evidence |
| `routing.avoid_for` | Topics the style must not get |
| `routing.signals` | Things that, when true of this topic's script, point to the style |
| `routing.moods` | The tones the style suits. A tie-break only |
| `images` | Generated images a video in this style costs, at most. A tie-break only |
| `experimental` | The style is new. A tie-break only, never a reason to skip it |
| `available`, `unavailable_reason` | Whether this install and this video can have the style now |

The last candidate is always `scenes`, the mixed scene system: each beat drawn with whatever suits
it, on a canvas chosen later. It is the fallback when no style clearly fits, and its own `best_for`
names the topics it is the best answer for: those that need two treatments no single style has.

Read the styles only from this list. Never pick a style from memory, from another video or from
these instructions: the list changes as styles are added, and it is the only place that says what
each style is for and whether this install can make it.

`style_routing.domain` is the video's domain `{name, description}`: who the channel is for and, when
its description says so, how its videos should look.

## Step 1: Describe the topic

Read the video's `title`, its `topic` (the brief) and the domain. Read the comments too: a person may
have asked for a look when approving or revising the topic. Then write down, in a few words each:

1. **Subject shape**, one or two of:
   - a path something travels through a system (a request, a packet, a payment, a signal)
   - how a physical thing works inside
   - reasoning worked out step by step, a formula, a chain of causes
   - a list of named items (types, tricks, mistakes, facts)
   - quantities over time, a ranking, a comparison of numbers
   - a place, and what happens in it
   - a person with something at stake, a story with a plot
   - the history of an idea, an invention or a person
   - a rule, a warning or a scam
   - text, code, a password, a cipher, letters being transformed
   - a set of real, specific things the viewer came to see (products, buildings, artworks, named people)
   - an idea or a feeling with nothing concrete to show
2. **People in it:** none, generic roles ("the user", "an attacker"), named real people, one
   protagonist, or recurring characters the viewer must recognise from scene to scene.
3. **What must be seen:** pictures of real named things, a place moved through, a mechanism or
   flow, numbers, text, or nothing concrete.
4. **Form:** how-it-works explainer, list, story, history, comparison, warning.
5. **Mood:** the tone the narration wants (calm, curious, dramatic, playful, sober, warm).

Describe the topic as it is, not as a style would like it to be. Describe it before you read the
candidates' `best_for`, so the description is not bent toward one of them.

## Step 2: Rule candidates out

Remove a candidate when:

- `available` is `false`. Note its `unavailable_reason`: if it would have won, the reason you record
  says so, so a person can fix the install.
- One of its `avoid_for` entries plainly describes this topic. "Plainly" means a reader would agree
  at once; a stretch is not a match.

## Step 3: Score the rest

For each remaining candidate, `scenes` included:

- **`best_for`:** 3 points when the topic is squarely one of the listed kinds; 1 point when it is a
  close neighbour of one. Count only the best `best_for` entry, not every entry that touches it.
- **`signals`:** 1 point for each signal that will plainly be true of this video's script, as you
  described it in Step 1.

Match the meaning, never a shared word. "Social network" does not match "networking and protocols";
"the history of encryption" is a history topic even though it mentions encryption. When in doubt,
do not count it.

A candidate is a **clear fit** with at least 3 points.

## Step 4: Decide

- When at least one candidate is a clear fit, pick the one with the most points.
- When none is, pick `scenes`. Do not pick a style that half fits: a topic forced into a style made
  for something else is worse than the mixed scene system.
- A style that carries only some of the beats half fits, however many points those beats earn it.
  This applies only when the topic plainly needs two treatments no single candidate has, and the
  first entry of `scenes`' `best_for` names that pair (for example full-frame pictures of real
  things next to roles acted out by figures). Then `scenes` is the clear fit. Otherwise the most
  points win.
- When two clear fits are within 1 point of each other, break the tie (Step 5).

## Step 5: Break ties, in this order

1. **Specificity.** The candidate whose winning `best_for` entry names this topic's kind more
   narrowly. "Networking and protocols" beats "mechanisms" for a protocol.
2. **A person's hint.** The domain's description or a comment asks for a look one candidate has.
3. **Mood.** The candidate whose `moods` match the mood from Step 1.
4. **Cost.** Fewer `images`. Generated images cost money on every video.
5. **Order.** The earlier candidate in the list.

Never break a tie by novelty, by what recent videos used, or by which style is the most elaborate.
The right style for this topic is right even if the last three videos used it.

## Step 6: Choose a runner-up

The runner-up is the candidate a person is most likely to want instead: the next-highest available
candidate with at least 1 point, `scenes` included. When you picked a style and nothing else scored,
the runner-up is `scenes`. When you picked `scenes`, the runner-up is the best-scoring style, or
`""` if none scored at all.

## Step 7: Record it

```
choose_visual_style(video_id, style=<id>, reason=<one sentence>, runner_up=<id or "">)
```

- `reason` is one sentence of at most 300 characters, written for the person who approves the
  script: the topic feature that decided it ("A packet's path from browser to server, step by
  step."). When a better fit was unavailable, name it and why ("A 3D world fits, but no renderer has
  a working GPU.").
- The call returns the video's new `visual_style` and its `style`, including `style.script`: that
  style's guidance for writing the narration and each segment's `visual` brief. The script-writing
  skill follows it.

Then `add_comment(video_id, "agent", …)` with your Step 1 description in one line and the top
three candidates with their points, for example `Picked X (6) over Y (4) and Z (1)`.

If the call refuses:

- **already picked, or chosen by a person:** someone decided first. Read `get_video` again and
  write the script for the style it now has.
- **not available:** the install changed since you read the list. Read `get_video` again and decide
  again from the new list.
- **the tool does not exist:** the server is older than these instructions. Leave the video at
  `TOPIC_APPROVED`, add a comment saying the style could not be picked, and stop; the next run picks
  it up after the server is updated.

## Worked example

The ids below are invented for the example; your list will differ.

A video titled "What happens when you press Enter on a URL" with the brief "The path of a web
request: DNS, TCP and TLS, the load balancer, the app server, the database, and the response back."

- Step 1: a path something travels through a system; generic roles at most (the browser, the
  server); a flow must be seen; how-it-works; calm and curious.
- Step 2: `world_3d` is unavailable (no working GPU) and its `avoid_for` says "pure mechanisms"
  anyway. Nothing else is ruled out.
- Step 3: `flow_diagram`'s `best_for` has "how a request is handled" (3), and three of its signals
  hold (components that talk, a path a request travels, an architecture) (3): 6.
  `line_art`'s `best_for` has "mechanisms: how a thing works" (a close neighbour, 1) and one signal
  (1): 2. `photo_led` scores 0.
- Step 4: `flow_diagram` is the only clear fit.
- Step 6: the runner-up is `line_art` (2).
- Step 7: `choose_visual_style(video_id, "flow_diagram", "A web request's path from browser to
  database and back, step by step.", "line_art")`, then the comment
  `Path through a system, roles only, calm. Picked flow_diagram (6) over line_art (2) and photo_led (0).`

## Checklist

- [ ] `style_routing.decided` was `false` and the video is at `TOPIC_APPROVED`
- [ ] Topic described on the five axes before reading the candidates
- [ ] Unavailable candidates and plain `avoid_for` matches ruled out
- [ ] Points counted from `best_for` and `signals` by meaning, not by shared words
- [ ] A style picked only as a clear fit (3 points or more), otherwise `scenes`
- [ ] Ties broken by specificity, a person's hint, mood, cost, then order
- [ ] `choose_visual_style` called with a one-sentence reason and a runner-up
- [ ] A comment with the description and the top three scores
