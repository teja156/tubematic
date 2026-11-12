---
name: tubematic-insert-routing
description: Decide whether a video's script will use short insert scenes (a diagram of parts, a string on screen) inside its main style, and which insert styles — read the candidates from get_video's insert_routing, list the beats the narration will reach, keep only beats an insert shows clearly better than the main style, and record the choice with choose_inserts
---

# Tubematic insert routing skill

**Invoke this skill when:** a video is at `TOPIC_APPROVED`, its main style is decided
(`get_video(video_id).style_routing.decided` is `true`), and `insert_routing.decided` is `false`.
Run it once, after the style routing skill and before the formula routing skill. Then go back to the
operator skill.

When `insert_routing.decided` is `true`, do not run this skill: inserts were chosen already, the
video's Inserts setting is None, or its main style takes no inserts.

---

## What an insert is

A video has one **main style**. It carries the opening, the payoff and the ending, and almost every
second of the video. An **insert** is a short scene (at most about 8 seconds) in another look, shown
over the main style where the narration reaches something that look shows best: a request travelling
between components, a password being hashed or a command being typed.
The main style's captions stay on screen through it, and the video goes back to the main style after
it.

An insert costs the viewer a change of look. It earns that only when it shows the beat clearly better
than the main style can. **Most videos need none.** Two inserts of the same kind in one video are
fine; an insert added for variety is a defect.

## The candidates are data

`get_video(video_id).insert_routing` holds:

| Field | Meaning |
|---|---|
| `candidates` | Every insert style: `id`, `label`, `routing` (`best_for`, `avoid_for`, `signals`, `cannot_show` when present), `max_seconds`, `script` (how an insert segment is narrated), `available` |
| `host`, `transition` | Whether the main style takes inserts, and how it goes into one |
| `max_styles` | The most insert styles one video may use |
| `limits` | The limits the scene check enforces: `target_seconds`, `max_seconds`, `max_share`, `min_main_gap_seconds` |

Read the insert styles only from `candidates`. The main style's own `routing` is in
`style_routing.candidates` (the entry whose `id` is the video's `visual_style`, or `scenes` when
`visual_style` is `auto`); read its `best_for` too.

## Step 1: list the beats

From the title, the topic brief, the angle and the comments, write down the four to eight things the
narration will show, in order, one line each ("the browser asks the resolver", "the resolver walks
root, TLD, authoritative", "the answer is cached for an hour"). Mark the opening beat and the payoff
beat (the answer the video builds to). Those two belong to the main style and are never inserts.

## Step 2: keep the beats an insert shows better

For each other beat and each available candidate, the beat is an **insert beat** for that candidate
when all of these hold:

1. One of the candidate's `best_for` entries squarely describes the beat (a reader would agree at
   once). Match the meaning, never a shared word.
2. None of its `avoid_for` entries describes the beat, and its `cannot_show` (when present) does not
   cover what the beat must show.
3. The main style cannot show the beat as well. When the main style's own `best_for` already names
   what the beat is (a Whiteboard working through arithmetic, an Under the Hood close-up of a part),
   the main style shows it and the beat is not an insert beat.
4. The beat can be said in one segment of at most about 8 seconds of narration (about 20 words).

## Step 3: decide

- Choose the candidates that have at least one insert beat, at most `max_styles`.
- Choose none (`[]`) when no beat qualifies. That is the right answer for a story, a list of habits,
  a history told through people, and most topics about real things the viewer came to see.
- Never choose a candidate for a beat you would only add to make the video "more visual".

## Step 4: record it

```
choose_inserts(video_id, inserts=[<ids>], reason=<one sentence>)
```

`reason` is one sentence of at most 300 characters for the person who approves the script: the beat
an insert shows ("The request's path from browser to server is a diagram insert.") or why none
helps ("A personal story with nothing to diagram or type.").

Then `add_comment(video_id, "agent", …)` with your beat list in one line and the insert beats you
found, for example `Beats: ask, resolve, cache, answer. Insert: resolve (system_flow).`

The script-writing skill then marks the segments that carry those beats. Choosing a style does not
oblige the script to use it.

If the call refuses:

- **already chosen, or the main style not decided:** read `get_video` again and follow what it says.
- **Inserts setting is None, or the main style takes none:** there is nothing to choose; go on.
- **the tool does not exist:** the server is older than these instructions. Go on without inserts.

## Checklist

- [ ] The main style was decided and `insert_routing.decided` was `false`
- [ ] Beats listed before reading the candidates; opening and payoff marked as the main style's
- [ ] A beat counted only when a candidate's `best_for` squarely names it and the main style's does not
- [ ] `[]` chosen when no beat qualifies
- [ ] `choose_inserts` called with a one-sentence reason, then a comment with the beats
