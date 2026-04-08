export type AlertRecommendation = {
  alert_id: string;
  alert_name: string;
  status: string;
  created_at?: string;
  target_host?: string;
  summary?: string;
  initial_ai_diagnosis?: string;
  initial_ai_reasoning?: string;
  post_command_ai_analysis?: string;
  diagnostic_command?: string;
  target_type?: string;
  should_execute?: boolean;
  execution_status?: string;
  last_execution_at?: string;
  command_output?: string;
  final_answer?: string;
  analysis_sections?: {
    root_cause?: string;
    evidence?: string;
    impact?: string;
    resolution?: string;
    remediation_steps?: string[];
    validation_steps?: string[];
    remediation_command?: string;
    remediation_target_host?: string;
    remediation_why?: string;
    remediation_requires_approval?: boolean;
  };
  remediation_command?: string;
  remediation_target_host?: string;
  remediation_why?: string;
  remediation_requires_approval?: boolean;
  remediation_execution_status?: string;
  remediation_last_execution_at?: string;
  remediation_output?: string;
  post_remediation_ai_analysis?: string;
  agent_success?: boolean;
  incident_key?: string;
  incident_title?: string;
  blast_radius?: string[];
  depends_on?: string[];
  predicted_risk_score?: number | null;
};

export type GraphNode = {
  id: string;
  label: string;
  service: string;
  kind: string;
  status: string;
  role: string;
  metrics?: Record<string, unknown>;
  prediction?: Record<string, unknown>;
  depends_on?: string[];
  dependents?: string[];
  ai_insight?: string;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
  relationship: string;
};

export type GraphPayload = {
  graph_type: string;
  key: string;
  title: string;
  summary: string;
  status: string;
  root_node_id?: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  blast_radius: string[];
  evidence?: Record<string, unknown>;
};

export type ApplicationComponent = {
  application: string;
  service: string;
  title: string;
  target_host: string;
  kind: string;
  status: string;
  metrics: {
    up?: number | null;
    request_rate?: number | null;
    latency_p95_seconds?: number | null;
    error_rate?: number | null;
  };
  recent_alerts?: Array<{
    alert_name: string;
    status: string;
    summary?: string;
  }>;
  depends_on?: string[];
  blast_radius?: string[];
  dependency_chain?: string[];
  ai_insight?: string;
  prediction?: {
    risk_score?: number | null;
    prediction_status?: string;
    predicted_window_minutes?: number;
  };
  business_impact?: {
    currency?: string;
    timezone?: string;
    business_peak_window?: string;
    avg_order_value?: number;
    baseline_transactions_per_day?: number;
    window_days?: number;
    daily?: Array<{
      date: string;
      transactions: number;
      error_rate: number;
      failed_transactions: number;
      estimated_revenue_lost: number;
      business_hours_window?: string;
      business_hours_transactions?: number;
      business_hours_failed_transactions?: number;
      off_hours_transactions?: number;
    }>;
    current_day?: {
      date: string;
      transactions: number;
      error_rate: number;
      failed_transactions: number;
      estimated_revenue_lost: number;
      business_hours_window?: string;
      business_hours_transactions?: number;
      business_hours_failed_transactions?: number;
      off_hours_transactions?: number;
    };
    trailing_7d_failed_transactions?: number;
    trailing_7d_revenue_lost?: number;
    impact_level?: string;
  };
};

export type ApplicationOverview = {
  application: string;
  title: string;
  description: string;
  status: string;
  active_alert_count: number;
  ai_insight: string;
  blast_radius: string[];
  components: ApplicationComponent[];
  prediction?: {
    risk_score?: number | null;
    prediction_status?: string;
    predicted_window_minutes?: number;
  };
  business_impact?: {
    currency?: string;
    timezone?: string;
    business_peak_window?: string;
    current_business_hours_transactions?: number;
    current_off_hours_transactions?: number;
    current_estimated_revenue_lost?: number;
    current_day_failed_transactions?: number;
    trailing_7d_revenue_lost?: number;
    trailing_7d_failed_transactions?: number;
    impact_level?: string;
  };
};

export type ChatMessage = {
  id: number;
  role: string;
  content: string;
  metadata?: Record<string, unknown>;
  created_at: string;
};

export type ChatSessionSummary = {
  session_id: string;
  title: string;
  updated_at: string;
  created_at: string;
  last_message_preview: string;
  message_count: number;
};

export type ChatSessionInit = {
  session_id: string;
  title: string;
  messages: ChatMessage[];
  user: string;
};

export type ChatReply = {
  session_id?: string;
  question?: string;
  answer?: string;
  follow_up_questions?: string[];
  suggested_command?: string;
  target_host?: string;
  is_destructive?: boolean;
  preview_text?: string;
  generated_sql?: string;
  error?: string;
  detail?: string;
};

export type DocumentRecord = {
  id: number;
  fileName: string;
  fileUrl: string;
  status: string;
  statusLabel: string;
  deletePath: string;
};

export type PredictionRow = {
  application: string;
  service: string;
  status: string;
  risk_score: number;
  incident_probability: number;
  predicted_window_minutes: number;
  model_version: string;
  features: Record<string, unknown>;
  blast_radius: string[];
  explanation: string;
  created_at: string;
};

export type IncidentSummary = {
  incident_key: string;
  application: string;
  title: string;
  status: string;
  severity: string;
  primary_service: string;
  target_host: string;
  summary: string;
  reasoning: string;
  blast_radius: string[];
  updated_at: string;
  opened_at: string;
  resolved_at?: string | null;
  alerts: Array<{
    alert_name: string;
    status: string;
    target_host: string;
    service_name: string;
    last_seen_at: string;
  }>;
  timeline_count: number;
  prediction?: {
    risk_score: number;
    incident_probability: number;
    predicted_window_minutes: number;
    explanation: string;
  } | null;
  business_impact?: {
    currency?: string;
    avg_order_value?: number;
    total_transactions?: number;
    failed_transactions?: number;
    revenue_lost?: number;
    revenue_per_hour?: number;
    duration_hours?: number;
    impact_level?: string;
    data_source?: string;
  } | null;
};

export type IncidentTimeline = IncidentSummary & {
  linked_recommendation?: AlertRecommendation | null;
  timeline: Array<{
    event_type: string;
    title: string;
    detail: string;
    payload: Record<string, unknown>;
    created_at: string;
  }>;
};

export type CommandExecutionResult = {
  execution_type?: string;
  final_answer: string;
  analysis_sections?: {
    root_cause?: string;
    evidence?: string;
    impact?: string;
    resolution?: string;
    remediation_steps?: string[];
    validation_steps?: string[];
    remediation_command?: string;
    remediation_target_host?: string;
    remediation_why?: string;
    remediation_requires_approval?: boolean;
  };
  command_output: string;
  agent_success: boolean;
  agent_response?: Record<string, unknown> | string;
  last_execution_at: string;
  execution_status: string;
};

type RecentAlertsResponse = {
  count: number;
  results: AlertRecommendation[];
};

type ApplicationOverviewResponse = {
  count: number;
  results: ApplicationOverview[];
};

type PredictionsResponse = {
  count: number;
  results: PredictionRow[];
};

type IncidentsResponse = {
  count: number;
  results: IncidentSummary[];
};

type SessionListResponse = {
  count: number;
  results: ChatSessionSummary[];
};

function getCsrfToken(): string {
  const cookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrftoken="));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  const contentType = response.headers.get("content-type") || "";
  if (
    response.redirected &&
    response.url.includes("/genai/login/")
  ) {
    window.location.href = response.url;
    throw new Error("Authentication required");
  }

  if (contentType.includes("text/html") && response.url.includes("/genai/login/")) {
    window.location.href = response.url;
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function fetchRecentAlerts(): Promise<AlertRecommendation[]> {
  const payload = await fetchJson<RecentAlertsResponse>("/genai/alerts/recent/");
  return payload.results || [];
}

export async function fetchApplicationGraph(applicationKey: string): Promise<GraphPayload> {
  return fetchJson<GraphPayload>(`/genai/applications/${applicationKey}/graph/`);
}

export async function fetchIncidentGraph(incidentKey: string): Promise<GraphPayload> {
  return fetchJson<GraphPayload>(`/genai/incidents/${incidentKey}/graph/`);
}

export async function fetchApplicationOverview(): Promise<ApplicationOverview[]> {
  const payload = await fetchJson<ApplicationOverviewResponse>("/genai/applications/overview/");
  return payload.results || [];
}

export async function fetchRecentPredictions(): Promise<PredictionRow[]> {
  const payload = await fetchJson<PredictionsResponse>("/genai/predictions/recent/");
  return payload.results || [];
}

export async function fetchRecentIncidents(): Promise<IncidentSummary[]> {
  const payload = await fetchJson<IncidentsResponse>("/genai/incidents/recent/");
  return payload.results || [];
}

export async function fetchIncidentTimeline(incidentKey: string): Promise<IncidentTimeline> {
  return fetchJson<IncidentTimeline>(`/genai/incidents/${incidentKey}/timeline/`);
}

export async function fetchChatSessions(): Promise<ChatSessionSummary[]> {
  const payload = await fetchJson<SessionListResponse>("/genai/session/list/");
  return payload.results || [];
}

export async function initChatSession(sessionId?: string): Promise<ChatSessionInit> {
  const response = await fetch("/genai/session/init/", {
    method: sessionId ? "POST" : "GET",
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(sessionId ? { "Content-Type": "application/json" } : {}),
    },
    body: sessionId ? JSON.stringify({ session_id: sessionId }) : undefined,
  });

  if (!response.ok) {
    throw new Error(`Session init failed: ${response.status}`);
  }

  return response.json() as Promise<ChatSessionInit>;
}

export async function resetChatSession(sessionId?: string): Promise<ChatSessionInit> {
  const response = await fetch("/genai/session/reset/", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId }),
  });

  if (!response.ok) {
    throw new Error(`Session reset failed: ${response.status}`);
  }

  return response.json() as Promise<ChatSessionInit>;
}

export async function sendChatMessage(payload: { session_id?: string; question: string; use_documents?: boolean }): Promise<ChatReply> {
  const response = await fetch("/genai/chat/", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const contentType = response.headers.get("content-type") || "";
  if (
    response.redirected &&
    response.url.includes("/genai/login/")
  ) {
    window.location.href = response.url;
    throw new Error("Authentication required");
  }

  if (contentType.includes("text/html") && response.url.includes("/genai/login/")) {
    window.location.href = response.url;
    throw new Error("Authentication required");
  }

  if (!contentType.includes("application/json")) {
    const text = await response.text();
    throw new Error(text || `Chat failed: ${response.status}`);
  }

  const body = (await response.json()) as ChatReply;
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Chat failed: ${response.status}`);
  }
  return body;
}

export async function fetchDocuments(): Promise<DocumentRecord[]> {
  const response = await fetch("/genai/console/", {
    credentials: "include",
    headers: {
      Accept: "text/html",
    },
  });

  if (!response.ok) {
    throw new Error(`Document console failed: ${response.status}`);
  }

  const html = await response.text();
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const rows = Array.from(doc.querySelectorAll("#document-list tbody tr"));

  return rows
    .map((row) => {
      const link = row.querySelector("td a");
      const badge = row.querySelector(".badge");
      const form = row.querySelector("form[action]");
      const action = form?.getAttribute("action") || "";
      const idMatch = action.match(/\/delete\/(\d+)\//);

      if (!link || !badge || !action || !idMatch) {
        return null;
      }

      const statusClass = badge.className.toLowerCase();
      const status = statusClass.includes("success")
        ? "success"
        : statusClass.includes("danger")
          ? "failed"
          : "pending";

      return {
        id: Number(idMatch[1]),
        fileName: link.textContent?.trim() || "Unknown file",
        fileUrl: link.getAttribute("href") || "#",
        status,
        statusLabel: badge.textContent?.trim() || "Unknown",
        deletePath: action,
      } satisfies DocumentRecord;
    })
    .filter((item): item is DocumentRecord => Boolean(item));
}

export async function uploadDocument(file: File): Promise<void> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/genai/console/", {
    method: "POST",
    credentials: "include",
    headers: {
      "X-CSRFToken": getCsrfToken(),
    },
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }
}

export async function deleteDocument(deletePath: string): Promise<void> {
  const response = await fetch(deletePath, {
    method: "POST",
    credentials: "include",
    headers: {
      "X-CSRFToken": getCsrfToken(),
    },
  });

  if (!response.ok) {
    throw new Error(`Delete failed: ${response.status}`);
  }
}

export async function executeDiagnosticCommand(payload: {
  alert_id?: string;
  command: string;
  original_question: string;
  target_host: string;
  execution_type?: "diagnostic" | "remediation";
}): Promise<CommandExecutionResult> {
  const response = await fetch("/genai/execute_command/", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });

  const body = (await response.json()) as CommandExecutionResult & { error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Command execution failed: ${response.status}`);
  }

  return body;
}

export type FleetComponentStatus = {
  name: string;
  status: string;
};

export type FleetTarget = {
  target_id: string;
  name: string;
  target_type: string;
  environment: string;
  hostname: string;
  status: string;
  last_heartbeat: string;
  profile_name: string;
  collector_status: string;
  discovered_service_count: number;
  components: FleetComponentStatus[];
};

export type TelemetryProfile = {
  slug: string;
  name: string;
  summary: string;
  default_for_target: string;
  components: string[];
  capabilities: string[];
};

export type EnrollmentBlueprint = {
  target_type: string;
  install_mode: string;
  token_preview: string;
  install_command: string;
  components: string[];
  next_steps: string[];
};

export type OnboardingRequest = {
  onboarding_id: string;
  name: string;
  hostname: string;
  ssh_user: string;
  ssh_port: number;
  target_type: string;
  profile_slug: string;
  status: string;
  connectivity_status: string;
  connectivity_message: string;
  last_connectivity_check_at?: string | null;
  last_install_at?: string | null;
  install_message: string;
  target_id?: string | null;
  pem_file_name?: string;
};

type FleetTargetsResponse = {
  count: number;
  results: FleetTarget[];
};

type FleetProfilesResponse = {
  count: number;
  results: TelemetryProfile[];
};

type FleetOnboardingResponse = {
  count: number;
  results: OnboardingRequest[];
};

export async function fetchFleetTargets(): Promise<FleetTarget[]> {
  const payload = await fetchJson<FleetTargetsResponse>("/genai/fleet/targets/");
  return payload.results || [];
}

export async function fetchTelemetryProfiles(): Promise<TelemetryProfile[]> {
  const payload = await fetchJson<FleetProfilesResponse>("/genai/fleet/profiles/");
  return payload.results || [];
}

export async function fetchEnrollmentBlueprint(targetType: string, profileName: string): Promise<EnrollmentBlueprint> {
  const query = new URLSearchParams({ target_type: targetType, profile: profileName }).toString();
  return fetchJson<EnrollmentBlueprint>(`/genai/fleet/enroll-blueprint/?${query}`);
}

export async function fetchOnboardingRequests(): Promise<OnboardingRequest[]> {
  const payload = await fetchJson<FleetOnboardingResponse>("/genai/fleet/onboarding/");
  return payload.results || [];
}

export async function createOnboardingRequest(payload: {
  name: string;
  hostname: string;
  ssh_user: string;
  ssh_port: number;
  target_type: string;
  profile: string;
  pem_file: File;
}): Promise<OnboardingRequest> {
  const formData = new FormData();
  formData.append("name", payload.name);
  formData.append("hostname", payload.hostname);
  formData.append("ssh_user", payload.ssh_user);
  formData.append("ssh_port", String(payload.ssh_port));
  formData.append("target_type", payload.target_type);
  formData.append("profile", payload.profile);
  formData.append("pem_file", payload.pem_file);

  const response = await fetch("/genai/fleet/onboarding/", {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: formData,
  });

  const body = (await response.json()) as OnboardingRequest & { error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Onboarding request failed: ${response.status}`);
  }

  return body;
}

export async function testOnboardingConnectivity(onboardingId: string): Promise<OnboardingRequest> {
  const response = await fetch(`/genai/fleet/onboarding/${onboardingId}/test-connectivity/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  });

  const body = (await response.json()) as OnboardingRequest & { error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Connectivity test failed: ${response.status}`);
  }

  return body;
}

export async function installOnboardingTarget(onboardingId: string): Promise<OnboardingRequest & { install_command?: string }> {
  const response = await fetch(`/genai/fleet/onboarding/${onboardingId}/install/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  });

  const body = (await response.json()) as OnboardingRequest & { install_command?: string; error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Remote install failed: ${response.status}`);
  }

  return body;
}

export async function updateOnboardingRequest(onboardingId: string, payload: {
  name: string;
  hostname: string;
  ssh_user: string;
  ssh_port: number;
  target_type: string;
  profile: string;
  pem_file?: File | null;
}): Promise<OnboardingRequest> {
  const formData = new FormData();
  formData.append("name", payload.name);
  formData.append("hostname", payload.hostname);
  formData.append("ssh_user", payload.ssh_user);
  formData.append("ssh_port", String(payload.ssh_port));
  formData.append("target_type", payload.target_type);
  formData.append("profile", payload.profile);
  if (payload.pem_file) {
    formData.append("pem_file", payload.pem_file);
  }

  const response = await fetch(`/genai/fleet/onboarding/${onboardingId}/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: formData,
  });

  const body = (await response.json()) as OnboardingRequest & { error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Update failed: ${response.status}`);
  }
  return body;
}

export async function deleteOnboardingRequest(onboardingId: string): Promise<void> {
  const response = await fetch(`/genai/fleet/onboarding/${onboardingId}/`, {
    method: "DELETE",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `Delete failed: ${response.status}`);
  }
}

export async function fetchCacheStats(): Promise<Record<string, any>> {
  const payload = await fetchJson<{ status: string; data: Record<string, any> }>("/genai/cache/stats/");
  return payload.data;
}

export async function purgeCache(prefix?: string): Promise<{ deleted: number }> {
  const response = await fetch("/genai/cache/purge/", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    credentials: "include",
    body: JSON.stringify(prefix ? { prefix } : {}),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `Purge failed: ${response.status}`);
  }
  return response.json();
}
