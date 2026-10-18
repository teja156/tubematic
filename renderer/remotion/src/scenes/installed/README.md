# Installed Scene Library

Scenes in this directory are **committed and baked into the renderer image** — they are the
curated, reusable counterpart to `../generated/` (where the agent authors bespoke, per-video
scenes at runtime).

## Convention

- Every scene here **must be generic and prop-driven** — no topic-specific content hardcoded into
  the component. A scene belongs here only if it's plausibly useful across multiple, unrelated
  videos (e.g. "a labeled step-flow diagram" is generic; "the DNS resolution hops" is not).
- Export the component as `export default`, matching the pattern `CompositionBuilder.tsx` expects
  from a dynamic scene import.
- Document the component's props with a TypeScript `interface`/JSDoc at the top of the file — this
  is what the agent reads to decide whether an installed scene fits a given script beat.

## How scenes get here

There is **no runtime "install" tool.** Promotion is a deliberate human step:

1. The agent authors a scene into `../generated/{video_id}/` (via the `write_scene_file` MCP tool)
   for a specific video.
2. A human reviews it, generalizes any hardcoded content into props, and copies it from
   `mounted/scenes/generated/{video_id}/{name}.tsx` (the host-visible bind mount) into this
   directory — dropping the `{video_id}/` prefix, since an installed scene's name must be free of
   any one video's identity.
3. Commit it. It ships in the image on the next `docker compose build`.

## Referencing an installed scene in `scene-config.json`

Same `"generated"` scene type as an agent-authored scene, plus `"source": "installed"`:

```json
{
  "type":             "generated",
  "src":              "StepFlowDiagram",
  "source":           "installed",
  "startFrame":       540,
  "durationInFrames": 600,
  "props": {
    "steps": [
      { "label": "Your Browser",  "icon": "💻" },
      { "label": "DNS Resolver",  "icon": "🔄" },
      { "label": "Root Server",   "icon": "🌍" }
    ],
    "connections": [[0, 1], [1, 2]],
    "activeStages": [[0, 1], [1, 2]],
    "highlightStage": 0
  }
}
```

Omitting `source` (or setting it to `"generated"`) resolves against `../generated/` as before.

## Current library

| Scene | Props | Good for |
|---|---|---|
| `StepFlowDiagram.tsx` | `steps`, `connections`, `activeStages`, `highlightStage`, `theme` | Any linear process with discrete, nameable stages — protocol hops, pipeline steps, state machines. `theme: "light"` draws it as black line art for the stick register; the default `"dark"` paints an opaque near-black background and would punch a slab through a white-canvas video |
| `KenBurnsImage.tsx` | `src`, `scaleFrom`/`scaleTo`, `panFrom`/`panTo`, `anchor`, `vignette`, `caption` | Dropping a `generate_image` result straight into a beat with a slow camera move — no scene file to author. **Leave `caption` out:** the narration is burned in as subtitles, so a caption naming the subject repeats it. The prop predates that and stays for older videos |
| `PanelImage.tsx` | `src`, `width`/`height`, `x`/`y`, `label`, `caption`, `ink`, `border`, plus the `ImageFX` pan/scale props | A generated image contained in a bordered panel on the canvas — the stick register's answer to a beat whose subject is a real, specific person, creature or place. Full-bleed would replace the white ground and the video would cut between two different-looking worlds |

## Components, not scenes

The remaining files here are **wrappers and helper modules**, never named as a scene-config `src`. Import
them from a scene you are authoring. Because a generated scene lives in `generated/{video_id}/`,
the import is two levels up: `../../installed/StickFigure`, not `../installed/StickFigure`.

| File | What it is |
|---|---|
| `ImageFX.tsx` | Ken Burns wrapper for a full-bleed image; see below |
| `StickFigure.tsx` | The stick register's figure — `pose`, `expression`, `attire`, `headwear`, `x`, `y`, `scale`, `flip`. Poses are a joint table, and a pose change is a prop change on a frame boundary: it never tweens, which is the register rather than a shortcut |
| `StickScene.tsx` | White-ground scaffold — optional comic banner title, optional panel frame. Takes your content as children. Paints no background by default, because the renderer already paints the video's canvas |
| `Entrances.tsx` | `PopIn`, `SlideIn`, `Swap` — the stick register's only three arrivals, at the durations its spec calls for |
| `Subtitles.tsx` | The burned-in captions. Neither a scene nor something you import — `CompositionBuilder` renders it from the top-level `subtitles` key, above every scene. Listed here only so it is not mistaken for a scene you may reference |

## `ImageFX.tsx` — a component, not a scene

`ImageFX.tsx` is the odd one out here: it is a **wrapper component**, not a standalone scene, so it is
never named as a scene-config `src`. Import it from a scene you are authoring when you want an image
background with your own content on top:

```tsx
import ImageFX from "../../installed/ImageFX";   // two levels up, extensionless — see below
```

`KenBurnsImage` is just a thin scene built on it.

Three rules that are easy to get wrong:

- **Go up two levels, not one.** Agent-authored scenes live at
  `../generated/{video_id}/{scene_name}.tsx`, so `installed/` is two directories above the importing
  file. A bare `../installed/ImageFX` resolves to `generated/installed/` and fails to compile.
- **Import it without the `.tsx` extension.** `renderer/remotion/tsconfig.json` has no
  `allowImportingTsExtensions`, so a suffixed import fails `tsc --noEmit` — which is what
  `validate_job` runs, so it fails validation rather than the render.
- **Pass `src` as the raw `public_path` string that `generate_image` returned.** Do not wrap it in
  `staticFile()`. Remotion's static base is literally `/public`, so the returned string is already
  exactly what `staticFile()` would produce, and passing an already-prefixed path into it throws.

A `src` that doesn't resolve is **not** a blank frame — Remotion's `<Img>` retries twice and then
calls `cancelRender()`, which fails the whole render. `validate_job` checks image paths before
`submit_render` precisely so that mistake never reaches the renderer.
