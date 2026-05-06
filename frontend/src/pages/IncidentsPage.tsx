import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
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
