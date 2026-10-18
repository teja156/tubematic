/**
 * ReviseDialog sizing and submit behaviour.
 *
 * The layout assertions are regression guards for the dialog's textarea
 * overflowing the dialog. jsdom does no layout, so they pin the three causes
 * rather than the geometry:
 *  1. DialogContent's base `sm:max-w-sm` (384px) beats a class-based width, so
 *     the width must be inline.
 *  2. The base is a grid with an auto column; the header's nowrap title line
 *     widened it past the dialog. `grid-cols-1` (minmax(0, 1fr)) lets it shrink.
 *  3. DialogFooter's -mx-4/-mb-4 assume the base p-4, which this dialog drops.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReviseDialog } from "@/components/ReviseDialog";

const LONG_TITLE = "An extremely long topic brief ".repeat(60);

function open(onSubmit = vi.fn(async () => {}), onClose = vi.fn()) {
  render(<ReviseDialog open title={LONG_TITLE} onClose={onClose} onSubmit={onSubmit} />);
  return { onSubmit, onClose };
}

describe("ReviseDialog — layout", () => {
  it("sizes itself with an inline width, not a class", async () => {
    open();
    const dialog = await screen.findByTestId("revise-dialog");
    // The clamp comes from DialogContent itself and cannot be removed, which
    // is exactly why the width has to be inline.
    expect(dialog.className).toContain("sm:max-w-sm");
    expect(dialog.className).not.toMatch(/(^|\s)max-w-(lg|xl|md)/);
    expect(dialog.style.width).not.toBe("");
    expect(dialog.style.maxWidth).not.toBe("");
  });

  it("stays narrower than the VideoModal it opens on top of", async () => {
    open();
    const dialog = await screen.findByTestId("revise-dialog");
    expect(parseInt(dialog.style.maxWidth, 10)).toBeLessThan(1280);
  });

  it("uses a shrinkable grid column so a long title cannot widen it", async () => {
    open();
    const dialog = await screen.findByTestId("revise-dialog");
    expect(dialog.className).toContain("grid-cols-1");
  });

  it("zeroes the footer's negative margins, since the dialog drops the base padding", async () => {
    open();
    const footer = (await screen.findByTestId("revise-dialog"))
      .querySelector('[data-slot="dialog-footer"]') as HTMLElement;
    expect(footer.className).toContain("mx-0");
    expect(footer.className).not.toContain("-mx-4");
    expect(footer.className).not.toContain("-mb-4");
  });
});

describe("ReviseDialog — submit", () => {
  it("disables Send until there is non-blank text", async () => {
    open();
    const send = (await screen.findByText("Send Revision Request")) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("Describe what needs to change..."),
      { target: { value: "   " } });
    expect(send.disabled).toBe(true);
  });

  it("submits the trimmed text and closes", async () => {
    const { onSubmit, onClose } = open();
    fireEvent.change(await screen.findByPlaceholderText("Describe what needs to change..."),
      { target: { value: "  tighten the hook  " } });
    fireEvent.click(screen.getByText("Send Revision Request"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith("tighten the hook"));
    expect(onClose).toHaveBeenCalled();
  });
});
