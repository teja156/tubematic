# Template style: how to write a video in it

This is the template the creation skill starts from; a real package replaces every word of this guide.

## What it looks like

One card per beat on a flat background: a heavy headline that rises in, an accent bar that draws out
under it, and up to three short lines that slide in on the words that say them. One palette for the
whole video.

## The script

Short declarative sentences, one idea each. Every beat's `visual` names the headline (at most five
words) and the lines that appear under it.

## The scenes

- Every scene is `{"type": "generated", "source": "external", "src": "ext_template/components/Card",
  "props": {"card": {...}}}`, one per beat, back to back from frame 0 to the last frame.
- `title`: the beat's idea in at most 5 words (32 characters).
- `lines`: 0 to 3 lines of at most 26 characters, each the words the narration says while it shows.
- `lineAt`: for each line, the frame of the scene on which its first word is spoken (word timings come
  from `get_timeline`; subtract the scene's `startFrame`).
- `palette`: the same for every scene of the video.

## Opening, turn, payoff, ending

- Opening: scene 1 is on screen from frame 0 with its headline already the first sentence's idea.
- Turn: a new card on the first word of a turn.
- Payoff: the card whose headline states the takeaway.
- Ending: hold the last card to the last frame; no closing card after it.

## Look before you submit

Take `preview_frames` on a frame of each scene once its lines are in, and on the first frame.
