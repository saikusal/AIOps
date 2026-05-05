import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchFleetTargets } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function healthTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "healthy" || normalized === "connected") return "healthy";
  if (normalized === "warning" || normalized === "degraded") return "warning";
  return "critical";
}

function runtimeLabel(containerRuntime: string) {
  return containerRuntime === "docker" ? "Docker runtime" : "Host runtime";
}

export function FleetPage() {
  const refreshQueryOptions = useRefreshQueryOptions();
  const fleetQuery = useQuery({
    queryKey: ["fleet-targets"],
    queryFn: fetchFleetTargets,
    ...refreshQueryOptions,
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
              <span>Docker Workloads</span>
              <strong>{targets.reduce((sum, target) => sum + target.runtime_summary.docker_container_count, 0)}</strong>
              <p>Containers discovered across Linux targets that expose a Docker runtime.</p>
            </article>
          </section>

          <section className="fleet-grid">
            {targets.map((target) => (
              <article key={target.target_id} className={`fleet-card fleet-card--${healthTone(target.status)}`}>
                <div className="fleet-card__top">
                  <div>
                    <div className="eyebrow">{target.target_type}</div>
                    <h3>
                      <Link className="shell__link shell__link--small" to={`/fleet/targets/${encodeURIComponent(target.target_id)}`}>
                        {target.name}
                      </Link>
                    </h3>
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
                    <span>Runtime</span>
                    <strong>{runtimeLabel(target.runtime_summary.container_runtime)}</strong>
                  </div>
                </div>

                <div className="fleet-card__components">
                  {target.components.map((component) => (
                    <span key={`${target.target_id}-${component.name}`} className={`fleet-pill fleet-pill--${component.status.toLowerCase()}`}>
                      {component.name}: {component.status}
                    </span>
                  ))}
                </div>

                <div className="fleet-card__components">
                  <span className={`fleet-pill fleet-pill--${healthTone(target.collector_status)}`}>
                    Collector: {target.collector_status}
                  </span>
                  <span className={`fleet-pill fleet-pill--${target.runtime_summary.docker_available ? "healthy" : "warning"}`}>
                    Docker: {target.runtime_summary.docker_available ? `${target.runtime_summary.docker_container_count} containers` : "not detected"}
                  </span>
                </div>

                {target.workload_preview.length > 0 ? (
                  <div className="checklist-panel" style={{ marginTop: "1rem" }}>
                    <div className="eyebrow">Docker Workloads</div>
                    <ul>
                      {target.workload_preview.map((workload) => (
                        <li key={`${target.target_id}-${workload.container_name || workload.service_name}`}>
                          {workload.service_name}
                          {workload.port ? ` :${workload.port}` : ""}
                          {workload.image ? ` · ${workload.image}` : ""}
                          {` · ${workload.status}`}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="page-card__meta">
                  <Link className="shell__link shell__link--small" to={`/fleet/targets/${encodeURIComponent(target.target_id)}`}>
                    View Runtime
                  </Link>
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
