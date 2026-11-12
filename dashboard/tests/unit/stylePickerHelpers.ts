/**
 * Driving the style picker (components/StylePicker.tsx) from a unit test, the
 * way a person does: open the list with the button, then click a row. The
 * button carries the picker's test id and its value in data-value; every row is
 * `${testId}-option-<value>` ("none" for the empty value), with aria-disabled
 * when it cannot be picked.
 */
import { fireEvent, screen } from "@testing-library/react";

export function openStyleList(testId: string): HTMLElement {
  const open = screen.queryByTestId(`${testId}-list`);
  if (open) return open;
  fireEvent.click(screen.getByTestId(testId));
  return screen.getByTestId(`${testId}-list`);
}

export function styleOption(testId: string, value: string): HTMLElement {
  openStyleList(testId);
  return screen.getByTestId(`${testId}-option-${value || "none"}`);
}

/** Opens the list and clicks the row: the change goes through only when the row is choosable. */
export function pickStyle(testId: string, value: string): void {
  fireEvent.click(styleOption(testId, value));
}

/** The value the picker holds. */
export function styleValue(testId: string): string | null {
  return screen.getByTestId(testId).getAttribute("data-value");
}

function rows(testId: string): HTMLElement[] {
  return Array.from(openStyleList(testId).querySelectorAll<HTMLElement>('[role="option"]'));
}

/** Every row's value, in list order. */
export function styleOptionValues(testId: string): string[] {
  return rows(testId).map((o) => o.dataset.value ?? "");
}

/** The values of the rows that cannot be picked. */
export function disabledStyleValues(testId: string): string[] {
  return rows(testId).filter((o) => o.getAttribute("aria-disabled") === "true").map((o) => o.dataset.value ?? "");
}

export function isStyleDisabled(testId: string, value: string): boolean {
  return styleOption(testId, value).getAttribute("aria-disabled") === "true";
}
