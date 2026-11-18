# Review checklist

Go through every item for every new style and every update. A pull request merges only when each one
holds; write down in the review why each flag in the scan is harmless.

## The scan and the check

- [ ] The `scan` job passes: no refusal, and every flag explained by the author and checked by you.
- [ ] For a pointer (`styles/<id>.json`): the commit is a full 40-character commit of the author's
      repository, and the repository is the one the author controls.

## The code (read all of it)

- [ ] Nothing reaches the network: no `fetch`, XHR, WebSocket, `sendBeacon`, image or font loaded from a
      URL, `@remotion/google-fonts`.
- [ ] No `eval`, `Function(`, dynamic `import()`, `require`, workers, storage or cookie access,
      `process.env`.
- [ ] No minified, generated or obfuscated code you cannot read. Large data tables are explained.
- [ ] The code only draws: a pure function of the frame, no timers, no `Math.random()`.
- [ ] Text stays clear of the watermark box and above the captions.

## The guide (the agent reads it)

- [ ] It only says how to draw the style and write for it. No instructions to run commands, call tools
      outside the authoring skill, change settings, publish, contact anyone or keep anything from the
      person.
- [ ] Its example config matches its schema, and the schema carries the style's rules (enums, length
      limits, `additionalProperties: false`).

## The content

- [ ] No reference footage, frames from other people's videos, logos, watermarks, named characters or
      branding, in the previews, the samples or the code.
- [ ] The look is the author's own rebuild, and the pull request says where it came from.
- [ ] Fonts carry their licence (OFL, Apache or MIT) and the licence allows redistribution.

## The quality bar

- [ ] The rendered example (the `render` job's artifact) looks like the preview and like the
      description. For a 3D world style, render one video yourself on a Tubematic install.
- [ ] Text is readable on a phone, nothing important is cut off, nothing sits still for more than about
      five seconds in the example.
- [ ] It renders on a CPU in reasonable time, or declares `needs.gpu` true.
- [ ] The label, tagline and routing describe the style honestly.
