# Storybook Reveal: the data contract

Every field of `props.reveal`, with its limits. `write_scene_config` checks all of it. The renderer's
side is `renderer/remotion/src/scenes/installed/storybookReveal/contract.ts`.

## The page

A 1080 x 1920 page in fixed zones, so nothing you write can land on another zone:

| Zone | From (y) | To (y) | Holds |
|---|---|---|---|
| Top margin | 0 | 230 | Plain paper |
| Title band | 230 | 390 | The title in hand-lettered capitals, one line, with a pencil swash under it at y 362 |
| Panel | 410 | 1280 | The picture, 900 x 870 px from x 90, in a rounded panel with a soft vignette |
| Captions | 1300 | 1500 | The captions, centred at 1382 (72%), no plate |
| Page number | about 1610 | about 1670 | "~ n ~", centred at y 1640 |

The picture is fitted whole inside the panel: a square still is 870 x 870 px, in
the middle, with its edges fading into the panel's paper. It is never cropped. After the colour lands it
pushes in slowly from 1 to 1.06 until the page ends, keeping its `focus` point in place. The title is
set at 92 px, or smaller down to 56 px so that it fits one line of 880 px.

## The whole video

```json
{"totalFrames": 908, "canvas": "light",
 "scenes": [{"type": "generated", "source": "installed", "src": "StorybookReveal",
             "startFrame": 0, "durationInFrames": 908,
             "props": {"reveal": {"pages": [ ... ]}}}]}
```

| Field | Rule |
|---|---|
| `pages` | 1 to 24 pages, in frame order. The first starts at frame 0 |

## A page

| Field | Rule |
|---|---|
| `start` | The page's first frame. 0 for the first page; on a word for the others. A page lasts at least 2.5 s |
| `title` | 1 to 3 words, at most 24 characters, on one line. Drawn in capitals |
| `image` | `/public/<video_id>/images/<name>.png`, the `public_path` from `generate_image`. Never the hero sheet (`hero`) |
| `pencil` | `/public/<video_id>/images/treated/<name>.pencil.png`, the `public_path` from `treat_image(video_id, "<name>", "pencil")` for the same `<name>` as `image` |
| `focus` | Optional. `[u, v]`, each from 0 to 1 (default `[0.5, 0.5]`): the point of the picture the slow push keeps in place, read off `read_image`'s grid |
| `pencilAt` | The word the pencil plate starts wiping in on, at least 6 frames after `start`. The first page may give 0 instead: its drawing is on screen whole from frame 0 |
| `colourAt` | The word the colour starts flooding in on, 12 to 30 frames after `pencilAt` (within a second of the pencil); the flood (18 frames) ends at least 8 frames before the page does |
| `turn` | Optional. `"cut"` (the default) or `"curl"`: the page before turns over from its bottom-right corner into this one. At most 2 curls a video, never on the first page |

At most 12 different `image` pictures per video. A page may show a picture again.

## Timings

In frames at 30 fps: the title wipes in over 10, the pencil plate over 12, the colour over 18, and a
curl takes 14. Time the colour to a word within a second of the pencil: from the pencil's first frame to
the colour landing takes at most 48 frames (1.6 s). Every `start` (but the first), `pencilAt` (but a first page's 0) and `colourAt` is within
2 frames of a word's `startFrame`.

On each page something new must happen at least every 6 seconds: from the page's start to its pencil
wipe, and from the colour landing to the page's end. The slow push
does not count, and a stretch inside an insert window is not counted. Inside an insert window no page
starts, no pencil wipes in and no colour floods.
