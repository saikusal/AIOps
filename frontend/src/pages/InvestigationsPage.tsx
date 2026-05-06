import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { fetchInvestigationRuns, type InvestigationRunSummary } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function stageTone(stage: string) {
  const normalized = stage.toLowerCase();
  if (normalized === "resolved" || normalized === "completed") return "healthy";
  if (normalized === "verifying" || normalized === "planning_next_step" || normalized === "assessing_evidence") return "warning";
  if (normalized === "failed") return "critical";
  return "healthy";
}

function confidenceLabel(score?: number) {
  if (typeof score !== "number") return "unknown";
  if (score >= 0.8) return "high";
  if (score <= 0.4) return "low";
  return "medium";
}

function formatWhen(value?: string) {
  if (!value) return "just now";
  return new Date(value).toLocaleString();
}

function InvestigationRow({ run }: { run: InvestigationRunSummary }) {
  const planner = (run.planner || {}) as Record<string, unknown>;
  const iterationPlan = (planner.iteration_plan || {}) as Record<string, unknown>;
  const candidateSteps = Array.isArray(iterationPlan.candidate_steps) ? iterationPlan.candidate_steps as Array<Record<string, unknown>> : [];
  const nextTool = String((candidateSteps[0] || {}).tool_name || "");
  const contradiction = (run.contradiction_assessment || {}) as Record<string, unknown>;
  const evidenceGap = (run.evidence_gap_assessment || {}) as Record<string, unknown>;

  return (
    <article className={`investigation-run-card investigation-run-card--${stageTone(run.current_stage || run.status)}`}>
      <div className="investigation-run-card__header">
        <div className="investigation-run-card__title">
          <div className="eyebrow">Investigation Run</div>
          <h3>{run.question}</h3>
          <p>{run.incident_title || run.incident_key || run.target_host || "Unscoped run"}</p>
        </div>
        <div className="investigation-run-card__status">
          <span className={`fleet-status fleet-status--${stageTone(run.current_stage || run.status)}`}>{run.current_stage || run.status}</span>
          <span className="investigation-run-card__timestamp">Updated {formatWhen(run.updated_at)}</span>
        </div>
      </div>
      <div className="investigation-run-card__metrics">
        <div><span>Application</span><strong>{run.application || "—"}</strong></div>
        <div><span>Service</span><strong>{run.service || "—"}</strong></div>
        <div><span>Confidence</span><strong>{confidenceLabel(run.confidence_score)} ({Math.round((run.confidence_score || 0) * 100)}%)</strong></div>
        <div><span>Tool calls</span><strong>{run.tool_call_count}</strong></div>
        <div><span>Contradictions</span><strong>{String(contradiction.severity || "none")}</strong></div>
        <div><span>Evidence gaps</span><strong>{String(evidenceGap.status || "none")}</strong></div>
      </div>
      <div className="investigation-run-card__detail">
        <div>
          <span>Next planned tool</span>
          <strong>{nextTool || "No further tool planned"}</strong>
        </div>
        <div>
          <span>Current target</span>
          <strong>{run.target_host || run.service || "unscoped"}</strong>
        </div>
      </div>
      <div className="page-card__meta investigation-run-card__actions">
        {run.incident_key ? (
          <Link className="shell__link shell__link--small" to={`/incidents?incident=${encodeURIComponent(run.incident_key)}`}>
            Open Incident
          </Link>
        ) : null}
        <Link className="shell__link shell__link--small" to={`/investigations/${run.run_id}`}>
          Open Investigation
        </Link>
      </div>
    </article>
  );
}

export function InvestigationsPage() {
  const [searchParams] = useSearchParams();
  const refreshQueryOptions = useRefreshQueryOptions();
  const incidentKey = searchParams.get("incident_key") || "";
  const targetHost = searchParams.get("target_host") || "";

  const investigationsQuery = useQuery({
    queryKey: ["investigations", incidentKey, targetHost],
    queryFn: () => fetchInvestigationRuns({ incident_key: incidentKey || undefined, target_host: targetHost || undefined }),
    ...refreshQueryOptions,
  });

  const runs = investigationsQuery.data || [];
  const activeRuns = runs.filter((run) => !["resolved", "completed", "failed"].includes((run.current_stage || run.status).toLowerCase()));

  return (
    <>
      <section className="hero-card hero-card--investigations">
        <div className="eyebrow">Live Investigation</div>
        <h2>Investigation Runs</h2>
        <p>See what the control plane is doing in real time, which tools it called, and how confidence changes before the RCA is finalized.</p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Runs {runs.length}</div>
          <div className="hero-card__chip">Active {activeRuns.length}</div>
          <div className="hero-card__chip">Filter {incidentKey || targetHost || "all"}</div>
        </div>
      </section>

      {investigationsQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Loading investigation runs</h2>
          <p>The control plane is fetching the latest staged investigations.</p>
        </section>
      ) : null}

      {!investigationsQuery.isLoading && runs.length === 0 ? (
        <section className="page-card">
          <div className="eyebrow">No Runs</div>
          <h2>No investigations match this filter</h2>
          <p>Try opening an incident or asking the assistant an RCA question to create a new investigation run.</p>
        </section>
      ) : null}

      <section className="investigations-layout">
        {runs.map((run) => (
          <InvestigationRow key={run.run_id} run={run} />
        ))}
      </section>
    </>
  );
}
