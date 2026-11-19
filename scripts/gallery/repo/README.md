# Tubematic style gallery

Visual styles for [Tubematic](https://github.com/teja156/tubematic) that a maintainer reviewed before
publishing them. Tubematic's dashboard lists them under **Profiles → Styles → Gallery**, and every
install checks the downloaded package against the checksum in this gallery's index.

- Browse the styles: https://gallery.tubematic.ai/
- The index Tubematic reads: https://gallery.tubematic.ai/index.json
- To submit a style, read [SUBMITTING.md](SUBMITTING.md).
- Reviewers follow [REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md).

A style package is code that runs in Tubematic's renderer. A review lowers the risk of installing
one; it does not remove it.

## How it works

- `styles/<id>/` is a package submitted into this repository, or `styles/<id>.json` points at the
  author's own repository at a pinned commit: `{"repo": "https://github.com/someone/style", "commit":
  "<40-hex commit>"}`.
- Every pull request runs the same check and scan an install runs (`scan`), and renders a scene
  style's example (`render`), attached to the run for the reviewer. Until Tubematic 2.4.0 is
  released no published image renders external styles: the render job then passes with a notice,
  and the reviewer renders the example on their own install.
- Merging to `main` publishes: `.github/style-authors.sh` finds the GitHub account that submitted
  each style (the author of the merged pull request that added it), which the gallery shows as its author,
  and `build` writes a deterministic zip of each package, its sha256, its
  previews, `index.json` and the browsable page `index.html`, and the workflow deploys them to GitHub
  Pages.

The tools are `scripts/gallery.py` in the Tubematic repository. The workflows use the newest
Tubematic release, found when they run (`.github/tubematic-release.sh`), so nothing here changes
when Tubematic releases.

## Claude review

Add the `claude-review` label to a pull request to have Claude read the submission against
[REVIEW-CHECKLIST.md](REVIEW-CHECKLIST.md) (`.github/workflows/claude-review.yml`). It posts one
comment with a verdict per checklist item (PASS, FLAG or HUMAN) and removes the label; add the label
again to review a newer push. The review advises: the maintainer still reads the flags and decides,
and a submission written to mislead a reviewer can mislead Claude too.

Only someone with triage access can add a label, so a stranger's pull request never starts a review
on its own. The pull request's files are checked out only in a job with no secrets. Claude can read
the workspace and write its review but run no command, and a review that quotes a credential is
withheld.

Setup, once:

1. Run `claude setup-token` and add the token as the repository secret `CLAUDE_CODE_OAUTH_TOKEN`
   (Settings → Secrets and variables → Actions). Reviews count against that Claude subscription.
2. Create the label `claude-review` (Issues → Labels).
