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

function serviceTone(component: ApplicationComponent) {
  const service = component.service.toLowerCase();
  const kind = component.kind.toLowerCase();

  if (service.includes("front") || kind === "edge") return "edge";
  if (service.includes("gateway") || kind === "gateway") return "gateway";
  if (service.includes("db") || kind === "database") return "database";
  if (service.includes("order")) return "orders";
  if (service.includes("inventory")) return "inventory";
  if (service.includes("billing")) return "billing";
  return "default";
}

function applicationGlyph(application: string) {
  const normalized = application.toLowerCase();
  if (normalized.includes("customer")) return "CP";
  if (normalized.includes("payments")) return "PH";
  if (normalized.includes("support")) return "SD";
  if (normalized.includes("analytics")) return "AS";
  return normalized.slice(0, 2).toUpperCase();
}

function ServiceIcon({ component }: { component: ApplicationComponent }) {
  const service = component.service.toLowerCase();
  const kind = component.kind.toLowerCase();
  const tone = serviceTone(component);

  const icon =
    service.includes("front") || kind === "edge" ? (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <rect x="9" y="11" width="30" height="22" rx="5" className="app-portfolio__icon-stroke" />
        <path d="M17 37h14" className="app-portfolio__icon-stroke" />
        <path d="M20 18h18M20 24h10" className="app-portfolio__icon-stroke app-portfolio__icon-stroke--soft" />
      </svg>
    ) : service.includes("gateway") || kind === "gateway" ? (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <path d="M24 7 38 15v18L24 41 10 33V15Z" className="app-portfolio__icon-stroke" />
        <path d="M18 17v14M30 17v14M18 17h12M18 31h12" className="app-portfolio__icon-stroke app-portfolio__icon-stroke--soft" />
        <path d="M14 24h-4M38 24h-4" className="app-portfolio__icon-stroke" />
      </svg>
    ) : service.includes("db") || kind === "database" ? (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <ellipse cx="24" cy="14" rx="11" ry="4.5" className="app-portfolio__icon-stroke" />
        <path d="M13 14v16c0 2.5 4.9 4.5 11 4.5s11-2 11-4.5V14" className="app-portfolio__icon-stroke" />
        <path d="M13 22c0 2.5 4.9 4.5 11 4.5s11-2 11-4.5M13 30c0 2.5 4.9 4.5 11 4.5s11-2 11-4.5" className="app-portfolio__icon-stroke app-portfolio__icon-stroke--soft" />
      </svg>
    ) : (
      <svg viewBox="0 0 48 48" aria-hidden="true">
        <circle cx="13" cy="24" r="4" className="app-portfolio__icon-fill" />
        <circle cx="24" cy="14" r="4" className="app-portfolio__icon-fill" />
        <circle cx="35" cy="24" r="4" className="app-portfolio__icon-fill" />
        <circle cx="24" cy="34" r="4" className="app-portfolio__icon-fill" />
        <path d="M16 22l5-6M27 16l5 6M16 26l5 6M27 32l5-6" className="app-portfolio__icon-stroke" />
      </svg>
    );

  return <div className={`app-portfolio__service-mark app-portfolio__service-mark--${tone}`}>{icon}</div>;
}

function ComponentCard({ application, component, alert }: { application: string; component: ApplicationComponent; alert?: AlertRecommendation }) {
  return (
    <article className={`app-portfolio__component app-portfolio__component--${component.status}`}>
      <div className="app-portfolio__component-top">
        <div className="app-portfolio__component-brand">
          <ServiceIcon component={component} />
          <div>
            <div className="eyebrow">{component.kind}</div>
            <h3>{component.title}</h3>
          </div>
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
                <div className="app-portfolio__application-brand">
                  <div className="app-portfolio__application-mark">
                    <span>{applicationGlyph(application.application)}</span>
                  </div>
                  <div>
                    <div className="eyebrow">Application</div>
                    <h2>{application.title}</h2>
                    <p>{application.description}</p>
                  </div>
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
