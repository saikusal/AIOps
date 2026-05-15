"""
views_analytics.py
====================
Production-grade analytics aggregation endpoints.

  GET /genai/analytics/signal-heatmap/
      Services × time buckets × alert density heatmap.
      Queries IncidentAlert (full history, one row per alert firing) rather
      than AlertEvent (upsert model, only latest state per unique alert).

  GET /genai/analytics/correlated-timeline/
      Unified event timeline merging alerts, incidents, and
      execution intents so operators can see causality at a glance.

All endpoints are:
  - Tenant-scoped
  - DB-aggregated (no Python loops over large querysets)
  - Capped to prevent runaway queries
  - CORS-safe (read-only GET, no mutations)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, List

from django.db.models import Count, Q
from django.db.models.functions import TruncDay, TruncHour, TruncMinute
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import ExecutionIntent, Incident, IncidentAlert

logger = logging.getLogger("egap.analytics")

# ---------------------------------------------------------------------------
# Severity ordering — used to pick the dominant severity per bucket
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: Dict[str, int] = {
    "critical": 4,
    "high": 3,
    "warning": 2,
    "info": 1,
    "unknown": 0,
}

# Hard caps to protect DB
_MAX_HOURS = 168          # 7 days
_MAX_ALERT_ROWS = 2000
_MAX_INCIDENT_ROWS = 500
_MAX_EXEC_ROWS = 500


def _incident_alert_qs(request: HttpRequest):
    """
    Returns a tenant-scoped IncidentAlert queryset.
    IncidentAlert has no direct tenant FK; scoping goes through incident__tenant.
    Rows with a null incident tenant are included (legacy/unscoped alerts).
    """
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        return IncidentAlert.objects.none()
    return IncidentAlert.objects.filter(
        Q(incident__tenant=tenant) | Q(incident__tenant__isnull=True)
    )


# ===========================================================================
# Signal Heatmap
# ===========================================================================

@require_GET
def signal_heatmap_view(request: HttpRequest) -> JsonResponse:
    """
    Returns a service × time-bucket alert density matrix.

    Query params:
      hours          (int, default=24)  — lookback window, max 168
      bucket_minutes (int, default=60)  — bucket granularity, 5–1440
      service        (str, optional)    — filter to a single service
      environment    (str, optional)    — filter to a specific environment
      severity       (str, optional)    — filter to a minimum severity
    """
    try:
        hours = min(int(request.GET.get("hours", 24)), _MAX_HOURS)
        bucket_minutes = max(min(int(request.GET.get("bucket_minutes", 60)), 1440), 5)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid numeric parameters."}, status=400)

    service_filter = request.GET.get("service", "").strip()
    env_filter = request.GET.get("environment", "").strip()

    cutoff = timezone.now() - timedelta(hours=hours)

    qs = _incident_alert_qs(request).filter(first_seen_at__gte=cutoff)

    if service_filter:
        qs = qs.filter(service_name=service_filter)
    if env_filter:
        qs = qs.filter(labels__environment=env_filter)

    # Choose truncation based on bucket size
    if bucket_minutes >= 1440:
        trunc_fn = TruncDay("first_seen_at")
    elif bucket_minutes >= 60:
        trunc_fn = TruncHour("first_seen_at")
    else:
        trunc_fn = TruncMinute("first_seen_at")

    raw_cells = (
        qs.annotate(bucket=trunc_fn)
        .values("service_name", "bucket", "status")
        .annotate(count=Count("id"))
        .order_by("service_name", "bucket")
    )

    # Aggregate: merge per (service, bucket) and extract severity from labels
    # Pull labels separately to get severity
    label_qs = (
        qs.annotate(bucket=trunc_fn)
        .values("service_name", "bucket", "labels")
        .order_by("service_name", "bucket")
    )

    services_set: set = set()
    buckets_set: set = set()
    cell_map: Dict[tuple, Dict[str, Any]] = {}

    # Build severity map from labels queryset (one pass)
    sev_map: Dict[tuple, str] = {}
    for row in label_qs:
        svc = row["service_name"] or "unknown"
        bkt = row["bucket"]
        if bkt is None:
            continue
        bkt_iso = bkt.isoformat()
        labels = row["labels"] or {}
        sev = str(labels.get("severity") or labels.get("alert_severity") or "unknown").lower()
        key = (svc, bkt_iso)
        # Keep highest severity seen in this bucket
        if _SEVERITY_ORDER.get(sev, 0) > _SEVERITY_ORDER.get(sev_map.get(key, "unknown"), 0):
            sev_map[key] = sev

    for row in raw_cells:
        svc = row["service_name"] or "unknown"
        bkt = row["bucket"]
        if bkt is None:
            continue
        bkt_iso = bkt.isoformat()
        cnt = int(row["count"])

        services_set.add(svc)
        buckets_set.add(bkt_iso)

        key = (svc, bkt_iso)
        sev = sev_map.get(key, "unknown")
        sev_order = _SEVERITY_ORDER.get(sev, 0)

        if key not in cell_map:
            cell_map[key] = {
                "count": 0,
                "max_severity": "unknown",
                "max_severity_order": -1,
                "severities": {},
            }
        cell_map[key]["count"] += cnt
        cell_map[key]["severities"][sev] = cell_map[key]["severities"].get(sev, 0) + cnt

        if sev_order > cell_map[key]["max_severity_order"]:
            cell_map[key]["max_severity"] = sev
            cell_map[key]["max_severity_order"] = sev_order

    services = sorted(services_set)
    buckets = sorted(buckets_set)

    cells: List[Dict[str, Any]] = [
        {
            "service": svc,
            "bucket": bkt,
            "count": data["count"],
            "max_severity": data["max_severity"],
            "severities": data["severities"],
        }
        for (svc, bkt), data in cell_map.items()
    ]

    max_count = max((c["count"] for c in cells), default=1)

    return JsonResponse({
        "services": services,
        "buckets": buckets,
        "cells": cells,
        "meta": {
            "hours": hours,
            "bucket_minutes": bucket_minutes,
            "total_alerts": sum(c["count"] for c in cells),
            "max_count": max_count,
            "service_count": len(services),
            "generated_at": timezone.now().isoformat(),
        },
    })


# ===========================================================================
# Correlated Timeline
# ===========================================================================

@require_GET
def correlated_timeline_view(request: HttpRequest) -> JsonResponse:
    """
    Returns a unified event stream across alerts, incidents, and execution
    intents, sorted by timestamp, with correlation links between events
    that share an incident_key.

    Query params:
      hours        (int, default=6)   — lookback window, max 168
      service      (str, optional)    — filter to a single service
      incident_key (str, optional)    — scope to a specific incident
    """
    try:
        hours = min(int(request.GET.get("hours", 6)), _MAX_HOURS)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid numeric parameters."}, status=400)

    service_filter = request.GET.get("service", "").strip()
    incident_key_filter = request.GET.get("incident_key", "").strip()

    cutoff = timezone.now() - timedelta(hours=hours)

    events: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 1. Alert events — from IncidentAlert (full history, not upsert)
    # ------------------------------------------------------------------
    alert_qs = (
        _incident_alert_qs(request)
        .filter(first_seen_at__gte=cutoff)
        .select_related("incident")
        .only(
            "id", "alert_name", "service_name", "status", "labels",
            "target_host", "first_seen_at", "last_seen_at",
            "incident__incident_key",
        )
    )
    if service_filter:
        alert_qs = alert_qs.filter(service_name=service_filter)
    if incident_key_filter:
        alert_qs = alert_qs.filter(incident__incident_key=incident_key_filter)

    for a in alert_qs[:_MAX_ALERT_ROWS]:
        labels = a.labels or {}
        sev = str(labels.get("severity") or labels.get("alert_severity") or "unknown").lower()
        env = str(labels.get("environment") or labels.get("env") or "").lower()
        events.append({
            "id": f"alert-{a.id}",
            "type": "alert",
            "lane": "alerts",
            "timestamp": a.first_seen_at.isoformat(),
            "title": a.alert_name,
            "service": a.service_name or "unknown",
            "environment": env,
            "severity": sev,
            "status": a.status or "unknown",
            "incident_key": a.incident.incident_key if a.incident_id else None,
            "meta": {
                "source": labels.get("source") or "",
                "target_host": a.target_host,
                "last_seen_at": a.last_seen_at.isoformat(),
            },
        })

    # ------------------------------------------------------------------
    # 2. Incidents — opened events (and resolved if in window)
    # ------------------------------------------------------------------
    tenant = getattr(request, "tenant", None)
    if tenant is None:
        incident_qs = Incident.objects.none()
    else:
        incident_qs = (
            Incident.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                opened_at__gte=cutoff,
                is_deleted=False,
            )
            .only(
                "incident_key", "title", "primary_service", "severity",
                "status", "priority", "blast_radius", "opened_at", "resolved_at",
            )
        )
    if service_filter:
        incident_qs = incident_qs.filter(primary_service=service_filter)
    if incident_key_filter:
        incident_qs = incident_qs.filter(incident_key=incident_key_filter)

    for inc in incident_qs[:_MAX_INCIDENT_ROWS]:
        events.append({
            "id": f"inc-open-{inc.incident_key}",
            "type": "incident_opened",
            "lane": "incidents",
            "timestamp": inc.opened_at.isoformat(),
            "title": inc.title,
            "service": inc.primary_service or "unknown",
            "environment": "",
            "severity": inc.severity or "warning",
            "status": inc.status,
            "incident_key": inc.incident_key,
            "meta": {
                "priority": inc.priority,
                "blast_radius_count": len(inc.blast_radius or []),
            },
        })
        if inc.resolved_at and inc.resolved_at >= cutoff:
            mttr = int((inc.resolved_at - inc.opened_at).total_seconds() / 60)
            events.append({
                "id": f"inc-close-{inc.incident_key}",
                "type": "incident_resolved",
                "lane": "incidents",
                "timestamp": inc.resolved_at.isoformat(),
                "title": f"Resolved: {inc.title}",
                "service": inc.primary_service or "unknown",
                "environment": "",
                "severity": "info",
                "status": "resolved",
                "incident_key": inc.incident_key,
                "meta": {"mttr_minutes": mttr},
            })

    # ------------------------------------------------------------------
    # 3. Execution intents
    # ------------------------------------------------------------------
    if tenant is None:
        exec_qs = ExecutionIntent.objects.none()
    else:
        exec_qs = (
            ExecutionIntent.objects.filter(
                Q(tenant=tenant) | Q(tenant__isnull=True),
                created_at__gte=cutoff,
            )
            .select_related("incident")
            .only(
                "intent_id", "action_type", "service", "environment",
                "status", "break_glass", "command", "created_at",
                "incident__incident_key",
            )
        )
    if service_filter:
        exec_qs = exec_qs.filter(service=service_filter)
    if incident_key_filter:
        exec_qs = exec_qs.filter(incident__incident_key=incident_key_filter)

    for ei in exec_qs[:_MAX_EXEC_ROWS]:
        sev = (
            "critical" if ei.break_glass
            else "high" if ei.status in ("failed", "blocked")
            else "warning" if ei.status in ("approval_required", "rollback_pending")
            else "info"
        )
        events.append({
            "id": f"exec-{ei.intent_id}",
            "type": "execution",
            "lane": "executions",
            "timestamp": ei.created_at.isoformat(),
            "title": f"{(ei.action_type or 'action').replace('_', ' ').title()}: {ei.service or 'unknown'}",
            "service": ei.service or "unknown",
            "environment": ei.environment or "",
            "severity": sev,
            "status": ei.status,
            "incident_key": ei.incident.incident_key if ei.incident_id else None,
            "meta": {
                "action_type": ei.action_type,
                "break_glass": ei.break_glass,
                "command_preview": (ei.command or "")[:80],
            },
        })

    # Sort by timestamp ascending
    events.sort(key=lambda e: e["timestamp"])

    # ------------------------------------------------------------------
    # Correlation links: events sharing an incident_key
    # ------------------------------------------------------------------
    inc_buckets: Dict[str, List[str]] = {}
    for ev in events:
        ik = ev.get("incident_key")
        if ik:
            inc_buckets.setdefault(ik, []).append(ev["id"])

    links: List[Dict[str, str]] = []
    for ik, eids in inc_buckets.items():
        anchor_id = next(
            (ev["id"] for ev in events
             if ev.get("incident_key") == ik and ev["type"] == "incident_opened"),
            None,
        )
        if anchor_id:
            for eid in eids:
                if eid != anchor_id:
                    links.append({"source": eid, "target": anchor_id, "incident_key": ik})

    lanes = [
        {"id": "alerts",     "label": "Alerts",     "color": "#ff8f95"},
        {"id": "incidents",  "label": "Incidents",  "color": "#ffd27a"},
        {"id": "executions", "label": "Executions", "color": "#a3ffcb"},
    ]

    return JsonResponse({
        "events": events,
        "links": links,
        "lanes": lanes,
        "meta": {
            "hours": hours,
            "event_count": len(events),
            "service_filter": service_filter or None,
            "incident_key_filter": incident_key_filter or None,
            "generated_at": timezone.now().isoformat(),
        },
    })
