import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { executeDiagnosticCommand, fetchIncidentTimeline, fetchRecentAlerts, fetchRecentIncidents } from "../lib/api";
import { useRefreshInterval } from "../lib/refresh";

export function IncidentsPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [activeIncidentKey, setActiveIncidentKey] = useState<string | undefined>(undefined);
  const [executionState, setExecutionState] = useState<Record<string, Record<string, unknown>>>({});
  const [autoExecuted, setAutoExecuted] = useState<Record<string, boolean>>({});
  const serviceFilter = searchParams.get("service");
  const { refreshMs } = useRefreshInterval();
  const incidentsQuery = useQuery({
    queryKey: ["recent-incidents"],
    queryFn: fetchRecentIncidents,
    refetchInterval: refreshMs,
  });

  const alertsQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    refetchInterval: refreshMs,
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
    final_answer?: string;
    analysis_sections?: {
      root_cause?: string;
      evidence?: string;
      impact?: string;
      resolution?: string;
      remediation_steps?: string[];
      validation_steps?: string[];
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

  return (
    <>
      <section className="hero-card">
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
              className={`incident-summary${selectedKey === incident.incident_key ? " is-active" : ""}`}
            >
              <button className="incident-summary__body" onClick={() => setActiveIncidentKey(incident.incident_key)}>
                <div className="eyebrow">{incident.severity}</div>
                <strong>{incident.title}</strong>
                <span>{incident.summary}</span>
              </button>
              <div className="page-card__meta">
                <Link className="shell__link shell__link--small" to={`/graph/incident/${encodeURIComponent(incident.incident_key)}`}>
                  Incident Graph
                </Link>
                <Link
                  className="shell__link shell__link--small"
                  to={`/assistant?incident=${encodeURIComponent(incident.incident_key)}&application=${encodeURIComponent(incident.application)}&service=${encodeURIComponent(incident.primary_service)}`}
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
                      to={`/assistant?incident=${encodeURIComponent(timelineQuery.data.incident_key)}&application=${encodeURIComponent(timelineQuery.data.application)}&service=${encodeURIComponent(timelineQuery.data.primary_service)}`}
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
                  </div>
                </div>
                <div className="incident-detail__stats">
                  <div><span>Status</span><strong>{timelineQuery.data.status}</strong></div>
                  <div><span>Service</span><strong>{timelineQuery.data.primary_service}</strong></div>
                  <div><span>Blast Radius</span><strong>{timelineQuery.data.blast_radius?.length || 0}</strong></div>
                </div>
              </div>
              <div className="incident-timeline-list">
                {deepDiveEntry ? (
                  <article className="incident-deep-dive">
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
                    <div className="page-card__meta">
                      <button
                        className="assistant-button"
                        onClick={() => executeMutation.mutate()}
                        disabled={executeMutation.isPending || !deepDiveEntry.diagnostic_command || !deepDiveEntry.target_host}
                      >
                        {executeMutation.isPending || deepDiveEntry.execution_status === "running" ? "Running..." : "Run Deep Dive"}
                      </button>
                      {deepDiveEntry.last_execution_at ? (
                        <code>last-run:{new Date(deepDiveEntry.last_execution_at).toLocaleString()}</code>
                      ) : null}
                    </div>
                    <div className="incident-deep-dive__evidence">
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
