/**
 * The style picker and its preview window (components/StylePicker.tsx,
 * TMDEV-226): what a person sees and can do with a mouse and with the keyboard.
 * The groups themselves are tested in visual-styles.test.ts.
 */
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { StylePicker, StylePreviewButton } from "@/components/StylePicker";
import type { VisualStyleInfo } from "@/lib/types";
import { INSERT_IDS, PACK_STYLES } from "./packStyles";
import { openStyleList, pickStyle, styleOption, styleValue } from "./stylePickerHelpers";

const WITH_INSERTS: VisualStyleInfo[] = PACK_STYLES.map((s) =>
  INSERT_IDS.includes(s.id) ? { ...s, role: "insert" } : s);

function Harness({ initial = "auto", onChange = () => {}, styles = WITH_INSERTS, gpu = { status: "working" as const },
                   canUseOpenAI = true, noneLabel }: {
  initial?: string; onChange?: (v: string) => void; styles?: VisualStyleInfo[];
  gpu?: { status: "working" | "not_usable" | "unknown" }; canUseOpenAI?: boolean; noneLabel?: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <StylePicker testId="sp" styles={styles} canUseOpenAI={canUseOpenAI} gpu={gpu} value={value} noneLabel={noneLabel}
                 onChange={(v) => { setValue(v); onChange(v); }} />
  );
}

describe("StylePicker", () => {
  it("names the chosen style on its button, with its tags", () => {
    render(<Harness initial="cartoon_3d" />);
    const button = screen.getByTestId("sp");
    expect(button.textContent).toContain("Cartoon 3D");
    expect(button.textContent).toContain("GPU");
    expect(button.textContent).toContain("EXP");
    expect(button.getAttribute("aria-haspopup")).toBe("listbox");
  });

  it("shows the groups, and the GPU tag only on the styles that need one", () => {
    render(<Harness />);
    const list = openStyleList("sp");
    expect(within(list).getByTestId("sp-group-2d")).toBeTruthy();
    expect(within(list).getByTestId("sp-group-3d").textContent).toContain("Cartoon 3D");
    expect(within(list).getByTestId("sp-group-insert").textContent).toContain("System Flow");
    expect(styleOption("sp", "cartoon_3d").textContent).toContain("GPU");
    expect(styleOption("sp", "stick").textContent).not.toContain("GPU");
  });

  it("picks a row on click and closes", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    pickStyle("sp", "whiteboard");
    expect(onChange).toHaveBeenCalledWith("whiteboard");
    expect(styleValue("sp")).toBe("whiteboard");
    expect(screen.queryByTestId("sp-list")).toBeNull();
  });

  it("never picks an insert style or one the install cannot make", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} canUseOpenAI={false} gpu={{ status: "not_usable" }} />);
    for (const v of ["system_flow", "illustrated", "cartoon_3d"]) {
      expect(styleOption("sp", v).getAttribute("aria-disabled")).toBe("true");
      fireEvent.click(styleOption("sp", v));
    }
    expect(onChange).not.toHaveBeenCalled();
    expect(styleOption("sp", "cartoon_3d").textContent).toContain("needs a working GPU");
  });

  it("offers an empty choice when asked, picked like any row", () => {
    const onChange = vi.fn();
    render(<Harness initial="stick" noneLabel="No style" onChange={onChange} />);
    expect(styleOption("sp", "").textContent).toContain("No style");
    pickStyle("sp", "");
    expect(onChange).toHaveBeenCalledWith("");
    expect(screen.getByTestId("sp").textContent).toContain("No style");
  });

  it("works from the keyboard: arrows move, Enter picks, typing jumps to a name", async () => {
    const onChange = vi.fn();
    render(<Harness initial="auto" onChange={onChange} />);
    openStyleList("sp");
    const list = screen.getByTestId("sp-list");
    styleOption("sp", "auto").focus();
    fireEvent.keyDown(list, { key: "ArrowDown" });
    expect(document.activeElement?.getAttribute("data-value")).not.toBe("auto");
    fireEvent.keyDown(list, { key: "Home" });
    expect(document.activeElement?.getAttribute("data-value")).toBe("auto");
    fireEvent.keyDown(list, { key: "w" });
    expect(document.activeElement?.getAttribute("data-value")).toBe("whiteboard");
    fireEvent.keyDown(list, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("whiteboard");
  });

  it("opens the preview from a row's eye without picking it, then steps and picks from there", () => {
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    openStyleList("sp");
    fireEvent.click(screen.getByTestId("sp-preview-storybook_atlas"));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByTestId("style-preview-title").textContent).toBe("Storybook Atlas");
    const video = screen.getByTestId("style-preview-video") as HTMLVideoElement;
    expect(video.getAttribute("src")).toBe("/style-previews/storybook_atlas.mp4");
    expect(video.getAttribute("poster")).toBe("/style-previews/storybook_atlas.webp");
    expect(video.muted).toBe(true);
    fireEvent.click(screen.getByTestId("style-preview-next"));
    const next = screen.getByTestId("style-preview-title").textContent;
    expect(next).not.toBe("Storybook Atlas");
    fireEvent.click(screen.getByTestId("style-preview-prev"));
    expect(screen.getByTestId("style-preview-title").textContent).toBe("Storybook Atlas");
    fireEvent.click(screen.getByTestId("style-preview-use"));
    expect(onChange).toHaveBeenCalledWith("storybook_atlas");
    expect(screen.queryByTestId("style-preview")).toBeNull();
  });

  it("previews an insert or an unavailable style without offering to use it", () => {
    render(<Harness gpu={{ status: "not_usable" }} />);
    openStyleList("sp");
    fireEvent.click(screen.getByTestId("sp-preview-system_flow"));
    expect(screen.getByTestId("style-preview").textContent).toContain("never for a whole video");
    expect(screen.queryByTestId("style-preview-use")).toBeNull();
    fireEvent.keyDown(screen.getByTestId("style-preview"), { key: "Escape" });
  });

  it("leaves the arrow keys to the player when its controls have focus", () => {
    render(<Harness />);
    openStyleList("sp");
    fireEvent.click(screen.getByTestId("sp-preview-whiteboard"));
    fireEvent.keyDown(screen.getByTestId("style-preview-video"), { key: "ArrowRight" });
    expect(screen.getByTestId("style-preview-title").textContent).toBe("Whiteboard");
    fireEvent.keyDown(screen.getByTestId("style-preview-title"), { key: "ArrowRight" });
    expect(screen.getByTestId("style-preview-title").textContent).not.toBe("Whiteboard");
  });

  it("says why a style shown in the preview cannot be made here", () => {
    render(<Harness gpu={{ status: "not_usable" }} />);
    openStyleList("sp");
    fireEvent.click(screen.getByTestId("sp-preview-cartoon_3d"));
    expect(screen.getByTestId("style-preview-why").textContent).toContain("needs a working GPU");
    expect(screen.getByTestId("style-preview-tag-gpu")).toBeTruthy();
    expect(screen.queryByTestId("style-preview-use")).toBeNull();
  });
});

describe("external styles (TMDEV-252)", () => {
  const EXTERNAL: VisualStyleInfo = {
    id: "ext_paper", label: "Paper Cut", experimental: true, canvas: "light",
    needs: { openai_key: false, gpu: false }, mascot: false, available: true, unavailable_reason: "",
    dimension: "2d", preview: "ext_paper", tagline: "A paper-cut look.", role: "main",
    inserts: { host: false }, external: true,
  };

  it("marks an installed external style and plays its preview from the package", () => {
    render(<Harness styles={[...WITH_INSERTS, EXTERNAL]} />);
    openStyleList("sp");
    expect(styleOption("sp", "ext_paper").textContent).toContain("EXTERNAL");
    expect(styleOption("sp", "whiteboard").textContent).not.toContain("EXTERNAL");
    fireEvent.click(screen.getByTestId("sp-preview-ext_paper"));
    expect(screen.getByTestId("style-preview-tag-ext")).toBeTruthy();
    const video = screen.getByTestId("style-preview-video");
    expect(video.getAttribute("src")).toBe("/external-style-previews/ext_paper/preview.mp4");
    expect(video.getAttribute("poster")).toBe("/external-style-previews/ext_paper/preview.webp");
  });
});

describe("StylePreviewButton", () => {
  it("opens the preview of a frozen style, with no way to pick it", () => {
    render(<StylePreviewButton styleId="whiteboard" styles={PACK_STYLES} testId="eye" />);
    fireEvent.click(screen.getByTestId("eye"));
    expect(screen.getByTestId("style-preview-title").textContent).toBe("Whiteboard");
    expect(screen.queryByTestId("style-preview-use")).toBeNull();
  });

  it("renders nothing for a style with no preview", () => {
    const { container } = render(<StylePreviewButton styleId="" styles={PACK_STYLES} testId="eye" />);
    expect(container.innerHTML).toBe("");
    render(<StylePreviewButton styleId="from_a_newer_backend" styles={PACK_STYLES} testId="eye2" />);
    expect(screen.queryByTestId("eye2")).toBeNull();
  });
});
