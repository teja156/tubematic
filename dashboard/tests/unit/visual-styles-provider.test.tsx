/**
 * VisualStylesProvider fetches GET /visual-styles once and shares the list.
 * vitest.setup.ts replaces useVisualStyles for every other test, so this file
 * reaches for the real module.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const real = await vi.importActual<typeof import("@/components/VisualStylesProvider")>("@/components/VisualStylesProvider");

function Show() {
  const styles = real.useVisualStyles();
  return <div data-testid="styles">{styles === null ? "null" : styles.map((s) => s.id).join(",")}</div>;
}

afterEach(() => vi.unstubAllGlobals());

describe("VisualStylesProvider", () => {
  it("shares the list the API returns", async () => {
    const fetchMock = vi.fn(async (_url: string) => new Response(JSON.stringify({ styles: [
      { id: "auto", label: "Auto", experimental: false, canvas: null, needs: { openai_key: false, gpu: false } },
      { id: "system_flow", label: "System Flow", experimental: false, canvas: "dark", needs: { openai_key: false, gpu: false } },
    ] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<real.VisualStylesProvider><Show /></real.VisualStylesProvider>);
    await waitFor(() => expect(screen.getByTestId("styles").textContent).toBe("auto,system_flow"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/proxy/visual-styles");
  });

  it("stays null when the API fails, so pickers offer only what they hold", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 502 })));
    render(<real.VisualStylesProvider><Show /></real.VisualStylesProvider>);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByTestId("styles").textContent).toBe("null");
  });
});
