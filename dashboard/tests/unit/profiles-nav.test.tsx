import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const pathname = vi.hoisted(() => ({ value: "/mascots" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.value }));

import { ProfilesNav } from "@/components/ProfilesNav";

describe("ProfilesNav", () => {
  it("links both pages and marks the current one", () => {
    pathname.value = "/mascots";
    render(<ProfilesNav />);
    expect(screen.getByTestId("profiles-subnav-script-profiles").getAttribute("href")).toBe("/script-profiles");
    expect(screen.getByTestId("profiles-subnav-mascots").getAttribute("aria-current")).toBe("page");
    expect(screen.getByTestId("profiles-subnav-script-profiles").getAttribute("aria-current")).toBeNull();
  });

  it("marks Script profiles on its own page", () => {
    pathname.value = "/script-profiles";
    render(<ProfilesNav />);
    expect(screen.getByTestId("profiles-subnav-script-profiles").getAttribute("aria-current")).toBe("page");
  });
});

describe("ProfilesNav, Styles (TMDEV-253)", () => {
  it("links the external styles page and marks it on its install screen", () => {
    pathname.value = "/styles/install/0123456789abcdef";
    render(<ProfilesNav />);
    expect(screen.getByTestId("profiles-subnav-styles").getAttribute("href")).toBe("/styles");
    expect(screen.getByTestId("profiles-subnav-styles").getAttribute("aria-current")).toBe("page");
  });
});
