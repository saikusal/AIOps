import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  acknowledgeSla,
  executeDiagnosticCommand,
  fetchIncidentTimeline,
  fetchRecentAlerts,
  fetchRecentIncidents,
  generateRunbook,
  generateTimelineNarrative,
  getRunbookDownloadUrl,
  getTimelineNarrativeDownloadUrl,
<<<<<<< Updated upstream
=======
  type AlertRecommendation,
  type BlastRadiusEstimate,
  type IncidentTimeline,
>>>>>>> Stashed changes
  type RunbookResult,
  type TypedAction,
} from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function formatCurrency(value?: number | null, currency = "INR") {
  if (value === undefined || value === null) return "—";
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `₹${Math.round(value).toLocaleString("en-IN")}`;
  }
}

function impactLevelColor(level?: string): string {
  switch (level) {
    case "critical": return "var(--color-danger, #ef4444)";
    case "high": return "var(--color-warning, #f59e0b)";
    case "medium": return "var(--color-caution, #eab308)";
    case "low": return "var(--color-info, #3b82f6)";
    default: return "var(--color-muted, #6b7280)";
  }
}

function slaBadgeColor(sla?: { breached: boolean; resolution_remaining_minutes: number | null } | null): string {
  if (!sla) return "var(--color-muted, #6b7280)";
  if (sla.breached) return "var(--color-danger, #ef4444)";
  if (sla.resolution_remaining_minutes !== null && sla.resolution_remaining_minutes < 30) return "var(--color-warning, #f59e0b)";
  return "var(--color-success, #22c55e)";
}

function formatSlaMinutes(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes < 0) return `${Math.abs(Math.round(minutes))}m overdue`;
  if (minutes < 60) return `${Math.round(minutes)}m left`;
  return `${Math.round(minutes / 60)}h ${Math.round(minutes % 60)}m left`;
}

<<<<<<< Updated upstream
=======
function formatDateTime(value?: string | null): string {
  if (!value) return "not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function compactText(value?: string | null, fallback = "Not available yet."): string {
  return value?.replace(/\s+/g, " ").trim() || fallback;
}

function joinDetail(parts: Array<string | undefined | null | false>): string {
  return parts.filter(Boolean).join(" ");
}

function hasDisplayValue(value: unknown): boolean {
  if (value === undefined || value === null || value === "") return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

function firstDisplayValue<T>(...values: T[]): T | undefined {
  return values.find((value) => hasDisplayValue(value));
}

>>>>>>> Stashed changes
type DecisionEvidenceMeta = {
  decision_policy?: string;
  confidence_reason?: string;
  confidence_assessment?: {
    level?: string;
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
};

function DecisionPanel({ meta }: { meta: DecisionEvidenceMeta }) {
  const decisionPolicy = meta.decision_policy || meta.evidence_assessment?.safe_action || "diagnose";
  const confidenceReason = meta.confidence_reason || meta.evidence_assessment?.confidence_reason || "";
  const confidenceAssessment = (meta.confidence_assessment || meta.evidence_assessment?.confidence_assessment || {}) as Record<string, unknown>;
  const contradictionAssessment = (meta.contradiction_assessment || meta.evidence_assessment?.contradiction_assessment || {}) as Record<string, unknown>;
  const evidenceGapAssessment = (meta.evidence_gap_assessment || meta.evidence_assessment?.evidence_gap_assessment || {}) as Record<string, unknown>;
  const hardEvidence = meta.hard_evidence || meta.evidence_assessment?.hard_evidence || [];
  const missingEvidence = meta.missing_evidence || meta.evidence_assessment?.missing_evidence || [];
  const bestDependencyTarget = meta.evidence_assessment?.best_dependency_target || "";

  if (!confidenceReason && hardEvidence.length === 0 && missingEvidence.length === 0 && !bestDependencyTarget && !Object.keys(confidenceAssessment).length && !Object.keys(contradictionAssessment).length && !Object.keys(evidenceGapAssessment).length) {
    return null;
  }

  return (
    <article className="incident-deep-dive__panel incident-deep-dive__panel--decision">
      <div className="incident-decision__header">
        <strong>Decision Policy</strong>
        <span className={`decision-policy decision-policy--${decisionPolicy}`}>{decisionPolicy.toUpperCase()}</span>
      </div>
      {(confidenceAssessment.score !== undefined || contradictionAssessment.severity || evidenceGapAssessment.status) ? (
        <p>
          {confidenceAssessment.score !== undefined ? `Confidence ${Math.round(Number(confidenceAssessment.score) * 100)}%` : "Confidence pending"}
          {confidenceAssessment.posture ? ` · ${String(confidenceAssessment.posture)}` : ""}
          {contradictionAssessment.severity ? ` · contradictions ${String(contradictionAssessment.severity)}` : ""}
          {evidenceGapAssessment.status ? ` · gaps ${String(evidenceGapAssessment.status)}` : ""}
        </p>
      ) : null}
      {confidenceReason ? <p>{confidenceReason}</p> : null}
      {bestDependencyTarget ? <p className="incident-decision__target">Preferred pivot target: {bestDependencyTarget}</p> : null}
      {hardEvidence.length > 0 ? (
        <div className="incident-decision__section incident-decision__section--hard">
          <span>Hard Evidence</span>
          <ul>
            {hardEvidence.map((item, index) => (
              <li key={`hard-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {missingEvidence.length > 0 ? (
        <div className="incident-decision__section incident-decision__section--missing">
          <span>Missing Evidence</span>
          <ul>
            {missingEvidence.map((item, index) => (
              <li key={`missing-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

type JourneyStatus = "pending" | "active" | "completed" | "blocked" | "failed" | "resolved";

type VisualJourneyStage = {
  key: string;
  label: string;
  meta: string;
  status: JourneyStatus;
  detail: string;
  action?: ReactNode;
};

type ImpactResource = {
  id: string;
  label: string;
  kind: "alert" | "service" | "dependency" | "impacted" | "runbook";
  status: JourneyStatus;
  meta: string;
};

function normalizeStatus(value?: string | null): string {
  return String(value || "").toLowerCase().replace(/[_\s]+/g, "-");
}

function statusToJourneyStatus(value?: string | null): JourneyStatus {
  const status = normalizeStatus(value);
  if (["resolved", "closed", "verified", "healthy"].includes(status)) return "resolved";
  if (["completed", "success", "succeeded", "done"].includes(status)) return "completed";
  if (["running", "in-progress", "executing", "active", "firing", "open", "triggered"].includes(status)) return "active";
  if (["approval-required", "blocked", "waiting", "verification-pending"].includes(status)) return "blocked";
  if (["failed", "error", "breached", "critical"].includes(status)) return "failed";
  return "pending";
}

function isTerminalIncident(status?: string | null): boolean {
  return ["resolved", "closed", "verified"].includes(normalizeStatus(status));
}

function hasRunbook(selectedKey: string | undefined, incident: IncidentTimeline, runbookState: Record<string, RunbookResult | null>) {
  return Boolean(selectedKey && (runbookState[selectedKey] || incident.latest_runbook));
}

function buildImpactResources(
  incident: IncidentTimeline,
  selectedAlert: AlertRecommendation | undefined,
  deepDiveEntry: (AlertRecommendation & Record<string, unknown>) | null,
  runbookReady: boolean,
): ImpactResource[] {
  const rootLabel = incident.primary_service || incident.target_host || "Primary service";
  const alertLabel = selectedAlert?.alert_name || incident.alerts?.[0]?.alert_name || "Alert signal";
  const dependencyNames = Array.from(new Set([
    ...(selectedAlert?.depends_on || []),
    ...(deepDiveEntry?.depends_on || []),
  ].filter(Boolean)));
  const impactedNames = Array.from(new Set([
    ...(incident.blast_radius || []),
    ...(selectedAlert?.blast_radius || []),
  ].filter((item) => item && item !== rootLabel)));

  return [
    {
      id: `alert-${alertLabel}`,
      label: alertLabel,
      kind: "alert",
      status: statusToJourneyStatus(selectedAlert?.status || incident.status),
      meta: selectedAlert?.status || "signal",
    },
    {
      id: `service-${rootLabel}`,
      label: rootLabel,
      kind: "service",
      status: incident.sla?.breached ? "failed" : statusToJourneyStatus(incident.status),
      meta: incident.target_host || "primary resource",
    },
    ...dependencyNames.slice(0, 4).map((name) => ({
      id: `dependency-${name}`,
      label: name,
      kind: "dependency" as const,
      status: "completed" as const,
      meta: "upstream dependency",
    })),
    ...impactedNames.slice(0, 6).map((name) => ({
      id: `impacted-${name}`,
      label: name,
      kind: "impacted" as const,
      status: isTerminalIncident(incident.status) ? "resolved" as const : "active" as const,
      meta: "blast radius",
    })),
    {
      id: `runbook-${incident.incident_key}`,
      label: runbookReady ? "Runbook ready" : "Runbook pending",
      kind: "runbook",
      status: runbookReady ? "completed" : "pending",
      meta: "knowledge base",
    },
  ];
}

function JourneyIcon({ kind }: { kind: ImpactResource["kind"] }) {
  const common = {
    width: 22,
    height: 22,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (kind === "alert") {
    return (
      <svg {...common}>
        <path d="M12 3l9 16H3L12 3z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </svg>
    );
  }
  if (kind === "dependency") {
    return (
      <svg {...common}>
        <rect x="3" y="4" width="6" height="6" rx="2" />
        <rect x="15" y="4" width="6" height="6" rx="2" />
        <path d="M9 7h6" />
        <path d="M12 10v7" />
        <circle cx="12" cy="19" r="2" />
      </svg>
    );
  }
  if (kind === "impacted") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 8v4l3 2" />
        <path d="M4 12H2" />
        <path d="M22 12h-2" />
      </svg>
    );
  }
  if (kind === "runbook") {
    return (
      <svg {...common}>
        <path d="M6 4h9l3 3v13H6z" />
        <path d="M15 4v4h4" />
        <path d="M9 12h6" />
        <path d="M9 16h5" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="5" y="5" width="14" height="14" rx="3" />
      <path d="M9 9h6v6H9z" />
      <path d="M12 2v3" />
      <path d="M12 19v3" />
      <path d="M2 12h3" />
      <path d="M19 12h3" />
    </svg>
  );
}

function IncidentVisualJourney({
  incident,
  stages,
  resources,
  graphUrl,
}: {
  incident: IncidentTimeline;
  stages: VisualJourneyStage[];
  resources: ImpactResource[];
  graphUrl: string;
}) {
  const primaryStatus = incident.sla?.breached ? "failed" : statusToJourneyStatus(incident.status);
  const revenueLost = incident.business_impact?.revenue_lost ?? 0;

  return (
    <section className={`incident-journey incident-journey--${primaryStatus}`}>
      <div className="incident-journey__header">
        <div>
          <div className="eyebrow">Live Incident Journey</div>
          <h3>{incident.incident_number ? `${incident.incident_number} · ${incident.title}` : incident.title}</h3>
          <p>{incident.reasoning || incident.summary}</p>
        </div>
        <div className="incident-journey__status-orb" aria-label={`Incident status ${incident.status}`}>
          <span />
          <strong>{incident.status || "unknown"}</strong>
        </div>
      </div>

      <div className="incident-journey__metrics">
        <div className={`incident-journey__metric is-${primaryStatus}`}>
          <span>Severity</span>
          <strong>{incident.severity || incident.priority || "unknown"}</strong>
        </div>
        <div className={`incident-journey__metric ${incident.sla?.breached ? "is-failed" : ""}`}>
          <span>SLA</span>
          <strong>{incident.sla ? formatSlaMinutes(incident.sla.resolution_remaining_minutes) : "not set"}</strong>
        </div>
        <div className="incident-journey__metric">
          <span>Affected</span>
          <strong>{incident.primary_service || incident.target_host}</strong>
        </div>
        <div className="incident-journey__metric">
          <span>Blast Radius</span>
          <strong>{incident.blast_radius?.length || 0}</strong>
        </div>
        <div className={`incident-journey__metric ${revenueLost > 0 ? "is-failed" : ""}`}>
          <span>Revenue</span>
          <strong>{formatCurrency(revenueLost, incident.business_impact?.currency || "INR")}</strong>
        </div>
      </div>

      <div className="incident-journey__stage-track" aria-label="Incident lifecycle stages">
        {stages.map((stage, index) => (
          <article key={stage.key} className={`incident-stage incident-stage--${stage.status}`}>
            <div className="incident-stage__rail">
              <span className="incident-stage__dot">{index + 1}</span>
            </div>
            <div className="incident-stage__content">
              <span>{stage.meta}</span>
              <strong>{stage.label}</strong>
              <p>{stage.detail}</p>
              {stage.action ? <div className="incident-stage__action">{stage.action}</div> : null}
            </div>
          </article>
        ))}
      </div>

      <div className="incident-resource-map">
        <div className="incident-resource-map__header">
          <div>
            <div className="eyebrow">Impacted Resource Map</div>
            <h3>{incident.primary_service || incident.target_host}</h3>
          </div>
          <Link className="shell__link shell__link--small" to={graphUrl}>
            Open 3D Incident Graph
          </Link>
        </div>
        <div className="incident-resource-map__canvas">
          {resources.map((resource) => (
            <article key={resource.id} className={`incident-resource incident-resource--${resource.kind} incident-resource--${resource.status}`}>
              <span className="incident-resource__icon">
                <JourneyIcon kind={resource.kind} />
              </span>
              <strong>{resource.label}</strong>
              <small>{resource.meta}</small>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

export function IncidentsPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [activeIncidentKey, setActiveIncidentKey] = useState<string | undefined>(undefined);
  const [executionState, setExecutionState] = useState<Record<string, Record<string, unknown>>>({});
  const [autoExecuted, setAutoExecuted] = useState<Record<string, boolean>>({});
  const [runbookState, setRunbookState] = useState<Record<string, RunbookResult | null>>({});
  const [narrativeState, setNarrativeState] = useState<Record<string, string | null>>({});
  const serviceFilter = searchParams.get("service");
  const refreshQueryOptions = useRefreshQueryOptions();
  const incidentsQuery = useQuery({
    queryKey: ["recent-incidents"],
    queryFn: fetchRecentIncidents,
    ...refreshQueryOptions,
  });

  const alertsQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    ...refreshQueryOptions,
  });

  const incidentList = (incidentsQuery.data || []).filter((incident) =>
    serviceFilter ? incident.primary_service === serviceFilter || incident.target_host === serviceFilter : true,
  );
  const selectedKey = activeIncidentKey || incidentList[0]?.incident_key;
  const timelineQuery = useQuery({
    queryKey: ["incident-timeline", selectedKey],
    queryFn: () => fetchIncidentTimeline(selectedKey!),
    enabled: Boolean(selectedKey),
  });
  const selectedAlert = (alertsQuery.data || []).find((alert) =>
    timelineQuery.data
      ? alert.target_host === timelineQuery.data.primary_service ||
        alert.target_host === timelineQuery.data.target_host ||
        alert.incident_key === timelineQuery.data.incident_key
      : false,
  );
  const linkedRecommendation = timelineQuery.data?.linked_recommendation || null;
  const executionKey = selectedAlert?.alert_id || selectedKey || "incident";
  const executionOverlay = (executionState[executionKey] || {}) as {
    execution_status?: string;
    last_execution_at?: string;
    post_command_ai_analysis?: string;
    command_output?: string;
    remediation_execution_status?: string;
    remediation_last_execution_at?: string;
    post_remediation_ai_analysis?: string;
    remediation_output?: string;
    remediation_command?: string;
    remediation_target_host?: string;
    remediation_why?: string;
    remediation_requires_approval?: boolean;
    diagnostic_typed_action?: TypedAction;
    remediation_typed_action?: TypedAction;
    decision_policy?: string;
    confidence_reason?: string;
    hard_evidence?: string[];
    missing_evidence?: string[];
    evidence_assessment?: {
      safe_action?: string;
      confidence_reason?: string;
      hard_evidence?: string[];
      missing_evidence?: string[];
      dependency_hard_evidence?: Record<string, string[]>;
      best_dependency_target?: string;
    };
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
      remediation_typed_action?: TypedAction;
    };
    agent_success?: boolean;
  };
  const deepDiveEntry = useMemo(() => {
    const source = linkedRecommendation || selectedAlert;
    if (!source) return null;
    return {
      ...source,
      ...executionOverlay,
      post_command_ai_analysis: executionOverlay.post_command_ai_analysis || source.post_command_ai_analysis,
      final_answer: executionOverlay.final_answer || source.final_answer,
      analysis_sections: executionOverlay.analysis_sections || source.analysis_sections,
      command_output: executionOverlay.command_output || source.command_output,
      execution_status: executionOverlay.execution_status || source.execution_status,
      last_execution_at: executionOverlay.last_execution_at || source.last_execution_at,
      remediation_command:
        executionOverlay.remediation_command ||
        executionOverlay.analysis_sections?.remediation_command ||
        source.remediation_command ||
        source.analysis_sections?.remediation_command,
      remediation_target_host:
        executionOverlay.remediation_target_host ||
        executionOverlay.analysis_sections?.remediation_target_host ||
        source.remediation_target_host ||
        source.analysis_sections?.remediation_target_host,
      remediation_why:
        executionOverlay.remediation_why ||
        executionOverlay.analysis_sections?.remediation_why ||
        source.remediation_why ||
        source.analysis_sections?.remediation_why,
      remediation_requires_approval:
        executionOverlay.remediation_requires_approval ??
        executionOverlay.analysis_sections?.remediation_requires_approval ??
        source.remediation_requires_approval ??
        source.analysis_sections?.remediation_requires_approval,
      diagnostic_typed_action:
        executionOverlay.diagnostic_typed_action ||
        source.diagnostic_typed_action,
      remediation_typed_action:
        executionOverlay.remediation_typed_action ||
        executionOverlay.analysis_sections?.remediation_typed_action ||
        source.remediation_typed_action ||
        source.analysis_sections?.remediation_typed_action,
      remediation_execution_status:
        executionOverlay.remediation_execution_status || source.remediation_execution_status,
      remediation_last_execution_at:
        executionOverlay.remediation_last_execution_at || source.remediation_last_execution_at,
      remediation_output: executionOverlay.remediation_output || source.remediation_output,
      post_remediation_ai_analysis:
        executionOverlay.post_remediation_ai_analysis || source.post_remediation_ai_analysis,
      agent_success: typeof executionOverlay.agent_success === "boolean" ? executionOverlay.agent_success : source.agent_success,
    };
  }, [executionOverlay, linkedRecommendation, selectedAlert]);

  const executeMutation = useMutation({
    mutationFn: async () => {
      if (!deepDiveEntry?.diagnostic_command || !deepDiveEntry?.target_host || !timelineQuery.data) {
        throw new Error("No diagnostic command is available for this incident yet.");
      }
      return executeDiagnosticCommand({
        alert_id: deepDiveEntry.alert_id,
        command: deepDiveEntry.diagnostic_command,
        original_question: timelineQuery.data.summary || timelineQuery.data.title,
        target_host: deepDiveEntry.target_host,
        typed_action: deepDiveEntry.diagnostic_typed_action,
      });
    },
    onMutate: () => {
      setExecutionState((current) => ({
        ...current,
        [executionKey]: {
          ...(current[executionKey] || {}),
          execution_status: "running",
        },
      }));
    },
    onSuccess: async (payload) => {
      setExecutionState((current) => ({
        ...current,
        [executionKey]: {
          ...(current[executionKey] || {}),
          execution_status: payload.execution_status,
          last_execution_at: payload.last_execution_at,
          post_command_ai_analysis: payload.final_answer,
          final_answer: payload.final_answer,
          analysis_sections: payload.analysis_sections,
          command_output: payload.command_output,
          agent_success: payload.agent_success,
          diagnostic_typed_action:
            payload.typed_action || (current[executionKey] as Record<string, unknown> | undefined)?.diagnostic_typed_action,
          remediation_typed_action:
            payload.analysis_sections?.remediation_typed_action || (current[executionKey] as Record<string, unknown> | undefined)?.remediation_typed_action,
        },
      }));
      await queryClient.invalidateQueries({ queryKey: ["recent-alerts"] });
      await queryClient.invalidateQueries({ queryKey: ["incident-timeline", selectedKey] });
    },
    onError: (error) => {
      setExecutionState((current) => ({
        ...current,
        [executionKey]: {
          ...(current[executionKey] || {}),
          execution_status: "failed",
          post_command_ai_analysis: error instanceof Error ? error.message : "Command execution failed.",
        },
      }));
    },
  });

  const remediationMutation = useMutation({
    mutationFn: async () => {
      if (!deepDiveEntry?.remediation_command || !deepDiveEntry?.remediation_target_host || !timelineQuery.data) {
        throw new Error("No remediation command is available for this incident yet.");
      }
      return executeDiagnosticCommand({
        alert_id: deepDiveEntry.alert_id,
        command: deepDiveEntry.remediation_command,
        original_question: `Apply remediation for ${timelineQuery.data.title}`,
        target_host: deepDiveEntry.remediation_target_host,
        execution_type: "remediation",
        typed_action: deepDiveEntry.remediation_typed_action,
      });
    },
    onMutate: () => {
      setExecutionState((current) => ({
        ...current,
        [executionKey]: {
          ...(current[executionKey] || {}),
          remediation_execution_status: "running",
        },
      }));
    },
    onSuccess: async (payload) => {
      setExecutionState((current) => ({
        ...current,
        [executionKey]: {
          ...(current[executionKey] || {}),
          remediation_execution_status: payload.execution_status,
          remediation_last_execution_at: payload.last_execution_at,
          post_remediation_ai_analysis: payload.final_answer,
          remediation_output: payload.command_output,
          analysis_sections: payload.analysis_sections,
          remediation_command: payload.analysis_sections?.remediation_command || (current[executionKey] as Record<string, unknown> | undefined)?.remediation_command,
          remediation_target_host: payload.analysis_sections?.remediation_target_host || (current[executionKey] as Record<string, unknown> | undefined)?.remediation_target_host,
          remediation_typed_action:
            payload.analysis_sections?.remediation_typed_action ||
            payload.typed_action ||
            (current[executionKey] as Record<string, unknown> | undefined)?.remediation_typed_action,
        },
      }));
      await queryClient.invalidateQueries({ queryKey: ["recent-alerts"] });
      await queryClient.invalidateQueries({ queryKey: ["incident-timeline", selectedKey] });
    },
    onError: (error) => {
      setExecutionState((current) => ({
        ...current,
        [executionKey]: {
          ...(current[executionKey] || {}),
          remediation_execution_status: "failed",
          post_remediation_ai_analysis: error instanceof Error ? error.message : "Remediation execution failed.",
        },
      }));
    },
  });

  const runbookMutation = useMutation({
    mutationFn: () => generateRunbook(selectedKey!),
    onSuccess: (data) => {
      setRunbookState((cur) => ({ ...cur, [selectedKey!]: data }));
    },
  });

  const narrativeMutation = useMutation({
    mutationFn: () => generateTimelineNarrative(selectedKey!),
    onSuccess: (data) => {
      setNarrativeState((cur) => ({ ...cur, [selectedKey!]: data.narrative }));
    },
  });

  const slaAckMutation = useMutation({
    mutationFn: () => acknowledgeSla(selectedKey!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recent-incidents"] }),
  });

  useEffect(() => {
    if (!deepDiveEntry?.should_execute || !deepDiveEntry?.diagnostic_command || !deepDiveEntry?.target_host) return;
    if (deepDiveEntry.execution_status && deepDiveEntry.execution_status !== "pending") return;
    if (executeMutation.isPending || autoExecuted[executionKey]) return;
    setAutoExecuted((current) => ({ ...current, [executionKey]: true }));
    executeMutation.mutate();
  }, [
    autoExecuted,
    deepDiveEntry?.diagnostic_command,
    deepDiveEntry?.execution_status,
    deepDiveEntry?.should_execute,
    deepDiveEntry?.target_host,
    executeMutation,
    executionKey,
  ]);

  useEffect(() => {
    if (!selectedKey || !timelineQuery.data) return;
    if (timelineQuery.data.latest_runbook) {
      setRunbookState((current) => ({
        ...current,
        [selectedKey]: current[selectedKey] || timelineQuery.data!.latest_runbook || null,
      }));
    }
    if (timelineQuery.data.latest_narrative?.narrative) {
      setNarrativeState((current) => ({
        ...current,
        [selectedKey]: current[selectedKey] || timelineQuery.data!.latest_narrative!.narrative || null,
      }));
    }
  }, [selectedKey, timelineQuery.data]);

  const runbookReady = Boolean(selectedKey && timelineQuery.data && hasRunbook(selectedKey, timelineQuery.data, runbookState));
  const narrativeReady = Boolean(selectedKey && (narrativeState[selectedKey] || timelineQuery.data?.latest_narrative?.narrative));
  const incidentGraphUrl = timelineQuery.data ? `/graph/incident/${encodeURIComponent(timelineQuery.data.incident_key)}` : "#";
  const alertGraphUrl = selectedAlert ? `/graph/${encodeURIComponent(selectedAlert.alert_id)}` : incidentGraphUrl;
  const revenueLost = timelineQuery.data?.business_impact?.revenue_lost ?? 0;
  const rcaStatus = executeMutation.isPending || deepDiveEntry?.execution_status === "running"
    ? "active"
    : deepDiveEntry?.execution_status === "failed"
      ? "failed"
      : deepDiveEntry?.post_command_ai_analysis || deepDiveEntry?.final_answer
        ? "completed"
        : deepDiveEntry
          ? "pending"
          : "blocked";
  const remediationStatus = remediationMutation.isPending || deepDiveEntry?.remediation_execution_status === "running"
    ? "active"
    : deepDiveEntry?.remediation_execution_status === "approval_required" || deepDiveEntry?.remediation_execution_status === "verification_pending"
      ? "blocked"
      : deepDiveEntry?.remediation_execution_status === "failed"
        ? "failed"
        : ["completed", "verified"].includes(normalizeStatus(deepDiveEntry?.remediation_execution_status))
          ? "completed"
          : deepDiveEntry?.remediation_command
            ? "pending"
            : "blocked";
  const journeyStages: VisualJourneyStage[] = timelineQuery.data ? [
    {
      key: "summary",
      label: "Incident Summary",
      meta: `${timelineQuery.data.severity || timelineQuery.data.priority || "unknown"} severity`,
      status: statusToJourneyStatus(timelineQuery.data.status),
      detail: joinDetail([
        compactText(timelineQuery.data.reasoning || timelineQuery.data.summary, "Incident summary is not available yet."),
        `Primary service: ${timelineQuery.data.primary_service || "unknown"}.`,
        `Target: ${timelineQuery.data.target_host || "unknown"}.`,
        `Opened: ${formatDateTime(timelineQuery.data.opened_at)}.`,
      ]),
      action: (
        <>
          <Link className="shell__link shell__link--small" to={alertGraphUrl}>
            Alert Graph
          </Link>
          {timelineQuery.data.sla && !timelineQuery.data.sla.response_acknowledged_at ? (
            <button
              className="shell__link shell__link--small incident-journey__link-button"
              onClick={() => slaAckMutation.mutate()}
              disabled={slaAckMutation.isPending || !canManageIncidents}
            >
              {slaAckMutation.isPending ? "Acknowledging..." : "Acknowledge SLA"}
            </button>
          ) : null}
        </>
      ),
    },
    {
      key: "timeline",
      label: "Timeline",
      meta: `${timelineQuery.data.timeline_count || timelineQuery.data.timeline.length} events`,
      status: timelineQuery.data.timeline.length > 0 ? "completed" : "pending",
      detail: joinDetail([
        `Opened ${formatDateTime(timelineQuery.data.opened_at)}.`,
        timelineQuery.data.resolved_at ? `Resolved ${formatDateTime(timelineQuery.data.resolved_at)}.` : `Last updated ${formatDateTime(timelineQuery.data.updated_at)}.`,
        timelineQuery.data.timeline[0]
          ? `Latest event: ${timelineQuery.data.timeline[0].title} - ${compactText(timelineQuery.data.timeline[0].detail)}`
          : "No detailed timeline events have been recorded yet.",
      ]),
      action: (
        <Link className="shell__link shell__link--small" to={incidentGraphUrl}>
          3D Incident Graph
        </Link>
      ),
    },
    {
      key: "evidence",
      label: "Evidence",
      meta: deepDiveEntry?.target_host || selectedAlert?.target_host || timelineQuery.data.target_host || "target pending",
      status: rcaStatus,
      detail: joinDetail([
        compactText(
          deepDiveEntry?.analysis_sections?.evidence ||
            deepDiveEntry?.post_command_ai_analysis ||
            deepDiveEntry?.initial_ai_diagnosis ||
            selectedAlert?.summary,
          "Diagnostic evidence is ready for deep-dive execution.",
        ),
        (deepDiveEntry?.hard_evidence || selectedAlert?.hard_evidence || []).length
          ? `Hard evidence: ${(deepDiveEntry?.hard_evidence || selectedAlert?.hard_evidence || []).slice(0, 3).join("; ")}.`
          : null,
        (deepDiveEntry?.missing_evidence || selectedAlert?.missing_evidence || []).length
          ? `Missing evidence: ${(deepDiveEntry?.missing_evidence || selectedAlert?.missing_evidence || []).slice(0, 2).join("; ")}.`
          : null,
      ]),
      action: (
        <>
          <button
            className="assistant-button assistant-button--secondary"
            onClick={() => executeMutation.mutate()}
            disabled={executeMutation.isPending || !deepDiveEntry?.diagnostic_command || !deepDiveEntry.target_host || !canRunDiagnostics}
          >
            {executeMutation.isPending || deepDiveEntry?.execution_status === "running" ? "Running..." : "Run Deep Dive"}
          </button>
          <Link className="shell__link shell__link--small" to={`/investigations?incident_key=${encodeURIComponent(timelineQuery.data.incident_key)}`}>
            Investigation
          </Link>
        </>
      ),
    },
    {
      key: "impact",
      label: "Impact",
      meta: `${timelineQuery.data.blast_radius?.length || 0} resources`,
      status: timelineQuery.data.sla?.breached || revenueLost > 0 ? "failed" : statusToJourneyStatus(timelineQuery.data.status),
      detail: joinDetail([
        compactText(deepDiveEntry?.analysis_sections?.impact, "Impact is calculated from the blast radius, SLA state, and business telemetry."),
        `${timelineQuery.data.blast_radius?.length || 0} services are in the current blast radius.`,
        timelineQuery.data.business_impact
          ? `${formatCurrency(revenueLost, timelineQuery.data.business_impact.currency || "INR")} estimated revenue impact across ${timelineQuery.data.business_impact.failed_transactions ?? 0} failed transactions.`
          : "Business impact telemetry is not available yet.",
        timelineQuery.data.sla
          ? `Resolution SLA: ${formatSlaMinutes(timelineQuery.data.sla.resolution_remaining_minutes)}.`
          : "SLA is not set.",
      ]),
      action: (
        <Link className="shell__link shell__link--small" to={incidentGraphUrl}>
          Impact Graph
        </Link>
      ),
    },
    {
      key: "resolution-actions",
      label: "Resolution actions",
      meta: deepDiveEntry?.remediation_requires_approval ? "approval gated" : "operator controlled",
      status: remediationStatus,
      detail: joinDetail([
        compactText(
          deepDiveEntry?.remediation_why ||
            deepDiveEntry?.analysis_sections?.resolution ||
            deepDiveEntry?.analysis_sections?.remediation_steps?.join("; "),
          "Recommended remediation will appear after RCA evidence is available.",
        ),
        deepDiveEntry?.remediation_command ? `Command: ${deepDiveEntry.remediation_command}.` : null,
        deepDiveEntry?.remediation_execution_status ? `Execution status: ${deepDiveEntry.remediation_execution_status}.` : null,
      ]),
      action: (
        <>
          {deepDiveEntry?.remediation_command ? (
            <button
              className="assistant-button assistant-button--secondary"
              onClick={() => remediationMutation.mutate()}
              disabled={
                remediationMutation.isPending ||
                !deepDiveEntry.remediation_command ||
                !deepDiveEntry.remediation_target_host ||
                !canRunRemediation ||
                Boolean(safetyPanel)
              }
            >
              {remediationMutation.isPending || deepDiveEntry.remediation_execution_status === "running"
                ? "Running Remediation..."
                : "Run Remediation"}
            </button>
          ) : null}
          <button
            className="assistant-button assistant-button--secondary"
            onClick={() => runbookMutation.mutate()}
            disabled={runbookMutation.isPending || !selectedKey || !canManageIncidents}
          >
            {runbookMutation.isPending ? "Generating..." : "Generate Runbook"}
          </button>
          {selectedKey && runbookReady ? (
            <a className="shell__link shell__link--small" href={getRunbookDownloadUrl(selectedKey)}>
              Download
            </a>
          ) : null}
        </>
      ),
    },
    {
      key: "executive-summary",
      label: "Executive summary",
      meta: narrativeReady ? "narrative ready" : "review pending",
      status: isTerminalIncident(timelineQuery.data.status)
        ? "resolved"
        : deepDiveEntry?.remediation_execution_status === "verified"
          ? "completed"
          : narrativeMutation.isPending
            ? "active"
            : "pending",
      detail: joinDetail([
        compactText(
          narrativeState[selectedKey || ""] || timelineQuery.data.latest_narrative?.narrative || deepDiveEntry?.final_answer,
          "Prepare the executive summary once validation evidence lands.",
        ),
        runbookReady ? "Runbook artifact is available for download." : null,
      ]),
      action: (
        <>
          <button
            className="assistant-button assistant-button--secondary"
            onClick={() => narrativeMutation.mutate()}
            disabled={narrativeMutation.isPending || !selectedKey || !canManageIncidents}
          >
            {narrativeMutation.isPending ? "Generating..." : "Post-Incident Narrative"}
          </button>
          {selectedKey && narrativeReady ? (
            <a className="shell__link shell__link--small" href={getTimelineNarrativeDownloadUrl(selectedKey)}>
              Download
            </a>
          ) : null}
        </>
      ),
    },
  ] : [];
  const impactResources = timelineQuery.data ? buildImpactResources(timelineQuery.data, selectedAlert, deepDiveEntry, runbookReady) : [];

  return (
    <>
      <section className="hero-card hero-card--incidents">
        <div className="eyebrow">Incident Intelligence</div>
        <h2>Correlated Incident Workspace</h2>
        <p>
          This page uses the existing Django incident summaries and timelines and re-presents them as a cleaner investigation workflow.
        </p>
        {serviceFilter ? (
          <div className="hero-card__grid">
            <div className="hero-card__chip">Filtered Service: {serviceFilter}</div>
          </div>
        ) : null}
      </section>

      <section className="incidents-layout">
        <aside className="incidents-list">
          {(incidentList || []).map((incident) => (
            <article
              key={incident.incident_key}
              className={`incident-summary incident-summary--${String(incident.severity || "medium").toLowerCase().replace(/_/g, "-")}${selectedKey === incident.incident_key ? " is-active" : ""}`}
            >
              <button className="incident-summary__body" onClick={() => setActiveIncidentKey(incident.incident_key)}>
                <div className="eyebrow">{incident.severity}</div>
                <strong>{incident.title}</strong>
                <span>{incident.summary}</span>
                {incident.business_impact && (incident.business_impact.revenue_lost ?? 0) > 0 && (
                  <div className="incident-summary__impact" style={{ marginTop: '0.35rem', fontSize: '0.78rem', color: impactLevelColor(incident.business_impact.impact_level) }}>
                    <span style={{ fontWeight: 600 }}>{formatCurrency(incident.business_impact.revenue_lost)}</span>
                    <span style={{ opacity: 0.7, marginLeft: '0.35rem' }}>
                      ({incident.business_impact.failed_transactions} failed txns)
                    </span>
                  </div>
                )}
              </button>
              <div className="page-card__meta">
                <Link className="shell__link shell__link--small" to={`/graph/incident/${encodeURIComponent(incident.incident_key)}`}>
                  Incident Graph
                </Link>
                <Link
                  className="shell__link shell__link--small"
                  to={`/genai?incident=${encodeURIComponent(incident.incident_key)}&application=${encodeURIComponent(incident.application)}&service=${encodeURIComponent(incident.primary_service)}`}
                >
                  Investigate
                </Link>
              </div>
            </article>
          ))}
        </aside>
        <section className="incident-detail">
          {timelineQuery.data ? (
            <>
<<<<<<< Updated upstream
              <div className="incident-detail__hero">
                <div>
                  <div className="eyebrow">Incident</div>
                  <h3>{timelineQuery.data.title}</h3>
                  <p>{timelineQuery.data.reasoning || timelineQuery.data.summary}</p>
                  <div className="page-card__meta">
                    <Link
                      className="shell__link shell__link--small"
                      to={`/genai?incident=${encodeURIComponent(timelineQuery.data.incident_key)}&application=${encodeURIComponent(timelineQuery.data.application)}&service=${encodeURIComponent(timelineQuery.data.primary_service)}`}
                    >
                      Investigate In Assistant
                    </Link>
                    <Link className="shell__link shell__link--small" to={`/graph/incident/${encodeURIComponent(timelineQuery.data.incident_key)}`}>
                      Incident Graph
                    </Link>
                    {selectedAlert ? (
                      <Link className="shell__link shell__link--small" to={`/graph/${encodeURIComponent(selectedAlert.alert_id)}`}>
                        Open Graph
                      </Link>
                    ) : null}
                    {timelineQuery.data.sla && !timelineQuery.data.sla.response_acknowledged_at ? (
                      <button
                        className="shell__link shell__link--small"
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                        onClick={() => slaAckMutation.mutate()}
                        disabled={slaAckMutation.isPending}
                      >
                        {slaAckMutation.isPending ? "Acknowledging..." : "Acknowledge SLA"}
                      </button>
                    ) : null}
                    <button
                      className="shell__link shell__link--small"
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                      onClick={() => runbookMutation.mutate()}
                      disabled={runbookMutation.isPending || !selectedKey}
                    >
                      {runbookMutation.isPending ? "Generating Runbook..." : "Generate Runbook"}
                    </button>
                    <button
                      className="shell__link shell__link--small"
                      style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                      onClick={() => narrativeMutation.mutate()}
                      disabled={narrativeMutation.isPending || !selectedKey}
                    >
                      {narrativeMutation.isPending ? "Generating Narrative..." : "Post-Incident Narrative"}
                    </button>
                    {selectedKey && (timelineQuery.data.latest_runbook || runbookState[selectedKey]) ? (
                      <a className="shell__link shell__link--small" href={getRunbookDownloadUrl(selectedKey)}>
                        Download Runbook CSV
                      </a>
                    ) : null}
                    {selectedKey && (timelineQuery.data.latest_narrative?.narrative || narrativeState[selectedKey]) ? (
                      <a className="shell__link shell__link--small" href={getTimelineNarrativeDownloadUrl(selectedKey)}>
                        Download Narrative CSV
                      </a>
                    ) : null}
                  </div>
                  <div className="incident-detail__stats">
                    <div><span>Status</span><strong>{timelineQuery.data.status}</strong></div>
                    <div><span>Service</span><strong>{timelineQuery.data.primary_service}</strong></div>
                    <div><span>Blast Radius</span><strong>{timelineQuery.data.blast_radius?.length || 0}</strong></div>
                    {timelineQuery.data.sla ? (
                      <>
                        <div>
                          <span>Priority</span>
                          <strong style={{ color: slaBadgeColor(timelineQuery.data.sla) }}>
                            {timelineQuery.data.sla.priority}
                            {timelineQuery.data.sla.breached ? " ⚠ BREACHED" : ""}
                          </strong>
                        </div>
                        <div>
                          <span>Response SLA</span>
                          <strong style={{ color: slaBadgeColor(timelineQuery.data.sla) }}>
                            {timelineQuery.data.sla.response_acknowledged_at
                              ? "✓ Acked"
                              : formatSlaMinutes(timelineQuery.data.sla.response_remaining_minutes)}
                          </strong>
                        </div>
                        <div>
                          <span>Resolution SLA</span>
                          <strong style={{ color: slaBadgeColor(timelineQuery.data.sla) }}>
                            {formatSlaMinutes(timelineQuery.data.sla.resolution_remaining_minutes)}
                          </strong>
                        </div>
                      </>
                    ) : null}
                    {timelineQuery.data.business_impact && (timelineQuery.data.business_impact.revenue_lost ?? 0) > 0 && (
                      <>
                        <div>
                          <span>Revenue Impact</span>
                          <strong style={{ color: impactLevelColor(timelineQuery.data.business_impact.impact_level) }}>
                            {formatCurrency(timelineQuery.data.business_impact.revenue_lost)}
                          </strong>
                        </div>
                        <div>
                          <span>Failed Txns</span>
                          <strong>{timelineQuery.data.business_impact.failed_transactions}</strong>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
=======
              <IncidentVisualJourney
                incident={timelineQuery.data}
                stages={journeyStages}
                resources={impactResources}
                graphUrl={incidentGraphUrl}
              />
              {(timelineQuery.data.related_incidents || []).length > 0 ? (
                <article className="incident-related">
                  <div>
                    <div className="eyebrow">Correlation</div>
                    <h3>Related Incidents</h3>
                  </div>
                  <div className="incident-related__list">
                    {(timelineQuery.data.related_incidents || []).map((related) => (
                      <button
                        key={related.incident_key}
                        className="incident-related__item"
                        onClick={() => setActiveIncidentKey(related.incident_key)}
                      >
                        <span>{related.incident_number || related.incident_key}</span>
                        <strong>{related.title}</strong>
                        <small>{related.score}% · {(related.reasons || []).map((reason) => reason.replace(/_/g, " ")).join(", ")}</small>
                      </button>
                    ))}
                  </div>
                </article>
              ) : null}
              {(timelineQuery.data.external_tickets || []).length > 0 ? (
                <article className="incident-related">
                  <div>
                    <div className="eyebrow">Writeback</div>
                    <h3>External Tickets</h3>
                  </div>
                  <div className="incident-related__list">
                    {(timelineQuery.data.external_tickets || []).map((ticket) => (
                      <a
                        key={ticket.ticket_id}
                        className="incident-related__item"
                        href={ticket.external_url || undefined}
                        target={ticket.external_url ? "_blank" : undefined}
                        rel="noreferrer"
                      >
                        <span>{ticket.integration_name}</span>
                        <strong>{ticket.external_key || ticket.external_id || ticket.status}</strong>
                        <small>{ticket.status} · {ticket.message || ticket.integration_type}</small>
                      </a>
                    ))}
                  </div>
                </article>
              ) : null}
>>>>>>> Stashed changes
              <div className="incident-timeline-list">
                {deepDiveEntry ? (
                  <article className="incident-deep-dive incident-deep-dive--investigation">
                    <div className="eyebrow">Secondary AI Analysis</div>
                    <h3>Diagnostic Deep Dive</h3>
                    <p>
                      Run the recommended command against the target host and send the output back through AI for a deeper RCA conclusion.
                    </p>
                    <div className="incident-deep-dive__grid">
                      <div className="incident-deep-dive__card">
                        <span>Target Host</span>
                        <strong>{deepDiveEntry.target_host || "Unavailable"}</strong>
                        {deepDiveEntry.target_type ? <small>{deepDiveEntry.target_type.replace(/_/g, " ")}</small> : null}
                      </div>
                      <div className="incident-deep-dive__card">
                        <span>Status</span>
                        <strong>{deepDiveEntry.execution_status || "pending"}</strong>
                      </div>
                      <div className="incident-deep-dive__card incident-deep-dive__card--wide">
                        <span>Suggested Command</span>
                        <code>{deepDiveEntry.diagnostic_command || "No command suggested yet."}</code>
                      </div>
                    </div>
                    <div className="incident-deep-dive__toolbar">
                      <button
                        className="assistant-button"
                        onClick={() => executeMutation.mutate()}
                        disabled={executeMutation.isPending || !deepDiveEntry.diagnostic_command || !deepDiveEntry.target_host}
                      >
                        {executeMutation.isPending || deepDiveEntry.execution_status === "running" ? "Running..." : "Run Deep Dive"}
                      </button>
                      <div className="incident-deep-dive__toolbar-actions">
                        {timelineQuery.data?.incident_key ? (
                          <Link className="shell__link shell__link--small" to={`/investigations?incident_key=${encodeURIComponent(timelineQuery.data.incident_key)}`}>
                            Open Investigation
                          </Link>
                        ) : null}
                        {deepDiveEntry.target_host ? (
                          <Link className="shell__link shell__link--small" to={`/genai?target_host=${encodeURIComponent(deepDiveEntry.target_host)}`}>
                            Open In Assistant
                          </Link>
                        ) : null}
                      </div>
                      {deepDiveEntry.last_execution_at ? (
                        <code>last-run:{new Date(deepDiveEntry.last_execution_at).toLocaleString()}</code>
                      ) : null}
                    </div>
                    <div className="incident-deep-dive__evidence">
                      <DecisionPanel meta={deepDiveEntry} />
                      <article className="incident-deep-dive__panel">
                        <strong>Initial Recommendation</strong>
                        <p>{deepDiveEntry.initial_ai_reasoning || deepDiveEntry.initial_ai_diagnosis || deepDiveEntry.summary || "No initial recommendation available."}</p>
                      </article>
                      <article className="incident-deep-dive__panel">
                        <strong>Post-Command AI Analysis</strong>
                        <p>{deepDiveEntry.post_command_ai_analysis || deepDiveEntry.final_answer || "No secondary AI analysis yet. Run the deep-dive command to generate it."}</p>
                      </article>
                      {deepDiveEntry.analysis_sections?.resolution ? (
                        <article className="incident-deep-dive__panel">
                          <strong>Resolution</strong>
                          <p>{deepDiveEntry.analysis_sections.resolution}</p>
                        </article>
                      ) : null}
                      {(deepDiveEntry.analysis_sections?.remediation_steps || []).length ? (
                        <article className="incident-deep-dive__panel">
                          <strong>Remediation</strong>
                          <ul>
                            {deepDiveEntry.analysis_sections?.remediation_steps?.map((step, index) => (
                              <li key={`remediation-${index}`}>{step}</li>
                            ))}
                          </ul>
                        </article>
                      ) : null}
                      {deepDiveEntry.remediation_command ? (
                        <article className="incident-deep-dive__panel">
                          <strong>Remediation Command</strong>
                          <p>{deepDiveEntry.remediation_why || "Apply the recommended fix once you are ready."}</p>
                          <code>{deepDiveEntry.remediation_command}</code>
                          <div className="page-card__meta">
                            <span>Target: {deepDiveEntry.remediation_target_host || deepDiveEntry.target_host || "Unavailable"}</span>
                            {deepDiveEntry.remediation_requires_approval ? <span>Approval gate ready</span> : null}
                          </div>
                          <div className="page-card__meta">
                            <button
                              className="assistant-button assistant-button--secondary"
                              onClick={() => remediationMutation.mutate()}
                              disabled={
                                remediationMutation.isPending ||
                                !deepDiveEntry.remediation_command ||
                                !deepDiveEntry.remediation_target_host
                              }
                            >
                              {remediationMutation.isPending || deepDiveEntry.remediation_execution_status === "running"
                                ? "Running Remediation..."
                                : "Run Remediation"}
                            </button>
                            <span>Status: {deepDiveEntry.remediation_execution_status || "pending"}</span>
                            {deepDiveEntry.remediation_last_execution_at ? (
                              <code>last-run:{new Date(deepDiveEntry.remediation_last_execution_at).toLocaleString()}</code>
                            ) : null}
                          </div>
                        </article>
                      ) : null}
                      {deepDiveEntry.post_remediation_ai_analysis ? (
                        <article className="incident-deep-dive__panel">
                          <strong>Post-Remediation AI Analysis</strong>
                          <p>{deepDiveEntry.post_remediation_ai_analysis}</p>
                        </article>
                      ) : null}
                      {deepDiveEntry.remediation_output ? (
                        <article className="incident-deep-dive__panel">
                          <strong>Remediation Output</strong>
                          <pre>{deepDiveEntry.remediation_output}</pre>
                        </article>
                      ) : null}
                      {(deepDiveEntry.analysis_sections?.validation_steps || []).length ? (
                        <article className="incident-deep-dive__panel">
                          <strong>Validation</strong>
                          <ul>
                            {deepDiveEntry.analysis_sections?.validation_steps?.map((step, index) => (
                              <li key={`validation-${index}`}>{step}</li>
                            ))}
                          </ul>
                        </article>
                      ) : null}
                      <article className="incident-deep-dive__panel">
                        <strong>Command Output</strong>
                        <pre>{deepDiveEntry.command_output || "Command output will appear here after execution."}</pre>
                      </article>
                    </div>
                  </article>
                ) : null}
                {timelineQuery.data.timeline.map((item, index) => (
                  <article key={`${item.created_at}-${index}`} className="incident-timeline-item">
                    <div className="incident-timeline-item__time">{new Date(item.created_at).toLocaleString()}</div>
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.detail}</p>
                    </div>
                  </article>
                ))}

                {/* M4 — Post-Incident Narrative */}
                {selectedKey && narrativeState[selectedKey] ? (
                  <article className="incident-deep-dive">
                    <div className="eyebrow">Post-Incident Review</div>
                    <h3>Timeline Narrative</h3>
                    <div className="incident-deep-dive__evidence">
                      <article className="incident-deep-dive__panel">
                        <strong>Chronological Summary</strong>
                        <p style={{ whiteSpace: "pre-wrap" }}>{narrativeState[selectedKey]}</p>
                      </article>
                    </div>
                  </article>
                ) : null}

                {/* M6 — Runbook */}
                {selectedKey && runbookState[selectedKey] ? (
                  <article className="incident-deep-dive">
                    <div className="eyebrow">Knowledge Base</div>
                    <h3>{runbookState[selectedKey]!.title}</h3>
                    <p style={{ fontSize: "0.8rem", color: "var(--color-muted)" }}>
                      Saved to Knowledge Base (id: {runbookState[selectedKey]!.runbook_id})
                    </p>
                    <div className="incident-deep-dive__evidence">
                      <article className="incident-deep-dive__panel">
                        <strong>Runbook Content</strong>
                        <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>{runbookState[selectedKey]!.content}</pre>
                      </article>
                    </div>
                  </article>
                ) : null}
              </div>
            </>
          ) : (
            <section className="page-card">
              <div className="eyebrow">Loading</div>
              <h2>Select an incident</h2>
              <p>Incident details will appear here.</p>
            </section>
          )}
        </section>
      </section>
    </>
  );
}
