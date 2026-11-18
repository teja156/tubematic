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
These are main styles: each carries a whole video. Insert styles (a short diagram of parts, a string or
number on screen) are never in this list. They are short scenes inside the main style, and the
tubematic-insert-routing skill decides them after you, so pick the main style that carries the whole
topic best and leave its diagram or string beats to the inserts. Each entry is:

| Field | Meaning |
|---|---|
| `id`, `label` | What you pass to `choose_visual_style`, and its name |
| `routing.best_for` | The kinds of topic the style is made for. The strongest evidence |
| `routing.avoid_for` | Topics the style must not get |
| `routing.cannot_show` | What the style cannot put on screen at all |
| `routing.signals` | Things that, when true of this topic's script, point to the style |
| `routing.moods` | The tones the style suits. A tie-break only |
| `routing.yields_ties` | When `true`, the style loses a tie to any candidate without it (Step 5) |
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
its description says so, how its videos should look. The description is the domain's standing
instructions, written by a person: Steps 2 and 4 follow what it says about the look.

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
   flow, numbers, text, or nothing concrete. Before you write it, answer one question: is the
   whole video the story of one real failure, accident or disaster that happened to a named
   machine, product, place or company (a launch that went wrong, a crash, an outage, a collapse),
   one the viewer would want to see (the rocket, the aircraft, the control room, the trading floor,
   the screens across the world)? If it is, pictures of that real thing are part of what must be
   seen, whatever the brief's angle is: a brief built around one idea (a number, a unit, a line of
   code) still tells the story of the real thing it happened to. Not this: a list of several
   things, each one item; history told as a story that is not a failure (an invention, a
   discovery, a famous first, a walk through a real place in the past), whose people and places
   can be drawn; a flaw in a piece of software with nothing to see beyond its code and the
   requests through it; and a real thing whose own text, code or number is the whole subject (a
   famous cipher, an inscription, a number's limit), which is seen through that text. For these,
   describe what must be seen as you would without this question.
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
- Its `cannot_show` plainly covers something you wrote under "what must be seen" in Step 1. A style
  that cannot show the subject makes an unwatchable video however many points it would score. A
  candidate with no `cannot_show` line has stated nothing; do not rule it out on this ground.
  `scenes` is the fallback and is never ruled out on this ground either.
- The domain's description rules it out: it says the domain's videos should not have that look
  ("no cartoons", "no generated pictures"). `scenes` is never ruled out on this ground.

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

- When the domain's description asks for one style for its videos, by name or by a description
  that fits only that candidate, and Step 2 left it in, pick it. Its reason names the description.
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

1. **Yielding.** A candidate whose `routing.yields_ties` is `true` loses a tie to one
   without it: its pack says it gives way when another style fits as well.
2. **Specificity.** The candidate whose winning `best_for` entry names this topic's kind more
   narrowly. "Networking and protocols" beats "mechanisms" for a protocol.
3. **A person's hint.** The domain's description or a comment asks for a look one candidate has.
4. **Mood.** The candidate whose `moods` match the mood from Step 1.
5. **Cost.** Fewer `images`. Generated images cost money on every video.
6. **Order.** The earlier candidate in the list.

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
  anyway. `photo_led`'s `cannot_show` is "figures acting out a step", which this topic does not
  need, so it stays. Nothing else is ruled out.
- Step 3: `acted_roles`' `best_for` has "how a system works, told with its parts as roles" (3),
  and two of its signals hold (the people are roles, a request walks through the parts of a system)
  (2): 5. `board_reasoning`'s `best_for` has "a chain of causes" (a close neighbour, 1) and one
  signal (1): 2. `photo_led` scores 0.
- Step 4: `acted_roles` is the only clear fit. The request's path as a diagram is not a reason to
  look for another style: that beat becomes an insert, decided by the next skill.
- Step 6: the runner-up is `board_reasoning` (2).
- Step 7: `choose_visual_style(video_id, "acted_roles", "A web request's path from browser to
  database and back, acted out by its parts.", "board_reasoning")`, then the comment
  `Path through a system, roles only, calm. Picked acted_roles (5) over board_reasoning (2) and photo_led (0).`

## Checklist

- [ ] `style_routing.decided` was `false` and the video is at `TOPIC_APPROVED`
- [ ] Topic described on the five axes before reading the candidates
- [ ] Asked whether the topic is a real failure, accident or disaster of a named thing, and if so
      put its pictures under "what must be seen"
- [ ] Unavailable candidates, plain `avoid_for` matches, candidates whose `cannot_show` covers
      what must be seen, and looks the domain's description rules out, ruled out
- [ ] Points counted from `best_for` and `signals` by meaning, not by shared words
- [ ] A style the domain's description asks for picked when it is still in; otherwise a style
      picked only as a clear fit (3 points or more), otherwise `scenes`
- [ ] Ties broken by yielding, specificity, a person's hint, mood, cost, then order
- [ ] `choose_visual_style` called with a one-sentence reason and a runner-up
- [ ] A comment with the description and the top three scores
