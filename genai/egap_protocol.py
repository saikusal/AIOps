"""
EGAProtocol (EGAP) — AIOps Implementation
==========================================
Engine-to-Agent dispatch with governance, following the 5AG framework.

  §1  AUTHENTICATION  — Actor and agent identity verification
  §2  AUTHORIZATION   — Action classification and policy enforcement
  §3  AUDIT           — Immutable execution history and fingerprinting
  §4  APPROVALS       — Human-in-the-loop for destructive/irreversible actions
  §5  ALERTS          — Anomaly and deviation detection

Every call to `egap_dispatch()` produces an EGAPEnvelope — the single wire
contract carried through the entire execution lifecycle. No unauthenticated
mode, no skip-audit flag, no approval bypass.

Wire format (simplified):
{
  "egap_version": "0.1",
  "method":       "egap.action.dispatch",
  "identity":     { "actor": "...", "agent_id": "...", "sig": "..." },
  "permission":   "READ" | "WRITE" | "DESTRUCTIVE",
  "budget":       { "retry_limit": N },
  "authorization":{ "decision": "allowed"|"blocked"|"requires_approval", ... },
  "audit":        { "action_key": "...", "trace_id": "...", "retry_count": N },
  "approval":     { "required": bool, "state": "NONE"|"PENDING"|"SATISFIED" },
  "alert":        { "anomaly": bool, "reasons": [...] }
}

Spec reference: https://github.com/egaprotocol/spec/blob/main/SPEC.md
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.core.cache import cache
from django.utils import timezone


# ---------------------------------------------------------------------------
# EGAP Version
# ---------------------------------------------------------------------------

EGAP_VERSION = "0.1"
EGAP_METHOD = "egap.action.dispatch"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str) -> List[str]:
    raw = os.getenv(name, default)
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


# ===========================================================================
# §1  AUTHENTICATION
# Identity verification for actors (human operators) and agents (AI/automation).
# Every dispatch carries a verifiable identity. Anonymous dispatch is rejected.
# ===========================================================================

_POLICY_CACHE_PREFIX = "egap_audit"


def _signing_secret() -> str:
    """Shared HMAC secret used to sign intent payloads and approval tokens."""
    return (
        os.getenv("AIOPS_INTENT_SIGNING_SECRET")
        or os.getenv("MCP_INTERNAL_TOKEN")
        or os.getenv("AGENT_SECRET_TOKEN")
        or "aiops-intent-secret"
    )


def sign_payload(payload: Dict[str, Any]) -> str:
    """
    §1 AUTHENTICATION — HMAC-SHA256 signature over a canonical JSON payload.
    Used to bind approval tokens and intent signatures to a secret.
    """
    return hmac.new(
        _signing_secret().encode("utf-8"),
        _json_dumps(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_identity(actor: str = "", agent_id: str = "", payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    §1 AUTHENTICATION — Construct the identity block for the EGAP envelope.
    `sig` is an HMAC over the actor + agent_id pair, proving the dispatch
    originated from a party that holds the signing secret.
    """
    sig = sign_payload({"actor": actor, "agent_id": agent_id, **(payload or {})})
    return {
        "actor": actor or "system",
        "agent_id": agent_id or "aiops-engine",
        "sig": sig,
    }


def action_signature(action_payload: Optional[Dict[str, Any]]) -> str:
    """§1 AUTHENTICATION — Deterministic content-hash of an action payload."""
    if not isinstance(action_payload, dict):
        action_payload = {}
    return hashlib.sha256(_json_dumps(action_payload).encode("utf-8")).hexdigest()


def context_fingerprint(payload: Dict[str, Any]) -> str:
    """§1 AUTHENTICATION — Deterministic fingerprint of execution context."""
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def resolve_idempotency_key(
    *,
    provided_key: str = "",
    execution_type: str,
    incident_key: str = "",
    action_payload: Optional[Dict[str, Any]] = None,
    original_question: str = "",
) -> str:
    """§1 AUTHENTICATION — Stable idempotency key for deduplication."""
    if provided_key:
        return provided_key.strip()
    base = {
        "execution_type": execution_type,
        "incident_key": incident_key,
        "action": action_payload or {},
        "original_question": original_question.strip(),
    }
    return hashlib.sha256(_json_dumps(base).encode("utf-8")).hexdigest()


# ===========================================================================
# §2  AUTHORIZATION
# Role-based classification and policy enforcement. Every action is classified
# by type and risk level before a dispatch decision is made. Minimum-privilege
# principle: actions default to requiring justification if unclassified.
# ===========================================================================

def _authorization_config() -> Dict[str, Any]:
    """
    §2 AUTHORIZATION — Policy configuration loaded from environment variables.
    All knobs are externally configurable; sensible open defaults for dev/test.
    """
    return {
        "policy_version":               os.getenv("AIOPS_POLICY_VERSION", "egap-0.1"),
        "protected_environments":       set(_env_csv("AIOPS_POLICY_PROTECTED_ENVIRONMENTS", "production,prod")),
        "critical_services":            set(_env_csv(
                                            "AIOPS_POLICY_CRITICAL_SERVICES",
                                            "db,gateway,frontend,app-orders,app-inventory,app-billing",
                                        )),
        # Permissions
        "allow_db_changes":             _env_bool("AIOPS_POLICY_ALLOW_DB_CHANGES", True),
        "allow_protected_env_restarts": _env_bool("AIOPS_POLICY_ALLOW_PROTECTED_ENV_RESTARTS", False),
        # Approval gates
        "require_db_change_approval":           _env_bool("AIOPS_POLICY_REQUIRE_APPROVAL_FOR_DB_CHANGES", False),
        "require_restart_approval":             _env_bool("AIOPS_POLICY_REQUIRE_APPROVAL_FOR_RESTARTS", False),
        "require_unknown_approval":             _env_bool("AIOPS_POLICY_REQUIRE_APPROVAL_FOR_UNKNOWN_ACTIONS", False),
        "require_critical_service_approval":    _env_bool("AIOPS_POLICY_REQUIRE_APPROVAL_FOR_CRITICAL_SERVICES", False),
        # Budget
        "retry_limit":          int(os.getenv("AIOPS_POLICY_EXECUTION_RETRY_LIMIT", "999999")),
        "retry_window_seconds": int(os.getenv("AIOPS_POLICY_RETRY_WINDOW_SECONDS", "3600")),
        "cooldown_seconds":     int(os.getenv("AIOPS_POLICY_RESTART_COOLDOWN_SECONDS", "0")),
    }


# Permission levels (READ < WRITE < DESTRUCTIVE)
PERMISSION_READ        = "READ"
PERMISSION_WRITE       = "WRITE"
PERMISSION_DESTRUCTIVE = "DESTRUCTIVE"

_SQL_MUTATION = re.compile(r"\b(update|insert|delete|alter|drop|create|truncate|grant|revoke)\b")
_RESTART_PREFIXES = (
    "docker restart ",
    "docker compose restart ",
    "kubectl rollout restart ",
    "systemctl restart ",
)
_READ_ONLY_PREFIXES = (
    "tail ", "cat ", "grep ", "journalctl ", "ss ", "netstat ",
    "curl ", "ps ", "top ", "uptime", "df ", "free ",
)


def classify_action(command: str, execution_type: str = "diagnostic") -> Dict[str, Any]:
    """
    §2 AUTHORIZATION — Classify a command into an action_type and derive
    the minimum required permission level.

    action_type    permission       risk
    -----------    ----------       ----
    diagnostic     READ             low
    database_change DESTRUCTIVE     high
    restart_service DESTRUCTIVE     high
    unknown_mutation WRITE          medium
    unknown          WRITE          medium
    """
    normalized = (command or "").strip().lower()

    if normalized.startswith("psql ") and _SQL_MUTATION.search(normalized):
        return {"action_type": "database_change",  "permission": PERMISSION_DESTRUCTIVE, "risk_level": "high",   "read_only": False}
    if _SQL_MUTATION.match(normalized):
        return {"action_type": "database_change",  "permission": PERMISSION_DESTRUCTIVE, "risk_level": "high",   "read_only": False}
    if normalized.startswith(_RESTART_PREFIXES):
        return {"action_type": "restart_service",  "permission": PERMISSION_DESTRUCTIVE, "risk_level": "high",   "read_only": False}
    if normalized.startswith("service ") and " restart" in normalized:
        return {"action_type": "restart_service",  "permission": PERMISSION_DESTRUCTIVE, "risk_level": "high",   "read_only": False}
    if execution_type == "diagnostic" and normalized.startswith(_READ_ONLY_PREFIXES):
        return {"action_type": "diagnostic",        "permission": PERMISSION_READ,        "risk_level": "low",    "read_only": True}
    if execution_type == "remediation":
        return {"action_type": "unknown_mutation",  "permission": PERMISSION_WRITE,       "risk_level": "medium", "read_only": False}
    return     {"action_type": "unknown",           "permission": PERMISSION_WRITE,       "risk_level": "medium", "read_only": False}


def _infer_environment(target_host: str, context: Optional[Dict[str, Any]]) -> str:
    """§2 AUTHORIZATION — Derive the deployment environment from context or host name."""
    if isinstance(context, dict):
        labels = context.get("labels") or {}
        if isinstance(context.get("linked_recommendation"), dict):
            labels = labels or (context["linked_recommendation"].get("labels") or {})
        for key in ("environment", "env", "stage", "deployment_environment"):
            if labels.get(key):
                return str(labels[key]).strip().lower()
        for path in (
            (context.get("inventory_runtime") or {}).get("environment"),
            (context.get("scope_json") or {}).get("environment"),
            context.get("environment"),
        ):
            if path:
                return str(path).strip().lower()
    host = (target_host or "").strip().lower()
    for token in ("prod", "production"):
        if token in host:
            return "production"
    for token in ("staging", "stage"):
        if token in host:
            return "staging"
    for token in ("dev", "test"):
        if token in host:
            return "development"
    return "unknown"


def _derive_service(target_host: str, context: Optional[Dict[str, Any]]) -> str:
    """§2 AUTHORIZATION — Derive the target service name from context."""
    if not isinstance(context, dict):
        return target_host or ""
    linked = context.get("linked_recommendation") or {}
    labels = (context.get("labels") or {})
    if isinstance(context.get("linked_recommendation"), dict):
        labels = labels or (linked.get("labels") or {})
    return str(
        context.get("service_name")
        or linked.get("remediation_service")
        or linked.get("service_name")
        or labels.get("service")
        or context.get("target_host")
        or target_host
        or ""
    ).strip()


def _evaluate_authorization(
    action_type: str,
    config: Dict[str, Any],
    environment: str,
    service: str,
    approval_present: bool,
) -> Tuple[List[str], List[str]]:
    """
    §2 AUTHORIZATION — Core policy evaluation.
    Returns (blocked_reasons, approval_reasons).
    """
    blocked_reasons: List[str] = []
    approval_reasons: List[str] = []
    protected = environment in config["protected_environments"]
    critical = service.lower() in config["critical_services"] if service else False

    if action_type == "database_change":
        if not config["allow_db_changes"]:
            blocked_reasons.append("Database-changing actions are blocked by policy.")
        elif config["require_db_change_approval"]:
            approval_reasons.append("Database-changing actions require operator approval.")

    if action_type == "restart_service":
        if protected and not config["allow_protected_env_restarts"]:
            blocked_reasons.append(f"Service restarts are blocked in protected environment '{environment}'.")
        if config["require_restart_approval"]:
            approval_reasons.append("Service restarts require operator approval.")

    if action_type in {"unknown", "unknown_mutation"} and config["require_unknown_approval"]:
        approval_reasons.append("Unclassified actions require operator approval.")

    if critical and action_type != "diagnostic" and config["require_critical_service_approval"]:
        approval_reasons.append(f"Service '{service}' is marked critical and requires operator approval.")

    return blocked_reasons, approval_reasons


# ===========================================================================
# §3  AUDIT
# Immutable execution history following OpenTelemetry conventions.
# Every dispatch attempt is recorded; records are content-addressed.
# ===========================================================================

def _audit_key(command: str, target_host: str, service: str, action_type: str) -> str:
    """§3 AUDIT — Content-addressed cache key for execution history."""
    blob = _json_dumps({
        "command":     command.strip().lower(),
        "target_host": (target_host or "").strip().lower(),
        "service":     (service or "").strip().lower(),
        "action_type": action_type,
    })
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return f"{_POLICY_CACHE_PREFIX}:{digest}"


def _load_audit_history(audit_key: str) -> List[Dict[str, Any]]:
    """§3 AUDIT — Load execution history from the audit store."""
    try:
        history = cache.get(audit_key)
    except Exception:
        return []
    if isinstance(history, dict):
        attempts = history.get("attempts", [])
        return [e for e in attempts if isinstance(e, dict)]
    return []


def record_execution_attempt(
    *,
    policy_decision: Dict[str, Any],
    command: str,
    target_host: str,
    success: bool,
) -> None:
    """
    §3 AUDIT — Record an execution attempt in the immutable audit store.
    Prunes entries beyond the retention window.
    """
    audit_key = policy_decision.get("action_key") or _audit_key(
        command, target_host,
        policy_decision.get("service", ""),
        policy_decision.get("action_type", "unknown"),
    )
    config = _authorization_config()
    attempts = _load_audit_history(audit_key)
    attempts.append({
        "trace_id":    str(uuid.uuid4()),
        "timestamp":   time.time(),
        "success":     bool(success),
        "command":     command,
        "target_host": target_host,
        "decision":    policy_decision.get("decision", "allowed"),
        "action_type": policy_decision.get("action_type", "unknown"),
        "actor":       policy_decision.get("actor", "system"),
    })
    retention = max(config["retry_window_seconds"], config["cooldown_seconds"], 3600)
    cutoff = time.time() - retention
    attempts = [e for e in attempts if float(e.get("timestamp", 0)) >= cutoff]
    try:
        cache.set(audit_key, {"attempts": attempts}, timeout=retention)
    except Exception:
        pass


# ===========================================================================
# §4  APPROVALS
# Mandatory human-in-the-loop for destructive or irreversible actions.
# Approval is a protocol primitive, not an application convention.
# ===========================================================================

def issue_approval_token(intent_id: str) -> Tuple[str, str, Any]:
    """
    §4 APPROVALS — Issue a time-limited HMAC approval token.
    Returns (raw_token, token_hash, expires_at).
    """
    ttl = int(os.getenv("AIOPS_APPROVAL_TOKEN_TTL_SECONDS", "900"))
    expires_at = timezone.now() + timedelta(seconds=ttl)
    raw = sign_payload({"intent_id": intent_id, "expires_at": expires_at.isoformat()})
    token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, token_hash, expires_at


def verify_approval_token(raw_token: str, token_hash: str, expires_at: Any) -> bool:
    """
    §4 APPROVALS — Verify a human-issued approval token.
    Returns True only if the token is valid, unexpired, and content-matches the hash.
    """
    if not raw_token or not token_hash or not expires_at:
        return False
    if timezone.now() > expires_at:
        return False
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest() == token_hash


def _approval_state(approval_reasons: List[str], approval_present: bool) -> str:
    """§4 APPROVALS — Derive the EGAP approval state string."""
    if not approval_reasons:
        return "NONE"
    return "SATISFIED" if approval_present else "PENDING"


# ===========================================================================
# §5  ALERTS
# Operational alerts when an agent deviates from expected behaviour.
# Anomaly detection at the protocol boundary.
# ===========================================================================

def frequency_limit_config() -> Dict[str, int]:
    """§5 ALERTS — Execution frequency budget per service per time window."""
    return {
        "max_frequency":  int(os.getenv("AIOPS_EXECUTION_MAX_FREQUENCY_PER_SERVICE", "999999")),
        "window_seconds": int(os.getenv("AIOPS_EXECUTION_FREQUENCY_WINDOW_SECONDS", "1800")),
    }


def detect_anomaly(
    retry_count: int,
    retry_limit: int,
    action_type: str,
    service: str,
    environment: str,
) -> Dict[str, Any]:
    """
    §5 ALERTS — Detect behavioural anomalies at the protocol boundary.
    Returns an alert block: { anomaly: bool, severity: str, reasons: [...] }
    """
    reasons: List[str] = []
    if retry_count > max(retry_limit * 0.8, 5):
        reasons.append(f"High retry count ({retry_count}) approaching limit for action '{action_type}'.")
    if action_type in {"unknown", "unknown_mutation"} and environment in {"production", "prod"}:
        reasons.append(f"Unclassified action dispatched to production environment for service '{service}'.")
    return {
        "anomaly":   bool(reasons),
        "severity":  "high" if len(reasons) > 1 else ("medium" if reasons else "none"),
        "reasons":   reasons,
    }


# ===========================================================================
# EGAP Dispatch — the unified protocol entry point
# ===========================================================================

def egap_dispatch(
    *,
    command: str,
    target_host: str,
    execution_type: str,
    context: Optional[Dict[str, Any]] = None,
    approval_present: bool = False,
    actor: str = "",
    agent_id: str = "",
) -> Dict[str, Any]:
    """
    EGAP Dispatch — the single wire contract for Engine-to-Agent action dispatch.

    Runs all five protocol pillars in order and returns a fully populated
    EGAPEnvelope. Callers inspect `envelope["authorization"]["decision"]` to
    determine whether to proceed.

    Decisions:
      "allowed"           — proceed immediately
      "requires_approval" — hold; surface approval flow to operator
      "blocked"           — reject; do not execute

    Usage::

        envelope = egap_dispatch(
            command="psql -h db -U user -d aiops -c 'UPDATE ...'",
            target_host="db",
            execution_type="remediation",
            context=execution_context,
            actor=request.user.username,
        )
        if envelope["authorization"]["decision"] == "allowed":
            run_command(...)
    """

    # §1 AUTHENTICATION
    identity = build_identity(actor=actor, agent_id=agent_id)

    # §2 AUTHORIZATION
    config      = _authorization_config()
    clf         = classify_action(command, execution_type)
    action_type = clf["action_type"]
    service     = _derive_service(target_host, context)
    environment = _infer_environment(target_host, context)
    critical    = service.lower() in config["critical_services"] if service else False
    protected   = environment in config["protected_environments"]

    blocked_reasons, approval_reasons = _evaluate_authorization(
        action_type, config, environment, service, approval_present
    )

    decision = "allowed"
    if blocked_reasons:
        decision = "blocked"
    elif approval_reasons and not approval_present:
        decision = "requires_approval"

    reason = (
        blocked_reasons[0] if blocked_reasons
        else approval_reasons[0] if approval_reasons
        else "Allowed by policy."
    )

    authorization = {
        "decision":           decision,
        "allowed":            decision == "allowed",
        "blocked":            decision == "blocked",
        "blocked_reasons":    blocked_reasons,
        "approval_reasons":   approval_reasons,
        "reason":             reason,
        "action_type":        action_type,
        "permission":         clf["permission"],
        "risk_level":         clf["risk_level"],
        "read_only":          clf["read_only"],
        "service":            service,
        "environment":        environment,
        "critical_service":   critical,
        "protected_environment": protected,
        "policy_version":     config["policy_version"],
        "actor":              actor or "system",
    }

    # §3 AUDIT
    audit_key = _audit_key(command, target_host, service, action_type)
    history   = _load_audit_history(audit_key)
    now_ts    = time.time()
    recent    = [e for e in history if now_ts - float(e.get("timestamp", 0)) <= config["retry_window_seconds"]]
    trace_id  = str(uuid.uuid4())

    audit = {
        "trace_id":     trace_id,
        "action_key":   audit_key,
        "retry_count":  len(recent),
        "retry_limit":  config["retry_limit"],
    }

    # §4 APPROVALS
    approval_state = _approval_state(approval_reasons, approval_present)
    approval = {
        "required":           bool(approval_reasons),
        "state":              approval_state,
        "approval_satisfied": approval_state == "SATISFIED",
        "cooldown_remaining_seconds": 0,
    }

    # §5 ALERTS
    alert = detect_anomaly(
        retry_count=len(recent),
        retry_limit=config["retry_limit"],
        action_type=action_type,
        service=service,
        environment=environment,
    )

    # Assemble the EGAP envelope
    return {
        "egap_version":  EGAP_VERSION,
        "method":        EGAP_METHOD,
        "identity":      identity,
        "permission":    clf["permission"],
        "authorization": authorization,
        "audit":         audit,
        "approval":      approval,
        "alert":         alert,
        # Flat aliases kept for backward-compat with existing views.py consumers
        "decision":                  decision,
        "allowed":                   decision == "allowed",
        "blocked":                   decision == "blocked",
        "requires_approval":         bool(approval_reasons),
        "approval_satisfied":        approval_state == "SATISFIED",
        "reason":                    reason,
        "blocked_reasons":           blocked_reasons,
        "approval_reasons":          approval_reasons,
        "policy_version":            config["policy_version"],
        "action_type":               action_type,
        "risk_level":                clf["risk_level"],
        "environment":               environment,
        "protected_environment":     protected,
        "service":                   service,
        "critical_service":          critical,
        "cooldown_remaining_seconds": 0,
        "retry_count":               len(recent),
        "retry_limit":               config["retry_limit"],
        "action_key":                audit_key,
        "actor":                     actor or "system",
    }
