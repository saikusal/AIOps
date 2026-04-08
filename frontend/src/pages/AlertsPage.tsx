import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchRecentAlerts } from "../lib/api";
import { useRefreshInterval } from "../lib/refresh";

export function AlertsPage() {
  const { refreshMs } = useRefreshInterval();
  const alertsQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    refetchInterval: refreshMs,
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
                <Link className="shell__link shell__link--small" to={`/assistant?service=${encodeURIComponent(alert.target_host || "")}`}>
                  Investigate In Assistant
                </Link>
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
