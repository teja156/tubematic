"use client";

import { useCallback, useEffect, useState } from "react";
import type { LogsResponse, LogRecord } from "@/lib/types";
import { SectionLabel } from "@/components/SectionLabel";
import { LogList } from "@/components/LogList";

function apiFetch(path: string, init?: RequestInit) {
  return fetch(`/api/proxy${path}`, { cache: "no-store", ...init });
}

const mono = { fontFamily: "var(--mono)" } as const;

const LIMITS = [50, 200, 500, 1000];

const control = {
  ...mono, fontSize: 11, background: "var(--panel)", color: "var(--fg, inherit)",
  border: "1px solid var(--border)", padding: "5px 8px",
} as const;

export default function LogsPage() {
  const [records, setRecords] = useState<LogRecord[]>([]);
  // Populated from the API's own response rather than hardcoded here, so the
  // filter lists cannot drift from the server's allowlist.
  const [services, setServices] = useState<string[]>([]);
  const [levels, setLevels] = useState<string[]>([]);

  const [service, setService] = useState("");
  const [level, setLevel] = useState("");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(200);

  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    setRefreshing(true);
    const params = new URLSearchParams();
    if (service) params.set("service", service);
    if (level) params.set("level", level);
    if (search.trim()) params.set("q", search.trim());
    params.set("limit", String(limit));

    return apiFetch(`/logs?${params.toString()}`)
      .then(async (r) => {
        const data: Partial<LogsResponse> & { error?: string } = await r.json();
        if (!r.ok) {
          setError(data?.error ?? "Could not load logs.");
          setRecords([]);
        } else {
          setError("");
          setRecords(Array.isArray(data.records) ? data.records : []);
          if (data.services) setServices(data.services);
          if (data.levels) setLevels(data.levels);
        }
      })
      .catch(() => setError("Could not reach the pipeline API."))
      .finally(() => { setLoaded(true); setRefreshing(false); });
  }, [service, level, search, limit]);

  // Filters re-query on change; there is deliberately no polling or live tail.
  useEffect(() => { load(); }, [load]);

  return (
    <>
      <SectionLabel label="Logs" count={loaded && !error ? `${records.length} Records` : undefined} />

      <p style={{ ...mono, fontSize: 11, color: "var(--mute)", marginBottom: 20, maxWidth: 720 }}>
        Structured logs from the API, MCP server, render worker and cron poller. Level filters by
        minimum severity, so <em>warning</em> also shows errors. How long these are kept is the
        <em> Keep logs for</em> setting on the Settings page.
      </p>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 18 }}>
        <select
          aria-label="Service" data-testid="filter-service" style={control}
          value={service} onChange={(e) => setService(e.target.value)}
        >
          <option value="">All services</option>
          {services.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          aria-label="Level" data-testid="filter-level" style={control}
          value={level} onChange={(e) => setLevel(e.target.value)}
        >
          <option value="">All levels</option>
          {levels.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>

        <input
          aria-label="Search" data-testid="filter-search" style={{ ...control, minWidth: 220 }}
          placeholder="Search…" value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <select
          aria-label="Limit" data-testid="filter-limit" style={control}
          value={limit} onChange={(e) => setLimit(Number(e.target.value))}
        >
          {LIMITS.map((n) => <option key={n} value={n}>{n} rows</option>)}
        </select>

        <button
          type="button" data-testid="logs-refresh" style={{ ...control, cursor: "pointer" }}
          onClick={() => load()} disabled={refreshing}
        >
          {refreshing ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div
          data-testid="logs-error"
          style={{
            ...mono, fontSize: 11, color: "var(--amber)", border: "1px solid var(--border)",
            background: "var(--panel)", padding: "12px 14px", marginBottom: 20, maxWidth: 640,
          }}
        >
          {error}
        </div>
      )}

      {loaded && !error && (
        <LogList
          records={records}
          emptyLabel={
            "No log records match these filters. A service that has not started since logging was "
            + "added, or one whose /logs mount is missing, writes only to container stdout."
          }
        />
      )}
    </>
  );
}
