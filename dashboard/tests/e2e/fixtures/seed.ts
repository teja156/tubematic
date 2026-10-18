import { readFileSync } from "fs";
import path from "path";

// Exported so a spec that needs a raw request still targets the isolated
// test API. A hand-written "http://localhost:4000" in a spec silently aims
// at the production stack: it fails when that stack is down, and passes
// against the wrong database when it is up.
export const BASE = "http://localhost:4001";

// The test stack's fixed tokens and dashboard password (TMDEV-152). Public on
// purpose: the stack runs on throwaway volumes, see tests/e2e/secrets/.
export const API_TOKEN = readFileSync(path.join(__dirname, "../secrets/api_token"), "utf8").trim();
export const API_AUTH = { Authorization: `Bearer ${API_TOKEN}` };
export const TEST_PASSWORD = "e2e test password";

// Every call below goes straight to the test API, which refuses one without
// the token. Shadowing fetch here keeps each helper unchanged.
function fetch(url: string, init: RequestInit = {}): Promise<Response> {
  return globalThis.fetch(url, {
    ...init,
    headers: { ...API_AUTH, ...((init.headers as Record<string, string>) ?? {}) },
  });
}

export interface VideoFields {
  topic: string;
  strategy?: string;
  producibility_score?: number;
  status?: string;
  script?: string;
  video_path?: string;
  project_id?: string;
  [key: string]: unknown;
}

export interface SeededVideo {
  id: string;
  topic: string;
  status: string;
  script: string | null;
  video_path: string | null;
  producibility_score: number;
  strategy: string;
  [key: string]: unknown;
}

export async function createVideo(fields: VideoFields): Promise<SeededVideo> {
  const res = await fetch(`${BASE}/videos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      producibility_score: 5,
      strategy: "curriculum",
      ...fields,
    }),
  });
  if (!res.ok) {
    throw new Error(`createVideo failed ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function patchVideo(
  id: string,
  fields: Partial<VideoFields>
): Promise<SeededVideo> {
  // The API refuses a script without its publish pair. Specs seeding a script
  // are about the script, so they get a placeholder pair unless they name one.
  const body = "script" in fields
    ? { publish_title: "Seeded title", publish_description: "Seeded description.", ...fields }
    : fields;
  const res = await fetch(`${BASE}/videos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`patchVideo failed ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function getVideo(id: string): Promise<SeededVideo> {
  const res = await fetch(`${BASE}/videos/${id}`);
  if (!res.ok) throw new Error(`getVideo failed ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Report one finished poller session, as scripts/poll.py does (TMDEV-129).
 *  A start_status equal to the video's current status is a no-progress session. */
export async function reportAgentOutcome(
  id: string, start_status: string,
): Promise<{ status: string; count: number; stuck: boolean }> {
  const res = await fetch(`${BASE}/videos/${id}/agent-outcome`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_status }),
  });
  if (!res.ok) throw new Error(`reportAgentOutcome failed ${res.status}: ${await res.text()}`);
  return res.json();
}

/** Delete a video's files and archive its row (TMDEV-84). */
export async function deleteVideo(id: string): Promise<unknown> {
  const res = await fetch(`${BASE}/videos/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deleteVideo failed ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function addComment(
  id: string,
  fields: { author: string; content: string }
): Promise<unknown> {
  const res = await fetch(`${BASE}/videos/${id}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!res.ok) {
    throw new Error(`addComment failed ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export interface ProjectFields {
  name: string;
  id?: string;
  description?: string;
  is_curriculum_seed?: boolean;
  status?: string;
  default_voice_id?: string;
  topic_cap?: number;
}

export async function createProject(fields: ProjectFields): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_curriculum_seed: false, status: "active", ...fields }),
  });
  if (!res.ok) {
    throw new Error(`createProject failed ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function setProjectStatus(id: string, status: "active" | "paused"): Promise<void> {
  const res = await fetch(`${BASE}/projects/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) {
    throw new Error(`setProjectStatus failed ${res.status}: ${await res.text()}`);
  }
}

export async function setStrategies(strategies: string[]): Promise<void> {
  const res = await fetch(`${BASE}/research/strategies`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategies }),
  });
  if (!res.ok) {
    throw new Error(`setStrategies failed ${res.status}: ${await res.text()}`);
  }
}

export async function setMiningSources(youtube_urls: string[]): Promise<void> {
  const res = await fetch(`${BASE}/research/mining-sources`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ youtube_urls }),
  });
  if (!res.ok) {
    throw new Error(`setMiningSources failed ${res.status}: ${await res.text()}`);
  }
}

export async function getSettings(): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/settings`);
  if (!res.ok) throw new Error(`getSettings failed ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function setSettings(partial: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(partial),
  });
  if (!res.ok) throw new Error(`setSettings failed ${res.status}: ${await res.text()}`);
}

// Unlike the helpers above, callers need the status code itself (e.g. to
// assert a 400 on a voice_id absent from the roster) — no throw-on-!ok here.
export async function previewVoice(
  voiceId: string, body?: Record<string, unknown>,
): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await fetch(`${BASE}/voices/${voiceId}/preview`, {
    method: "POST",
    ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
  });
  return { status: res.status, body: await res.json() };
}
