import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  createAlertNoiseRule,
  disableAlertNoiseRule,
  explainAnomaly,
  fetchAlertNoiseRules,
  fetchRecentAlerts,
  type AlertNoiseRuleInput,
  type AlertRecommendation,
} from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";
import { useTenant } from "../lib/tenant";
import { useQuery } from "@tanstack/react-query";

function AlertCard({ alert }: { alert: AlertRecommendation }) {
  const [explanation, setExplanation] = useState<string | null>(null);
  const source = alert.latest_investigation || alert;
  const explainMutation = useMutation({
    mutationFn: () =>
      explainAnomaly({
        alert_name: alert.alert_name,
        target_host: alert.target_host,
        labels: alert.labels,
        summary: source.initial_ai_diagnosis || source.post_command_ai_analysis || alert.initial_ai_diagnosis || alert.summary,
        incident_key: alert.incident_key,
      }),
    onSuccess: (data) => setExplanation(data.explanation),
  });

  return (
    <article key={alert.alert_id} className="prediction-card">
      <div className="prediction-card__top">
        <div>
          <div className="eyebrow">{alert.status || "unknown"}</div>
          <h3>{alert.alert_name}</h3>
        </div>
        <div
          className={`app-portfolio__status app-portfolio__status--${
            alert.status === "resolved" ? "healthy" : alert.status === "firing" ? "down" : "degraded"
          }`}
        >
          {alert.status || "unknown"}
        </div>
      </div>
      <div className="prediction-card__score">
        <strong>{alert.target_host || "Unknown target"}</strong>
        <span>{(alert.blast_radius || []).length} blast-radius services</span>
      </div>
      <p>{source.post_command_ai_analysis || source.initial_ai_diagnosis || alert.summary || "No summary available yet."}</p>

      {explanation ? (
        <div style={{ marginTop: "0.75rem", padding: "0.6rem", background: "var(--color-surface-2, #1e293b)", borderRadius: "0.375rem", fontSize: "0.82rem", lineHeight: 1.5 }}>
          <strong style={{ display: "block", marginBottom: "0.35rem", fontSize: "0.75rem", textTransform: "uppercase", opacity: 0.6 }}>Anomaly Explanation</strong>
          <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{explanation}</p>
        </div>
      ) : null}

      <div className="page-card__meta">
        {(alert.depends_on || []).map((item) => (
          <code key={`${alert.alert_id}-${item}`}>depends_on:{item}</code>
        ))}
      </div>
      <div className="page-card__meta">
        <Link className="shell__link shell__link--small" to={`/graph/${encodeURIComponent(alert.alert_id)}`}>
          Open Graph
        </Link>
        {alert.incident_key ? (
          <Link className="shell__link shell__link--small" to={`/graph/incident/${encodeURIComponent(alert.incident_key)}`}>
            Incident Graph
          </Link>
        ) : null}
        <Link className="shell__link shell__link--small" to={`/genai?service=${encodeURIComponent(alert.target_host || "")}`}>
          Investigate In Assistant
        </Link>
        <button
          className="shell__link shell__link--small"
          style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
          onClick={() => explainMutation.mutate()}
          disabled={explainMutation.isPending}
        >
          {explainMutation.isPending ? "Explaining..." : explanation ? "Re-explain" : "Explain Anomaly"}
        </button>
      </div>
    </article>
  );
}

export function AlertsPage() {
  const queryClient = useQueryClient();
  const { hasPermission } = useTenant();
  const canManageAlerts = hasPermission("alerts.manage");
  const refreshQueryOptions = useRefreshQueryOptions();
  const [ruleType, setRuleType] = useState<"suppression" | "maintenance">("suppression");
  const [ruleForm, setRuleForm] = useState({
    name: "",
    alert_name: "",
    service_name: "",
    target_host: "",
    environment: "",
    reason: "",
    expires_at: "",
    starts_at: "",
    ends_at: "",
  });
  const alertsQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    ...refreshQueryOptions,
  });
  const noiseRulesQuery = useQuery({
    queryKey: ["alert-noise-rules"],
    queryFn: fetchAlertNoiseRules,
    ...refreshQueryOptions,
  });
  const createRuleMutation = useMutation({
    mutationFn: (input: AlertNoiseRuleInput) => createAlertNoiseRule(input),
    onSuccess: () => {
      setRuleForm({
        name: "",
        alert_name: "",
        service_name: "",
        target_host: "",
        environment: "",
        reason: "",
        expires_at: "",
        starts_at: "",
        ends_at: "",
      });
      queryClient.invalidateQueries({ queryKey: ["alert-noise-rules"] });
    },
  });
  const disableRuleMutation = useMutation({
    mutationFn: ({ type, id }: { type: "suppression" | "maintenance"; id: string }) => disableAlertNoiseRule(type, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alert-noise-rules"] }),
  });

  const submitNoiseRule = () => {
    const payload: AlertNoiseRuleInput = {
      rule_type: ruleType,
      name: ruleForm.name.trim(),
      enabled: true,
      service_name: ruleForm.service_name.trim(),
      target_host: ruleForm.target_host.trim(),
      environment: ruleForm.environment.trim(),
      reason: ruleForm.reason.trim() || (ruleType === "maintenance" ? "maintenance_window" : "suppression_rule"),
    };
    if (ruleType === "suppression") {
      payload.alert_name = ruleForm.alert_name.trim();
      if (ruleForm.expires_at) payload.expires_at = new Date(ruleForm.expires_at).toISOString();
    } else {
      if (ruleForm.starts_at) payload.starts_at = new Date(ruleForm.starts_at).toISOString();
      if (ruleForm.ends_at) payload.ends_at = new Date(ruleForm.ends_at).toISOString();
    }
    createRuleMutation.mutate(payload);
  };
  const stats = noiseRulesQuery.data?.stats;
  const activeSuppressions = noiseRulesQuery.data?.suppressions || [];
  const maintenanceWindows = noiseRulesQuery.data?.maintenance_windows || [];

  return (
    <>
      <section className="hero-card">
        <div className="eyebrow">Alert Feed</div>
        <h2>Active Alert Stream</h2>
        <p>
          Review the latest alert signals, AI diagnosis, and graph entry points without leaving the main observability workflow.
        </p>
      </section>

      <section className="alert-noise-layout">
        <article className="page-card alert-noise-panel">
          <div className="eyebrow">Noise Reduction</div>
          <h2>Suppression And Maintenance</h2>
          <div className="incident-detail__stats alert-noise-stats">
            <div><span>Raw</span><strong>{stats?.raw_notifications ?? 0}</strong></div>
            <div><span>Unique</span><strong>{stats?.unique_lifecycles ?? 0}</strong></div>
            <div><span>Duplicates</span><strong>{stats?.duplicate_notifications ?? 0}</strong></div>
            <div><span>Suppressed</span><strong>{stats?.suppressed_lifecycles ?? 0}</strong></div>
            <div><span>Reduction</span><strong>{Math.round((stats?.noise_reduction_ratio ?? 0) * 100)}%</strong></div>
          </div>
          <div className="alert-noise-form">
            <div className="alert-noise-form__mode">
              <button className={ruleType === "suppression" ? "is-active" : ""} onClick={() => setRuleType("suppression")}>Suppress Alert</button>
              <button className={ruleType === "maintenance" ? "is-active" : ""} onClick={() => setRuleType("maintenance")}>Maintenance</button>
            </div>
            <label>
              Name
              <input value={ruleForm.name} onChange={(event) => setRuleForm((cur) => ({ ...cur, name: event.target.value }))} />
            </label>
            {ruleType === "suppression" ? (
              <label>
                Alert Name
                <input value={ruleForm.alert_name} onChange={(event) => setRuleForm((cur) => ({ ...cur, alert_name: event.target.value }))} placeholder="DemoAppErrorsHigh" />
              </label>
            ) : null}
            <label>
              Service
              <input value={ruleForm.service_name} onChange={(event) => setRuleForm((cur) => ({ ...cur, service_name: event.target.value }))} placeholder="app-inventory" />
            </label>
            <label>
              Target
              <input value={ruleForm.target_host} onChange={(event) => setRuleForm((cur) => ({ ...cur, target_host: event.target.value }))} />
            </label>
            <label>
              Environment
              <input value={ruleForm.environment} onChange={(event) => setRuleForm((cur) => ({ ...cur, environment: event.target.value }))} placeholder="prod" />
            </label>
            <label className="alert-noise-form__wide">
              Reason
              <input value={ruleForm.reason} onChange={(event) => setRuleForm((cur) => ({ ...cur, reason: event.target.value }))} />
            </label>
            {ruleType === "suppression" ? (
              <label>
                Expires
                <input type="datetime-local" value={ruleForm.expires_at} onChange={(event) => setRuleForm((cur) => ({ ...cur, expires_at: event.target.value }))} />
              </label>
            ) : (
              <>
                <label>
                  Starts
                  <input type="datetime-local" value={ruleForm.starts_at} onChange={(event) => setRuleForm((cur) => ({ ...cur, starts_at: event.target.value }))} />
                </label>
                <label>
                  Ends
                  <input type="datetime-local" value={ruleForm.ends_at} onChange={(event) => setRuleForm((cur) => ({ ...cur, ends_at: event.target.value }))} />
                </label>
              </>
            )}
            <button className="assistant-button" onClick={submitNoiseRule} disabled={createRuleMutation.isPending || !ruleForm.name.trim() || !canManageAlerts}>
              {createRuleMutation.isPending ? "Saving..." : "Save Rule"}
            </button>
          </div>
          {createRuleMutation.isError ? <p className="alert-noise-error">{createRuleMutation.error instanceof Error ? createRuleMutation.error.message : "Unable to save rule."}</p> : null}
        </article>
        <article className="page-card alert-noise-panel">
          <div className="eyebrow">Active Controls</div>
          <h2>Noise Rules</h2>
          <div className="alert-noise-rule-list">
            {[...activeSuppressions, ...maintenanceWindows].map((rule) => (
              <div key={`${rule.rule_type}-${rule.id}`} className={`alert-noise-rule ${rule.enabled ? "" : "is-disabled"}`}>
                <div>
                  <strong>{rule.name}</strong>
                  <span>{rule.rule_type === "maintenance" ? "maintenance" : rule.alert_name || "suppression"} · {rule.service_name || rule.target_host || "global"}</span>
                  <small>{rule.reason || "No reason set"}</small>
                </div>
                {rule.enabled ? (
                  <button
                    className="shell__link shell__link--small"
                    onClick={() => disableRuleMutation.mutate({ type: rule.rule_type, id: rule.id })}
                    disabled={disableRuleMutation.isPending || !canManageAlerts}
                  >
                    Disable
                  </button>
                ) : (
                  <span>Disabled</span>
                )}
              </div>
            ))}
            {!noiseRulesQuery.isLoading && activeSuppressions.length === 0 && maintenanceWindows.length === 0 ? (
              <p>No suppression rules or maintenance windows configured.</p>
            ) : null}
          </div>
        </article>
      </section>

      {alertsQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching alerts</h2>
          <p>The frontend is waiting on `/genai/alerts/recent/`.</p>
        </section>
      ) : alertsQuery.isError ? (
        <section className="page-card">
          <div className="eyebrow">Error</div>
          <h2>Unable to load alerts</h2>
          <p>The alert feed is unavailable right now.</p>
        </section>
      ) : (
        <section className="prediction-grid">
          {(alertsQuery.data || []).map((alert) => (
            <AlertCard key={alert.alert_id} alert={alert} />
          ))}
        </section>
      )}
    </>
  );
}
