import { execSync } from "child_process";
import path from "path";
import { test, expect } from "@playwright/test";
import { createVideo, patchVideo, addComment, getVideo, reportAgentOutcome, setSettings } from "../fixtures/seed";

test.describe("VideoModal", () => {
  let uid: string;

  test.beforeEach(() => {
    uid = crypto.randomUUID().slice(0, 8);
  });

  test("clicking a Kanban card opens the modal with matching title", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Modal test video` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    // The heading, specifically. The topic now renders twice in the modal --
    // once here (the header falls back to `title || topic`, and a seeded video
    // has no short title) and once in the Topic tab's body -- so a plain
    // getByText is ambiguous and fails Playwright's strict mode.
    await expect(
      modal.getByRole("heading", { name: `[${uid}] Modal test video` }),
    ).toBeVisible();
  });

  test("Script tab hidden when script is empty", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] No script video` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("tab", { name: /Script/ })).not.toBeVisible();
  });

  test("Script tab visible when script has content", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Has script` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Hello world" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("tab", { name: /Script/ })).toBeVisible();
  });

  test("Comments tab always present", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Comments tab test` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("tab", { name: /Comments/ })).toBeVisible();
  });

  test("Comments tab is read-only — no compose box", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Read-only comments` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("tab", { name: /Comments/ }).click();

    await expect(modal.getByTestId("comments-readonly-note")).toBeVisible();
    await expect(modal.locator("textarea")).toHaveCount(0);
    await expect(modal.getByRole("button", { name: "Send" })).toHaveCount(0);
  });

  test("a revision comment appears in the Comments thread", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Revision comment thread` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Script content" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    const commentText = `Revision note [${uid}]`;
    await modal.getByRole("button", { name: "Request Revision" }).click();
    await page.getByPlaceholder("Describe what needs to change...").fill(commentText);
    await page.getByRole("button", { name: "Send Revision Request" }).click();
    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    // Reopen from the Revision Requested column and read the thread.
    const reopened = page.getByTestId("kanban-col-REVISION_REQUESTED").getByTestId(`kanban-card-${video.id}`);
    await expect(reopened).toBeVisible({ timeout: 10_000 });
    await reopened.click();
    await modal.getByRole("tab", { name: /Comments/ }).click();
    await expect(modal.getByText(commentText)).toBeVisible({ timeout: 5_000 });
  });

  test("comment survives modal close and reopen", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Comment persist test` });
    await addComment(video.id, { author: "human", content: `Seeded comment [${uid}]` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("tab", { name: /Comments/ }).click();
    await expect(modal.getByText(`Seeded comment [${uid}]`)).toBeVisible({ timeout: 5_000 });

    // Close modal (press Escape)
    await page.keyboard.press("Escape");
    await expect(modal).not.toBeVisible();

    // Reopen
    await card.click();
    await expect(modal).toBeVisible();
    await modal.getByRole("tab", { name: /Comments/ }).click();
    await expect(modal.getByText(`Seeded comment [${uid}]`)).toBeVisible({ timeout: 5_000 });
  });

  test("Mark as published moves a partial publish to Published (TMDEV-191)", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Partial publish` });
    await patchVideo(video.id, { status: "PARTIALLY_PUBLISHED" });

    await page.goto("/");
    // No column of its own: it sits in Published, tagged PARTIAL.
    const publishedCol = page.getByTestId("kanban-col-PUBLISHED");
    const card = publishedCol.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card.getByTestId(`kanban-card-partial-${video.id}`)).toBeVisible();
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Mark as published…" }).click();

    const dialog = page.getByTestId("mark-published-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByTestId("mark-published-warning")).toContainText("Download the video first");
    await expect(dialog.getByTestId("mark-published-download")).toHaveAttribute("download", `${video.id}.mp4`);
    await dialog.getByRole("button", { name: "Mark as published" }).click();
    await expect(dialog).not.toBeVisible({ timeout: 5_000 });

    await expect.poll(async () => (await getVideo(video.id)).status).toBe("PUBLISHED");
    await expect(modal.getByRole("button", { name: "Mark as published…" })).not.toBeVisible();
  });

  test("Approve Topic in modal triggers status transition and closes modal", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Approve via modal` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Approve Topic" }).click();

    // Modal should close
    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    // Card should appear in TOPIC_APPROVED column after polling
    const approvedCol = page.getByTestId("kanban-col-TOPIC_APPROVED");
    await expect(approvedCol.getByText(`[${uid}] Approve via modal`)).toBeVisible({ timeout: 10_000 });
  });

  test("Revise button opens ReviseDialog for SCRIPT_READY video", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Revise test` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Script content" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Request Revision" }).click();

    // ReviseDialog textarea should appear
    await expect(page.getByPlaceholder("Describe what needs to change...")).toBeVisible();
  });

  test("Submitting a SCRIPT_READY revision actually moves the video to REVISION_REQUESTED", async ({ page }) => {
    // Regression test for a bug found during the TMDEV-1 audit: this dialog used to
    // post the comment but never change status, silently stranding the video at
    // SCRIPT_READY forever.
    const video = await createVideo({ topic: `[${uid}] Revise script for real` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Script content" });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal).toBeVisible();
    await modal.getByRole("button", { name: "Request Revision" }).click();
    await page.getByPlaceholder("Describe what needs to change...").fill("Rewrite the opening line");
    await page.getByRole("button", { name: "Send Revision Request" }).click();

    await expect(modal).not.toBeVisible({ timeout: 5_000 });

    const revisionCol = page.getByTestId("kanban-col-REVISION_REQUESTED");
    await expect(revisionCol.getByText(`[${uid}] Revise script for real`)).toBeVisible({ timeout: 10_000 });
    const scriptReadyCol = page.getByTestId("kanban-col-SCRIPT_READY");
    await expect(scriptReadyCol.getByText(`[${uid}] Revise script for real`)).not.toBeVisible();
  });

  test("a stuck video shows STUCK on its card, and Retry agent hands it back", async ({ page }) => {
    // TMDEV-129: three poller sessions in a row that leave the video where
    // they found it flag it stuck. Driven through the real API route the
    // poller calls, so the dashboard reads the flag exactly as it would live.
    const video = await createVideo({ topic: `[${uid}] Stuck video` });
    await patchVideo(video.id, { status: "VOICE_READY" });
    for (let i = 0; i < 3; i++) await reportAgentOutcome(video.id, "VOICE_READY");

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId(`kanban-card-stuck-${video.id}`)).toBeVisible();
    await card.click();

    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("agent-stuck-banner")).toContainText("3 sessions in a row");
    await modal.getByRole("button", { name: "Retry agent" }).click();
    await expect(modal.getByTestId("agent-stuck-banner")).not.toBeVisible({ timeout: 5_000 });

    const after = await getVideo(video.id);
    expect(after.agent_stuck_at).toBeNull();
    expect(after.agent_no_progress_count).toBe(0);
    expect(after.status).toBe("VOICE_READY");
  });

  test("Details shows the voice and its model once the voice picker is gone", async ({ page }) => {
    // TMDEV-147: the list row the modal opens on carries no voice_info, only
    // the single-video fetch does, so this drives the real API and modal
    // together. Never voiced here, so the model is the voice's current setting.
    await setSettings({
      elevenlabs_voices: [{ name: "Narrator", voice_id: `${uid}-narrator`, model_id: "eleven_multilingual_v2" }],
      elevenlabs_voice_id: `${uid}-narrator`,
    });
    try {
      const video = await createVideo({ topic: `[${uid}] Voice details` });
      await patchVideo(video.id, { status: "VOICE_READY" });

      await page.goto("/");
      const card = page.getByTestId(`kanban-card-${video.id}`);
      await expect(card).toBeVisible({ timeout: 10_000 });
      await card.click();

      const modal = page.getByTestId("video-modal");
      await expect(modal.getByText("Voice model")).toBeVisible({ timeout: 10_000 });
      await expect(modal.getByText("Narrator", { exact: true })).toBeVisible();
      await expect(modal.getByText("eleven_multilingual_v2")).toBeVisible();
      await expect(modal.getByText("(current setting)")).toBeVisible();
    } finally {
      // Other specs assume an empty roster (no voice picker rendered).
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    }
  });

  // A voice per segment (TMDEV-216). Segments are written only by the agent's
  // update_video, and the test stack runs no agent, so they are seeded in the
  // API container. What a unit test cannot show: the real conflicts the API
  // computes, and the segment_voices PATCH landing in the database.
  test("Script tab: a segment's voice is picked from the roster and saved", async ({ page }) => {
    await setSettings({
      elevenlabs_voices: [
        { name: "Narrator", voice_id: `${uid}-n`, model_id: "eleven_v4" },
        { name: "Skeptic", voice_id: `${uid}-s`, model_id: "eleven_multilingual_v2" },
      ],
      elevenlabs_voice_id: `${uid}-n`,
    });
    try {
      const video = await createVideo({ topic: `[${uid}] Segment voices` });
      await patchVideo(video.id, { status: "SCRIPT_READY", script: "So here. Wait, really?" });
      const repoRoot = path.resolve(__dirname, "../../../..");
      execSync(
        `docker compose -f "${path.join(repoRoot, "docker-compose.test.yml")}" exec -T tubematic-api-test python3 -`,
        {
          cwd: repoRoot,
          input: [
            "import json, sqlite3",
            "segs = [{'id': 's1', 'voice': 'So [pause] here.', 'visual': ''},",
            "        {'id': 's2', 'voice': 'Wait, really?', 'visual': ''}]",
            "con = sqlite3.connect('/data/tubematic.db')",
            "con.execute('UPDATE videos SET script_segments = ? WHERE id = ?', "
              + `(json.dumps(segs), '${video.id}'))`,
            "con.commit()",
          ].join("\n"),
          stdio: ["pipe", "inherit", "inherit"],
        },
      );

      await page.goto("/");
      const card = page.getByTestId(`kanban-card-${video.id}`);
      await expect(card).toBeVisible({ timeout: 10_000 });
      await card.click();
      const modal = page.getByTestId("video-modal");

      // [pause] is v3/v4 markup, which the Skeptic's model cannot speak.
      const s1 = modal.getByTestId("segment-voice-s1");
      await expect(s1).toBeVisible({ timeout: 10_000 });
      await expect(s1.locator(`option[value="${uid}-s"]`)).toHaveJSProperty("disabled", true);

      await modal.getByTestId("segment-voice-s2").selectOption(`${uid}-s`);
      await expect.poll(async () => {
        const v = await getVideo(video.id) as unknown as { script_segments: { voice_id?: string }[] };
        return v.script_segments[1].voice_id;
      }).toBe(`${uid}-s`);
      await expect(modal.getByTestId("segment-voice-s2")).toHaveValue(`${uid}-s`);
    } finally {
      await setSettings({ elevenlabs_voices: [], elevenlabs_voice_id: "" });
    }
  });

  // Auto's style pick (TMDEV-203). Only the agent's choose_visual_style writes
  // a pick, and the test stack runs no agent, so the row is seeded in the API
  // container the way stream.spec.ts seeds its files.
  test("Switch to the runner-up sends the video back to scripting in that style", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Switch style` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Hello world" });
    const repoRoot = path.resolve(__dirname, "../../../..");
    execSync(
      `docker compose -f "${path.join(repoRoot, "docker-compose.test.yml")}" exec -T tubematic-api-test python3 -`,
      {
        cwd: repoRoot,
        input: [
          "import sqlite3",
          "con = sqlite3.connect('/data/tubematic.db')",
          "con.execute(\"UPDATE videos SET visual_style = 'system_flow', style_pick = 'system_flow', "
            + "style_runner_up = 'stick', style_reason = 'A request path through a system.' "
            + `WHERE id = '${video.id}'\")`,
          "con.commit()",
        ].join("\n"),
        stdio: ["pipe", "inherit", "inherit"],
      },
    );

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("style-pick-reason")).toContainText("A request path through a system.");
    await expect(modal.getByText("Auto — System Flow")).toBeVisible();

    page.once("dialog", (d) => d.accept());
    await modal.getByRole("button", { name: /^Switch to / }).click();
    await expect.poll(async () => (await getVideo(video.id)).status, { timeout: 10_000 }).toBe("TOPIC_APPROVED");
    const after = await getVideo(video.id) as unknown as Record<string, unknown>;
    expect(after.visual_style).toBe("stick");
    expect(after.style_runner_up).toBe("system_flow");
  });

  // The script formula (TMDEV-213). Only the agent's choose_script_formula
  // writes a pick, so the row is seeded in the API container like the style
  // pick above. What only a real browser against the real API shows: the
  // labels from GET /script-formulas, and each switch landing in the database.
  function seedFormula(videoId: string, sql: string, params: string) {
    const repoRoot = path.resolve(__dirname, "../../../..");
    execSync(
      `docker compose -f "${path.join(repoRoot, "docker-compose.test.yml")}" exec -T tubematic-api-test python3 -`,
      {
        cwd: repoRoot,
        input: [
          "import json, sqlite3",
          "hooks = [{'type': 'problem', 'text': 'You renamed one file.', 'kept': True, 'note': ''},",
          "         {'type': 'question', 'text': 'Why does the log stop?', 'kept': False, 'note': ''},",
          "         {'type': 'myth', 'text': 'A rename is recorded.', 'kept': False, 'note': 'overclaims'}]",
          "con = sqlite3.connect('/data/tubematic.db')",
          `con.execute("UPDATE videos SET ${sql} WHERE id = '${videoId}'", ${params})`,
          "con.commit()",
        ].join("\n"),
        stdio: ["pipe", "inherit", "inherit"],
      },
    );
  }

  test("Switch to the runner-up formula sends the video back to scripting in that formula", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Switch formula` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "# Hello world" });
    seedFormula(video.id,
      "visual_style = 'system_flow', formula_pick = 'follow-the-flow', formula_runner_up = 'scene-story', "
        + "formula_reason = 'A request moves through fixed stages.', formula_id = 'follow-the-flow', "
        // What the watch figures said about the pick; the switch clears it.
        + "formula_evidence = '{\"formula\": \"follow-the-flow\", \"mode\": \"learned\", "
        + "\"standing\": \"better\", \"points\": 2, \"videos\": 24, \"accounts\": 1, \"min_group\": 20}'",
      "()");

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("video-formula")).toHaveText("Auto — Follow the Flow");
    await expect(modal.getByTestId("formula-pick-reason")).toContainText("A request moves through fixed stages.");
    await expect(modal.getByTestId("formula-pick-reason")).toContainText("Runner-up: Scene Story");
    await expect(modal.getByTestId("formula-pick-evidence")).toContainText(
      "Leaned on this install's watch figures: Follow the Flow held more of each video");

    page.once("dialog", (d) => d.accept());
    await modal.getByRole("button", { name: "Switch to Scene Story" }).click();
    await expect.poll(async () => (await getVideo(video.id)).status, { timeout: 10_000 }).toBe("TOPIC_APPROVED");
    const after = await getVideo(video.id) as unknown as Record<string, unknown>;
    expect(after.formula_pick).toBe("scene-story");
    expect(after.formula_runner_up).toBe("follow-the-flow");
    expect(after.formula_choice).toBe("scene-story");
    expect(after.formula_evidence).toBe("");
  });

  test("Use this opening sends the video back to scripting with that opening in use", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Switch opening` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "You renamed one file. It stops." });
    seedFormula(video.id,
      "visual_style = 'system_flow', formula_id = 'broken-expectation', "
        + "formula_pick = 'broken-expectation', hook_type = 'problem', hook_alternatives = ?",
      "(json.dumps(hooks),)");

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("script-hook-0")).toHaveAttribute("data-kept", "true");
    await expect(modal.getByTestId("use-opening-0")).toHaveCount(0);

    page.once("dialog", (d) => d.accept());
    await modal.getByTestId("use-opening-1").click();
    await expect.poll(async () => (await getVideo(video.id)).status, { timeout: 10_000 }).toBe("TOPIC_APPROVED");
    const after = await getVideo(video.id) as unknown as {
      hook_type: string; hook_alternatives: { kept: boolean }[]; formula_pick: string;
      comments: { author: string; content: string }[];
    };
    expect(after.hook_type).toBe("question");
    expect(after.hook_alternatives.map((h) => h.kept)).toEqual([false, true, false]);
    expect(after.formula_pick).toBe("broken-expectation");
    expect(after.comments.at(-1)?.content).toContain("Opening switched to the Question one");
  });

  test("a formula chosen at the topic goes with the approval", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Choose formula` });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    const modal = page.getByTestId("video-modal");
    const select = modal.getByTestId("video-modal-formula-select");
    await expect(select).toHaveValue("");
    // The list is the real one: the core formulas, then the experimental ones marked.
    await expect(select.locator("option", { hasText: "Scene Story" })).toHaveCount(1);
    await expect(select.locator("option", { hasText: "News Take (experimental)" })).toHaveCount(1);
    await select.selectOption("news-take");
    await modal.getByRole("button", { name: "Approve Topic" }).click();
    await expect.poll(async () => (await getVideo(video.id)).status, { timeout: 10_000 }).toBe("TOPIC_APPROVED");
    const after = await getVideo(video.id) as unknown as Record<string, unknown>;
    expect(after.formula_choice).toBe("news-take");
    expect(after.formula_pick).toBe("");    // the agent makes the pick; the test stack has none
  });

  // What the agent records with a script (TMDEV-211). Only update_video
  // writes it, and the test stack runs no agent, so the row is seeded in the
  // API container like the style pick above. The labels come from the real
  // GET /script-formulas, which is the part a unit test cannot show.
  test("Script tab shows the formula, the openings and the warnings recorded with the script", async ({ page }) => {
    const video = await createVideo({ topic: `[${uid}] Script record` });
    await patchVideo(video.id, { status: "SCRIPT_READY", script: "You renamed one file. It stops." });
    const repoRoot = path.resolve(__dirname, "../../../..");
    execSync(
      `docker compose -f "${path.join(repoRoot, "docker-compose.test.yml")}" exec -T tubematic-api-test python3 -`,
      {
        cwd: repoRoot,
        input: [
          "import json, sqlite3",
          "hooks = [{'type': 'problem', 'text': 'You renamed one file.', 'kept': True, 'note': ''},",
          "         {'type': 'question', 'text': 'Why does the log stop?', 'kept': False, 'note': ''},",
          "         {'type': 'myth', 'text': 'A rename is recorded.', 'kept': False, 'note': 'overclaims'}]",
          "warnings = [{'id': 'closing_ask', 'message': 'The last sentence asks the viewer to follow.'}]",
          "con = sqlite3.connect('/data/tubematic.db')",
          "con.execute('UPDATE videos SET formula_id = ?, hook_type = ?, hook_alternatives = ?, '",
          "            'script_warnings = ? WHERE id = ?',",
          "            ('broken-expectation', 'problem', json.dumps(hooks), json.dumps(warnings), "
            + `'${video.id}'))`,
          "con.commit()",
        ].join("\n"),
        stdio: ["pipe", "inherit", "inherit"],
      },
    );

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("script-formula")).toHaveText("Broken Expectation");
    await expect(modal.getByTestId("script-hook-type")).toHaveText("The viewer's problem");
    await expect(modal.getByTestId("script-hook-0")).toHaveAttribute("data-kept", "true");
    await expect(modal.getByTestId("script-hook-2")).toContainText("Not used: overclaims");
    await expect(modal.getByTestId("script-warning-closing_ask"))
      .toContainText("The last sentence asks the viewer to follow.");

    // A script written over HTTP replaces the words, so the record goes with it.
    await patchVideo(video.id, { script: "Other words entirely." });
    const after = await getVideo(video.id) as unknown as Record<string, unknown>;
    expect(after.formula_id).toBe("");
    expect(after.script_warnings).toEqual([]);
  });

  test("Topic tab shows the angle, lets it be edited at Topic Proposed and closes it after approval", async ({ page }) => {
    const video = await createVideo({
      topic: `[${uid}] Topic angle`,
      angle: "Deleting the file frees no space until the last program holding it lets go.",
      angle_kind: "paradox",
      angle_score: 7,
    });

    await page.goto("/");
    const card = page.getByTestId(`kanban-card-${video.id}`);
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.click();
    const modal = page.getByTestId("video-modal");
    await expect(modal.getByTestId("topic-angle-text"))
      .toHaveText("Deleting the file frees no space until the last program holding it lets go.");
    // The label comes from GET /angle-kinds on the real API.
    await expect(modal.getByTestId("topic-angle-kind")).toHaveText("Paradox");
    await expect(modal.getByTestId("topic-angle-score")).toHaveText("7/10");

    await modal.getByTestId("topic-angle-edit").click();
    await modal.getByTestId("topic-angle-input").fill("Most people think a deleted file is gone at once.");
    await modal.getByTestId("topic-angle-kind-select").selectOption("myth");
    await modal.getByTestId("topic-angle-save").click();
    await expect(modal.getByTestId("topic-angle-text"))
      .toHaveText("Most people think a deleted file is gone at once.");
    await expect(modal.getByTestId("topic-angle-kind")).toHaveText("Myth");
    // The agent's score described the sentence it replaced.
    await expect(modal.getByTestId("topic-angle-score")).toHaveText("—");
    const stored = await getVideo(video.id) as unknown as Record<string, unknown>;
    expect(stored.angle).toBe("Most people think a deleted file is gone at once.");
    expect(stored.angle_kind).toBe("myth");
    expect(stored.angle_score).toBe(0);

    // Past the topic the script may already be written from it: read-only,
    // in the window and in the API.
    await patchVideo(video.id, { status: "TOPIC_APPROVED" });
    await page.reload();
    const approved = page.getByTestId(`kanban-card-${video.id}`);
    await expect(approved).toBeVisible({ timeout: 10_000 });
    await approved.click();
    await expect(modal.getByTestId("topic-angle-text"))
      .toHaveText("Most people think a deleted file is gone at once.");
    await expect(modal.getByTestId("topic-angle-edit")).toHaveCount(0);
    await expect(patchVideo(video.id, { angle: "Too late.", angle_kind: "myth" })).rejects.toThrow();
  });
});
