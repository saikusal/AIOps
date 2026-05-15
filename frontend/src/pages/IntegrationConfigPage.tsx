import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";

import {
  fetchIntegrationConfig,
  saveIntegrationConfig,
  type IntegrationConfig,
} from "../lib/api";
import { useTenant } from "../lib/tenant";

const vendorLogos: Record<string, string> = {
  prometheus: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/prometheus/prometheus-original.svg",
  victoriametrics: "https://cdn.simpleicons.org/victoriametrics/009688",
  tempo: "https://upload.wikimedia.org/wikipedia/commons/3/3b/Grafana_icon.svg",
  jaeger: "https://www.vectorlogo.zone/logos/jaegertracing/jaegertracing-icon.svg",
  opensearch: "https://cdn.simpleicons.org/opensearch/005EB8",
  elasticsearch: "https://cdn.simpleicons.org/elasticsearch/005571",
  loki: "https://upload.wikimedia.org/wikipedia/commons/3/3b/Grafana_icon.svg",
  splunk: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/splunk/splunk-original-wordmark.svg",
  dynatrace: "https://www.vectorlogo.zone/logos/dynatrace/dynatrace-icon.svg",
  datadog: "https://cdn.worldvectorlogo.com/logos/datadog.svg",
  newrelic: "https://cdn.worldvectorlogo.com/logos/new-relic.svg",
  nagios: "https://www.vectorlogo.zone/logos/nagios/nagios-icon.svg",
  alertmanager: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/prometheus/prometheus-original.svg",
  pagerduty: "https://cdn.simpleicons.org/pagerduty/06AC38",
  servicenow: "https://cdn.simpleicons.org/servicenow/81B5A1",
  jira: "https://cdn.simpleicons.org/jira/0052CC",
  opsgenie: "https://cdn.simpleicons.org/opsgenie/172B4D",
  slack: "https://cdn.simpleicons.org/slack/4A154B",
  teams: "https://cdn.simpleicons.org/microsoftteams/6264A7",
  aws: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/amazonwebservices/amazonwebservices-original-wordmark.svg",
  azure: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/azure/azure-original.svg",
  gcp: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/googlecloud/googlecloud-original.svg",
  github: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/github/github-original.svg",
  gitlab: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/gitlab/gitlab-original.svg",
  bitbucket: "https://cdn.simpleicons.org/bitbucket/0052CC",
  jenkins: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/jenkins/jenkins-original.svg",
  argocd: "https://cdn.simpleicons.org/argo/EF7B4D",
  fluxcd: "https://cdn.simpleicons.org/flux/5468FF",
  kubernetes: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/kubernetes/kubernetes-plain.svg",
  custom: "https://cdn.simpleicons.org/openapiinitiative/6BA539",
};

const emptyConfig = (vendor: string): IntegrationConfig => ({
  name: vendor,
  integration_type: vendor,
  category: "mixed",
  endpoint_url: "",
  auth_mode: "none",
  enabled: true,
  metadata_json: {},
  credential: {
    secret_ref: "",
    credential_metadata: {},
  },
  bindings: [{ environment: "", application_name: "", priority: 10, enabled: true }],
});

export function IntegrationConfigPage() {
  const { vendor = "custom" } = useParams<{ vendor: string }>();
  const navigate = useNavigate();
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [form, setForm] = useState<IntegrationConfig>(emptyConfig(vendor));
  const { hasPermission } = useTenant();
  const canManageIntegrations = hasPermission("integrations.manage");

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    fetchIntegrationConfig(vendor)
      .then((payload) => {
        if (!active) return;
        setForm({
          ...emptyConfig(vendor),
          ...payload,
          credential: {
            ...emptyConfig(vendor).credential,
            ...(payload.credential || {}),
          },
          bindings: payload.bindings?.length ? payload.bindings : emptyConfig(vendor).bindings,
        });
        setError("");
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message || "Unable to load integration.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [vendor]);

  const vendorName = vendor ? vendor.charAt(0).toUpperCase() + vendor.slice(1).replace("-", " ") : "Integration";
  const logo = vendorLogos[vendor] || "";
  const binding = form.bindings[0] || { environment: "", application_name: "", priority: 10, enabled: true };

  const updateCredentialMetadata = (key: string, value: string) => {
    setForm((current) => ({
      ...current,
      credential: {
        ...current.credential,
        credential_metadata: {
          ...(current.credential.credential_metadata || {}),
          [key]: value,
        },
      },
    }));
  };

  const updateMetadata = (key: string, value: string) => {
    setForm((current) => ({
      ...current,
      metadata_json: {
        ...(current.metadata_json || {}),
        [key]: value,
      },
    }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canManageIntegrations) {
      setError("You do not have permission to manage integrations in this workspace.");
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      await saveIntegrationConfig({
        ...form,
        integration_type: vendor,
        bindings: [binding],
      });
      navigate("/integrations");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save integration.");
    } finally {
      setIsSaving(false);
    }
  };

  const renderVendorSpecificFields = () => {
    switch (vendor) {
      case "aws":
        return (
          <>
            <div className="form-field-group">
              <label>AWS Access Key ID</label>
              <input type="text" value={String(form.credential.credential_metadata?.access_key_id || "")} onChange={(event) => updateCredentialMetadata("access_key_id", event.target.value)} />
            </div>
            <div className="form-field-group">
              <label>AWS Secret Access Key</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
            <div className="form-field-group">
              <label>Default Region</label>
              <input type="text" value={String(form.metadata_json?.region || "us-east-1")} onChange={(event) => updateMetadata("region", event.target.value)} />
            </div>
          </>
        );
      case "datadog":
        return (
          <>
            <div className="form-field-group">
              <label>Datadog API Key</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
            <div className="form-field-group">
              <label>Datadog Application Key</label>
              <input type="password" value={String(form.credential.credential_metadata?.application_key || "")} onChange={(event) => updateCredentialMetadata("application_key", event.target.value)} />
            </div>
            <div className="form-field-group">
              <label>Site</label>
              <select value={String(form.metadata_json?.site || "datadoghq.com")} onChange={(event) => updateMetadata("site", event.target.value)}>
                <option value="datadoghq.com">datadoghq.com (US1)</option>
                <option value="datadoghq.eu">datadoghq.eu (EU)</option>
                <option value="us3.datadoghq.com">us3.datadoghq.com (US3)</option>
              </select>
            </div>
          </>
        );
      case "splunk":
        return (
          <>
            <div className="form-field-group">
              <label>Splunk HEC Endpoint URL</label>
              <input type="url" value={form.endpoint_url} onChange={(event) => setForm((current) => ({ ...current, endpoint_url: event.target.value }))} required />
            </div>
            <div className="form-field-group">
              <label>HEC Token</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} required />
            </div>
          </>
        );
      case "newrelic":
        return (
          <>
            <div className="form-field-group">
              <label>GraphQL Endpoint</label>
              <input type="url" value={form.endpoint_url} onChange={(event) => setForm((current) => ({ ...current, endpoint_url: event.target.value }))} placeholder="https://api.newrelic.com/graphql" />
            </div>
            <div className="form-field-group">
              <label>User API Key</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
            <div className="form-field-group">
              <label>Account ID</label>
              <input type="text" value={String(form.metadata_json?.account_id || "")} onChange={(event) => updateMetadata("account_id", event.target.value)} />
            </div>
          </>
        );
      case "servicenow":
      case "jira":
      case "jenkins":
      case "bitbucket":
        return (
          <>
            <div className="form-field-group">
              <label>Endpoint URL</label>
              <input type="url" value={form.endpoint_url} onChange={(event) => setForm((current) => ({ ...current, endpoint_url: event.target.value }))} required />
            </div>
            <div className="form-field-group">
              <label>Username / Email</label>
              <input type="text" value={String(form.credential.credential_metadata?.username || form.credential.credential_metadata?.email || "")} onChange={(event) => updateCredentialMetadata(vendor === "jira" ? "email" : "username", event.target.value)} />
            </div>
            <div className="form-field-group">
              <label>Token / Password</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
          </>
        );
      case "pagerduty":
      case "opsgenie":
      case "slack":
      case "github":
      case "gitlab":
      case "argocd":
      case "kubernetes":
        return (
          <>
            <div className="form-field-group">
              <label>Endpoint URL</label>
              <input type="url" value={form.endpoint_url} onChange={(event) => setForm((current) => ({ ...current, endpoint_url: event.target.value }))} placeholder={vendor === "github" ? "https://api.github.com" : "https://api.vendor.com"} />
            </div>
            <div className="form-field-group">
              <label>Token</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
          </>
        );
      case "teams":
        return (
          <div className="form-field-group">
            <label>Incoming Webhook URL</label>
            <input type="url" value={form.endpoint_url} onChange={(event) => setForm((current) => ({ ...current, endpoint_url: event.target.value }))} required />
          </div>
        );
      case "azure":
        return (
          <>
            <div className="form-field-group">
              <label>Tenant ID</label>
              <input type="text" value={String(form.credential.credential_metadata?.tenant_id || "")} onChange={(event) => updateCredentialMetadata("tenant_id", event.target.value)} />
            </div>
            <div className="form-field-group">
              <label>Client ID</label>
              <input type="text" value={String(form.credential.credential_metadata?.client_id || "")} onChange={(event) => updateCredentialMetadata("client_id", event.target.value)} />
            </div>
            <div className="form-field-group">
              <label>Client Secret</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
          </>
        );
      case "gcp":
        return (
          <>
            <div className="form-field-group">
              <label>Project ID</label>
              <input type="text" value={String(form.credential.credential_metadata?.project_id || "")} onChange={(event) => updateCredentialMetadata("project_id", event.target.value)} />
            </div>
            <div className="form-field-group">
              <label>Service Account JSON / Secret Ref</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} />
            </div>
          </>
        );
      default:
        return (
          <>
            <div className="form-field-group">
              <label>Endpoint URL</label>
              <input type="url" value={form.endpoint_url} onChange={(event) => setForm((current) => ({ ...current, endpoint_url: event.target.value }))} placeholder={`https://api.${vendor}.com`} />
            </div>
            <div className="form-field-group">
              <label>Authentication Token / Secret</label>
              <input type="password" value={form.credential.secret_ref} onChange={(event) => setForm((current) => ({ ...current, credential: { ...current.credential, secret_ref: event.target.value } }))} placeholder="Enter API key or bearer token" />
            </div>
          </>
        );
    }
  };

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="integration-config-layout">
      <header className="integration-config-header">
        <button className="back-btn" onClick={() => navigate("/integrations")}>←</button>
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          {logo && (
            <div className="integration-logo-box" style={{ width: "64px", height: "64px" }}>
              <img src={logo} alt={`${vendorName} logo`} />
            </div>
          )}
          <div>
            <h2>Configure {vendorName}</h2>
            <p style={{ color: "var(--text-muted)", fontSize: "0.9rem", margin: 0 }}>
              Set up credentials and binding for the {vendorName} integration.
            </p>
          </div>
        </div>
      </header>

      {error && <div className="rounded-lg border border-red-500/40 bg-red-900/20 p-3 mb-6 text-sm text-red-300">{error}</div>}
      {isLoading && <div className="text-sm text-muted mb-6">Loading integration...</div>}

      <form onSubmit={handleSave}>
        <div className="config-section">
          <h3>Connection Details</h3>
          <div className="form-field-group">
            <label>Name</label>
            <input type="text" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required />
          </div>
          {renderVendorSpecificFields()}
        </div>

        <div className="config-section">
          <h3>Environment Binding</h3>
          <div className="form-field-group">
            <label>Environment</label>
            <input type="text" value={binding.environment} onChange={(event) => setForm((current) => ({ ...current, bindings: [{ ...binding, environment: event.target.value }] }))} placeholder="production" />
          </div>
          <div className="form-field-group">
            <label>Application Name</label>
            <input type="text" value={binding.application_name} onChange={(event) => setForm((current) => ({ ...current, bindings: [{ ...binding, application_name: event.target.value }] }))} placeholder="customer-portal" />
            <p>Leave both fields blank to make this the global default source.</p>
          </div>
          <div className="form-field-group">
            <label>Priority</label>
            <input type="number" value={binding.priority} onChange={(event) => setForm((current) => ({ ...current, bindings: [{ ...binding, priority: Number(event.target.value) || 10 }] }))} min={1} />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "24px", paddingTop: "24px", borderTop: "1px solid var(--glass-border)" }}>
            <input
              type="checkbox"
              id="enabledCheck"
              checked={form.enabled}
              onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))}
              style={{ width: "18px", height: "18px", accentColor: "var(--accent-blue)" }}
            />
            <label htmlFor="enabledCheck" style={{ fontSize: "0.95rem", fontWeight: 600, cursor: "pointer" }}>Enable this integration immediately</label>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "16px", marginTop: "32px" }}>
          <button type="button" className="action-button" style={{ background: "rgba(255,255,255,0.05)" }} onClick={() => navigate("/integrations")} disabled={isSaving}>
            Cancel
          </button>
          <button type="submit" className="action-button action-button--primary" style={{ minWidth: "160px" }} disabled={isSaving || isLoading || !canManageIntegrations}>
            {isSaving ? "Saving..." : "Save Integration"}
          </button>
        </div>
      </form>
    </motion.div>
  );
}
