import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import TopicsPage from "@/app/topics/page";

const MINING_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";

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

  it("reports a refused pause and leaves the domain as it was", async () => {
    mockDomains(false);
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    render(<TopicsPage />);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.click(await waitFor(() => screen.getByTestId("toggle-domain-seed-1")));
    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    expect(alertSpy.mock.calls[0][0]).toContain("not a curriculum seed");
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
    await waitFor(() => expect(illustratedOption("domain-style-seed-1").disabled).toBe(true));
    expect(illustratedOption("domain-style-seed-1").textContent).toMatch(/needs an OpenAI key/);
    expect(illustratedOption("domain-style-select").disabled).toBe(true);
  });

  it("offers it when a key is stored", async () => {
    mockWithKey("••••••••abcd");
    render(<TopicsPage />);
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
    const select = await waitFor(() => screen.getByTestId("domain-voice-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(select.value).toBe("a1"));
    expect([...select.options].map((o) => o.textContent)).toContain("Adam · eleven_v3");
  });

  it("changing the voice re-sends every other field", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const select = await waitFor(() => screen.getByTestId("domain-voice-seed-1"));
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("a1"));
    fireEvent.change(select, { target: { value: "r1" } });
    await waitFor(() => expect(postedProject(spy)).toEqual({
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "stick", default_voice_id: "r1",
      default_script_profile_id: "", topic_cap: 300 }));
  });

  it("changing the style keeps the default voice", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const select = await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    fireEvent.change(select, { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy).default_voice_id).toBe("a1"));
  });

  it("keeps a default voice that has left the roster visible as removed", async () => {
    mockDomains({ ...DOMAIN, default_voice_id: "gone" });
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByRole("option", { name: "gone (removed)" })).toBeTruthy());
  });

  it("the add-domain form sends the picked voice", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
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
    const select = await waitFor(() => screen.getByTestId("domain-profile-seed-1") as HTMLSelectElement);
    await waitFor(() => expect(select.value).toBe("p-ready"));
    fireEvent.change(select, { target: { value: "" } });
    await waitFor(() => expect(postedProject(spy)).toEqual({
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "stick", default_voice_id: "",
      default_script_profile_id: "", topic_cap: 300 }));
  });

  it("changing the style keeps the default profile", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    const select = await waitFor(() => screen.getByTestId("domain-style-seed-1"));
    fireEvent.change(select, { target: { value: "auto" } });
    await waitFor(() => expect(postedProject(spy).default_script_profile_id).toBe("p-ready"));
  });

  it("keeps a default that is no longer offered visible as unavailable", async () => {
    // A deleted profile is missing from the list, so there is no name; the id
    // is a UUID in a real install and must not be shown in its place.
    mockDomains({ ...DOMAIN, default_script_profile_id: "p-gone" });
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Unavailable profile" })).toBeTruthy());
  });

  // Profile names are user-supplied with no length limit, and a <select> is as
  // wide as its longest option: unbounded, one long name pushed the controls
  // after it off-screen, where overflow-x: hidden made them unreachable.
  it("caps the profile picker's width on the row and in the add form", async () => {
    mockDomains();
    render(<TopicsPage />);
    const row = await waitFor(() => screen.getByTestId("domain-profile-seed-1"));
    expect((row as HTMLSelectElement).style.maxWidth).toBe("220px");
    expect((screen.getByTestId("domain-profile-select") as HTMLSelectElement).style.maxWidth).toBe("220px");
  });

  it("names a held default that is listed but not READY", async () => {
    mockDomains({ ...DOMAIN, default_script_profile_id: "p-pending" });
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Still building (unavailable)" })).toBeTruthy());
  });

  it("the add-domain form sends the picked profile", async () => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getAllByRole("option", { name: "Fireship" }).length).toBe(2));
    fireEvent.change(screen.getByTestId("domain-profile-select"), { target: { value: "p-ready" } });
    fireEvent.change(screen.getByPlaceholderText(/name/i), { target: { value: "New domain" } });
    fireEvent.click(screen.getByTestId("add-domain-submit"));
    await waitFor(() => expect(postedProject(spy).default_script_profile_id).toBe("p-ready"));
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
    const input = await waitFor(() => screen.getByTestId("domain-cap-seed-1"));
    await waitFor(() => expect((input as HTMLInputElement).value).toBe("100"));
    fireEvent.change(input, { target: { value: "250" } });
    expect(projectPosts(spy)).toEqual([]); // nothing until the field is left
    fireEvent.blur(input);
    await waitFor(() => expect(projectPosts(spy)).toEqual([{
      id: "seed-1", name: "Linux internals", description: "kernels", is_curriculum_seed: true,
      status: "active", default_visual_style: "", default_voice_id: "",
      default_script_profile_id: "", topic_cap: 250 }]));
  });

  it.each(["24", "751", "abc", "100.5", ""])("reverts %j without saving", async (bad) => {
    const spy = mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
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
    await waitFor(() => expect(screen.getByTestId("domain-expired-seed-1").textContent).toBe("EXPIRED"));
  });

  // ACTIVE beside EXPIRED read as a contradiction: an active seed at its cap
  // generates nothing. A pause is still shown, since it is a second reason.
  it("hides ACTIVE on an expired seed but keeps PAUSED", async () => {
    mockDomains({ ...DOMAIN, topic_cap: 40, expired: true });
    const { unmount } = render(<TopicsPage />);
    await waitFor(() => screen.getByTestId("domain-expired-seed-1"));
    expect(screen.queryByTestId("domain-status-seed-1")).toBeNull();
    expect(screen.getByTestId("toggle-domain-seed-1")).toBeTruthy();
    unmount();
    vi.restoreAllMocks();

    mockDomains({ ...DOMAIN, status: "paused", topic_cap: 40, expired: true });
    render(<TopicsPage />);
    await waitFor(() => expect(screen.getByTestId("domain-status-seed-1").textContent).toBe("PAUSED"));
    expect(screen.getByTestId("domain-expired-seed-1")).toBeTruthy();
  });

  it("lowering the cap to the count expires the domain at once", async () => {
    mockDomains();
    const { fireEvent } = await import("@testing-library/react");
    render(<TopicsPage />);
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
