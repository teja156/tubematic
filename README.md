<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="logos/lockup-horizontal/tubematic-horizontal-on-dark-2x.png">
    <img alt="Tubematic" src="logos/lockup-horizontal/tubematic-horizontal-on-light-2x.png" width="360">
  </picture>
</p>

Tubematic is a self-hosted pipeline that turns a topic into a finished YouTube Short. It researches
topics, writes a script, voices it, generates imagery, animates it in code, renders an mp4, has an AI
watch the result for defects, and waits at three points for a human to approve before money is spent
or a video goes out (unless you hand those approvals to Auto Pilot).

It is not a template filler. Every scene is a React component that an AI agent (Claude Code, Codex or
OpenCode) writes for that specific video, rendered by [Remotion](https://remotion.dev), so you can read
exactly what produced any frame. You run it from a web dashboard on your own Linux machine with
Docker.

## Walkthrough

<p align="center">
  <a href="https://youtu.be/-y9zBSg8WEc">
    <img alt="Watch the Tubematic walkthrough" src="https://img.youtube.com/vi/-y9zBSg8WEc/maxresdefault.jpg" width="640">
  </a>
</p>

## Documentation

**[docs.tubematic.ai](https://docs.tubematic.ai)** has the quickstart, the user guide (installing,
the dashboard, settings, publishing, upgrading) and the developer docs (how it works and how to
change it), for each release.

## Licence

Tubematic is licensed under the [Apache License 2.0](LICENSE).

**Remotion is licensed separately.** Tubematic renders with [Remotion](https://remotion.dev), which it
installs as a dependency rather than including. Remotion's licence is not Apache-2.0: it is free for
individuals, non-profits and for-profit companies with up to three employees, and a larger for-profit
company needs a paid Remotion company licence to run Tubematic. Tubematic's licence does not cover
Remotion. Read
[Remotion's licence terms](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md) before you
use it in a company.

## History

This repository starts at its first commit. Development before 2.0.0 happened in a private repository
whose history is not public. Every 1.x release was internal beta testing, so 2.0.0 is Tubematic's
first public release.
