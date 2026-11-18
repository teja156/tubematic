# Submitting a style

1. Make the style. Tubematic's `/tubematic-create-style` builds a package from reference videos and
   checks it by staging it on your own install. Install it and render a few videos in it first.
2. The package must pass Tubematic's check and scan with no refusals. Each flag in the scan needs a
   reason in your pull request.
3. Open a pull request that adds one of:
   - `styles/<id>/`: the package folder itself (style id = folder name), or
   - `styles/<id>.json`: `{"repo": "https://github.com/you/your-style", "commit": "<40-hex commit>"}`
     for a package at the root of your own repository. A branch or tag is not accepted: the reviewed
     bytes must be the published bytes.
4. In the pull request, say: what the style looks like and what it suits, where its look came from,
   that no reference footage, frames, logos, watermarks, named characters or branding are in it, and
   the licence of its code and fonts.
5. To update a published style, bump `external.version` and open a new pull request (a new commit for
   a pointer). A changed package is reviewed again.

A maintainer reviews it against [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md). Merging publishes it.
