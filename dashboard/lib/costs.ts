// Formatting shared by every cost surface (TMDEV-107): the video modal, the
// Analytics Spend tab and Settings → Costs.

/** The one disclaimer, worded once so the surfaces cannot drift apart. */
export const COST_DISCLAIMER =
  "Estimated at each provider's API list prices — does not reflect subscriptions, " +
  "plan credits or discounts. ElevenLabs is shown in plan credits, never dollars.";

export function formatUsd(usd: number): string {
  if (!usd) return "$0.00";
  if (usd > 0 && usd < 0.01) return "<$0.01";
  return `$${usd.toFixed(2)}`;
}

export function formatCredits(n: number): string {
  return `${n.toLocaleString("en-US")} credit${n === 1 ? "" : "s"}`;
}

const SERVICE_LABELS: Record<string, string> = {
  elevenlabs: "ElevenLabs",
  gemini: "Gemini",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

export function serviceLabel(service: string): string {
  return SERVICE_LABELS[service] ?? service;
}

const OPERATION_LABELS: Record<string, string> = {
  voice: "voice",
  voice_preview: "preview",
  ai_review: "review",
  mining: "mining",
  publish_metadata: "publish metadata",
  image: "image",
  character: "character",
};

export function operationLabel(operation: string): string {
  return OPERATION_LABELS[operation] ?? operation;
}

/** The stage an agent session is recorded under: the video's status when it started.
 *  Exact since the poller runs one stage per session (TMDEV-129): a session that
 *  starts at VOICING stops at VOICE_READY. Before that it carried straight on into
 *  scene writing — seen live, a $7.85 "voicing" session was almost entirely scene
 *  work — so migration 0007 relabelled every VOICING session recorded until then
 *  as VOICING_WITH_SCENES. */
const STAGE_LABELS: Record<string, string> = {
  TOPIC_APPROVED: "Script writing",
  VOICING: "Voicing",
  VOICING_WITH_SCENES: "Voicing & scene writing",
  VOICE_READY: "Scene writing",
  REVISION_REQUESTED: "Revision",
};

export function stageLabel(stage: string | null): string {
  if (!stage) return "Agent session";
  return STAGE_LABELS[stage] ?? stage;
}

/** USD per token → USD per million tokens, the unit every pricing page quotes. */
export function perMillion(usdPerToken: number): number {
  return usdPerToken * 1_000_000;
}
