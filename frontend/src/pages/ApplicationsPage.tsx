import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchApplicationOverview, fetchRecentAlerts, type AlertRecommendation, type ApplicationComponent } from "../lib/api";
import { useRefreshInterval } from "../lib/refresh";

function formatPercent(value?: number | null) {
  if (value === null || value === undefined) {
    return "Unknown";
  }
  return `${Math.round(value * 100)}%`;
}

function formatLatency(value?: number | null) {
  if (value === null || value === undefined) {
    return "Unknown";
  }
  return `${value.toFixed(2)}s`;
}

function formatRate(value?: number | null) {
  if (value === null || value === undefined) {
    return "Unknown";
  }
  return `${value.toFixed(1)}/s`;
}

function riskLabel(score?: number | null) {
  const numeric = score ?? 0;
  if (numeric >= 0.75) return "High";
  if (numeric >= 0.45) return "Medium";
  return "Low";
}

function findAlertForService(alerts: AlertRecommendation[], serviceName: string, application?: string) {
  return alerts.find(
    (alert) =>
      alert.target_host === serviceName ||
      alert.target_host === application ||
      alert.blast_radius?.includes(serviceName) ||
      alert.depends_on?.includes(serviceName),
  );
}

function ComponentCard({ application, component, alert }: { application: string; component: ApplicationComponent; alert?: AlertRecommendation }) {
  return (
    <article className={`app-portfolio__component app-portfolio__component--${component.status}`}>
      <div className="app-portfolio__component-top">
        <div>
          <div className="eyebrow">{component.kind}</div>
          <h3>{component.title}</h3>
        </div>
        <span className={`app-portfolio__status app-portfolio__status--${component.status}`}>{component.status}</span>
      </div>
      <p>{component.ai_insight || "No AI insight available yet."}</p>
      <div className="app-portfolio__metrics">
        <div>
          <span>Latency p95</span>
          <strong>{formatLatency(component.metrics?.latency_p95_seconds)}</strong>
        </div>
        <div>
          <span>Error Rate</span>
          <strong>{formatPercent(component.metrics?.error_rate)}</strong>
        </div>
        <div>
          <span>Request Rate</span>
          <strong>{formatRate(component.metrics?.request_rate)}</strong>
        </div>
        <div>
          <span>Risk</span>
          <strong>{riskLabel(component.prediction?.risk_score)} {component.prediction?.risk_score !== undefined && component.prediction?.risk_score !== null ? `(${Math.round(component.prediction.risk_score * 100)}%)` : ""}</strong>
        </div>
      </div>
      <div className="page-card__meta">
        <Link className="shell__link shell__link--small" to={`/assistant?application=${encodeURIComponent(application)}&service=${encodeURIComponent(component.service)}`}>
          Investigate In Assistant
        </Link>
        <Link className="shell__link shell__link--small" to={`/incidents?service=${encodeURIComponent(component.service)}`}>
          View Incidents
        </Link>
        <Link className="shell__link shell__link--small" to={`/graph/application/${encodeURIComponent(application)}`}>
          App Graph
        </Link>
        {alert ? (
          <Link className="shell__link shell__link--small" to={`/graph/${encodeURIComponent(alert.alert_id)}`}>
            Open Graph
          </Link>
        ) : null}
      </div>
    </article>
  );
}

export function ApplicationsPage() {
  const { refreshMs } = useRefreshInterval();
  const overviewQuery = useQuery({
    queryKey: ["applications-overview"],
    queryFn: fetchApplicationOverview,
    refetchInterval: refreshMs,
  });

  const alertsQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    refetchInterval: refreshMs,
  });

  const applications = overviewQuery.data || [];
  const alerts = alertsQuery.data || [];

  return (
    <>
      <section className="hero-card">
        <div className="eyebrow">Portfolio Command Center</div>
        <h2>Applications Experience Layer</h2>
        <p>
          This page now uses the live Django overview endpoint and turns it into an immersive application portfolio.
          It is the first real dashboard migration after the graph page.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Live applications data</div>
          <div className="hero-card__chip">Prediction-aware cards</div>
          <div className="hero-card__chip">Component health</div>
          <div className="hero-card__chip">AI insights</div>
        </div>
      </section>

      {overviewQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching application portfolio</h2>
          <p>The frontend is waiting on `/genai/applications/overview/`.</p>
        </section>
      ) : overviewQuery.isError ? (
        <section className="page-card">
          <div className="eyebrow">Error</div>
          <h2>Unable to load applications</h2>
          <p>Check that the Django backend is running and the Vite proxy is reaching `localhost:8000`.</p>
        </section>
      ) : (
        <section className="app-portfolio">
          {applications.map((application) => (
            <article key={application.application} className={`app-portfolio__card app-portfolio__card--${application.status}`}>
              <div className="app-portfolio__card-head">
                <div>
                  <div className="eyebrow">Application</div>
                  <h2>{application.title}</h2>
                  <p>{application.description}</p>
                </div>
                <div className="app-portfolio__health">
                  <span className={`app-portfolio__status app-portfolio__status--${application.status}`}>{application.status}</span>
                  <strong>{riskLabel(application.prediction?.risk_score)} risk</strong>
                  <div>{application.prediction?.risk_score !== undefined && application.prediction?.risk_score !== null ? `${Math.round(application.prediction.risk_score * 100)}% next ${application.prediction?.predicted_window_minutes || 15}m` : "No prediction yet"}</div>
                </div>
              </div>

              <div className="app-portfolio__headline">
                <strong>AI Insight</strong>
                <p>{application.ai_insight}</p>
              </div>

              <div className="app-portfolio__summary">
                <div className="app-portfolio__summary-chip">
                  <span>Active Alerts</span>
                  <strong>{application.active_alert_count}</strong>
                </div>
                <div className="app-portfolio__summary-chip">
                  <span>Blast Radius</span>
                  <strong>{application.blast_radius?.length || 0} services</strong>
                </div>
                <div className="app-portfolio__summary-chip">
                  <span>Components</span>
                  <strong>{application.components.length}</strong>
                </div>
              </div>

              <div className="page-card__meta">
                <Link className="shell__link shell__link--small" to={`/assistant?application=${encodeURIComponent(application.application)}`}>
                  Open In Assistant
                </Link>
                <Link className="shell__link shell__link--small" to="/incidents">
                  Open Incidents
                </Link>
                <Link className="shell__link shell__link--small" to={`/graph/application/${encodeURIComponent(application.application)}`}>
                  Topology Graph
                </Link>
                {findAlertForService(alerts, application.application, application.application) ? (
                  <Link
                    className="shell__link shell__link--small"
                    to={`/graph/${encodeURIComponent(findAlertForService(alerts, application.application, application.application)!.alert_id)}`}
                  >
                    Open Graph
                  </Link>
                ) : null}
              </div>

              <div className="app-portfolio__component-grid">
                {application.components.map((component) => (
                  <ComponentCard
                    key={`${application.application}-${component.service}`}
                    application={application.application}
                    component={component}
                    alert={findAlertForService(alerts, component.service, application.application)}
                  />
                ))}
              </div>
            </article>
          ))}
        </section>
      )}
    </>
  );
}
