import hashlib
import json
from datetime import timedelta, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import AlertEvent, AlertSuppression, Incident, IncidentCorrelationLink, MaintenanceWindow


def _labels(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("labels") if isinstance(payload.get("labels"), dict) else {}


def _annotations(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("annotations") if isinstance(payload.get("annotations"), dict) else {}


def _parse_time(value: Any):
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value
    parsed = parse_datetime(str(value))
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone=dt_timezone.utc)
    return parsed


def _stable_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def normalize_alert_payload(alert_payload: Dict[str, Any], *, source: str = "manual") -> Dict[str, Any]:
    labels = _labels(alert_payload)
    annotations = _annotations(alert_payload)
    alert_name = str(alert_payload.get("alert_name") or labels.get("alertname") or "unknown_alert").strip()
    fingerprint = str(alert_payload.get("fingerprint") or labels.get("fingerprint") or alert_payload.get("group_key") or "").strip()
    starts_at_raw = alert_payload.get("starts_at") or alert_payload.get("startsAt")
    starts_at = _parse_time(starts_at_raw)
    ends_at = _parse_time(alert_payload.get("ends_at") or alert_payload.get("endsAt"))
    service_name = str(
        alert_payload.get("service_name")
        or labels.get("service")
        or labels.get("app")
        or labels.get("job")
        or ""
    ).strip()
    target_host = str(alert_payload.get("target_host") or labels.get("instance") or labels.get("pod") or service_name or "").strip()
    environment = str(labels.get("environment") or labels.get("env") or alert_payload.get("environment") or "").strip().lower()
    namespace = str(labels.get("namespace") or alert_payload.get("namespace") or "").strip()
    cluster = str(labels.get("cluster") or alert_payload.get("cluster") or "").strip()
    lifecycle_identity = {
        "alert_name": alert_name,
        "fingerprint": fingerprint,
        "starts_at": starts_at.isoformat() if starts_at else "",
        "service_name": service_name,
        "target_host": target_host,
    }
    if not fingerprint and not starts_at:
        lifecycle_identity["fallback"] = _stable_hash(
            {
                "alert_name": alert_name,
                "service_name": service_name,
                "target_host": target_host,
                "status": alert_payload.get("status") or "firing",
            }
        )
    lifecycle_key = _stable_hash(lifecycle_identity)
    return {
        "source": source,
        "lifecycle_key": lifecycle_key,
        "alert_name": alert_name,
        "fingerprint": fingerprint,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "status": str(alert_payload.get("status") or "firing").strip().lower() or "unknown",
        "severity": str(labels.get("severity") or labels.get("alert_severity") or "warning").strip().lower(),
        "service_name": service_name,
        "target_host": target_host,
        "environment": environment,
        "namespace": namespace,
        "cluster": cluster,
        "labels": labels,
        "annotations": annotations,
        "raw_payload": alert_payload,
    }


def persist_alert_event(alert_payload: Dict[str, Any], *, source: str = "manual", tenant=None) -> Tuple[AlertEvent, bool]:
    data = normalize_alert_payload(alert_payload, source=source)
    if tenant is not None:
        data["tenant"] = tenant
    queryset = AlertEvent.objects.filter(source=data["source"], lifecycle_key=data["lifecycle_key"])
    if tenant is not None:
        queryset = queryset.filter(tenant=tenant)
    event = queryset.first()
    if event:
        event.repeat_count += 1
        for field in (
            "status",
            "severity",
            "service_name",
            "target_host",
            "environment",
            "namespace",
            "cluster",
            "labels",
            "annotations",
            "raw_payload",
            "ends_at",
        ):
            setattr(event, field, data[field])
        event.save(
            update_fields=[
                "repeat_count",
                "status",
                "severity",
                "service_name",
                "target_host",
                "environment",
                "namespace",
                "cluster",
                "labels",
                "annotations",
                "raw_payload",
                "ends_at",
                "last_seen_at",
            ]
        )
        return event, True
    event = AlertEvent.objects.create(**data)
    return event, False


def _matches_scope(rule: Any, event: AlertEvent) -> bool:
    for field in ("alert_name", "service_name", "target_host", "environment"):
        expected = str(getattr(rule, field, "") or "").strip()
        if expected and expected != str(getattr(event, field, "") or "").strip():
            return False
    return True


def evaluate_suppression(event: AlertEvent) -> Tuple[bool, str]:
    now = timezone.now()
    tenant_filter = Q()
    if getattr(event, "tenant_id", None):
        tenant_filter = Q(tenant=event.tenant)
    maintenance = (
        MaintenanceWindow.objects.filter(tenant_filter, enabled=True, starts_at__lte=now, ends_at__gte=now)
        .filter(
            Q(service_name="") | Q(service_name=event.service_name),
            Q(target_host="") | Q(target_host=event.target_host),
            Q(environment="") | Q(environment=event.environment),
        )
        .order_by("-starts_at")
        .first()
    )
    if maintenance:
        return True, maintenance.reason or "maintenance_window"

    rules = AlertSuppression.objects.filter(tenant_filter, enabled=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    for rule in rules:
        if _matches_scope(rule, event):
            return True, rule.reason or "suppression_rule"
    return False, ""


def mark_suppression(event: AlertEvent, suppressed: bool, reason: str = "") -> None:
    event.suppressed = bool(suppressed)
    event.suppression_reason = reason if suppressed else ""
    event.save(update_fields=["suppressed", "suppression_reason", "last_seen_at"])


def attach_incident(event: Optional[AlertEvent], incident: Optional[Incident]) -> None:
    if not event or not incident or event.incident_id == incident.id:
        return
    event.incident = incident
    event.save(update_fields=["incident", "last_seen_at"])


def correlate_incident(event: Optional[AlertEvent], incident: Optional[Incident], *, window_minutes: int = 30) -> List[IncidentCorrelationLink]:
    if not event or not incident:
        return []
    window_start = timezone.now() - timedelta(minutes=window_minutes)
    candidates = Incident.objects.filter(is_deleted=False, updated_at__gte=window_start).exclude(id=incident.id)
    if getattr(incident, "tenant_id", None):
        candidates = candidates.filter(tenant=incident.tenant)
    candidates = candidates.order_by("-updated_at")[:50]
    links: List[IncidentCorrelationLink] = []
    for candidate in candidates:
        score = 0
        reasons: List[str] = []
        if event.service_name and event.service_name == candidate.primary_service:
            score += 40
            reasons.append("same_service")
        if event.target_host and event.target_host == candidate.target_host:
            score += 25
            reasons.append("same_target_host")
        candidate_env = str((candidate.labels or {}).get("environment") or (candidate.labels or {}).get("env") or "").lower()
        if event.environment and candidate_env and event.environment == candidate_env:
            score += 20
            reasons.append("same_environment")
        if event.cluster and str((candidate.labels or {}).get("cluster") or "") == event.cluster:
            score += 15
            reasons.append("same_cluster")
        if event.namespace and str((candidate.labels or {}).get("namespace") or "") == event.namespace:
            score += 15
            reasons.append("same_namespace")
        if score < 40:
            continue
        link, _created = IncidentCorrelationLink.objects.update_or_create(
            source_incident=incident,
            related_incident=candidate,
            defaults={"score": score, "reasons": reasons, "tenant": incident.tenant},
        )
        links.append(link)
    return links


def noise_reduction_stats(*, minutes: int = 1440, tenant=None) -> Dict[str, Any]:
    since = timezone.now() - timedelta(minutes=minutes)
    events = AlertEvent.objects.filter(last_seen_at__gte=since)
    if tenant is not None:
        events = events.filter(tenant=tenant)
    raw_notifications = sum(item.repeat_count for item in events)
    lifecycle_count = events.count()
    duplicate_count = max(raw_notifications - lifecycle_count, 0)
    suppressed_count = events.filter(suppressed=True).count()
    incident_count = events.exclude(incident__isnull=True).values("incident_id").distinct().count()
    return {
        "window_minutes": minutes,
        "raw_notifications": raw_notifications,
        "unique_lifecycles": lifecycle_count,
        "duplicate_notifications": duplicate_count,
        "suppressed_lifecycles": suppressed_count,
        "incidents_created_or_linked": incident_count,
        "noise_reduction_ratio": round((duplicate_count + suppressed_count) / raw_notifications, 4) if raw_notifications else 0.0,
    }
