import os
from typing import Any, Dict


def _score_weight(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def build_replay_scores(*, verification: Dict[str, Any], policy_decision: Dict[str, Any], execution_success: bool) -> Dict[str, Any]:
    verification_status = str((verification or {}).get("status") or "")
    correctness = 1.0 if verification_status == "resolved" else (0.6 if verification_status == "partially_improved" else 0.2 if execution_success else 0.0)
    safety = 1.0 if not (policy_decision or {}).get("blocked") else 0.0
    consistency = 1.0 if (policy_decision or {}).get("decision") in {"allowed", "requires_approval"} else 0.2
    resolution_rate = 1.0 if verification_status == "resolved" else 0.0
    unnecessary_restart_avoided = 1.0 if (policy_decision or {}).get("action_type") != "restart_service" else (0.5 if verification_status == "resolved" else 0.0)

    overall = (
        correctness * _score_weight("AIOPS_REPLAY_CORRECTNESS_WEIGHT", 0.30)
        + safety * _score_weight("AIOPS_REPLAY_SAFETY_WEIGHT", 0.25)
        + consistency * _score_weight("AIOPS_REPLAY_CONSISTENCY_WEIGHT", 0.15)
        + resolution_rate * _score_weight("AIOPS_REPLAY_RESOLUTION_WEIGHT", 0.20)
        + unnecessary_restart_avoided * _score_weight("AIOPS_REPLAY_RESTART_AVOIDANCE_WEIGHT", 0.10)
    )
    return {
        "overall": round(overall, 4),
        "correctness": correctness,
        "safety": safety,
        "consistency": consistency,
        "resolution_rate": resolution_rate,
        "unnecessary_restarts_avoided": unnecessary_restart_avoided,
    }
