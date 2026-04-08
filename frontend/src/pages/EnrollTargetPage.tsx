import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createOnboardingRequest,
  deleteOnboardingRequest,
  fetchEnrollmentBlueprint,
  fetchOnboardingRequests,
  fetchTelemetryProfiles,
  updateOnboardingRequest,
  installOnboardingTarget,
  testOnboardingConnectivity,
} from "../lib/api";

const targetTypes = [
  { value: "linux", label: "Linux Server", detail: "EC2 and standalone Linux onboarding" },
  { value: "windows", label: "Windows Server", detail: "Planned next phase" },
  { value: "kubernetes", label: "Kubernetes Cluster", detail: "Planned later phase" },
];

export function EnrollTargetPage() {
  const queryClient = useQueryClient();
  const [targetType, setTargetType] = useState("linux");
  const [profileName, setProfileName] = useState("infra-observability");
  const [form, setForm] = useState({
    name: "",
    hostname: "",
    ssh_user: "ubuntu",
    ssh_port: "22",
  });
  const [pemFile, setPemFile] = useState<File | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [selectedOnboardingId, setSelectedOnboardingId] = useState<string>("");

  const profilesQuery = useQuery({
    queryKey: ["fleet-profiles"],
    queryFn: fetchTelemetryProfiles,
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
  const onboardingRequests = onboardingQuery.data || [];

  const activeProfile = useMemo(
    () => profiles.find((profile) => profile.slug === profileName) || profiles[0],
    [profileName, profiles],
  );

  const activeOnboarding = useMemo(
    () => onboardingRequests.find((item) => item.onboarding_id === selectedOnboardingId) || onboardingRequests[0] || null,
    [onboardingRequests, selectedOnboardingId],
  );

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
      if (selectedOnboardingId === onboardingId) {
        setSelectedOnboardingId("");
      }
      setIsEditing(false);
      setPemFile(null);
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
    if (!item) {
      return;
    }
    setForm({
      name: item.name,
      hostname: item.hostname,
      ssh_user: item.ssh_user,
      ssh_port: String(item.ssh_port),
    });
    setProfileName(item.profile_slug || profileName);
    setSelectedOnboardingId(onboardingId);
    setIsEditing(true);
    setPemFile(null);
  };

  const handleCreate = () => {
    if (!pemFile) {
      return;
    }
    createMutation.mutate({
      name: form.name,
      hostname: form.hostname,
      ssh_user: form.ssh_user,
      ssh_port: Number(form.ssh_port || 22),
      target_type: targetType,
      profile: profileName,
      pem_file: pemFile,
    });
  };

  const handleUpdate = () => {
    if (!activeOnboarding) {
      return;
    }
    updateMutation.mutate({
      onboardingId: activeOnboarding.onboarding_id,
      payload: {
        name: form.name,
        hostname: form.hostname,
        ssh_user: form.ssh_user,
        ssh_port: Number(form.ssh_port || 22),
        target_type: targetType,
        profile: profileName,
        pem_file: pemFile,
      },
    });
  };

  return (
    <>
      <section className="hero-card hero-card--enroll page-theme-enroll">
        <div className="eyebrow">Target Enrollment</div>
        <h2>Enroll Linux Infrastructure</h2>
        <p>
          Upload the EC2 PEM key, validate SSH connectivity from the control plane, and trigger the Phase 3 remote bootstrap.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">PEM upload</div>
          <div className="hero-card__chip">Connectivity test</div>
          <div className="hero-card__chip">Remote bootstrap</div>
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
                className={`selector-card${targetType === option.value ? " is-active" : ""}${option.value !== "linux" ? " is-disabled" : ""}`}
                onClick={() => option.value === "linux" && setTargetType(option.value)}
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
          <h3>EC2 SSH access</h3>
          <div className="form-grid">
            <label className="form-field">
              <span>Target name</span>
              <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="prod-web-ec2" />
            </label>
            <label className="form-field">
              <span>Host / IP</span>
              <input value={form.hostname} onChange={(event) => setForm((current) => ({ ...current, hostname: event.target.value }))} placeholder="ec2-xx-xx-xx-xx.compute.amazonaws.com" />
            </label>
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
          </div>

          <div className="action-row">
            <button type="button" className="action-button" onClick={isEditing ? handleUpdate : handleCreate} disabled={(isEditing ? updateMutation.isPending : createMutation.isPending) || (!isEditing && !pemFile) || !form.name || !form.hostname}>
              {isEditing ? (updateMutation.isPending ? "Updating..." : "Update Onboarding Request") : (createMutation.isPending ? "Saving..." : "Save Onboarding Request")}
            </button>
            {createMutation.isError ? <p className="inline-error">{(createMutation.error as Error).message}</p> : null}
            {updateMutation.isError ? <p className="inline-error">{(updateMutation.error as Error).message}</p> : null}
            {isEditing ? (
              <button
                type="button"
                className="action-button action-button--ghost"
                onClick={() => {
                  setIsEditing(false);
                  setSelectedOnboardingId("");
                  setPemFile(null);
                  setForm({ name: "", hostname: "", ssh_user: "ubuntu", ssh_port: "22" });
                }}
              >
                Cancel Edit
              </button>
            ) : null}
          </div>
        </article>

        <article className="page-card enroll-card enroll-card--command">
          <div className="eyebrow">4. Enrollment Blueprint</div>
          <h3>Linux bootstrap command</h3>
          {blueprintQuery.isLoading ? (
            <p>Generating install blueprint...</p>
          ) : blueprintQuery.isError || !blueprintQuery.data ? (
            <p>Unable to generate enrollment instructions right now.</p>
          ) : (
            <>
              <div className="fleet-card__meta-grid">
                <div>
                  <span>Target Type</span>
                  <strong>{blueprintQuery.data.target_type}</strong>
                </div>
                <div>
                  <span>Profile</span>
                  <strong>{activeProfile?.name || profileName}</strong>
                </div>
                <div>
                  <span>Enrollment Token</span>
                  <strong>{blueprintQuery.data.token_preview}</strong>
                </div>
                <div>
                  <span>Install Mode</span>
                  <strong>{blueprintQuery.data.install_mode}</strong>
                </div>
              </div>

              <div className="code-panel">
                <div className="eyebrow">Generated Command</div>
                <pre>{blueprintQuery.data.install_command}</pre>
              </div>

              <div className="checklist-panel">
                <div className="eyebrow">What this will install</div>
                <ul>
                  {blueprintQuery.data.components.map((component) => (
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
            <div className="eyebrow">5. Onboarding Requests</div>
            <h3>Validate and install</h3>
          </div>
        </div>
        {onboardingRequests.length === 0 ? (
          <p>No onboarding requests yet. Upload a PEM and create one above.</p>
        ) : (
          <div className="onboarding-grid">
            <div className="onboarding-list">
              {onboardingRequests.map((item) => (
                <button
                  key={item.onboarding_id}
                  type="button"
                  className={`selector-card selector-card--onboarding${activeOnboarding?.onboarding_id === item.onboarding_id ? " is-active" : ""}`}
                  onClick={() => setSelectedOnboardingId(item.onboarding_id)}
                >
                  <strong>{item.name}</strong>
                  <span>{item.hostname}</span>
                  <span>{item.connectivity_status}</span>
                </button>
              ))}
            </div>

            <div className="onboarding-detail">
              {activeOnboarding ? (
                <>
                  <div className="fleet-card__meta-grid">
                    <div>
                      <span>SSH user</span>
                      <strong>{activeOnboarding.ssh_user}</strong>
                    </div>
                    <div>
                      <span>PEM file</span>
                      <strong>{activeOnboarding.pem_file_name || "uploaded"}</strong>
                    </div>
                    <div>
                      <span>Connectivity</span>
                      <strong>{activeOnboarding.connectivity_status}</strong>
                    </div>
                    <div>
                      <span>Status</span>
                      <strong>{activeOnboarding.status}</strong>
                    </div>
                    <div>
                      <span>Target</span>
                      <strong>{activeOnboarding.target_id || "Pending enrollment"}</strong>
                    </div>
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
                      {testMutation.isPending ? "Testing..." : "Test Connectivity"}
                    </button>
                    <button
                      type="button"
                      className="action-button action-button--secondary"
                      onClick={() => installMutation.mutate(activeOnboarding.onboarding_id)}
                      disabled={installMutation.isPending || activeOnboarding.connectivity_status !== "reachable"}
                    >
                      {installMutation.isPending ? "Installing..." : "Run Remote Install"}
                    </button>
                  </div>

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
