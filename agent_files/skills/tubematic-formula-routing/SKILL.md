---
name: tubematic-formula-routing
description: Pick a video's script formula before its script is written, after its visual style is decided — read the candidate formulas from get_video's formula_routing, describe the topic's shape, rule candidates out, score the rest, rotate away from the domain's recent formulas, and record the choice with choose_script_formula
---

# Tubematic formula routing skill

**Invoke this skill when:** a video is at `TOPIC_APPROVED`, `get_video(video_id)` says
`style_routing.decided` is `true` and `formula_routing.decided` is `false`. Run it once, after the
style is decided and before the script is written, then go back to the operator skill and write the
script in the formula the tool returned.

When `formula_routing.decided` is `true`, do not run this skill: the formula is picked. The
exceptions are two kinds of script revision (see "A revision" below).

---

## Why this matters

A formula is the script's structure: which beats it has, in which order, how it opens and how it
ends. The right formula for a topic holds a viewer where a sound script in the wrong structure
loses them in the first seconds. A person sees your choice and your reason at the script
checkpoint and can switch to your runner-up, but a switch throws the script away, so get it right
the first time.

## The candidates are data

`get_video(video_id).formula_routing.candidates` lists every formula, in a fixed order. Each entry
is:

| Field | Meaning |
|---|---|
| `id`, `label` | What you pass to `choose_script_formula`, and its name |
| `line` | The formula in one sentence |
| `family` | The broad kind of structure: `explain`, `story` or `ladder` |
| `best_for` | The kinds of topic the formula is the first choice for. The strongest evidence |
| `also_for` | Kinds of topic it also fits |
| `avoid_for` | Topics the formula must not get |
| `signals` | Statements that, when plainly true of this topic, point to the formula |
| `words` | Its length band, `[min, max]` words. A tie-break only |
| `suits_style` | The formula suits the picture of this video's visual style |
| `recent` | It is the formula of one of the domain's previous two videos |
| `experimental` | The formula is new. Never a reason to skip an available one |
| `available`, `unavailable_reason` | Whether Auto may pick it on this install now |
| `learned` | What this install's own viewers say about it in this domain: `{points, standing, videos}` (Step 3b) |

Read the formulas only from this list. Never pick a formula from memory, from another video or
from these instructions: the list changes as formulas are added, and it is the only place that
says what each is for and whether this install lets you pick it.

`formula_routing.recent` is `{formulas, hook_types}`: the formulas and the types of opening of the
domain's previous two videos, newest first.

`formula_routing.learned` is what the domain's published videos say: `active` is `true` when
some formula has enough videos with watch figures to read, and `mode` is `"learned"` or
`"explore"`. When `active` is `false`, every candidate's `learned.points` is 0 and routing is
exactly as below without Step 3b.

`formula_routing.choice` is the formula a person chose for this video, or `""`. **When it is set,
route exactly as below and pass your own best formula.** The tool writes the script's formula as
the person's choice and records yours beside it as what Auto would have picked, which the person
can switch to. Never pass the person's choice just because it is theirs.

## Step 1: Describe the topic

Read the video's `title`, its `topic` (the brief) and the comments: a person may have asked for a
structure when approving or revising the topic. Read the topic's angle too: `angle` is one
sentence on what the opening will use, `angle_kind` is its kind and `angle_formula` is the formula
that kind is the first choice for. All three are `""` when the topic has no angle, which is a
normal state: then work the shape out from the topic alone. Then write down:

1. **The shape, in one line.** When the topic has an angle, `angle_kind` already names it: take
   it, unless the brief's facts plainly contradict it. Otherwise, what kind of thing the topic is: a thing the viewer owns that
   behaves strangely, a tool that did something wrong-looking, a process with an order, a belief,
   a design that looks stupid, an incident with a timeline, a scheme, evidence that looked wrong,
   one person in one moment, something with a measure, a set of separate items, a rule system, a
   superlative, something that just happened.
2. **What is real in it.** The dates, numbers, named sources, and the person who decided
   something, that the brief gives you. A formula can only be filled with facts the topic has.
3. **What the style asks for.** Read `get_video().style.script`. When it asks for a shape (a list
   of named items, a walk through a system, steps worked out on a board, a story told in
   chapters), note that shape: the style's text outranks the formula.

Describe the topic as it is, before you read the candidates' `best_for`, so the description is not
bent toward one of them.

## Step 2: Rule candidates out

Remove a candidate when:

- `available` is `false`. Note its `unavailable_reason`.
- One of its `avoid_for` entries plainly describes this topic. "Plainly" means a reader would
  agree at once; a stretch is not a match.
- The topic cannot fill it with real facts. A formula built on an incident needs a real one with
  times and numbers, one built on an anomaly a real anomaly, one built on a belief a belief
  people hold and a real source against it. No formula licenses an invented fact.
- Its structure contradicts the shape `style.script` asks for.
- Its beats give lines to a second speaker, and `get_pipeline_status()`'s `elevenlabs_voices` has
  no voice besides this video's.

## Step 3: Score the rest

For each remaining candidate:

- **The kind of topic:** 3 points when the topic is squarely one of its `best_for` kinds; 1 point
  when it is squarely one of its `also_for` kinds, or a close neighbour of a `best_for` kind. Count
  only the best match, once.
- **The angle:** when `get_video` returns a non-empty `angle_formula`, that formula's kind of
  topic is taken as squarely matched (3 points), unless Step 2 ruled it out.
- **`signals`:** 1 point for each signal that is plainly true of this topic, from what the brief
  says.
- **The style:** 1 point when `suits_style` is `true`. 1 more when its structure is the shape
  `style.script` asks for.

Match the meaning, never a shared word. "A security tip" does not match "a scam that works as a
loop"; "the history of an outage" is an incident only if the brief gives its times and numbers.
When in doubt, do not count it.

A candidate is a **clear fit** with at least 3 points.

## Step 3b: Add what this install's viewers say

Only now, and **only to the clear fits**, add each one's `learned.points`. A candidate that is not
a clear fit gets nothing, whatever its points: a formula that does not fit the topic is never
picked for how other videos did. Whether a candidate is a clear fit is decided by the Step 3
points alone, before this step.

The server works the points out from the share of the video viewers watched, compared inside
each account the domain posts to:

- In `"learned"` mode, a formula that holds this domain's viewers clearly better than the domain's
  videos as a whole has 2, one that holds them clearly worse has -1, and the rest 0.
- In `"explore"` mode (every fourth pick in a domain with figures), the figures are set aside
  and a formula with too few videos to read has 2. This is how the install keeps learning about
  formulas it has not tried; take the points as they are.

Never add points of your own for what you believe works, and never read the figures as a reason
a formula fits. `learned.standing` is `better`, `even`, `mixed` (the accounts disagree), `worse`
or `thin` (too few videos); `learned.videos` is how many videos are behind it.

## Step 4: Decide, and rotate

1. Take the clear fit with the most points, counting Step 3b. When two are within 1 point, break the tie (Step 5).
2. **Rotation.** When that candidate is `recent` and another clear fit is not, take the best clear
   fit that is not `recent`: a domain whose videos all share one structure reads as templated.
   Only when no other candidate is a clear fit, keep the `recent` one and pass `repeat_reason`
   (Step 7): one sentence on why nothing else fits this topic. How well a formula holds viewers
   is never a `repeat_reason`.
   When `formula_routing.choice` is set, skip this rotation step: the script is written in the
   person's choice, and your formula is recorded only as what Auto would have picked.
3. When no candidate is a clear fit: `follow-the-flow` for an explanation, `scene-story` for a
   true case about a person. If that one is `recent`, it still needs `repeat_reason`.

## Step 5: Break ties, in this order

1. **The opening.** The candidate whose opening this topic can fill most concretely with the real
   facts from Step 1.
2. **A person's hint.** The domain's description or a comment asks for a structure one candidate
   has.
3. **The style.** `suits_style` is `true`.
4. **Length.** The shorter band (the lower maximum in `words`).
5. **Order.** The earlier candidate in the list.

## Step 6: Choose a runner-up

The runner-up is the formula a person is most likely to want instead: the next-highest available
candidate with at least 1 point, whether or not it is `recent`. `""` when no other candidate
scored.

## Step 7: Record it

```
choose_script_formula(video_id, formula=<id>, reason=<one sentence>, runner_up=<id or "">,
                      repeat_reason=<one sentence, only for a recent formula>,
                      learned_stamp=<formula_routing.learned.stamp, or "">)
```

- `learned_stamp` is `formula_routing.learned.stamp` whenever `learned.active` was `true`, also
  when Step 3b changed nothing (no clear fit, or only clear fits with 0 points), and `""` when it
  was `false`.

- `reason` is one sentence of at most 300 characters, written for the person who approves the
  script: the feature of the topic that decided it ("A dated outage with a public account of
  times and one wrong command.").
- The call returns `formula_pick`: **the formula the script is written in.** It is yours when
  `chosen_by` is `"auto"`, and the person's choice when it is `"person"`. It also returns the
  formula's `words` band and `reference`, the file to read in the script-writing skill's
  directory. `update_video` refuses a script recorded under any other formula.

Then `add_comment(video_id, "agent", …)` with your Step 1 shape in one line and the top three
candidates with their points, for example `Picked X (6) over Y (4) and Z (2)`. When Step 3b added
points, give them separately: `Picked X (4+2 from this domain's figures) over Y (5)`. When the script is
written in a person's choice, say so: `Written in W (chosen by a person); Auto's pick was X (6)`.

If the call refuses:

- **already picked:** read `get_video` again and write the script in `formula_routing.pick`.
- **the style is not decided:** the style comes first. Run tubematic-style-routing, then this
  skill again.
- **not available:** the setting changed since you read the list. Read `get_video` again and
  decide again from the new list.
- **a recent formula with no `repeat_reason`:** go back to Step 4. Take another clear fit, or call
  again with `repeat_reason` when there is none.
- **the domain's watch figures changed since you read `get_video`:** another video of the domain
  was picked in between, a setting changed or new analytics arrived. Read `get_video` again and go
  back to Step 3b with the new points and `stamp`.
- **`formula_routing` has no `learned`, or a candidate has no `learned`:** the server is older than
  these instructions. Count its points as 0 and pass no `learned_stamp`.
- **`get_video` has no `formula_routing`, or the tool does not exist:** the server is older than
  these instructions. Take `follow-the-flow` for an explanation or `scene-story` for a true case,
  add a comment saying the formula could not be recorded before the script, and go on to the
  script. `update_video` records the formula with the script on such a server.

## A revision

A script revision keeps the formula: rewrite in `formula_routing.pick`.

Run this skill at `REVISION_REQUESTED` only for a script revision (the operator skill decides
which kind of revision it is), and only in two cases. The candidates are in `get_video` then.
A new formula always means a new script that goes back to `SCRIPT_READY` for a person to approve;
never take a video on to voicing or scenes after a pick in a revision.

- **The person's comment asks for a different structure** ("tell it as a story", "make it a
  list") and `formula_routing.choice` is `""`. Decide as above, with the comment as the strongest
  hint, and call `choose_script_formula`: it replaces the pick. Pass the old pick as `runner_up`
  unless another candidate scored higher. When `formula_routing.choice` is set, a person chose the
  formula: the tool refuses, the script is rewritten in that formula, and your comment says the
  chosen formula was kept and that the runner-up can be taken at Script Ready.
- **The video has no formula this version knows:** `formula_routing.pick` is `""` and the stored
  `formula_id` is `""` (it was scripted before formulas were picked) or not among the candidates
  (a later version dropped it). Decide as above and record it. The
  style is not checked here: the video keeps the style it has.

## Worked example

The ids below are invented for the example; your list will differ.

A video titled "The command that took a storage service down for four hours", in the style
`flow_diagram`, with a brief that gives the date, the command, what it removed and how long the
service was down. `formula_routing.recent.formulas` is `["case-timeline", "belief-and-break"]`.

- Step 1: an incident with a timeline; real: a date, a duration, one engineer's command, the
  service's own status page failing; the style asks for one step per sentence in the order things
  happened.
- Step 2: `odd-evidence` is out (no real anomaly). `news-angle` is unavailable (experimental
  formulas are off).
- Step 3: `case-timeline` has "an outage with a timeline" in `best_for` (3), three true signals
  (3) and `suits_style` (1): 7. `walk-the-path` has "a failure that proceeds step by step" in
  `also_for` (1), one signal (1), `suits_style` (1) and the style's shape (1): 4. `one-person` has
  a close neighbour (1) and one signal (1): 2.
- Step 3b: `formula_routing.learned.active` is `false` (the domain has too few videos with
  figures), so nothing is added.
- Step 4: `case-timeline` wins but is `recent`. `walk-the-path` is a clear fit and is not: take
  it.
- Step 6: the runner-up is `case-timeline` (7).
- Step 7: `choose_script_formula(video_id, "walk-the-path", "One command's effects, followed step
  by step through the systems it took down.", "case-timeline")`, then the comment
  `Incident with a timeline; date, duration and command are real. Picked walk-the-path (4) over
  case-timeline (7, used in the last two videos) and one-person (2).`

## Checklist

- [ ] The style was decided, `formula_routing.decided` was `false` and the video is at
      `TOPIC_APPROVED` (or a revision whose comment asks for another structure, with no person's
      choice)
- [ ] The topic's shape and its real facts written down before reading the candidates
- [ ] Unavailable candidates, plain `avoid_for` matches and formulas the facts cannot fill ruled
      out
- [ ] Points counted by meaning from `best_for`, `also_for`, the angle, `signals` and the style
- [ ] `learned.points` added to the clear fits only, and to nothing else
- [ ] A `recent` formula passed over for another clear fit, or kept with `repeat_reason`
- [ ] Your own best formula passed, also when a person chose one
- [ ] `choose_script_formula` called with a one-sentence reason and a runner-up
- [ ] The script written in the returned `formula_pick`
- [ ] A comment with the shape and the top three scores
