import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchFleetTargets } from "../lib/api";
import { useRefreshInterval } from "../lib/refresh";

function healthTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "healthy" || normalized === "connected") return "healthy";
  if (normalized === "warning" || normalized === "degraded") return "warning";
  return "critical";
}

export function FleetPage() {
  const { refreshMs } = useRefreshInterval();
  const fleetQuery = useQuery({
    queryKey: ["fleet-targets"],
    queryFn: fetchFleetTargets,
    refetchInterval: refreshMs,
  });

  const targets = fleetQuery.data || [];

  return (
    <>
      <section className="hero-card hero-card--fleet">
        <div className="eyebrow">Fleet Control</div>
        <h2>Infrastructure Fleet</h2>
        <p>
          Track enrolled infrastructure, collector health, discovered services, and rollout readiness from a single control plane view.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Linux-first onboarding</div>
          <div className="hero-card__chip">Collector + exporter health</div>
          <div className="hero-card__chip">Discovered services</div>
          <div className="hero-card__chip">Enrollment status</div>
        </div>
      </section>

      {fleetQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching fleet inventory</h2>
          <p>The control plane is loading the Phase 1 fleet overview.</p>
        </section>
      ) : fleetQuery.isError ? (
        <section className="page-card">
          <div className="eyebrow">Error</div>
          <h2>Unable to load fleet inventory</h2>
          <p>Check that the backend fleet scaffolding endpoints are reachable.</p>
        </section>
      ) : (
        <>
          <section className="fleet-summary-grid">
            <article className="fleet-summary-card fleet-summary-card--primary">
              <span>Targets</span>
              <strong>{targets.length}</strong>
              <p>Enrolled or pre-staged infrastructure targets visible to the control plane.</p>
            </article>
            <article className="fleet-summary-card fleet-summary-card--success">
              <span>Connected</span>
              <strong>{targets.filter((target) => target.status === "connected").length}</strong>
              <p>Targets currently heartbeating and sending control-plane status.</p>
            </article>
            <article className="fleet-summary-card fleet-summary-card--accent">
              <span>Discovered Services</span>
              <strong>{targets.reduce((sum, target) => sum + target.discovered_service_count, 0)}</strong>
              <p>Services discovered across enrolled Linux targets in the Phase 1 model.</p>
            </article>
          </section>

          <section className="fleet-grid">
            {targets.map((target) => (
              <article key={target.target_id} className={`fleet-card fleet-card--${healthTone(target.status)}`}>
                <div className="fleet-card__top">
                  <div>
                    <div className="eyebrow">{target.target_type}</div>
                    <h3>{target.name}</h3>
                    <p>{target.hostname} · {target.environment}</p>
                  </div>
                  <span className={`fleet-status fleet-status--${healthTone(target.status)}`}>{target.status}</span>
                </div>

                <div className="fleet-card__meta-grid">
                  <div>
                    <span>Last heartbeat</span>
                    <strong>{target.last_heartbeat}</strong>
                  </div>
                  <div>
                    <span>Profile</span>
                    <strong>{target.profile_name}</strong>
                  </div>
                  <div>
                    <span>Discovered services</span>
                    <strong>{target.discovered_service_count}</strong>
                  </div>
                  <div>
                    <span>Collector</span>
                    <strong>{target.collector_status}</strong>
                  </div>
                </div>

                <div className="fleet-card__components">
                  {target.components.map((component) => (
                    <span key={`${target.target_id}-${component.name}`} className={`fleet-pill fleet-pill--${component.status.toLowerCase()}`}>
                      {component.name}: {component.status}
                    </span>
                  ))}
                </div>

                <div className="page-card__meta">
                  <Link className="shell__link shell__link--small" to="/enroll">
                    Enroll Another Target
                  </Link>
                  <Link className="shell__link shell__link--small" to="/profiles">
                    View Profiles
                  </Link>
                </div>
              </article>
            ))}
          </section>
        </>
      )}
    </>
  );
}
