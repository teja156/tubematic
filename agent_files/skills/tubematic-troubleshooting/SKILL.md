---
name: tubematic-troubleshooting
description: Diagnose a broken or misbehaving Tubematic install with the human, collect redacted evidence, and draft a GitHub bug report for them to file. Interactive only, and only when the human asks for it by name.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Tubematic Troubleshooting

**Invoke this skill when:** the human asks for it by name, to work out why their Tubematic install
is misbehaving and, if it is a bug, to draft an issue report. It is never part of a scheduled
pipeline run. If you were started by the poller, stop and do nothing.

You are helping a person at their keyboard. Work with them step by step: say what you are about
to look at, and why, before you look.

---

## Hard rules — these override everything below

1. **Never read a raw log or the data directory.** Do not open anything under `~/.tubematic-data/`
   (the database holds every API key; `secrets/` holds the service tokens), any `.env` file, the
   poller's logs under `~/.tubematic-agent/logs/` or its session output, and do not run
   `docker logs` or `docker compose logs`. None of those are redacted — `poll.log` quotes agent
   output verbatim — and whatever you read is sent to your model provider. Do not query the
   database, and do not call the API's `/logs` route (it needs a token you must not read). Logs
   reach you only through the diagnostics report, which is redacted before you see it.
2. **Never print, copy or repeat a credential**, even partly, even if one turns up in output.
   If you see something that looks like a key, token, cookie or password, say "this line contains
   what looks like a credential" and leave it out.
3. **Never post anything anywhere.** You draft the issue. The human files it, using the command
   or link the diagnostics report gives them. Do not run `gh`, open a browser to submit, or send
   the text to any service.
4. **Never change the pipeline while diagnosing.** No status changes, approvals, retries,
   re-renders, re-voices, settings writes, restarts or anything that spends money — unless the
   human has asked for that specific action after you explained what it does.

---

## 1. Ask what they see

Start by asking the human to describe the problem in their own words: what they did, what they
expected, what happened instead, and when it started. Ask for an exact error message if there is
one. Do not start collecting evidence before you know which symptom you are chasing.

Then match it to one section of the troubleshooting guide, `docs/user-guide/08-troubleshooting.md`
in the Tubematic install directory. Read that section and follow its checks before improvising
your own — it holds the known causes and fixes, and this skill does not repeat them.

| What they describe | Guide section |
|---|---|
| Nothing moves, a video is stuck, cron does nothing | Nothing is happening |
| The agent says it has no Tubematic tools, or MCP answers 401 | The agent has no Tubematic tools |
| The agent follows old instructions after an upgrade | The agent has stale skills |
| A render fails, times out or loops | Renders |
| The AI review keeps sending a video back | AI review |
| Wrong pronunciation, voice errors, ElevenLabs refusals | Voice |
| The dashboard will not load, or login fails | Dashboard |
| Posts fail, scheduling or Auto Pilot misbehaves | Publishing |
| Discord messages missing | Notifications |
| Disk full, missing files, an empty database after an upgrade | Data and disk |

An upgrade that refused or failed part-way is covered by `docs/user-guide/07-upgrading.md`
instead, in the same directory.

The install directory is the one the human ran `onboard.py` from. If they are unsure, the cron
entry names it: the line containing `scripts/poll.py` in `crontab -l`.

---

## 2. Gather evidence, cheapest first

Stop as soon as you understand the problem. Each step is optional once the cause is clear.

1. **MCP tools.** `get_pipeline_status` for the overall picture; `get_video` for a specific
   video — its comments and AI review feedback usually say what went wrong. `list_videos` to find
   a video the human can only describe.
2. **Health commands**, if you can run shell commands, from the install directory:
   - `python3 scripts/service.py status` — version, schema, cron entry and containers
   - `python3 onboard.py --status` — the install checklist

   If you cannot run commands, ask the human to run them and paste the output.
3. **The diagnostics report** — as soon as you need any log, including the poller's:

   ```
   python3 scripts/collect_diagnostics.py --video <video id if there is one>
   ```

   Add `--since <hours>` if the problem is older than a day. Do **not** add `--include-content`
   unless the human asks for it; it puts their topics and comments into the report. If you cannot
   run commands, ask the human to run it and tell you the path it prints. Then read the
   `report.md` it wrote. It holds a redacted tail of the poller's log, the structured logs and
   every container's output — the only log material you may read or use in the issue.

   If it exits with "Redaction check failed", nothing was written. Tell the human, do not try to
   work around it, and leave log excerpts out of the issue.

---

## 3. Diagnose with the human

Explain what the evidence shows in plain language, and what you think the cause is. If the guide
has a fix, walk the human through it and let them run it. If it turns out to be a configuration
problem with a known fix, it is not a bug — there is nothing to report.

Draft an issue only when the human agrees it looks like a bug in Tubematic itself.

---

## 4. Redaction gate — read the report before using any of it

The collector removes what code can recognise. You are the second check. Read every line of
`report.md` you intend to quote, and look for:

- keys, tokens, passwords, webhook URLs, OAuth codes — anything long and random-looking
- cookies or session values
- email addresses, IP addresses, host names, user names, home-directory paths
- social media handles, channel names, account ids
- the human's topics, scripts, comments or preferences, especially reworded ones
- names of people, companies or products that are not Tubematic's own

Do not silently edit something out. List each doubtful line for the human, say why, and let them
decide. Quote as little as proves the point — the lines around the failure, not whole sections.

---

## 5. Draft the issue

Use exactly these headings, in this order, so the report matches the repository's bug-report form:

```markdown
### Summary
<one or two sentences>

### What I expected

### What happened instead

### Steps to reproduce
1.

### Version and install
- Tubematic version:
- Install type: release tarball / source checkout
- OS:
- Agent: <CLI name and version, model>

### Containers
<the Stack table from the report>

### Relevant logs
<short excerpts from report.md only, with their UTC timestamps>

### What I already tried

### Redaction
<the report's "Redaction summary" line, plus anything the human removed by hand>
```

Show the human the complete draft and ask them to read it. Change anything they ask. When they
are happy, save it as `issue.md` in the same directory as `report.md`. If you cannot write files,
give it to them as one block to copy.

---

## 6. Hand over

Give the human the "Filing" section of `report.md`: the new-issue link and the `gh issue create`
command, which already point at the right repository. Remind them the issue is public. Then stop —
filing is theirs to do.
