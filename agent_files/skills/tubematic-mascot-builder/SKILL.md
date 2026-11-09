---
name: tubematic-mascot-builder
description: Build or revise one mascot, an animated watercolour character drawn by p5.js code that Tubematic videos can show on screen reacting to the narration. Write the drawing code, render its three model sheets, look at every one, fix what is wrong and submit it for a human to review
---

# Tubematic mascot builder

**Invoke this skill when:** the poller (or a person) asks you to build a mascot and gives you a mascot id. You
work on that one mascot only. You never touch a video, another mascot, or any file: the code goes in and the
sheets come out through the MCP tools, and the tool descriptions own their exact shapes (this skill does not
repeat them).

A mascot is a character that sits on top of a narrated Short and **reacts** to what the narration says: it
changes expression, emotes, looks around, hops, walks. **It never talks.** It is never presented as the
narrator, so there is no talking mouth and nothing is lip-synced. The mouth only ever shows the current emotion.

A shared engine already provides the expressions, emotes, mouths, squash and stretch, acted emotion changes,
walking and the paper-sticker look. You write only the **body**: one drawing function. The full contract,
the options the engine hands you, the drawing helpers and the traps are in `reference/guide.md` in this
skill's directory. **Read it before writing a line.**

## Workflow

1. Call `get_mascot_job` and read the job. `kind` tells you what to do:
   - **new**: draw the character in `description`.
   - **surprise**: there is no description; invent a character of your own with a clear silhouette and a
     face area, and say in your notes what you made. Keep it kind and simple to read at sticker size.
   - **change**: a human reviewed a version and asked for `change_request`. Start from `previous_code` and
     change what was asked, **literally**: do not redesign what they did not mention, and do not "improve"
     things beside it. If the request cannot be done within the contract, say so in your notes.
   - A non-empty `based_on_code` (any kind) is another mascot's approved code to start from: keep its
     structure and helpers, and change the shape, colours and features into the described character.
   - A fresh `new` with no `based_on_code` has no code to start from: build from the contract in the guide.
2. Write the complete drawing code (one file's worth of JavaScript, as a string).
3. Render and look. Call `render_mascot_sheets` with the code and **one** sheet name per call: `turn`,
   `feels`, `act`. A successful call returns a picture; a failed render returns an error instead (read it, fix
   the code, call again: the failure still cost a render). **Look at every picture** with your image-viewing ability
   before deciding anything. Code that runs is not a mascot that looks right. Judge it against the checklist
   below, fix the code, and render again.
4. Mind the cap. Every render counts, a failed render too, and `renders_left` (in each result and in
   `get_mascot_job`) says how many remain. Plan for it: a first full pass is three renders, so you have room
   for about one more full pass, or a few single-sheet fixes. Changing the code discards the sheets rendered
   from the old code, so the last renders you make must be of your **final** code: before you run out, make
   sure all three sheets exist for the code you will submit.
5. Call `submit_mascot` when the checklist passes **or** when you are about to run out of renders with all
   three sheets rendered for the current code. **Never finish a run without submitting once all three sheets
   exist for the current code**: a good-enough mascot goes to the human, who can ask for changes; an
   unsubmitted one is a lost attempt. If you cannot get all three sheets rendered (the code keeps failing),
   stop and say so: do not submit and do not invent a result.
6. Put honest `notes` on the submission: what the character is, what you changed in this attempt, and which
   checklist items do **not** pass. Do not claim a pass you did not see.

## Checklist (judge the pictures against it)

- It reads as the description (or, for a surprise, as one clear character) at a glance, in all five turnaround
  poses: front, three-quarter, side, back, and the three-quarter flipped.
- The three-quarter and side views look like the same character turned, not a different drawing. A turn is
  never faked by squashing the front view.
- In every view and every emotion, nothing covers the eyes (raised arms included) and nothing floats detached.
- The face sits on a **light area** of the body, so the ink eyes and mouth read on it in every mood tint.
- All ten emotions on the feels sheet are readable on its face; emotes sit near the head, not on it.
- On the act sheet the legs step while walking, the jump stretches and squashes, and the mouth shows the
  emotion only: it is not a talking mouth.
- The paint is clean: no stray olive or grey bleed from a fill, no first-figure wash missing (see the guide's
  brush traps), no page error reported by the render.
- The drawing is a pure function of its options and the time (see **Determinism** in the guide).

## Rules

- Work only through `get_mascot_job`, `render_mascot_sheets` and `submit_mascot`. Do not advance or edit any
  video, do not read or write other mascots, do not write files, do not run shell commands.
- The code must not use the network, web fonts, images from a URL, `fetch`, `import`, or anything that names
  a character from another product. Draw everything with the helpers.
- Keep the function lean: the render tool states a maximum code size, and a tidy mascot is far below it.
