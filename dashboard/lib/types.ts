export type VideoStatus =
  | "TOPIC_PROPOSED"
  | "TOPIC_APPROVED"
  | "TOPIC_REJECTED"
  | "SCRIPT_READY"
  | "VOICING"
  | "VOICE_READY"
  | "RENDER_QUEUED"
  | "RENDERING"
  | "VIDEO_READY"
  | "VIDEO_APPROVED"
  | "REVISION_REQUESTED"
  | "SCHEDULED"
  | "PUBLISHING"
  | "PUBLISHED"
  | "FAILED";

export type Strategy = "curriculum" | "trending" | "mining" | "manual";
export type ProjectStatus = "active" | "paused";
/** Which visual register a video is produced in. "auto" means the agent picks
 *  one, video-wide, at scene-config time and records it in
 *  resolved_visual_style. Keep in sync: mcp/server.py and
 *  renderer/api/pipeline.py's VISUAL_STYLES. */
export type VisualStyle = "auto" | "motion_graphics" | "stick" | "illustrated";
export type CommentAuthor = "human" | "agent";
export type ScriptProfileStatus = "PENDING" | "GENERATING" | "READY" | "FAILED";

export interface ScriptSegment {
  id: string;
  voice: string;
  visual: string;
}

export interface Voice {
  name: string;
  voice_id: string;
  /** The ElevenLabs model this voice speaks with (TMDEV-121). There is no
   *  install-wide model: the model, and so the markup a script may use,
   *  follows the voice. */
  model_id: string;
}

export interface VoiceInfo {
  /** The video's own voice, else the install default; kept when it has left
   *  the roster, so a removed voice still shows as its id. */
  voice_id: string;
  /** The roster name, or "" when the voice is no longer on the roster. */
  name: string;
  /** The model the latest voicing call used (model_voiced true), else the
   *  voice's current roster model — before voicing, or for a video voiced
   *  before usage was recorded. "" when neither is known. */
  model_id: string;
  model_voiced: boolean;
}

export interface Comment {
  id: number;
  video_id: string;
  author: CommentAuthor;
  content: string;
  created_at: string;
}

export interface Video {
  id: string;
  project_id: string | null;
  title: string | null;
  topic: string;
  strategy: Strategy;
  producibility_score: number;
  status: VideoStatus;
  script: string | null;
  script_segments?: ScriptSegment[] | null;
  /** Exact text sent to ElevenLabs (respell/lexicon applied); '' until voiced.
   *  Optional so existing object literals stay valid — nothing renders it yet. */
  tts_text?: string;
  /** Which installed agent runs this video, assigned at creation; null means
   *  the default agent. Optional for the same reason as tts_text above. */
  agent_id?: string | null;
  /** Per-video model for that agent; '' uses the agent's own default
   *  (models[0]). The API rejects a value outside the agent's model list.
   *  Optional for the same reason as tts_text above. */
  agent_model?: string;
  /** Per-video effort level for that agent; '' uses the agent's own effort.
   *  One of AGENT_EFFORTS (lib/agents.ts). Frozen after TOPIC_PROPOSED like
   *  agent_model. Optional for the same reason as tts_text above. */
  agent_effort?: string;
  /** Which script profile the script is written in; '' means the script-writing
   *  skill's own generic style. Optional for the same reason as tts_text. */
  script_profile_id?: string;
  /** The register chosen at the topic checkpoint, frozen after it. "auto"
   *  defers the choice to the agent. Optional for the same reason as tts_text:
   *  older object literals stay valid. */
  visual_style?: VisualStyle;
  /** What "auto" settled on, written once by the agent at scene-config time.
   *  '' until it has. Meaningless unless visual_style is "auto". */
  resolved_visual_style?: string;
  /** Scheduled agent sessions in a row that left this video at the status
   *  they found it at (TMDEV-129). Reset by any progress. Optional for the
   *  same reason as tts_text above. */
  agent_no_progress_count?: number;
  /** When the poller stopped dispatching this video after too many sessions
   *  without progress; null while it is not stuck. A human status change or
   *  Retry agent clears it. */
  agent_stuck_at?: string | null;
  voice_file_path: string | null;
  timeline_path: string | null;
  scene_config_path: string | null;
  video_path: string | null;
  /** When the video's files were deleted (manually or by retention) and the
   *  row archived; null/absent while live. GET /videos omits archived rows
   *  unless asked with ?archived=only. An archived row keeps its status. */
  archived_at?: string | null;
  /** When a scheduled post goes out, UTC ISO; '' when not scheduled. Only
   *  meaningful while status is SCHEDULED (TMDEV-133). */
  scheduled_at?: string;
  /** The IANA zone the schedule was picked in, for showing it back in that
   *  zone rather than the host's. */
  scheduled_timezone?: string;
  video_version: number;
  gemini_feedback: string | null;
  /** True when `gemini_feedback` above is only a preview. List endpoints clip
   *  it (the stored review is uncapped and every row ships in a list payload);
   *  `GET /videos/<id>` always returns it whole and sets this false. */
  gemini_feedback_truncated?: boolean;
  /** @deprecated Retired as a read path by TMDEV-83 — a video can be live on
   *  several platforms at once and one TEXT column cannot hold four URLs. The
   *  column and its writers are deliberately left in place (dropping it is a
   *  one-way ALTER, and removing update_video's kwarg would change an MCP
   *  signature). Read video_publications instead. */
  youtube_url: string | null;
  voice_id: string;
  /** The voice this video will be voiced with — its own voice_id, else the
   *  install default — or '' when neither is in the roster. */
  effective_voice_id?: string;
  /** Roster voices whose model cannot speak this video's script, keyed by
   *  voice_id, with the reason. Computed by the API with the same check that
   *  refuses such a voice with a 409, so a picker that disables these can
   *  never disagree with the server. Empty for an unscripted video. */
  voice_conflicts?: Record<string, string>;
  /** The voice and model for the modal's read-only rows (TMDEV-147). Only on
   *  single-video responses (GET/PATCH /videos/<id>), never in a list. */
  voice_info?: VoiceInfo;
  created_at: string;
  updated_at: string;
  comments?: Comment[];
}

export interface Project {
  id: string;
  name: string;
  description: string;
  is_curriculum_seed: number; // SQLite integer: 0 or 1
  status: ProjectStatus;
  created_at: string;
  /** Register this domain's CURRICULUM videos start in; '' means the domain
   *  has no preference. Deliberately not the same as "auto": auto is a
   *  per-video instruction to the agent, this is the absence of a
   *  domain-level one. Videos filed here by trending/mining/manual ignore it. */
  default_visual_style?: VisualStyle | "";
  /** The voice every new video filed into this domain starts with, whatever
   *  its sourcing mode; '' means the install default. Changing it never
   *  touches videos already filed. */
  default_voice_id?: string;
  /** The script profile this domain's CURRICULUM videos start with, like
   *  default_visual_style; '' means none. Changing it never touches videos
   *  already filed. */
  default_script_profile_id?: string;
  /** How many topics the domain may ever hold, 25–750 (100 by default). */
  topic_cap?: number;
  /** Every video ever filed into the domain, archived and rejected included —
   *  unlike the board's counts. Derived by the API, never stored. */
  topic_count?: number;
  /** topic_count has reached topic_cap: research files nothing more here
   *  (manual submissions still go through). Derived, never stored. */
  expired?: boolean;
}

export interface ScriptProfile {
  id: string;
  name: string;
  status: ScriptProfileStatus;
  source_urls: string[];
  error: string;
  attempt_count: number;
  /** Deleted-but-still-referenced. The list endpoint omits archived rows, so
   *  this is only ever true on a by-id fetch. */
  archived: boolean;
  created_at: string;
  updated_at: string;
  /** Only returned by GET /script-profiles/<id>; the list payload omits both,
   *  since the markdown is a whole style guide per row. */
  markdown?: string;
  corpus_summary?: string;
}

export type Stats = Partial<Record<VideoStatus, number>>;

export interface Settings {
  pipeline_paused: boolean;
  gemini_review_enabled: boolean;
  /** Render crash/timeout retry cap. Since VQA-7 this covers renders only —
   *  the AI review loop has its own ai_review_max_loops. */
  max_render_retries: number;
  ai_review_model: string;
  ai_review_fps: number;
  ai_review_max_loops: number;
  max_curriculum_per_run: number;
  max_trending_per_run: number;
  max_mining_per_run: number;
  research_pending_cap: number;
  max_research_runs_per_day: number;
  trending_sources: string[];
  elevenlabs_voices: Voice[];
  elevenlabs_voice_id: string;
  /** Scene images. OpenAI is the only image provider. */
  image_model: string;
  /** The Illustrated style's transparent cut-outs, from the same OpenAI
   *  image catalog as image_model. */
  character_model: string;
  render_timeout_secs: number;
  /** Burn the "Made with tubematic.ai" mark into every render. Human-only:
   *  nothing in scene-config.json can switch it. */
  watermark_enabled: boolean;
  /** Pipeline sessions the cron supervisor runs at once (TMDEV-129); research
   *  and script profiles run beside them, outside this cap. 1..10. */
  max_concurrent_agent_sessions: number;
  /** How long one agent session may run before its process group is killed.
   *  Stored in seconds like render_timeout_secs, shown in minutes. */
  agent_session_timeout_secs: number;
  log_retention_days: number;
  /** Days after publishing before a PUBLISHED video's files are deleted and
   *  its row archived. 0 disables the sweep. */
  retention_days: number;
  /** Days after a FAILED or TOPIC_REJECTED video last changed before its files
   *  are deleted and its row archived (TMDEV-134). 0, the default, is off. */
  unpublished_retention_days: number;
  /** API keys (TMDEV-73). The server stores these raw and returns only a mask
   *  ("••••••••4f2a"), or "" when nothing is stored — a real key never reaches
   *  the browser. POSTing the mask back unchanged is a no-op, so the page can
   *  round-trip these fields safely; POSTing "" clears the key. */
  elevenlabs_api_key: string;
  gemini_api_key: string;
  openai_api_key: string;
  youtube_transcript_api_key: string;
  postforme_api_key: string;
  /** Publishing to social platforms via postforme.dev (TMDEV-83). Off means
   *  VIDEO_APPROVED reads as terminal and every publishing affordance is
   *  hidden — a UI filter only; PUBLISHING/PUBLISHED stay in VideoStatus. */
  publishing_enabled: boolean;
  /** Discord notifications (TMDEV-5). The webhook URL is a credential — anyone
   *  holding it can post to that channel — so the server masks it exactly like
   *  the API keys above, and the same round-trip rules apply. Off in two
   *  independent ways: no URL, and no trigger enabled. */
  discord_webhook_url: string;
  notify_topic_proposed: boolean;
  notify_script_ready: boolean;
  notify_video_ready: boolean;
  /** Where the dashboard is reachable from wherever Discord is read, e.g.
   *  "http://192.168.1.20:3000". Blank means notifications carry no links —
   *  the container cannot know what hostname a human reaches it by. */
  dashboard_base_url: string;
  /** The operator's standing preferences for every video, as free text
   *  (TMDEV-117). Handed to the agent on every run, which applies only the
   *  parts that fit the stage it is in. "" means none. */
  user_preferences: string;
  /** Auto Pilot (TMDEV-139). Edited on its own tab through /autopilot, never
   *  through the settings form: the project list saves with it as one document. */
  auto_pilot_enabled: boolean;
  /** Minimum minutes between two posts on one account under Auto Pilot. */
  auto_pilot_gap_mins: number;
  /** Most videos in progress before Auto Pilot stops starting new ones; 0 means no limit. */
  auto_pilot_max_in_flight: number;
}

/** One (video, account) publish target (TMDEV-83). Replaces videos.youtube_url
 *  as the read path: one TEXT column cannot hold four platform URLs. */
export interface VideoPublication {
  id: string;
  video_id: string;
  platform: string;
  social_account_id: string;
  /** PENDING until postforme reports a result for this target, then PUBLISHED
   *  or FAILED. A video is PUBLISHED if ANY of its targets succeeded. */
  status: "PENDING" | "PUBLISHED" | "FAILED";
  post_url: string;
  error: string;
  published_at: string;
  created_at: string;
  updated_at: string;
}

/** One metrics snapshot for one publication. A time series, not latest-only —
 *  history cannot be backfilled. Nulls mean "not reported", never zero. */
export interface VideoMetric {
  id: number;
  publication_id: string;
  fetched_at: string;
  views: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
}

/** A postforme account as the dashboard sees it — an allowlisted projection.
 *  postforme's own payload carries the channel's live OAuth tokens; the API
 *  strips them before this crosses the proxy. */
export interface SocialAccount {
  id: string;
  platform: string;
  username: string;
  profile_photo_url: string;
  status: string;
  /** Whether Tubematic may post to it. The stored list is an allowlist, not a
   *  mirror of what is connected to postforme. */
  allowed: boolean;
  /** False when it is allowlisted but no longer connected upstream. */
  available: boolean;
  /** False when postforme *rejects* a read of this account's feed. `feeds` is
   *  granted separately from posting at connect time, so an account can publish
   *  fine and yield no metrics at all — but true here does NOT prove analytics
   *  work: Instagram answers such a read with 200 and empty metrics rather than
   *  rejecting, so a feeds-less account reads as true. See pipeline.py
   *  `_feeds_available`. null = not checked (only allowlisted accounts are
   *  probed). */
  analytics?: boolean | null;
}

export interface PipelineStatus {
  paused: boolean;
  workable_count: number;
  proposed_count: number;
  video_counts: Stats;
  last_research_at: string | null;
  active_strategies: Strategy[];
  research_pending_cap: number;
  research_runs_today: number;
  max_research_runs_per_day: number;
  research_window_resets_at: string | null;
  pending_script_profiles: number;
  timezone: string | null;
  timezone_label: string;
  /** The installed Tubematic version, e.g. "1.0.1". Optional: an API predating
   * TMDEV-100 does not send it, and the top bar renders nothing in that case
   * rather than guessing. */
  version?: string;
}

export interface PatchVideoBody {
  status?: VideoStatus;
  title?: string;
  script?: string;
  video_version?: number;
  youtube_url?: string;
  gemini_feedback?: string;
  voice_id?: string;
  script_profile_id?: string;
  agent_model?: string;
  agent_effort?: string;
  visual_style?: VisualStyle;
  onlyIfCurrentStatus?: VideoStatus;
}

/** An installed agent CLI (e.g. Claude Code), from GET /agents. Rows are
 *  written only by the host-side installer, which validates `models` against
 *  the real binary — so the dashboard can pick the default agent, the weight,
 *  which listed model is the default and the effort level, but never add or
 *  remove models. `models[0]` is this agent's default model. */
export interface Agent {
  id: string;
  name: string;
  binary: string;
  run_path: string;
  install_scope: string;
  models: string[];
  /** This agent's default effort level, one of AGENT_EFFORTS (lib/agents.ts).
   *  Unlike `models`, editable here: the levels are fixed by the CLI rather
   *  than discovered per install, so there is nothing to validate against. */
  effort: string;
  is_default: boolean;
  /** Relative share of new videos assigned to this agent. */
  weight: number;
  verified_at: string;
  /** Set once the agent is uninstalled on the host; such rows are still
   *  listed and read-only. */
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

/** One structured log record from GET /logs (TMDEV-86).
 *
 * `ts` is UTC (written with a trailing Z) — the whole app stores UTC and
 * formats in the host's zone at display time. The context fields are optional
 * because a record only carries the ones its writer had. */
export interface LogRecord {
  ts: string;
  service: string;
  level: string;
  message: string;
  video_id?: string;
  profile_id?: string;
  request_id?: string;
  [key: string]: unknown;
}

export interface LogsResponse {
  records: LogRecord[];
  count: number;
  limit: number;
  /** Echoed by the API so the filter lists are not a second copy of the
   * server's allowlist that could drift from it. */
  services: string[];
  levels: string[];
}

// ── Costs (TMDEV-107) — GET /videos/<id>/costs, /usage/summary, /prices ──────
// Every dollar figure is an API list price; ElevenLabs is plan credits.

export interface CostLine {
  service: string;
  model: string;
  operation: string;
  calls: number;
  /** null when none of the calls were priced. */
  cost_usd: number | null;
  credits: number;
  unpriced_calls: number;
  estimated: boolean;
}

export interface AgentSessionCost {
  session_id: string;
  created_at: string;
  /** The video's status when the session started — what it was working on. */
  stage: string | null;
  operation: string;
  batch_size: number;
  models: string[];
  total_usd: number;
  share_usd: number;
  unpriced: boolean;
  estimated: boolean;
}

export interface VideoCosts {
  has_usage: boolean;
  lines: CostLine[];
  agent: {
    models: string[];
    share_usd: number;
    session_total_usd: number;
    shared: boolean;
    estimated: boolean;
    sessions: AgentSessionCost[];
  } | null;
  total_usd: number;
  credits: number;
  unpriced_calls: number;
}

export interface SpendSummary {
  since: string;
  /** Exclusive end of the window; null when open-ended. */
  until: string | null;
  /** Echoed only for a from/to request: the inclusive days and the zone they were cut in. */
  from?: string;
  to?: string;
  timezone?: string;
  total_usd: number;
  videos: number;
  research: number;
  agent_other: number;
  other: number;
  video_count: number;
  unpriced_calls: number;
  voice_credits: number;
  preview_credits: number;
  estimated: boolean;
  elevenlabs_pool: { tier: string | null; used: number; limit: number;
                     resets_at_unix: number | null } | null;
}

export interface ModelPrice {
  service: string;
  model: string;
  /** "manual" | "openrouter" | "litellm" | "built-in", or null when unpriced. */
  source: string | null;
  /** USD per token (per credit never — ElevenLabs is not priced). */
  rates: Record<string, number>;
  tiered: boolean;
  effective_from: string | null;
}

export interface PriceTable {
  models: ModelPrice[];
  unpriced: { service: string; model: string; calls: number }[];
  unit_kinds: string[];
  last_sync_attempt_at: string | null;
  last_sync_ok_at: string | null;
  last_sync_error: string | null;
}

/** GET /retention/backlog (TMDEV-134): the non-archived FAILED and
 *  TOPIC_REJECTED videos unpublished_retention_days would sweep, and the disk
 *  their mp4s and job dirs hold. Answered whether or not the key is on. */
export interface RetentionBacklog {
  failed: { count: number; bytes: number };
  rejected: { count: number; bytes: number };
}
