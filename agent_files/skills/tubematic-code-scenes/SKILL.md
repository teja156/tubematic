---
name: tubematic-code-scenes
description: Author a Code Scenes insert as data — a few lines of real source code on an editor card inside another style's video, changing step by step as the narration explains it (the highlight moves to the line being read, an error callout opens under a bug, the code morphs into its fix, a small pane shows what it prints) — for a segment the script marked as a code_scenes insert
---

# Tubematic Code Scenes authoring skill

**Invoke this skill when:** a video's script marked a segment `"insert": "code_scenes"` and the main
style's skill sends you here through the **tubematic-inserts** skill to write that insert's data.
Code Scenes is an insert style only: it is never a video's own style. Read **As an insert**, write
the data, and go back to tubematic-inserts.

---

## As an insert

- **You write one entry of the config's `inserts`, not a scene.** `{"style": "code_scenes",
  "startFrame": ..., "durationInFrames": ..., "props": {"codeScenes": {...}}}`. Never put a
  `CodeScenes` scene in `scenes`: the tool refuses it.
- **The window comes from the marked segment.** tubematic-inserts says how to place it: on a word
  of that segment, 2 to 8 seconds long.
- **The first step starts at the insert's `startFrame`.** Every other `at` is a frame of the video,
  from `get_timeline(video_id, include_words=True)`, inside the window, on the first frame of the
  word that names what changes.
- **Leave `subtitles` alone.** The main style's captions stay on screen over the insert; the card
  moves clear of them by itself.
- **Leave out `src`, `palette` and `shift`.** The look follows the video's canvas: a dark card on a
  dark video, a white card on a light one.
- **No mascot cue inside the window, or in the transition frames just before and after it.** The
  mascot is hidden while the insert slides in, plays and slides out.
- There are no images in this style: never call `generate_image` for it.

## What you are making

A code editor card fills the top of the frame: a tag in capitals above it ("SQL INJECTION"), a
step counter with a short label ("2/3 · the exploit") and one progress segment per step, then the
card with its file name and line numbers. The narration reads the code, and the card follows it:

- **Focus.** The lines the narration is about carry a highlight bar; the others dim.
- **An error.** A red squiggle draws under the characters at fault and a red-ruled callout opens
  under the line with a short message; the lines below slide down to make room.
- **A change.** The code morphs into its next version: pieces of code that stay glide to their new
  places, removed pieces fade, new ones fade in. Unchanged code holds perfectly still.
- **Output.** A small OUTPUT pane under the card shows up to three lines the code prints, with an
  optional label ("3 rows"). Output belongs to the code on screen: when the code changes, the pane
  clears.

The tokeniser colours the code by language. You write only data: the language, the code as text,
and one to four steps timed to the narration.

## Code Scenes or Terminal Doc

Both put text on a screen, so pick by what the narration is about:

| The narration is about | Insert |
|---|---|
| Source code being read, written or fixed: a line, a bug, its fix, two versions, what a snippet prints | Code Scenes |
| A command typed at a shell and what it prints (`git`, `curl`, `nmap`, `ls`) | Terminal Doc |
| One string, password or hash transformed step by step, or one big number | Terminal Doc |

The script was written for the insert it was marked with; follow the mark.

## The data

```json
{"lang": "python", "file": "users.py", "tag": "SQL injection",
 "steps": [{"at": 612, "code": "...", "label": "the bug", "focus": [3]}, ...]}
```

| Key | What it is |
|---|---|
| `lang` | One of `python`, `javascript`, `typescript`, `sql`, `c`, `java`, `go`, `rust`, `json`, `yaml`, `html`, `css` |
| `file` | Optional file name on the card's tab, at most 24 characters |
| `tag` | Optional topic tag above the card, at most 24 characters |
| `steps` | One to four steps, in time order |

A step:

| Key | What it is |
|---|---|
| `at` | The frame it starts on. Step 1: the insert's `startFrame`. Later steps: a word's first frame |
| `code` | The whole code as text, from this step on. Step 1 must have it; leave it out to keep the code as it was |
| `label` | Optional short label for the counter, at most 24 characters ("the bug", "the fix") |
| `focus` | Optional line numbers (from 1) the narration is about; the other lines dim |
| `error` | Optional `{"line", "match", "text"}`: the line, characters on it as written to underline, and a message of at most 48 characters |
| `output` | Optional `{"lines", "label"}`: up to 3 lines of at most 40 characters the code prints, and an optional label of at most 12 characters. No lines needs a label ("0 rows") |
| `reveal` | Step 1 only, `"type"`: types the code in. For a line or two (at most 120 characters) |

## Rules the tool enforces

`write_scene_config` refuses an insert that breaks any of these, naming the step:

- At most 14 lines of code and 40 characters per line, indented with spaces (no tabs). Show only
  the lines the narration is about: a whole function rarely fits, and a phone cannot read it.
- At least 45 frames (1.5 s) between steps; the last step starts at least 30 frames before the
  insert's end; nothing holds still for more than 3 seconds, so an 8-second insert needs about
  three steps.
- A later step's `code` must differ from the code before it; a step that only moves the focus,
  the error or the output leaves `code` out.
- `focus` and `error.line` name lines the code has; `error.match` is on that line as written.
- Output never starts with a shell prompt (`$ `, `# `, `> `). A typed command is Terminal Doc's.
- A typed first step finishes typing before step 2.

## Step 1: the code

- Write real code in the language you name, short and correct: the smallest snippet that shows the
  point. Shorten names before you break lines (`db`, `rows`, `user`).
- Keep the code the viewer reads in the order the narration reads it. A bug and its fix are two
  versions of the same snippet: change only what the fix changes, so the morph shows the change and
  everything else stays still.
- Never put a real secret, a real person's name or a working exploit against a named live service in
  the code. Use the textbook example of the bug.

## Step 2: the steps

Read the marked segment's words. Give each change its own step on the word that names it:

- "the f-string on line three" → `focus: [3]` on "f-string"
- "Python raises an IndexError" → `error` on "IndexError"
- "and every row comes back" → `output` on "every"
- "a placeholder fixes it" → the fixed `code` on "placeholder"

Step 1 already shows the code and, when the first sentence is about one line, its focus.

## Step 3: output only when it is certain

The output pane shows what the code on screen prints, and nothing runs it for you. Show output only
when it follows directly and certainly from the code itself: a value the code prints, a row count
it leads to, or the language's own error message for the line at fault, word for word. When you are
not certain what the code prints, leave `output` out and let the narration describe the result. The
AI review checks the pane against the code, and a wrong pane sends the video back.

## Worked example

The marked segment (frames 612 to 845) says: "Your name goes straight into the query. Type a quote,
OR one equals one, and every row comes back. A placeholder keeps what you type out of the SQL." The
full entry, with the word frames it was timed to, is `reference/example-insert.json`:

- step 1 at 612 ("Your"): the vulnerable code, focus on the f-string line;
- step 2 at 676 ("Type"): the error callout under `{name}`;
- step 3 at 731 ("every"): focus on the loop, the output pane with three rows;
- step 4 at 790 ("placeholder"): the code morphs to the parameterised query; the output clears.

## Check and submit

Go back to **tubematic-inserts** with the entry. The main style's skill writes the whole config with
`write_scene_config`, validates it and submits it; a refusal about this insert names the step, and
you fix it here.

## Checklist

- [ ] One entry in `inserts`, style `code_scenes`, over the marked segment; no `CodeScenes` scene
- [ ] Step 1 at the insert's `startFrame` with the code; later steps on the words that name them
- [ ] At most 14 lines of 40 characters, spaces only, real and correct code
- [ ] A change every 3 seconds or sooner; the last step 30 frames or more before the end
- [ ] Output only when certain from the code, never a shell prompt
- [ ] `src`, `palette`, `shift` and `subtitles` left alone; no mascot cue in or near the window
