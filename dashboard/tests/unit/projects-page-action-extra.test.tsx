import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Captures the onAction the page hands the modal, so the test can invoke it
// exactly as the modal's Approve Topic button does — with a fourth `extra`
// argument — and then assert on the PATCH that results.
let captured: ((id: string, action: string, video: unknown, extra?: Record<string, unknown>) => void) | null = null;
// The voice roster the page hands the modal (TMDEV-127).
let capturedVoices: { voices?: unknown[]; defaultVoiceId?: string } = {};
let capturedPublishing: boolean | undefined;

vi.mock("@/components/VideoModal", () => ({
  VideoModal: (props: {
    onAction: (id: string, action: string, video: unknown, extra?: Record<string, unknown>) => void;
    voices?: unknown[]; defaultVoiceId?: string; publishingEnabled?: boolean;
  }) => {
    captured = props.onAction;
    capturedPublishing = props.publishingEnabled;
    capturedVoices = { voices: props.voices, defaultVoiceId: props.defaultVoiceId };
    return <div data-testid="modal-stub" />;
  },
}));
vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

import ProjectsPage from "@/app/projects/page";

const PROJECT = {
  id: "proj-1", name: "Domain", description: "d", is_curriculum_seed: 1,
  status: "active", created_at: "2026-01-01T00:00:00Z",
};
const VIDEO = {
  id: "vid-1", project_id: "proj-1", topic: "A topic", strategy: "curriculum",
  status: "TOPIC_PROPOSED", producibility_score: 7,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks(); captured = null; capturedVoices = {}; capturedPublishing = undefined;
});

describe("Projects page forwards the modal's frozen-at-approval picks", () => {
  it("sends visual_style in the same PATCH as the status change", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const u = url.toString();
      if (u.includes("/videos")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([VIDEO]) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([PROJECT]) } as Response);
    });

    render(<ProjectsPage />);
    fireEvent.click(await screen.findByText("Domain"));
    fireEvent.click(await screen.findByText("A topic"));
    await waitFor(() => expect(screen.getByTestId("modal-stub")).toBeTruthy());

    fetchSpy.mockClear();
    captured!("vid-1", "approve-topic", VIDEO, {
      script_profile_id: "prof-1", agent_model: "opus", agent_effort: "max",
      visual_style: "stick", voice_id: "v3voice",
    });

    await waitFor(() => {
      const patch = fetchSpy.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
      expect(patch).toBeTruthy();
      const body = JSON.parse((patch![1] as RequestInit).body as string);
      // The status change and the picks must travel together: every one of
      // these fields is refused once the video leaves TOPIC_PROPOSED, so a
      // pick that does not ride along can never be applied afterwards.
      expect(body.status).toBe("TOPIC_APPROVED");
      expect(body.visual_style).toBe("stick");
      expect(body.script_profile_id).toBe("prof-1");
      expect(body.agent_model).toBe("opus");
      expect(body.agent_effort).toBe("max");
      expect(body.voice_id).toBe("v3voice");
    });
  });

  it("hands the modal the voice roster from /settings", async () => {
    const roster = [{ name: "Expressive", voice_id: "v3voice", model_id: "eleven_v3" }];
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const u = url.toString();
      const body = u.includes("/settings")
        ? { elevenlabs_voices: roster, elevenlabs_voice_id: "v3voice" }
        : u.includes("/videos") ? [VIDEO] : [PROJECT];
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);
    });

    render(<ProjectsPage />);
    fireEvent.click(await screen.findByText("Domain"));
    fireEvent.click(await screen.findByText("A topic"));
    await waitFor(() => {
      expect(capturedVoices.voices).toEqual(roster);
      expect(capturedVoices.defaultVoiceId).toBe("v3voice");
    });
  });

  it("omits nothing and adds nothing when there is no extra", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const u = url.toString();
      if (u.includes("/videos")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([VIDEO]) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([PROJECT]) } as Response);
    });

    render(<ProjectsPage />);
    fireEvent.click(await screen.findByText("Domain"));
    fireEvent.click(await screen.findByText("A topic"));
    await waitFor(() => expect(screen.getByTestId("modal-stub")).toBeTruthy());

    fetchSpy.mockClear();
    captured!("vid-1", "reject-topic", VIDEO);

    await waitFor(() => {
      const patch = fetchSpy.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
      expect(patch).toBeTruthy();
      const body = JSON.parse((patch![1] as RequestInit).body as string);
      expect(body).toEqual({ status: "TOPIC_REJECTED", onlyIfCurrentStatus: "TOPIC_PROPOSED" });
    });
  });

  it("reports a refused action instead of treating it as done", async () => {
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        return Promise.resolve({
          ok: false, status: 409,
          json: () => Promise.resolve({ error: "Status precondition failed", current: "TOPIC_APPROVED" }),
        } as Response);
      }
      const u = url.toString();
      return Promise.resolve({ ok: true, json: () => Promise.resolve(u.includes("/videos") ? [VIDEO] : [PROJECT]) } as Response);
    });
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});

    render(<ProjectsPage />);
    fireEvent.click(await screen.findByText("Domain"));
    fireEvent.click(await screen.findByText("A topic"));
    await waitFor(() => expect(screen.getByTestId("modal-stub")).toBeTruthy());
    captured!("vid-1", "approve-topic", VIDEO, { agent_id: "codex" });

    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Status conflict — action already taken"));
  });
});

// The modal offers Publish… only when told publishing is on. Projects already
// fetched /settings for the voice roster but dropped this flag, so an approved
// video opened from here could not be published.
describe("Projects page passes the publishing flag to the modal", () => {
  async function openWith(settings: Record<string, unknown>) {
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const u = url.toString();
      if (u.endsWith("/settings")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(settings) } as Response);
      }
      if (u.includes("/videos")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ ...VIDEO, status: "VIDEO_APPROVED" }]) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([PROJECT]) } as Response);
    });
    render(<ProjectsPage />);
    fireEvent.click(await screen.findByText("Domain"));
    fireEvent.click(await screen.findByText("A topic"));
    await waitFor(() => expect(screen.getByTestId("modal-stub")).toBeTruthy());
  }

  it("on when /settings says so", async () => {
    await openWith({ publishing_enabled: true });
    await waitFor(() => expect(capturedPublishing).toBe(true));
  });

  it("off when publishing is disabled", async () => {
    await openWith({ publishing_enabled: false });
    await waitFor(() => expect(capturedPublishing).toBe(false));
  });
});
