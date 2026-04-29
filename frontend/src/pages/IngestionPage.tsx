import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchFleetTargets, fetchTelemetryProfiles } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function healthTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "healthy" || normalized === "connected") return "healthy";
  if (normalized === "warning" || normalized === "degraded") return "warning";
  return "critical";
}

export function IngestionPage() {
  const [tab, setTab] = useState<"fleet" | "profiles">("fleet");
  const refreshQueryOptions = useRefreshQueryOptions();

  const fleetQuery = useQuery({
    queryKey: ["fleet-targets"],
    queryFn: fetchFleetTargets,
    ...refreshQueryOptions,
  });

  const profilesQuery = useQuery({
    queryKey: ["fleet-profiles"],
    queryFn: fetchTelemetryProfiles,
  });

  const targets = fleetQuery.data || [];
  const profiles = profilesQuery.data || [];

  return (
    <>
      <div className="incidents-tabs" style={{ marginBottom: "1.5rem" }}>
        <button
          className={`incidents-tab${tab === "fleet" ? " is-active" : ""}`}
          onClick={() => setTab("fleet")}
        >
          Fleet Targets
        </button>
        <button
          className={`incidents-tab${tab === "profiles" ? " is-active" : ""}`}
          onClick={() => setTab("profiles")}
        >
          Install Profiles
        </button>
      </div>

      {tab === "fleet" && (
        fleetQuery.isLoading ? (
          <section className="page-card">
            <div className="eyebrow">Loading</div>
            <h2>Fetching fleet inventory</h2>
            <p>The control plane is loading the fleet overview.</p>
          </section>
        ) : fleetQuery.isError ? (
          <section className="page-card">
            <div className="eyebrow">Error</div>
            <h2>Unable to load fleet inventory</h2>
            <p>Check that the backend fleet endpoints are reachable.</p>
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
                <strong>{targets.filter((t) => t.status === "connected").length}</strong>
                <p>Targets currently heartbeating and sending control-plane status.</p>
              </article>
              <article className="fleet-summary-card fleet-summary-card--accent">
                <span>Discovered Services</span>
                <strong>{targets.reduce((sum, t) => sum + t.discovered_service_count, 0)}</strong>
                <p>Services discovered across enrolled Linux targets.</p>
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
                    <div><span>Last heartbeat</span><strong>{target.last_heartbeat}</strong></div>
                    <div><span>Profile</span><strong>{target.profile_name}</strong></div>
                    <div><span>Discovered services</span><strong>{target.discovered_service_count}</strong></div>
                    <div><span>Collector</span><strong>{target.collector_status}</strong></div>
                  </div>
                  <div className="fleet-card__components">
                    {target.components.map((component) => (
                      <span key={`${target.target_id}-${component.name}`} className={`fleet-pill fleet-pill--${component.status.toLowerCase()}`}>
                        {component.name}: {component.status}
                      </span>
                    ))}
                  </div>
                  <div className="page-card__meta">
                    <Link className="shell__link shell__link--small" to="/domain-onboarding">Enroll Another Target</Link>
                    <button className="shell__link shell__link--small" onClick={() => setTab("profiles")}>View Profiles</button>
                  </div>
                </article>
              ))}
            </section>
          </>
        )
      )}

      {tab === "profiles" && (
        profilesQuery.isLoading ? (
          <section className="page-card">
            <div className="eyebrow">Loading</div>
            <h2>Fetching telemetry profiles</h2>
            <p>The control plane is loading the enrollment profiles.</p>
          </section>
        ) : profilesQuery.isError ? (
          <section className="page-card">
            <div className="eyebrow">Error</div>
            <h2>Unable to load profiles</h2>
            <p>Check that the backend profile endpoint is reachable.</p>
          </section>
        ) : (
          <section className="profiles-grid">
            {profiles.map((profile) => (
              <article key={profile.slug} className={`profile-card profile-card--${profile.default_for_target === "linux" ? "linux" : "generic"}`}>
                <div className="profile-card__top">
                  <div>
                    <div className="eyebrow">{profile.default_for_target}</div>
                    <h3>{profile.name}</h3>
                  </div>
                  <span className="fleet-status fleet-status--healthy">recommended</span>
                </div>
                <p>{profile.summary}</p>
                <div className="checklist-panel">
                  <div className="eyebrow">Components</div>
                  <ul>
                    {profile.components.map((component) => (
                      <li key={component}>{component}</li>
                    ))}
                  </ul>
                </div>
                <div className="fleet-card__components">
                  {profile.capabilities.map((capability) => (
                    <span key={capability} className="fleet-pill fleet-pill--healthy">{capability}</span>
                  ))}
                </div>
              </article>
            ))}
          </section>
        )
      )}
    </>
  );
}
