import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  applyFleetTargetConfig,
  executeDiagnosticCommand,
  fetchFleetTargetConfig,
  fetchFleetTargetDetail,
  fetchPolicyProfiles,
  updateFleetTargetConfig,
  type CommandExecutionResult,
  type FleetDiscoveredService,
  type FleetTargetConfigPayload,
  type TypedAction,
} from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function healthTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "healthy" || normalized === "connected" || normalized === "running" || normalized === "observed") return "healthy";
  if (normalized === "warning" || normalized === "degraded") return "warning";
  return "critical";
}

function runtimeLabel(containerRuntime: string) {
  if (containerRuntime === "docker") return "Docker runtime";
  if (containerRuntime === "kubernetes") return "Kubernetes runtime";
  return "Host runtime";
}

type WorkloadActionKind = "logs" | "inspect" | "restart" | "describe";

type WorkloadActionState = {
  status: "idle" | "running" | "completed" | "failed";
  result?: CommandExecutionResult;
  error?: string;
};

function actionLabel(action: WorkloadActionKind) {
  if (action === "logs") return "Logs";
  if (action === "inspect") return "Inspect";
  if (action === "describe") return "Describe";
  return "Restart";
}

function verificationTone(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "resolved") return "healthy";
  if (normalized === "partially_improved" || normalized === "unchanged" || normalized === "inconclusive") return "warning";
  return "critical";
}

function ownerString(owner: Record<string, unknown>) {
  return String(owner.repository || owner.application_name || "").trim();
}

function workloadRuntimeKind(workload: FleetDiscoveredService) {
  return String(workload.runtime || workload.metadata_json?.runtime || "").trim();
}

type ConfigEditorState = {
  role: string;
  environment: string;
  runtime_type: string;
  hostname: string;
  os_family: string;
  docker_available: boolean;
  systemd_available: boolean;
  primary_restart_mode: string;
  notes: string;
  policy_profile_slug: string;
  service_name: string;
  service_kind: string;
  systemd_unit: string;
  container_name: string;
  process_name: string;
  port: string;
  log_source_type: string;
  journal_unit: string;
  file_path: string;
  log_container_name: string;
  stream_family: string;
  parser_name: string;
  shipper_type: string;
  opensearch_pipeline: string;
};

function buildConfigEditorState(config?: FleetTargetConfigPayload): ConfigEditorState {
  const runtime = config?.runtime_profile;
  const policySlug = config?.policy_assignment?.policy_profile?.slug || "";
  const primaryBinding = config?.service_bindings?.find((item) => item.is_primary) || config?.service_bindings?.[0];
  const primaryLogSource = config?.log_sources?.find((item) => item.is_primary) || config?.log_sources?.[0];
  return {
    role: runtime?.role || "app",
    environment: runtime?.environment || "prod",
    runtime_type: runtime?.runtime_type || "systemd",
    hostname: runtime?.hostname || "",
    os_family: runtime?.os_family || "",
    docker_available: Boolean(runtime?.docker_available),
    systemd_available: Boolean(runtime?.systemd_available),
    primary_restart_mode: runtime?.primary_restart_mode || "unknown",
    notes: runtime?.notes || "",
    policy_profile_slug: policySlug,
    service_name: primaryBinding?.service_name || "",
    service_kind: primaryBinding?.service_kind || "systemd",
    systemd_unit: primaryBinding?.systemd_unit || "",
    container_name: primaryBinding?.container_name || "",
    process_name: primaryBinding?.process_name || "",
    port: primaryBinding?.port != null ? String(primaryBinding.port) : "",
    log_source_type: primaryLogSource?.source_type || "journald",
    journal_unit: primaryLogSource?.journal_unit || "",
    file_path: primaryLogSource?.file_path || "",
    log_container_name: primaryLogSource?.container_name || "",
    stream_family: primaryLogSource?.stream_family || config?.log_ingestion_profile?.stream_family || "",
    parser_name: primaryLogSource?.parser_name || "",
    shipper_type: config?.log_ingestion_profile?.shipper_type || "fluent-bit",
    opensearch_pipeline: config?.log_ingestion_profile?.opensearch_pipeline || "",
  };
}

export function FleetTargetPage() {
  const { targetId = "" } = useParams();
  const queryClient = useQueryClient();
  const refreshQueryOptions = useRefreshQueryOptions();
  const [actionState, setActionState] = useState<Record<string, WorkloadActionState>>({});
  const [configEditor, setConfigEditor] = useState<ConfigEditorState | null>(null);
  const targetQuery = useQuery({
    queryKey: ["fleet-target-detail", targetId],
    queryFn: () => fetchFleetTargetDetail(targetId),
    enabled: Boolean(targetId),
    ...refreshQueryOptions,
  });
  const configQuery = useQuery({
    queryKey: ["fleet-target-config", targetId],
    queryFn: () => fetchFleetTargetConfig(targetId),
    enabled: Boolean(targetId),
    ...refreshQueryOptions,
  });
  const policyProfilesQuery = useQuery({
    queryKey: ["fleet-policy-profiles", targetQuery.data?.target_type || "", configEditor?.runtime_type || ""],
    queryFn: () => fetchPolicyProfiles(targetQuery.data?.target_type || "", configEditor?.runtime_type || ""),
    enabled: Boolean(targetQuery.data?.target_type && configEditor?.runtime_type),
  });

  useEffect(() => {
    if (configQuery.data) {
      setConfigEditor(buildConfigEditorState(configQuery.data));
    }
  }, [configQuery.data]);

  const policyProfiles = policyProfilesQuery.data || [];
  const configStatus = useMemo(() => {
    if (!configQuery.data) return "";
    return `policy v${configQuery.data.config_version.policy} · logs v${configQuery.data.config_version.log_ingestion}`;
  }, [configQuery.data]);

  const saveConfigMutation = useMutation({
    mutationFn: async (editor: ConfigEditorState) =>
      updateFleetTargetConfig(targetId, {
        runtime_profile: {
          role: editor.role,
          environment: editor.environment,
          runtime_type: editor.runtime_type,
          hostname: editor.hostname,
          os_family: editor.os_family,
          docker_available: editor.docker_available,
          systemd_available: editor.systemd_available,
          primary_restart_mode: editor.primary_restart_mode,
          notes: editor.notes,
        },
        policy_profile_slug: editor.policy_profile_slug,
        service_bindings: [
          {
            service_name: editor.service_name,
            service_kind: editor.service_kind,
            systemd_unit: editor.systemd_unit,
            container_name: editor.container_name,
            process_name: editor.process_name,
            port: editor.port ? Number(editor.port) : null,
            is_primary: true,
          },
        ],
        log_sources: [
          {
            service_name: editor.service_name,
            source_type: editor.log_source_type,
            journal_unit: editor.journal_unit,
            file_path: editor.file_path,
            container_name: editor.log_container_name,
            stream_family: editor.stream_family,
            parser_name: editor.parser_name,
            shipper_type: editor.shipper_type,
            is_primary: true,
          },
        ],
        log_ingestion_profile: {
          shipper_type: editor.shipper_type,
          stream_family: editor.stream_family,
          opensearch_pipeline: editor.opensearch_pipeline,
          record_metadata_json: {
            service_name: editor.service_name,
            environment: editor.environment,
            runtime_type: editor.runtime_type,
            component_role: editor.role,
          },
        },
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["fleet-target-config", targetId] }),
        queryClient.invalidateQueries({ queryKey: ["fleet-target-detail", targetId] }),
      ]);
    },
  });

  const applyConfigMutation = useMutation({
    mutationFn: async () => applyFleetTargetConfig(targetId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["fleet-target-config", targetId] }),
        queryClient.invalidateQueries({ queryKey: ["fleet-target-detail", targetId] }),
      ]);
    },
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
      const runtime = workloadRuntimeKind(workload);
      const metadata = workload.metadata_json || {};
      const namespace = String(metadata.namespace || "default");
      const resourceKind = String(metadata.resource_kind || "deployment").toLowerCase();
      const workloadName = workload.service_name;
      const command =
        runtime === "kubernetes"
          ? action === "logs"
            ? `kubectl logs -n ${namespace} ${resourceKind}/${workloadName} --tail=200`
            : action === "describe"
              ? `kubectl describe ${resourceKind} -n ${namespace} ${workloadName}`
              : `kubectl rollout restart ${resourceKind}/${workloadName} -n ${namespace}`
          : action === "logs"
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
              metadata:
                runtime === "kubernetes"
                  ? {
                      executor: "kubernetes",
                      resource_kind: resourceKind,
                      resource_name: workloadName,
                      namespace,
                    }
                  : { executor: "docker", container_name: containerName },
            }
          : {
              action: "diagnostic",
              target: workload.service_name,
              target_host: targetHost,
              service: workload.service_name,
              reason:
                runtime === "kubernetes"
                  ? `Collect Kubernetes ${action === "describe" ? "describe" : action} evidence for ${workloadName}.`
                  : `Collect Docker ${action} evidence for ${containerName}.`,
              command,
              validation_plan: ["Review the command output before taking any remediation action."],
              metadata:
                runtime === "kubernetes"
                  ? { executor: "kubernetes", resource_kind: resourceKind, resource_name: workloadName, namespace }
                  : { executor: "docker", container_name: containerName },
            };
      return executeDiagnosticCommand({
        command,
        original_question:
          action === "restart"
            ? runtime === "kubernetes"
              ? `Restart Kubernetes workload ${workloadName} in namespace ${namespace} on cluster ${targetHost} and verify recovery.`
              : `Restart Docker workload ${containerName} on ${targetHost} and verify recovery.`
            : runtime === "kubernetes"
              ? `Collect Kubernetes ${action === "describe" ? "describe" : action} evidence for workload ${workloadName} in namespace ${namespace} on cluster ${targetHost}.`
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
          <div className="hero-card__chip">
            {target.runtime_summary.container_runtime === "kubernetes"
              ? `Kubernetes ${target.runtime_summary.kubernetes_workload_count}`
              : `Docker ${target.runtime_summary.docker_container_count}`}
          </div>
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
            <div>
              <span>Runtime capability</span>
              <strong>
                {target.runtime_summary.container_runtime === "kubernetes"
                  ? "kubernetes"
                  : target.runtime_summary.docker_available
                    ? "docker"
                    : "host only"}
              </strong>
            </div>
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
              <div className="eyebrow">Target Configuration</div>
              <h3>Editable runtime and policy config</h3>
              <p>Update the saved Track 1 configuration without reinstalling the target bundle.</p>
            </div>
          </div>
          {configEditor ? (
            <>
              <div className="fleet-card__meta-grid">
                <div><span>Config versions</span><strong>{configStatus || "pending"}</strong></div>
                <div><span>Policy apply</span><strong>{target.policy_assignment?.last_apply_status || "unassigned"}</strong></div>
                <div><span>Log apply</span><strong>{target.log_ingestion_profile?.last_apply_status || "unassigned"}</strong></div>
                <div><span>Last apply</span><strong>{target.log_ingestion_profile?.last_applied_at || target.policy_assignment?.last_applied_at || "never"}</strong></div>
              </div>
              <div className="form-grid">
                <label className="form-field">
                  <span>Role</span>
                  <select value={configEditor.role} onChange={(event) => setConfigEditor((current) => current ? { ...current, role: event.target.value } : current)}>
                    <option value="app">Application</option>
                    <option value="db">Database</option>
                    <option value="cache">Cache</option>
                    <option value="gateway">Gateway</option>
                    <option value="custom">Custom</option>
                  </select>
                </label>
                <label className="form-field">
                  <span>Environment</span>
                  <select value={configEditor.environment} onChange={(event) => setConfigEditor((current) => current ? { ...current, environment: event.target.value } : current)}>
                    <option value="prod">Production</option>
                    <option value="staging">Staging</option>
                    <option value="dev">Development</option>
                    <option value="test">Test</option>
                  </select>
                </label>
                <label className="form-field">
                  <span>Runtime</span>
                  <select value={configEditor.runtime_type} onChange={(event) => setConfigEditor((current) => current ? { ...current, runtime_type: event.target.value } : current)}>
                    <option value="systemd">Systemd</option>
                    <option value="docker">Docker</option>
                    <option value="standalone">Standalone</option>
                    <option value="kubernetes">Kubernetes</option>
                    <option value="unknown">Unknown</option>
                  </select>
                </label>
                <label className="form-field">
                  <span>Policy profile</span>
                  <select value={configEditor.policy_profile_slug} onChange={(event) => setConfigEditor((current) => current ? { ...current, policy_profile_slug: event.target.value } : current)}>
                    {policyProfiles.map((profile) => (
                      <option key={profile.slug} value={profile.slug}>{profile.name}</option>
                    ))}
                  </select>
                </label>
                <label className="form-field">
                  <span>Primary service</span>
                  <input value={configEditor.service_name} onChange={(event) => setConfigEditor((current) => current ? { ...current, service_name: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Service kind</span>
                  <select value={configEditor.service_kind} onChange={(event) => setConfigEditor((current) => current ? { ...current, service_kind: event.target.value } : current)}>
                    <option value="systemd">Systemd</option>
                    <option value="docker_container">Docker container</option>
                    <option value="process">Process</option>
                    <option value="database">Database</option>
                    <option value="kubernetes_workload">Kubernetes workload</option>
                  </select>
                </label>
                <label className="form-field">
                  <span>Systemd unit</span>
                  <input value={configEditor.systemd_unit} onChange={(event) => setConfigEditor((current) => current ? { ...current, systemd_unit: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Container name</span>
                  <input value={configEditor.container_name} onChange={(event) => setConfigEditor((current) => current ? { ...current, container_name: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Process name</span>
                  <input value={configEditor.process_name} onChange={(event) => setConfigEditor((current) => current ? { ...current, process_name: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Port</span>
                  <input value={configEditor.port} onChange={(event) => setConfigEditor((current) => current ? { ...current, port: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Log source</span>
                  <select value={configEditor.log_source_type} onChange={(event) => setConfigEditor((current) => current ? { ...current, log_source_type: event.target.value } : current)}>
                    <option value="journald">Journald</option>
                    <option value="file">File</option>
                    <option value="docker">Docker</option>
                    <option value="kubernetes">Kubernetes</option>
                  </select>
                </label>
                <label className="form-field">
                  <span>Journald unit</span>
                  <input value={configEditor.journal_unit} onChange={(event) => setConfigEditor((current) => current ? { ...current, journal_unit: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>File path</span>
                  <input value={configEditor.file_path} onChange={(event) => setConfigEditor((current) => current ? { ...current, file_path: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Log container</span>
                  <input value={configEditor.log_container_name} onChange={(event) => setConfigEditor((current) => current ? { ...current, log_container_name: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Stream family</span>
                  <input value={configEditor.stream_family} onChange={(event) => setConfigEditor((current) => current ? { ...current, stream_family: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Parser</span>
                  <input value={configEditor.parser_name} onChange={(event) => setConfigEditor((current) => current ? { ...current, parser_name: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>Shipper</span>
                  <input value={configEditor.shipper_type} onChange={(event) => setConfigEditor((current) => current ? { ...current, shipper_type: event.target.value } : current)} />
                </label>
                <label className="form-field">
                  <span>OpenSearch pipeline</span>
                  <input value={configEditor.opensearch_pipeline} onChange={(event) => setConfigEditor((current) => current ? { ...current, opensearch_pipeline: event.target.value } : current)} />
                </label>
                <label className="form-field form-field--full">
                  <span>Notes</span>
                  <textarea rows={3} value={configEditor.notes} onChange={(event) => setConfigEditor((current) => current ? { ...current, notes: event.target.value } : current)} />
                </label>
              </div>
              <div className="action-row">
                <button className="action-button" onClick={() => configEditor && saveConfigMutation.mutate(configEditor)} disabled={saveConfigMutation.isPending}>
                  {saveConfigMutation.isPending ? "Saving..." : "Save Config"}
                </button>
                <button className="action-button action-button--secondary" onClick={() => applyConfigMutation.mutate()} disabled={applyConfigMutation.isPending}>
                  {applyConfigMutation.isPending ? "Requesting..." : "Request Agent Refresh"}
                </button>
                {saveConfigMutation.isError ? <p className="inline-error">{(saveConfigMutation.error as Error).message}</p> : null}
                {applyConfigMutation.isError ? <p className="inline-error">{(applyConfigMutation.error as Error).message}</p> : null}
              </div>
              {configQuery.data?.generated_configs?.fluent_bit?.enabled ? (
                <div className="code-panel">
                  <div className="eyebrow">Generated Fluent Bit Config</div>
                  <p>Suggested path: {configQuery.data.generated_configs.fluent_bit.path_hint}</p>
                  <pre>{configQuery.data.generated_configs.fluent_bit.config}</pre>
                </div>
              ) : (
                <div className="checklist-panel">
                  <div className="eyebrow">Generated Fluent Bit Config</div>
                  <p>No Fluent Bit config was generated yet. Add at least one configured log source and use `fluent-bit` as the shipper.</p>
                </div>
              )}
            </>
          ) : (
            <p>Loading saved target configuration...</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Configured Runtime</div>
              <h3>{target.runtime_profile?.runtime_type || "not configured"}</h3>
              <p>Saved runtime and operating model applied from the onboarding request.</p>
            </div>
          </div>
          {target.runtime_profile ? (
            <div className="fleet-card__meta-grid">
              <div><span>Role</span><strong>{target.runtime_profile.role}</strong></div>
              <div><span>Environment</span><strong>{target.runtime_profile.environment}</strong></div>
              <div><span>Restart mode</span><strong>{target.runtime_profile.primary_restart_mode}</strong></div>
              <div><span>Systemd</span><strong>{target.runtime_profile.systemd_available ? "available" : "no"}</strong></div>
              <div><span>Docker</span><strong>{target.runtime_profile.docker_available ? "available" : "no"}</strong></div>
              <div><span>Notes</span><strong>{target.runtime_profile.notes || "none"}</strong></div>
            </div>
          ) : (
            <p>No runtime profile has been saved for this target yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Execution Policy</div>
              <h3>{target.policy_assignment?.policy_profile?.name || "unassigned"}</h3>
              <p>Target-specific policy profile that scopes diagnostics and remediation.</p>
            </div>
          </div>
          {target.policy_assignment?.policy_profile ? (
            <div className="checklist-panel">
              <p>{target.policy_assignment.policy_profile.description}</p>
              <ul>
                <li>Runtime: {target.policy_assignment.policy_profile.runtime_type}</li>
                <li>Restart approval: {target.policy_assignment.policy_profile.requires_approval_for_restart ? "required" : "not required by profile"}</li>
                <li>Write-action approval: {target.policy_assignment.policy_profile.requires_approval_for_write_actions ? "required" : "not required by profile"}</li>
                <li>Sudo mode: {target.policy_assignment.policy_profile.sudo_mode}</li>
              </ul>
            </div>
          ) : (
            <p>No policy assignment has been applied to this target yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Service Bindings</div>
              <h3>{target.service_bindings.length} configured</h3>
              <p>Primary workload bindings the control plane should use before falling back to discovery.</p>
            </div>
          </div>
          {target.service_bindings.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.service_bindings.map((binding) => (
                  <li key={binding.binding_id}>
                    <strong>{binding.service_name}</strong>
                    {binding.service_kind ? ` · ${binding.service_kind}` : ""}
                    {binding.systemd_unit ? ` · ${binding.systemd_unit}` : ""}
                    {binding.container_name ? ` · ${binding.container_name}` : ""}
                    {binding.process_name ? ` · ${binding.process_name}` : ""}
                    {binding.port ? ` · :${binding.port}` : ""}
                    {binding.is_primary ? " · primary" : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>No configured service bindings were saved for this target yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Log Sources</div>
              <h3>{target.log_sources.length} configured</h3>
              <p>Centralized log source definitions and stream-family metadata from onboarding.</p>
            </div>
          </div>
          {target.log_sources.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.log_sources.map((source) => (
                  <li key={source.log_source_id}>
                    <strong>{source.source_type}</strong>
                    {source.journal_unit ? ` · ${source.journal_unit}` : ""}
                    {source.file_path ? ` · ${source.file_path}` : ""}
                    {source.container_name ? ` · ${source.container_name}` : ""}
                    {source.stream_family ? ` · ${source.stream_family}` : ""}
                    {source.shipper_type ? ` · ${source.shipper_type}` : ""}
                    {source.is_primary ? " · primary" : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p>No configured log sources were saved for this target yet.</p>
          )}
        </article>

        <article className="fleet-card fleet-card--healthy">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Log Ingestion</div>
              <h3>{target.log_ingestion_profile?.shipper_type || "not configured"}</h3>
              <p>Current centralized log shipping metadata applied to this target.</p>
            </div>
          </div>
          {target.log_ingestion_profile ? (
            <div className="fleet-card__meta-grid">
              <div><span>Stream family</span><strong>{target.log_ingestion_profile.stream_family || "unassigned"}</strong></div>
              <div><span>Pipeline</span><strong>{target.log_ingestion_profile.opensearch_pipeline || "default"}</strong></div>
              <div><span>Config version</span><strong>{target.log_ingestion_profile.config_version}</strong></div>
              <div><span>Apply status</span><strong>{target.log_ingestion_profile.last_apply_status}</strong></div>
            </div>
          ) : (
            <p>No log ingestion profile has been applied to this target yet.</p>
          )}
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
                          {activeState.result?.verification ? (
                            <div className={`checklist-panel checklist-panel--${verificationTone(activeState.result.verification.status)}`} style={{ marginTop: "0.75rem" }}>
                              <div className="eyebrow">Verification</div>
                              <p>
                                <strong>{activeState.result.verification.status || "unknown"}</strong>
                                {activeState.result.verification.verification_loop_state ? ` · ${activeState.result.verification.verification_loop_state}` : ""}
                              </p>
                              {activeState.result.verification.reason ? <p>{activeState.result.verification.reason}</p> : null}
                              {typeof activeState.result.verification.issue_score_delta === "number" ? (
                                <p>
                                  Issue score delta: {activeState.result.verification.issue_score_delta > 0 ? "+" : ""}
                                  {activeState.result.verification.issue_score_delta.toFixed(2)}
                                </p>
                              ) : null}
                              {activeState.result.verification.recommended_next_step ? <p>Next: {activeState.result.verification.recommended_next_step}</p> : null}
                            </div>
                          ) : null}
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
              <div className="eyebrow">Kubernetes Workloads</div>
              <h3>{target.runtime_summary.kubernetes_workload_count} workloads</h3>
              <p>Cluster workloads discovered from the monitored Kubernetes target.</p>
            </div>
          </div>
          {target.kubernetes_workloads.length > 0 ? (
            <div className="checklist-panel">
              <ul>
                {target.kubernetes_workloads.map((workload) => (
                  <li key={`${workload.service_name}-${String(workload.metadata_json?.namespace || "default")}`}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                      <div>
                        <strong>{workload.service_name}</strong>
                        <span>
                          {workload.metadata_json?.resource_kind ? ` · ${String(workload.metadata_json.resource_kind)}` : ""}
                          {workload.metadata_json?.namespace ? ` · ${String(workload.metadata_json.namespace)}` : ""}
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
                        <button className="shell__link shell__link--small" onClick={() => void runWorkloadAction(workload, "describe")}>
                          Describe
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
                      const describeState = actionState[`${workload.container_name || workload.service_name}:describe`];
                      const restartState = actionState[`${workload.container_name || workload.service_name}:restart`];
                      const activeState = restartState || describeState || logsState;
                      if (!activeState) return null;
                      return (
                        <div className="checklist-panel" style={{ marginTop: "0.75rem" }}>
                          <div className="eyebrow">
                            {activeState.status === "running" ? "Running Action" : activeState.result?.execution_status || activeState.status}
                          </div>
                          <p>{activeState.error || activeState.result?.final_answer || "Action completed."}</p>
                          {activeState.result?.typed_action_summary ? <p>{activeState.result.typed_action_summary}</p> : null}
                          {activeState.result?.verification ? (
                            <div className={`checklist-panel checklist-panel--${verificationTone(activeState.result.verification.status)}`} style={{ marginTop: "0.75rem" }}>
                              <div className="eyebrow">Verification</div>
                              <p>
                                <strong>{activeState.result.verification.status || "unknown"}</strong>
                                {activeState.result.verification.verification_loop_state ? ` · ${activeState.result.verification.verification_loop_state}` : ""}
                              </p>
                              {activeState.result.verification.reason ? <p>{activeState.result.verification.reason}</p> : null}
                              {typeof activeState.result.verification.issue_score_delta === "number" ? (
                                <p>
                                  Issue score delta: {activeState.result.verification.issue_score_delta > 0 ? "+" : ""}
                                  {activeState.result.verification.issue_score_delta.toFixed(2)}
                                </p>
                              ) : null}
                              {activeState.result.verification.recommended_next_step ? <p>Next: {activeState.result.verification.recommended_next_step}</p> : null}
                            </div>
                          ) : null}
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
            <p>No Kubernetes workloads reported for this target yet.</p>
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
