export type TypedAction = {
  action: string;
  target?: string;
  target_host?: string;
  service?: string;
  reason?: string;
  requires_approval?: boolean;
  command?: string;
  validation_plan?: string[];
  metadata?: Record<string, unknown>;
};

export type WorkflowStage = {
  stage: string;
  status: string;
  summary: string;
  details?: Record<string, unknown>;
};

export type InvestigationToolCall = {
  invocation_id?: string;
  server_name: string;
  tool_name: string;
  status: string;
  latency_ms: number;
  created_at: string;
  request_json?: Record<string, unknown>;
  response_json?: Record<string, unknown>;
  error_detail?: string;
};

export type InvestigationLiveStep = {
  step_key: string;
  title: string;
  status: "queued" | "running" | "completed" | "skipped" | string;
  summary: string;
  findings: string[];
  inference: string;
  tool_names: string[];
  tool_call_count: number;
  latest_activity_at?: string;
  technical_details?: Record<string, unknown>;
};

export type InvestigationLiveSummary = {
  active_step_key?: string;
  current_title?: string;
  current_summary?: string;
  current_inference?: string;
  completed_steps?: number;
  total_steps?: number;
  stream_state?: "live" | "final" | string;
};

export type InvestigationRunSummary = {
  run_id: string;
  status: string;
  question: string;
  application: string;
  service: string;
  target_host: string;
  incident_key?: string;
  incident_title?: string;
  session_id?: string;
  tool_call_count: number;
  current_stage: string;
  confidence_score: number;
  planner: Record<string, unknown>;
  workflow: WorkflowStage[];
  evidence_bundle: Record<string, unknown>;
  missing_evidence: string[];
  contradicting_evidence: string[];
  confidence_assessment?: Record<string, unknown>;
  contradiction_assessment?: Record<string, unknown>;
  evidence_gap_assessment?: Record<string, unknown>;
  created_at?: string;
  updated_at: string;
  completed_at?: string | null;
  tool_calls: InvestigationToolCall[];
  live_steps?: InvestigationLiveStep[];
  live_summary?: InvestigationLiveSummary;
  stream_url?: string;
};

export type InvestigationRunDetail = InvestigationRunSummary & {
  route?: string;
  evidence_summary?: Record<string, unknown>;
  hypotheses?: Array<Record<string, unknown>>;
};

export type AlertRecommendation = {
  alert_id: string;
  alert_name: string;
  status: string;
  created_at?: string;
  target_host?: string;
  decision_policy?: string;
  confidence_reason?: string;
  confidence_assessment?: {
    level?: "high" | "medium" | "low";
    score?: number;
    posture?: string;
    summary?: string;
  };
  hard_evidence?: string[];
  missing_evidence?: string[];
  contradiction_assessment?: {
    severity?: string;
    count?: number;
    blocks_dependency_claim?: boolean;
    summary?: string;
  };
  evidence_gap_assessment?: {
    status?: string;
    count?: number;
    summary?: string;
  };
  evidence_assessment?: {
    safe_action?: string;
    confidence_reason?: string;
    hard_evidence?: string[];
    missing_evidence?: string[];
    dependency_hard_evidence?: Record<string, string[]>;
    best_dependency_target?: string;
    confidence_assessment?: Record<string, unknown>;
    contradiction_assessment?: Record<string, unknown>;
    evidence_gap_assessment?: Record<string, unknown>;
  };
  labels?: Record<string, string>;
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
  diagnostic_typed_action?: TypedAction;
  remediation_typed_action?: TypedAction;
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
    remediation_typed_action?: TypedAction;
  };
  remediation_command?: string;
  remediation_target_host?: string;
  remediation_why?: string;
  remediation_requires_approval?: boolean;
  demo_command_bypass?: boolean;
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
  latest_investigation?: InvestigationProjection | null;
};

export type InvestigationProjection = {
  alert_id?: string;
  run_id?: string;
  status?: string;
  route?: string;
  question?: string;
  application?: string;
  service?: string;
  target_host?: string;
  summary?: string;
  incident_key?: string;
  incident_title?: string;
  current_stage?: string;
  confidence_score?: number;
  workflow?: WorkflowStage[];
  evidence_bundle?: Record<string, unknown>;
  evidence_summary?: Record<string, unknown>;
  missing_evidence?: string[];
  contradicting_evidence?: string[];
  confidence_assessment?: Record<string, unknown>;
  contradiction_assessment?: Record<string, unknown>;
  evidence_gap_assessment?: Record<string, unknown>;
  evidence_assessment?: Record<string, unknown>;
  updated_at?: string;
  decision_policy?: string;
  confidence_reason?: string;
  hard_evidence?: string[];
  initial_ai_diagnosis?: string;
  initial_ai_reasoning?: string;
  post_command_ai_analysis?: string;
  final_answer?: string;
  analysis_sections?: AlertRecommendation["analysis_sections"];
  diagnostic_command?: string;
  command_output?: string;
  target_type?: string;
  execution_status?: string;
  last_execution_at?: string;
  should_execute?: boolean;
  remediation_command?: string;
  remediation_target_host?: string;
  remediation_why?: string;
  remediation_requires_approval?: boolean;
  diagnostic_typed_action?: TypedAction;
  remediation_typed_action?: TypedAction;
  remediation_execution_status?: string;
  remediation_last_execution_at?: string;
  remediation_output?: string;
  post_remediation_ai_analysis?: string;
  agent_success?: boolean;
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

export type CodeContextGraphNode = {
  id: string;
  label: string;
  type: string;
  size: number;
  risk: string;
  metadata: Record<string, unknown>;
};

export type CodeContextGraphLink = {
  source: string;
  target: string;
  label: string;
  weight: number;
};

export type CodeContextRepositoryOption = {
  name: string;
  application_names: string[];
  indexed_at?: string | null;
  index_status: string;
};

export type CodeContextGraphPayload = {
  repository: {
    name: string;
    local_path: string;
    default_branch: string;
    index_status: string;
    last_indexed_at?: string | null;
  } | null;
  application: string;
  nodes: CodeContextGraphNode[];
  links: CodeContextGraphLink[];
  repository_options: CodeContextRepositoryOption[];
  summary: {
    service_count: number;
    route_count: number;
    span_count: number;
    change_count: number;
    relation_count: number;
  };
};

export type IntegrationBindingPayload = {
  binding_id?: string;
  environment: string;
  application_name: string;
  target_id?: string;
  target_name?: string;
  priority: number;
  enabled: boolean;
};

export type IntegrationCredentialPayload = {
  credential_id?: string;
  secret_ref: string;
  credential_metadata: Record<string, unknown>;
  rotation_status?: string;
};

export type IntegrationConfig = {
  integration_id?: string;
  name: string;
  integration_type: string;
  category: string;
  endpoint_url: string;
  auth_mode: string;
  enabled: boolean;
  metadata_json: Record<string, unknown>;
  health_status?: string;
  last_health_check_at?: string | null;
  credential: IntegrationCredentialPayload;
  bindings: IntegrationBindingPayload[];
  latest_health_check?: {
    check_id?: string;
    status?: string;
    latency_ms?: number;
    message?: string;
    details_json?: Record<string, unknown>;
    checked_at?: string;
  };
  capabilities?: string[];
  created_at?: string;
  updated_at?: string;
  exists?: boolean;
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
  confidence?: "high" | "medium" | "low";
  confidence_reason?: string;
  confidence_assessment?: {
    level?: "high" | "medium" | "low";
    score?: number;
    posture?: string;
    hard_evidence_count?: number;
    supporting_evidence_count?: number;
    contradicting_evidence_count?: number;
    missing_evidence_count?: number;
    summary?: string;
  };
  hard_evidence?: string[];
  missing_evidence?: string[];
  decision_policy?: string;
  supporting_evidence?: string[];
  contradicting_evidence?: string[];
  contradiction_assessment?: {
    severity?: string;
    count?: number;
    blocks_dependency_claim?: boolean;
    summary?: string;
  };
  evidence_gap_assessment?: {
    status?: string;
    count?: number;
    summary?: string;
  };
  next_verification_step?: string;
  follow_up_questions?: string[];
  workflow?: WorkflowStage[];
  suggested_command?: string;
  target_host?: string;
  business_impact?: Record<string, unknown>;
  code_context?: Record<string, unknown>;
  retrieval?: Record<string, unknown>;
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
  incident_number?: string;
  application: string;
  title: string;
  status: string;
  severity: string;
  priority: string;
  primary_service: string;
  target_host: string;
  summary: string;
  reasoning: string;
  blast_radius: string[];
  updated_at: string;
  opened_at: string;
  resolved_at?: string | null;
  is_deleted?: boolean;
  deleted_at?: string | null;
  alerts: Array<{
    alert_name: string;
    status: string;
    target_host: string;
    service_name: string;
    last_seen_at: string;
  }>;
  related_incidents?: Array<{
    incident_key: string;
    incident_number?: string;
    title: string;
    score: number;
    reasons: string[];
    direction?: string;
  }>;
  external_tickets?: Array<{
    ticket_id: string;
    integration_type: string;
    integration_name: string;
    external_id: string;
    external_key: string;
    external_url: string;
    status: string;
    message: string;
    created_at: string;
    updated_at: string;
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
  sla?: {
    priority: string;
    response_due_at: string | null;
    resolution_due_at: string | null;
    response_acknowledged_at: string | null;
    response_remaining_minutes: number | null;
    resolution_remaining_minutes: number | null;
    response_breached: boolean;
    resolution_breached: boolean;
    breached: boolean;
  } | null;
};

export type AlertNoiseStats = {
  window_minutes: number;
  raw_notifications: number;
  unique_lifecycles: number;
  duplicate_notifications: number;
  suppressed_lifecycles: number;
  incidents_created_or_linked: number;
  noise_reduction_ratio: number;
};

export type AlertSuppressionRule = {
  rule_type: "suppression";
  id: string;
  name: string;
  enabled: boolean;
  alert_name: string;
  service_name: string;
  target_host: string;
  environment: string;
  reason: string;
  expires_at?: string | null;
  created_by_username?: string;
  created_at: string;
  updated_at: string;
};

export type MaintenanceWindowRule = {
  rule_type: "maintenance";
  id: string;
  name: string;
  enabled: boolean;
  service_name: string;
  target_host: string;
  environment: string;
  reason: string;
  starts_at: string;
  ends_at: string;
  created_by_username?: string;
  created_at: string;
  updated_at: string;
};

export type AlertNoiseRulesPayload = {
  stats: AlertNoiseStats;
  suppressions: AlertSuppressionRule[];
  maintenance_windows: MaintenanceWindowRule[];
};

export type AlertNoiseRuleInput = {
  rule_type: "suppression" | "maintenance";
  name: string;
  enabled?: boolean;
  alert_name?: string;
  service_name?: string;
  target_host?: string;
  environment?: string;
  reason?: string;
  expires_at?: string;
  starts_at?: string;
  ends_at?: string;
};

export type IncidentTimeline = IncidentSummary & {
  linked_recommendation?: AlertRecommendation | null;
  latest_investigation?: InvestigationProjection | null;
  deep_dive?: AlertRecommendation | null;
  latest_runbook?: RunbookResult & { created_at: string } | null;
  latest_narrative?: { narrative: string; created_at: string | null } | null;
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
  typed_action?: TypedAction;
  typed_action_summary?: string;
  workflow?: WorkflowStage[];
  ranking?: Record<string, unknown>;
  behavior_version?: Record<string, unknown>;
  execution_intent_id?: string;
  idempotency_key?: string;
  rollback_metadata?: Record<string, unknown>;
  replay_scores?: Record<string, unknown>;
  policy_decision?: Record<string, unknown>;
  demo_command_bypass?: boolean;
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
    remediation_typed_action?: TypedAction;
  };
  command_output: string;
  agent_success: boolean;
  agent_response?: Record<string, unknown> | string;
  last_execution_at: string;
  execution_status: string;
  verification?: {
    status?: string;
    reason?: string;
    execution_type?: string;
    command?: string;
    baseline_issue_score?: number;
    post_issue_score?: number;
    issue_score_delta?: number;
    improvement_detected?: boolean;
    verification_loop_state?: string;
    requires_follow_up?: boolean;
    recommended_next_step?: string;
    baseline_evidence?: Record<string, unknown>;
    post_evidence?: Record<string, unknown>;
    post_context_summary?: Record<string, unknown>;
  };
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

type InvestigationsResponse = {
  count: number;
  results: InvestigationRunSummary[];
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

export type TenantMembership = {
  membership_id: string;
  tenant_id: string;
  name: string;
  slug: string;
  domain: string;
  role: string;
  permissions: string[];
  user?: {
    id: number;
    username: string;
    email: string;
    is_active: boolean;
  };
  is_active?: boolean;
};

export type TenantContextPayload = {
  current: TenantMembership;
  tenants: TenantMembership[];
};

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    headers: {
      Accept: "application/json",
    },
  });

  const contentType = response.headers.get("content-type") || "";
  // Django's @login_required redirects to /genai/login/ for unauthenticated users.
  // Surface that as a clean error — the React route guard handles redirecting to /login.
  if (
    (response.redirected && response.url.includes("/genai/login/")) ||
    (contentType.includes("text/html") && response.url.includes("/genai/login/"))
  ) {
    throw new Error("Authentication required");
  }

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function readApiJson<T>(response: Response, fallbackMessage: string): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const body = await response.text().catch(() => "");
    const backendUnavailable =
      response.status >= 500 ||
      body.trimStart().startsWith("<!DOCTYPE html") ||
      body.trimStart().startsWith("<html");

    if (backendUnavailable) {
      throw new Error("Backend is unavailable. Wait for the API service to finish starting, then try again.");
    }

    throw new Error(fallbackMessage);
  }

  return response.json() as Promise<T>;
}

export interface SessionUser {
  id: number;
  username: string;
  email: string;
  is_superuser: boolean;
  is_staff: boolean;
}

export async function fetchSession(): Promise<{ authenticated: boolean; user?: SessionUser }> {
  const response = await fetch("/genai/auth/session/", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (response.status === 401) return { authenticated: false };
  if (!response.ok) throw new Error(`Session check failed: ${response.status}`);
  return readApiJson<{ authenticated: boolean; user?: SessionUser }>(response, "Unable to load session.");
}

export async function loginUser(username: string, password: string): Promise<{ status: string; user: SessionUser }> {
  const response = await fetch("/genai/auth/login/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify({ username, password }),
  });
  const body = await readApiJson<{ status: string; user: SessionUser; error?: string }>(response, "Login failed.");
  if (!response.ok) throw new Error(body.error === "invalid_credentials" ? "Invalid username or password." : body.error || "Login failed.");
  return body;
}

export async function logoutUser(): Promise<void> {
  const response = await fetch("/genai/auth/logout/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
  });
  if (!response.ok) {
    await readApiJson<{ error?: string }>(response, "Logout failed.");
    throw new Error(`Logout failed: ${response.status}`);
  }
}

/* ---------- Admin (super-admin only, cross-tenant) ---------- */

export interface AdminTenant {
  tenant_id: string;
  name: string;
  slug: string;
  domain: string;
  is_active: boolean;
  created_at: string;
  member_count: number;
}

export interface AdminUserMembership {
  membership_id: string;
  tenant_id: string;
  tenant_name: string;
  role: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  is_staff: boolean;
  memberships: AdminUserMembership[];
  date_joined: string;
}

export interface AdminMembership {
  membership_id: string;
  tenant_id: string;
  name: string;
  slug: string;
  domain: string;
  role: string;
  permissions: string[];
  extra_permissions: string[];
  user: { id: number; username: string; email: string; is_active: boolean; is_superuser?: boolean };
  is_active: boolean;
}

export interface AdminAuditEvent {
  event_id: string;
  tenant_id: string;
  tenant_name: string;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

async function adminJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
  if (response.status === 401) throw new Error("authentication_required");
  if (response.status === 403) throw new Error("superuser_required");
  if (!response.ok) throw new Error(`Admin request failed: ${response.status}`);
  return response.json();
}

async function adminSend<T>(url: string, method: "POST" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const payload = (await response.json()) as T & { error?: string };
  if (!response.ok) throw new Error(payload.error || `Admin ${method} failed: ${response.status}`);
  return payload;
}

export const adminApi = {
  listTenants: () => adminJson<{ count: number; results: AdminTenant[] }>("/genai/admin/tenants/"),
  createTenant: (input: { name: string; slug?: string; domain?: string }) =>
    adminSend<{ status: string; tenant: AdminTenant }>("/genai/admin/tenants/", "POST", input),
  updateTenant: (tenantId: string, input: { name?: string; domain?: string; is_active?: boolean }) =>
    adminSend<{ status: string; tenant: AdminTenant }>(`/genai/admin/tenants/${encodeURIComponent(tenantId)}/`, "PATCH", input),

  listUsers: () => adminJson<{ count: number; results: AdminUser[] }>("/genai/admin/users/"),
  createUser: (input: { username: string; email?: string; password: string; is_superuser?: boolean }) =>
    adminSend<{ status: string; user: AdminUser }>("/genai/admin/users/", "POST", input),
  updateUser: (userId: number, input: { email?: string; is_active?: boolean; is_superuser?: boolean; password?: string }) =>
    adminSend<{ status: string; user: AdminUser }>(`/genai/admin/users/${userId}/`, "PATCH", input),

  createMembership: (input: { tenant_id: string; user_id: number; role: string }) =>
    adminSend<{ status: string; member: AdminMembership }>("/genai/admin/memberships/", "POST", input),
  updateMembership: (membershipId: string, input: { role?: string; is_active?: boolean; extra_permissions?: string[] }) =>
    adminSend<{ status: string; member: AdminMembership }>(`/genai/admin/memberships/${encodeURIComponent(membershipId)}/`, "PATCH", input),
  disableMembership: (membershipId: string) =>
    adminSend<{ status: string; member: AdminMembership }>(`/genai/admin/memberships/${encodeURIComponent(membershipId)}/`, "DELETE"),
  fetchMembership: (membershipId: string) =>
    adminJson<AdminMembership>(`/genai/admin/memberships/${encodeURIComponent(membershipId)}/`),

  permissionCatalog: () =>
    adminJson<{ count: number; permissions: string[]; grouped: Record<string, string[]> }>("/genai/admin/permissions/catalog/"),

  auditLog: (params: { limit?: number; tenant_id?: string; action?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.limit) search.set("limit", String(params.limit));
    if (params.tenant_id) search.set("tenant_id", params.tenant_id);
    if (params.action) search.set("action", params.action);
    const suffix = search.toString();
    return adminJson<{ count: number; results: AdminAuditEvent[] }>(`/genai/admin/audit/${suffix ? `?${suffix}` : ""}`);
  },
};

export async function fetchCurrentTenant(): Promise<TenantContextPayload> {
  return fetchJson<TenantContextPayload>("/genai/tenants/current/");
}

export async function selectTenant(tenantId: string): Promise<{ current: TenantMembership }> {
  const response = await fetch("/genai/tenants/select/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify({ tenant_id: tenantId }),
  });
  const body = (await response.json()) as { current: TenantMembership; error?: string };
  if (!response.ok) throw new Error(body.error || `Tenant switch failed: ${response.status}`);
  return body;
}

export async function fetchTenantMembers(): Promise<TenantMembership[]> {
  const payload = await fetchJson<{ count: number; results: TenantMembership[] }>("/genai/tenants/members/");
  return payload.results || [];
}

export async function createTenantMember(input: { username?: string; email?: string; role: string }): Promise<{ status: string; member: TenantMembership }> {
  const response = await fetch("/genai/tenants/members/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify(input),
  });
  const body = (await response.json()) as { status: string; member: TenantMembership; error?: string };
  if (!response.ok) throw new Error(body.error || `Member create failed: ${response.status}`);
  return body;
}

export async function updateTenantMember(membershipId: string, input: { role?: string; is_active?: boolean }): Promise<{ status: string; member: TenantMembership }> {
  const response = await fetch(`/genai/tenants/members/${encodeURIComponent(membershipId)}/`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify(input),
  });
  const body = (await response.json()) as { status: string; member: TenantMembership; error?: string };
  if (!response.ok) throw new Error(body.error || `Member update failed: ${response.status}`);
  return body;
}

export async function disableTenantMember(membershipId: string): Promise<{ status: string; member: TenantMembership }> {
  const response = await fetch(`/genai/tenants/members/${encodeURIComponent(membershipId)}/`, {
    method: "DELETE",
    credentials: "include",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
  });
  const body = (await response.json()) as { status: string; member: TenantMembership; error?: string };
  if (!response.ok) throw new Error(body.error || `Member disable failed: ${response.status}`);
  return body;
}

export async function fetchRecentAlerts(): Promise<AlertRecommendation[]> {
  const payload = await fetchJson<RecentAlertsResponse>("/genai/alerts/recent/");
  return payload.results || [];
}

export async function closeAlerts(alertIds: string[], reason?: string): Promise<{ status: string; closed_count: number; events_updated: number; closed_alert_ids: string[]; closed_at: string }> {
  const response = await fetch("/genai/alerts/close/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify({ alert_ids: alertIds, reason: reason || "" }),
  });
  const body = (await response.json()) as { status: string; closed_count: number; events_updated: number; closed_alert_ids: string[]; closed_at: string; error?: string };
  if (!response.ok) throw new Error(body.error || `Alert close failed: ${response.status}`);
  return body;
}

export async function fetchAlertNoiseRules(): Promise<AlertNoiseRulesPayload> {
  return fetchJson<AlertNoiseRulesPayload>("/genai/alerts/noise/rules/");
}

export async function createAlertNoiseRule(input: AlertNoiseRuleInput): Promise<{ status: string; rule: AlertSuppressionRule | MaintenanceWindowRule }> {
  const response = await fetch("/genai/alerts/noise/rules/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify(input),
  });
  const body = (await response.json()) as { status: string; rule: AlertSuppressionRule | MaintenanceWindowRule; error?: string };
  if (!response.ok) throw new Error(body.error || `Noise rule creation failed: ${response.status}`);
  return body;
}

export async function disableAlertNoiseRule(ruleType: "suppression" | "maintenance", ruleId: string): Promise<{ status: string; rule: AlertSuppressionRule | MaintenanceWindowRule }> {
  const response = await fetch(`/genai/alerts/noise/rules/${encodeURIComponent(ruleType)}/${encodeURIComponent(ruleId)}/delete/`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify({}),
  });
  const body = (await response.json()) as { status: string; rule: AlertSuppressionRule | MaintenanceWindowRule; error?: string };
  if (!response.ok) throw new Error(body.error || `Noise rule disable failed: ${response.status}`);
  return body;
}

export async function fetchApplicationGraph(applicationKey: string): Promise<GraphPayload> {
  return fetchJson<GraphPayload>(`/genai/applications/${applicationKey}/graph/`);
}

export async function fetchIncidentGraph(incidentKey: string): Promise<GraphPayload> {
  return fetchJson<GraphPayload>(`/genai/incidents/${incidentKey}/graph/`);
}

export async function fetchCodeContextGraph(params?: {
  application?: string;
  repository?: string;
}): Promise<CodeContextGraphPayload> {
  const query = new URLSearchParams();
  if (params?.application) query.set("application", params.application);
  if (params?.repository) query.set("repository", params.repository);
  const suffix = query.toString() ? `?${query}` : "";
  return fetchJson<CodeContextGraphPayload>(`/genai/code-context/graph/${suffix}`);
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

export async function deleteIncident(incidentKey: string, reason = ""): Promise<{ status: string; incident_key: string; incident_number?: string }> {
  const response = await fetch(`/genai/incidents/${encodeURIComponent(incidentKey)}/delete/`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify({ reason }),
  });
  const body = (await response.json()) as { status: string; incident_key: string; incident_number?: string; error?: string };
  if (!response.ok) throw new Error(body.error || `Incident archive failed: ${response.status}`);
  return body;
}

export async function fetchInvestigationRuns(params?: {
  incident_key?: string;
  session_id?: string;
  target_host?: string;
}): Promise<InvestigationRunSummary[]> {
  const query = new URLSearchParams();
  if (params?.incident_key) query.set("incident_key", params.incident_key);
  if (params?.session_id) query.set("session_id", params.session_id);
  if (params?.target_host) query.set("target_host", params.target_host);
  const suffix = query.toString() ? `?${query}` : "";
  const payload = await fetchJson<InvestigationsResponse>(`/genai/investigations/recent/${suffix}`);
  return payload.results || [];
}

export async function fetchInvestigationRun(runId: string): Promise<InvestigationRunDetail> {
  return fetchJson<InvestigationRunDetail>(`/genai/investigations/${runId}/`);
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

export async function sendChatMessage(payload: {
  session_id?: string;
  question: string;
  use_documents?: boolean;
  application?: string;
  service?: string;
  incident?: string;
}): Promise<ChatReply> {
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

export type BlastRadiusEstimate = {
  affected_services: string[];
  affected_count: number;
  risk_score: number;
  risk_label: "low" | "medium" | "high" | "critical";
  environment: string;
  is_protected_env: boolean;
  is_critical_service: boolean;
  reasons: string[];
  requires_approval: boolean;
  action_type: string;
  service: string;
};

export async function executeDiagnosticCommand(payload: {
  alert_id?: string;
  command?: string;
  original_question: string;
  target_host?: string;
  execution_type?: "diagnostic" | "remediation";
  typed_action?: TypedAction;
  dry_run?: boolean;
  approval_token?: string;
  approval_reason?: string;
  idempotency_key?: string;
  rollback_metadata?: Record<string, unknown>;
  break_glass?: boolean;
  break_glass_reason?: string;
  requires_verification?: boolean;
}): Promise<CommandExecutionResult> {
  const send = async (requestPayload: typeof payload) =>
    fetch("/genai/execute_command/", {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(requestPayload),
    });

  let response = await send(payload);
  let body = (await response.json()) as CommandExecutionResult & {
    error?: string;
    detail?: string;
    approval_required?: boolean;
    approval_token?: string;
    estimated_blast_radius?: BlastRadiusEstimate;
    execution_intent_id?: string;
  };

  // Surface approval flow — do NOT auto-approve; return info for the UI to handle
  if (response.status === 409 && body.approval_required) {
    return body as unknown as CommandExecutionResult;
  }

  if (!response.ok) {
    throw new Error(body.detail || body.error || `Command execution failed: ${response.status}`);
  }

  return body;
}

export async function approveExecutionIntent(
  intentId: string,
  payload: { approval_token: string; approval_reason: string }
): Promise<{ approved: boolean; intent_id: string; status: string; approver_identity: string }> {
  const response = await fetch(`/genai/executions/${intentId}/approve/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || `Approval failed: ${response.status}`);
  }
  return body;
}

export async function rollbackExecutionIntent(
  intentId: string,
  payload: { reason?: string }
): Promise<{
  rollback_initiated: boolean;
  rollback_intent_id: string;
  rollback_command: string;
  rollback_action: TypedAction;
  status: string;
  requires_approval: boolean;
}> {
  const response = await fetch(`/genai/executions/${intentId}/rollback/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || `Rollback failed: ${response.status}`);
  }
  return body;
}

export async function verifyExecutionIntent(
  intentId: string,
  payload: { outcome: string; notes?: string }
): Promise<{ verified: boolean; intent_id: string; status: string; verification_outcome: string }> {
  const response = await fetch(`/genai/executions/${intentId}/verify/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || `Verification failed: ${response.status}`);
  }
  return body;
}

export type FleetComponentStatus = {
  name: string;
  status: string;
};

export type FleetRuntimeSummary = {
  container_runtime: string;
  docker_available: boolean;
  docker_container_count: number;
  kubernetes_available: boolean;
  kubernetes_workload_count: number;
  host_service_count: number;
  host_application_service_count: number;
  host_support_service_count: number;
  docker_error: string;
};

export type FleetWorkloadPreview = {
  service_name: string;
  process_name: string;
  port?: number | null;
  status: string;
  runtime: string;
  image: string;
  container_name: string;
  category?: string;
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
  runtime_summary: FleetRuntimeSummary;
  workload_preview: FleetWorkloadPreview[];
  components: FleetComponentStatus[];
};

export type FleetDiscoveredService = FleetWorkloadPreview & {
  metadata_json?: Record<string, unknown>;
  owner?: Record<string, unknown>;
};

export type FleetPolicyProfile = {
  slug: string;
  name: string;
  description: string;
  target_type: string;
  runtime_type: string;
  allow_service_status: boolean;
  allow_service_restart: boolean;
  allow_docker_logs: boolean;
  allow_docker_restart: boolean;
  allow_journal_logs: boolean;
  allow_file_logs: boolean;
  allow_db_diagnostics: boolean;
  allow_db_changes: boolean;
  allow_process_kill: boolean;
  requires_approval_for_restart: boolean;
  requires_approval_for_write_actions: boolean;
  sudo_mode: string;
  allowed_command_patterns: string[];
  metadata_json: Record<string, unknown>;
};

export type FleetPolicyAssignment = {
  policy_profile?: FleetPolicyProfile;
  override_json: Record<string, unknown>;
  config_version: number;
  last_applied_at?: string | null;
  last_apply_status: string;
};

export type FleetTargetRuntimeProfile = {
  profile_id: string;
  role: string;
  environment: string;
  runtime_type: string;
  hostname: string;
  os_family: string;
  docker_available: boolean;
  systemd_available: boolean;
  primary_restart_mode: string;
  notes: string;
  metadata_json: Record<string, unknown>;
};

export type FleetTargetServiceBinding = {
  binding_id: string;
  service_name: string;
  service_kind: string;
  systemd_unit: string;
  container_name: string;
  process_name: string;
  port?: number | null;
  is_primary: boolean;
  restart_command_template: string;
  status_command_template: string;
  metadata_json: Record<string, unknown>;
};

export type FleetTargetLogSource = {
  log_source_id: string;
  service_binding_id?: string | null;
  source_type: string;
  journal_unit: string;
  file_path: string;
  container_name: string;
  stream_family: string;
  parser_name: string;
  include_patterns: string[];
  exclude_patterns: string[];
  shipper_type: string;
  parser_type: string;
  is_primary: boolean;
  metadata_json: Record<string, unknown>;
};

export type FleetTargetLogIngestionProfile = {
  shipper_type: string;
  stream_family: string;
  opensearch_pipeline: string;
  record_metadata_json: Record<string, unknown>;
  config_version: number;
  last_applied_at?: string | null;
  last_apply_status: string;
};

export type FleetTargetConfigPayload = {
  target: {
    target_id: string;
    name: string;
    target_type: string;
    environment: string;
    hostname: string;
  };
  config_version: {
    policy: number;
    log_ingestion: number;
  };
  runtime_profile?: FleetTargetRuntimeProfile;
  policy_assignment?: FleetPolicyAssignment;
  service_bindings: FleetTargetServiceBinding[];
  log_sources: FleetTargetLogSource[];
  log_ingestion_profile?: FleetTargetLogIngestionProfile;
  generated_configs: {
    fluent_bit: {
      enabled: boolean;
      path_hint: string;
      config: string;
    };
  };
  generated_at: string;
};

export type FleetTargetDetail = FleetTarget & {
  ip_address: string;
  os_name: string;
  os_version: string;
  metadata_json: Record<string, unknown>;
  docker_workloads: FleetDiscoveredService[];
  kubernetes_workloads: FleetDiscoveredService[];
  host_services: FleetDiscoveredService[];
  host_application_services: FleetDiscoveredService[];
  host_support_services: FleetDiscoveredService[];
  policy_assignment?: FleetPolicyAssignment;
  runtime_profile?: FleetTargetRuntimeProfile;
  service_bindings: FleetTargetServiceBinding[];
  log_sources: FleetTargetLogSource[];
  log_ingestion_profile?: FleetTargetLogIngestionProfile;
  recent_execution_history: Array<{
    intent_id: string;
    execution_type: string;
    action_type: string;
    service: string;
    target_host: string;
    status: string;
    dry_run: boolean;
    requires_approval: boolean;
    command: string;
    created_at?: string | null;
    completed_at?: string | null;
    typed_action_summary?: string;
    final_answer?: string;
  }>;
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
  control_plane_ready: boolean;
  missing_requirements: string[];
  warnings: string[];
};

export type OnboardingRequest = {
  onboarding_id: string;
  name: string;
  hostname: string;
  target_role: string;
  runtime_type: string;
  target_environment: string;
  ssh_user: string;
  ssh_port: number;
  target_type: string;
  profile_slug: string;
  policy_profile_slug: string;
  policy_profile_name: string;
  status: string;
  connectivity_status: string;
  connectivity_message: string;
  last_connectivity_check_at?: string | null;
  last_install_at?: string | null;
  install_message: string;
  target_id?: string | null;
  pem_file_name?: string;
  notes: string;
  config_json: Record<string, unknown>;
};

type FleetTargetsResponse = {
  count: number;
  results: FleetTarget[];
};

type FleetProfilesResponse = {
  count: number;
  results: TelemetryProfile[];
};

type FleetPolicyProfilesResponse = {
  count: number;
  results: FleetPolicyProfile[];
};

type FleetOnboardingResponse = {
  count: number;
  results: OnboardingRequest[];
};

export async function fetchFleetTargets(): Promise<FleetTarget[]> {
  const payload = await fetchJson<FleetTargetsResponse>("/genai/fleet/targets/");
  return payload.results || [];
}

export async function fetchFleetTargetDetail(targetId: string): Promise<FleetTargetDetail> {
  return fetchJson<FleetTargetDetail>(`/genai/fleet/targets/${encodeURIComponent(targetId)}/`);
}

export async function fetchFleetTargetConfig(targetId: string): Promise<FleetTargetConfigPayload> {
  return fetchJson<FleetTargetConfigPayload>(`/genai/fleet/targets/${encodeURIComponent(targetId)}/config/`);
}

export async function updateFleetTargetConfig(
  targetId: string,
  payload: {
    runtime_profile: Record<string, unknown>;
    policy_profile_slug?: string;
    policy_override_json?: Record<string, unknown>;
    service_bindings: Record<string, unknown>[];
    log_sources: Record<string, unknown>[];
    log_ingestion_profile: Record<string, unknown>;
  },
): Promise<FleetTargetConfigPayload> {
  const response = await fetch(`/genai/fleet/targets/${encodeURIComponent(targetId)}/config/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const body = (await response.json()) as FleetTargetConfigPayload & { error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Target config update failed: ${response.status}`);
  }
  return body;
}

export async function applyFleetTargetConfig(targetId: string): Promise<{
  status: string;
  requested_at: string;
  config_payload: FleetTargetConfigPayload;
}> {
  const response = await fetch(`/genai/fleet/targets/${encodeURIComponent(targetId)}/config/apply/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  });
  const body = (await response.json()) as {
    status: string;
    requested_at: string;
    config_payload: FleetTargetConfigPayload;
    error?: string;
    detail?: string;
  };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Target config apply failed: ${response.status}`);
  }
  return body;
}

export async function fetchTelemetryProfiles(targetType?: string): Promise<TelemetryProfile[]> {
  const query = targetType ? `?${new URLSearchParams({ target_type: targetType }).toString()}` : "";
  const payload = await fetchJson<FleetProfilesResponse>(`/genai/fleet/profiles/${query}`);
  return payload.results || [];
}

export async function fetchPolicyProfiles(targetType?: string, runtimeType?: string): Promise<FleetPolicyProfile[]> {
  const query = new URLSearchParams();
  if (targetType) query.set("target_type", targetType);
  if (runtimeType) query.set("runtime_type", runtimeType);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const payload = await fetchJson<FleetPolicyProfilesResponse>(`/genai/fleet/policy-profiles/${suffix}`);
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
  target_role?: string;
  runtime_type?: string;
  target_environment?: string;
  ssh_user: string;
  ssh_port: number;
  target_type: string;
  profile: string;
  policy_profile?: string;
  service_name?: string;
  service_kind?: string;
  systemd_unit?: string;
  container_name?: string;
  process_name?: string;
  port?: number | null;
  log_source_type?: string;
  journal_unit?: string;
  file_path?: string;
  log_container_name?: string;
  log_stream_family?: string;
  parser_name?: string;
  ship_logs_centrally?: boolean;
  shipper_type?: string;
  opensearch_pipeline?: string;
  application_name?: string;
  notes?: string;
  pem_file?: File | null;
}): Promise<OnboardingRequest> {
  const formData = new FormData();
  formData.append("name", payload.name);
  formData.append("hostname", payload.hostname);
  if (payload.target_role) formData.append("target_role", payload.target_role);
  if (payload.runtime_type) formData.append("runtime_type", payload.runtime_type);
  if (payload.target_environment) formData.append("target_environment", payload.target_environment);
  formData.append("ssh_user", payload.ssh_user);
  formData.append("ssh_port", String(payload.ssh_port));
  formData.append("target_type", payload.target_type);
  formData.append("profile", payload.profile);
  if (payload.policy_profile) formData.append("policy_profile", payload.policy_profile);
  if (payload.service_name) formData.append("service_name", payload.service_name);
  if (payload.service_kind) formData.append("service_kind", payload.service_kind);
  if (payload.systemd_unit) formData.append("systemd_unit", payload.systemd_unit);
  if (payload.container_name) formData.append("container_name", payload.container_name);
  if (payload.process_name) formData.append("process_name", payload.process_name);
  if (payload.port != null) formData.append("port", String(payload.port));
  if (payload.log_source_type) formData.append("log_source_type", payload.log_source_type);
  if (payload.journal_unit) formData.append("journal_unit", payload.journal_unit);
  if (payload.file_path) formData.append("file_path", payload.file_path);
  if (payload.log_container_name) formData.append("log_container_name", payload.log_container_name);
  if (payload.log_stream_family) formData.append("log_stream_family", payload.log_stream_family);
  if (payload.parser_name) formData.append("parser_name", payload.parser_name);
  if (payload.ship_logs_centrally != null) formData.append("ship_logs_centrally", String(payload.ship_logs_centrally));
  if (payload.shipper_type) formData.append("shipper_type", payload.shipper_type);
  if (payload.opensearch_pipeline) formData.append("opensearch_pipeline", payload.opensearch_pipeline);
  if (payload.application_name) formData.append("application_name", payload.application_name);
  if (payload.notes) formData.append("notes", payload.notes);
  if (payload.pem_file) {
    formData.append("pem_file", payload.pem_file);
  }

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
  target_role?: string;
  runtime_type?: string;
  target_environment?: string;
  ssh_user: string;
  ssh_port: number;
  target_type: string;
  profile: string;
  policy_profile?: string;
  service_name?: string;
  service_kind?: string;
  systemd_unit?: string;
  container_name?: string;
  process_name?: string;
  port?: number | null;
  log_source_type?: string;
  journal_unit?: string;
  file_path?: string;
  log_container_name?: string;
  log_stream_family?: string;
  parser_name?: string;
  ship_logs_centrally?: boolean;
  shipper_type?: string;
  opensearch_pipeline?: string;
  application_name?: string;
  notes?: string;
  pem_file?: File | null;
}): Promise<OnboardingRequest> {
  const formData = new FormData();
  formData.append("name", payload.name);
  formData.append("hostname", payload.hostname);
  if (payload.target_role) formData.append("target_role", payload.target_role);
  if (payload.runtime_type) formData.append("runtime_type", payload.runtime_type);
  if (payload.target_environment) formData.append("target_environment", payload.target_environment);
  formData.append("ssh_user", payload.ssh_user);
  formData.append("ssh_port", String(payload.ssh_port));
  formData.append("target_type", payload.target_type);
  formData.append("profile", payload.profile);
  if (payload.policy_profile) formData.append("policy_profile", payload.policy_profile);
  if (payload.service_name) formData.append("service_name", payload.service_name);
  if (payload.service_kind) formData.append("service_kind", payload.service_kind);
  if (payload.systemd_unit) formData.append("systemd_unit", payload.systemd_unit);
  if (payload.container_name) formData.append("container_name", payload.container_name);
  if (payload.process_name) formData.append("process_name", payload.process_name);
  if (payload.port != null) formData.append("port", String(payload.port));
  if (payload.log_source_type) formData.append("log_source_type", payload.log_source_type);
  if (payload.journal_unit) formData.append("journal_unit", payload.journal_unit);
  if (payload.file_path) formData.append("file_path", payload.file_path);
  if (payload.log_container_name) formData.append("log_container_name", payload.log_container_name);
  if (payload.log_stream_family) formData.append("log_stream_family", payload.log_stream_family);
  if (payload.parser_name) formData.append("parser_name", payload.parser_name);
  if (payload.ship_logs_centrally != null) formData.append("ship_logs_centrally", String(payload.ship_logs_centrally));
  if (payload.shipper_type) formData.append("shipper_type", payload.shipper_type);
  if (payload.opensearch_pipeline) formData.append("opensearch_pipeline", payload.opensearch_pipeline);
  if (payload.application_name) formData.append("application_name", payload.application_name);
  if (payload.notes) formData.append("notes", payload.notes);
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

export async function fetchIntegrations(): Promise<IntegrationConfig[]> {
  const payload = await fetchJson<{ count: number; results: IntegrationConfig[] }>("/genai/integrations/");
  return payload.results || [];
}

export async function fetchIntegrationConfig(integrationRef: string): Promise<IntegrationConfig> {
  return fetchJson<IntegrationConfig>(`/genai/integrations/${encodeURIComponent(integrationRef)}/`);
}

export async function saveIntegrationConfig(payload: IntegrationConfig): Promise<IntegrationConfig> {
  const integrationRef = payload.integration_id || payload.integration_type;
  const response = await fetch(`/genai/integrations/${encodeURIComponent(integrationRef)}/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const body = (await response.json()) as IntegrationConfig & { error?: string; detail?: string };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Save integration failed: ${response.status}`);
  }
  return body;
}

export async function testIntegrationConnection(integrationRef: string): Promise<{
  integration: IntegrationConfig;
  healthy: boolean;
  status: string;
  latency_ms: number;
  message: string;
}> {
  const response = await fetch(`/genai/integrations/${encodeURIComponent(integrationRef)}/test/`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "X-CSRFToken": getCsrfToken(),
    },
  });
  const body = (await response.json()) as {
    integration: IntegrationConfig;
    healthy: boolean;
    status: string;
    latency_ms: number;
    message: string;
    error?: string;
    detail?: string;
  };
  if (!response.ok) {
    throw new Error(body.detail || body.error || `Integration test failed: ${response.status}`);
  }
  return body;
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

// ---------------------------------------------------------------------------
// M6 — Runbook Generator
// ---------------------------------------------------------------------------

export type RunbookResult = {
  runbook_id: number;
  title: string;
  content: string;
};

export async function generateRunbook(incidentKey: string): Promise<RunbookResult> {
  const response = await fetch(`/genai/incidents/${encodeURIComponent(incidentKey)}/generate-runbook/`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
  });
  const body = (await response.json()) as RunbookResult & { error?: string; detail?: string };
  if (!response.ok) throw new Error(body.detail || body.error || `Runbook generation failed: ${response.status}`);
  return body;
}

// ---------------------------------------------------------------------------
// M6 — Anomaly Explainer
// ---------------------------------------------------------------------------

export type AnomalyExplanation = {
  alert_name: string;
  explanation: string;
};

export async function explainAnomaly(payload: {
  alert_name: string;
  target_host?: string;
  labels?: Record<string, string>;
  summary?: string;
  incident_key?: string;
}): Promise<AnomalyExplanation> {
  const response = await fetch("/genai/anomaly-explain/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify(payload),
  });
  const body = (await response.json()) as AnomalyExplanation & { error?: string; detail?: string };
  if (!response.ok) throw new Error(body.detail || body.error || `Anomaly explain failed: ${response.status}`);
  return body;
}

// ---------------------------------------------------------------------------
// M6 — Change Risk Explainer
// ---------------------------------------------------------------------------

export type ChangeRiskAnalysis = {
  risk_score: number;
  risk_level: string;
  affected_services: string[];
  recommended_window: string;
  rollback_steps: string[];
  risk_factors: string[];
  mitigations: string[];
  raw?: string;
};

export type ChangeRiskResult = {
  service: string;
  change_description: string;
  planned_at: string;
  change_type: string;
  analysis: ChangeRiskAnalysis;
  blast_radius: string[];
  depends_on: string[];
};

export async function analyzeChangeRisk(payload: {
  service: string;
  change_description: string;
  planned_at?: string;
  change_type?: string;
}): Promise<ChangeRiskResult> {
  const response = await fetch("/genai/change-risk/", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
    body: JSON.stringify(payload),
  });
  const body = (await response.json()) as ChangeRiskResult & { error?: string; detail?: string };
  if (!response.ok) throw new Error(body.detail || body.error || `Change risk analysis failed: ${response.status}`);
  return body;
}

// ---------------------------------------------------------------------------
// M4 — SLA Acknowledge
// ---------------------------------------------------------------------------

export async function acknowledgeSla(incidentKey: string): Promise<{ status: string }> {
  const response = await fetch(`/genai/incidents/${encodeURIComponent(incidentKey)}/acknowledge-sla/`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
  });
  const body = (await response.json()) as { status: string; error?: string };
  if (!response.ok) throw new Error(body.error || `SLA acknowledge failed: ${response.status}`);
  return body;
}

// ---------------------------------------------------------------------------
// M4 — Post-Incident Timeline Narrative
// ---------------------------------------------------------------------------

export async function generateTimelineNarrative(incidentKey: string): Promise<{ incident_key: string; narrative: string }> {
  const response = await fetch(`/genai/incidents/${encodeURIComponent(incidentKey)}/timeline-narrative/`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "X-CSRFToken": getCsrfToken() },
  });
  const body = (await response.json()) as { incident_key: string; narrative: string; error?: string; detail?: string };
  if (!response.ok) throw new Error(body.detail || body.error || `Narrative generation failed: ${response.status}`);
  return body;
}

export function getRunbookDownloadUrl(incidentKey: string): string {
  return `/genai/incidents/${encodeURIComponent(incidentKey)}/runbook/download/`;
}

export function getTimelineNarrativeDownloadUrl(incidentKey: string): string {
  return `/genai/incidents/${encodeURIComponent(incidentKey)}/timeline-narrative/download/`;
}

// ---------------------------------------------------------------------------
// Analytics — Signal Heatmap
// ---------------------------------------------------------------------------

export type HeatmapSeverity = "critical" | "high" | "warning" | "info" | "unknown";

export type HeatmapCell = {
  service: string;
  bucket: string;       // ISO timestamp string
  count: number;
  max_severity: HeatmapSeverity;
  severities: Partial<Record<HeatmapSeverity, number>>;
};

export type HeatmapData = {
  services: string[];
  buckets: string[];
  cells: HeatmapCell[];
  meta: {
    hours: number;
    bucket_minutes: number;
    total_alerts: number;
    max_count: number;
    service_count: number;
    generated_at: string;
  };
};

export async function fetchSignalHeatmap(params: {
  hours?: number;
  bucket_minutes?: number;
  service?: string;
  environment?: string;
} = {}): Promise<HeatmapData> {
  const qs = new URLSearchParams();
  if (params.hours)          qs.set("hours",          String(params.hours));
  if (params.bucket_minutes) qs.set("bucket_minutes", String(params.bucket_minutes));
  if (params.service)        qs.set("service",        params.service);
  if (params.environment)    qs.set("environment",    params.environment);
  const url = `/genai/analytics/signal-heatmap/${qs.toString() ? "?" + qs : ""}`;
  const response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Signal heatmap fetch failed: ${response.status}`);
  return response.json() as Promise<HeatmapData>;
}

// ---------------------------------------------------------------------------
// Analytics — Correlated Timeline
// ---------------------------------------------------------------------------

export type TimelineEventType =
  | "alert"
  | "incident_opened"
  | "incident_resolved"
  | "execution";

export type TimelineLane = "alerts" | "incidents" | "executions";

export type TimelineEvent = {
  id: string;
  type: TimelineEventType;
  lane: TimelineLane;
  timestamp: string;      // ISO
  title: string;
  service: string;
  environment: string;
  severity: HeatmapSeverity;
  status: string;
  incident_key: string | null;
  meta: Record<string, unknown>;
};

export type TimelineLink = {
  source: string;
  target: string;
  incident_key: string;
};

export type TimelineLaneConfig = {
  id: TimelineLane;
  label: string;
  color: string;
};

export type CorrelatedTimelineData = {
  events: TimelineEvent[];
  links: TimelineLink[];
  lanes: TimelineLaneConfig[];
  meta: {
    hours: number;
    event_count: number;
    service_filter: string | null;
    incident_key_filter: string | null;
    generated_at: string;
  };
};

export async function fetchCorrelatedTimeline(params: {
  hours?: number;
  service?: string;
  incident_key?: string;
} = {}): Promise<CorrelatedTimelineData> {
  const qs = new URLSearchParams();
  if (params.hours)        qs.set("hours",        String(params.hours));
  if (params.service)      qs.set("service",      params.service);
  if (params.incident_key) qs.set("incident_key", params.incident_key);
  const url = `/genai/analytics/correlated-timeline/${qs.toString() ? "?" + qs : ""}`;
  const response = await fetch(url, { credentials: "include", headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Correlated timeline fetch failed: ${response.status}`);
  return response.json() as Promise<CorrelatedTimelineData>;
}
