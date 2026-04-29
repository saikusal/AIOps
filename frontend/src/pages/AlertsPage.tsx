import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { explainAnomaly, fetchRecentAlerts, type AlertRecommendation } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";
import { useQuery } from "@tanstack/react-query";

function AlertCard({ alert }: { alert: AlertRecommendation }) {
  const [explanation, setExplanation] = useState<string | null>(null);
  const explainMutation = useMutation({
    mutationFn: () =>
      explainAnomaly({
        alert_name: alert.alert_name,
        target_host: alert.target_host,
        labels: alert.labels,
        summary: alert.initial_ai_diagnosis || alert.summary,
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
      <p>{alert.initial_ai_diagnosis || alert.summary || "No summary available yet."}</p>

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
  const refreshQueryOptions = useRefreshQueryOptions();
  const alertsQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    ...refreshQueryOptions,
  });

  return (
    <>
      <section className="hero-card">
        <div className="eyebrow">Alert Feed</div>
        <h2>Active Alert Stream</h2>
        <p>
          Review the latest alert signals, AI diagnosis, and graph entry points without leaving the main observability workflow.
        </p>
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
