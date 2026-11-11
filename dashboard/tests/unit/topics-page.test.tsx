import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TopicsPage from "@/app/topics/page";

const MINING_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";

// A domain's defaults sit in a panel under its row, rendered only while the row
// is open. Every case that reads or changes a row's picker opens it first.
async function openDefaults(id = "seed-1") {
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.click(await waitFor(() => screen.getByTestId(`domain-edit-${id}`)));
}

function mockFetch({ miningOk = true, miningUrls = [MINING_URL] as string[],
                     savedUrls = undefined as string[] | undefined,
                     failBody = {} as Record<string, unknown> } = {}) {
  return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request,
                                                        init?: RequestInit) => {
    const urlStr = url.toString();
    if (urlStr.includes("/research/mining-sources")) {
      if (!miningOk) {
        return Promise.resolve({ ok: false, status: 400, json: () => Promise.resolve(failBody) } as Response);
      }
      // A save answers with the list as the API stored it.
      const stored = init?.method === "POST" ? (savedUrls ?? miningUrls) : miningUrls;
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: stored }) } as Response);
    }
    if (urlStr.includes("/research/strategies")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: ["curriculum", "trending", "mining"] }) } as Response);
    }
    if (urlStr.includes("/videos")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
  });
}

describe("TopicsPage — mining sources", () => {
  afterEach(() => vi.restoreAllMocks());

  it("displays mining URLs loaded from the API after mount", async () => {
    mockFetch({ miningUrls: [MINING_URL] });
    render(<TopicsPage />);

    // Regression: MiningSources previously seeded state from an initialUrls
    // prop that was always [] at first mount, so a loaded URL never rendered.
    await waitFor(() => {
      expect(screen.getByText(MINING_URL)).toBeTruthy();
    });
  });

  it("reverts the list and shows an error when saving mining sources fails", async () => {
    const fetchSpy = mockFetch({ miningOk: false, miningUrls: [] });
    render(<TopicsPage />);

    await waitFor(() => screen.getByTestId("mining-url-input"));

    const input = screen.getByTestId("mining-url-input");
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(input, { target: { value: MINING_URL } });
    fireEvent.click(screen.getByTestId("mining-url-add"));

    await waitFor(() => {
      expect(screen.getByText(/Failed to save mining sources/)).toBeTruthy();
    });
    // Reverted — the optimistically-added URL should not remain listed.
    expect(screen.queryByTestId("mining-url-item")).toBeNull();

    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/proxy/research/mining-sources",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows the API's refusal, which names the bad entries", async () => {
    mockFetch({ miningOk: false, miningUrls: [],
                failBody: { error: "Not a YouTube video URL: 'file:///x'." } });
    render(<TopicsPage />);
    await waitFor(() => screen.getByTestId("mining-url-input"));
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(screen.getByTestId("mining-url-input"), { target: { value: MINING_URL } });
    fireEvent.click(screen.getByTestId("mining-url-add"));
    await waitFor(() => {
      expect(screen.getByText(/Not a YouTube video URL: 'file:\/\/\/x'/)).toBeTruthy();
    });
  });

  it("lists what the API stored after a save", async () => {
    // Whatever the API answers is what is listed — here deliberately not
    // what was sent, so a page that kept its own copy would fail.
    const stored = "https://www.youtube.com/watch?v=abcdefghijk";
    mockFetch({ miningUrls: [], savedUrls: [stored] });
    render(<TopicsPage />);
    await waitFor(() => screen.getByTestId("mining-url-input"));
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(screen.getByTestId("mining-url-input"),
      { target: { value: "https://youtu.be/dQw4w9WgXcQ?si=x" } });
    fireEvent.click(screen.getByTestId("mining-url-add"));
    await waitFor(() => {
      expect(screen.getAllByTestId("mining-url-item").map((el) => el.textContent))
        .toEqual([expect.stringContaining(stored)]);
    });
  });
});

describe("TopicsPage — removing a mining URL", () => {
  afterEach(() => vi.restoreAllMocks());

  it("applies at once and offers an Undo that puts the list back", async () => {
    let stored = [MINING_URL];
    const posts: string[][] = [];
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.includes("/research/mining-sources")) {
        if (init?.method === "POST") {
          stored = JSON.parse(String(init.body)).youtube_urls;
          posts.push(stored);
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: stored }) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: ["mining"] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    fireEvent.click(await screen.findByRole("button", { name: `Remove ${MINING_URL}` }));
    await waitFor(() => expect(screen.getByTestId("toast-success").textContent)
      .toContain(`Removed ${MINING_URL}.`));
    expect(screen.queryByTestId("mining-url-item")).toBeNull();
    expect(screen.getByTestId("mining-save-status").textContent).toBe("✓ Saved");

    // A URL added after the removal stays when the removal is undone.
    const later = "https://www.youtube.com/watch?v=abcdefghijk";
    fireEvent.change(screen.getByTestId("mining-url-input"), { target: { value: later } });
    fireEvent.click(screen.getByTestId("mining-url-add"));
    await waitFor(() => expect(screen.getAllByTestId("mining-url-item")).toHaveLength(1));

    fireEvent.click(screen.getByTestId("toast-action"));
    await waitFor(() => expect(screen.getAllByTestId("mining-url-item")).toHaveLength(2));
    expect(posts).toEqual([[], [later], [MINING_URL, later]]);
  });
});

describe("TopicsPage — mining saves run one at a time", () => {
  afterEach(() => vi.restoreAllMocks());

  it("a second change waits for the first to be answered", async () => {
    const second = "https://www.youtube.com/watch?v=abcdefghijk";
    const answers: Array<() => void> = [];
    const posts: string[][] = [];
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.includes("/research/mining-sources")) {
        if (init?.method === "POST") {
          const list = JSON.parse(String(init.body)).youtube_urls as string[];
          posts.push(list);
          return new Promise((resolve) => answers.push(() => resolve(
            { ok: true, json: () => Promise.resolve({ youtube_urls: list }) } as Response)));
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [MINING_URL, second] }) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: ["mining"] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    fireEvent.click(await screen.findByRole("button", { name: `Remove ${MINING_URL}` }));
    await waitFor(() => expect(posts).toHaveLength(1));
    // The list is disabled while saving; the Undo in the toast is not.
    answers[0]();
    await waitFor(() => expect(screen.getByTestId("toast-action")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: `Remove ${second}` }));
    fireEvent.click(screen.getByTestId("toast-action"));
    await waitFor(() => expect(posts).toHaveLength(2));
    await new Promise((r) => setTimeout(r, 20));
    expect(posts).toHaveLength(2);
    answers[1]();
    await waitFor(() => expect(posts).toHaveLength(3));
    answers[2]();
    expect(posts).toEqual([[second], [], [MINING_URL]]);
  });
});

// Pause is a curriculum-seed control: for any other domain the pause could
// never stop the subject being researched, only which row it was filed into.
describe("TopicsPage — domain pause", () => {
  afterEach(() => vi.restoreAllMocks());

  const SEED = {
    id: "seed-1", name: "Linux internals", description: "", is_curriculum_seed: 1,
    status: "active", default_visual_style: "", created_at: "2026-01-01T00:00:00Z",
  };
  const NON_SEED = { ...SEED, id: "plain-1", name: "Database internals", is_curriculum_seed: 0 };

  function mockDomains(statusOk = true) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.includes("/status")) {
        return Promise.resolve({
          ok: statusOk, status: statusOk ? 200 : 409,
          json: () => Promise.resolve(statusOk ? {} : { error: "Project 'seed-1' is not a curriculum seed" }),
        } as Response);
      }
      if (urlStr.endsWith("/projects")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([SEED, NON_SEED]) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: [] }) } as Response);
      }
      if (urlStr.includes("/research/mining-sources")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
  }

  it("offers the renamed pause control and badge on a curriculum seed", async () => {
    mockDomains();
    render(<TopicsPage />);
    const toggle = await waitFor(() => screen.getByTestId("toggle-domain-seed-1"));
    expect(toggle.textContent).toBe("Pause topic generation");
    expect(screen.getByTestId("domain-status-seed-1").textContent).toBe("ACTIVE");
  });

  it("offers neither on a domain that is not a seed", async () => {
    mockDomains();
    render(<TopicsPage />);
    await waitFor(() => screen.getByTestId("domain-row-plain-1"));
    expect(screen.queryByTestId("toggle-domain-plain-1")).toBeNull();
    expect(screen.queryByTestId("domain-status-plain-1")).toBeNull();
  });

  it("shows the paused state once the pause is accepted", async () => {
    mockDomains();
    render(<TopicsPage />);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(await waitFor(() => screen.getByTestId("toggle-domain-seed-1")));
    await waitFor(() => {
      expect(screen.getByTestId("domain-status-seed-1").textContent).toBe("PAUSED");
    });
    expect(screen.getByTestId("toggle-domain-seed-1").textContent).toBe("Resume topic generation");
  });

  it("reports a refused pause beside the domain and leaves it as it was", async () => {
    mockDomains(false);
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    render(<TopicsPage />);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(await waitFor(() => screen.getByTestId("toggle-domain-seed-1")));
    await waitFor(() => expect(screen.getByTestId("domain-save-status-seed-1").textContent)
      .toContain("not a curriculum seed"));
    expect(alertSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId("domain-status-seed-1").textContent).toBe("ACTIVE");
  });
});

// ── Illustrated as a domain default needs an OpenAI key ─────────────────────

describe("TopicsPage — Illustrated default", () => {
  afterEach(() => vi.restoreAllMocks());

  const DOMAIN = {
    id: "seed-1", name: "Linux internals", description: "", is_curriculum_seed: 1,
    status: "active", default_visual_style: "", created_at: "2026-01-01T00:00:00Z",
  };

  function mockWithKey(openaiKey: string) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/settings")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ openai_api_key: openaiKey }) } as Response);
      }
      if (urlStr.endsWith("/projects")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([DOMAIN]) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: [] }) } as Response);
      }
      if (urlStr.includes("/research/mining-sources")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
  }

  function illustratedOption(testId: string) {
    const select = screen.getByTestId(testId) as HTMLSelectElement;
    return [...select.options].find((o) => o.value === "illustrated")!;
  }

  it("disables it in both pickers when no OpenAI key is stored", async () => {
    mockWithKey("");
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(illustratedOption("domain-style-seed-1").disabled).toBe(true));
    expect(illustratedOption("domain-style-seed-1").textContent).toMatch(/needs an OpenAI key/);
    expect(illustratedOption("domain-style-select").disabled).toBe(true);
  });

  it("offers it when a key is stored", async () => {
    mockWithKey("••••••••abcd");
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    await waitFor(() => expect(illustratedOption("domain-style-seed-1").disabled).toBe(false));
    expect(illustratedOption("domain-style-select").disabled).toBe(false);
  });
});

// TMDEV-121: a domain's default voice. POST /projects is a full replace, so
// every edit must re-send every field, or changing one silently clears another.
describe("TopicsPage — default voice", () => {
  afterEach(() => vi.restoreAllMocks());

  const VOICES = [
    { name: "Rachel", voice_id: "r1", model_id: "eleven_multilingual_v2" },
    { name: "Adam", voice_id: "a1", model_id: "eleven_v3" },
  ];
  const DOMAIN = {
    id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: 1,
    status: "active", default_visual_style: "stick", default_voice_id: "a1",
    topic_cap: 300, topic_count: 12, expired: false, created_at: "2026-01-01T00:00:00Z",
  };

  function mockDomains(domain: object = DOMAIN) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/projects") && !init?.method) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([domain]) } as Response);
      }
      if (urlStr.includes("/settings")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          elevenlabs_voices: VOICES, elevenlabs_voice_id: "r1", openai_api_key: "" }) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: [] }) } as Response);
      }
      if (urlStr.includes("/research/mining-sources")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
  }

  function postedProject(spy: ReturnType<typeof mockDomains>) {
    const call = spy.mock.calls.find(([u, i]) => u.toString().endsWith("/projects")
      && (i as RequestInit | undefined)?.method === "POST");
    return JSON.parse(String((call![1] as RequestInit).body));
  }

  it("shows the domain's default voice with each voice's model", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-voice-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(select.value).toBe("a1"));
    expect([...select.options].map((o) => o.textContent)).toContain("Adam · eleven_v3");
  });

  it("changing the voice re-sends every other field", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-voice-seed-1"));
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("a1"));
    fireEvent.change(select, { target: { value: "r1" } });
    await waitFor(() => expect(postedProject(spy)).toEqual({
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "stick", default_voice_id: "r1",
      default_script_profile_id: "", default_mascot_id: "", default_agent_id: "", default_agent_model: "",
      default_agent_effort: "", topic_cap: 300 }));
  });

  it("changing the style keeps the default voice", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    fireEvent.change(select, { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy).default_voice_id).toBe("a1"));
  });

  it("keeps a default voice that has left the roster visible as removed", async () => {
    mockDomains({ ...DOMAIN, default_voice_id: "gone" });
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getByRole("option", { name: "gone (removed)" })).toBeTruthy());
  });

  it("the add-domain form sends the picked voice", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Adam · eleven_v3" }).length).toBe(2));
    fireEvent.change(screen.getByTestId("domain-voice-select"), { target: { value: "a1" } });
    fireEvent.change(screen.getByPlaceholderText(/name/i), { target: { value: "New domain" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(postedProject(spy).default_voice_id).toBe("a1"));
  });
});

// TMDEV-145: a domain's default script profile, the third per-domain picker.
// It seeds curriculum videos only, like the visual style, and rides the same
// full-replace POST /projects, so it must be re-sent by every other edit.
describe("TopicsPage — default script profile", () => {
  afterEach(() => vi.restoreAllMocks());

  const PROFILES = [
    { id: "p-ready", name: "Fireship", status: "READY" },
    { id: "p-pending", name: "Still building", status: "PENDING" },
  ];
  const DOMAIN = {
    id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: 1,
    status: "active", default_visual_style: "stick", default_voice_id: "",
    default_script_profile_id: "p-ready", topic_cap: 300, topic_count: 12, expired: false,
    created_at: "2026-01-01T00:00:00Z",
  };

  function mockDomains(domain: object = DOMAIN) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/projects") && !init?.method) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([domain]) } as Response);
      }
      if (urlStr.endsWith("/script-profiles")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(PROFILES) } as Response);
      }
      if (urlStr.includes("/settings")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          elevenlabs_voices: [], elevenlabs_voice_id: "", openai_api_key: "" }) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: [] }) } as Response);
      }
      if (urlStr.includes("/research/mining-sources")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
  }

  function postedProject(spy: ReturnType<typeof mockDomains>) {
    const call = spy.mock.calls.find(([u, i]) => u.toString().endsWith("/projects")
      && (i as RequestInit | undefined)?.method === "POST");
    return JSON.parse(String((call![1] as RequestInit).body));
  }

  it("labels all three domain pickers", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => screen.getByTestId("domain-profile-seed-1"));
    const row = screen.getByTestId("domain-row-seed-1");
    for (const label of ["Visual style", "Default voice", "Script profile"]) {
      expect(row.textContent).toContain(label);
    }
    // Each label names its own select, not merely sits near it.
    expect(screen.getAllByLabelText("Script profile")).toContain(screen.getByTestId("domain-profile-seed-1"));
  });

  it("offers only READY profiles and shows the domain's default", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-profile-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(select.value).toBe("p-ready"));
    const names = [...select.options].map((o) => o.textContent);
    expect(names).toContain("Fireship");
    expect(names).not.toContain("Still building");
  });

  it("changing the profile re-sends every other field", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-profile-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(select.value).toBe("p-ready"));
    fireEvent.change(select, { target: { value: "" } });
    await waitFor(() => expect(postedProject(spy)).toEqual({
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "stick", default_voice_id: "",
      default_script_profile_id: "", default_mascot_id: "", default_agent_id: "", default_agent_model: "",
      default_agent_effort: "", topic_cap: 300 }));
  });

  it("changing the style keeps the default profile", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    fireEvent.change(select, { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy).default_script_profile_id).toBe("p-ready"));
  });

  it("keeps a default that is no longer offered visible as unavailable", async () => {
    // A deleted profile is missing from the list, so there is no name; the id
    // is a UUID in a real install and must not be shown in its place.
    mockDomains({ ...DOMAIN, default_script_profile_id: "p-gone" });
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getByRole("option", { name: "Unavailable profile" })).toBeTruthy());
  });

  // Profile names are user-supplied with no length limit, and a <select> is as
  // wide as its longest option: sized by its content, one long name pushed the
  // controls after it off-screen, where overflow-x: hidden made them
  // unreachable. Each picker fills its field instead.
  it("sizes the profile picker to its field, on the row and in the add form", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    const row = await waitFor(() => screen.getByTestId("domain-profile-seed-1"));
    expect((row as HTMLSelectElement).style.width).toBe("100%");
    expect((screen.getByTestId("domain-profile-select") as HTMLSelectElement).style.width).toBe("100%");
  });

  it("names a held default that is listed but not READY", async () => {
    mockDomains({ ...DOMAIN, default_script_profile_id: "p-pending" });
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getByRole("option", { name: "Still building (unavailable)" })).toBeTruthy());
  });

  it("the add-domain form sends the picked profile", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Fireship" }).length).toBe(2));
    fireEvent.change(screen.getByTestId("domain-profile-select"), { target: { value: "p-ready" } });
    fireEvent.change(screen.getByPlaceholderText(/name/i), { target: { value: "New domain" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(postedProject(spy).default_script_profile_id).toBe("p-ready"));
  });
});

// A domain's default mascot: "" inherits the install default, "none" pins no
// mascot. It rides the same full-replace POST /projects, so every other edit
// must re-send it.
describe("TopicsPage — default mascot", () => {
  afterEach(() => vi.restoreAllMocks());
  let gpuStatus = "working";
  beforeEach(() => { gpuStatus = "working"; });

  const MASCOTS = [
    { id: "tubi", name: "Tubi", pickable: true },
    { id: "moss", name: "Moss", pickable: false },
  ];
  const DOMAIN = {
    id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: 1,
    status: "active", default_visual_style: "stick", default_voice_id: "",
    default_script_profile_id: "", default_mascot_id: "tubi", topic_cap: 300, topic_count: 12,
    expired: false, created_at: "2026-01-01T00:00:00Z",
  };

  function mockDomains(domain: object = DOMAIN) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      const ok = (body: unknown) => Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
      if (urlStr.endsWith("/projects") && !init?.method) return ok([domain]);
      if (urlStr.endsWith("/mascots")) return ok(MASCOTS);
      if (urlStr.endsWith("/render/gpu")) return ok({ status: gpuStatus });
      if (urlStr.includes("/settings")) return ok({ elevenlabs_voices: [], elevenlabs_voice_id: "", openai_api_key: "" });
      if (urlStr.includes("/research/strategies")) return ok({ strategies: [] });
      if (urlStr.includes("/research/mining-sources")) return ok({ youtube_urls: [] });
      return ok([]);
    });
  }

  function postedProject(spy: ReturnType<typeof mockDomains>) {
    const call = spy.mock.calls.find(([u, i]) => u.toString().endsWith("/projects")
      && (i as RequestInit | undefined)?.method === "POST");
    return JSON.parse(String((call![1] as RequestInit).body));
  }

  it("offers install default, None and each pickable mascot", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-mascot-seed-1") as HTMLSelectElement);
    await waitFor(() => expect([...select.options].map((o) => o.value)).toEqual(["", "none", "tubi"]));
    expect(select.value).toBe("tubi");
    expect(screen.getByLabelText("Mascot (exp.)", { selector: "[data-testid='domain-mascot-seed-1']" })).toBe(select);
    expect(screen.getAllByRole("option", { name: "Use install default" }).length).toBe(2);
  });

  it("changing the mascot re-sends every other field", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-mascot-seed-1"));
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("tubi"));
    fireEvent.change(select, { target: { value: "none" } });
    await waitFor(() => expect(postedProject(spy)).toEqual({
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "stick", default_voice_id: "",
      default_script_profile_id: "", default_mascot_id: "none", default_agent_id: "", default_agent_model: "",
      default_agent_effort: "", topic_cap: 300 }));
  });

  it("another edit re-sends the stored default mascot (POST /projects is a full replace)", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    fireEvent.change(select, { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy).default_mascot_id).toBe("tubi"));
  });

  it("a domain with no mascot set re-sends an empty string, never omits the field", async () => {
    const spy = mockDomains({ ...DOMAIN, default_mascot_id: undefined });
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    fireEvent.change(select, { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy)).toHaveProperty("default_mascot_id", ""));
  });

  it("keeps a held default that is no longer pickable visible as unavailable", async () => {
    mockDomains({ ...DOMAIN, default_mascot_id: "moss" });
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getByRole("option", { name: "Moss (unavailable)" })).toBeTruthy());
  });

  it.each([
    ["not_usable", "Tubi (Mascots need a working GPU)"],
    ["not_configured", "Tubi (Mascots need a working GPU)"],
    ["unknown", "Tubi (GPU not tested yet)"],
  ])("disables the mascots, not the non-mascot choices, while the GPU is %s", async (status, label) => {
    gpuStatus = status;
    mockDomains({ ...DOMAIN, default_mascot_id: "" });
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-mascot-seed-1") as HTMLSelectElement);
    await waitFor(() => expect([...select.options].find((o) => o.value === "tubi")?.textContent).toBe(label));
    const by = (v: string) => [...select.options].find((o) => o.value === v)!;
    expect(by("tubi").disabled).toBe(true);
    expect(by("").disabled).toBe(false);
    expect(by("none").disabled).toBe(false);
    const add = screen.getByTestId("domain-mascot-select") as HTMLSelectElement;
    expect([...add.options].find((o) => o.value === "tubi")!.disabled).toBe(true);
  });

  it("a held default stays shown and is re-sent untouched while the GPU is not working", async () => {
    gpuStatus = "not_usable";
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-mascot-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(select.value).toBe("tubi"));
    expect([...select.options].find((o) => o.value === "tubi")!.disabled).toBe(false);
    fireEvent.change(screen.getByTestId("domain-style-seed-1"), { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy).default_mascot_id).toBe("tubi"));
  });

  it("fails closed before the GPU status has loaded", async () => {
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const u = url.toString();
      const ok = (b: unknown) => Promise.resolve({ ok: true, json: () => Promise.resolve(b) } as Response);
      if (u.endsWith("/render/gpu")) return new Promise<Response>(() => {});
      if (u.endsWith("/projects")) return ok([{ ...DOMAIN, default_mascot_id: "" }]);
      if (u.endsWith("/mascots")) return ok(MASCOTS);
      if (u.includes("/settings")) return ok({ elevenlabs_voices: [], elevenlabs_voice_id: "", openai_api_key: "" });
      if (u.includes("/research/strategies")) return ok({ strategies: [] });
      if (u.includes("/research/mining-sources")) return ok({ youtube_urls: [] });
      return ok([]);
    });
    render(<TopicsPage />);
    await openDefaults();
    const select = await waitFor(() => screen.getByTestId("domain-mascot-seed-1") as HTMLSelectElement);
    await waitFor(() => expect([...select.options].find((o) => o.value === "tubi")?.disabled).toBe(true));
  });

  it("the add-domain form sends the picked mascot", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Tubi" }).length).toBe(2));
    fireEvent.change(screen.getByTestId("domain-mascot-select"), { target: { value: "tubi" } });
    fireEvent.change(screen.getByPlaceholderText(/name/i), { target: { value: "New domain" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(postedProject(spy).default_mascot_id).toBe("tubi"));
  });
});

// TMDEV-153: a domain's topic cap. Research deduplicates against every topic
// ever filed into a domain, so the domain may only ever hold so many; at the
// cap it is expired and research files nothing more there.
describe("TopicsPage — topic cap", () => {
  afterEach(() => vi.restoreAllMocks());

  const DOMAIN = {
    id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: 1,
    status: "active", default_visual_style: "", default_voice_id: "",
    default_script_profile_id: "", topic_cap: 100, topic_count: 40, expired: false,
    created_at: "2026-01-01T00:00:00Z",
  };

  // `filedNow` is the count the API holds when a save lands, which can be
  // ahead of what the page loaded: research may have filed in between.
  function mockDomains(domain: object = DOMAIN, filedNow = (domain as typeof DOMAIN).topic_count) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/projects") && !init?.method) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([domain]) } as Response);
      }
      if (urlStr.endsWith("/projects") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        const row = { ...domain, ...body, is_curriculum_seed: body.is_curriculum_seed ? 1 : 0,
                      topic_count: filedNow, expired: filedNow >= body.topic_cap };
        return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve(row) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: [] }) } as Response);
      }
      if (urlStr.includes("/research/mining-sources")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
  }

  function projectPosts(spy: ReturnType<typeof mockDomains>) {
    return spy.mock.calls
      .filter(([u, i]) => u.toString().endsWith("/projects") && (i as RequestInit | undefined)?.method === "POST")
      .map(([, i]) => JSON.parse(String((i as RequestInit).body)));
  }

  it("shows the cap, bounded, and the whole topic history beside it", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    const input = await waitFor(() => screen.getByTestId("domain-cap-seed-1") as HTMLInputElement);
    await waitFor(() => expect(input.value).toBe("100"));
    expect(input.min).toBe("25");
    expect(input.max).toBe("750");
    expect(screen.getByTestId("domain-topic-count-seed-1").textContent).toBe("40 filed");
    expect(screen.getAllByLabelText("Topic cap")).toContain(input);
    expect(screen.queryByTestId("domain-expired-seed-1")).toBeNull();
  });

  it("saves a new cap on blur, re-sending every other field", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const input = await waitFor(() => screen.getByTestId("domain-cap-seed-1"));
    await waitFor(() => expect((input as HTMLInputElement).value).toBe("100"));
    fireEvent.change(input, { target: { value: "250" } });
    expect(projectPosts(spy)).toEqual([]); // nothing until the field is left
    fireEvent.blur(input);
    await waitFor(() => expect(projectPosts(spy)).toEqual([{
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "", default_voice_id: "",
      default_script_profile_id: "", default_mascot_id: "", default_agent_id: "", default_agent_model: "",
      default_agent_effort: "", topic_cap: 250 }]));
  });

  it.each(["24", "751", "abc", "100.5", ""])("reverts %j without saving", async (bad) => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const input = await waitFor(() => screen.getByTestId("domain-cap-seed-1") as HTMLInputElement);
    await waitFor(() => expect(input.value).toBe("100"));
    fireEvent.change(input, { target: { value: bad } });
    fireEvent.blur(input);
    await waitFor(() => expect(input.value).toBe("100"));
    expect(projectPosts(spy)).toEqual([]);
  });

  it("shows EXPIRED on any domain at its cap, seed or not", async () => {
    mockDomains({ ...DOMAIN, is_curriculum_seed: 0, topic_cap: 40, expired: true });
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getByTestId("domain-expired-seed-1").textContent).toBe("EXPIRED"));
  });

  // ACTIVE beside EXPIRED read as a contradiction: an active seed at its cap
  // generates nothing. A pause is still shown, since it is a second reason.
  it("hides ACTIVE on an expired seed but keeps PAUSED", async () => {
    mockDomains({ ...DOMAIN, topic_cap: 40, expired: true });
    const { unmount } = render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => screen.getByTestId("domain-expired-seed-1"));
    expect(screen.queryByTestId("domain-status-seed-1")).toBeNull();
    expect(screen.getByTestId("toggle-domain-seed-1")).toBeTruthy();
    unmount();
    vi.restoreAllMocks();

    mockDomains({ ...DOMAIN, status: "paused", topic_cap: 40, expired: true });
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect(screen.getByTestId("domain-status-seed-1").textContent).toBe("PAUSED"));
    expect(screen.getByTestId("domain-expired-seed-1")).toBeTruthy();
  });

  it("lowering the cap to the count expires the domain at once", async () => {
    mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const input = await waitFor(() => screen.getByTestId("domain-cap-seed-1"));
    await waitFor(() => expect((input as HTMLInputElement).value).toBe("100"));
    fireEvent.change(input, { target: { value: "40" } });
    fireEvent.blur(input);
    await waitFor(() => expect(screen.getByTestId("domain-expired-seed-1")).toBeTruthy());
  });

  // The page loaded with 40 filed, but research filed 20 more before the cap
  // was edited. Worked out from the stale 40, a cap of 50 would read as open
  // while the API refuses research; the saved row says expired, at 60.
  it("takes the count and expiry from the saved row, not the stale page", async () => {
    mockDomains(DOMAIN, 60);
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const input = await waitFor(() => screen.getByTestId("domain-cap-seed-1"));
    await waitFor(() => expect((input as HTMLInputElement).value).toBe("100"));
    expect(screen.getByTestId("domain-topic-count-seed-1").textContent).toBe("40 filed");
    fireEvent.change(input, { target: { value: "50" } });
    fireEvent.blur(input);
    await waitFor(() => expect(screen.getByTestId("domain-expired-seed-1")).toBeTruthy());
    expect(screen.getByTestId("domain-topic-count-seed-1").textContent).toBe("60 filed");
  });
});

// ── Mining needs a Gemini key (TMDEV-165) ─────────────────────────────────────

function mockStrategies({ miningAvailable, strategies, postStatus = 200,
                          postBody = {} as Record<string, unknown> }:
                        { miningAvailable: boolean; strategies: string[]; postStatus?: number;
                          postBody?: Record<string, unknown> }) {
  return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request,
                                                        init?: RequestInit) => {
    const urlStr = url.toString();
    if (urlStr.includes("/research/strategies")) {
      if (init?.method === "POST") {
        return Promise.resolve({ ok: postStatus < 400, status: postStatus,
                                 json: () => Promise.resolve(postBody) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(
        { strategies, mining_available: miningAvailable }) } as Response);
    }
    if (urlStr.includes("/research/mining-sources")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
  });
}

describe("TopicsPage — mining needs a Gemini key", () => {
  afterEach(() => vi.restoreAllMocks());

  it("greys out the mining toggle with the reason on hover when no key is stored", async () => {
    mockStrategies({ miningAvailable: false, strategies: ["curriculum", "trending"] });
    render(<TopicsPage />);
    await waitFor(() => {
      expect((screen.getByTestId("mode-toggle-mining") as HTMLButtonElement).disabled).toBe(true);
    });
    const mining = screen.getByTestId("mode-toggle-mining");
    expect(mining.getAttribute("title")).toMatch(/Needs a Gemini API key/);
    expect((screen.getByTestId("mode-toggle-trending") as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByText(/Mining is off: it needs a Gemini API key/)).toBeTruthy();
  });

  it("leaves mining usable when a key is stored", async () => {
    mockStrategies({ miningAvailable: true, strategies: ["curriculum", "trending", "mining"] });
    render(<TopicsPage />);
    await waitFor(() => screen.getByTestId("mode-toggle-mining"));
    await waitFor(() => {
      expect(screen.getByTestId("mode-toggle-mining").getAttribute("title"))
        .toBe("Spin-offs from YouTube videos via Gemini");
    });
    expect((screen.getByTestId("mode-toggle-mining") as HTMLButtonElement).disabled).toBe(false);
  });

  it("a refused save shows the API's reason and keeps the toggles as they were", async () => {
    mockStrategies({ miningAvailable: true, strategies: ["curriculum", "trending", "mining"],
                     postStatus: 400, postBody: { error: "Gemini API key not set. The mining strategy…" } });
    render(<TopicsPage />);
    await waitFor(() => screen.getByTestId("mode-toggle-trending"));
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(screen.getByTestId("mode-toggle-trending"));
    await waitFor(() => {
      expect(screen.getByTestId("mode-error").textContent).toMatch(/Gemini API key not set/);
    });
    // Trending is still shown as on: nothing was stored.
    expect(screen.getByTestId("mode-toggle-trending").getAttribute("style")).toMatch(/var\(--cyan\)/);
  });
});

// TMDEV-170: the add-domain description is a multi-line scope statement,
// capped at 2000 characters counted as the API counts them (code points).
describe("TopicsPage — add-domain description", () => {
  afterEach(() => vi.restoreAllMocks());

  function postedProject(spy: ReturnType<typeof mockFetch>) {
    const call = spy.mock.calls.find(([u, i]) => u.toString().endsWith("/projects")
      && (i as RequestInit | undefined)?.method === "POST");
    return JSON.parse(String((call![1] as RequestInit).body));
  }

  it("is a textarea that can be dragged taller", async () => {
    mockFetch();
    render(<TopicsPage />);
    const field = await waitFor(() => screen.getByTestId("domain-description-input"));
    expect(field.tagName).toBe("TEXTAREA");
    expect((field as HTMLTextAreaElement).style.resize).toBe("vertical");
  });

  it("sends interior newlines intact and trims the ends", async () => {
    const spy = mockFetch();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const field = await waitFor(() => screen.getByTestId("domain-description-input"));
    fireEvent.change(field, { target: { value: "  Storage engines.\n\nNot: ORMs.\n  " } });
    fireEvent.change(screen.getByTestId("domain-name-input"), { target: { value: "DB internals" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(postedProject(spy).description).toBe("Storage engines.\n\nNot: ORMs."));
  });

  it("stops at 2000 characters and counts them", async () => {
    mockFetch();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const field = await waitFor(() => screen.getByTestId("domain-description-input")) as HTMLTextAreaElement;
    expect(screen.getByTestId("domain-description-count").textContent).toBe("0 / 2000");
    fireEvent.change(field, { target: { value: "x".repeat(2050) } });
    expect(field.value).toBe("x".repeat(2000));
    expect(screen.getByTestId("domain-description-count").textContent).toBe("2000 / 2000");
  });

  it("counts an emoji as one character, as the API does", async () => {
    mockFetch();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const field = await waitFor(() => screen.getByTestId("domain-description-input")) as HTMLTextAreaElement;
    fireEvent.change(field, { target: { value: "🐘".repeat(2000) } });
    expect(field.value).toBe("🐘".repeat(2000));
    expect(screen.getByTestId("domain-description-count").textContent).toBe("2000 / 2000");
  });
});

// TMDEV-207: a domain row is one summary line, and its defaults (now with an
// agent, model and effort) sit in a panel that "Edit defaults" opens.
describe("TopicsPage — domain summary and agent defaults", () => {
  afterEach(() => vi.restoreAllMocks());

  const AGENT = {
    binary: "/bin/x", run_path: "/w", install_scope: "user", effort: "high", is_default: false,
    weight: 1, verified_at: "", archived_at: null, created_at: "", updated_at: "",
  };
  const AGENTS = [
    { ...AGENT, id: "claude", name: "Claude Code", models: ["opus", "sonnet"], is_default: true },
    { ...AGENT, id: "codex", name: "Codex", models: ["gpt-a", "gpt-b"], effort: "medium" },
    { ...AGENT, id: "old", name: "Old Agent", models: ["m1"], archived_at: "2026-01-02T00:00:00Z" },
  ];
  const VOICES = [{ name: "Adam", voice_id: "a1", model_id: "eleven_v3" }];
  const DOMAIN = {
    id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: 1,
    status: "active", default_visual_style: "stick", default_voice_id: "a1",
    default_script_profile_id: "", default_mascot_id: "none",
    default_agent_id: "claude", default_agent_model: "sonnet", default_agent_effort: "max",
    topic_cap: 300, topic_count: 12, expired: false, created_at: "2026-01-01T00:00:00Z",
  };
  const PLAIN = {
    id: "plain-1", name: "Database internals", description: "", is_curriculum_seed: 0,
    status: "active", topic_cap: 100, topic_count: 3, created_at: "2026-01-01T00:00:00Z",
  };

  function mockDomains(domains: object[] = [DOMAIN, PLAIN], agents: object[] | null = AGENTS,
                       refusal: string | null = null) {
    return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      const urlStr = url.toString();
      if (urlStr.endsWith("/projects") && init?.method === "POST" && refusal) {
        return Promise.resolve({ ok: false, status: 400,
          json: () => Promise.resolve({ error: refusal }) } as Response);
      }
      if (urlStr.endsWith("/projects") && !init?.method) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(domains) } as Response);
      }
      if (urlStr.endsWith("/agents")) {
        return Promise.resolve({ ok: agents !== null, json: () => Promise.resolve(agents ?? {}) } as Response);
      }
      if (urlStr.endsWith("/visual-styles")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([
          { id: "stick", label: "Stick Explainer", experimental: false, needs: {} },
        ]) } as Response);
      }
      if (urlStr.includes("/settings")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          elevenlabs_voices: VOICES, elevenlabs_voice_id: "a1", openai_api_key: "" }) } as Response);
      }
      if (urlStr.includes("/research/strategies")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ strategies: [] }) } as Response);
      }
      if (urlStr.includes("/research/mining-sources")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ youtube_urls: [] }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });
  }

  function projectPosts(spy: ReturnType<typeof mockDomains>) {
    return spy.mock.calls
      .filter(([u, i]) => u.toString().endsWith("/projects") && (i as RequestInit | undefined)?.method === "POST")
      .map(([, i]) => JSON.parse(String((i as RequestInit).body)));
  }

  function options(testId: string) {
    return [...(screen.getByTestId(testId) as HTMLSelectElement).options];
  }

  it("keeps the pickers out of a closed row and says what the domain overrides", async () => {
    mockDomains();
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-seed-1").textContent)
      .toBe("AgentClaude Code · sonnet · max"));
    expect(screen.queryByTestId("domain-panel-seed-1")).toBeNull();
    expect(screen.queryByTestId("domain-voice-seed-1")).toBeNull();
    expect(screen.getByTestId("domain-chip-voice-seed-1").textContent).toBe("VoiceAdam");
    expect(screen.getByTestId("domain-chip-mascot-seed-1").textContent).toBe("MascotNone");
    expect(screen.queryByTestId("domain-chip-profile-seed-1")).toBeNull();
    expect(screen.getByTestId("domain-topics-seed-1").textContent).toBe("12 / 300 topics");
    // The name is cut with an ellipsis when it is long, so the whole of it is
    // on hover.
    expect(screen.getByTestId("domain-name-seed-1").getAttribute("title")).toBe("Linux internals");
  });

  it("says so when a domain overrides nothing", async () => {
    mockDomains();
    render(<TopicsPage />);
    const chips = await waitFor(() => screen.getByTestId("domain-chips-plain-1"));
    expect(chips.textContent).toBe("Install defaults for everything");
  });

  it("opens and closes a row's defaults, one row at a time", async () => {
    mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const edit = await waitFor(() => screen.getByTestId("domain-edit-seed-1"));
    expect(edit.textContent).toBe("Edit defaults");
    expect(edit.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(edit);
    expect(edit.textContent).toBe("Close");
    expect(edit.getAttribute("aria-expanded")).toBe("true");
    expect(edit.getAttribute("aria-controls")).toBe(screen.getByTestId("domain-panel-seed-1").id);
    // The other row stays shut, and this one's summary stays in place.
    expect(screen.queryByTestId("domain-panel-plain-1")).toBeNull();
    expect(screen.getByTestId("domain-chip-agent-seed-1")).toBeTruthy();
    fireEvent.click(edit);
    expect(screen.queryByTestId("domain-panel-seed-1")).toBeNull();
  });

  it("shows the domain's agent, model and effort, and offers only live agents", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults();
    await waitFor(() => expect((screen.getByTestId("domain-agent-seed-1") as HTMLSelectElement).value).toBe("claude"));
    expect(options("domain-agent-seed-1").map((o) => o.textContent))
      .toEqual(["Automatic (dealt by weight)", "Claude Code", "Codex"]);
    expect((screen.getByTestId("domain-agent-model-seed-1") as HTMLSelectElement).value).toBe("sonnet");
    expect(options("domain-agent-model-seed-1").map((o) => o.textContent))
      .toEqual(["opus (agent default)", "opus", "sonnet"]);
    expect((screen.getByTestId("domain-agent-effort-seed-1") as HTMLSelectElement).value).toBe("max");
    expect(options("domain-agent-effort-seed-1")[0].textContent).toBe("high (agent default)");
    expect(screen.getAllByLabelText("Agent")).toContain(screen.getByTestId("domain-agent-seed-1"));
  });

  it("disables the model under Automatic and leaves the effort usable", async () => {
    mockDomains();
    render(<TopicsPage />);
    await openDefaults("plain-1");
    const model = await waitFor(() => screen.getByTestId("domain-agent-model-plain-1") as HTMLSelectElement);
    expect(model.disabled).toBe(true);
    expect(options("domain-agent-model-plain-1").map((o) => o.textContent)).toEqual(["Agent default"]);
    expect((screen.getByTestId("domain-agent-effort-plain-1") as HTMLSelectElement).disabled).toBe(false);
    expect(options("domain-agent-effort-plain-1")[0].textContent).toBe("Agent default");
  });

  it("changing the agent clears the model and re-sends every other field", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const agent = await waitFor(() => screen.getByTestId("domain-agent-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(agent.value).toBe("claude"));
    fireEvent.change(agent, { target: { value: "codex" } });
    await waitFor(() => expect(projectPosts(spy)).toEqual([{
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "stick", default_voice_id: "a1",
      default_script_profile_id: "", default_mascot_id: "none",
      default_agent_id: "codex", default_agent_model: "", default_agent_effort: "max",
      topic_cap: 300 }]));
    // The row then offers the new agent's models and names its effort.
    await waitFor(() => expect(options("domain-agent-model-seed-1").map((o) => o.textContent))
      .toEqual(["gpt-a (agent default)", "gpt-a", "gpt-b"]));
    expect(options("domain-agent-effort-seed-1")[0].textContent).toBe("medium (agent default)");
    expect(screen.getByTestId("domain-chip-agent-seed-1").textContent).toBe("AgentCodex · max");
  });

  it("saves a model or an effort on its own", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const model = await waitFor(() => screen.getByTestId("domain-agent-model-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(model.value).toBe("sonnet"));
    fireEvent.change(model, { target: { value: "" } });
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    expect(projectPosts(spy)[0]).toMatchObject({
      default_agent_id: "claude", default_agent_model: "", default_agent_effort: "max" });
    fireEvent.change(screen.getByTestId("domain-agent-effort-seed-1"), { target: { value: "" } });
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(2));
    expect(projectPosts(spy)[1]).toMatchObject({
      default_agent_id: "claude", default_agent_model: "", default_agent_effort: "" });
  });

  // POST /projects replaces the whole row, so saves to one domain run one at
  // a time, each built from the row as the save before it left it. Sent side
  // by side, the second would carry the first field as it was before, and the
  // first pick would be lost with no error.
  function holdPosts(spy: ReturnType<typeof mockDomains>) {
    const answer = spy.getMockImplementation()!;
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    spy.mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
      if (url.toString().endsWith("/projects") && init?.method === "POST") await held;
      return answer(url, init);
    });
    return () => release();
  }

  it("sends a second change after the first is answered, and with it", async () => {
    const spy = mockDomains([PLAIN]);
    const release = holdPosts(spy);
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults("plain-1");
    await waitFor(() => expect(options("domain-agent-plain-1")).toHaveLength(3));
    fireEvent.change(screen.getByTestId("domain-agent-plain-1"), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId("domain-agent-effort-plain-1"), { target: { value: "low" } });
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    // Each write carries a time limit: with none, one that never answered
    // would hold every later change to the domain behind it.
    const first = spy.mock.calls.find(([u, i]) => u.toString().endsWith("/projects")
      && (i as RequestInit | undefined)?.method === "POST")![1] as RequestInit;
    expect(first.signal).toBeInstanceOf(AbortSignal);
    release();
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(2));
    expect(projectPosts(spy)[1]).toMatchObject({
      default_agent_id: "codex", default_agent_effort: "low" });
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-plain-1").textContent)
      .toBe("AgentCodex · low"));
  });

  it("a refused change does not ride on the change made after it", async () => {
    // Only the agent change is refused; the effort change behind it must go
    // out without it and be saved.
    const spy = mockDomains([PLAIN]);
    const answer = spy.getMockImplementation()!;
    spy.mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      if (url.toString().endsWith("/projects") && init?.method === "POST"
          && JSON.parse(String(init.body)).default_agent_id === "codex") {
        return Promise.resolve({ ok: false, status: 400,
          json: () => Promise.resolve({ error: "default_agent_id 'codex' is uninstalled" }) } as Response);
      }
      return answer(url, init);
    });
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults("plain-1");
    await waitFor(() => expect(options("domain-agent-plain-1")).toHaveLength(3));
    fireEvent.change(screen.getByTestId("domain-agent-plain-1"), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId("domain-agent-effort-plain-1"), { target: { value: "low" } });
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(2));
    expect(projectPosts(spy)[1]).toMatchObject({ default_agent_id: "", default_agent_effort: "low" });
    expect(alertSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-plain-1").textContent)
      .toBe("AgentAutomatic · low"));
  });

  it("reports a save that could not reach the API and keeps the row as it was", async () => {
    const spy = mockDomains([PLAIN]);
    const answer = spy.getMockImplementation()!;
    let down = true;
    spy.mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      if (down && url.toString().endsWith("/projects") && init?.method === "POST") {
        return Promise.reject(new TypeError("Failed to fetch"));
      }
      return answer(url, init);
    });
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults("plain-1");
    const effort = await waitFor(() => screen.getByTestId("domain-agent-effort-plain-1") as HTMLSelectElement);
    fireEvent.change(effort, { target: { value: "low" } });
    await waitFor(() => expect(screen.getByTestId("domain-save-status-plain-1").textContent)
      .toBe("Not saved: could not change this domain's agent's effort"));
    expect(alertSpy).not.toHaveBeenCalled();
    expect(effort.value).toBe("");
    expect(screen.queryByTestId("domain-chip-agent-plain-1")).toBeNull();
    // The next save is not stuck behind the failed one.
    down = false;
    fireEvent.change(effort, { target: { value: "max" } });
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-plain-1").textContent)
      .toBe("AgentAutomatic · max"));
  });

  // A change sent while a pause is unanswered would re-send status "active"
  // on the full replace and undo the pause.
  it("a change made behind a pause waits for it and keeps the domain paused", async () => {
    const spy = mockDomains([{ ...DOMAIN, default_agent_id: "", default_agent_model: "" }]);
    const answer = spy.getMockImplementation()!;
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    let statusCalls = 0;
    spy.mockImplementation(async (url: string | URL | Request, init?: RequestInit) => {
      if (url.toString().includes("/status")) {
        statusCalls += 1;
        await held;
        return { ok: true, json: () => Promise.resolve({}) } as Response;
      }
      return answer(url, init);
    });
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    fireEvent.click(screen.getByTestId("toggle-domain-seed-1"));
    fireEvent.change(screen.getByTestId("domain-agent-effort-seed-1"), { target: { value: "low" } });
    // The pause is out and unanswered; given time, the change still has not gone.
    await waitFor(() => expect(statusCalls).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(projectPosts(spy)).toHaveLength(0);
    release();
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    expect(projectPosts(spy)[0]).toMatchObject({ status: "paused", default_agent_effort: "low" });
  });

  it("a pause made behind a change waits for it", async () => {
    const spy = mockDomains([{ ...DOMAIN, default_agent_id: "", default_agent_model: "" }]);
    const release = holdPosts(spy);
    const statusCalls = () => spy.mock.calls.filter(([u]) => u.toString().includes("/status")).length;
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    fireEvent.change(screen.getByTestId("domain-agent-effort-seed-1"), { target: { value: "low" } });
    fireEvent.click(screen.getByTestId("toggle-domain-seed-1"));
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(statusCalls()).toBe(0);
    release();
    await waitFor(() => expect(statusCalls()).toBe(1));
    await waitFor(() => expect(screen.getByTestId("domain-status-seed-1").textContent).toBe("PAUSED"));
    expect(screen.getByTestId("domain-chip-agent-seed-1").textContent).toBe("AgentAutomatic · low");
  });

  it("a write that throws does not hold up the next one", async () => {
    const spy = mockDomains([PLAIN]);
    const answer = spy.getMockImplementation()!;
    let first = true;
    spy.mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      if (first && url.toString().endsWith("/projects") && init?.method === "POST") {
        first = false;
        // Reading this answer throws, so that write ends in an exception.
        return Promise.resolve({ ok: false, status: 500,
          json: () => { throw new Error("unreadable body"); } } as unknown as Response);
      }
      return answer(url, init);
    });
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults("plain-1");
    const effort = await waitFor(() => screen.getByTestId("domain-agent-effort-plain-1"));
    fireEvent.change(effort, { target: { value: "low" } });
    fireEvent.change(effort, { target: { value: "max" } });
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(2));
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-plain-1").textContent)
      .toBe("AgentAutomatic · max"));
  });

  it("puts a refused topic cap back in its field", async () => {
    mockDomains([PLAIN], AGENTS, "topic_cap must be a whole number from 25 to 750");
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults("plain-1");
    const cap = await waitFor(() => screen.getByTestId("domain-cap-plain-1") as HTMLInputElement);
    fireEvent.change(cap, { target: { value: "250" } });
    fireEvent.blur(cap);
    await waitFor(() => expect(screen.getByTestId("domain-save-status-plain-1").textContent)
      .toBe("Not saved: topic_cap must be a whole number from 25 to 750"));
    expect(alertSpy).not.toHaveBeenCalled();
    await waitFor(() => expect(cap.value).toBe("100"));
    expect(screen.getByTestId("domain-topics-plain-1").textContent).toBe("3 / 100 topics");
  });

  it("an effort alone reads as Automatic with that effort", async () => {
    mockDomains([{ ...PLAIN, default_agent_effort: "low" }]);
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-plain-1").textContent)
      .toBe("AgentAutomatic · low"));
  });

  it("keeps an agent since uninstalled, and a model since dropped, visible and unpickable", async () => {
    mockDomains([{ ...DOMAIN, default_agent_id: "old", default_agent_model: "m9" }]);
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-seed-1").textContent)
      .toBe("AgentOld Agent (uninstalled) · m9 · max"));
    await openDefaults();
    const agent = screen.getByTestId("domain-agent-seed-1") as HTMLSelectElement;
    expect(agent.value).toBe("old");
    const held = options("domain-agent-seed-1").find((o) => o.value === "old")!;
    expect(held.textContent).toBe("Old Agent (uninstalled)");
    expect(held.disabled).toBe(true);
    // No live agent to take a model from, so the model cannot be changed, but
    // the stored one still shows.
    const model = screen.getByTestId("domain-agent-model-seed-1") as HTMLSelectElement;
    expect(model.disabled).toBe(true);
    expect(model.value).toBe("m9");
    expect(options("domain-agent-model-seed-1").map((o) => o.textContent))
      .toEqual(["Agent default", "m9 (unavailable)"]);
  });

  it("another edit re-sends a stale agent and model untouched", async () => {
    const spy = mockDomains([{ ...DOMAIN, default_agent_id: "old", default_agent_model: "m9" }]);
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    fireEvent.change(screen.getByTestId("domain-voice-seed-1"), { target: { value: "" } });
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    expect(projectPosts(spy)[0]).toMatchObject({
      default_voice_id: "", default_agent_id: "old", default_agent_model: "m9",
      default_agent_effort: "max" });
  });

  it("shows a stored agent by its id, and offers only Automatic, when the agent list fails", async () => {
    mockDomains([DOMAIN], null);
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByTestId("domain-chip-agent-seed-1").textContent)
      .toBe("Agentclaude · sonnet · max"));
    await openDefaults();
    expect(options("domain-agent-seed-1").map((o) => [o.textContent, o.disabled]))
      .toEqual([["Automatic (dealt by weight)", false], ["claude", true]]);
    expect((screen.getByTestId("domain-agent-seed-1") as HTMLSelectElement).value).toBe("claude");
  });

  it("a refused change says why and leaves the domain as it was", async () => {
    mockDomains([DOMAIN], AGENTS, "default_agent_id 'codex' is uninstalled");
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await openDefaults();
    const agent = await waitFor(() => screen.getByTestId("domain-agent-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(agent.value).toBe("claude"));
    fireEvent.change(agent, { target: { value: "codex" } });
    await waitFor(() => expect(screen.getByTestId("domain-save-status-seed-1").textContent)
      .toBe("Not saved: default_agent_id 'codex' is uninstalled"));
    expect(alertSpy).not.toHaveBeenCalled();
    expect(agent.value).toBe("claude");
    expect((screen.getByTestId("domain-agent-model-seed-1") as HTMLSelectElement).value).toBe("sonnet");
  });

  it("the add-domain form sends the picked agent, model and effort", async () => {
    const spy = mockDomains([]);
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await waitFor(() => expect(options("domain-agent-select")).toHaveLength(3));
    expect((screen.getByTestId("domain-agent-model-select") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.change(screen.getByTestId("domain-agent-select"), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId("domain-agent-model-select"), { target: { value: "gpt-b" } });
    fireEvent.change(screen.getByTestId("domain-agent-effort-select"), { target: { value: "low" } });
    fireEvent.change(screen.getByPlaceholderText(/name/i), { target: { value: "New domain" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    expect(projectPosts(spy)[0]).toMatchObject({
      id: "new-domain", default_agent_id: "codex", default_agent_model: "gpt-b",
      default_agent_effort: "low" });
  });

  it("the add-domain form drops the model when the agent changes", async () => {
    const spy = mockDomains([]);
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await waitFor(() => expect(options("domain-agent-select")).toHaveLength(3));
    fireEvent.change(screen.getByTestId("domain-agent-select"), { target: { value: "codex" } });
    fireEvent.change(screen.getByTestId("domain-agent-model-select"), { target: { value: "gpt-b" } });
    fireEvent.change(screen.getByTestId("domain-agent-select"), { target: { value: "claude" } });
    expect((screen.getByTestId("domain-agent-model-select") as HTMLSelectElement).value).toBe("");
    fireEvent.change(screen.getByPlaceholderText(/name/i), { target: { value: "New domain" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(projectPosts(spy)).toHaveLength(1));
    expect(projectPosts(spy)[0]).toMatchObject({ default_agent_id: "claude", default_agent_model: "" });
  });
});
