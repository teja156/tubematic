"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SocialAccount } from "@/lib/types";
import { addDays, wallClock } from "@/lib/datetime";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

// Privacy is per platform because the platforms differ: YouTube has three
// states, TikTok two, Instagram and Facebook none at all. One shared control
// would have to offer "unlisted" where it cannot exist, or silently map it onto
// something else. First entry is the default and matches what postforme
// documents for both fields.
// Keep in sync: renderer/api/postforme.py PRIVACY_OPTIONS.
const PRIVACY_OPTIONS: Record<string, string[]> = {
  youtube: ["public", "unlisted", "private"],
  tiktok: ["public", "private"],
};

const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  tiktok: "TikTok",
  facebook: "Facebook",
};

// The zone the schedule defaults to is the browser's, not the host's: the
// person picking "9:00" means nine o'clock where they are sitting. The API
// converts the wall time; nothing here computes UTC (TMDEV-133).
function browserZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

// Every IANA zone the browser knows. UTC is added by hand because some engines
// list only "Etc/UTC", and the browser's own zone in case it is a legacy alias
// (Asia/Calcutta) that the canonical list leaves out.
function zoneOptions(own: string): string[] {
  const list = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return Array.from(new Set([...list, "UTC", own])).sort();
}

const SCHEDULE_PRESETS: Array<{ label: string; pick: (tz: string) => { date: string; time: string } }> = [
  { label: "In 1 hour", pick: (tz) => wallClock(tz, new Date(Date.now() + 3_600_000)) },
  { label: "Tomorrow 9:00", pick: (tz) => ({ date: addDays(wallClock(tz, new Date()).date, 1), time: "09:00" }) },
  { label: "Tomorrow 18:00", pick: (tz) => ({ date: addDays(wallClock(tz, new Date()).date, 1), time: "18:00" }) },
];

interface PublishDialogProps {
  open: boolean;
  videoId: string;
  videoTitle: string;
  onClose: () => void;
  onPublished: () => void;
}

export function PublishDialog({
  open, videoId, videoTitle, onClose, onPublished,
}: PublishDialogProps) {
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState("");
  const [privacy, setPrivacy] = useState<Record<string, string>>({});
  // null = unknown (no timeline). Only a definite false warrants a warning —
  // claiming either answer from a missing duration would be worse than silence.
  const [isShort, setIsShort] = useState<boolean | null>(null);
  const [durationSecs, setDurationSecs] = useState<number | null>(null);
  const ownZone = useMemo(browserZone, []);
  const zones = useMemo(() => zoneOptions(ownZone), [ownZone]);
  const [mode, setMode] = useState<"now" | "schedule">("now");
  const [zone, setZone] = useState(ownZone);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const scheduling = mode === "schedule";

  useEffect(() => {
    if (!open) return;
    // Cleared synchronously, before the awaits below. Otherwise reopening the
    // dialog on a different video leaves the previous video's targets, title
    // and description on screen until the fetches land — and publishing is
    // irreversible, so a click in that window posts the wrong metadata to the
    // wrong accounts. `loading` also disables the confirm button for the same
    // window; both are needed, since clearing alone would still show an
    // enabled button over a half-built form.
    setSelected([]);
    setTitle("");
    setDescription("");
    setAccounts([]);
    setPrivacy({});
    setIsShort(null);
    setDurationSecs(null);
    // Publish now is the default every time — a schedule left over from the
    // last video would otherwise hold this one back without anyone asking.
    setMode("now");
    setZone(ownZone);
    setDate("");
    setTime("");
    setLoading(true);
    setError("");
    Promise.all([
      apiFetch("/publishing/accounts").then(async (r) => ({ ok: r.ok, body: await r.json() })),
      // Always answers 200 — the title and description the agent wrote with
      // the script, or the video's own title and topic if it wrote none.
      apiFetch(`/videos/${videoId}/publish-prefill`, { method: "POST" })
        .then(async (r) => ({ ok: r.ok, body: await r.json() }))
        .catch(() => ({ ok: false, body: null })),
    ])
      .then(([accountsRes, prefill]) => {
        if (!accountsRes.ok) {
          setError(accountsRes.body?.error ?? "Could not load accounts.");
        } else {
          const list: SocialAccount[] = Array.isArray(accountsRes.body) ? accountsRes.body : [];
          const usable = list.filter((a) => a.allowed && a.available);
          setAccounts(usable);
          // Nothing is pre-ticked: publishing is irreversible, so every target
          // is an explicit choice rather than something to remember to untick.
          setSelected([]);
        }
        setTitle(prefill.body?.title ?? videoTitle);
        setDescription(prefill.body?.description ?? "");
        setIsShort(prefill.body?.youtube_short ?? null);
        setDurationSecs(prefill.body?.duration_secs ?? null);
      })
      .catch(() => setError("Could not reach the pipeline API."))
      .finally(() => setLoading(false));
  }, [open, videoId, videoTitle, ownZone]);

  async function publish() {
    setPublishing(true);
    setError("");
    try {
      const r = await apiFetch(`/videos/${videoId}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_ids: selected, title, description, privacy,
          ...(scheduling ? { schedule: { local: `${date}T${time}`, timezone: zone } } : {}),
        }),
      });
      const body = await r.json().catch(() => null);
      if (!r.ok) {
        setError(body?.error ?? "Publishing failed.");
        return;
      }
      onPublished();
      onClose();
    } finally {
      setPublishing(false);
    }
  }

  const groups = accounts.reduce<Record<string, SocialAccount[]>>((acc, a) => {
    (acc[a.platform || "unknown"] ??= []).push(a);
    return acc;
  }, {});

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      {/* Width comes from an inline style, not a class, and that is load-bearing:
          DialogContent's own base classes end with `sm:max-w-sm` (384px). twMerge
          cannot collapse that against an unprefixed max-w-* — different variant
          scopes, so both survive — and the media-query rule then wins on any
          desktop screen. A class-based width is silently clamped to 384px, which
          is what made the title and description fields overflow. VideoModal sizes
          itself the same way for the same reason.

          Deliberately smaller than VideoModal (95vw / 1280): this opens on top of
          it, and a child dialog that fills its parent reads as a page change
          rather than a step within one. */}
      <DialogContent
        data-testid="publish-dialog"
        className="border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff] p-0"
        style={{ width: "90vw", maxWidth: 880, maxHeight: "80vh" }}
      >
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-[#1e1e30]">
          <DialogTitle className="text-sm font-semibold text-[#f0f0ff]">Publish</DialogTitle>
          <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-[#555572]">
            {videoTitle}
          </p>
        </DialogHeader>

        <div className="px-6 py-4 overflow-y-auto">
          {error && (
            <p data-testid="publish-error" className="mb-4 font-mono text-[11px] text-amber-400">
              {error}
            </p>
          )}

          {loading ? (
            <p className="font-mono text-[11px] text-[#555572]">Loading…</p>
          ) : (
            /* Targets beside metadata. min-w-0 on both: a grid child defaults to
               min-width:auto and will not shrink below its content, which is the
               other way inputs escape a dialog. */
            <div className="grid gap-6 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
              <div className="min-w-0">
                <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[#555572]">
                  Publish to
                </p>
                {accounts.length === 0 ? (
                  <p data-testid="publish-no-accounts" className="font-mono text-[11px] text-[#9a9ab8]">
                    No accounts enabled — pick some on the Socials page first.
                  </p>
                ) : (
                  Object.entries(groups).map(([platform, list]) => (
                    <div key={platform} className="mb-4">
                      <p className="mb-1 font-mono text-[10px] text-[#555572]">
                        {PLATFORM_LABEL[platform] ?? platform}
                      </p>
                      {list.map((a) => (
                        <label
                          key={a.id}
                          className="flex items-center gap-2 py-1 font-mono text-[12px] text-[#f0f0ff]"
                        >
                          <input
                            type="checkbox"
                            data-testid={`publish-target-${a.id}`}
                            checked={selected.includes(a.id)}
                            onChange={(e) =>
                              setSelected((prev) =>
                                e.target.checked
                                  ? [...prev, a.id]
                                  : prev.filter((id) => id !== a.id),
                              )
                            }
                          />
                          @{a.username || a.id}
                        </label>
                      ))}
                      {platform === "youtube" && isShort === false && (
                        /* YouTube decides Shorts from the file — vertical AND
                           <= 3 minutes — and there is no flag to send. Aspect
                           always qualifies here, so length is the only thing
                           that decides it, and nothing enforces the script
                           budget that keeps videos under it. */
                        <p
                          data-testid="publish-not-a-short"
                          className="mt-1 font-mono text-[10px] text-amber-400"
                        >
                          {durationSecs
                            ? `${Math.floor(durationSecs / 60)}:${String(
                                Math.round(durationSecs % 60)).padStart(2, "0")} — `
                            : ""}
                          over 3 min, posts as a regular video, not a Short
                        </p>
                      )}
                      {PRIVACY_OPTIONS[platform] ? (
                        <select
                          data-testid={`publish-privacy-${platform}`}
                          value={privacy[platform] ?? PRIVACY_OPTIONS[platform][0]}
                          onChange={(e) =>
                            setPrivacy((prev) => ({ ...prev, [platform]: e.target.value }))
                          }
                          className="mt-1 w-full rounded border border-[#2a2a42] bg-[#131325]
                                     px-2 py-1 font-mono text-[11px] text-[#f0f0ff]"
                        >
                          {PRIVACY_OPTIONS[platform].map((o) => (
                            <option key={o} value={o}>{o}</option>
                          ))}
                        </select>
                      ) : (
                        /* Not an omission — these platforms have no privacy
                           field at all, so saying nothing would leave the user
                           wondering why the control disappeared. */
                        <p
                          data-testid={`publish-no-privacy-${platform}`}
                          className="mt-1 font-mono text-[10px] text-[#555572]"
                        >
                          always public
                        </p>
                      )}
                    </div>
                  ))
                )}

                <div className="mt-2 border-t border-[#1e1e30] pt-4">
                  <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-[#555572]">
                    When
                  </p>
                  <label className="flex items-center gap-2 py-1 font-mono text-[12px] text-[#f0f0ff]">
                    <input
                      type="radio"
                      name="publish-when"
                      data-testid="publish-when-now"
                      checked={!scheduling}
                      onChange={() => setMode("now")}
                    />
                    Publish now
                  </label>
                  <label className="flex items-center gap-2 py-1 font-mono text-[12px] text-[#f0f0ff]">
                    <input
                      type="radio"
                      name="publish-when"
                      data-testid="publish-when-schedule"
                      checked={scheduling}
                      onChange={() => setMode("schedule")}
                    />
                    Schedule
                  </label>
                  {scheduling && (
                    <div className="mt-2 flex flex-col gap-2">
                      <select
                        data-testid="publish-timezone"
                        value={zone}
                        onChange={(e) => setZone(e.target.value)}
                        className="w-full rounded border border-[#2a2a42] bg-[#131325]
                                   px-2 py-1 font-mono text-[11px] text-[#f0f0ff]"
                      >
                        {zones.map((z) => (
                          <option key={z} value={z}>{z === ownZone ? `${z} (yours)` : z}</option>
                        ))}
                      </select>
                      <div className="flex gap-2">
                        <input
                          type="date"
                          data-testid="publish-date"
                          value={date}
                          min={wallClock(zone, new Date()).date}
                          onChange={(e) => setDate(e.target.value)}
                          className="min-w-0 flex-1 rounded border border-[#2a2a42] bg-[#131325]
                                     px-2 py-1 font-mono text-[11px] text-[#f0f0ff] [color-scheme:dark]"
                        />
                        <input
                          type="time"
                          data-testid="publish-time"
                          value={time}
                          onChange={(e) => setTime(e.target.value)}
                          className="w-[92px] rounded border border-[#2a2a42] bg-[#131325]
                                     px-2 py-1 font-mono text-[11px] text-[#f0f0ff] [color-scheme:dark]"
                        />
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {SCHEDULE_PRESETS.map((p, i) => (
                          <button
                            key={p.label}
                            type="button"
                            data-testid={`publish-preset-${i}`}
                            onClick={() => {
                              const picked = p.pick(zone);
                              setDate(picked.date);
                              setTime(picked.time);
                            }}
                            className="rounded border border-[#2a2a42] px-2 py-0.5 font-mono
                                       text-[10px] text-[#9a9ab8] hover:text-[#f0f0ff]"
                          >
                            {p.label}
                          </button>
                        ))}
                      </div>
                      <p className="font-mono text-[10px] text-[#555572]">
                        The video uploads now; postforme holds the post and sends it at this
                        time. It can be cancelled until then.
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div className="min-w-0">
              <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-[#555572]">
                Title
              </label>
              <input
                data-testid="publish-title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="mb-4 w-full rounded-md border border-[#2a2a42] bg-[#131325] px-3 py-2
                           text-sm text-[#f0f0ff] focus:outline-none focus:ring-1
                           focus:ring-cyan-500/40"
              />

              <label className="mb-1 block font-mono text-[10px] uppercase tracking-widest text-[#555572]">
                Description
              </label>
              <textarea
                data-testid="publish-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="h-40 w-full resize-none rounded-md border border-[#2a2a42] bg-[#131325]
                           px-3 py-2 text-sm text-[#f0f0ff] focus:outline-none focus:ring-1
                           focus:ring-cyan-500/40"
              />
              <p className="mt-2 font-mono text-[10px] text-[#555572]">
                YouTube gets the title and description separately. Instagram, TikTok and Facebook
                have no title field, so they get both as one caption.
              </p>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="px-6 pb-5">
          <button
            onClick={onClose}
            className="rounded px-4 py-2 text-sm text-[#9a9ab8] transition-colors hover:text-[#f0f0ff]"
          >
            Cancel
          </button>
          <button
            data-testid="publish-confirm"
            onClick={publish}
            disabled={loading || publishing || selected.length === 0 || !title.trim()
                      || (scheduling && (!date || !time))}
            className="rounded bg-cyan-500/15 px-4 py-2 text-sm text-cyan-300 transition-colors
                       hover:bg-cyan-500/25 disabled:opacity-40"
          >
            {publishing
              ? (scheduling ? "Scheduling…" : "Publishing…")
              : scheduling ? `Schedule for ${selected.length}` : `Publish to ${selected.length}`}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
