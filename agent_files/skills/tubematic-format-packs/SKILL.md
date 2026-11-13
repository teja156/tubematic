---
name: tubematic-format-packs
description: Author a Format Packs insert as data — one phone-native format inside another style's video (a made-up message thread with its tells marked, a short numbered list, a quiz with a locked answer, or a dated news strap with a changing value), timed to the narration, with no real app, brand, account or phone number — for a segment the script marked as a format_packs insert
---

# Tubematic Format Packs authoring skill

**Invoke this skill when:** a video's script marked a segment `"insert": "format_packs"` and the main
style's skill sends you here through the **tubematic-inserts** skill to write that insert's data.
Format Packs is an insert style only: it is never a video's own style. Read **As an insert**, write
the data, and go back to tubematic-inserts.

---

## As an insert

- **You write one entry of the config's `inserts`, not a scene.** `{"style": "format_packs",
  "startFrame": ..., "durationInFrames": ..., "props": {"formatPacks": {...}}}`. Never put a
  `FormatPacks` scene in `scenes`: the tool refuses it.
- **The window comes from the marked segment.** tubematic-inserts says how to place it: on a word
  of that segment, 2 to 8 seconds long.
- **The first message, row or headline is on screen at the insert's `startFrame`.** Every other
  `at` is a frame of the video, from `get_timeline(video_id, include_words=True)`, inside the window,
  on the first frame of the word that reads it.
- **Leave `subtitles` alone.** The main style's captions stay on screen over the insert; the format
  moves clear of them by itself.
- **Leave out `src`, `palette` and `shift`.** The look follows the video's canvas: dark ink on a
  dark video, paper on a light one.
- **No mascot cue inside the window, or in the transition frames just before and after it.** The
  mascot is hidden while the insert slides in, plays and slides out.
- There are no images in this style: never call `generate_image` for it.

## What you are making

One format per insert, chosen by what the narration does in the marked segment:

| `format` | When the narration | What the viewer sees |
|---|---|---|
| `chat` | quotes messages sent between people: a scam text, a DM, a pretext | A plain phone with a generic contact; bubbles arrive one by one (typing dots before theirs), and red underlines or rings mark the tells, each with a short label |
| `list` | counts two to four short points in one breath | A title and numbered rows, each arriving as it is read |
| `quiz` | asks the viewer a question with options | The question, the options popping in as they are read, then the answer locking in amber |
| `strap` | reads a dated headline, or a value that changed | A news strap with a kicker and the date, words of the headline highlighted, and a split-flap board flipping from one value to another |

## Nothing passes for real

The component draws a plain phone with no maker's look, and an **EXAMPLE** tag on every message
thread and on every headline without a `source`. It cannot be switched off, and you must not try to
work around it. In the data:

- Every thread is made up. Never name a real bank, courier, shop, app or person in a message, a
  contact or a title: write "your bank", "a parcel company", "Unknown number", "Mum".
- A phone number only from the ranges kept for fiction: UK `07700 900000` to `07700 900999`, US
  `555-0100` to `555-0199`. The tool refuses any other number anywhere in the data, however it is
  written (spaces, dashes, dots or slashes). A price, a date or a plain count is not a phone
  number.
- No tick or verified mark, anywhere. No app name (WhatsApp, iMessage, Instagram, TikTok and the
  like) in a contact, a title or a kicker.
- A `strap` headline is either a real headline quoted word for word with its `source` ("Reuters,
  12 Mar 2026"), or made up and left without one, so it carries the EXAMPLE tag. Never invent a
  source.

## The data

Every format holds `format` and its own keys. Lengths are counted in characters.

**chat**: `title` (optional, one line above the phone: about 22 characters, fewer with wide letters), `contact` `{name, number}` (name at most 24; number
optional, fiction ranges only), `messages` (2 to 5, each `{at, from, text}`, `from` `"them"` or
`"me"`, text at most 90), `marks` (at most 3, each `{at, message, match, kind, label}`: `message` is
the message's index from 0, `match` the words in it to mark as written, at most 22, `kind`
`"underline"` or `"ring"`, `label` at most 16; one labelled mark per message; marks on one message never overlap).

**list**: `title` (at most 40, two lines), `items` (2 to 4, each `{at, lead, text}`: a lead of at
most 24 and a text of at most 64 that fits two lines).

**quiz**: `question` (at most 80, three lines), `options` (2 to 4, each `{at, text}`, text at most
30 and fitting one row), `answer` (the right option's index from 0), `lockAt` (the frame the answer locks in, on the
word that gives it).

**strap**: `kicker` (at most 20), `headline` (at most 70, three lines), `date` (at most 24),
`source` (optional, at most 40), `marks` (at most 2 `{at, match}` highlights on the headline's
words, never overlapping), `flap` (optional `{label, from, to, at}`: a value of at most 10
characters flipping to another, letters, digits and signs only; the tiles that change flip one after
another, so start it early enough to land before the last 30 frames).

## Rules the tool enforces

`write_scene_config` refuses an insert that breaks any of these, naming the part at fault:

- The first message, row or headline arrives at the insert's `startFrame`; each later arrival, mark
  and lock is on a word (within 2 frames), at least 18 frames after the one before, and at least 30
  frames before the insert's end.
- Nothing holds still for more than 3 seconds: an 8-second insert needs a change about every two to
  three seconds (a message, a mark, a row, an option, the lock, a highlight, the flip).
- The messages fit the phone together, and the list fits the frame; a mark lands after its message
  is on screen. Lines are counted by the width of the words, so wide letters (W, M) take more room
  than their count.
- The quiz locks at least 18 frames after its last option.
- The impersonation rules above.

## Timing it to the narration

Read the marked segment's words, then:

- **chat**: message 1 at the insert's first frame; each later message on the first word that reads
  it; each mark on the word that names the tell ("the new number", "today", "eight hundred").
- **list**: row 1 at the first frame; each row on its lead word.
- **quiz**: the question is on screen from the first frame; each option on the word that reads it;
  `lockAt` on the word that gives the answer.
- **strap**: the headline at the first frame; highlights on the words read; the flip on the new
  value.

## Worked example

The marked segment (frames 612 to 845) says: "Hi Mum, I dropped my phone, this is my new number.
Oh no, you OK? Then the new number, and the ask: I need to pay a bill today, send eight hundred
pounds." The full entry, with the word frames it was timed to, is `reference/example-insert.json`:

- message 1 at 612, the reply at 676, the underline on "new number" at 701;
- the request at 731, the ring around "£800" at 790;
- the contact is "Unknown number" with a fiction-range number, and nothing names a real app.

## Check and submit

Go back to **tubematic-inserts** with the entry. The main style's skill writes the whole config with
`write_scene_config`, validates it and submits it; a refusal about this insert names the part at
fault, and you fix it here.

## Checklist

- [ ] One entry in `inserts`, style `format_packs`, over the marked segment; no `FormatPacks` scene
- [ ] One format, chosen by what the narration does
- [ ] The first item at the insert's `startFrame`; later ones on the words that read them
- [ ] A change every 3 seconds or sooner; nothing in the last 30 frames
- [ ] No real app, brand, account, person, tick or phone number; a strap headline is quoted with
      its source or left without one
- [ ] `src`, `palette`, `shift` and `subtitles` left alone; no mascot cue in or near the window
