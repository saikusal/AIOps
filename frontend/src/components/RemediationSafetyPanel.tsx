/**
 * RemediationSafetyPanel
 *
 * Renders approval, break-glass, rollback, and verification UI flows
 * for execution intents that require operator interaction before proceeding.
 *
 * Usage:
 *   <RemediationSafetyPanel
 *     mode="approval"
 *     intentId="..."
 *     approvalToken="..."
 *     blastRadius={...}
 *     typedAction={...}
 *     onComplete={(result) => ...}
 *     onDismiss={() => ...}
 *   />
 */

import React, { useState } from "react";
import {
  rollbackExecutionIntent,
  verifyExecutionIntent,
  BlastRadiusEstimate,
} from "../lib/api";

type TypedActionLike = {
  action?: string;
  service?: string;
  target?: string;
  reason?: string;
  command?: string;
};

type Mode = "approval" | "break-glass" | "rollback" | "verify";

interface Props {
  mode: Mode;
  intentId: string;
  approvalToken?: string;
  blastRadius?: BlastRadiusEstimate;
  typedAction?: TypedActionLike;
  policyDecision?: Record<string, unknown>;
  onComplete: (result: Record<string, unknown>) => void;
  onDismiss: () => void;
}

const RISK_COLOR: Record<string, string> = {
  low: "#16a34a",
  medium: "#d97706",
  high: "#dc2626",
  critical: "#7c3aed",
};

const VERIFY_OUTCOMES = [
  { value: "resolved", label: "Resolved — issue is gone" },
  { value: "confirmed", label: "Confirmed — fix applied successfully" },
  { value: "partially_improved", label: "Partially improved — still degraded" },
  { value: "unchanged", label: "Unchanged — no effect observed" },
  { value: "worsened", label: "Worsened — situation is worse" },
  { value: "inconclusive", label: "Inconclusive — cannot determine" },
];

function BlastRadiusCard({ br }: { br: BlastRadiusEstimate }) {
  const color = RISK_COLOR[br.risk_label] || "#6b7280";
  return (
    <div style={{ border: `1px solid ${color}`, borderRadius: 6, padding: "10px 14px", marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ fontWeight: 700, color, fontSize: 13 }}>
          Blast Radius — {br.risk_label.toUpperCase()} RISK
        </span>
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          score {br.risk_score.toFixed(2)} · {br.affected_count} service(s) potentially affected
        </span>
      </div>
      {br.affected_services.length > 0 && (
        <div style={{ fontSize: 12, color: "#374151", marginBottom: 4 }}>
          Services: {br.affected_services.slice(0, 6).join(", ")}
          {br.affected_services.length > 6 && ` +${br.affected_services.length - 6} more`}
        </div>
      )}
      <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: "#4b5563" }}>
        {br.reasons.map((r, i) => <li key={i}>{r}</li>)}
      </ul>
    </div>
  );
}

export function RemediationSafetyPanel({
  mode,
  intentId,
  approvalToken,
  blastRadius,
  typedAction,
  policyDecision,
  onComplete,
  onDismiss,
}: Props) {
  const [reason, setReason] = useState("");
  const [breakGlassReason, setBreakGlassReason] = useState("");
  const [verifyOutcome, setVerifyOutcome] = useState("confirmed");
  const [verifyNotes, setVerifyNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApprove = async () => {
    if (!reason.trim()) { setError("Approval reason is required."); return; }
    if (!approvalToken) { setError("No approval token — re-trigger the command first."); return; }
    onComplete({ approval_token: approvalToken, approval_reason: reason, intent_id: intentId });
  };

  const handleBreakGlass = async () => {
    if (!breakGlassReason.trim()) { setError("A reason is mandatory for break-glass activation."); return; }
    onComplete({ break_glass: true, break_glass_reason: breakGlassReason });
  };

  const handleRollback = async () => {
    setLoading(true); setError(null);
    try {
      const result = await rollbackExecutionIntent(intentId, { reason });
      onComplete(result as Record<string, unknown>);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Rollback failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    setLoading(true); setError(null);
    try {
      const result = await verifyExecutionIntent(intentId, {
        outcome: verifyOutcome,
        notes: verifyNotes,
      });
      onComplete(result as Record<string, unknown>);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Verification failed.");
    } finally {
      setLoading(false);
    }
  };

  const panelTitle: Record<Mode, string> = {
    "approval": "Execution Requires Approval",
    "break-glass": "Break-Glass Activation",
    "rollback": "Initiate Rollback",
    "verify": "Post-Action Verification",
  };

  return (
    <div style={{
      background: "#fff",
      border: "1px solid #e5e7eb",
      borderRadius: 8,
      padding: 20,
      maxWidth: 560,
      boxShadow: "0 4px 12px rgba(0,0,0,0.10)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 14 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#111827" }}>
          {panelTitle[mode]}
        </h3>
        <button
          onClick={onDismiss}
          style={{ background: "none", border: "none", cursor: "pointer", fontSize: 18, color: "#6b7280" }}
        >
          ×
        </button>
      </div>

      {/* Action summary */}
      {typedAction && (
        <div style={{ fontSize: 12, background: "#f3f4f6", borderRadius: 4, padding: "8px 10px", marginBottom: 12 }}>
          <strong>{(typedAction.action || "command").replace(/_/g, " ")}</strong>
          {typedAction.service && <span> · {typedAction.service}</span>}
          {typedAction.command && (
            <div style={{ fontFamily: "monospace", marginTop: 4, color: "#374151" }}>
              {typedAction.command.slice(0, 120)}{typedAction.command.length > 120 ? "…" : ""}
            </div>
          )}
        </div>
      )}

      {/* Blast radius */}
      {blastRadius && <BlastRadiusCard br={blastRadius} />}

      {/* Policy block reason */}
      {policyDecision && (policyDecision.approval_reasons as string[] | undefined)?.length ? (
        <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 12 }}>
          <strong>Why approval is required:</strong>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {(policyDecision.approval_reasons as string[]).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {error && (
        <div style={{ color: "#dc2626", fontSize: 13, marginBottom: 10, background: "#fef2f2", borderRadius: 4, padding: "6px 10px" }}>
          {error}
        </div>
      )}

      {/* ---- Approval mode ---- */}
      {mode === "approval" && (
        <>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4, color: "#374151" }}>
            Approval Reason <span style={{ color: "#dc2626" }}>*</span>
          </label>
          <textarea
            rows={3}
            placeholder="Explain why you are approving this action…"
            value={reason}
            onChange={e => setReason(e.target.value)}
            style={{ width: "100%", fontSize: 13, borderRadius: 4, border: "1px solid #d1d5db", padding: "6px 8px", resize: "vertical", boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button onClick={onDismiss} disabled={loading} style={btnGhost}>Cancel</button>
            <button onClick={handleApprove} disabled={loading || !reason.trim()} style={btnPrimary}>
              {loading ? "Approving…" : "Approve & Execute"}
            </button>
          </div>
        </>
      )}

      {/* ---- Break-glass mode ---- */}
      {mode === "break-glass" && (
        <>
          <div style={{ background: "#fef3c7", border: "1px solid #f59e0b", borderRadius: 4, padding: "8px 10px", marginBottom: 12, fontSize: 13, color: "#92400e" }}>
            <strong>Warning:</strong> Break-glass bypasses all policy restrictions. This action will be logged and immediately visible to all administrators.
          </div>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4, color: "#374151" }}>
            Emergency Reason <span style={{ color: "#dc2626" }}>*</span>
          </label>
          <textarea
            rows={3}
            placeholder="Describe the emergency that requires bypassing policy controls…"
            value={breakGlassReason}
            onChange={e => setBreakGlassReason(e.target.value)}
            style={{ width: "100%", fontSize: 13, borderRadius: 4, border: "1px solid #f59e0b", padding: "6px 8px", resize: "vertical", boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button onClick={onDismiss} style={btnGhost}>Cancel</button>
            <button onClick={handleBreakGlass} disabled={!breakGlassReason.trim()} style={{ ...btnPrimary, background: "#dc2626" }}>
              Activate Break-Glass
            </button>
          </div>
        </>
      )}

      {/* ---- Rollback mode ---- */}
      {mode === "rollback" && (
        <>
          <div style={{ fontSize: 13, color: "#374151", marginBottom: 10 }}>
            Rolling back intent <code style={{ fontSize: 12 }}>{intentId.slice(0, 8)}…</code>. A rollback action will be created and must be confirmed before execution.
          </div>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4, color: "#374151" }}>
            Reason for Rollback
          </label>
          <textarea
            rows={2}
            placeholder="Describe why this action should be rolled back…"
            value={reason}
            onChange={e => setReason(e.target.value)}
            style={{ width: "100%", fontSize: 13, borderRadius: 4, border: "1px solid #d1d5db", padding: "6px 8px", resize: "vertical", boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button onClick={onDismiss} disabled={loading} style={btnGhost}>Cancel</button>
            <button onClick={handleRollback} disabled={loading} style={{ ...btnPrimary, background: "#d97706" }}>
              {loading ? "Initiating…" : "Initiate Rollback"}
            </button>
          </div>
        </>
      )}

      {/* ---- Verification mode ---- */}
      {mode === "verify" && (
        <>
          <div style={{ fontSize: 13, color: "#374151", marginBottom: 10 }}>
            Confirm the post-action state for intent <code style={{ fontSize: 12 }}>{intentId.slice(0, 8)}…</code>.
            This must be completed before the linked incident can be resolved.
          </div>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4, color: "#374151" }}>
            Verification Outcome <span style={{ color: "#dc2626" }}>*</span>
          </label>
          <select
            value={verifyOutcome}
            onChange={e => setVerifyOutcome(e.target.value)}
            style={{ width: "100%", fontSize: 13, borderRadius: 4, border: "1px solid #d1d5db", padding: "6px 8px", marginBottom: 10 }}
          >
            {VERIFY_OUTCOMES.map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, marginBottom: 4, color: "#374151" }}>
            Notes
          </label>
          <textarea
            rows={2}
            placeholder="Optional — describe what you observed after the action…"
            value={verifyNotes}
            onChange={e => setVerifyNotes(e.target.value)}
            style={{ width: "100%", fontSize: 13, borderRadius: 4, border: "1px solid #d1d5db", padding: "6px 8px", resize: "vertical", boxSizing: "border-box" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
            <button onClick={onDismiss} disabled={loading} style={btnGhost}>Cancel</button>
            <button onClick={handleVerify} disabled={loading} style={btnPrimary}>
              {loading ? "Submitting…" : "Submit Verification"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

const btnPrimary: React.CSSProperties = {
  background: "#2563eb",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  padding: "7px 16px",
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

const btnGhost: React.CSSProperties = {
  background: "none",
  color: "#374151",
  border: "1px solid #d1d5db",
  borderRadius: 4,
  padding: "7px 16px",
  fontSize: 13,
  cursor: "pointer",
};

export default RemediationSafetyPanel;
