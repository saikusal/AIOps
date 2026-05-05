import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { executeDiagnosticCommand, fetchFleetTargetDetail, type CommandExecutionResult, type FleetDiscoveredService, type TypedAction } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function healthTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "healthy" || normalized === "connected" || normalized === "running" || normalized === "observed") return "healthy";
  if (normalized === "warning" || normalized === "degraded") return "warning";
  return "critical";
}

function runtimeLabel(containerRuntime: string) {
  return containerRuntime === "docker" ? "Docker runtime" : "Host runtime";
}

type WorkloadActionKind = "logs" | "inspect" | "restart";

type WorkloadActionState = {
  status: "idle" | "running" | "completed" | "failed";
  result?: CommandExecutionResult;
  error?: string;
};

function actionLabel(action: WorkloadActionKind) {
  if (action === "logs") return "Logs";
  if (action === "inspect") return "Inspect";
  return "Restart";
}

function ownerString(owner: Record<string, unknown>) {
  return String(owner.repository || owner.application_name || "").trim();
}

export function FleetTargetPage() {
  const { targetId = "" } = useParams();
  const refreshQueryOptions = useRefreshQueryOptions();
  const [actionState, setActionState] = useState<Record<string, WorkloadActionState>>({});
  const targetQuery = useQuery({
    queryKey: ["fleet-target-detail", targetId],
    queryFn: () => fetchFleetTargetDetail(targetId),
    enabled: Boolean(targetId),
    ...refreshQueryOptions,
  });

  const workloadActionMutation = useMutation({
    mutationFn: async ({
      workload,
      action,
      targetHost,
    }: {
      workload: FleetDiscoveredService;
      action: WorkloadActionKind;
      targetHost: string;
    }) => {
      const containerName = workload.container_name || workload.service_name;
      const command =
        action === "logs"
          ? `docker logs --tail 200 ${containerName}`
          : action === "inspect"
            ? `docker inspect ${containerName}`
            : `docker restart ${containerName}`;
      const typedAction: TypedAction | undefined =
        action === "restart"
          ? {
              action: "restart_service",
              target: workload.service_name,
              target_host: targetHost,
              service: workload.service_name,
              reason: `Restart Docker workload ${containerName} on the target host.`,
              requires_approval: true,
              command,
              validation_plan: [
                `Confirm ${workload.service_name} returns healthy after the restart.`,
                "Review recent logs for recurring error signatures.",
                "Verify alerts clear and latency/error-rate recover.",
              ],
              metadata: { executor: "docker", container_name: containerName },
            }
          : {
              action: "diagnostic",
              target: workload.service_name,
              target_host: targetHost,
              service: workload.service_name,
              reason: `Collect Docker ${action} evidence for ${containerName}.`,
              command,
              validation_plan: ["Review the command output before taking any remediation action."],
              metadata: { executor: "docker", container_name: containerName },
            };
      return executeDiagnosticCommand({
        command,
        original_question:
          action === "restart"
            ? `Restart Docker workload ${containerName} on ${targetHost} and verify recovery.`
            : `Collect Docker ${action} evidence for workload ${containerName} on ${targetHost}.`,
        target_host: targetHost,
        execution_type: action === "restart" ? "remediation" : "diagnostic",
        typed_action: typedAction,
        dry_run: false,
      });
    },
  });

  const runWorkloadAction = async (workload: FleetDiscoveredService, action: WorkloadActionKind) => {
    const workloadKey = `${workload.container_name || workload.service_name}:${action}`;
    const targetHost = targetQuery.data?.hostname || targetQuery.data?.name || "";
    if (!targetHost) return;
    setActionState((current: Record<string, WorkloadActionState>) => ({
      ...current,
      [workloadKey]: { status: "running" },
    }));
    try {
      const result = await workloadActionMutation.mutateAsync({ workload, action, targetHost });
      setActionState((current: Record<string, WorkloadActionState>) => ({
        ...current,
        [workloadKey]: { status: "completed", result },
      }));
    } catch (error) {
      setActionState((current: Record<string, WorkloadActionState>) => ({
        ...current,
        [workloadKey]: {
          status: "failed",
          error: error instanceof Error ? error.message : `Unable to run ${actionLabel(action)}.`,
        },
      }));
    }
  };

  if (targetQuery.isLoading) {
    return (
      <section className="page-card">
        <div className="eyebrow">Loading</div>
        <h2>Fetching target runtime detail</h2>
        <p>The control plane is loading the selected Fleet target.</p>
      </section>
    );
  }

  if (targetQuery.isError || !targetQuery.data) {
    return (
      <section className="page-card">
        <div className="eyebrow">Error</div>
        <h2>Unable to load target detail</h2>
        <p>Check that the Fleet target still exists and that the backend detail endpoint is reachable.</p>
        <div className="page-card__meta">
          <Link className="shell__link shell__link--small" to="/ingestion">
            Back To Fleet
          </Link>
        </div>
      </section>
    );
  }

  const target = targetQuery.data;

  return (
    <>
      <section className="hero-card hero-card--fleet">
        <div className="eyebrow">{target.target_type}</div>
        <h2>{target.name}</h2>
        <p>
          {target.hostname || target.ip_address || "unknown host"} · {target.environment} · {runtimeLabel(target.runtime_summary.container_runtime)}
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Collector {target.collector_status}</div>
          <div className="hero-card__chip">Services {target.discovered_service_count}</div>
          <div className="hero-card__chip">Docker {target.runtime_summary.docker_container_count}</div>
          <div className="hero-card__chip">Host Apps {target.runtime_summary.host_application_service_count}</div>
        </div>
        <div className="page-card__meta">
          <Link className="shell__link shell__link--small" to="/ingestion">
            Back To Fleet
          </Link>
          <Link className="shell__link shell__link--small" to={`/genai?target_host=${encodeURIComponent(target.hostname || target.name)}`}>
            Open In Assistant
          </Link>
        </div>
      </section>

      <section className="fleet-summary-grid">
        <article className="fleet-summary-card fleet-summary-card--primary">
          <span>Status</span>
          <strong>{target.status}</strong>
          <p>Overall target status reported by the control plane.</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--success">
          <span>Last heartbeat</span>
          <strong>{target.last_heartbeat || "not connected yet"}</strong>
          <p>Most recent heartbeat received from the installed target bundle.</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--accent">
          <span>Runtime</span>
          <strong>{runtimeLabel(target.runtime_summary.container_runtime)}</strong>
          <p>Detected runtime capability for this host.</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--primary">
          <span>Recent Actions</span>
          <strong>{target.recent_execution_history.length}</strong>
          <p>Recent diagnostic and remediation actions executed against this target.</p>
        </article>
      </section>

      <section className="fleet-grid">
        <article className={`fleet-card fleet-card--${healthTone(target.status)}`}>
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Host Detail</div>
              <h3>{target.profile_name}</h3>
              <p>{target.os_name || "Linux"} {target.os_version || ""}</p>
            </div>
            <span className={`fleet-status fleet-status--${healthTone(target.status)}`}>{target.status}</span>
          </div>
          <div className="fleet-card__meta-grid">
            <div><span>Hostname</span><strong>{target.hostname || "unknown"}</strong></div>
            <div><span>IP address</span><strong>{target.ip_address || "unknown"}</strong></div>
            <div><span>Collector</span><strong>{target.collector_status}</strong></div>
            <div><span>Docker runtime</span><strong>{target.runtime_summary.docker_available ? "available" : "not detected"}</strong></div>
          </div>
          <div className="fleet-card__components">
            {target.components.map((component) => (
              <span key={`${target.target_id}-${component.name}`} className={`fleet-pill fleet-pill--${component.status.toLowerCase()}`}>
                {component.name}: {component.status}
              </span>
            ))}
          </div>
          {target.runtime_summary.docker_error ? (
            <div className="checklist-panel" style={{ marginTop: "1rem" }}>
              <div className="eyebrow">Docker Discovery Note</div>
              <p>{target.runtime_summary.docker_error}</p>
            </div>
          ) : null}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Docker Workloads</div>
              <h3>{target.runtime_summary.docker_container_count} containers</h3>
              <p>Container workloads discovered from the host runtime.</p>
            </div>
          </div>
          {target.docker_workloads.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.docker_workloads.map((workload) => (
                  <li key={`${workload.container_name || workload.service_name}-${workload.port || "na"}`}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                      <div>
                        <strong>{workload.service_name}</strong>
                        <span>
                          {workload.container_name ? ` · ${workload.container_name}` : ""}
                          {workload.port ? ` · :${workload.port}` : ""}
                          {workload.image ? ` · ${workload.image}` : ""}
                          {` · ${workload.status}`}
                        </span>
                        {ownerString(workload.owner || {}) ? (
                          <div>
                            <small>Owner: {ownerString(workload.owner || {})}</small>
                          </div>
                        ) : null}
                      </div>
                      <div className="page-card__meta">
                        <button className="shell__link shell__link--small" onClick={() => void runWorkloadAction(workload, "logs")}>
                          Logs
                        </button>
                        <button className="shell__link shell__link--small" onClick={() => void runWorkloadAction(workload, "inspect")}>
                          Inspect
                        </button>
                        <button className="shell__link shell__link--small" onClick={() => void runWorkloadAction(workload, "restart")}>
                          Restart
                        </button>
                        {(workload.owner || {}).repository ? (
                          <Link className="shell__link shell__link--small" to={`/code-context?repository=${encodeURIComponent(String((workload.owner || {}).repository))}`}>
                            Code Context
                          </Link>
                        ) : (
                          <Link className="shell__link shell__link--small" to={`/genai?service=${encodeURIComponent(workload.service_name)}`}>
                            Code Lookup
                          </Link>
                        )}
                      </div>
                    </div>
                    {(() => {
                      const logsState = actionState[`${workload.container_name || workload.service_name}:logs`];
                      const inspectState = actionState[`${workload.container_name || workload.service_name}:inspect`];
                      const restartState = actionState[`${workload.container_name || workload.service_name}:restart`];
                      const activeState = restartState || inspectState || logsState;
                      if (!activeState) return null;
                      return (
                        <div className="checklist-panel" style={{ marginTop: "0.75rem" }}>
                          <div className="eyebrow">
                            {activeState.status === "running" ? "Running Action" : activeState.result?.execution_status || activeState.status}
                          </div>
                          <p>{activeState.error || activeState.result?.final_answer || "Action completed."}</p>
                          {activeState.result?.typed_action_summary ? <p>{activeState.result.typed_action_summary}</p> : null}
                          {activeState.result?.command_output ? (
                            <pre style={{ whiteSpace: "pre-wrap", overflowX: "auto" }}>
                              {activeState.result.command_output.slice(0, 4000)}
                            </pre>
                          ) : null}
                        </div>
                      );
                    })()}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>No Docker workloads reported for this host yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Host Application Services</div>
              <h3>{target.runtime_summary.host_application_service_count} services</h3>
              <p>Non-containerized Linux services that look application-owned or code-bound.</p>
            </div>
          </div>
          {target.host_application_services.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.host_application_services.map((service) => (
                  <li key={`${service.service_name}-${service.port || "na"}`}>
                    {service.service_name}
                    {service.port ? ` · :${service.port}` : ""}
                    {service.process_name ? ` · ${service.process_name}` : ""}
                    {` · ${service.status}`}
                    {service.owner?.repository ? ` · ${String(service.owner.repository)}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>No application-oriented host services reported for this target yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Supporting Host Services</div>
              <h3>{target.runtime_summary.host_support_service_count} services</h3>
              <p>Supporting Linux processes and systemd-managed services discovered on the host.</p>
            </div>
          </div>
          {target.host_support_services.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.host_support_services.map((service) => (
                  <li key={`${service.service_name}-${service.port || "na"}`}>
                    {service.service_name}
                    {service.port ? ` · :${service.port}` : ""}
                    {service.process_name ? ` · ${service.process_name}` : ""}
                    {` · ${service.status}`}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>No supporting host services reported for this target yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Recent Actions</div>
              <h3>{target.recent_execution_history.length} entries</h3>
              <p>Recent executions recorded by the control plane for this target.</p>
            </div>
          </div>
          {target.recent_execution_history.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.recent_execution_history.map((entry) => (
                  <li key={entry.intent_id}>
                    <strong>{entry.execution_type}</strong>
                    {entry.service ? ` · ${entry.service}` : ""}
                    {entry.action_type ? ` · ${entry.action_type}` : ""}
                    {` · ${entry.status}`}
                    {entry.dry_run ? " · dry run" : ""}
                    {entry.requires_approval ? " · approval" : ""}
                    {entry.typed_action_summary ? ` · ${entry.typed_action_summary}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>No recent action history recorded for this target yet.</p>
          )}
        </article>
      </section>
    </>
  );
}
