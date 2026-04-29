import os
from typing import Any, Dict

from django.db.models import Avg, Case, Count, FloatField, Value, When

from .models import RemediationOutcome


def _weight(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _avg_boolean(field_name: str) -> Case:
    return Case(
        When(**{field_name: True}, then=Value(1.0)),
        default=Value(0.0),
        output_field=FloatField(),
    )


def rank_typed_action(action_payload: Dict[str, Any], *, service: str = "", environment: str = "", blast_radius_size: int = 0) -> Dict[str, Any]:
    action_type = str((action_payload or {}).get("action") or "")
    signature = str((action_payload or {}).get("command") or "")
    queryset = RemediationOutcome.objects.all()
    if action_type:
        queryset = queryset.filter(action_type=action_type)
    if service:
        queryset = queryset.filter(service=service)

    overall = queryset.aggregate(
        sample_size=Count("id"),
        success_rate=Avg(_avg_boolean("success")),
        avg_ttr=Avg("time_to_recovery_seconds"),
        avg_blast_radius=Avg("blast_radius_risk"),
    )
    env_match = queryset.filter(environment=environment).aggregate(
        sample_size=Count("id"),
        success_rate=Avg(_avg_boolean("success")),
    ) if environment else {"sample_size": 0, "success_rate": None}
    signature_match = queryset.filter(action_signature=signature).aggregate(
        sample_size=Count("id"),
        success_rate=Avg(_avg_boolean("success")),
    ) if signature else {"sample_size": 0, "success_rate": None}

    success_score = float(signature_match.get("success_rate") or env_match.get("success_rate") or overall.get("success_rate") or 0.0)
    recovery_penalty = float((overall.get("avg_ttr") or 0.0) / max(_weight("AIOPS_RANKING_TTR_NORMALIZER", 1800.0), 1.0))
    blast_penalty = float((overall.get("avg_blast_radius") or float(blast_radius_size or 0)) / max(_weight("AIOPS_RANKING_BLAST_RADIUS_NORMALIZER", 10.0), 1.0))
    environment_bonus = 1.0 if environment and (env_match.get("sample_size") or 0) > 0 else 0.0

    score = (
        success_score * _weight("AIOPS_RANKING_SUCCESS_WEIGHT", 0.55)
        + environment_bonus * _weight("AIOPS_RANKING_ENVIRONMENT_WEIGHT", 0.15)
        + min((signature_match.get("sample_size") or 0) / max(_weight("AIOPS_RANKING_SAMPLE_NORMALIZER", 5.0), 1.0), 1.0) * _weight("AIOPS_RANKING_HISTORY_WEIGHT", 0.20)
        - recovery_penalty * _weight("AIOPS_RANKING_TTR_WEIGHT", 0.05)
        - blast_penalty * _weight("AIOPS_RANKING_BLAST_RADIUS_WEIGHT", 0.05)
    )

    return {
        "score": round(score, 4),
        "sample_size": int(overall.get("sample_size") or 0),
        "environment_sample_size": int(env_match.get("sample_size") or 0),
        "signature_sample_size": int(signature_match.get("sample_size") or 0),
        "success_rate": round(success_score, 4),
        "avg_time_to_recovery_seconds": overall.get("avg_ttr"),
        "avg_blast_radius_risk": overall.get("avg_blast_radius"),
        "environment_match": bool(environment and (env_match.get("sample_size") or 0) > 0),
        "action_type": action_type,
        "service": service,
    }
