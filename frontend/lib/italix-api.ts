import "server-only";

import type { DashboardOverview, OverviewResult } from "@/types/dashboard";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

function backendUrl(): string {
  return (process.env.ITALIX_API_URL || DEFAULT_API_URL).replace(/\/$/, "");
}

function looksLikeOverview(value: unknown): value is DashboardOverview {
  if (!value || typeof value !== "object") return false;
  const overview = value as Partial<DashboardOverview>;
  return (
    typeof overview.total_requests === "number" &&
    Array.isArray(overview.active_models) &&
    typeof overview.observed_usage === "object" &&
    typeof overview.registry === "object" &&
    typeof overview.costs === "object"
  );
}

export async function getDashboardOverview(): Promise<OverviewResult> {
  const token = process.env.ITALIX_VIEWER_TOKEN;
  if (!token) {
    return {
      ok: false,
      kind: "configuration",
      message: "The server-side ITALIX viewer token is not configured.",
    };
  }

  try {
    const response = await fetch(`${backendUrl()}/v1/dashboard/overview`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(5_000),
    });
    if (response.status === 401 || response.status === 403) {
      return {
        ok: false,
        kind: "authentication",
        message: "FastAPI rejected the server-side viewer credentials.",
      };
    }
    if (!response.ok) {
      return {
        ok: false,
        kind: "backend",
        message: `FastAPI returned HTTP ${response.status}.`,
      };
    }

    const overview: unknown = await response.json();
    if (!looksLikeOverview(overview)) {
      return {
        ok: false,
        kind: "response",
        message: "FastAPI returned an unexpected overview response.",
      };
    }
    return { ok: true, overview };
  } catch {
    return {
      ok: false,
      kind: "backend",
      message: "FastAPI is unavailable at the configured local address.",
    };
  }
}
