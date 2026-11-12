"use client";

/**
 * The visual style picker (TMDEV-226), used wherever a style is chosen: a
 * domain's defaults, New Video, the video window at Topic Proposed and Quick
 * Actions. A native <select> cannot show a preview, so this is a button that
 * opens a list: Auto, then the 2D and 3D styles, then the insert styles (shown
 * for reference, never a video's style). Each row carries its tags (experimental,
 * GPU) and an eye button that opens the style's preview loop in a window, where
 * Prev/Next step through every style and "Use this style" picks the one shown.
 *
 * The groups and tags come from the style packs through GET /visual-styles
 * (lib/visualStyles.ts::styleGroups); nothing here names a style.
 *
 * Keyboard: the list opens on the button's Enter, Space or ArrowDown with the
 * chosen row focused; ArrowUp/ArrowDown/Home/End move, typing jumps to a name,
 * Enter or Space picks, ArrowRight opens the focused row's preview, Escape closes.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent } from "react";
import { Popover } from "@base-ui/react/popover";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import type { GpuStatus, VisualStyleInfo } from "@/lib/types";
import { previewableRows, previewUrls, styleGroups, type StyleGroup, type StyleRow } from "@/lib/visualStyles";

const TAG_BASE: CSSProperties = {
  fontFamily: "var(--mono)", fontSize: 9, letterSpacing: "0.08em", padding: "1px 5px",
  borderRadius: 3, border: "1px solid var(--border-2)", color: "var(--dim)", whiteSpace: "nowrap",
  lineHeight: "14px", flex: "none",
};

export function StyleTags({ row, testId }: { row: Pick<StyleRow, "experimental" | "gpu">; testId?: string }) {
  return (
    <>
      {row.experimental && (
        <span data-testid={testId ? `${testId}-exp` : undefined}
              style={{ ...TAG_BASE, color: "var(--purple)", borderColor: "rgba(183,148,246,0.4)" }}>EXP</span>
      )}
      {row.gpu && (
        <span data-testid={testId ? `${testId}-gpu` : undefined} title="Renders on a GPU only"
              style={{ ...TAG_BASE, color: "var(--cyan)", borderColor: "rgba(79,209,199,0.45)" }}>GPU</span>
      )}
    </>
  );
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
      <path d="M1 8s2.6-5 7-5 7 5 7 5-2.6 5-7 5-7-5-7-5Z" />
      <circle cx="8" cy="8" r="2.2" />
    </svg>
  );
}

const BTN: CSSProperties = {
  fontFamily: "var(--mono)", fontSize: 11, letterSpacing: "0.06em", padding: "7px 14px", textTransform: "uppercase",
  color: "var(--ink-2)", border: "1px solid var(--border-2)", background: "transparent", cursor: "pointer",
};
const BTN_PRIMARY: CSSProperties = {
  ...BTN, color: "var(--green)", borderColor: "var(--green)", background: "rgba(101,210,122,0.08)",
};

const EYE_STYLE: CSSProperties = {
  flex: "none", width: 26, height: 26, display: "grid", placeItems: "center", borderRadius: 4,
  border: "1px solid var(--border-2)", background: "transparent", color: "var(--ink-2)", cursor: "pointer",
};

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The preview window: the loop (muted, looping; with controls and no autoplay
 * when the viewer asks for reduced motion), the style's group and tags, its
 * tagline, Prev/Next over `rows`, and "Use this style" when `onUse` is given
 * and the shown style can be picked.
 */
export function StylePreviewDialog({ rows, index, onIndex, onClose, onUse }: {
  rows: StyleRow[];
  index: number | null;
  onIndex: (i: number) => void;
  onClose: () => void;
  onUse?: (value: string) => void;
}) {
  const row = index === null ? null : rows[index] ?? null;
  const reduced = prefersReducedMotion();
  const step = (d: number) => index !== null && rows.length > 0 && onIndex((index + d + rows.length) % rows.length);
  return (
    <Dialog open={row !== null} onOpenChange={(v) => !v && onClose()}>
      {row && (
        <DialogContent
          data-testid="style-preview"
          className="grid-cols-1 border-[#1e1e30] bg-[var(--panel)] text-[var(--ink)]"
          style={{ width: "auto", maxWidth: "calc(100vw - 32px)", zIndex: 300 }}
          onKeyDown={(e) => {
            // The player's own controls (shown with reduced motion) seek with the arrows.
            if (e.target instanceof HTMLMediaElement) return;
            if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
            if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
          }}
        >
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "flex-start" }}>
            {row.preview ? (
              <video
                key={row.preview}
                data-testid="style-preview-video"
                src={previewUrls(row.preview).video}
                poster={previewUrls(row.preview).poster}
                autoPlay={!reduced}
                controls={reduced}
                muted
                loop
                playsInline
                style={{ width: "min(300px, 70vw)", aspectRatio: "9 / 16", background: "#000", borderRadius: 4,
                         display: "block", objectFit: "cover" }}
              />
            ) : null}
            <div style={{ display: "grid", gap: 10, width: 220, maxWidth: "100%", alignContent: "start" }}>
              <DialogTitle className="text-base font-semibold" data-testid="style-preview-title">{row.label}</DialogTitle>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <span style={TAG_BASE}>{row.insert ? "INSERT" : (row.dimension ?? "2d").toUpperCase()}</span>
                <StyleTags row={row} testId="style-preview-tag" />
              </div>
              {row.tagline && <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: "var(--ink-2)" }}>{row.tagline}</p>}
              {row.insert && (
                <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--dim)" }}>
                  Used for a few seconds inside another style, never for a whole video.
                </p>
              )}
              {row.why && (
                <p data-testid="style-preview-why" style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--dim)" }}>
                  Not available on this install: {row.why}.
                </p>
              )}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 4 }}>
                <button type="button" className="tm-btn" style={BTN} data-testid="style-preview-prev" onClick={() => step(-1)}
                        aria-label="Previous style">‹ Prev</button>
                <button type="button" className="tm-btn" style={BTN} data-testid="style-preview-next" onClick={() => step(1)}
                        aria-label="Next style">Next ›</button>
              </div>
              {onUse && row.choosable && (
                <button type="button" className="tm-btn" style={BTN_PRIMARY} data-testid="style-preview-use"
                        onClick={() => onUse(row.value)}>
                  Use this style
                </button>
              )}
            </div>
          </div>
        </DialogContent>
      )}
    </Dialog>
  );
}

/** The eye button beside a style that is no longer chosen here (the video
 *  window after the topic is approved): opens the same preview window, without
 *  "Use this style". Renders nothing for a style with no preview. */
export function StylePreviewButton({ styleId, styles, testId }: {
  styleId: string;
  styles: VisualStyleInfo[] | null;
  testId?: string;
}) {
  const rows = useMemo(() => previewableRows(styleGroups(styles, true, null)), [styles]);
  const [index, setIndex] = useState<number | null>(null);
  const at = rows.findIndex((r) => r.value === styleId);
  if (at < 0) return null;
  const label = rows[at].label;
  return (
    <>
      <button type="button" data-testid={testId} aria-label={`Preview ${label}`} title={`Preview ${label}`}
              style={EYE_STYLE} onClick={() => setIndex(at)}>
        <EyeIcon />
      </button>
      <StylePreviewDialog rows={rows} index={index} onIndex={setIndex} onClose={() => setIndex(null)} />
    </>
  );
}

export interface StylePickerProps {
  /** On the button; rows get `${testId}-option-<value>`, eye buttons `${testId}-preview-<value>`. */
  testId: string;
  styles: VisualStyleInfo[] | null;
  canUseOpenAI: boolean;
  gpu?: Pick<GpuStatus, "status"> | null;
  value: string;
  onChange: (value: string) => void;
  /** Adds a first row with value "" (a domain may have no default style). */
  noneLabel?: string;
  title?: string;
  buttonStyle?: CSSProperties;
  /** The list is at least this wide, so a narrow button still shows full names. */
  listMinWidth?: number;
}

export function StylePicker({
  testId, styles, canUseOpenAI, gpu, value, onChange, noneLabel, title, buttonStyle, listMinWidth = 300,
}: StylePickerProps) {
  const [open, setOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const typed = useRef({ text: "", at: 0 });

  const groups: StyleGroup[] = useMemo(() => {
    const g = styleGroups(styles, canUseOpenAI, gpu, value);
    if (noneLabel === undefined) return g;
    const none: StyleRow = { value: "", label: noneLabel, experimental: false, gpu: false, why: "",
      choosable: true, preview: null, dimension: null, tagline: "", insert: false };
    if (g.length && g[0].key === "top") return [{ ...g[0], rows: [none, ...g[0].rows] }, ...g.slice(1)];
    return [{ key: "top", title: "", note: "", rows: [none] }, ...g];
  }, [styles, canUseOpenAI, gpu, value, noneLabel]);
  const allRows = groups.flatMap((g) => g.rows);
  const previews = previewableRows(groups);
  const chosen = allRows.find((r) => r.value === value) ?? null;

  // Focus the chosen row (or the first) once the list is in the page.
  useEffect(() => {
    if (!open) return;
    const t = window.setTimeout(() => {
      const list = listRef.current;
      if (!list) return;
      const target = list.querySelector<HTMLElement>('[role="option"][aria-selected="true"]')
        ?? list.querySelector<HTMLElement>('[role="option"]');
      target?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open]);

  const pick = (row: StyleRow) => {
    if (!row.choosable) return;
    setOpen(false);
    if (row.value !== value) onChange(row.value);
  };
  const openPreview = (row: StyleRow) => {
    const i = previews.findIndex((r) => r.value === row.value);
    if (i < 0) return;
    setOpen(false);
    setPreviewIndex(i);
  };

  const onListKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const options = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? []);
    const at = options.indexOf(document.activeElement as HTMLElement);
    const focus = (i: number) => options[Math.max(0, Math.min(options.length - 1, i))]?.focus();
    const rowAt = (i: number) => allRows.find((r) => r.value === options[i]?.dataset.value);
    if (e.key === "ArrowDown") { e.preventDefault(); focus(at + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); focus(at - 1); }
    else if (e.key === "Home") { e.preventDefault(); focus(0); }
    else if (e.key === "End") { e.preventDefault(); focus(options.length - 1); }
    else if ((e.key === "Enter" || e.key === " ") && at >= 0) {
      e.preventDefault();
      const row = rowAt(at);
      if (row) pick(row);
    } else if (e.key === "ArrowRight" && at >= 0) {
      e.preventDefault();
      const row = rowAt(at);
      if (row) openPreview(row);
    } else if (e.key.length === 1 && /\S/.test(e.key) && !e.metaKey && !e.ctrlKey && !e.altKey) {
      const now = Date.now();
      typed.current = { text: (now - typed.current.at < 700 ? typed.current.text : "") + e.key.toLowerCase(), at: now };
      const q = typed.current.text;
      const order = [...options.slice(at + 1), ...options.slice(0, at + 1)];
      const hit = order.find((o) => (allRows.find((r) => r.value === o.dataset.value)?.label ?? "").toLowerCase().startsWith(q))
        ?? options.find((o) => (allRows.find((r) => r.value === o.dataset.value)?.label ?? "").toLowerCase().startsWith(q));
      hit?.focus();
    }
  };

  const buttonLabel = chosen?.label ?? (value || noneLabel || "");
  return (
    <>
      <Popover.Root open={open} onOpenChange={setOpen}>
        <Popover.Trigger
          data-testid={testId}
          aria-haspopup="listbox"
          title={title}
          data-value={value}
          onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); } }}
          style={{
            display: "flex", alignItems: "center", gap: 6, textAlign: "left", cursor: "pointer",
            fontFamily: "inherit", fontSize: 13, padding: "6px 8px", borderRadius: 4,
            background: "var(--panel)", color: "var(--ink)", border: "1px solid var(--border-2)",
            minWidth: 0, ...buttonStyle,
          }}
        >
          <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {buttonLabel}
          </span>
          {chosen && <StyleTags row={chosen} />}
          <span aria-hidden style={{ color: "var(--dim)", fontSize: 9 }}>▼</span>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner side="bottom" align="start" sideOffset={4} style={{ zIndex: 250 }}>
            <Popover.Popup
              style={{
                minWidth: listMinWidth, maxWidth: "calc(100vw - 32px)", maxHeight: "min(520px, calc(100vh - 120px))",
                overflowY: "auto", background: "var(--panel-2)", border: "1px solid var(--border-2)", borderRadius: 6,
                padding: 6, boxShadow: "0 12px 32px rgba(0,0,0,0.55)", outline: "none",
              }}
            >
              <div ref={listRef} role="listbox" aria-label="Visual style" data-testid={`${testId}-list`}
                   onKeyDown={onListKey} style={{ display: "grid", gap: 2 }}>
                {groups.map((g) => (
                  <div key={g.key} role="group" aria-label={g.title || "Auto"} data-testid={`${testId}-group-${g.key}`}
                       style={{ display: "grid", gap: 2 }}>
                    {g.title && (
                      <div style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase",
                                    color: "var(--mute)", padding: "10px 8px 4px", display: "flex", gap: 8, alignItems: "baseline" }}>
                        {g.title}
                        {g.note && <span style={{ textTransform: "none", letterSpacing: 0, fontFamily: "inherit", fontSize: 10 }}>{g.note}</span>}
                      </div>
                    )}
                    {g.rows.map((r) => {
                      const selected = r.value === value;
                      return (
                        <div
                          key={r.value || "_none"}
                          role="option"
                          tabIndex={-1}
                          aria-selected={selected}
                          aria-disabled={!r.choosable}
                          data-value={r.value}
                          data-testid={`${testId}-option-${r.value || "none"}`}
                          onClick={() => pick(r)}
                          style={{
                            display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 4,
                            cursor: r.choosable ? "pointer" : "default", fontSize: 13, outlineOffset: -1,
                            background: selected ? "var(--amber-soft)" : "transparent",
                            border: `1px solid ${selected ? "rgba(245,166,35,0.35)" : "transparent"}`,
                          }}
                        >
                          <span style={{ flex: 1, minWidth: 0, color: r.choosable ? "var(--ink)" : "var(--mute)" }}>
                            {r.label}
                            {r.why && <span style={{ display: "block", fontSize: 11, color: "var(--mute)" }}>{r.why}</span>}
                          </span>
                          <StyleTags row={r} />
                          {r.preview && (
                            <button
                              type="button"
                              tabIndex={-1}
                              data-testid={`${testId}-preview-${r.value}`}
                              aria-label={`Preview ${r.label}`}
                              title={`Preview ${r.label} (→)`}
                              style={EYE_STYLE}
                              onClick={(e) => { e.stopPropagation(); openPreview(r); }}
                            >
                              <EyeIcon />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
      <StylePreviewDialog
        rows={previews}
        index={previewIndex}
        onIndex={setPreviewIndex}
        onClose={() => setPreviewIndex(null)}
        onUse={(v) => { setPreviewIndex(null); if (v !== value) onChange(v); }}
      />
    </>
  );
}
