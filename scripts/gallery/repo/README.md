# Tubematic style gallery

Visual styles for [Tubematic](https://github.com/teja156/tubematic) that a maintainer reviewed before
publishing them. Tubematic's dashboard lists them under **Profiles → Styles → Gallery**, and every
install checks the downloaded package against the checksum in this gallery's index.

- The index: https://tejaswaroop.com/tubematic-styles/index.json
- To submit a style, read [SUBMITTING.md](SUBMITTING.md).
- Reviewers follow [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md).

A style package is code that runs in Tubematic's renderer. A review lowers the risk of installing
one; it does not remove it.

## How it works

- `styles/<id>/` is a package submitted into this repository, or `styles/<id>.json` points at the
  author's own repository at a pinned commit: `{"repo": "https://github.com/someone/style", "commit":
  "<40-hex commit>"}`.
- Every pull request runs the same check and scan an install runs (`scan`), and renders a scene
  style's example (`render`), attached to the run for the reviewer.
- Merging to `main` publishes: `build` writes a deterministic zip of each package, its sha256, its
  previews and `index.json`, and the workflow deploys them to GitHub Pages.

The tools are `scripts/gallery.py` in the Tubematic repository; the workflows check it out at the
version in `TUBEMATIC_REF`.
