import { useQuery } from "@tanstack/react-query";
import { fetchTelemetryProfiles } from "../lib/api";

export function ProfilesPage() {
  const profilesQuery = useQuery({
    queryKey: ["fleet-profiles"],
    queryFn: fetchTelemetryProfiles,
  });

  const profiles = profilesQuery.data || [];

  return (
    <>
      <section className="hero-card hero-card--profiles">
        <div className="eyebrow">Telemetry Profiles</div>
        <h2>Install Profiles</h2>
        <p>
          Profiles define the default Linux bundle shape for Phase 1 so operators can choose infra-only or richer observability without hand-assembling components.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Infra only</div>
          <div className="hero-card__chip">Infra + logs</div>
          <div className="hero-card__chip">Infra + logs + traces</div>
        </div>
      </section>

      {profilesQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching telemetry profiles</h2>
          <p>The control plane is loading the initial enrollment profiles.</p>
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
      )}
    </>
  );
}
