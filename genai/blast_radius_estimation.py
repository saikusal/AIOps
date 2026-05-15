"""
Pre-execution blast radius estimation.

Produces a structured estimate of how many services and resources could be
affected by a proposed action before it is dispatched to an agent.  This is
shown to operators during dry-run and approval flows so they can make an
informed decision before approving.

The estimate is deliberately conservative — it over-estimates rather than
under-estimates because the cost of a false negative (unexpected impact) is
much higher than a false positive (unnecessary caution).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Tier definitions — order matters: higher index = higher impact
# ---------------------------------------------------------------------------

_CRITICAL_SERVICES = None  # loaded lazily from env


def _get_critical_services() -> set:
    global _CRITICAL_SERVICES
    if _CRITICAL_SERVICES is None:
        raw = os.getenv(
            "AIOPS_POLICY_CRITICAL_SERVICES",
            "db,gateway,frontend,app-orders,app-inventory,app-billing",
        )
        _CRITICAL_SERVICES = {s.strip().lower() for s in raw.split(",") if s.strip()}
    return _CRITICAL_SERVICES


_PROTECTED_ENVIRONMENTS = None


def _get_protected_environments() -> set:
    global _PROTECTED_ENVIRONMENTS
    if _PROTECTED_ENVIRONMENTS is None:
        raw = os.getenv("AIOPS_POLICY_PROTECTED_ENVIRONMENTS", "production,prod")
        _PROTECTED_ENVIRONMENTS = {e.strip().lower() for e in raw.split(",") if e.strip()}
    return _PROTECTED_ENVIRONMENTS


# ---------------------------------------------------------------------------
# Risk scoring helpers
# ---------------------------------------------------------------------------

_ACTION_BASE_RISK: Dict[str, float] = {
    "diagnostic":       0.05,
    "restart_service":  0.60,
    "database_change":  0.85,
    "rollback":         0.50,
    "unknown_mutation": 0.45,
    "unknown":          0.30,
}

_ENV_MULTIPLIER: Dict[str, float] = {
    "production":  2.0,
    "prod":        2.0,
    "staging":     1.2,
    "stage":       1.2,
    "development": 0.6,
    "dev":         0.6,
    "test":        0.5,
}


def _risk_label(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.50:
        return "high"
    if score >= 0.25:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_blast_radius(
    *,
    service: str,
    action_type: str,
    environment: str,
    dependency_graph: Optional[Dict[str, Any]] = None,
    target_host: str = "",
) -> Dict[str, Any]:
    """
    Return a pre-execution blast radius estimate for the proposed action.

    The result is a structured dict that can be stored in
    ``ExecutionIntent.estimated_blast_radius_json`` and surfaced in dry-run
    and approval API responses.

    Fields:
        affected_services   — list of service names that could be impacted
        affected_count      — number of potentially affected services
        risk_score          — float 0.0–1.0 (higher = more dangerous)
        risk_label          — "low" | "medium" | "high" | "critical"
        environment         — resolved environment string
        is_protected_env    — whether the environment is protected
        is_critical_service — whether the target service is critical
        reasons             — human-readable list of contributing factors
        requires_approval   — whether this estimate alone triggers approval
    """
    svc = (service or target_host or "").strip().lower()
    env = (environment or "unknown").strip().lower()

    critical_services = _get_critical_services()
    protected_envs = _get_protected_environments()

    is_critical = svc in critical_services
    is_protected = env in protected_envs

    # Resolve affected services from topology
    affected: List[str] = []
    if isinstance(dependency_graph, dict):
        blast_list = dependency_graph.get("blast_radius") or []
        depends_on = dependency_graph.get("depends_on") or []
        depended_by = dependency_graph.get("depended_by") or dependency_graph.get("dependents") or []
        for node in blast_list + depends_on + depended_by:
            node_str = str(node).strip()
            if node_str and node_str not in affected:
                affected.append(node_str)

    if svc and svc not in affected:
        affected.insert(0, svc)

    affected_count = len(affected)

    # Base risk from action type
    base_risk = _ACTION_BASE_RISK.get(action_type, 0.30)

    # Multiply by environment sensitivity
    env_mult = _ENV_MULTIPLIER.get(env, 1.0)
    risk = base_risk * env_mult

    # Additional penalties
    if is_critical:
        risk = min(1.0, risk + 0.20)
    if affected_count > 3:
        risk = min(1.0, risk + 0.10)
    if affected_count > 6:
        risk = min(1.0, risk + 0.10)

    risk = min(1.0, max(0.0, risk))

    # Build human-readable reasons
    reasons: List[str] = []
    if is_protected:
        reasons.append(f"Environment '{env}' is protected — changes here have production impact.")
    if is_critical:
        reasons.append(f"Service '{svc}' is classified as critical.")
    if affected_count > 1:
        reasons.append(f"{affected_count} services could be affected: {', '.join(affected[:5])}.")
    if action_type == "database_change":
        reasons.append("Database changes can cause cascading failures across all services sharing the schema.")
    if action_type == "restart_service":
        reasons.append("Service restarts cause brief availability loss and may surface downstream timeouts.")
    if action_type == "rollback":
        reasons.append("Rollbacks restore prior state but can reintroduce the conditions that caused the original incident.")
    if not reasons:
        reasons.append("Low-risk diagnostic action with minimal expected side-effects.")

    # Approval trigger: blast radius + risk
    requires_approval = is_protected and action_type != "diagnostic"
    if risk >= 0.50 and action_type != "diagnostic":
        requires_approval = True
    if affected_count > 2 and action_type not in ("diagnostic",):
        requires_approval = True

    return {
        "affected_services":    affected,
        "affected_count":       affected_count,
        "risk_score":           round(risk, 3),
        "risk_label":           _risk_label(risk),
        "environment":          env,
        "is_protected_env":     is_protected,
        "is_critical_service":  is_critical,
        "reasons":              reasons,
        "requires_approval":    requires_approval,
        "action_type":          action_type,
        "service":              svc,
    }
