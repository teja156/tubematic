---
name: tubematic-topic-research
description: Research and propose new video topics using the curriculum, trending, or mining strategies
---

# Tubematic Topic Research Skill

**Invoke this skill when:** researching and proposing new video topics during a scheduled research run.

Tool signatures are in the MCP docstrings. This skill covers the workflow and scoring policy.

---

## Research Workflow

> **Note:** Per-run topic caps and trending sources are configured during onboarding or on the Settings dashboard; they arrive embedded in the research prompt.

**Before researching**, call `list_projects()` once to get the current project list. If the prompt
carries no USER PREFERENCES block (an interactive session), read `user_preferences` from
`get_pipeline_status()` once. Either way, apply only the parts about topics — subjects to favour or
avoid, audience, angle — when choosing and scoring candidates.

For each active strategy:
1. Research topic candidates using that strategy's method (below)
2. Score every candidate with the producibility rubric — drop anything below 5
3. For each surviving candidate, file it into the right domain (**universal filing rule**):
   - Match to an existing project by subject/domain
   - **If the best-matching project is paused** (`status='paused'`) **or expired**
     (`expired` is true in `list_projects()`), **skip the candidate.**
     Do not file it into a loosely related domain instead, and do not create a new domain
     for it. A pause means "no videos on this subject right now", not "not in this row of
     the database"; an expired domain already holds as many topics as its `topic_cap`
     allows. `create_video` refuses a paused or expired project anyway; treat that refusal
     the same way, as a skip, never as a reason to retry somewhere else. Name each skipped
     candidate in your run summary.
   - **Deduplicate against that project** (see the Deduplication Rule) — drop the candidate
     if its core mechanism is > 70% similar to a topic already there
   - Only if **no** project matches the subject at all, paused, expired or not, call
     `upsert_project` to create one — a new project has no topics to deduplicate against
   - Call `create_video` with the topic, a short title, strategy name, producibility score,
     and project_id. **Both text fields, every time:** `topic` is the full descriptive
     brief you researched — the thing the producibility score is about — and `title` is a
     short headline for it, at most 70 characters, which is what dashboard cards show.
     Write the title as a real headline, not the first 70 characters of the topic.
   - Call `add_comment` with the hook angle and score rationale

After all strategies are done: call `mark_research_done` to record when research last completed
(for display only — scheduling is governed by `poll.py`'s two run caps, not this timestamp).

---

## Producibility Scoring

Score ≥ 5 required to propose. Sum the signals below and clamp to 0–10. A topic scores on
whichever track fits; scoring on both simply means the topic is rich on both tracks, and says
nothing about how its scenes should be built — that is decided per-beat downstream.

**DIAGRAM track — the pipeline draws it in SVG**

| Signal | Points |
|---|---|
| Step-by-step process with discrete stages | +2 |
| Before/after comparison (state A vs state B) | +2 |
| Countable elements (≤ 12, e.g. "Python allocates 8 slots") | +2 |
| Flow diagram or state machine exists for this topic | +2 |
| Terminal / scriptable output (output known at script time) | +1 |

**PHOTO track — the pipeline generates images of it**

| Signal | Points |
|---|---|
| The topic is about a named character, real person, creature or animal | +2 |
| A specific real place, structure, or physical object with a distinctive look | +2 |
| One specific dramatic or historical moment (a battle, an ambush, a launch, a signing) | +2 |

**Penalties**

| Signal | Points |
|---|---|
| Requires genuinely live, unpredictable output (real network latency, random results) | −3 |
| Scores zero on **both** tracks — nothing to see and nothing to track | −3 |
| Requires real archival footage or a real screen recording that cannot be generated as a still | −2 |

**Examples:**
- "Storming of the Dragonpit" → named characters +2, real structure +2, one specific moment +2, step-by-step +2 = **8** ✓
- "Python list over-allocation" → step +2, before/after +2, countable +2 = **6** ✓
- "TCP three-way handshake" → step +2, countable +2, flow +2 = **6** ✓
- "Best Python libraries 2026" → no track scores, both-tracks-zero −3 = **0** ✗

A candidate that scores on the PHOTO track will classify PHOTO downstream in
`tubematic-scene-config`'s subject test (or, where a beat turns on *where* or *in what order*,
HYBRID) — write its hook angle and `visual` briefs photographically (name the subject, the moment,
the framing), not as an abstract diagram.

---

## Strategy: Curriculum

Enumerate sub-topics from **user-seeded domains only** — these are projects where `is_curriculum_seed=1` and `status='active'`. Do not pick arbitrary broad topics.

1. From `list_projects()`, filter to `is_curriculum_seed=1 AND status='active'` and `expired` false
2. For each seed domain: generate sub-topics that each explain ONE mechanism in 60–90 seconds (respect the per-run target given in the research prompt; if no target is given, default to 3–5 new candidates; not exhaustive)
3. Score, deduplicate against the seed domain's own topics (`list_project_topics`), and propose survivors

Good sub-topics: specific mechanisms (GIL, reference counting, list over-allocation). Not vague overviews ("Python performance").

**If no seed domains exist:** skip curriculum strategy and note this — the user needs to add domains with `/tubematic-add-topic`.

---

## Strategy: Trending

Find what's hot in tech right now and extract producible angles.

1. Scan the trending sources listed in the research prompt (configured on the Settings dashboard or during onboarding). Use your web-fetch and web-search tools to retrieve each source — these are public pages requiring no authentication or captcha solving. Supported sources: **GitHub Trending**, **Hacker News** (Show HN + technical posts), **Lobsters**, **Dev.to**. If no sources are listed in the prompt, fall back to GitHub Trending + Hacker News.
2. For each item: ask "What is the ONE mechanism here I can show visually in 60 seconds?"
3. Score, deduplicate, and propose survivors using the universal filing rule

Good angle: new open-source tool → "How does X's core algorithm work?" Not: "X released version 3".

---

## Strategy: Mining

Spin off topics that were mentioned briefly in YouTube videos. Gemini processes
the videos natively — no local transcript files are involved.

**Requires:** a Gemini API key configured on the Settings dashboard. While none is
stored, mining is left out of your active strategies altogether — do not mine.
If `mine_youtube_topics` still returns an error about the key, skip mining, report
it in your research summary, and continue with other strategies.

1. Call `get_mining_sources()` to retrieve the configured YouTube URLs.
   If the list is empty, skip mining and note it in your summary.
2. Choose the most relevant project domain (`project_id`). Call `list_projects()` if unsure.
3. Call `mine_youtube_topics(project_id=..., youtube_urls=[...])` **once**.
   It files at most this run's mining cap itself: it asks Gemini only for what is
   left under the cap, shows it the topics that already exist, and skips any
   candidate that still repeats one or scores below 5. Each run starts from a
   different URL, and asks at most as many URLs as topics it may file, so a run
   can end with URLs untried — the next run carries on from there.
   Pass the list exactly as `get_mining_sources()` returned it. The tool refuses
   the whole call, with no Gemini call made, if any URL is not a YouTube video
   URL, and refuses a call made while another mining run is in progress.
4. **Do not file extra mining topics with `create_video`, and do not reject what the
   tool filed.** If it filed fewer than the cap, that is this run's result.
5. If the tool returns an `error` key, report it and skip mining gracefully. Do not
   retry it in the same run.
6. Report: how many topics were proposed, and what came back in `not_filed` and why.

**Example:** a video on Python internals briefly mentions "reference counting" →
spin-off: "How Python's reference counting actually works" (score: 6).

---

## Deduplication Rule

**Never set a topic to `TOPIC_REJECTED`.** Rejecting a topic is the human's decision at the
topic checkpoint, and the MCP server refuses it. A candidate that duplicates an existing topic, or
would go over a per-run cap, is simply never filed — don't file it and then reject it.

Before calling `create_video`, call `list_project_topics(project_id)` for the project you are
filing into (once per project per run is enough — add what you file yourself as you go) and check
for overlap. Use it, not `list_videos`: `list_videos` never shows an archived video, so a topic
that was made and deleted, or swept by retention, would come back. `list_project_topics` lists
every topic ever filed there, archived and rejected ones included — a topic the human turned down
counts as covered too.

Compare against each existing `topic` — the brief — not its `title`, which is only a short display
name and can omit the very mechanism you are checking for. If an existing `topic` covers the same
core mechanism (even with different wording), skip the candidate and note it was deduplicated.
