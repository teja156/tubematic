"use client";

// Every setting on the dashboard is kept the moment it is changed (TMDEV-218).
// This module holds the status each change shows beside its field ("Saving…",
// "✓ Saved", "Not saved: <reason>") and, through SavesProvider, the page-wide
// count the Settings header sums up.

import {
  createContext, useCallback, useContext, useEffect, useId, useMemo, useRef, useState,
} from "react";

export type SaveState =
  | { state: "saving"; label?: string }
  | { state: "saved" }
  | { state: "error"; message: string };

/** How long "✓ Saved" stays beside a field. */
export const SAVED_TTL_MS = 3000;

interface SavesContext {
  report: (id: string, state: SaveState | null) => void;
}

export interface SavesSummary {
  saving: number;
  errors: number;
}

const ReportContext = createContext<SavesContext | null>(null);
const SummaryContext = createContext<SavesSummary>({ saving: 0, errors: 0 });

/** Sums up every useSaveStatus below it, and asks before the browser tab is
 *  closed or reloaded while a change is still on its way to the API. */
export function SavesProvider({ children }: { children: React.ReactNode }) {
  const [entries, setEntries] = useState<Record<string, SaveState>>({});

  const report = useCallback((id: string, state: SaveState | null) => {
    setEntries((prev) => {
      if (!state) {
        if (!(id in prev)) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      }
      return { ...prev, [id]: state };
    });
  }, []);

  const summary = useMemo<SavesSummary>(() => {
    let saving = 0;
    let errors = 0;
    for (const s of Object.values(entries)) {
      if (s.state === "saving") saving++;
      else if (s.state === "error") errors++;
    }
    return { saving, errors };
  }, [entries]);

  useEffect(() => {
    if (!summary.saving) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Older browsers show the prompt only when returnValue is set.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [summary.saving]);

  const ctx = useMemo(() => ({ report }), [report]);
  return (
    <ReportContext.Provider value={ctx}>
      <SummaryContext.Provider value={summary}>{children}</SummaryContext.Provider>
    </ReportContext.Provider>
  );
}

export function useSavesSummary(): SavesSummary {
  return useContext(SummaryContext);
}

/** Runs a save and returns the reason it was refused, or null when it was kept. */
export type SaveFn = () => Promise<string | null>;

export interface SaveStatusApi {
  get: (key: string) => SaveState | undefined;
  /** Shows "Saving…" (or `label`) while `fn` runs, then its outcome. Resolves
   *  true when the change was kept. Only the newest run for a key may set its
   *  status, so an older answer arriving late cannot overwrite a newer one. */
  run: (key: string, fn: SaveFn, label?: string) => Promise<boolean>;
  /** Marks a change as waiting (a debounced text save) without running it yet. */
  pending: (key: string) => void;
  fail: (key: string, message: string) => void;
  clear: (key: string) => void;
  /** Clears every status except a save still in flight. */
  clearAll: () => void;
}

export function useSaveStatus(): SaveStatusApi {
  const scope = useId();
  const ctx = useContext(ReportContext);
  const [map, setMap] = useState<Record<string, SaveState>>({});
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const seq = useRef(new Map<string, number>());
  const keys = useRef(new Set<string>());
  const states = useRef(new Map<string, SaveState>());
  const mounted = useRef(true);
  // Keys with a `run` in progress, and the newest run started for each.
  const running = useRef(new Set<string>());
  const runs = useRef(new Map<string, number>());

  const set = useCallback((key: string, state: SaveState | null) => {
    if (!mounted.current) {
      // Unmounted with a save on its way (the field's tab was left): the page
      // kept counting it, and stops once it is over.
      if (state?.state !== "saving") ctx?.report(`${scope}:${key}`, null);
      return;
    }
    const timer = timers.current.get(key);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(key);
    }
    setMap((prev) => {
      if (!state) {
        if (!(key in prev)) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      }
      return { ...prev, [key]: state };
    });
    if (state) {
      keys.current.add(key);
      states.current.set(key, state);
    } else {
      keys.current.delete(key);
      states.current.delete(key);
    }
    ctx?.report(`${scope}:${key}`, state);
    if (state?.state === "saved") {
      timers.current.set(key, setTimeout(() => set(key, null), SAVED_TTL_MS));
    }
  }, [ctx, scope]);

  useEffect(() => {
    mounted.current = true;
    const timerMap = timers.current;
    const keySet = keys.current;
    return () => {
      // Report the keys gone, or a field unmounted would hold the page's
      // "Saving…" (and the leave-page prompt) for good. A save still on its
      // way stays counted until it is over (see `set`).
      keySet.forEach((k) => { if (!running.current.has(k)) ctx?.report(`${scope}:${k}`, null); });
      keySet.clear();
      timerMap.forEach(clearTimeout);
      timerMap.clear();
      mounted.current = false;
    };
  }, [ctx, scope]);

  const run = useCallback(async (key: string, fn: SaveFn, label?: string) => {
    const mine = (seq.current.get(key) ?? 0) + 1;
    seq.current.set(key, mine);
    set(key, { state: "saving", label });
    const myRun = (runs.current.get(key) ?? 0) + 1;
    runs.current.set(key, myRun);
    running.current.add(key);
    let error: string | null;
    try {
      error = await fn();
    } catch (e) {
      error = e instanceof Error && e.message ? e.message : "could not reach the API";
    }
    const last = runs.current.get(key) === myRun;
    if (last) running.current.delete(key);
    if (seq.current.get(key) === mine) {
      set(key, error ? { state: "error", message: error } : { state: "saved" });
    } else if (last && !mounted.current) {
      ctx?.report(`${scope}:${key}`, null);
    }
    return !error;
  }, [set]);

  // Does not bump the sequence: a save already on its way still reports its
  // outcome, and a refusal is never hidden by typing that follows it.
  const pending = useCallback((key: string) => {
    set(key, { state: "saving" });
  }, [set]);

  const fail = useCallback((key: string, message: string) => {
    seq.current.set(key, (seq.current.get(key) ?? 0) + 1);
    set(key, { state: "error", message });
  }, [set]);

  const clear = useCallback((key: string) => {
    seq.current.set(key, (seq.current.get(key) ?? 0) + 1);
    set(key, null);
  }, [set]);

  // A save still on its way is left alone: clearing it would drop the page's
  // "Saving…" and the leave-page prompt while the request is in flight.
  const clearAll = useCallback(() => {
    Array.from(keys.current)
      .filter((k) => states.current.get(k)?.state !== "saving")
      .forEach((k) => clear(k));
  }, [clear]);

  const get = useCallback((key: string) => map[key], [map]);

  return useMemo(
    () => ({ get, run, pending, fail, clear, clearAll }),
    [get, run, pending, fail, clear, clearAll],
  );
}

/** Reads an API error body's reason, or the HTTP status when there is none. */
export async function responseError(r: Response | null): Promise<string> {
  if (!r) return "could not reach the API";
  try {
    const body = await r.json();
    if (body && typeof body.error === "string" && body.error) return body.error;
  } catch { /* non-JSON error body — the status is all we have */ }
  return `HTTP ${r.status}`;
}

/** One chain of writes: each starts after the one before has answered, so a
 *  late answer can never overwrite a newer one. A refused or failed write does
 *  not stop the chain. */
export function useSerialQueue() {
  const tail = useRef<Promise<unknown>>(Promise.resolve());
  return useCallback(<T,>(write: () => Promise<T>): Promise<T> => {
    const run = tail.current.then(write);
    tail.current = run.then(() => undefined, () => undefined);
    return run;
  }, []);
}
