import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { fetchInvestigationRun } from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

function tone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "resolved" || normalized === "completed") return "healthy";
  if (normalized === "failed") return "critical";
  return "warning";
}

function shortJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatWhen(value?: string | null) {
  if (!value) return "in progress";
  return new Date(value).toLocaleString();
}

export function InvestigationDetailPage() {
  const { runId = "" } = useParams();
  const refreshQueryOptions = useRefreshQueryOptions();
  const runQuery = useQuery({
    queryKey: ["investigation-run", runId],
    queryFn: () => fetchInvestigationRun(runId),
    enabled: Boolean(runId),
    ...refreshQueryOptions,
  });

  const run = runQuery.data;

  if (runQuery.isLoading) {
    return (
      <section className="page-card">
        <div className="eyebrow">Loading</div>
        <h2>Loading investigation</h2>
        <p>The control plane is fetching the live investigation trace.</p>
      </section>
    );
  }

  if (!run) {
    return (
      <section className="page-card">
        <div className="eyebrow">Not Found</div>
        <h2>Investigation not found</h2>
        <p>The requested run could not be loaded.</p>
      </section>
    );
  }

  const confidence = run.confidence_assessment || {};
  const contradiction = run.contradiction_assessment || {};
  const evidenceGaps = run.evidence_gap_assessment || {};
  const iterationPlan = (run.planner || {}).iteration_plan as Record<string, unknown> | undefined;
  const codeContext = ((run.evidence_bundle || {}).code_context || {}) as Record<string, unknown>;
  const evidenceAssessment = ((run.evidence_bundle || {}).evidence_assessment || {}) as Record<string, unknown>;
  const iterations = Array.isArray(iterationPlan?.iterations) ? iterationPlan?.iterations as Array<Record<string, unknown>> : [];

  return (
    <>
      <section className="hero-card hero-card--investigation-detail">
        <div className="eyebrow">Investigation Run</div>
        <h2>{run.question}</h2>
        <p>{run.incident_title || run.incident_key || run.target_host || "Unscoped investigation"} · {run.current_stage}</p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Confidence {Math.round((run.confidence_score || 0) * 100)}%</div>
          <div className="hero-card__chip">Tool Calls {run.tool_calls.length}</div>
          <div className="hero-card__chip">Status {run.status}</div>
          <div className="hero-card__chip">Started {formatWhen(run.created_at)}</div>
        </div>
        <div className="page-card__meta">
          <Link className="shell__link shell__link--small" to="/investigations">
            Back To Investigations
          </Link>
          {run.incident_key ? (
            <Link className="shell__link shell__link--small" to={`/incidents?incident=${encodeURIComponent(run.incident_key)}`}>
              Open Incident
            </Link>
          ) : null}
        </div>
      </section>

      <section className="investigation-summary-grid">
        <article className={`fleet-summary-card fleet-summary-card--${tone(run.current_stage || run.status)}`}>
          <span>Current Stage</span>
          <strong>{run.current_stage}</strong>
          <p>Current live stage reported by the control plane.</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--accent">
          <span>Confidence</span>
          <strong>{String(confidence.level || "unknown")}</strong>
          <p>{String(confidence.summary || "No explicit confidence summary yet.")}</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--primary">
          <span>Contradictions</span>
          <strong>{String(contradiction.severity || "none")}</strong>
          <p>{String(contradiction.summary || "No contradiction summary.")}</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--primary">
          <span>Evidence Gaps</span>
          <strong>{String(evidenceGaps.status || "none")}</strong>
          <p>{String(evidenceGaps.summary || "No evidence-gap summary.")}</p>
        </article>
      </section>

      <section className="investigation-detail-layout">
        <article className="investigation-panel investigation-panel--timeline">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Stage Timeline</div>
              <h3>What the system is doing</h3>
              <p>Live and replayable stages from scoping through verification.</p>
            </div>
          </div>
          <div className="investigation-timeline">
              {run.workflow.map((stage, index) => (
                <div key={`${stage.stage}-${index}`} className={`investigation-timeline__item investigation-timeline__item--${tone(stage.status || stage.stage)}`}>
                  <div className="investigation-timeline__rail">
                    <span className="investigation-timeline__dot" />
                    {index < run.workflow.length - 1 ? <span className="investigation-timeline__line" /> : null}
                  </div>
                  <div className="investigation-timeline__content">
                    <div className="investigation-timeline__header">
                      <strong>{stage.stage}</strong>
                      <span>{stage.status}</span>
                    </div>
                    <div>{stage.summary}</div>
                  {stage.details && Object.keys(stage.details).length > 0 ? (
                    <pre className="investigation-code-block">
                      {shortJson(stage.details)}
                    </pre>
                  ) : null}
                  </div>
                </div>
              ))}
          </div>
        </article>

        <div className="investigation-detail-layout__side">
        <article className="investigation-panel">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Tool Activity</div>
              <h3>{run.tool_calls.length} MCP calls</h3>
              <p>Exact tools invoked while the investigation was running.</p>
            </div>
          </div>
          <div className="investigation-activity-list">
            <ul>
              {run.tool_calls.map((call, index) => (
                <li key={`${call.tool_name}-${index}`} className="investigation-activity-list__item">
                  <div className="investigation-activity-list__title">
                    <strong>{call.tool_name}</strong>
                    <span>{call.latency_ms}ms</span>
                  </div>
                  <div><small>{call.server_name} · {call.created_at}</small></div>
                </li>
              ))}
            </ul>
          </div>
        </article>

        <article className="investigation-panel">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Evidence State</div>
              <h3>Current RCA posture</h3>
              <p>What is missing, what contradicts the hypothesis, and how good the code context is.</p>
            </div>
          </div>
          <div className="investigation-signal-grid">
            <div><span>Missing evidence</span><strong>{run.missing_evidence.length}</strong></div>
            <div><span>Contradictions</span><strong>{run.contradicting_evidence.length}</strong></div>
            <div><span>Code quality</span><strong>{String(codeContext.quality || "unknown")}</strong></div>
            <div><span>Safe to claim code RCA</span><strong>{codeContext.safe_to_claim_code_root_cause ? "yes" : "no"}</strong></div>
          </div>
          {(run.missing_evidence.length > 0 || run.contradicting_evidence.length > 0) ? (
            <div className="checklist-panel" style={{ marginTop: "1rem" }}>
              {run.missing_evidence.length > 0 ? (
                <>
                  <div className="eyebrow">Missing Evidence</div>
                  <ul>{run.missing_evidence.map((item, index) => <li key={`missing-${index}`}>{item}</li>)}</ul>
                </>
              ) : null}
              {run.contradicting_evidence.length > 0 ? (
                <>
                  <div className="eyebrow">Contradicting Evidence</div>
                  <ul>{run.contradicting_evidence.map((item, index) => <li key={`contra-${index}`}>{item}</li>)}</ul>
                </>
              ) : null}
            </div>
          ) : null}
        </article>
        </div>

        <article className="investigation-panel investigation-panel--wide">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Planner And Iterations</div>
              <h3>Next-step control loop</h3>
              <p>Why the system chose the next evidence step and whether it should keep iterating.</p>
            </div>
          </div>
          {iterations.length > 0 ? (
            <div className="investigation-iteration-grid">
              {iterations.map((entry, index) => (
                <div key={`iteration-${index}`} className="investigation-iteration-card">
                  <span>Iteration {String(entry.iteration || index + 1)}</span>
                  <strong>{String(entry.selected_tool || "none")}</strong>
                  <p>{String(entry.reason || "No reason recorded.")}</p>
                </div>
              ))}
            </div>
          ) : null}
          <pre className="investigation-code-block">
            {shortJson(iterationPlan || run.planner || {})}
          </pre>
        </article>

        <article className="investigation-panel investigation-panel--wide">
          <div className="fleet-card__top">
            <div>
              <div className="eyebrow">Evidence Bundle</div>
              <h3>Normalized investigation payload</h3>
              <p>What the control plane had available while it reasoned.</p>
            </div>
          </div>
          <pre className="investigation-code-block">
            {shortJson({
              evidence_assessment: evidenceAssessment,
              code_context: codeContext,
              metrics: (run.evidence_bundle || {}).metrics,
              logs: (run.evidence_bundle || {}).logs,
              traces: (run.evidence_bundle || {}).traces,
            })}
          </pre>
        </article>
      </section>
    </>
  );
}
