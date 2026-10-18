import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { canonicalYouTubeUrl, MiningSources } from "@/components/MiningSources";

// Stored URLs are canonical: the API rewrites every accepted form to this.
const VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";
const VALID_URL_2 = "https://www.youtube.com/watch?v=abcdefghijk";
const SHORT_FORM = "https://youtu.be/dQw4w9WgXcQ?si=tracking";

// The same table as tubematic_core/tests/test_youtube.py, abridged: the Add
// button must light for what the API stores and stay dark for what it refuses.
describe("canonicalYouTubeUrl", () => {
  const ID = "dQw4w9WgXcQ";
  const CANON = `https://www.youtube.com/watch?v=${ID}`;

  it.each([
    `https://www.youtube.com/watch?v=${ID}`,
    `http://youtube.com/watch?v=${ID}&t=30`,
    `https://m.youtube.com/watch?feature=share&v=${ID}`,
    `https://youtu.be/${ID}?si=AbC`,
    `https://www.youtube.com/shorts/${ID}`,
    `https://youtube.com/live/${ID}?si=x`,
    `  https://youtu.be/${ID}  `,
    `HTTPS://WWW.YOUTUBE.COM/watch?v=${ID}`,
  ])("accepts %s", (url) => {
    expect(canonicalYouTubeUrl(url)).toBe(CANON);
  });

  it.each([
    "file:///etc/passwd",
    `http://127.0.0.1/watch?v=${ID}`,
    `http://169.254.169.254/?v=${ID}`,
    `https://youtube.com.evil.com/watch?v=${ID}`,
    `https://youtube.com@evil.com/watch?v=${ID}`,
    `https://www.youtube.com:8080/watch?v=${ID}`,
    "https://youtu.be/dQw4w9WgXc",
    "https://youtu.be/dQw4w9WgXcQQ",
    "https://www.youtube.com/watch?v=abc123",
    `https://youtu.be/${ID}\nhttp://127.0.0.1/`,
    `https://youtu.be/${ID}/extra`,
    `https://www.youtube.com/embed/${ID}`,
    "not-a-url",
    "",
  ])("refuses %s", (url) => {
    expect(canonicalYouTubeUrl(url)).toBeNull();
  });
});

describe("MiningSources", () => {
  it("renders the section with empty list", () => {
    render(<MiningSources urls={[]} saving={false} error={null} onChange={vi.fn()} />);
    expect(screen.getByTestId("mining-sources-section")).toBeTruthy();
    expect(screen.getByPlaceholderText("https://youtu.be/...")).toBeTruthy();
  });

  it("renders provided URLs with remove buttons", () => {
    render(<MiningSources urls={[VALID_URL, VALID_URL_2]} saving={false} error={null} onChange={vi.fn()} />);
    const items = screen.getAllByTestId("mining-url-item");
    expect(items).toHaveLength(2);
    expect(screen.getByText(VALID_URL)).toBeTruthy();
    expect(screen.getByText(VALID_URL_2)).toBeTruthy();
  });

  it("Add button is disabled when input is empty", () => {
    render(<MiningSources urls={[]} saving={false} error={null} onChange={vi.fn()} />);
    const addBtn = screen.getByTestId("mining-url-add") as HTMLButtonElement;
    expect(addBtn.disabled).toBe(true);
  });

  it("Add button is disabled for invalid URL", () => {
    render(<MiningSources urls={[]} saving={false} error={null} onChange={vi.fn()} />);
    const input = screen.getByTestId("mining-url-input");
    fireEvent.change(input, { target: { value: "not-a-url" } });
    const addBtn = screen.getByTestId("mining-url-add") as HTMLButtonElement;
    expect(addBtn.disabled).toBe(true);
  });

  it("Add button is enabled for a valid YouTube URL", () => {
    render(<MiningSources urls={[]} saving={false} error={null} onChange={vi.fn()} />);
    const input = screen.getByTestId("mining-url-input");
    fireEvent.change(input, { target: { value: VALID_URL } });
    const addBtn = screen.getByTestId("mining-url-add") as HTMLButtonElement;
    expect(addBtn.disabled).toBe(false);
  });

  it("clicking Add calls onChange with the appended URL in its canonical form", () => {
    const onChange = vi.fn();
    render(<MiningSources urls={[]} saving={false} error={null} onChange={onChange} />);
    const input = screen.getByTestId("mining-url-input");
    fireEvent.change(input, { target: { value: SHORT_FORM } });
    fireEvent.click(screen.getByTestId("mining-url-add"));
    expect(onChange).toHaveBeenCalledWith([VALID_URL]);
  });

  it("Add button is disabled for a URL with a wrong-length id", () => {
    render(<MiningSources urls={[]} saving={false} error={null} onChange={vi.fn()} />);
    fireEvent.change(screen.getByTestId("mining-url-input"),
      { target: { value: "https://www.youtube.com/watch?v=abc123" } });
    expect((screen.getByTestId("mining-url-add") as HTMLButtonElement).disabled).toBe(true);
  });

  it("clicking Remove calls onChange with the URL excluded", () => {
    const onChange = vi.fn();
    render(<MiningSources urls={[VALID_URL, VALID_URL_2]} saving={false} error={null} onChange={onChange} />);
    const removeButtons = screen.getAllByRole("button", { name: /Remove/ });
    fireEvent.click(removeButtons[0]);
    expect(onChange).toHaveBeenCalledWith([VALID_URL_2]);
  });

  it("does not add another spelling of a URL already listed", () => {
    render(<MiningSources urls={[VALID_URL]} saving={false} error={null} onChange={vi.fn()} />);
    const input = screen.getByTestId("mining-url-input");
    fireEvent.change(input, { target: { value: SHORT_FORM } });
    const addBtn = screen.getByTestId("mining-url-add") as HTMLButtonElement;
    expect(addBtn.disabled).toBe(true);
  });

  it("reflects an updated urls prop after a rerender", () => {
    const { rerender } = render(<MiningSources urls={[]} saving={false} error={null} onChange={vi.fn()} />);
    expect(screen.queryByTestId("mining-url-item")).toBeNull();

    rerender(<MiningSources urls={[VALID_URL]} saving={false} error={null} onChange={vi.fn()} />);
    expect(screen.getByText(VALID_URL)).toBeTruthy();
  });

  it("renders the error message when error is set", () => {
    render(<MiningSources urls={[]} saving={false} error="Failed to save mining sources — changes were not persisted." onChange={vi.fn()} />);
    expect(screen.getByText(/Failed to save mining sources/)).toBeTruthy();
  });

  it("disables Add and Remove buttons while saving", () => {
    render(<MiningSources urls={[VALID_URL]} saving={true} error={null} onChange={vi.fn()} />);
    const input = screen.getByTestId("mining-url-input");
    fireEvent.change(input, { target: { value: VALID_URL_2 } });
    expect((screen.getByTestId("mining-url-add") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: `Remove ${VALID_URL}` }) as HTMLButtonElement).disabled).toBe(true);
  });
});
