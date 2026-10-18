"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type ToastKind = "success" | "error";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

/** Successes auto-dismiss; errors do not — a failed save is the one thing the
 *  user must not miss, and before this the page discarded non-ok responses
 *  silently and kept rendering stale state. */
const SUCCESS_TTL_MS = 3000;

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = nextId.current++;
    setToasts((t) => [...t, { id, kind, message }]);
    if (kind === "success") {
      timers.current.set(id, setTimeout(() => dismiss(id), SUCCESS_TTL_MS));
    }
    return id;
  }, [dismiss]);

  // Clearing on unmount matters because the success timers outlive the page
  // otherwise and call setState on a gone component.
  useEffect(() => {
    const map = timers.current;
    return () => { map.forEach(clearTimeout); map.clear(); };
  }, []);

  return { toasts, push, dismiss };
}

export function ToastStack({
  toasts,
  onDismiss,
}: {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}) {
  if (!toasts.length) return null;
  return (
    <div
      // aria-live so a screen reader announces a save without the user having
      // to go looking for the confirmation.
      role="status"
      aria-live="polite"
      data-testid="toast-stack"
      style={{
        position: "fixed",
        right: 24,
        bottom: 24,
        zIndex: 60,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        maxWidth: 380,
      }}
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          data-testid={`toast-${t.kind}`}
          onClick={() => onDismiss(t.id)}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            padding: "10px 14px",
            background: "var(--panel)",
            border: `1px solid ${t.kind === "error" ? "var(--red, #d9534f)" : "var(--border)"}`,
            borderLeft: `2px solid ${t.kind === "error" ? "var(--red, #d9534f)" : "var(--amber)"}`,
            color: "var(--ink)",
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            lineHeight: 1.5,
            cursor: "pointer",
            boxShadow: "0 2px 12px rgba(0,0,0,0.35)",
          }}
          title="Dismiss"
        >
          <span style={{ color: t.kind === "error" ? "var(--red, #d9534f)" : "var(--amber)" }}>
            {t.kind === "error" ? "✕" : "✓"}
          </span>
          <span style={{ whiteSpace: "pre-wrap" }}>{t.message}</span>
        </div>
      ))}
    </div>
  );
}
