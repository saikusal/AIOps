import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchInvestigationRun,
  type BlastRadiusEstimate,
  type InvestigationLiveStep,
  type InvestigationRunDetail,
  type InvestigationToolCall,
  type TypedAction,
} from "../lib/api";
import { RemediationSafetyPanel } from "../components/RemediationSafetyPanel";

function tone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "resolved" || normalized === "completed") return "healthy";
  if (normalized === "failed") return "critical";
  if (normalized === "running" || normalized === "verifying" || normalized === "assessing_evidence" || normalized === "planning_next_step") {
    return "warning";
  }
  return "healthy";
}

function streamLabel(state: string) {
  if (state === "final") return "Final";
  if (state === "reconnecting") return "Reconnecting";
  if (state === "error") return "Stream Error";
  return "Live";
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

function toolLabel(toolName: string) {
  const labels: Record<string, string> = {
    "incidents.get_timeline": "incident timeline",
    "applications.get_graph": "dependency graph",
    "applications.get_component_snapshot": "component health",
    "metrics.query_service_overview": "service metrics",
    "logs.search": "centralized logs",
    "traces.search": "request traces",
    "runbooks.search": "runbooks",
    "source.read_traceback": "traceback source",
    "code.search_context": "code context",
  };
  return labels[toolName] || toolName;
}

function InvestigationStepCard({ step, isLast }: { step: InvestigationLiveStep; isLast: boolean }) {
  const details = step.technical_details && Object.keys(step.technical_details).length > 0;
  return (
    <div className={`investigation-timeline__item investigation-timeline__item--${tone(step.status || "queued")}`}>
      <div className="investigation-timeline__rail">
        <span className="investigation-timeline__dot" />
        {!isLast ? <span className="investigation-timeline__line" /> : null}
      </div>
      <div className="investigation-timeline__content investigation-step">
        <div className="investigation-timeline__header">
          <strong>{step.title}</strong>
          <span>{step.status}</span>
        </div>
        <p className="investigation-step__summary">{step.summary}</p>
        {step.findings.length > 0 ? (
          <div className="investigation-step__section">
            <span>What We Found</span>
            <ul>
              {step.findings.map((item, index) => (
                <li key={`${step.step_key}-finding-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {step.inference ? (
          <div className="investigation-step__section investigation-step__section--inference">
            <span>What It Means</span>
            <p>{step.inference}</p>
          </div>
        ) : null}
        <div className="investigation-step__meta">
          {step.tool_names.length > 0 ? <small>Sources: {step.tool_names.map(toolLabel).join(", ")}</small> : <small>Internal control-plane stage</small>}
          {step.latest_activity_at ? <small>Updated {formatWhen(step.latest_activity_at)}</small> : null}
        </div>
        {details ? (
          <details className="investigation-step__details">
            <summary>Technical details</summary>
            <pre className="investigation-code-block">{shortJson(step.technical_details)}</pre>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function ToolActivityPanel({ calls }: { calls: InvestigationToolCall[] }) {
  return (
    <article className="investigation-panel">
      <div className="fleet-card__top">
        <div>
          <div className="eyebrow">Tool Activity</div>
          <h3>{calls.length} evidence calls</h3>
          <p>Exact backend tools used while the live investigation was running.</p>
        </div>
      </div>
      <div className="investigation-activity-list">
        <ul>
          {calls.map((call, index) => (
            <li key={`${call.invocation_id || call.tool_name}-${index}`} className="investigation-activity-list__item">
              <div className="investigation-activity-list__title">
                <strong>{toolLabel(call.tool_name)}</strong>
                <span>{call.latency_ms}ms</span>
              </div>
              <div><small>{call.server_name} · {formatWhen(call.created_at)}</small></div>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

export function InvestigationDetailPage() {
  const { runId = "" } = useParams();
  const [liveRun, setLiveRun] = useState<InvestigationRunDetail | null>(null);
  const [streamState, setStreamState] = useState<"live" | "final" | "reconnecting" | "error">("live");
  const [safetyPanel, setSafetyPanel] = useState<{
    mode: "approval" | "break-glass" | "rollback" | "verify";
    intentId: string;
    approvalToken?: string;
    blastRadius?: BlastRadiusEstimate;
    typedAction?: TypedAction;
    policyDecision?: Record<string, unknown>;
  } | null>(null);

  const runQuery = useQuery({
    queryKey: ["investigation-run", runId],
    queryFn: () => fetchInvestigationRun(runId),
    enabled: Boolean(runId),
  });

  useEffect(() => {
    if (!runQuery.data) return;
    setLiveRun((current) => {
      if (!current) return runQuery.data;
      if (current.run_id !== runQuery.data.run_id) return runQuery.data;
      return new Date(runQuery.data.updated_at).getTime() > new Date(current.updated_at).getTime() ? runQuery.data : current;
    });
  }, [runQuery.data]);

  useEffect(() => {
    if (!runId) return undefined;
    const streamUrl = runQuery.data?.stream_url || `/genai/investigations/${runId}/stream/`;
    const source = new EventSource(streamUrl);
    let closedByClient = false;

    const onSnapshot = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as InvestigationRunDetail;
        setLiveRun(payload);
        if (payload.live_summary?.stream_state === "final") {
          closedByClient = true;
          source.close();
          setStreamState("final");
          return;
        }
        setStreamState("live");
      } catch {
        setStreamState("error");
      }
    };

    source.addEventListener("snapshot", onSnapshot as EventListener);
    source.onopen = () => setStreamState((current) => (current === "final" ? current : "live"));
    source.onerror = () => {
      if (closedByClient) {
        return;
      }
      setStreamState((current) => (current === "final" ? current : "reconnecting"));
    };

    return () => {
      closedByClient = true;
      source.removeEventListener("snapshot", onSnapshot as EventListener);
      source.close();
    };
  }, [runId, runQuery.data?.stream_url]);

  const run = liveRun || runQuery.data;
  const confidence = run?.confidence_assessment || {};
  const contradiction = run?.contradiction_assessment || {};
  const evidenceGaps = run?.evidence_gap_assessment || {};
  const liveSummary = run?.live_summary || {};
  const liveSteps = run?.live_steps || [];
  const currentStep = liveSteps.find((item) => item.step_key === liveSummary.active_step_key) || liveSteps[0];

  if (runQuery.isLoading && !run) {
    return (
      <section className="page-card">
        <div className="eyebrow">Loading</div>
        <h2>Loading investigation</h2>
        <p>The control plane is preparing the live investigation screen.</p>
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

  return (
    <>
      <section className="hero-card hero-card--investigation-detail">
        <div className="eyebrow">Investigation Run</div>
        <h2>{run.question}</h2>
        <p>{run.incident_title || run.incident_key || run.target_host || "Unscoped investigation"} · {run.current_stage}</p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Confidence {Math.round((run.confidence_score || 0) * 100)}%</div>
          <div className="hero-card__chip">Steps {liveSummary.completed_steps || 0}/{liveSummary.total_steps || liveSteps.length}</div>
          <div className="hero-card__chip">Status {run.status}</div>
          <div className="hero-card__chip">Stream {streamLabel(streamState)}</div>
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
          <span>Current Step</span>
          <strong>{currentStep?.title || run.current_stage}</strong>
          <p>{currentStep?.summary || "The control plane is continuing the active investigation."}</p>
        </article>
        <article className="fleet-summary-card fleet-summary-card--accent">
          <span>Confidence</span>
          <strong>{String(confidence.level || "unknown")}</strong>
          <p>{String(confidence.summary || liveSummary.current_inference || "No explicit confidence summary yet.")}</p>
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
              <div className="eyebrow">Live Investigation Feed</div>
              <h3>What the system is checking right now</h3>
              <p>Operator-facing progress from scope through evidence, decision, and verification.</p>
            </div>
          </div>
          <div className="investigation-timeline">
            {liveSteps.map((step, index) => (
              <InvestigationStepCard key={step.step_key} step={step} isLast={index === liveSteps.length - 1} />
            ))}
          </div>
        </article>

        <div className="investigation-detail-layout__side">
          <article className="investigation-panel">
            <div className="fleet-card__top">
              <div>
                <div className="eyebrow">Current Inference</div>
                <h3>{currentStep?.title || "Investigation in progress"}</h3>
                <p>The latest conclusion the control plane is comfortable telling the operator.</p>
              </div>
            </div>
            <div className="investigation-current-state">
              <div className={`investigation-current-state__pill investigation-current-state__pill--${streamState}`}>
                {streamLabel(streamState)}
              </div>
              <strong>{liveSummary.current_summary || currentStep?.summary || "Investigation is still gathering evidence."}</strong>
              <p>{liveSummary.current_inference || currentStep?.inference || "The system has not published a stronger inference yet."}</p>
              <small>Last update {formatWhen(run.updated_at)}</small>
            </div>
          </article>

          <ToolActivityPanel calls={run.tool_calls} />

          {/* Remediation safety flows — approval, break-glass, rollback, verify */}
          {safetyPanel && (
            <article className="investigation-panel">
              <div className="fleet-card__top">
                <div>
                  <div className="eyebrow">Operator Action Required</div>
                  <h3>Remediation Gate</h3>
                </div>
              </div>
              <RemediationSafetyPanel
                mode={safetyPanel.mode}
                intentId={safetyPanel.intentId}
                approvalToken={safetyPanel.approvalToken}
                blastRadius={safetyPanel.blastRadius}
                typedAction={safetyPanel.typedAction}
                policyDecision={safetyPanel.policyDecision}
                onComplete={() => setSafetyPanel(null)}
                onDismiss={() => setSafetyPanel(null)}
              />
            </article>
          )}

          <article className="investigation-panel">
            <div className="fleet-card__top">
              <div>
                <div className="eyebrow">Technical Drill-Down</div>
                <h3>Raw evidence on demand</h3>
                <p>Hidden by default so operators can stay on the live narrative unless they need lower-level detail.</p>
              </div>
            </div>
            <details className="investigation-step__details">
              <summary>Show technical evidence bundle</summary>
              <pre className="investigation-code-block">{shortJson(run.evidence_bundle || {})}</pre>
            </details>
            <details className="investigation-step__details">
              <summary>Show workflow and planner internals</summary>
              <pre className="investigation-code-block">{shortJson({ planner: run.planner, workflow: run.workflow })}</pre>
            </details>
          </article>
        </div>
      </section>
    </>
  );
}
