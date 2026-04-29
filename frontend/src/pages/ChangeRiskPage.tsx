import { useMutation } from "@tanstack/react-query";
import { type ChangeEvent, useState } from "react";
import { analyzeChangeRisk, type ChangeRiskResult } from "../lib/api";

const CHANGE_TYPES = ["deployment", "configuration", "database migration", "infrastructure", "rollback", "patch"];

function riskColor(level?: string) {
  switch (level) {
    case "critical": return "var(--color-danger, #ef4444)";
    case "high": return "var(--color-warning, #f59e0b)";
    case "medium": return "var(--color-caution, #eab308)";
    case "low": return "var(--color-success, #22c55e)";
    default: return "var(--color-muted, #6b7280)";
  }
}

export function ChangeRiskPage() {
  const [service, setService] = useState("");
  const [changeType, setChangeType] = useState("deployment");
  const [changeDescription, setChangeDescription] = useState("");
  const [plannedAt, setPlannedAt] = useState("");
  const [result, setResult] = useState<ChangeRiskResult | null>(null);

  const analyseMutation = useMutation({
    mutationFn: () =>
      analyzeChangeRisk({
        service,
        change_description: changeDescription,
        planned_at: plannedAt,
        change_type: changeType,
      }),
    onSuccess: setResult,
  });

  const analysis = result?.analysis;

  return (
    <>
      <section className="hero-card">
        <div className="eyebrow">M6 — GenAI</div>
        <h2>Change Risk Explainer</h2>
        <p>
          Describe a planned deployment or configuration change. Qwen analyses your
          topology blast radius, recent incidents, and dependency graph to return a
          risk score, affected services, and the optimal maintenance window.
        </p>
      </section>

      <section className="page-card" style={{ maxWidth: "720px" }}>
        <div className="eyebrow">Plan Details</div>

        <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "0.75rem" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.85rem" }}>
            Service / Component
            <input
              className="assistant-input"
              style={{ padding: "0.5rem 0.75rem", borderRadius: "0.375rem", border: "1px solid var(--color-border, #374151)", background: "var(--color-surface-2, #1e293b)", color: "inherit", fontSize: "0.9rem" }}
              placeholder="e.g. app-orders, payment-gateway, db-primary"
              value={service}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setService(e.target.value)}
            />
          </label>

          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.85rem" }}>
            Change Type
            <select
              style={{ padding: "0.5rem 0.75rem", borderRadius: "0.375rem", border: "1px solid var(--color-border, #374151)", background: "var(--color-surface-2, #1e293b)", color: "inherit", fontSize: "0.9rem" }}
              value={changeType}
              onChange={(e: ChangeEvent<HTMLSelectElement>) => setChangeType(e.target.value)}
            >
              {CHANGE_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </label>

          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.85rem" }}>
            Change Description
            <textarea
              style={{ padding: "0.5rem 0.75rem", borderRadius: "0.375rem", border: "1px solid var(--color-border, #374151)", background: "var(--color-surface-2, #1e293b)", color: "inherit", fontSize: "0.9rem", minHeight: "90px", resize: "vertical" }}
              placeholder="Describe exactly what is being changed, why, and the expected scope…"
              value={changeDescription}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setChangeDescription(e.target.value)}
            />
          </label>

          <label style={{ display: "flex", flexDirection: "column", gap: "0.3rem", fontSize: "0.85rem" }}>
            Planned Date/Time (optional)
            <input
              type="datetime-local"
              style={{ padding: "0.5rem 0.75rem", borderRadius: "0.375rem", border: "1px solid var(--color-border, #374151)", background: "var(--color-surface-2, #1e293b)", color: "inherit", fontSize: "0.9rem" }}
              value={plannedAt}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setPlannedAt(e.target.value)}
            />
          </label>

          <div>
            <button
              className="assistant-button"
              onClick={() => analyseMutation.mutate()}
              disabled={analyseMutation.isPending || !changeDescription.trim()}
            >
              {analyseMutation.isPending ? "Analysing with Qwen…" : "Analyse Change Risk"}
            </button>
          </div>
        </div>
      </section>

      {analyseMutation.isError ? (
        <section className="page-card">
          <div className="eyebrow" style={{ color: "var(--color-danger)" }}>Error</div>
          <p>{(analyseMutation.error as Error).message}</p>
        </section>
      ) : null}

      {result && analysis ? (
        <>
          {/* Risk score banner */}
          <section className="page-card" style={{ borderLeft: `4px solid ${riskColor(analysis.risk_level)}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: "1.5rem", flexWrap: "wrap" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: "2.5rem", fontWeight: 800, lineHeight: 1, color: riskColor(analysis.risk_level) }}>
                  {analysis.risk_score ?? "—"}
                </div>
                <div style={{ fontSize: "0.72rem", textTransform: "uppercase", opacity: 0.6 }}>Risk Score / 100</div>
              </div>
              <div>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: riskColor(analysis.risk_level) }}>
                  {(analysis.risk_level || "unknown").toUpperCase()} RISK
                </div>
                <div style={{ fontSize: "0.85rem", opacity: 0.75 }}>
                  Recommended window: <strong>{analysis.recommended_window || "Not specified"}</strong>
                </div>
                <div style={{ fontSize: "0.8rem", opacity: 0.6, marginTop: "0.2rem" }}>
                  Blast radius: {(result.blast_radius || []).join(", ") || "none identified"}
                </div>
              </div>
            </div>
          </section>

          {/* Details grid */}
          <section className="prediction-grid" style={{ marginTop: "1rem" }}>
            {(analysis.affected_services || []).length > 0 ? (
              <article className="page-card">
                <div className="eyebrow">Affected Services</div>
                <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
                  {analysis.affected_services.map((s, i) => <li key={i}>{s}</li>)}
                </ul>
              </article>
            ) : null}

            {(analysis.risk_factors || []).length > 0 ? (
              <article className="page-card">
                <div className="eyebrow">Risk Factors</div>
                <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
                  {analysis.risk_factors.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
              </article>
            ) : null}

            {(analysis.mitigations || []).length > 0 ? (
              <article className="page-card">
                <div className="eyebrow">Recommended Mitigations</div>
                <ul style={{ paddingLeft: "1.2rem", margin: 0 }}>
                  {analysis.mitigations.map((m, i) => <li key={i}>{m}</li>)}
                </ul>
              </article>
            ) : null}

            {(analysis.rollback_steps || []).length > 0 ? (
              <article className="page-card">
                <div className="eyebrow">Rollback Steps</div>
                <ol style={{ paddingLeft: "1.2rem", margin: 0 }}>
                  {analysis.rollback_steps.map((s, i) => <li key={i}>{s}</li>)}
                </ol>
              </article>
            ) : null}
          </section>

          {/* Raw AI output fallback */}
          {analysis.raw ? (
            <section className="page-card" style={{ marginTop: "1rem" }}>
              <div className="eyebrow">AI Output</div>
              <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.82rem" }}>{analysis.raw}</pre>
            </section>
          ) : null}
        </>
      ) : null}
    </>
  );
}
