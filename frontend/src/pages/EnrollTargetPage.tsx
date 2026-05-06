import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createOnboardingRequest,
  deleteOnboardingRequest,
  fetchEnrollmentBlueprint,
  fetchOnboardingRequests,
  fetchPolicyProfiles,
  fetchTelemetryProfiles,
  installOnboardingTarget,
  testOnboardingConnectivity,
  updateOnboardingRequest,
  type FleetPolicyProfile,
  type OnboardingRequest,
} from "../lib/api";

const targetTypes = [
  { value: "linux", label: "Linux Server", detail: "EC2, VM, or bare-metal Linux onboarding" },
  { value: "windows", label: "Windows Server", detail: "Planned next phase" },
  { value: "kubernetes", label: "Kubernetes Cluster", detail: "Cluster-agent onboarding for monitored clusters" },
];

const roleOptions = [
  { value: "app", label: "Application" },
  { value: "db", label: "Database" },
  { value: "cache", label: "Cache" },
  { value: "gateway", label: "Gateway" },
  { value: "custom", label: "Custom" },
];

const environmentOptions = [
  { value: "prod", label: "Production" },
  { value: "staging", label: "Staging" },
  { value: "dev", label: "Development" },
  { value: "test", label: "Test" },
];

const runtimeOptionsByTarget: Record<string, Array<{ value: string; label: string }>> = {
  linux: [
    { value: "systemd", label: "Systemd service" },
    { value: "docker", label: "Docker on Linux" },
    { value: "standalone", label: "Standalone process" },
  ],
  kubernetes: [{ value: "kubernetes", label: "Kubernetes cluster" }],
  windows: [{ value: "unknown", label: "Unknown" }],
};

const serviceKindOptionsByRuntime: Record<string, Array<{ value: string; label: string }>> = {
  systemd: [{ value: "systemd", label: "Systemd unit" }],
  docker: [{ value: "docker_container", label: "Docker container" }],
  standalone: [{ value: "process", label: "Process" }],
  kubernetes: [{ value: "kubernetes_workload", label: "Kubernetes workload" }],
  unknown: [{ value: "systemd", label: "Systemd unit" }],
};

const logSourceOptionsByRuntime: Record<string, Array<{ value: string; label: string }>> = {
  systemd: [
    { value: "journald", label: "Journald" },
    { value: "file", label: "File path" },
  ],
  docker: [
    { value: "docker", label: "Docker stdout/stderr" },
    { value: "file", label: "Mounted file path" },
  ],
  standalone: [
    { value: "file", label: "File path" },
    { value: "journald", label: "Journald" },
  ],
  kubernetes: [{ value: "kubernetes", label: "Kubernetes workload logs" }],
  unknown: [{ value: "file", label: "File path" }],
};

type EnrollFormState = {
  name: string;
  hostname: string;
  ssh_user: string;
  ssh_port: string;
  target_role: string;
  runtime_type: string;
  target_environment: string;
  policy_profile: string;
  application_name: string;
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
  log_stream_family: string;
  parser_name: string;
  ship_logs_centrally: boolean;
  shipper_type: string;
  opensearch_pipeline: string;
  notes: string;
};

function initialForm(targetType = "linux"): EnrollFormState {
  return {
    name: "",
    hostname: "",
    ssh_user: targetType === "linux" ? "ubuntu" : "",
    ssh_port: "22",
    target_role: "app",
    runtime_type: targetType === "kubernetes" ? "kubernetes" : "systemd",
    target_environment: "prod",
    policy_profile: "",
    application_name: "",
    service_name: "",
    service_kind: targetType === "kubernetes" ? "kubernetes_workload" : "systemd",
    systemd_unit: "",
    container_name: "",
    process_name: "",
    port: "",
    log_source_type: targetType === "kubernetes" ? "kubernetes" : "journald",
    journal_unit: "",
    file_path: "",
    log_container_name: "",
    log_stream_family: targetType === "kubernetes" ? "logs-kubernetes" : "logs-systemd",
    parser_name: "",
    ship_logs_centrally: true,
    shipper_type: "fluent-bit",
    opensearch_pipeline: "",
    notes: "",
  };
}

function runtimeSummary(form: EnrollFormState) {
  if (form.runtime_type === "docker") {
    return `${form.service_name || "workload"} via Docker logs`;
  }
  if (form.runtime_type === "kubernetes") {
    return `${form.service_name || "workload"} via Kubernetes cluster agent`;
  }
  if (form.log_source_type === "file") {
    return `${form.service_name || "workload"} via file path`;
  }
  return `${form.service_name || "workload"} via journald/systemd`;
}

function policySummary(policy?: FleetPolicyProfile) {
  if (!policy) return "No policy selected yet.";
  const capabilities = [
    policy.allow_service_status ? "status" : "",
    policy.allow_service_restart ? "restart" : "",
    policy.allow_docker_logs ? "docker logs" : "",
    policy.allow_journal_logs ? "journald" : "",
    policy.allow_file_logs ? "file logs" : "",
    policy.allow_db_diagnostics ? "db diagnostics" : "",
  ].filter(Boolean);
  return capabilities.length ? capabilities.join(" · ") : "restricted";
}

function onboardingConfig(config: Record<string, unknown> | undefined | null) {
  return config && typeof config === "object" ? config : {};
}

export function EnrollTargetPage() {
  const queryClient = useQueryClient();
  const [targetType, setTargetType] = useState("linux");
  const [profileName, setProfileName] = useState("infra-observability");
  const [form, setForm] = useState<EnrollFormState>(() => initialForm("linux"));
  const [pemFile, setPemFile] = useState<File | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [selectedOnboardingId, setSelectedOnboardingId] = useState<string>("");

  const profilesQuery = useQuery({
    queryKey: ["fleet-profiles", targetType],
    queryFn: () => fetchTelemetryProfiles(targetType),
  });

  const policyProfilesQuery = useQuery({
    queryKey: ["fleet-policy-profiles", targetType, form.runtime_type],
    queryFn: () => fetchPolicyProfiles(targetType, form.runtime_type),
    enabled: targetType !== "windows",
  });

  const blueprintQuery = useQuery({
    queryKey: ["enrollment-blueprint", targetType, profileName],
    queryFn: () => fetchEnrollmentBlueprint(targetType, profileName),
  });

  const onboardingQuery = useQuery({
    queryKey: ["fleet-onboarding"],
    queryFn: fetchOnboardingRequests,
  });

  const profiles = profilesQuery.data || [];
  const policyProfiles = policyProfilesQuery.data || [];
  const onboardingRequests = onboardingQuery.data || [];
  const blueprint = blueprintQuery.data;
  const controlPlaneReady = blueprint?.control_plane_ready ?? false;

  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.slug === profileName) || profiles[0],
    [profileName, profiles],
  );

  const activePolicyProfile = useMemo(
    () => policyProfiles.find((profile) => profile.slug === form.policy_profile) || policyProfiles[0],
    [form.policy_profile, policyProfiles],
  );

  const activeOnboarding = useMemo(
    () => onboardingRequests.find((item) => item.onboarding_id === selectedOnboardingId) || onboardingRequests[0] || null,
    [onboardingRequests, selectedOnboardingId],
  );

  useEffect(() => {
    if (!profiles.length) return;
    if (!profiles.some((profile) => profile.slug === profileName)) {
      setProfileName(profiles[0].slug);
    }
  }, [profileName, profiles]);

  useEffect(() => {
    if (targetType === "kubernetes") {
      setPemFile(null);
      setForm((current) => ({
        ...current,
        ssh_user: "",
        ssh_port: "22",
        runtime_type: "kubernetes",
        service_kind: "kubernetes_workload",
        log_source_type: "kubernetes",
        log_stream_family: current.log_stream_family || "logs-kubernetes",
      }));
      return;
    }
    if (targetType === "linux") {
      setForm((current) => ({
        ...current,
        ssh_user: current.ssh_user || "ubuntu",
        ssh_port: current.ssh_port || "22",
        runtime_type: current.runtime_type === "kubernetes" ? "systemd" : current.runtime_type || "systemd",
      }));
    }
  }, [targetType]);

  useEffect(() => {
    const serviceKinds = serviceKindOptionsByRuntime[form.runtime_type] || serviceKindOptionsByRuntime.unknown;
    const logSources = logSourceOptionsByRuntime[form.runtime_type] || logSourceOptionsByRuntime.unknown;
    const nextServiceKind = serviceKinds.some((item) => item.value === form.service_kind) ? form.service_kind : serviceKinds[0]?.value || "systemd";
    const nextLogSource = logSources.some((item) => item.value === form.log_source_type) ? form.log_source_type : logSources[0]?.value || "file";
    const nextStreamFamily = form.log_stream_family || `logs-${form.runtime_type || "default"}`;

    if (
      nextServiceKind !== form.service_kind
      || nextLogSource !== form.log_source_type
      || nextStreamFamily !== form.log_stream_family
    ) {
      setForm((current) => ({
        ...current,
        service_kind: nextServiceKind,
        log_source_type: nextLogSource,
        log_stream_family: nextStreamFamily,
      }));
    }
  }, [form.log_source_type, form.log_stream_family, form.runtime_type, form.service_kind]);

  useEffect(() => {
    if (!policyProfiles.length) return;
    if (!policyProfiles.some((profile) => profile.slug === form.policy_profile)) {
      setForm((current) => ({ ...current, policy_profile: policyProfiles[0].slug }));
    }
  }, [form.policy_profile, policyProfiles]);

  const createMutation = useMutation({
    mutationFn: createOnboardingRequest,
    onSuccess: async (created) => {
      setSelectedOnboardingId(created.onboarding_id);
      await queryClient.invalidateQueries({ queryKey: ["fleet-onboarding"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ onboardingId, payload }: { onboardingId: string; payload: Parameters<typeof updateOnboardingRequest>[1] }) =>
      updateOnboardingRequest(onboardingId, payload),
    onSuccess: async (updated) => {
      setSelectedOnboardingId(updated.onboarding_id);
      setIsEditing(false);
      setPemFile(null);
      await queryClient.invalidateQueries({ queryKey: ["fleet-onboarding"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteOnboardingRequest,
    onSuccess: async (_, onboardingId) => {
      if (selectedOnboardingId === onboardingId) setSelectedOnboardingId("");
      setIsEditing(false);
      setPemFile(null);
      setForm(initialForm(targetType));
      await queryClient.invalidateQueries({ queryKey: ["fleet-onboarding"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: testOnboardingConnectivity,
    onSuccess: async (updated) => {
      setSelectedOnboardingId(updated.onboarding_id);
      await queryClient.invalidateQueries({ queryKey: ["fleet-onboarding"] });
    },
  });

  const installMutation = useMutation({
    mutationFn: installOnboardingTarget,
    onSuccess: async (updated) => {
      setSelectedOnboardingId(updated.onboarding_id);
      await queryClient.invalidateQueries({ queryKey: ["fleet-onboarding"] });
      await queryClient.invalidateQueries({ queryKey: ["fleet-targets"] });
    },
  });

  const syncFormFromOnboarding = (onboardingId: string) => {
    const item = onboardingRequests.find((entry) => entry.onboarding_id === onboardingId);
    if (!item) return;
    const config = onboardingConfig(item.config_json);
    const primaryService = onboardingConfig(config.primary_service as Record<string, unknown>);
    const logSource = onboardingConfig(config.log_source as Record<string, unknown>);
    const logIngestion = onboardingConfig(config.log_ingestion as Record<string, unknown>);
    const recordMetadata = onboardingConfig(config.record_metadata_json as Record<string, unknown>);
    setTargetType(item.target_type || "linux");
    setForm({
      name: item.name,
      hostname: item.hostname,
      ssh_user: item.ssh_user,
      ssh_port: String(item.ssh_port),
      target_role: item.target_role || "app",
      runtime_type: item.runtime_type || (item.target_type === "kubernetes" ? "kubernetes" : "systemd"),
      target_environment: item.target_environment || "prod",
      policy_profile: item.policy_profile_slug || "",
      application_name: String(recordMetadata.application || ""),
      service_name: String(primaryService.service_name || ""),
      service_kind: String(primaryService.service_kind || (item.runtime_type === "docker" ? "docker_container" : "systemd")),
      systemd_unit: String(primaryService.systemd_unit || ""),
      container_name: String(primaryService.container_name || ""),
      process_name: String(primaryService.process_name || ""),
      port: primaryService.port != null ? String(primaryService.port) : "",
      log_source_type: String(logSource.source_type || (item.runtime_type === "docker" ? "docker" : "journald")),
      journal_unit: String(logSource.journal_unit || ""),
      file_path: String(logSource.file_path || ""),
      log_container_name: String(logSource.container_name || ""),
      log_stream_family: String(logSource.stream_family || ""),
      parser_name: String(logSource.parser_name || ""),
      ship_logs_centrally: logIngestion.enabled !== false,
      shipper_type: String(logIngestion.shipper_type || "fluent-bit"),
      opensearch_pipeline: String(logIngestion.opensearch_pipeline || ""),
      notes: item.notes || "",
    });
    setProfileName(item.profile_slug || profileName);
    setSelectedOnboardingId(onboardingId);
    setIsEditing(true);
    setPemFile(null);
  };

  const onboardingPayload = {
    name: form.name,
    hostname: form.hostname,
    target_role: form.target_role,
    runtime_type: form.runtime_type,
    target_environment: form.target_environment,
    ssh_user: form.ssh_user,
    ssh_port: Number(form.ssh_port || 22),
    target_type: targetType,
    profile: profileName,
    policy_profile: form.policy_profile,
    application_name: form.application_name,
    service_name: form.service_name,
    service_kind: form.service_kind,
    systemd_unit: form.systemd_unit,
    container_name: form.container_name,
    process_name: form.process_name,
    port: form.port ? Number(form.port) : null,
    log_source_type: form.log_source_type,
    journal_unit: form.journal_unit,
    file_path: form.file_path,
    log_container_name: form.log_container_name,
    log_stream_family: form.log_stream_family,
    parser_name: form.parser_name,
    ship_logs_centrally: form.ship_logs_centrally,
    shipper_type: form.shipper_type,
    opensearch_pipeline: form.opensearch_pipeline,
    notes: form.notes,
    pem_file: pemFile,
  };

  const handleCreate = () => {
    if (targetType === "linux" && !pemFile) return;
    createMutation.mutate(onboardingPayload);
  };

  const handleUpdate = () => {
    if (!activeOnboarding) return;
    updateMutation.mutate({
      onboardingId: activeOnboarding.onboarding_id,
      payload: onboardingPayload,
    });
  };

  const resetEditor = () => {
    setIsEditing(false);
    setSelectedOnboardingId("");
    setPemFile(null);
    setForm(initialForm(targetType));
  };

  return (
    <>
      <section className="hero-card hero-card--enroll page-theme-enroll">
        <div className="eyebrow">Target Enrollment</div>
        <h2>Define runtime, policy, and log ingestion up front</h2>
        <p>
          Capture how the target actually runs, which workload matters, where logs come from, and what the agent is allowed to do before you install anything.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Runtime classification</div>
          <div className="hero-card__chip">Policy-scoped execution</div>
          <div className="hero-card__chip">Centralized log source</div>
        </div>
      </section>

      <section className="enroll-layout">
        <article className="page-card enroll-card">
          <div className="eyebrow">1. Target Setup</div>
          <h3>Choose deployment target</h3>
          <div className="selector-grid">
            {targetTypes.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`selector-card${targetType === option.value ? " is-active" : ""}${option.value === "windows" ? " is-disabled" : ""}`}
                onClick={() => option.value !== "windows" && setTargetType(option.value)}
              >
                <strong>{option.label}</strong>
                <span>{option.detail}</span>
              </button>
            ))}
          </div>

          <div className="eyebrow">2. Telemetry Profile</div>
          <h3>Select install profile</h3>
          <div className="selector-grid selector-grid--profiles">
            {profiles.map((profile) => (
              <button
                key={profile.slug}
                type="button"
                className={`selector-card selector-card--profile${profileName === profile.slug ? " is-active" : ""}`}
                onClick={() => setProfileName(profile.slug)}
              >
                <strong>{profile.name}</strong>
                <span>{profile.summary}</span>
              </button>
            ))}
          </div>

          <div className="eyebrow">3. Connection Details</div>
          <h3>{targetType === "kubernetes" ? "Cluster registration" : "Target access and identity"}</h3>
          <div className="form-grid">
            <label className="form-field">
              <span>{targetType === "kubernetes" ? "Cluster name" : "Target name"}</span>
              <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder={targetType === "kubernetes" ? "prod-cluster-apac" : "orders-prod-01"} />
            </label>
            <label className="form-field">
              <span>{targetType === "kubernetes" ? "Cluster label / endpoint" : "Host / IP"}</span>
              <input value={form.hostname} onChange={(event) => setForm((current) => ({ ...current, hostname: event.target.value }))} placeholder={targetType === "kubernetes" ? "customer-prod-cluster" : "10.0.10.42"} />
            </label>
            <label className="form-field">
              <span>Role</span>
              <select value={form.target_role} onChange={(event) => setForm((current) => ({ ...current, target_role: event.target.value }))}>
                {roleOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="form-field">
              <span>Environment</span>
              <select value={form.target_environment} onChange={(event) => setForm((current) => ({ ...current, target_environment: event.target.value }))}>
                {environmentOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            {targetType === "linux" ? (
              <>
                <label className="form-field">
                  <span>SSH user</span>
                  <input value={form.ssh_user} onChange={(event) => setForm((current) => ({ ...current, ssh_user: event.target.value }))} placeholder="ubuntu" />
                </label>
                <label className="form-field">
                  <span>SSH port</span>
                  <input value={form.ssh_port} onChange={(event) => setForm((current) => ({ ...current, ssh_port: event.target.value }))} placeholder="22" />
                </label>
                <label className="form-field form-field--full">
                  <span>PEM file</span>
                  <input type="file" accept=".pem" onChange={(event) => setPemFile(event.target.files?.[0] || null)} />
                </label>
              </>
            ) : (
              <div className="checklist-panel form-field--full">
                <div className="eyebrow">Kubernetes onboarding</div>
                <p>No SSH or PEM is required. Save the onboarding request, validate control-plane prerequisites, then apply the generated cluster-agent manifest to the customer cluster.</p>
              </div>
            )}
          </div>

          <div className="eyebrow">4. Runtime and Policy</div>
          <h3>Describe how this target actually runs</h3>
          <div className="form-grid">
            <label className="form-field">
              <span>Runtime</span>
              <select value={form.runtime_type} onChange={(event) => setForm((current) => ({ ...current, runtime_type: event.target.value }))}>
                {(runtimeOptionsByTarget[targetType] || runtimeOptionsByTarget.linux).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="form-field">
              <span>Policy profile</span>
              <select value={form.policy_profile} onChange={(event) => setForm((current) => ({ ...current, policy_profile: event.target.value }))}>
                {policyProfiles.map((profile) => (
                  <option key={profile.slug} value={profile.slug}>{profile.name}</option>
                ))}
              </select>
            </label>
            <label className="form-field form-field--full">
              <span>Application name</span>
              <input value={form.application_name} onChange={(event) => setForm((current) => ({ ...current, application_name: event.target.value }))} placeholder="orders-api" />
            </label>
          </div>

          <div className="checklist-panel">
            <div className="eyebrow">Selected policy</div>
            <p>{activePolicyProfile?.description || "Choose a policy profile to scope allowed diagnostics and remediation."}</p>
            <p>{policySummary(activePolicyProfile)}</p>
          </div>

          <div className="eyebrow">5. Primary Service Mapping</div>
          <h3>Identify the workload OpsMitra should treat as primary</h3>
          <div className="form-grid">
            <label className="form-field">
              <span>Service name</span>
              <input value={form.service_name} onChange={(event) => setForm((current) => ({ ...current, service_name: event.target.value }))} placeholder="orders-api" />
            </label>
            <label className="form-field">
              <span>Service kind</span>
              <select value={form.service_kind} onChange={(event) => setForm((current) => ({ ...current, service_kind: event.target.value }))}>
                {(serviceKindOptionsByRuntime[form.runtime_type] || serviceKindOptionsByRuntime.unknown).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            {(form.runtime_type === "systemd" || form.log_source_type === "journald") ? (
              <label className="form-field">
                <span>Systemd unit</span>
                <input value={form.systemd_unit} onChange={(event) => setForm((current) => ({ ...current, systemd_unit: event.target.value }))} placeholder="orders-api.service" />
              </label>
            ) : null}
            {form.runtime_type === "docker" ? (
              <label className="form-field">
                <span>Container name</span>
                <input value={form.container_name} onChange={(event) => setForm((current) => ({ ...current, container_name: event.target.value }))} placeholder="orders-api" />
              </label>
            ) : null}
            {form.runtime_type === "standalone" ? (
              <label className="form-field">
                <span>Process name</span>
                <input value={form.process_name} onChange={(event) => setForm((current) => ({ ...current, process_name: event.target.value }))} placeholder="orders-api" />
              </label>
            ) : null}
            <label className="form-field">
              <span>Port</span>
              <input value={form.port} onChange={(event) => setForm((current) => ({ ...current, port: event.target.value }))} placeholder="8080" />
            </label>
          </div>

          <div className="eyebrow">6. Centralized Log Ingestion</div>
          <h3>Tell the platform where logs come from and how to label them</h3>
          <div className="form-grid">
            <label className="form-field">
              <span>Log source</span>
              <select value={form.log_source_type} onChange={(event) => setForm((current) => ({ ...current, log_source_type: event.target.value }))}>
                {(logSourceOptionsByRuntime[form.runtime_type] || logSourceOptionsByRuntime.unknown).map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label className="form-field">
              <span>Shipper</span>
              <select value={form.shipper_type} onChange={(event) => setForm((current) => ({ ...current, shipper_type: event.target.value }))}>
                <option value="fluent-bit">Fluent Bit</option>
              </select>
            </label>
            {form.log_source_type === "journald" ? (
              <label className="form-field">
                <span>Journald unit</span>
                <input value={form.journal_unit} onChange={(event) => setForm((current) => ({ ...current, journal_unit: event.target.value }))} placeholder="orders-api.service" />
              </label>
            ) : null}
            {form.log_source_type === "file" ? (
              <label className="form-field">
                <span>File path</span>
                <input value={form.file_path} onChange={(event) => setForm((current) => ({ ...current, file_path: event.target.value }))} placeholder="/opt/orders/logs/app.log" />
              </label>
            ) : null}
            {form.log_source_type === "docker" ? (
              <label className="form-field">
                <span>Log container name</span>
                <input value={form.log_container_name} onChange={(event) => setForm((current) => ({ ...current, log_container_name: event.target.value }))} placeholder="orders-api" />
              </label>
            ) : null}
            <label className="form-field">
              <span>OpenSearch stream family</span>
              <input value={form.log_stream_family} onChange={(event) => setForm((current) => ({ ...current, log_stream_family: event.target.value }))} placeholder="logs-linux" />
            </label>
            <label className="form-field">
              <span>Parser name</span>
              <input value={form.parser_name} onChange={(event) => setForm((current) => ({ ...current, parser_name: event.target.value }))} placeholder="json-app-logs" />
            </label>
            <label className="form-field">
              <span>OpenSearch ingest pipeline</span>
              <input value={form.opensearch_pipeline} onChange={(event) => setForm((current) => ({ ...current, opensearch_pipeline: event.target.value }))} placeholder="opsmitra-linux-default" />
            </label>
            <label className="form-field form-field--checkbox">
              <span>Ship logs centrally</span>
              <input type="checkbox" checked={form.ship_logs_centrally} onChange={(event) => setForm((current) => ({ ...current, ship_logs_centrally: event.target.checked }))} />
            </label>
            <label className="form-field form-field--full">
              <span>Operator notes</span>
              <textarea value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} placeholder="Notes about sudo scope, rollout expectations, or target-specific quirks." rows={3} />
            </label>
          </div>

          <div className="checklist-panel">
            <div className="eyebrow">Resulting config</div>
            <p>{runtimeSummary(form)}</p>
            <p>{form.ship_logs_centrally ? `Logs will ship centrally via ${form.shipper_type} into ${form.log_stream_family || "the configured stream family"}.` : "Centralized log shipping is disabled for this target."}</p>
          </div>

          <div className="action-row">
            <button
              type="button"
              className="action-button"
              onClick={isEditing ? handleUpdate : handleCreate}
              disabled={
                (isEditing ? updateMutation.isPending : createMutation.isPending)
                || (targetType === "linux" && !isEditing && !pemFile)
                || !form.name
                || !form.hostname
              }
            >
              {isEditing ? (updateMutation.isPending ? "Updating..." : "Update Onboarding Request") : (createMutation.isPending ? "Saving..." : "Save Onboarding Request")}
            </button>
            {createMutation.isError ? <p className="inline-error">{(createMutation.error as Error).message}</p> : null}
            {updateMutation.isError ? <p className="inline-error">{(updateMutation.error as Error).message}</p> : null}
            {isEditing ? (
              <button type="button" className="action-button action-button--ghost" onClick={resetEditor}>
                Cancel Edit
              </button>
            ) : null}
          </div>
        </article>

        <article className="page-card enroll-card enroll-card--command">
          <div className="eyebrow">7. Enrollment Blueprint</div>
          <h3>{targetType === "kubernetes" ? "Kubernetes cluster-agent install command" : "Linux bootstrap command"}</h3>
          {blueprintQuery.isLoading ? (
            <p>Generating install blueprint...</p>
          ) : blueprintQuery.isError || !blueprintQuery.data ? (
            <p>Unable to generate enrollment instructions right now.</p>
          ) : (
            <>
              {!blueprint?.control_plane_ready ? (
                <div className="checklist-panel" style={{ marginBottom: "1rem" }}>
                  <div className="eyebrow">Control Plane Action Required</div>
                  <p>
                    The control plane is not ready to install the {targetType === "kubernetes" ? "Kubernetes cluster agent" : "Linux execution bundle"} yet.
                  </p>
                  <ul>
                    {(blueprint?.missing_requirements || []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {(blueprint?.warnings || []).length > 0 ? (
                <div className="checklist-panel" style={{ marginBottom: "1rem" }}>
                  <div className="eyebrow">Warnings</div>
                  <ul>
                    {(blueprint?.warnings || []).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="fleet-card__meta-grid">
                <div>
                  <span>Target Type</span>
                  <strong>{blueprint?.target_type || targetType}</strong>
                </div>
                <div>
                  <span>Profile</span>
                  <strong>{activeProfile?.name || profileName}</strong>
                </div>
                <div>
                  <span>Policy</span>
                  <strong>{activePolicyProfile?.name || "pending"}</strong>
                </div>
                <div>
                  <span>Control Plane</span>
                  <strong>{blueprint?.control_plane_ready ? "ready" : "action required"}</strong>
                </div>
              </div>

              <div className="code-panel">
                <div className="eyebrow">Generated Command</div>
                <pre>{blueprint?.install_command || ""}</pre>
              </div>

              <div className="checklist-panel">
                <div className="eyebrow">What this will install</div>
                <ul>
                  {(blueprint?.components || []).map((component) => (
                    <li key={component}>{component}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </article>
      </section>

      <section className="page-card enroll-card enroll-card--status">
        <div className="fleet-card__top">
          <div>
            <div className="eyebrow">8. Onboarding Requests</div>
            <h3>Validate, install, and review saved target config</h3>
          </div>
        </div>
        {onboardingRequests.length === 0 ? (
          <p>No onboarding requests yet. Create one above to persist runtime and policy configuration.</p>
        ) : (
          <div className="onboarding-grid">
            <div className="onboarding-list">
              {onboardingRequests.map((item) => (
                <button
                  key={item.onboarding_id}
                  type="button"
                  className={`selector-card selector-card--onboarding${activeOnboarding?.onboarding_id === item.onboarding_id ? " is-active" : ""}`}
                  onClick={() => {
                    setSelectedOnboardingId(item.onboarding_id);
                    setTargetType(item.target_type || "linux");
                  }}
                >
                  <strong>{item.name}</strong>
                  <span>{item.hostname}</span>
                  <span>{item.runtime_type} · {item.target_role} · {item.connectivity_status}</span>
                </button>
              ))}
            </div>

            <div className="onboarding-detail">
              {activeOnboarding ? (
                <>
                  <div className="fleet-card__meta-grid">
                    <div>
                      <span>Runtime</span>
                      <strong>{activeOnboarding.runtime_type}</strong>
                    </div>
                    <div>
                      <span>Role</span>
                      <strong>{activeOnboarding.target_role}</strong>
                    </div>
                    <div>
                      <span>Environment</span>
                      <strong>{activeOnboarding.target_environment}</strong>
                    </div>
                    <div>
                      <span>Policy</span>
                      <strong>{activeOnboarding.policy_profile_name || "unassigned"}</strong>
                    </div>
                    <div>
                      <span>{activeOnboarding.target_type === "kubernetes" ? "Install mode" : "PEM file"}</span>
                      <strong>{activeOnboarding.target_type === "kubernetes" ? "cluster manifest" : (activeOnboarding.pem_file_name || "uploaded")}</strong>
                    </div>
                    <div>
                      <span>Target</span>
                      <strong>{activeOnboarding.target_id || "Pending enrollment"}</strong>
                    </div>
                  </div>

                  <div className="checklist-panel">
                    <div className="eyebrow">Primary service and logs</div>
                    <p>
                      {String((onboardingConfig(activeOnboarding.config_json).primary_service as Record<string, unknown> | undefined)?.service_name || "not configured")}
                      {" · "}
                      {String((onboardingConfig(activeOnboarding.config_json).primary_service as Record<string, unknown> | undefined)?.service_kind || "unknown")}
                      {" · "}
                      {String((onboardingConfig(activeOnboarding.config_json).log_source as Record<string, unknown> | undefined)?.source_type || "unknown")}
                    </p>
                    <p>
                      Stream family: {String((onboardingConfig(activeOnboarding.config_json).log_source as Record<string, unknown> | undefined)?.stream_family || "unassigned")}
                    </p>
                  </div>

                  <div className="action-row">
                    <button
                      type="button"
                      className="action-button action-button--secondary"
                      onClick={() => syncFormFromOnboarding(activeOnboarding.onboarding_id)}
                    >
                      Edit Request
                    </button>
                    <button
                      type="button"
                      className="action-button action-button--danger"
                      onClick={() => deleteMutation.mutate(activeOnboarding.onboarding_id)}
                      disabled={deleteMutation.isPending}
                    >
                      {deleteMutation.isPending ? "Deleting..." : "Delete Request"}
                    </button>
                    <button
                      type="button"
                      className="action-button"
                      onClick={() => testMutation.mutate(activeOnboarding.onboarding_id)}
                      disabled={testMutation.isPending}
                    >
                      {testMutation.isPending ? "Testing..." : (activeOnboarding.target_type === "kubernetes" ? "Validate Prerequisites" : "Test Connectivity")}
                    </button>
                    <button
                      type="button"
                      className="action-button action-button--secondary"
                      onClick={() => installMutation.mutate(activeOnboarding.onboarding_id)}
                      disabled={installMutation.isPending || activeOnboarding.connectivity_status !== "reachable" || !controlPlaneReady}
                    >
                      {installMutation.isPending ? "Installing..." : (activeOnboarding.target_type === "kubernetes" ? "Generate Cluster Install" : "Run Remote Install")}
                    </button>
                  </div>

                  {!controlPlaneReady ? (
                    <div className="checklist-panel">
                      <div className="eyebrow">Install Blocked</div>
                      <p>Fix the control-plane prerequisites shown in the Enrollment Blueprint before running install.</p>
                    </div>
                  ) : null}

                  <div className="checklist-panel">
                    <div className="eyebrow">Connectivity Result</div>
                    <p>{activeOnboarding.connectivity_message || "Not tested yet."}</p>
                  </div>

                  <div className="checklist-panel">
                    <div className="eyebrow">Install Result</div>
                    <p>{activeOnboarding.install_message || "Install has not been run yet."}</p>
                  </div>

                  {testMutation.isError ? <p className="inline-error">{(testMutation.error as Error).message}</p> : null}
                  {installMutation.isError ? <p className="inline-error">{(installMutation.error as Error).message}</p> : null}
                  {deleteMutation.isError ? <p className="inline-error">{(deleteMutation.error as Error).message}</p> : null}
                </>
              ) : null}
            </div>
          </div>
        )}
      </section>
    </>
  );
}
