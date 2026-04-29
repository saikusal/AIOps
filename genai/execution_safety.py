"""
execution_safety.py — backward-compatibility shim
==================================================
All execution safety primitives have been consolidated into the EGAP protocol.
This module re-exports them so existing imports continue to work.

  from genai.execution_safety import issue_approval_token, ...
  → resolves to genai.egap_protocol
"""

from genai.egap_protocol import (  # noqa: F401  (re-exports)
    # §1 AUTHENTICATION
    sign_payload as sign_intent_payload,
    action_signature,
    context_fingerprint,
    resolve_idempotency_key,
    # §4 APPROVALS
    issue_approval_token,
    verify_approval_token,
    # §5 ALERTS
    frequency_limit_config,
)
