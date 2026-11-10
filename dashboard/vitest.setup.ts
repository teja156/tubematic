import "@testing-library/jest-dom";
import { vi } from "vitest";

// Components read the style list from VisualStylesProvider, which fetches it
// once at the app root. Tests render components without that root, so the
// hook answers with the list built from the real style packs.
vi.mock("@/components/VisualStylesProvider", async (importOriginal) => {
  const orig = await importOriginal<typeof import("@/components/VisualStylesProvider")>();
  const { PACK_STYLES } = await import("./tests/unit/packStyles");
  return { ...orig, useVisualStyles: () => PACK_STYLES };
});
