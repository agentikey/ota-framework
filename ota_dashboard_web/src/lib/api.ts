// Thin, hand-written fetch client.
// The OpenAPI-generated client lives under src/api/generated/ after
// `pnpm gen-api`. Until then this minimal wrapper keeps the UI moving.

export interface ApprovalQueueItem {
  id: string;
  routine_id: string;
  routine_run_id: string;
  gate_id: string;
  status: string;
  summary: string;
  kind: string | null;
  payload: Record<string, unknown>;
  similarity_key: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface ApprovalQueueListResponse {
  items: ApprovalQueueItem[];
}

export interface AuditEvent {
  event_id: string;
  event_type: string;
  severity: string;
  timestamp: string;
  trace_id: string | null;
  routine_run_id: string | null;
  payload: Record<string, unknown> | null;
  principal_id: string;
  principal_type: string;
}

export interface AuditScanResponse {
  events: AuditEvent[];
  next_cursor: string | null;
}

export interface WhyEntry {
  timestamp: string;
  kind: string;
  description: string;
  payload: Record<string, unknown>;
}

export interface WhyResponse {
  email_id: string;
  entries: WhyEntry[];
}

export interface FleetEntry {
  deployment_id: string;
  edition: string;
  framework_version: string;
  routines: string[];
}

export interface FleetResponse {
  entries: FleetEntry[];
}

export interface KnobValue {
  name: string;
  type: string;
  value: unknown;
  default: unknown;
  description: string;
}

export interface RoutineKnobsResponse {
  routine_id: string;
  knobs: KnobValue[];
}

export interface CriticalBannerResponse {
  active: boolean;
  severity: "info" | "warn" | "error" | "critical" | null;
  title: string | null;
  description: string | null;
  raised_at: string | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status} ${path}: ${text.slice(0, 200)}`);
  }
  return (await response.json()) as T;
}

export const api = {
  approvals: {
    list: (routineId?: string) =>
      request<ApprovalQueueListResponse>(
        `/api/v1/approvals${routineId ? `?routine_id=${encodeURIComponent(routineId)}` : ""}`,
      ),
    recent: (limit = 50) =>
      request<ApprovalQueueListResponse>(`/api/v1/approvals/recent?limit=${limit}`),
    decide: (
      id: string,
      action: "approve" | "reject" | "edit_and_approve" | "remember_and_approve",
      edits?: Record<string, unknown>,
    ) =>
      request<{ id: string; status: string }>(
        `/api/v1/approvals/${encodeURIComponent(id)}/decide`,
        {
          method: "POST",
          body: JSON.stringify({ action, edits: edits ?? null }),
        },
      ),
  },
  audit: {
    scan: (q?: string) =>
      request<AuditScanResponse>(
        `/api/v1/audit${q ? `?q=${encodeURIComponent(q)}` : ""}`,
      ),
    byTrace: (traceId: string) =>
      request<AuditScanResponse>(`/api/v1/audit/trace/${encodeURIComponent(traceId)}`),
  },
  why: (emailId: string) =>
    request<WhyResponse>(`/api/v1/why/${encodeURIComponent(emailId)}`),
  fleet: () => request<FleetResponse>("/api/v1/fleet"),
  knobs: {
    get: (routineId: string) =>
      request<RoutineKnobsResponse>(
        `/api/v1/routines/${encodeURIComponent(routineId)}/knobs`,
      ),
    update: (routineId: string, knobs: Record<string, unknown>) =>
      request<{ routine_id: string; applied: Record<string, unknown> }>(
        `/api/v1/routines/${encodeURIComponent(routineId)}/knobs`,
        { method: "POST", body: JSON.stringify({ knobs }) },
      ),
  },
  banner: {
    get: () => request<CriticalBannerResponse>("/api/v1/notifications/banner"),
    clear: () =>
      request<CriticalBannerResponse>("/api/v1/notifications/banner", {
        method: "DELETE",
      }),
  },
};
