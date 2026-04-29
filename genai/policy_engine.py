"""
policy_engine.py — backward-compatibility shim
===============================================
All policy logic has been consolidated into the EGAP protocol implementation.
This module re-exports canonical names so existing imports continue to work.

  from genai.policy_engine import evaluate_execution_policy, ...
  → resolves to genai.egap_protocol

Direct use of egap_protocol is preferred for new code:

  from genai.egap_protocol import egap_dispatch
  envelope = egap_dispatch(command=..., target_host=..., execution_type=...)
"""

from genai.egap_protocol import (  # noqa: F401  (re-exports)
    # §1 AUTHENTICATION
    sign_payload,
    build_identity,
    action_signature,
    context_fingerprint,
    resolve_idempotency_key,
    # §2 AUTHORIZATION
    classify_action,
    _authorization_config as _policy_config,
    # §3 AUDIT
    record_execution_attempt,
    # §4 APPROVALS
    issue_approval_token,
    verify_approval_token,
    # §5 ALERTS
    frequency_limit_config,
    detect_anomaly,
    # Dispatch
    egap_dispatch,
)

# Legacy alias — views.py calls evaluate_execution_policy(...)
# egap_dispatch() is a drop-in replacement with the same flat output shape.
evaluate_execution_policy = egap_dispatch

POLICY_CACHE_PREFIX = "egap_audit"
