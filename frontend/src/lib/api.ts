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
  should_execute?: boolean;
  execution_status?: string;
  last_execution_at?: string;
  command_output?: string;
  final_answer?: string;
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
  final_answer: string;
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
