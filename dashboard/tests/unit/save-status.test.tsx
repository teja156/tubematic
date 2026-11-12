import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SAVED_TTL_MS, SavesProvider, useSaveStatus, useSavesSummary, useSerialQueue,
} from "@/lib/saveStatus";
import { ACTION_TTL_MS, ToastStack, useToasts } from "@/components/Toast";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

const wrapper = ({ children }: { children: React.ReactNode }) => <SavesProvider>{children}</SavesProvider>;

describe("useSaveStatus", () => {
  afterEach(() => { vi.useRealTimers(); });

  it("shows saving, then saved, and clears the saved mark after a few seconds", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useSaveStatus());
    const d = deferred<string | null>();
    let done!: Promise<boolean>;
    act(() => { done = result.current.run("k", () => d.promise); });
    expect(result.current.get("k")).toEqual({ state: "saving", label: undefined });
    await act(async () => { d.resolve(null); await done; });
    expect(result.current.get("k")).toEqual({ state: "saved" });
    act(() => { vi.advanceTimersByTime(SAVED_TTL_MS); });
    expect(result.current.get("k")).toBeUndefined();
  });

  it("keeps a refusal's reason until the next change, and reports false", async () => {
    const { result } = renderHook(() => useSaveStatus());
    let ok = true;
    await act(async () => { ok = await result.current.run("k", async () => "too big"); });
    expect(ok).toBe(false);
    expect(result.current.get("k")).toEqual({ state: "error", message: "too big" });
  });

  it("lets only the newest run for a key set its outcome", async () => {
    const { result } = renderHook(() => useSaveStatus());
    const first = deferred<string | null>();
    const second = deferred<string | null>();
    let a!: Promise<boolean>;
    let b!: Promise<boolean>;
    act(() => { a = result.current.run("k", () => first.promise); });
    act(() => { b = result.current.run("k", () => second.promise); });
    await act(async () => { second.resolve(null); await b; });
    await act(async () => { first.resolve("old refusal"); await a; });
    // The older answer arrived last but must not replace the newer outcome.
    expect(result.current.get("k")).toEqual({ state: "saved" });
  });

  it("clearAll leaves a save still in flight alone", async () => {
    const { result } = renderHook(() => useSaveStatus());
    const d = deferred<string | null>();
    act(() => { result.current.fail("bad", "no"); });
    act(() => { void result.current.run("busy", () => d.promise); });
    act(() => { result.current.clearAll(); });
    expect(result.current.get("bad")).toBeUndefined();
    expect(result.current.get("busy")?.state).toBe("saving");
    await act(async () => { d.resolve(null); });
  });
});

describe("SavesProvider", () => {
  it("sums every field's state and asks before the tab closes while one is saving", async () => {
    const { result } = renderHook(() => ({ s: useSaveStatus(), sum: useSavesSummary() }), { wrapper });
    const unload = () => {
      const e = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(e);
      return e.defaultPrevented;
    };
    expect(result.current.sum).toEqual({ saving: 0, errors: 0 });
    expect(unload()).toBe(false);

    const d = deferred<string | null>();
    act(() => { void result.current.s.run("a", () => d.promise); });
    act(() => { result.current.s.fail("b", "refused"); });
    expect(result.current.sum).toEqual({ saving: 1, errors: 1 });
    expect(unload()).toBe(true);

    await act(async () => { d.resolve(null); });
    expect(result.current.sum).toEqual({ saving: 0, errors: 1 });
    expect(unload()).toBe(false);
  });

  it("drops a field's state when its component goes away", () => {
    function Field() {
      const s = useSaveStatus();
      return <button onClick={() => s.pending("x")}>wait</button>;
    }
    function Summary() {
      const { saving } = useSavesSummary();
      return <span data-testid="sum">{saving}</span>;
    }
    const { rerender } = render(<SavesProvider><Field /><Summary /></SavesProvider>);
    fireEvent.click(screen.getByText("wait"));
    expect(screen.getByTestId("sum").textContent).toBe("1");
    rerender(<SavesProvider><Summary /></SavesProvider>);
    expect(screen.getByTestId("sum").textContent).toBe("0");
  });
});

describe("a field gone with its save on its way", () => {
  it("stays counted until that save is over", async () => {
    let finish!: (v: string | null) => void;
    function Field() {
      const s = useSaveStatus();
      return <button onClick={() => { void s.run("x", () => new Promise((r) => { finish = r; })); }}>go</button>;
    }
    function Summary() {
      const { saving } = useSavesSummary();
      return <span data-testid="sum">{saving}</span>;
    }
    const { rerender } = render(<SavesProvider><Field /><Summary /></SavesProvider>);
    fireEvent.click(screen.getByText("go"));
    rerender(<SavesProvider><Summary /></SavesProvider>);
    expect(screen.getByTestId("sum").textContent).toBe("1");
    await act(async () => { finish(null); });
    expect(screen.getByTestId("sum").textContent).toBe("0");
  });
});

describe("useSerialQueue", () => {
  it("starts each write only after the one before has answered, even a failed one", async () => {
    const { result } = renderHook(() => useSerialQueue());
    const order: string[] = [];
    const first = deferred<void>();
    const a = result.current(async () => { order.push("a start"); await first.promise; throw new Error("x"); });
    const b = result.current(async () => { order.push("b start"); });
    await Promise.resolve();
    expect(order).toEqual(["a start"]);
    first.resolve();
    await expect(a).rejects.toThrow("x");
    await b;
    expect(order).toEqual(["a start", "b start"]);
  });
});

describe("Toast action", () => {
  afterEach(() => { vi.useRealTimers(); });

  function Harness({ onUndo }: { onUndo: () => void }) {
    const { toasts, push, dismiss } = useToasts();
    return (
      <>
        <button onClick={() => push("success", "Removed.", { label: "Undo", onClick: onUndo })}>go</button>
        <ToastStack toasts={toasts} onDismiss={dismiss} />
      </>
    );
  }

  it("runs the action once and closes the toast", () => {
    const onUndo = vi.fn();
    render(<Harness onUndo={onUndo} />);
    fireEvent.click(screen.getByText("go"));
    fireEvent.click(screen.getByTestId("toast-action"));
    expect(onUndo).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("toast-success")).toBeNull();
  });

  it("stays long enough to be clicked, then goes", () => {
    vi.useFakeTimers();
    render(<Harness onUndo={vi.fn()} />);
    fireEvent.click(screen.getByText("go"));
    act(() => { vi.advanceTimersByTime(ACTION_TTL_MS - 100); });
    expect(screen.getByTestId("toast-action")).toBeTruthy();
    act(() => { vi.advanceTimersByTime(200); });
    expect(screen.queryByTestId("toast-success")).toBeNull();
  });
});
