# genai/views.py
import os
import re
import json
import logging
import traceback
import time
import subprocess
import uuid
import hashlib
from datetime import timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from io import BytesIO
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, HttpRequest
from django.conf import settings
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.db import connection, models
from django.core.cache import cache
from django.utils import timezone

import pandas as pd

from .models import (
    ChatMessage,
    ChatSession,
    DiscoveredService,
    EnrollmentToken,
    GenAIChatHistory,
    Incident,
    IncidentAlert,
    IncidentTimelineEvent,
    ServicePrediction,
    Target,
    TargetComponent,
    TargetHeartbeat,
    TargetOnboardingRequest,
    TelemetryProfile,
)
from .predictions import score_components
from .sso import ensure_sso_user, get_sso_identity
from better_profanity import profanity
import os

# ---------------- logging ----------------
logger = logging.getLogger("genai")

def load_custom_profanity_words():
    """Reads a list of words from profanity_wordlist.txt and adds them to the better-profanity filter."""
    try:
        # Build the path relative to the current file
        wordlist_path = os.path.join(os.path.dirname(__file__), 'profanity_wordlist.txt')
        if os.path.exists(wordlist_path):
            with open(wordlist_path, 'r') as f:
                # Read words, filter out empty lines and comments
                custom_words = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                if custom_words:
                    profanity.add_censor_words(custom_words)
                    logger.info(f"Loaded {len(custom_words)} custom profanity words.")
    except Exception as e:
        logger.error(f"Failed to load custom profanity words: {e}")

# Load the words when the module is first imported
load_custom_profanity_words()
from .semantic_cache import simple_cache
from .telemetry_cache import (
    instant_cache_get_or_fetch,
    instant_cache_batch_get,
    instant_cache_batch_set,
    metadata_cache_get_or_fetch,
    get_cache_stats,
    get_http_session,
    purge_cache,
)

# ---------------- config ----------------
TARGET_TABLE = os.getenv("GENAI_TABLE", "")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL")
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL")
JAEGER_URL = os.getenv("JAEGER_URL")
AIDE_API_URL = os.getenv("AIDE_API_URL")
AIDE_API_KEY = os.getenv("AIDE_API_KEY")
AIDE_API_URL_SECONDARY = os.getenv("AIDE_API_URL_SECONDARY")
AIDE_API_KEY_SECONDARY = os.getenv("AIDE_API_KEY_SECONDARY")
AIDE_TIMEOUT = int(os.getenv("AIDE_TIMEOUT", "30"))
AIDE_RETRIES = int(os.getenv("AIDE_RETRIES", "3"))
AIDE_VERIFY_SSL = os.getenv("AIDE_VERIFY_SSL", "true").lower() not in ("false", "0", "no")
AIDE_DEBUG = os.getenv("AIDE_DEBUG", "false").lower() in ("true", "1", "yes")
VERIFY_PARAM = os.getenv("AIDE_CA_BUNDLE") or AIDE_VERIFY_SSL
AGENT_PORT = int(os.getenv("AGENT_PORT", "9999"))
DB_AGENT_HOST = os.getenv("DB_AGENT_HOST", "db-agent")
CONTROL_AGENT_HOST = os.getenv("CONTROL_AGENT_HOST", "control-agent")
DB_NAME = os.getenv("POSTGRES_DB", "aiops")
DB_USER = os.getenv("POSTGRES_USER", "user")
AIOPS_PUBLIC_BASE_URL = os.getenv("AIOPS_PUBLIC_BASE_URL", "").strip()
AIOPS_PUBLIC_OTLP_GRPC_ENDPOINT = os.getenv("AIOPS_PUBLIC_OTLP_GRPC_ENDPOINT", "").strip()
AIOPS_OTELCOL_VERSION = os.getenv("AIOPS_OTELCOL_VERSION", "0.87.0")
AIOPS_NODE_EXPORTER_VERSION = os.getenv("AIOPS_NODE_EXPORTER_VERSION", "1.8.1")
CHAT_HISTORY_WINDOW = int(os.getenv("CHAT_HISTORY_WINDOW", "12"))
RECENT_ALERT_CACHE_KEY = "aiops_recent_alert_recommendations"
RECENT_ALERT_CACHE_TTL = 60 * 60 * 24
MAX_RECENT_ALERTS = 20
APP_OVERVIEW_CACHE_KEY = "aiops_application_overview"
APP_OVERVIEW_CACHE_TTL = 60
IMPACT_WINDOW_DAYS = 7
IMPACT_BASELINE_TX_PER_DAY = int(os.getenv("AIOPS_BASELINE_TX_PER_DAY", "1000"))
IMPACT_DEFAULT_AOV = float(os.getenv("AIOPS_DEFAULT_AOV", "1499"))
APP_AVG_ORDER_VALUE = {
    "customer-portal": 1299.0,
    "payments-hub": 1899.0,
    "support-desk": 799.0,
    "analytics-studio": 1599.0,
}
APP_OVERVIEW_APPLICATIONS = [
    {
        "application": "customer-portal",
        "title": "Customer Portal",
        "description": "Customer-facing application composed of frontend, gateway, database, and three business microservices.",
        "mode": "live",
        "components": [
            {
                "service": "frontend",
                "title": "Frontend",
                "target_host": "frontend",
                "kind": "edge",
                "up_query": 'nginx_up{job="demo-frontend"}',
                "request_query": 'rate(nginx_http_requests_total{job="demo-frontend"}[5m])',
            },
            {
                "service": "gateway",
                "title": "Gateway",
                "target_host": "gateway",
                "kind": "gateway",
                "up_query": 'nginx_up{job="demo-gateway"}',
                "request_query": 'rate(nginx_http_requests_total{job="demo-gateway"}[5m])',
            },
            {
                "service": "db",
                "title": "Database",
                "target_host": "db",
                "kind": "database",
                "up_query": 'up{job="postgres-exporter"}',
                "request_query": 'sum(pg_stat_activity_count{datname="aiops",state="active"})',
            },
            {
                "service": "app-orders",
                "title": "Orders",
                "target_host": "app-orders",
                "kind": "microservice",
                "up_query": 'up{job="demo-apps",instance="app-orders:8000"}',
                "latency_query": 'histogram_quantile(0.95, sum(rate(demo_http_request_duration_seconds_bucket{service="app-orders"}[5m])) by (le))',
                "error_query": 'sum(rate(demo_http_requests_total{service="app-orders",status=~"5.."}[5m]))',
            },
            {
                "service": "app-inventory",
                "title": "Inventory",
                "target_host": "app-inventory",
                "kind": "microservice",
                "up_query": 'up{job="demo-apps",instance="app-inventory:8000"}',
                "latency_query": 'histogram_quantile(0.95, sum(rate(demo_http_request_duration_seconds_bucket{service="app-inventory"}[5m])) by (le))',
                "error_query": 'sum(rate(demo_http_requests_total{service="app-inventory",status=~"5.."}[5m]))',
            },
            {
                "service": "app-billing",
                "title": "Billing",
                "target_host": "app-billing",
                "kind": "microservice",
                "up_query": 'up{job="demo-apps",instance="app-billing:8000"}',
                "latency_query": 'histogram_quantile(0.95, sum(rate(demo_http_request_duration_seconds_bucket{service="app-billing"}[5m])) by (le))',
                "error_query": 'sum(rate(demo_http_requests_total{service="app-billing",status=~"5.."}[5m]))',
            },
        ],
    },
    {
        "application": "payments-hub",
        "title": "Payments Hub",
        "description": "Payment orchestration platform with settlement, ledger, and fraud services.",
        "mode": "demo",
        "status": "healthy",
        "ai_insight": "Payments Hub is stable. Settlement traffic is elevated but there are no active incidents and the service mesh looks balanced.",
        "components": [
            {"service": "payments-frontend", "title": "Frontend", "target_host": "payments-frontend", "kind": "edge", "status": "healthy", "metrics": {"up": 1, "request_rate": 18.4, "latency_p95_seconds": 0.42, "error_rate": 0}, "recent_alerts": [], "ai_insight": "The public payments UI is responsive and healthy."},
            {"service": "payments-gateway", "title": "Gateway", "target_host": "payments-gateway", "kind": "gateway", "status": "healthy", "metrics": {"up": 1, "request_rate": 22.7, "latency_p95_seconds": 0.36, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Gateway routing is healthy with no retry spikes."},
            {"service": "payments-db", "title": "Database", "target_host": "payments-db", "kind": "database", "status": "healthy", "metrics": {"up": 1, "request_rate": 14, "latency_p95_seconds": 0.12, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Database activity is normal and transaction pressure is within expected range."},
            {"service": "payments-ledger", "title": "Ledger", "target_host": "payments-ledger", "kind": "microservice", "status": "healthy", "metrics": {"up": 1, "request_rate": 9.7, "latency_p95_seconds": 0.51, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Ledger writes are healthy with no backlog indications."},
            {"service": "payments-settlement", "title": "Settlement", "target_host": "payments-settlement", "kind": "microservice", "status": "healthy", "metrics": {"up": 1, "request_rate": 6.2, "latency_p95_seconds": 0.73, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Settlement jobs are slightly busier than usual but remain within SLO."},
            {"service": "payments-fraud", "title": "Fraud", "target_host": "payments-fraud", "kind": "microservice", "status": "healthy", "metrics": {"up": 1, "request_rate": 4.8, "latency_p95_seconds": 0.65, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Fraud scoring latency is steady and there is no model service degradation."},
        ],
    },
    {
        "application": "support-desk",
        "title": "Support Desk",
        "description": "Internal support application for ticketing, notifications, and reporting.",
        "mode": "demo",
        "status": "degraded",
        "ai_insight": "Support Desk is degraded because the reporting service is slow and pushing higher response times into the gateway tier.",
        "components": [
            {"service": "support-frontend", "title": "Frontend", "target_host": "support-frontend", "kind": "edge", "status": "healthy", "metrics": {"up": 1, "request_rate": 12.1, "latency_p95_seconds": 0.58, "error_rate": 0}, "recent_alerts": [], "ai_insight": "The UI is currently healthy, but users may feel slower reports."},
            {"service": "support-gateway", "title": "Gateway", "target_host": "support-gateway", "kind": "gateway", "status": "degraded", "metrics": {"up": 1, "request_rate": 15.9, "latency_p95_seconds": 1.82, "error_rate": 0.03}, "recent_alerts": [{"alert_name": "SupportGatewayLatencyHigh", "status": "firing"}], "ai_insight": "Gateway latency is elevated because downstream report calls are slower than normal."},
            {"service": "support-db", "title": "Database", "target_host": "support-db", "kind": "database", "status": "healthy", "metrics": {"up": 1, "request_rate": 8.4, "latency_p95_seconds": 0.16, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Database health is normal, so the issue is likely above the storage layer."},
            {"service": "support-tickets", "title": "Tickets", "target_host": "support-tickets", "kind": "microservice", "status": "healthy", "metrics": {"up": 1, "request_rate": 7.4, "latency_p95_seconds": 0.49, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Ticket operations are stable."},
            {"service": "support-notify", "title": "Notifications", "target_host": "support-notify", "kind": "microservice", "status": "healthy", "metrics": {"up": 1, "request_rate": 3.7, "latency_p95_seconds": 0.44, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Notification delivery is healthy."},
            {"service": "support-reporting", "title": "Reporting", "target_host": "support-reporting", "kind": "microservice", "status": "degraded", "metrics": {"up": 1, "request_rate": 2.1, "latency_p95_seconds": 2.43, "error_rate": 0.08}, "recent_alerts": [{"alert_name": "SupportReportingLatencyHigh", "status": "firing"}], "ai_insight": "Reporting is the bottleneck and is driving the degraded application state."},
        ],
    },
    {
        "application": "analytics-studio",
        "title": "Analytics Studio",
        "description": "Data workspace for ingestion, processing, and dashboard APIs.",
        "mode": "demo",
        "status": "down",
        "ai_insight": "Analytics Studio is down because the processing engine is unavailable, which makes the application unsuitable for new report generation.",
        "components": [
            {"service": "analytics-frontend", "title": "Frontend", "target_host": "analytics-frontend", "kind": "edge", "status": "degraded", "metrics": {"up": 1, "request_rate": 5.2, "latency_p95_seconds": 1.94, "error_rate": 0.04}, "recent_alerts": [{"alert_name": "AnalyticsFrontendErrorsHigh", "status": "firing"}], "ai_insight": "Users can load the shell UI, but core report actions are failing."},
            {"service": "analytics-gateway", "title": "Gateway", "target_host": "analytics-gateway", "kind": "gateway", "status": "degraded", "metrics": {"up": 1, "request_rate": 7.8, "latency_p95_seconds": 1.63, "error_rate": 0.05}, "recent_alerts": [{"alert_name": "AnalyticsGatewayErrorsHigh", "status": "firing"}], "ai_insight": "Gateway errors are being driven by a failed downstream service."},
            {"service": "analytics-db", "title": "Database", "target_host": "analytics-db", "kind": "database", "status": "healthy", "metrics": {"up": 1, "request_rate": 4.3, "latency_p95_seconds": 0.21, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Storage remains healthy, so the outage is not database-led."},
            {"service": "analytics-ingestion", "title": "Ingestion", "target_host": "analytics-ingestion", "kind": "microservice", "status": "healthy", "metrics": {"up": 1, "request_rate": 2.9, "latency_p95_seconds": 0.87, "error_rate": 0}, "recent_alerts": [], "ai_insight": "Ingestion is healthy and not contributing to the incident."},
            {"service": "analytics-processing", "title": "Processing", "target_host": "analytics-processing", "kind": "microservice", "status": "down", "metrics": {"up": 0, "request_rate": 0, "latency_p95_seconds": None, "error_rate": 1}, "recent_alerts": [{"alert_name": "AnalyticsProcessingDown", "status": "firing"}], "ai_insight": "Processing is unavailable and is the primary cause of the application outage."},
            {"service": "analytics-api", "title": "Dashboard API", "target_host": "analytics-api", "kind": "microservice", "status": "degraded", "metrics": {"up": 1, "request_rate": 3.6, "latency_p95_seconds": 2.18, "error_rate": 0.14}, "recent_alerts": [{"alert_name": "AnalyticsApiLatencyHigh", "status": "firing"}], "ai_insight": "Dashboard API is degraded because it depends on the unavailable processing layer."},
        ],
    },
]
DEPENDENCY_GRAPH_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo", "dependencies", "application_graph.json")
_dependency_graph_cache: Tuple[Dict[str, Any], float] = ({}, 0.0)

FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE)\b", re.IGNORECASE)
SQL_STOP_TOKENS = ["\n\n", "\nSQL:", "```", ";"]
SCHEMA_CACHE_TTL = int(os.getenv("SCHEMA_CACHE_TTL", "300"))

# schema cache (text, expiry)
_schema_cache: Tuple[str, float] = ("", 0.0)


def _application_lookup() -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    for app in APP_OVERVIEW_APPLICATIONS:
        title = app.get("title") or app.get("application") or ""
        app_key = app.get("application") or ""
        for component in app.get("components", []):
            if not isinstance(component, dict):
                continue
            for key in (component.get("service"), component.get("target_host")):
                if key:
                    lookup[str(key)] = {"application": app_key, "title": title}
    return lookup


APP_LOOKUP = _application_lookup()


def _get_application_info(service_or_host: Optional[str]) -> Dict[str, str]:
    if not service_or_host:
        return {"application": "", "title": ""}
    return APP_LOOKUP.get(str(service_or_host), {"application": "", "title": ""})


def _serialize_chat_message(message: ChatMessage) -> Dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "metadata": message.metadata or {},
        "created_at": message.created_at.isoformat(),
    }


def _serialize_chat_session(session: ChatSession) -> Dict[str, Any]:
    latest_message = session.messages.order_by("-created_at").first()
    latest_preview = ""
    if latest_message:
        latest_preview = latest_message.content[:140]
    return {
        "session_id": str(session.session_id),
        "title": session.title or "Untitled conversation",
        "updated_at": session.updated_at.isoformat(),
        "created_at": session.created_at.isoformat(),
        "last_message_preview": latest_preview,
        "message_count": session.messages.count(),
    }


def _get_or_create_chat_session(request: HttpRequest, session_id: Optional[str] = None) -> ChatSession:
    candidate = (session_id or request.session.get("genai_chat_session_id") or "").strip()
    if candidate:
        session, created = ChatSession.objects.get_or_create(session_id=candidate)
    else:
        session = ChatSession.objects.create()
        created = True

    if request.user.is_authenticated and session.user_id != request.user.id:
        session.user = request.user
        session.save(update_fields=["user", "updated_at", "last_activity_at"])
    elif created:
        session.save(update_fields=["updated_at", "last_activity_at"])

    request.session["genai_chat_session_id"] = str(session.session_id)
    return session


def _chat_history_for_prompt(session: ChatSession, limit: int = CHAT_HISTORY_WINDOW) -> str:
    recent_messages = list(session.messages.order_by("-created_at")[:limit])
    if not recent_messages:
        return ""
    lines = []
    for message in reversed(recent_messages):
        role = "User" if message.role == "user" else "Assistant"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def _append_chat_message(session: ChatSession, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ChatMessage:
    text = (content or "").strip()
    message = ChatMessage.objects.create(
        session=session,
        role=role,
        content=text,
        metadata=metadata or {},
    )
    updates = ["updated_at", "last_activity_at"]
    if role == "user" and not session.title:
        session.title = text[:120]
        updates.append("title")
    session.save(update_fields=updates)
    return message


def _record_chat_reply(session: Optional[ChatSession], payload: Dict[str, Any]) -> None:
    if not session:
        return
    content = payload.get("answer") or payload.get("summary") or payload.get("error") or ""
    _append_chat_message(session, "assistant", str(content), payload)


def _recent_chat_sessions_for_request(request: HttpRequest, requested_ids: Optional[List[str]] = None) -> List[ChatSession]:
    queryset = ChatSession.objects.filter(is_active=True)
    if request.user.is_authenticated:
        queryset = queryset.filter(user=request.user)
    elif requested_ids:
        queryset = queryset.filter(session_id__in=requested_ids)
    else:
        current_id = request.session.get("genai_chat_session_id")
        if not current_id:
            return []
        queryset = queryset.filter(session_id=current_id)
    return list(queryset.order_by("-updated_at")[:20])


def _build_incident_title(application_title: str, alert_name: str, service_name: str) -> str:
    if service_name:
        return f"{application_title or 'Application'}: {service_name} incident"
    return f"{application_title or 'Application'}: {alert_name}"


def _incident_fingerprint(alert_payload: Dict[str, Any], target_host: str, service_name: str) -> str:
    labels = alert_payload.get("labels") if isinstance(alert_payload.get("labels"), dict) else {}
    fingerprint = labels.get("fingerprint") or alert_payload.get("group_key")
    if fingerprint:
        return str(fingerprint)
    alert_name = alert_payload.get("alert_name") or labels.get("alertname") or "unknown_alert"
    return f"{alert_name}:{service_name or target_host}"


def _correlate_alert_to_incident(alert_payload: Dict[str, Any], context: Dict[str, Any], summary: str, why: str) -> Incident:
    labels = alert_payload.get("labels") if isinstance(alert_payload.get("labels"), dict) else {}
    annotations = alert_payload.get("annotations") if isinstance(alert_payload.get("annotations"), dict) else {}
    alert_name = alert_payload.get("alert_name") or labels.get("alertname") or "unknown_alert"
    target_host = context.get("target_host") or _extract_target_host_from_payload(alert_payload) or ""
    service_name = context.get("service_name") or labels.get("service") or target_host
    application_info = _get_application_info(service_name or target_host)
    application = application_info.get("application", "")
    application_title = application_info.get("title") or (application or "Application")
    dependency_context = context.get("dependency_graph") or {}
    blast_radius = dependency_context.get("blast_radius") or []
    fingerprint = _incident_fingerprint(alert_payload, target_host, service_name)
    alert_status = str(alert_payload.get("status") or "firing").lower()

    incident = (
        Incident.objects.filter(status__in=["open", "investigating"], application=application)
        .filter(models.Q(primary_service=service_name) | models.Q(target_host=target_host) | models.Q(title__icontains=alert_name))
        .order_by("-updated_at")
        .first()
    )
    if incident is None:
        incident = Incident.objects.create(
            application=application,
            title=_build_incident_title(application_title, alert_name, service_name),
            status="resolved" if alert_status == "resolved" else "open",
            severity=(labels.get("severity") or labels.get("alert_severity") or "warning"),
            primary_service=service_name or "",
            target_host=target_host or "",
            summary=summary or "",
            reasoning=why or "",
            blast_radius=blast_radius,
            dependency_graph=dependency_context,
            labels=labels,
            annotations=annotations,
            resolved_at=timezone.now() if alert_status == "resolved" else None,
        )
        IncidentTimelineEvent.objects.create(
            incident=incident,
            event_type="incident_created",
            title=f"Incident created from {alert_name}",
            detail=summary or why or "",
            payload={"alert_payload": alert_payload, "context": context},
        )
    else:
        incident.status = "resolved" if alert_status == "resolved" else "investigating"
        incident.summary = summary or incident.summary
        incident.reasoning = why or incident.reasoning
        incident.primary_service = service_name or incident.primary_service
        incident.target_host = target_host or incident.target_host
        incident.blast_radius = blast_radius or incident.blast_radius
        incident.dependency_graph = dependency_context or incident.dependency_graph
        incident.labels = labels or incident.labels
        incident.annotations = annotations or incident.annotations
        incident.resolved_at = timezone.now() if alert_status == "resolved" else None
        incident.save()

    incident_alert, created = IncidentAlert.objects.update_or_create(
        incident=incident,
        alert_name=alert_name,
        alert_fingerprint=fingerprint,
        defaults={
            "status": alert_status,
            "target_host": target_host or "",
            "service_name": service_name or "",
            "labels": labels,
            "annotations": annotations,
            "raw_payload": alert_payload,
        },
    )

    IncidentTimelineEvent.objects.create(
        incident=incident,
        event_type="alert_correlated" if created else "alert_updated",
        title=f"{alert_name} {alert_status}",
        detail=summary or why or "",
        payload={
            "alert_name": alert_name,
            "status": alert_status,
            "target_host": target_host,
            "service_name": service_name,
            "blast_radius": blast_radius,
        },
    )

    if incident.status == "resolved":
        still_open = incident.alerts.exclude(id=incident_alert.id).exclude(status="resolved").exists()
        if still_open:
            incident.status = "investigating"
            incident.resolved_at = None
            incident.save(update_fields=["status", "resolved_at", "updated_at"])

    return incident


def _compute_incident_revenue_impact(incident: Incident) -> Optional[Dict[str, Any]]:
    """Estimate revenue impact for an incident based on failed orders during incident window."""
    application_key = (incident.application or "").strip()
    service_key = (incident.primary_service or "").strip()
    avg_order_value = float(APP_AVG_ORDER_VALUE.get(application_key, IMPACT_DEFAULT_AOV))

    ist_zone = ZoneInfo("Asia/Kolkata")
    opened_at = incident.opened_at
    resolved_at = incident.resolved_at or timezone.now()
    duration_seconds = max((resolved_at - opened_at).total_seconds(), 0)
    duration_hours = round(duration_seconds / 3600, 2)

    # Try DB-backed calculation for orders-related incidents
    normalized_service = service_key.lower()
    orders_related = normalized_service in {"app-orders", "orders", "app-billing", "billing", "app-inventory", "inventory"}

    if orders_related:
        start_utc = opened_at.astimezone(ZoneInfo("UTC"))
        end_utc = resolved_at.astimezone(ZoneInfo("UTC"))
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM demo_orders
                WHERE created_at >= %s AND created_at <= %s
                """,
                [start_utc, end_utc],
            )
            total_orders = cursor.fetchone()[0] or 0

            cursor.execute(
                """
                SELECT COUNT(DISTINCT o.order_ref)
                FROM demo_orders o
                LEFT JOIN demo_billing b
                  ON o.order_ref = b.order_ref AND b.status = 'authorized'
                WHERE o.created_at >= %s AND o.created_at <= %s
                  AND b.order_ref IS NULL
                """,
                [start_utc, end_utc],
            )
            failed_transactions = cursor.fetchone()[0] or 0

        revenue_lost = round(failed_transactions * avg_order_value, 2)
        revenue_per_hour = round(revenue_lost / duration_hours, 2) if duration_hours > 0 else revenue_lost
        data_source = "demo_orders+demo_billing"
    else:
        # Synthetic estimate for non-orders services
        baseline_per_hour = IMPACT_BASELINE_TX_PER_DAY / 24.0
        total_orders = round(baseline_per_hour * duration_hours)
        # Use a severity-based error rate estimate
        severity_error_map = {"critical": 0.25, "high": 0.15, "warning": 0.08, "low": 0.04}
        error_rate = severity_error_map.get((incident.severity or "").lower(), 0.10)
        failed_transactions = round(total_orders * error_rate)
        revenue_lost = round(failed_transactions * avg_order_value, 2)
        revenue_per_hour = round(revenue_lost / duration_hours, 2) if duration_hours > 0 else revenue_lost
        data_source = "estimated"

    impact_level = "none"
    if revenue_lost >= 250000:
        impact_level = "critical"
    elif revenue_lost >= 100000:
        impact_level = "high"
    elif revenue_lost >= 25000:
        impact_level = "medium"
    elif revenue_lost > 0:
        impact_level = "low"

    return {
        "currency": "INR",
        "avg_order_value": avg_order_value,
        "total_transactions": total_orders,
        "failed_transactions": failed_transactions,
        "revenue_lost": revenue_lost,
        "revenue_per_hour": revenue_per_hour,
        "duration_hours": duration_hours,
        "impact_level": impact_level,
        "data_source": data_source,
    }


def _incident_summary_payload(incident: Incident) -> Dict[str, Any]:
    alerts = list(incident.alerts.order_by("-last_seen_at")[:10])
    latest_prediction = ServicePrediction.objects.filter(
        application=incident.application,
        service=incident.primary_service,
    ).order_by("-created_at").first()
    return {
        "incident_key": str(incident.incident_key),
        "application": incident.application,
        "title": incident.title,
        "status": incident.status,
        "severity": incident.severity,
        "primary_service": incident.primary_service,
        "target_host": incident.target_host,
        "summary": incident.summary,
        "reasoning": incident.reasoning,
        "blast_radius": incident.blast_radius,
        "updated_at": incident.updated_at.isoformat(),
        "opened_at": incident.opened_at.isoformat(),
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "alerts": [
            {
                "alert_name": alert.alert_name,
                "status": alert.status,
                "target_host": alert.target_host,
                "service_name": alert.service_name,
                "last_seen_at": alert.last_seen_at.isoformat(),
            }
            for alert in alerts
        ],
        "timeline_count": incident.timeline.count(),
        "prediction": (
            {
                "risk_score": latest_prediction.risk_score,
                "incident_probability": latest_prediction.incident_probability,
                "predicted_window_minutes": latest_prediction.predicted_window_minutes,
                "explanation": latest_prediction.explanation,
            }
            if latest_prediction
            else None
        ),
        "business_impact": _compute_incident_revenue_impact(incident),
    }


def _incident_timeline_payload(incident: Incident) -> Dict[str, Any]:
    linked_recommendation = None
    recent_entries = cache.get(RECENT_ALERT_CACHE_KEY) or []
    if isinstance(recent_entries, list):
        for entry in recent_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("incident_key") or "") == str(incident.incident_key):
                linked_recommendation = entry
                break

    return {
        **_incident_summary_payload(incident),
        "linked_recommendation": linked_recommendation,
        "timeline": [
            {
                "event_type": item.event_type,
                "title": item.title,
                "detail": item.detail,
                "payload": item.payload,
                "created_at": item.created_at.isoformat(),
            }
            for item in incident.timeline.all()
        ],
    }


def _extract_investigation_scope(question: str, body: Dict[str, Any]) -> Dict[str, str]:
    text = " ".join(
        part for part in [
            question or "",
            str(body.get("application") or ""),
            str(body.get("service") or ""),
            str(body.get("incident") or ""),
        ]
        if part
    )
    scope = {"application": "", "service": "", "incident": ""}
    for key in ("application", "service", "incident"):
        match = re.search(rf"{key}=([A-Za-z0-9_\-:]+)", text, re.IGNORECASE)
        if match:
            scope[key] = match.group(1)
    return scope


def _find_investigation_incident(scope: Dict[str, str]) -> Optional[Incident]:
    incident_key = scope.get("incident") or ""
    if incident_key:
        incident = Incident.objects.filter(incident_key=incident_key).first()
        if incident:
            return incident

    service = scope.get("service") or ""
    if service:
        incident = Incident.objects.filter(primary_service=service).order_by("-updated_at").first()
        if incident:
            return incident

    application = scope.get("application") or ""
    if application:
        incident = Incident.objects.filter(application=application).order_by("-updated_at").first()
        if incident:
            return incident
    return None


def _find_component_snapshot(application_key: str, service: str) -> Optional[Dict[str, Any]]:
    overview = _build_application_overview(include_ai=True, include_predictions=True)
    for application in overview.get("results", []):
        if application.get("application") != application_key:
            continue
        for component in application.get("components", []):
            if component.get("service") == service or component.get("target_host") == service:
                return component
    return None


def build_investigation_context(question: str, body: Dict[str, Any]) -> Dict[str, Any]:
    scope = _extract_investigation_scope(question, body)
    incident = _find_investigation_incident(scope)
    linked_recommendation = None
    application_graph = None
    component_snapshot = None
    dependency_context: Dict[str, Any] = {}
    logs: Dict[str, Any] = {}
    traces: Dict[str, Any] = {}
    prometheus_context: Dict[str, Any] = {}

    application_key = scope.get("application") or ""
    service = scope.get("service") or ""

    if incident:
        timeline_payload = _incident_timeline_payload(incident)
        linked_recommendation = timeline_payload.get("linked_recommendation")
        dependency_context = incident.dependency_graph or _get_dependency_context(incident.primary_service or incident.target_host)
        application_key = application_key or incident.application or dependency_context.get("application") or ""
        service = service or incident.primary_service or incident.target_host or ""
    else:
        timeline_payload = None
        dependency_context = _get_dependency_context(service or "")

    if application_key:
        application_graph = _application_graph_payload(application_key)

    if application_key and service:
        component_snapshot = _find_component_snapshot(application_key, service)

    target_host = (
        (component_snapshot or {}).get("target_host")
        or (incident.target_host if incident else "")
        or service
        or scope.get("service")
        or ""
    )
    service_name = (
        (component_snapshot or {}).get("service")
        or (incident.primary_service if incident else "")
        or service
        or target_host
    )

    if target_host or service_name:
        logs = _fetch_elasticsearch_logs(target_host, question or service_name)
        traces = _fetch_jaeger_traces(service_name)
        prometheus_context = {
            "latency_p95_seconds": _fetch_prometheus_custom_query(
                f'histogram_quantile(0.95, sum by (le) (rate(flask_http_request_duration_seconds_bucket{{job="{service_name}"}}[5m])))'
            ) if service_name else {},
            "error_rate": _fetch_prometheus_custom_query(
                f'sum(rate(flask_http_request_total{{job="{service_name}",status=~"5.."}}[5m]))'
            ) if service_name else {},
        }

    return {
        "scope": scope,
        "incident": _incident_timeline_payload(incident) if incident else None,
        "linked_recommendation": linked_recommendation,
        "application_graph": application_graph,
        "component_snapshot": component_snapshot,
        "dependency_graph": dependency_context,
        "prometheus": prometheus_context,
        "elasticsearch": logs,
        "jaeger": traces,
        "target_host": target_host,
        "service_name": service_name,
        "application": application_key,
    }


def _chat_json_response(session: Optional[ChatSession], payload: Dict[str, Any], status: int = 200) -> JsonResponse:
    if session:
        enriched_payload = {**payload, "session_id": str(session.session_id)}
        _record_chat_reply(session, enriched_payload)
        return JsonResponse(enriched_payload, status=status)
    return JsonResponse(payload, status=status)

# --- VIP User Check ---
def get_vip_emails() -> set:
    """Reads VIP email addresses from vip_emails.txt and returns them as a lowercase set."""
    vip_file_path = os.path.join(os.path.dirname(__file__), 'vip_emails.txt')
    if not os.path.exists(vip_file_path):
        logger.warning(f"VIP emails file not found at: {vip_file_path}")
        return set()
    try:
        with open(vip_file_path, 'r') as f:
            # Read lines, strip whitespace, convert to lowercase, and ignore empty lines or comments
            vips = {line.strip().lower() for line in f if line.strip() and not line.startswith('#')}
            logger.info(f"Successfully loaded {len(vips)} VIP emails.")
            return vips
    except Exception as e:
        logger.error(f"Failed to read VIP emails file: {e}")
        return set()

def get_vip_users() -> set:
    """Reads VIP user IDs from vip_users.txt and returns them as a set."""
    vip_file_path = os.path.join(os.path.dirname(__file__), 'vip_users.txt')
    if not os.path.exists(vip_file_path):
        logger.warning(f"VIP users file not found at: {vip_file_path}")
        return set()
    try:
        with open(vip_file_path, 'r') as f:
            # Read lines, strip whitespace, and ignore empty lines or comments
            vips = {line.strip() for line in f if line.strip() and not line.startswith('#')}
            logger.info(f"Successfully loaded {len(vips)} VIP users: {vips}")
            return vips
    except Exception as e:
        logger.error(f"Failed to read VIP users file: {e}")
        return set()


# ---------------- utilities ----------------
def _to_bool(v, default=False):
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return default

def _safe_preview_value(val, max_len=80):
    try:
        if val is None:
            return "NULL"
        s = str(val).replace("\n", " ").replace("\r", " ").strip()
        return s if len(s) <= max_len else s[: max_len - 3] + "..."
    except Exception:
        return "<unprintable>"


def _load_dependency_graph() -> Dict[str, Any]:
    global _dependency_graph_cache
    cached_graph, cached_at = _dependency_graph_cache
    if cached_graph and (time.time() - cached_at) < 300:
        return cached_graph
    try:
        with open(DEPENDENCY_GRAPH_PATH, "r", encoding="utf-8") as handle:
            graph = json.load(handle)
    except Exception:
        logger.exception("Failed to load dependency graph from %s", DEPENDENCY_GRAPH_PATH)
        graph = {"applications": {}}
    _dependency_graph_cache = (graph, time.time())
    return graph


def _find_application_for_service(service: str) -> Optional[str]:
    graph = _load_dependency_graph().get("applications", {})
    for application, nodes in graph.items():
        if service in nodes:
            return application
    return None


def _get_dependency_context(service: Optional[str]) -> Dict[str, Any]:
    if not service:
        return {}
    graph = _load_dependency_graph().get("applications", {})
    application = _find_application_for_service(service)
    if not application:
        return {}
    nodes = graph.get(application, {})
    downstream = nodes.get(service, [])

    reverse = {}
    for node, deps in nodes.items():
        for dep in deps:
            reverse.setdefault(dep, []).append(node)

    direct_dependents = reverse.get(service, [])
    visited = set()
    queue = list(direct_dependents)
    blast_radius = []
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        blast_radius.append(current)
        queue.extend(reverse.get(current, []))

    dependency_chain = [service] + downstream[:]
    return {
        "application": application,
        "service": service,
        "depends_on": downstream,
        "direct_dependents": direct_dependents,
        "blast_radius": blast_radius,
        "dependency_chain": dependency_chain,
        "graph": nodes,
    }

def _serialize_value_for_json(val):
    if val is None:
        return None
    try:
        # datetimes
        import datetime as _dt
        if isinstance(val, _dt.datetime):
            return val.isoformat()
        if isinstance(val, (str, int, float, bool)):
            return val
        return str(val)
    except Exception:
        return str(val)


def _extract_target_host_from_instance(instance: str) -> str:
    if not instance:
        return ""
    return str(instance).split(":", 1)[0].strip()


RESTARTABLE_CONTAINER_NAMES = {
    "db": "aiops-db",
    "frontend": "aiops-frontend",
    "gateway": "aiops-gateway",
    "app-orders": "aiops-app-orders",
    "app-inventory": "aiops-app-inventory",
    "app-billing": "aiops-app-billing",
    "toxiproxy": "aiops-toxiproxy",
}


def _normalize_agent_target_host(target_host: str) -> str:
    host = (target_host or "").strip()
    if host == "db":
        return DB_AGENT_HOST
    if host in ("controller", "control", "control-agent"):
        return CONTROL_AGENT_HOST
    return host


def _normalize_agent_command(command_to_run: str, target_host: str) -> str:
    command = (command_to_run or "").strip()
    if not command:
        return command

    # The demo agent executes tokenized commands directly, so shell substitutions like
    # $(docker ps ...) will never work. Normalize common docker-log patterns into a
    # concrete container name based on the demo service naming convention.
    if command.startswith("docker logs") and target_host.startswith("app-"):
        tail_match = re.search(r"--tail\s+(\d+)", command)
        tail_value = tail_match.group(1) if tail_match else "200"
        return f"tail -n {tail_value} /var/log/demo/{target_host}.log"

    if target_host == "db":
        if command.startswith("pg_isready") or command.startswith("psql "):
            if command.startswith("pg_isready"):
                return "pg_isready -h db"
            sql_match = re.search(r'-c\s+"(.*)"$', command)
            sql = sql_match.group(1) if sql_match else (
                "select now() as observed_at, count(*) as total_sessions, "
                "count(*) filter (where state = 'active') as active_sessions, "
                "count(*) filter (where wait_event is not null) as waiting_sessions "
                "from pg_stat_activity;"
            )
            return f'psql -h db -U {DB_USER} -d {DB_NAME} -c "{sql}"'
        if command.startswith("docker logs") or command.startswith("tail ") or command.startswith("cat "):
            return (
                f'psql -h db -U {DB_USER} -d {DB_NAME} -c '
                '"select now() as observed_at, state, wait_event_type, wait_event, count(*) as sessions '
                "from pg_stat_activity group by 1,2,3,4 order by sessions desc;\""
            )
        return (
            f'psql -h db -U {DB_USER} -d {DB_NAME} -c '
            '"select now() as observed_at, count(*) as total_sessions, '
            "count(*) filter (where state = 'active') as active_sessions, "
            "count(*) filter (where wait_event is not null) as waiting_sessions "
            'from pg_stat_activity;"'
        )

    return command


def _lookup_recent_alert_recommendation(alert_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not alert_id:
        return None
    entries = cache.get(RECENT_ALERT_CACHE_KEY) or []
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("alert_id") == alert_id:
            return entry
    return None


def _shared_dependency_suspected(context: Dict[str, Any]) -> bool:
    haystack = json.dumps(context or {}, default=str).lower()
    dependency_graph = context.get("dependency_graph") if isinstance(context, dict) else {}
    blast_radius = (dependency_graph or {}).get("blast_radius") or []
    return any(token in haystack for token in ("toxiproxy", "psycopg2", "connection timed out", "timeout expired", "postgres", "database")) or len(blast_radius) > 1


def _default_diagnostic_for_target(target_host: str) -> str:
    if target_host == "db":
        return (
            f'psql -h db -U {DB_USER} -d {DB_NAME} -c '
            '"select now() as observed_at, count(*) as total_sessions, '
            "count(*) filter (where state = 'active') as active_sessions, "
            "count(*) filter (where wait_event is not null) as waiting_sessions "
            'from pg_stat_activity;"'
        )
    if target_host.startswith("app-"):
        return f"tail -n 200 /var/log/demo/{target_host}.log"
    if target_host == "gateway":
        return "tail -n 200 /var/log/nginx/error.log"
    return "ss -tulpn"


def _coerce_diagnostic_plan(
    alert_payload: Dict[str, Any],
    context: Dict[str, Any],
    ai_plan: Dict[str, Any],
    fallback_target_host: Optional[str],
) -> Dict[str, Any]:
    target_host = _extract_target_host_from_text(ai_plan.get("target_host")) or fallback_target_host or ""
    diagnostic_command = (ai_plan.get("diagnostic_command") or "").strip()
    summary = ai_plan.get("summary") or "Alert investigation prepared."
    why = ai_plan.get("why") or ""
    target_type = "service"

    service_name = context.get("service_name") or target_host
    dependency_graph = context.get("dependency_graph") or {}
    suspected_dependency = _shared_dependency_suspected(context)

    if suspected_dependency and (service_name or "").startswith("app-") and "db" in (dependency_graph.get("depends_on") or []):
        target_host = "db"
        target_type = "database"
        why = why or "Shared dependency indicators point to the database path, so the next diagnostic should pivot to the database agent."
        if not diagnostic_command or diagnostic_command.startswith("tail ") or "/var/log/demo/" in diagnostic_command:
            diagnostic_command = _default_diagnostic_for_target(target_host)

    if target_host == "db":
        target_type = "database"
        if not diagnostic_command:
            diagnostic_command = _default_diagnostic_for_target(target_host)
    elif target_host.startswith("app-"):
        target_type = "application_container"
        if not diagnostic_command:
            diagnostic_command = _default_diagnostic_for_target(target_host)
    elif target_host in ("gateway", "frontend"):
        target_type = "edge_proxy" if target_host == "gateway" else "edge_frontend"
        if not diagnostic_command:
            diagnostic_command = _default_diagnostic_for_target(target_host)
    else:
        if not diagnostic_command and target_host:
            diagnostic_command = _default_diagnostic_for_target(target_host)

    should_execute = _to_bool(
        ai_plan.get("should_execute"),
        default=bool(diagnostic_command and target_host),
    )

    return {
        "summary": summary,
        "why": why,
        "target_host": target_host,
        "target_type": target_type,
        "diagnostic_command": diagnostic_command,
        "should_execute": should_execute,
    }


def _format_analysis_sections(sections: Dict[str, Any]) -> str:
    ordered_keys = [
        ("root_cause", "Root Cause"),
        ("evidence", "Evidence"),
        ("impact", "Impact"),
        ("resolution", "Resolution"),
        ("remediation_steps", "Remediation"),
        ("validation_steps", "Validation"),
    ]
    parts = []
    for key, label in ordered_keys:
        value = sections.get(key)
        if not value:
            continue
        if isinstance(value, list):
            rendered = "\n".join(f"- {item}" for item in value if item)
        else:
            rendered = str(value)
        parts.append(f"{label}: {rendered}")
    return "\n\n".join(parts).strip()


def _summarize_execution_type(execution_type: str) -> str:
    return "remediation" if execution_type == "remediation" else "diagnostic"


def _coerce_remediation_command(analysis_sections: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(analysis_sections, dict):
        return {}

    context_blob = json.dumps(context or {}, default=str).lower()
    linked_recommendation = (context or {}).get("linked_recommendation") if isinstance(context, dict) else {}
    dependency_graph = (context or {}).get("dependency_graph") if isinstance(context, dict) else {}
    service_name = (
        ((linked_recommendation or {}).get("target_host"))
        or ((linked_recommendation or {}).get("labels") or {}).get("service")
        or (context or {}).get("service_name")
        or (dependency_graph or {}).get("service")
        or ""
    )
    depends_on = (dependency_graph or {}).get("depends_on") or []

    candidate_service = service_name
    if "toxiproxy" in context_blob or "connection to server at \"toxiproxy\"" in context_blob:
        candidate_service = "toxiproxy"
    elif service_name in ("app-orders", "app-inventory", "app-billing", "gateway", "frontend"):
        candidate_service = service_name
    elif "db" in depends_on or "postgres" in context_blob or "database" in context_blob:
        candidate_service = "db"

    container_name = RESTARTABLE_CONTAINER_NAMES.get(candidate_service)
    if not container_name:
        analysis_sections["remediation_command"] = ""
        analysis_sections["remediation_target_host"] = ""
        analysis_sections["remediation_why"] = analysis_sections.get("remediation_why") or ""
        analysis_sections["remediation_requires_approval"] = False
        return analysis_sections

    analysis_sections["remediation_command"] = f"docker restart {container_name}"
    analysis_sections["remediation_target_host"] = "control-agent"
    analysis_sections["remediation_why"] = (
        analysis_sections.get("remediation_why")
        or f"Restart the {candidate_service} container through the control agent to attempt recovery of the affected service path."
    )
    analysis_sections["remediation_service"] = candidate_service
    analysis_sections["remediation_requires_approval"] = True
    return analysis_sections


def _normalize_alertmanager_payload(body: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    alerts = body.get("alerts")
    if not isinstance(alerts, list) or not alerts:
        return body, False

    firing_alert = None
    for candidate in alerts:
        if isinstance(candidate, dict) and candidate.get("status") == "firing":
            firing_alert = candidate
            break
    if not firing_alert:
        firing_alert = alerts[0] if isinstance(alerts[0], dict) else {}

    labels = {}
    labels.update(body.get("commonLabels") or {})
    labels.update(firing_alert.get("labels") or {})

    annotations = {}
    annotations.update(body.get("commonAnnotations") or {})
    annotations.update(firing_alert.get("annotations") or {})

    alert_payload = {
        "alert_name": labels.get("alertname") or firing_alert.get("alertname") or body.get("groupKey") or "AlertmanagerAlert",
        "status": firing_alert.get("status") or body.get("status") or "firing",
        "target_host": _extract_target_host_from_instance(labels.get("instance") or ""),
        "labels": labels,
        "annotations": annotations,
        "starts_at": firing_alert.get("startsAt"),
        "ends_at": firing_alert.get("endsAt"),
        "generator_url": firing_alert.get("generatorURL") or body.get("externalURL"),
        "receiver": body.get("receiver"),
        "group_key": body.get("groupKey"),
        "alertmanager_envelope": {
            "receiver": body.get("receiver"),
            "status": body.get("status"),
            "externalURL": body.get("externalURL"),
            "groupLabels": body.get("groupLabels") or {},
            "commonLabels": body.get("commonLabels") or {},
            "commonAnnotations": body.get("commonAnnotations") or {},
            "truncatedAlerts": body.get("truncatedAlerts"),
            "alert_count": len(alerts),
        },
    }
    return alert_payload, True


def _store_recent_alert_recommendation(entry: Dict[str, Any]) -> None:
    try:
        existing = cache.get(RECENT_ALERT_CACHE_KEY) or []
        if not isinstance(existing, list):
            existing = []
        updated_entries = []
        matched = False
        for current in existing:
            if not isinstance(current, dict):
                updated_entries.append(current)
                continue

            same_identity = (
                current.get("alert_name") == entry.get("alert_name")
                and current.get("target_host") == entry.get("target_host")
                and current.get("from_alertmanager") == entry.get("from_alertmanager")
            )
            if same_identity and not matched:
                merged = {
                    **current,
                    **entry,
                    "alert_id": current.get("alert_id") or entry.get("alert_id"),
                    "last_execution_at": entry.get("last_execution_at") or current.get("last_execution_at"),
                    "execution_status": entry.get("execution_status") or current.get("execution_status"),
                    "agent_success": entry.get("agent_success", current.get("agent_success")),
                    "analysis_ok": entry.get("analysis_ok", current.get("analysis_ok")),
                    "final_answer": entry.get("final_answer") or current.get("final_answer"),
                    "post_command_ai_analysis": entry.get("post_command_ai_analysis") or current.get("post_command_ai_analysis"),
                    "command_output": entry.get("command_output") or current.get("command_output"),
                    "agent_response": entry.get("agent_response") or current.get("agent_response"),
                }
                updated_entries.append(merged)
                matched = True
            else:
                updated_entries.append(current)

        if not matched:
            updated_entries.insert(0, entry)

        cache.set(RECENT_ALERT_CACHE_KEY, updated_entries[:MAX_RECENT_ALERTS], RECENT_ALERT_CACHE_TTL)
    except Exception:
        logger.exception("Failed to persist recent alert recommendation.")


def _update_recent_alert_recommendation(alert_id: str, updates: Dict[str, Any]) -> None:
    try:
        existing = cache.get(RECENT_ALERT_CACHE_KEY) or []
        if not isinstance(existing, list):
            return
        updated = []
        for entry in existing:
            if isinstance(entry, dict) and entry.get("alert_id") == alert_id:
                entry = {**entry, **updates}
            updated.append(entry)
        cache.set(RECENT_ALERT_CACHE_KEY, updated[:MAX_RECENT_ALERTS], RECENT_ALERT_CACHE_TTL)
    except Exception:
        logger.exception("Failed to update recent alert recommendation for alert_id=%s", alert_id)


def _remove_recent_alert_recommendation_by_identity(alert_name: str, target_host: Optional[str], from_alertmanager: bool) -> int:
    """Remove cached recent alert entries matching the provided identity.

    Returns the number of removed entries.
    """
    try:
        existing = cache.get(RECENT_ALERT_CACHE_KEY) or []
        if not isinstance(existing, list):
            return 0
        # First try strict identity match (alert_name + target_host + from_alertmanager)
        kept = []
        removed = 0
        for entry in existing:
            if not isinstance(entry, dict):
                kept.append(entry)
                continue

            if (
                entry.get("alert_name") == alert_name
                and entry.get("target_host") == target_host
                and entry.get("from_alertmanager") == from_alertmanager
            ):
                removed += 1
                continue
            kept.append(entry)

        if removed:
            cache.set(RECENT_ALERT_CACHE_KEY, kept[:MAX_RECENT_ALERTS], RECENT_ALERT_CACHE_TTL)
            logger.info("Removed %d cached alert(s) by strict identity for %s", removed, alert_name)
            return removed

        # Fallback: be more permissive and remove by alert_name only (covers payloads
        # that don't include Alertmanager envelope or instance labels). This helps
        # avoid stale UI entries while still being conservative.
        kept2 = []
        removed2 = 0
        for entry in existing:
            if not isinstance(entry, dict):
                kept2.append(entry)
                continue
            if entry.get("alert_name") == alert_name:
                removed2 += 1
                continue
            kept2.append(entry)

        if removed2:
            cache.set(RECENT_ALERT_CACHE_KEY, kept2[:MAX_RECENT_ALERTS], RECENT_ALERT_CACHE_TTL)
            logger.info("Removed %d cached alert(s) by alert_name fallback for %s", removed2, alert_name)
        return removed2
    except Exception:
        logger.exception("Failed to remove recent alert recommendation for %s@%s", alert_name, target_host)
        return 0

def _rows_to_json_safe_lists(rows: List[Tuple]) -> List[List]:
    out = []
    for r in rows:
        out.append([_serialize_value_for_json(v) for v in r])
    return out

def _extract_target_host_from_text(value: str) -> Optional[str]:
    if not value:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    if ":" in candidate and candidate.count(":") == 1:
        host_part, port_part = candidate.rsplit(":", 1)
        if port_part.isdigit():
            candidate = host_part
    return candidate or None

def _extract_target_host_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    for key in ("target_host", "host", "hostname", "instance", "server", "node"):
        value = payload.get(key)
        host = _extract_target_host_from_text(value)
        if host:
            return host

    for container_key in ("labels", "annotations", "commonLabels", "commonAnnotations"):
        container = payload.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ("target_host", "host", "hostname", "instance", "server", "node"):
            host = _extract_target_host_from_text(container.get(key))
            if host:
                return host
    return None

def _fetch_prometheus_alert(alert_name: str, target_host: Optional[str]) -> Dict[str, Any]:
    if not PROMETHEUS_URL or not alert_name:
        return {}
    selectors = [f'alertname="{alert_name}"']
    if target_host:
        selectors.append(f'instance=~"{target_host}(:.*)?"')
    query = f'ALERTS{{{",".join(selectors)}}}'
    cache_id = f"alert:{query}"

    def _do_fetch():
        session = get_http_session("victoriametrics")
        response = session.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=(3, 10),
        )
        response.raise_for_status()
        return response.json().get("data", {})

    return metadata_cache_get_or_fetch("prom_alert", cache_id, _do_fetch, ttl=30, backend="victoriametrics")

def _fetch_prometheus_custom_query(query: str) -> Dict[str, Any]:
    if not PROMETHEUS_URL or not query:
        return {}

    def _do_fetch(q: str) -> Dict[str, Any]:
        session = get_http_session("victoriametrics")
        response = session.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": q},
            timeout=(3, 10),
        )
        response.raise_for_status()
        return response.json().get("data", {})

    return instant_cache_get_or_fetch(query, _do_fetch, backend="victoriametrics")

def _fetch_elasticsearch_logs(target_host: Optional[str], query_text: str) -> Dict[str, Any]:
    if not ELASTICSEARCH_URL:
        return {}
    should = []
    if target_host:
        should.extend([
            {"term": {"host.name.keyword": target_host}},
            {"term": {"host.hostname.keyword": target_host}},
            {"term": {"agent.hostname.keyword": target_host}},
        ])
    if query_text:
        should.append({"match": {"message": query_text}})
    if not should:
        return {}
    cache_id = f"es:{target_host or ''}:{query_text or ''}"

    def _do_fetch():
        session = get_http_session("elasticsearch")
        body = {
            "size": 5,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "should": should,
                    "minimum_should_match": 1,
                }
            },
            "_source": ["@timestamp", "message", "host.name", "host.hostname", "agent.hostname", "log.level"],
        }
        response = session.post(
            f"{ELASTICSEARCH_URL.rstrip('/')}/_search",
            json=body,
            timeout=(3, 10),
            verify=VERIFY_PARAM,
        )
        response.raise_for_status()
        return response.json()

    return metadata_cache_get_or_fetch("es_logs", cache_id, _do_fetch, ttl=60, backend="elasticsearch")

def _fetch_jaeger_traces(service_name: Optional[str]) -> Dict[str, Any]:
    if not JAEGER_URL or not service_name:
        return {}
    cache_id = f"jaeger:{service_name}"

    def _do_fetch():
        session = get_http_session("jaeger")
        response = session.get(
            f"{JAEGER_URL.rstrip('/')}/api/traces",
            params={"service": service_name, "limit": 5, "lookback": "1h"},
            timeout=(3, 10),
        )
        response.raise_for_status()
        return response.json()

    return metadata_cache_get_or_fetch("jaeger", cache_id, _do_fetch, ttl=120, backend="jaeger")

def collect_alert_context(alert_payload: Dict[str, Any]) -> Dict[str, Any]:
    labels = alert_payload.get("labels") if isinstance(alert_payload.get("labels"), dict) else {}
    annotations = alert_payload.get("annotations") if isinstance(alert_payload.get("annotations"), dict) else {}
    alert_name = (
        alert_payload.get("alert_name")
        or labels.get("alertname")
        or alert_payload.get("name")
        or "unknown_alert"
    )
    target_host = _extract_target_host_from_payload(alert_payload)
    query_text = (
        alert_payload.get("log_query")
        or annotations.get("summary")
        or annotations.get("description")
        or alert_name
    )
    service_name = (
        alert_payload.get("service_name")
        or labels.get("service_name")
        or labels.get("service")
        or labels.get("job")
    )
    prometheus_query = alert_payload.get("prometheus_query")
    dependency_context = _get_dependency_context(service_name or target_host)

    return {
        "alert_name": alert_name,
        "target_host": target_host,
        "service_name": service_name,
        "dependency_graph": dependency_context,
        "prometheus": {
            "alert_state": _fetch_prometheus_alert(alert_name, target_host),
            "custom_query": _fetch_prometheus_custom_query(prometheus_query) if prometheus_query else {},
        },
        "elasticsearch": _fetch_elasticsearch_logs(target_host, query_text),
        "jaeger": _fetch_jaeger_traces(service_name),
    }

def delegate_command_to_agent(command_to_run: str, target_host: str) -> Tuple[bool, str, Dict[str, Any]]:
    requested_target_host = target_host
    command_to_run = _normalize_agent_command(command_to_run, requested_target_host)
    target_host = _normalize_agent_target_host(requested_target_host)
    agent_url = f"http://{target_host}:{AGENT_PORT}/execute"
    headers = {
        "Authorization": f"Bearer {AGENT_SECRET_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"command": command_to_run}
    try:
        logger.info("Delegating command '%s' to agent at %s", command_to_run, agent_url)
        response = requests.post(agent_url, headers=headers, json=payload, timeout=70)
        if not response.ok:
            # Capture the response body to surface the real error from the agent
            try:
                agent_err = response.json()
            except Exception:
                agent_err = {"raw": response.text[:500]}
            logger.error(
                "Agent at %s returned HTTP %s for command '%s': %s",
                agent_url, response.status_code, command_to_run, agent_err
            )
            detail = agent_err.get("detail") or agent_err.get("error") or agent_err.get("raw") or str(agent_err)
            output = (
                f"Error: Agent on {requested_target_host} returned {response.status_code}. "
                f"Detail: {detail}"
            )
            return False, output, agent_err
        agent_response = response.json()
        agent_response["requested_target_host"] = requested_target_host
        agent_response["agent_target_host"] = target_host
        output = agent_response.get("output", "No output received from agent.")
        return True, output, agent_response
    except requests.RequestException as exc:
        logger.exception("Failed to communicate with agent at %s", agent_url)
        output = f"Error: Could not communicate with the agent on {requested_target_host}. Details: {exc}"
        return False, output, {"error": str(exc)}

def analyze_command_output(
    original_question: str,
    target_host: str,
    command_to_run: str,
    command_output: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    analysis_prompt = (
        "You are an IT infrastructure expert. A diagnostic command was run on a remote server. "
        "Analyze the output and provide JSON only with keys: answer, root_cause, evidence, impact, resolution, remediation_steps, validation_steps, remediation_command, remediation_target_host, remediation_why, remediation_requires_approval. "
        "remediation_steps and validation_steps must be arrays of concise action items. "
        "If a concrete remediation command is justified, remediation_command must be a single executable command suitable for the target troubleshooting agent. "
        "If no safe remediation command should be proposed yet, return an empty remediation_command string. "
        "remediation_requires_approval should be true whenever a remediation_command is returned. "
        "Do not ask the operator to inspect logs manually. If the command output contains logs, extract the likely error, impact, and concrete next action directly.\n\n"
        f"Original Question: '{original_question}'\n"
        f"Target Server: {target_host}\n"
        f"Command Run: `{command_to_run}`\n"
        f"Context: {json.dumps(context or {}, indent=2)[:4000]}\n"
        f"Command Output:\n---\n{command_output}\n---\n"
    )
    ok, status, body_text = query_aide_api(analysis_prompt)
    if not ok:
        return False, "AI service failed to analyze the command output.", {}
    try:
        start_index = body_text.find('{')
        end_index = body_text.rfind('}')
        if start_index != -1 and end_index != -1:
            response_data = json.loads(body_text[start_index:end_index + 1])
        else:
            response_data = {"answer": body_text}
        if isinstance(response_data, dict):
            remediation_target_host = _extract_target_host_from_text(response_data.get("remediation_target_host")) or target_host
            remediation_command = (response_data.get("remediation_command") or "").strip()
            response_data["remediation_target_host"] = remediation_target_host if remediation_command else ""
            response_data["remediation_command"] = remediation_command
            response_data["remediation_requires_approval"] = _to_bool(
                response_data.get("remediation_requires_approval"),
                default=bool(remediation_command),
            )
            response_data = _coerce_remediation_command(response_data, context)
        answer = response_data.get("answer") or _format_analysis_sections(response_data) or body_text
        return True, answer, response_data if isinstance(response_data, dict) else {}
    except json.JSONDecodeError:
        return True, body_text, {}


def _extract_first_sample_value(query_result: Dict[str, Any]) -> Optional[float]:
    if not isinstance(query_result, dict):
        return None
    result = query_result.get("result")
    if not isinstance(result, list) or not result:
        return None
    sample = result[0]
    value = sample.get("value") if isinstance(sample, dict) else None
    if not isinstance(value, list) or len(value) < 2:
        return None
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return None


def _recent_alerts_for_service(service: str, target_host: str) -> List[Dict[str, Any]]:
    entries = cache.get(RECENT_ALERT_CACHE_KEY) or []
    if not isinstance(entries, list):
        return []
    matched = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        labels = entry.get("labels") if isinstance(entry.get("labels"), dict) else {}
        entry_service = labels.get("service") or entry.get("target_host")
        if entry_service == service or entry.get("target_host") == target_host:
            matched.append({
                "alert_name": entry.get("alert_name"),
                "status": entry.get("status"),
                "summary": entry.get("summary") or entry.get("initial_ai_diagnosis"),
                "created_at": entry.get("created_at"),
            })
    return matched[:3]


def _derive_overview_status(component: Dict[str, Any], metrics: Dict[str, Optional[float]], alerts: List[Dict[str, Any]]) -> str:
    if metrics.get("up") == 0:
        return "down"
    if any(alert.get("status") == "firing" for alert in alerts):
        return "degraded"
    if component["kind"] == "app":
        if (metrics.get("latency_p95_seconds") or 0) > 2 or (metrics.get("error_rate") or 0) > 0.1:
            return "degraded"
    return "healthy"


def _fallback_overview_insight(component: Dict[str, Any], metrics: Dict[str, Optional[float]], status: str, alerts: List[Dict[str, Any]]) -> str:
    if status == "down":
        return f"{component['title']} is not reachable from Prometheus. Investigate container availability and the upstream dependency path."
    if status == "degraded":
        active_alert = next((alert for alert in alerts if alert.get("status") == "firing"), None)
        if active_alert and active_alert.get("summary"):
            return active_alert["summary"]
        if component["kind"] == "app" and (metrics.get("latency_p95_seconds") or 0) > 2:
            return f"{component['title']} is serving elevated latency and should be checked for slow downstream dependencies."
        return f"{component['title']} is degraded based on current telemetry and needs investigation."
    return f"{component['title']} is healthy. No active alert is firing and the latest telemetry snapshot looks normal."


def _stable_noise(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def _estimate_error_rate_for_day(status: str, current_error_rate: float, service_key: str, day_offset: int) -> float:
    if status == "down":
        return 1.0
    if day_offset == 0:
        return max(0.0, min(1.0, current_error_rate))

    if current_error_rate > 0:
        baseline = current_error_rate
    elif status == "degraded":
        baseline = 0.035
    else:
        baseline = 0.0

    jitter = (_stable_noise(f"{service_key}:error:{day_offset}") - 0.5) * 0.02
    value = baseline + jitter
    return max(0.0, min(0.35, value))


def _hour_weight(hour: int) -> float:
    if 9 <= hour < 18:
        return 2.8
    if 7 <= hour < 9 or 18 <= hour < 21:
        return 1.35
    return 0.55


def _distribute_transactions_with_business_peak(total_transactions: int, service_key: str, day_offset: int) -> List[int]:
    weighted: List[float] = []
    for hour in range(24):
        base = _hour_weight(hour)
        jitter = 0.9 + (_stable_noise(f"{service_key}:hourly:{day_offset}:{hour}") * 0.2)
        weighted.append(base * jitter)

    total_weight = sum(weighted) or 1.0
    raw = [(w / total_weight) * total_transactions for w in weighted]
    distributed = [int(value) for value in raw]
    remainder = total_transactions - sum(distributed)

    if remainder > 0:
        remainders = sorted(
            ((index, raw[index] - distributed[index]) for index in range(24)),
            key=lambda item: item[1],
            reverse=True,
        )
        for index, _ in remainders[:remainder]:
            distributed[index] += 1
    return distributed


def _build_orders_business_impact_from_db(
    application_key: str,
    service_key: str,
    metrics: Dict[str, Optional[float]],
) -> Optional[Dict[str, Any]]:
    normalized = service_key.lower()
    if normalized not in {"app-orders", "orders"}:
        return None

    ist_zone = ZoneInfo("Asia/Kolkata")
    ist_now = timezone.localtime(timezone.now(), ist_zone)
    start_date = ist_now.date() - timedelta(days=IMPACT_WINDOW_DAYS - 1)
    start_dt_ist = timezone.datetime.combine(start_date, timezone.datetime.min.time(), tzinfo=ist_zone)
    start_dt_utc = start_dt_ist.astimezone(ZoneInfo("UTC"))

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT order_ref, created_at
            FROM demo_orders
            WHERE created_at >= %s
            ORDER BY created_at ASC
            """,
            [start_dt_utc],
        )
        order_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT DISTINCT order_ref
            FROM demo_billing
            WHERE created_at >= %s
              AND status = 'authorized'
            """,
            [start_dt_utc],
        )
        authorized_order_refs = {str(row[0]) for row in cursor.fetchall()}

    if not order_rows:
        return None

    daily_map: Dict[str, Dict[str, Any]] = {}
    for offset in range(IMPACT_WINDOW_DAYS):
        date_value = (start_date + timedelta(days=offset)).isoformat()
        daily_map[date_value] = {
            "date": date_value,
            "transactions": 0,
            "failed_transactions": 0,
            "business_hours_window": "09:00-18:00 IST",
            "business_hours_transactions": 0,
            "business_hours_failed_transactions": 0,
            "off_hours_transactions": 0,
        }

    for order_ref, created_at in order_rows:
        if not created_at:
            continue
        localized = timezone.localtime(created_at, ist_zone)
        day_key = localized.date().isoformat()
        if day_key not in daily_map:
            continue

        bucket = daily_map[day_key]
        bucket["transactions"] += 1
        in_business_hours = 9 <= localized.hour < 18
        if in_business_hours:
            bucket["business_hours_transactions"] += 1
        else:
            bucket["off_hours_transactions"] += 1

        if str(order_ref) not in authorized_order_refs:
            bucket["failed_transactions"] += 1
            if in_business_hours:
                bucket["business_hours_failed_transactions"] += 1

    avg_order_value = float(APP_AVG_ORDER_VALUE.get(application_key, IMPACT_DEFAULT_AOV))
    daily_series: List[Dict[str, Any]] = []
    for offset in range(IMPACT_WINDOW_DAYS):
        day_key = (start_date + timedelta(days=offset)).isoformat()
        bucket = daily_map[day_key]
        tx = int(bucket["transactions"])
        failed = int(bucket["failed_transactions"])
        error_rate = (failed / tx) if tx else float(metrics.get("error_rate") or 0.0)
        revenue_lost = round(failed * avg_order_value, 2)
        daily_series.append({
            "date": day_key,
            "transactions": tx,
            "error_rate": round(error_rate, 4),
            "failed_transactions": failed,
            "estimated_revenue_lost": revenue_lost,
            "business_hours_window": "09:00-18:00 IST",
            "business_hours_transactions": int(bucket["business_hours_transactions"]),
            "business_hours_failed_transactions": int(bucket["business_hours_failed_transactions"]),
            "off_hours_transactions": int(bucket["off_hours_transactions"]),
        })

    today = daily_series[-1]
    trailing_revenue = round(sum(item["estimated_revenue_lost"] for item in daily_series), 2)
    trailing_failed = sum(item["failed_transactions"] for item in daily_series)

    impact_level = "none"
    if today["estimated_revenue_lost"] >= 250000:
        impact_level = "high"
    elif today["estimated_revenue_lost"] >= 50000:
        impact_level = "medium"
    elif today["estimated_revenue_lost"] > 0:
        impact_level = "low"

    return {
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "business_peak_window": "09:00-18:00 IST",
        "avg_order_value": round(avg_order_value, 2),
        "baseline_transactions_per_day": IMPACT_BASELINE_TX_PER_DAY,
        "window_days": IMPACT_WINDOW_DAYS,
        "daily": daily_series,
        "current_day": today,
        "trailing_7d_failed_transactions": trailing_failed,
        "trailing_7d_revenue_lost": trailing_revenue,
        "impact_level": impact_level,
        "data_source": "demo_orders+demo_billing",
    }


def _build_component_business_impact(
    application_key: str,
    service_key: str,
    status: str,
    metrics: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    db_derived_impact = _build_orders_business_impact_from_db(application_key, service_key, metrics)
    if db_derived_impact:
        return db_derived_impact

    ist_now = timezone.localtime(timezone.now(), ZoneInfo("Asia/Kolkata"))
    now = ist_now.date()
    avg_order_value = float(APP_AVG_ORDER_VALUE.get(application_key, IMPACT_DEFAULT_AOV))
    base_tx = max(100, IMPACT_BASELINE_TX_PER_DAY)
    current_error_rate = float(metrics.get("error_rate") or 0.0)

    daily_series: List[Dict[str, Any]] = []
    for day_offset in range(IMPACT_WINDOW_DAYS - 1, -1, -1):
        day = now - timedelta(days=day_offset)
        tx_jitter = (_stable_noise(f"{service_key}:tx:{day_offset}") - 0.5) * 0.16
        transactions = max(50, int(round(base_tx * (1 + tx_jitter))))
        error_rate = _estimate_error_rate_for_day(status, current_error_rate, service_key, day_offset)

        hourly_transactions = _distribute_transactions_with_business_peak(transactions, service_key, day_offset)
        hourly_failed: List[int] = []
        for hour, hour_transactions in enumerate(hourly_transactions):
            hour_error_jitter = (_stable_noise(f"{service_key}:err-hourly:{day_offset}:{hour}") - 0.5) * 0.008
            hour_error_rate = max(0.0, min(1.0, error_rate + hour_error_jitter))
            hourly_failed.append(int(round(hour_transactions * hour_error_rate)))

        failed = sum(hourly_failed)
        revenue_lost = round(failed * avg_order_value, 2)
        business_hours_transactions = sum(hourly_transactions[9:18])
        business_hours_failed = sum(hourly_failed[9:18])
        off_hours_transactions = transactions - business_hours_transactions

        daily_series.append({
            "date": day.isoformat(),
            "transactions": transactions,
            "error_rate": round(error_rate, 4),
            "failed_transactions": failed,
            "estimated_revenue_lost": revenue_lost,
            "business_hours_window": "09:00-18:00 IST",
            "business_hours_transactions": business_hours_transactions,
            "business_hours_failed_transactions": business_hours_failed,
            "off_hours_transactions": off_hours_transactions,
        })

    today = daily_series[-1] if daily_series else {
        "date": now.isoformat(),
        "transactions": base_tx,
        "error_rate": current_error_rate,
        "failed_transactions": 0,
        "estimated_revenue_lost": 0.0,
        "business_hours_window": "09:00-18:00 IST",
        "business_hours_transactions": int(base_tx * 0.7),
        "business_hours_failed_transactions": 0,
        "off_hours_transactions": int(base_tx * 0.3),
    }
    trailing_revenue = round(sum(item["estimated_revenue_lost"] for item in daily_series), 2)
    trailing_failed = sum(item["failed_transactions"] for item in daily_series)

    impact_level = "none"
    if today["estimated_revenue_lost"] >= 2500:
        impact_level = "high"
    elif today["estimated_revenue_lost"] >= 500:
        impact_level = "medium"
    elif today["estimated_revenue_lost"] > 0:
        impact_level = "low"

    return {
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "business_peak_window": "09:00-18:00 IST",
        "avg_order_value": round(avg_order_value, 2),
        "baseline_transactions_per_day": base_tx,
        "window_days": IMPACT_WINDOW_DAYS,
        "daily": daily_series,
        "current_day": today,
        "trailing_7d_failed_transactions": trailing_failed,
        "trailing_7d_revenue_lost": trailing_revenue,
        "impact_level": impact_level,
    }


def _aggregate_application_business_impact(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    current_loss = 0.0
    trailing_loss = 0.0
    trailing_failed = 0
    current_day_failed = 0
    business_hours_transactions = 0
    off_hours_transactions = 0
    for component in components:
        impact = component.get("business_impact") or {}
        current_day = impact.get("current_day") if isinstance(impact.get("current_day"), dict) else {}
        current_loss += float(current_day.get("estimated_revenue_lost") or 0.0)
        trailing_loss += float(impact.get("trailing_7d_revenue_lost") or 0.0)
        trailing_failed += int(impact.get("trailing_7d_failed_transactions") or 0)
        current_day_failed += int(current_day.get("failed_transactions") or 0)
        business_hours_transactions += int(current_day.get("business_hours_transactions") or 0)
        off_hours_transactions += int(current_day.get("off_hours_transactions") or 0)

    impact_level = "none"
    if current_loss >= 6000:
        impact_level = "high"
    elif current_loss >= 1500:
        impact_level = "medium"
    elif current_loss > 0:
        impact_level = "low"

    return {
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "business_peak_window": "09:00-18:00 IST",
        "current_business_hours_transactions": business_hours_transactions,
        "current_off_hours_transactions": off_hours_transactions,
        "current_estimated_revenue_lost": round(current_loss, 2),
        "current_day_failed_transactions": current_day_failed,
        "trailing_7d_revenue_lost": round(trailing_loss, 2),
        "trailing_7d_failed_transactions": trailing_failed,
        "impact_level": impact_level,
    }


def _generate_overview_insights(components: List[Dict[str, Any]]) -> Dict[str, str]:
    prompt = (
        "You are an AIOps analyst creating a portfolio overview for multiple applications. "
        "Given the current telemetry snapshot, return JSON only with a top-level key named 'applications'. "
        "That key must map service names to a short operational insight string of at most 2 sentences each. "
        "Focus on current status, likely impact, blast radius, and next attention area. Do not mention missing data unless it matters.\n\n"
        f"APPLICATION SNAPSHOT:\n{json.dumps(components, indent=2)[:12000]}"
    )
    ok, status, body_text = query_aide_api(prompt)
    if not ok:
        return {}
    try:
        start_index = body_text.find("{")
        end_index = body_text.rfind("}")
        payload = json.loads(body_text[start_index:end_index + 1]) if start_index != -1 and end_index != -1 else {}
    except json.JSONDecodeError:
        return {}
    applications = payload.get("applications")
    return applications if isinstance(applications, dict) else {}


def _build_application_overview(include_ai: bool = True, include_predictions: bool = True) -> Dict[str, Any]:
    cache_key = APP_OVERVIEW_CACHE_KEY if include_ai and include_predictions else None
    cached = cache.get(cache_key) if cache_key else None
    if isinstance(cached, dict):
        return cached

    flat_components = []
    # --- Batch MGET: collect all PromQL queries, check cache in one pipeline ---
    all_queries = []
    query_map = []  # [(app_idx, comp_idx, metric_key, query_str)]
    for app_idx, application in enumerate(APP_OVERVIEW_APPLICATIONS):
        if application.get("mode") == "demo":
            continue
        for comp_idx, component in enumerate(application["components"]):
            for metric_key, query_key in [
                ("up", "up_query"),
                ("request_rate", "request_query"),
                ("latency_p95_seconds", "latency_query"),
                ("error_rate", "error_query"),
            ]:
                q = component.get(query_key, "")
                if q:
                    all_queries.append(q)
                    query_map.append((app_idx, comp_idx, metric_key, q))

    # Pipeline cache lookup
    cached_results = instant_cache_batch_get(all_queries)

    # Fetch only cache misses
    misses = {}
    for _, _, _, q in query_map:
        if q and q not in cached_results and q not in misses:
            misses[q] = _fetch_prometheus_custom_query(q)

    # Batch-store misses (the individual fetch already caches via instant_cache_get_or_fetch,
    # but this is a no-op if the key was just set — harmless)
    if misses:
        instant_cache_batch_set(misses)

    # Merge
    all_results = {**cached_results, **misses}

    for application in APP_OVERVIEW_APPLICATIONS:
        if application.get("mode") == "demo":
            continue
        for component in application["components"]:
            metrics = {
                "up": _extract_first_sample_value(all_results.get(component.get("up_query", ""), {})),
                "request_rate": _extract_first_sample_value(all_results.get(component.get("request_query", ""), {})),
                "latency_p95_seconds": _extract_first_sample_value(all_results.get(component.get("latency_query", ""), {})),
                "error_rate": _extract_first_sample_value(all_results.get(component.get("error_query", ""), {})),
            }
            alerts = _recent_alerts_for_service(component["service"], component["target_host"])
            status = _derive_overview_status(component, metrics, alerts)
            logs = _fetch_elasticsearch_logs(component["target_host"], component["service"])
            traces = _fetch_jaeger_traces(component["service"] if component["kind"] == "microservice" else None)
            dependency_context = _get_dependency_context(component["service"])
            flat_components.append({
                "application": application["application"],
                "service": component["service"],
                "title": component["title"],
                "target_host": component["target_host"],
                "kind": component["kind"],
                "status": status,
                "metrics": metrics,
                "recent_alerts": alerts,
                "dependency_context": dependency_context,
                "depends_on": dependency_context.get("depends_on", []),
                "blast_radius": dependency_context.get("blast_radius", []),
                "dependency_chain": dependency_context.get("dependency_chain", []),
                "logs_summary": logs.get("hits", {}).get("hits", [])[:2] if isinstance(logs, dict) else [],
                "trace_count": len(traces.get("data", [])) if isinstance(traces, dict) and isinstance(traces.get("data"), list) else 0,
                "business_impact": _build_component_business_impact(
                    application["application"],
                    component["service"],
                    status,
                    metrics,
                ),
            })

    insights = _generate_overview_insights(flat_components) if include_ai else {}
    for component in flat_components:
        component["ai_insight"] = (
            insights.get(component["service"])
            if include_ai
            else ""
        ) or _fallback_overview_insight(
            component,
            component["metrics"],
            component["status"],
            component["recent_alerts"],
        )

    results = []
    for application in APP_OVERVIEW_APPLICATIONS:
        if application.get("mode") == "demo":
            components = []
            for component in application["components"]:
                dependency_context = _get_dependency_context(component["service"])
                components.append({
                    **component,
                    "dependency_context": dependency_context,
                    "depends_on": dependency_context.get("depends_on", []),
                    "blast_radius": dependency_context.get("blast_radius", []),
                    "dependency_chain": dependency_context.get("dependency_chain", []),
                    "business_impact": _build_component_business_impact(
                        application["application"],
                        component.get("service", ""),
                        component.get("status", "healthy"),
                        component.get("metrics") if isinstance(component.get("metrics"), dict) else {},
                    ),
                })
            overall_status = application.get("status", "healthy")
            active_alert_count = sum(
                1
                for component in components
                for alert in component.get("recent_alerts", [])
                if alert.get("status") == "firing"
            )
            headline = application.get("ai_insight") or f"{application['title']} is {overall_status}."
        else:
            components = [c for c in flat_components if c["application"] == application["application"]]
            overall_status = "healthy"
            if any(component["status"] == "down" for component in components):
                overall_status = "down"
            elif any(component["status"] == "degraded" for component in components):
                overall_status = "degraded"

            active_alert_count = sum(
                1
                for component in components
                for alert in component.get("recent_alerts", [])
                if alert.get("status") == "firing"
            )
            headline = next(
                (component.get("ai_insight") for component in components if component.get("status") != "healthy" and component.get("ai_insight")),
                f"{application['title']} is {overall_status}.",
            )
        results.append({
            "application": application["application"],
            "title": application["title"],
            "description": application["description"],
            "status": overall_status,
            "active_alert_count": active_alert_count,
            "ai_insight": headline,
            "blast_radius": sorted({node for component in components for node in component.get("blast_radius", [])}),
            "components": components,
            "business_impact": _aggregate_application_business_impact(components),
        })

    all_components = []
    for application in results:
        for component in application.get("components", []):
            all_components.append({
                **component,
                "application": application["application"],
            })
    if include_predictions:
        component_predictions = {
            (item["application"], item["service"]): item
            for item in score_components(all_components, save_results=False)
        }
        for application in results:
            application_risk_score = 0.0
            for component in application.get("components", []):
                prediction = component_predictions.get((application["application"], component["service"]), {})
                component["prediction"] = prediction
                application_risk_score = max(application_risk_score, float(prediction.get("risk_score") or 0.0))
            application["prediction"] = {
                "risk_score": round(application_risk_score, 4),
                "prediction_status": "high" if application_risk_score >= 0.75 else "medium" if application_risk_score >= 0.45 else "low",
                "predicted_window_minutes": 15,
            }

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(results),
        "results": results,
    }
    if cache_key:
        cache.set(cache_key, payload, APP_OVERVIEW_CACHE_TTL)
    return payload


def recent_predictions_view(request: HttpRequest):
    rows = list(
        ServicePrediction.objects.values(
            "application",
            "service",
            "status",
            "risk_score",
            "incident_probability",
            "predicted_window_minutes",
            "model_version",
            "features",
            "blast_radius",
            "explanation",
            "created_at",
        )[:30]
    )
    return JsonResponse({"count": len(rows), "results": rows})

# ---------------- LLM API (delegated to genai.llm_backend) ----------------
# Backward-compatible: query_aide_api is now imported from llm_backend.
# The original inline implementation has been moved to genai/llm_backend.py
# which supports both AIDE and vLLM (Qwen) backends via LLM_BACKEND env var.
from genai.llm_backend import query_aide_api  # noqa: E402

# ---------------- schema helpers ----------------
def get_full_schema_for_prompt(target_table: str = TARGET_TABLE, max_tables: int = 6, sample_rows_limit: int = 2, max_total_chars: int = 6000) -> str:
    global _schema_cache
    now = time.time()
    if _schema_cache[0] and _schema_cache[1] > now:
        return _schema_cache[0]
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema NOT IN ('information_schema','pg_catalog') AND table_type='BASE TABLE'
                ORDER BY table_schema, table_name
                """
            )
            tables = [(r[0], r[1]) for r in cur.fetchall()]
    except Exception:
        tables = []

    if target_table:
        idx = next((i for i, t in enumerate(tables) if t[1] == target_table), None)
        if idx is not None:
            tables.insert(0, tables.pop(idx))

    tables = tables[:max_tables]
    lines = []
    total_chars = 0
    for schema, tbl in tables:
        lines.append(f"Table: {schema}.{tbl}")
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    [schema, tbl]
                )
                cols = cur.fetchall()
        except Exception:
            cols = []

        for col_name, data_type, is_nullable, col_default in cols:
            line = f"  - {col_name} ({data_type}, nullable={is_nullable}, default={col_default})"
            lines.append(line)
            total_chars += len(line)
            if total_chars > max_total_chars:
                break

        # sample rows
        if sample_rows_limit and total_chars < max_total_chars and cols:
            sample_cols = [c[0] for c in cols][:6]
            try:
                col_list_sql = ", ".join([f'"{c}"' for c in sample_cols])
                with connection.cursor() as cur:
                    cur.execute(f"SELECT {col_list_sql} FROM {schema}.{tbl} LIMIT %s", [sample_rows_limit])
                    sample_rows = cur.fetchall()
                if sample_rows:
                    lines.append("  Sample rows:")
                    for r in sample_rows:
                        lines.append("    - " + "; ".join(f"{c}={_safe_preview_value(v,40)}" for c, v in zip(sample_cols, r)))
            except Exception:
                logger.exception("Failed to sample rows for %s.%s", schema, tbl)

        lines.append("")
        if total_chars > max_total_chars:
            break

    result = "\n".join(lines)[:max_total_chars]
    _schema_cache = (result, now + SCHEMA_CACHE_TTL)
    return result

# ---------------- helpful SQL utilities ----------------
def _extract_sql_from_markdown(text: str) -> str:
    """
    Extracts a SQL query from a markdown code block.
    Handles ```sql ... ``` or just ``` ... ```.
    """
    match = re.search(r"```(?:sql)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip() # Fallback for raw SQL

def _strip_after_stop_tokens(s: str) -> str:
    if not s: return ""
    sem_idx = s.find(";")
    candidates = [s]
    if sem_idx != -1: candidates.append(s[: sem_idx + 1])
    for token in SQL_STOP_TOKENS:
        idx = s.find(token)
        if idx != -1: candidates.append(s[:idx])
    candidates = [c for c in candidates if c.strip()]
    return min(candidates, key=len).strip() if candidates else s.strip()

def _ensure_select_prefix(sql: str) -> str:
    s = (sql or "").strip()
    if re.match(r"^(WHERE|ORDER\s+BY|GROUP\s+BY|LIMIT)\b", s, re.IGNORECASE):
        return f"SELECT * FROM {TARGET_TABLE} {s}"
    return s

def _quote_text_literals(sql: str) -> str:
    def repl_ilike(m):
        v = m.group(1).strip()
        if v.startswith("'") and v.endswith("'"): return f"ILIKE {v}"
        safe = v.replace("'", "''")
        return f"ILIKE '%{safe}%'"
    sql = re.sub(r"ILIKE\s+([^\s,);]+)", repl_ilike, sql, flags=re.IGNORECASE)
    def repl_eq(m):
        col = m.group(1); val = m.group(2).strip()
        if re.match(r"^\d+(\.\d+)?$", val): return f"{col} = {val}"
        if val.upper() in ("NULL","TRUE","FALSE"): return f"{col} = {val}"
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')): return f"{col} = {val}"
        safe = val.replace("'", "''")
        return f"{col} = '{safe}'"
    sql = re.sub(r"([A-Za-z0-9_\.]+)\s*=\s*([A-Za-z0-9_\.%-]+)", repl_eq, sql)
    return sql

def _prefer_ilike_for_strings(sql: str) -> str:
    if not sql:
        return sql
    def repl(m):
        col = m.group(1)
        val = m.group(2)
        if re.match(r"^\d+(\.\d+)?$", val) or val.upper() in ("NULL","TRUE","FALSE"):
            return f"{col} = {val}"
        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
            val2 = val[1:-1]
        else:
            val2 = val
        safe = val2.replace("'", "''")
        return f"{col} ILIKE '%{safe}%'"
    pattern = re.compile(r"([A-Za-z0-9_\.]+)\s*=\s*('.*?'|\".*?\"|\w+)", re.IGNORECASE)
    return pattern.sub(repl, sql)

def _extract_selected_columns(sql: str) -> List[str]:
    m = re.search(r"select\s+(.*?)\s+from\s", sql, flags=re.IGNORECASE | re.DOTALL)
    if not m: return []
    cols_part = m.group(1).strip()
    if re.search(r"\b\*\b", cols_part): return ["*"]
    cols = []
    for part in re.split(r',\s*(?![^()]*\))', cols_part):
        p = re.sub(r"\s+AS\s+.+$", "", part.strip(), flags=re.IGNORECASE)
        func_inner = re.sub(r"^[A-Za-z_][A-Za-z0-9_]*\s*\s*(.*?)\s*\s*$", r"\1", p)
        candidate = func_inner if func_inner != p else p
        candidate = candidate.split('.')[-1].strip().strip('"').strip("'")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", candidate):
            cols.append(candidate)
    return cols

# ---------------- intent detection ----------------
def classify_query(query: str):
    """Decide routing: docs, or general LLM (simple heuristics)."""
    if not query:
        return "general"
    t = query.lower()

    # Investigation / RCA prompts should stay on the general assistant path even if
    # they contain service, latency, or incident context. These are reasoning-heavy
    # prompts, not raw metric-query requests.
    investigation_keywords = [
        "rca",
        "root cause",
        "blast radius",
        "investigate",
        "investigation",
        "diagnose",
        "diagnostic step",
        "next diagnostic",
        "next step",
        "what happened",
        "why did",
        "why is",
        "impact",
        "impacted",
        "incident",
        "deep dive",
        "recommendation",
        "recommended command",
    ]
    contextual_handoff_markers = ["application=", "service=", "incident="]
    if any(keyword in t for keyword in investigation_keywords) or any(marker in t for marker in contextual_handoff_markers):
        return "investigation"
    
    # --- Prometheus/Observability Intent (Network & Server) ---
    observability_keywords = [
        'status', 'health', 'uptime', 'downtime', 'availability', 'reachable', 'online', 'offline', 'load', 'usage', 'utilization', 'capacity', 'bottleneck', 'saturation', 'throughput', 'slowdown', 'link', 'connection', 'line', 'cable', 'channel', 'speed', 'duplex', 'negotiation', 'link quality', 'flapping', 'instability', 'incoming', 'outgoing', 'upload', 'download', 'inbound', 'outbound', 'spikes', 'bursts', 'flow', 'congestion', 'faults', 'issues', 'anomalies', 'corruption', 'drops', 'failures', 'degraded link', 'signal problems', 'hostname', 'model', 'vendor', 'version', 'firmware', 'temperature', 'serial number', 'hardware status', 'power usage', 'poe usage', 'poe load', 'power consumption', 'overheating', 'fan status', 'neighbors', 'connected devices', 'upstream', 'downstream', 'path', 'hop', 'segment', 'vlan group', 'broadcast domain', 'unauthorized access', 'blocked', 'allowed', 'authentication issues', 'login attempts', 'security posture', 'alarms', 'warnings', 'critical events', 'logs', 'system messages', 'traps','packets','discarded','bandwidth','discarded','snmp'
        # Server
        'server', 'machine', 'system', 'host', 'node', 'computer',
'cpu', 'processor', 'core', 'load', 'usage', 'performance', 'slow', 'overload',
'memory', 'ram', 'swap', 'out of memory', 'running out of memory',
'disk', 'storage', 'hard drive', 'ssd', 'disk space', 'space full', 'low space',
'network', 'connection', 'internet', 'latency', 'ping', 'connectivity',
'process', 'task', 'app', 'program', 'service', 'daemon', 'running', 'stuck',
'boot', 'startup', 'reboot', 'shutdown', 'crash', 'freeze',
'temperature', 'heat', 'overheating',
'permissions', 'users', 'login', 'access', 'credentials',
'logs', 'errors', 'warnings', 'events',
'update', 'upgrade', 'patch', 'package', 'software install'
    ]
    
    # --- Direct File/System Action Intent ---
    direct_action_keywords = [
        'list files', 'delete file', 'remove file', 'ls', 'rm', 'show directory'
    ]
    if any(keyword in t for keyword in direct_action_keywords) and 'server' in t:
        return "direct_action"

    explicit_metric_keywords = [
        "prometheus",
        "promql",
        "metric",
        "metrics",
        "query",
        "cpu usage",
        "memory usage",
        "disk usage",
        "bandwidth",
        "process usage",
        "server health",
        "node exporter",
        "snmp",
        "rate(",
        "sum by",
        "avg by",
    ]
    if any(keyword in t for keyword in explicit_metric_keywords):
        return "prometheus_query"

    if any(keyword in t for keyword in observability_keywords):
        return "prometheus_query"

    # Rule for initiating a password reset. This is a fast, local rule that doesn't require an API call.
    password_reset_patterns = [
        r'reset\s+(my\s+)?password',
        r'password\s+reset',
        r'forgot\s+(my\s+)?password',
        r'change\s+(my\s+)?password',
        r'update\s+(my\s+)?password',
        r'unlock\s+(my\s+)?account',
        r'account\s+locked',
        r'cant\s+login',
        r'login\s+issue',
        r'unable to login'
    ]
    if any(re.search(pattern, t, re.IGNORECASE) for pattern in password_reset_patterns):
        return "initiate_password_reset"

    # All other queries will now be routed to either 'docs' or 'general'.
    doc_tokens = ["document", "docs", "confluence", "policy", "manual", "procedure", "pdf", "doc", "wiki"]
    if any(tok in t for tok in doc_tokens):
        return "docs"

    # Short greetings are routed to the general model.
    if len(t.split()) <= 6 and any(t.startswith(g) for g in ("hi", "hello", "hey", "what's up", "how are you", "good")):
        return "general"
    
    # Default to the general assistant. Documents are now opt-in instead of the default boundary.
    return "general"

# ---------------- visualization suggestion ----------------
def suggest_visualization(columns: List[str], rows: List[Tuple]) -> dict:
    sample_lines = []
    for r in rows[:10]:
        sample_lines.append(", ".join(f"{c}={_safe_preview_value(v,40)}" for c, v in zip(columns, r)))
    sample_preview = "\n".join(sample_lines) if sample_lines else ""
    prompt = (
        "You are a tool that suggests a single best visualization for a small SQL result set.\n"
        "Return a JSON object with keys: chart_type (one of bar,line,pie,table,scatter), x (column for x-axis or null), "
        "y (column for y-axis or null), explanation (1 sentence). Do NOT include other fields.\n\n"
        f"Columns: {', '.join(columns)}\nSample rows:\n{sample_preview}\n\nReturn JSON only:"
    )
    ok, status, body = query_aide_api(prompt)
    if not ok:
        if "status" in [c.lower() for c in columns]:
            return {"chart_type": "bar", "x": "status", "y": "count", "explanation": "Count records per status with a bar chart."}
        return {"chart_type": "table", "x": None, "y": None, "explanation": "No clear visualization suggested; return table."}
    try:
        # Clean the text to make sure it's valid JSON
        start_index = body.find('{')
        end_index = body.rfind('}')
        if start_index != -1 and end_index != -1:
            json_string = body[start_index:end_index+1]
            parsed = json.loads(json_string)
        else:
            parsed = {}

        chart_type = parsed.get("chart_type") if isinstance(parsed.get("chart_type"), str) else parsed.get("type") or "table"
        xcol = parsed.get("x")
        ycol = parsed.get("y")
        explanation = parsed.get("explanation") or parsed.get("why") or ""
        return {"chart_type": chart_type, "x": xcol, "y": ycol, "explanation": explanation}
    except Exception:
        if "status" in [c.lower() for c in columns]:
            return {"chart_type": "bar", "x": "status", "y": "count", "explanation": "Count records per status with a bar chart."}
        return {"chart_type": "table", "x": None, "y": None, "explanation": "No clear visualization suggested; return table."}

# ---------------- SQL handler (text->SQL->execute -> visualize -> persist) ----------------
def handle_direct_action(prompt: str) -> Tuple[Optional[dict], str]:
    """
    Handles a direct action request by using the AI to generate a safe command.
    Returns a dictionary with the command and target host, or an error string.
    """
    action_prompt = (
        "You are a system administrator's assistant. Your task is to convert a user's request into a single, safe Linux command. "
        "1.  **Identify the Action:** Determine if the user wants to list files (`ls`), delete a file (`rm`), or another simple file operation. "
        "2.  **Identify the Target:** Extract the target server's IP address or hostname. "
        "3.  **Identify the Path:** Extract the file or directory path. "
        "4.  **Assess Risk:** Determine if the command is destructive (e.g., `rm`, `find -delete`). "
        "5.  **Be Verbose:** For any destructive action, ensure the command produces output. Use verbose flags (e.g., `rm -v`) or print flags (e.g., `find ... -print -delete`). "
        "6.  **Handle Compound Requests:** If the user asks to show and then delete, combine the commands with a semicolon (e.g., `ls -l /some/dir; find /some/dir -name '*.log' -delete`)."
        "7.  **Format Output:** Return a JSON object with three keys: 'command' (string), 'target_host' (string), and 'is_destructive' (boolean). "
        "Return ONLY the JSON object.\n\n"
        "--- EXAMPLES ---\n"
        "User: 'list files in /var/log on server 10.1.10.5' -> {\"command\": \"ls -l /var/log\", \"target_host\": \"10.1.10.5\", \"is_destructive\": false}\n"
        "User: 'delete the file /tmp/error.log on the server 192.168.1.100' -> {\"command\": \"rm -v /tmp/error.log\", \"target_host\": \"192.168.1.100\", \"is_destructive\": true}\n"
        "User: 'show me the contents of /etc and delete all .tmp files there on server web-01' -> {\"command\": \"ls -l /etc; find /etc -name '*.tmp' -print -delete\", \"target_host\": \"web-01\", \"is_destructive\": true}\n\n"
        f"--- TASK ---\n"
        f"Generate the JSON for this request: '{prompt}'"
    )

    ok, status, body = query_aide_api(action_prompt)
    if not ok:
        return None, "Sorry, I couldn't understand that command. Please try rephrasing."

    try:
        start_index = body.find('{')
        end_index = body.rfind('}')
        if start_index != -1 and end_index != -1:
            json_string = body[start_index:end_index+1]
            response_data = json.loads(json_string)
            
            # Basic validation
            if 'command' in response_data and 'target_host' in response_data:
                return response_data, ""
            else:
                return None, "Sorry, I understood the request but couldn't determine the exact command or target server."
        else:
            return None, "Sorry, I failed to generate a valid command structure."
            
    except json.JSONDecodeError:
        logger.exception("Failed to decode JSON from direct action prompt.")
        return None, "Sorry, there was an issue interpreting the command."


def handle_prometheus_query(prompt: str) -> Tuple[Optional[dict], dict, str, str]:
    """
    Handles an observability query by dynamically generating and executing a PromQL query.
    This is a two-step AI process:
    1. Text-to-PromQL: Convert the user's question into a PromQL query for either network or server metrics.
    2. Results-to-Text: Interpret the Prometheus data and form a natural language answer with suggestions.
    """
    if not PROMETHEUS_URL:
        return None, {}, "Prometheus URL not configured", ""

    # --- Step 1: Generate PromQL from the user's prompt ---
    text_to_promql_prompt = (
        "You are a Prometheus expert for an IT infrastructure environment. Your task is to convert a user's question into a valid PromQL query. "
        "Determine if the user is asking about a **Network Device**, a **Server**, or a specific **Process**. Then, use the appropriate metrics.\n"
        "Return ONLY the PromQL query string. Do not add any explanation or markdown.\n\n"
        "--- CONTEXT 1: Network Device Metrics (SNMP Exporter) ---\n"
        "Use these for questions about switches, routers, and bandwidth.\n"
        "Metrics: ifHCInOctets, ifHCOutOctets, ifInErrors, ifOutErrors, ifOperStatus.\n"
        "Labels: 'instance' (device IP), 'ifName' (interface name).\n"
        "Example Q: 'What is the bandwidth for 172.24.95.10?' -> A: sum by (instance) (rate(ifHCInOctets{instance=\"172.24.95.10\"}[5m]))\n\n"
        "--- CONTEXT 2: Server Metrics (Node Exporter) ---\n"
        "Use these for general questions about servers, CPU, memory, and disk space.\n"
        "Metrics: node_cpu_seconds_total, node_memory_MemTotal_bytes, node_memory_MemAvailable_bytes, node_filesystem_size_bytes, node_filesystem_avail_bytes.\n"
        "Labels: 'instance' (server IP/hostname), 'device' (for disks), 'mountpoint'.\n"
        "Example Q: 'CPU usage for server 10.0.1.5?' -> A: 100 - (avg by (instance) (rate(node_cpu_seconds_total{instance=\"10.0.1.5\",mode='idle'}[5m])) * 100)\n\n"
        "--- CONTEXT 3: Per-Process Metrics (Process Exporter) ---\n"
        "Use these for specific questions about running processes like 'java' or 'nginx'.\n"
        "Metrics:\n"
        "- namedprocess_namegroup_cpu_seconds_total: CPU time for a process group.\n"
        "- namedprocess_namegroup_memory_bytes: Memory usage (resident, virtual, etc.). Use `memtype='resident'` for actual physical memory.\n"
        "- namedprocess_namegroup_num_threads: Number of threads.\n"
        "Labels: 'instance' (server IP), 'groupname' (the name of the process, e.g., 'java', 'nginx').\n"
        "Example Q: 'Which process is using the most CPU on 10.1.10.4?' -> A: topk(5, sum by (groupname) (rate(namedprocess_namegroup_cpu_seconds_total{instance=\"10.1.10.4\"}[5m])))\n"
        "Example Q: 'How much memory is the java process using on server 10.1.10.4?' -> A: namedprocess_namegroup_memory_bytes{groupname='java', instance='10.1.10.4', memtype='resident'}\n\n"
        f"--- TASK ---\n"
        f"Generate the PromQL query for this question: '{prompt}'"
    )

    ok, status, generated_query = query_aide_api(text_to_promql_prompt)
    if not ok or not generated_query.strip():
        logger.error(f"Failed to generate PromQL query. Status: {status}, Body: {generated_query}")
        return None, {}, "Sorry, I couldn't understand how to query that. Please try rephrasing your question.", ""

    promql_query = generated_query.strip()
    logger.info(f"Dynamically generated PromQL query: {promql_query}")

    # --- Step 2: Execute the generated query ---
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={'query': promql_query}, timeout=10)
        response.raise_for_status()
        prometheus_data = response.json()
    except requests.exceptions.RequestException as e:
        logger.exception("Failed to query Prometheus with generated query: %s", e)
        return None, {}, f"Error executing query against Prometheus: {e}", promql_query

    if not prometheus_data.get('data', {}).get('result'):
        return None, {}, "Sorry, your query returned no data. Please check the device or interface name and try again.", promql_query

    # --- Step 3: Interpret the results and suggest next steps ---
    results_to_text_prompt = (
        "You are an IT infrastructure observability expert. Your job is to interpret raw Prometheus data, provide a clear answer, and suggest relevant follow-up actions or diagnostic commands.\n"
        "1.  **Answer:** Directly answer the user's question based on the data.\n"
        "    - For **Bandwidth**, convert bytes/sec to a readable format like Mbps or Gbps.\n"
        "    - For **CPU Usage**, state the percentage clearly.\n"
        "    - For **Memory/Disk**, convert bytes to a readable format like MB, GB, or TB.\n"
        "    - For **Status**, explain the value (1=up, 2=down).\n"
        "    - For **Errors/Discards**, state the count. If it's high, mention that it might indicate a problem.\n"
        "2.  **Suggestions:** Provide a list of 2-3 insightful follow-up questions.\n"
        "3.  **Suggested Command:** If relevant, suggest a single, non-destructive Linux command that could help diagnose the issue further. For example, if CPU is high, suggest `top -b -n 1`. If disk is low, suggest `df -h`. If network errors are high, suggest `ip -s link show [interface]`.\n\n"
        "Format the output as a JSON object with three keys: 'answer' (string), 'follow_up_questions' (list of strings), and 'suggested_command' (string or null).\n\n"
        f"USER'S QUESTION: {prompt}\n"
        f"PROMETHEUS DATA: {json.dumps(prometheus_data.get('data', {}), indent=2)}\n\n"
        "JSON Response:"
    )

    ok, status, body = query_aide_api(results_to_text_prompt)
    if not ok:
        return None, {}, "Error: AI service failed to interpret the data.", promql_query

    # --- Step 4: Extract target_host and parse AI response ---
    target_host = None
    try:
        # Extract the 'instance' label from the first result to identify the target host.
        result_list = prometheus_data.get('data', {}).get('result', [])
        if result_list:
            metric_info = result_list[0].get('metric', {})
            if 'instance' in metric_info:
                target_host = metric_info['instance']
                # Often the instance includes the port, which we don't want for the host address.
                if ':' in target_host:
                    target_host = target_host.split(':')[0]
                logger.info(f"Extracted target_host='{target_host}' from Prometheus data.")

    except Exception as e:
        logger.warning(f"Could not extract target_host from Prometheus data: {e}")


    try:
        start_index = body.find('{')
        end_index = body.rfind('}')
        if start_index != -1 and end_index != -1:
            json_string = body[start_index:end_index+1]
            response_data = json.loads(json_string)
        else:
            response_data = {"answer": body, "follow_up_questions": [], "suggested_command": None}
        
        answer = response_data.get("answer", body)
        follow_ups = response_data.get("follow_up_questions", [])
        suggested_command = response_data.get("suggested_command")
        
    except json.JSONDecodeError:
        answer = body
        follow_ups = []
        suggested_command = None

    # The final dictionary now includes the target_host
    final_result = {
        "answer": answer, 
        "follow_up_questions": follow_ups, 
        "suggested_command": suggested_command,
        "target_host": target_host
    }
    return final_result, {}, "", promql_query

def handle_sql(prompt: str) -> Tuple[Optional[dict], dict, str, str]:
    """
    Returns (results_json_safe_or_None, vis_dict, error_msg_or_empty, generated_sql)
    results_json_safe = {'columns': [...], 'rows': [[..],[..]]}
    """
    schema = get_full_schema_for_prompt(target_table=TARGET_TABLE, max_tables=6, sample_rows_limit=0, max_total_chars=3000)
    sql_system = (
        "You are a PostgreSQL SQL generator. Return exactly ONE valid SQL SELECT statement only.\n"
        "Use ONLY the exact column names present in the schema below. If impossible to answer, return exactly: SELECT 'NOT_POSSIBLE' AS note;\n"
        "Return SQL only (no explanation)."
    )
    full_prompt = f"{sql_system}\n\nSCHEMA:\n{schema}\n\nQUESTION: {prompt}\nSQL:"
    ok, status, body = query_aide_api(full_prompt)
    logger.info("AIDE raw for SQL prompt: %s", (body or "")[:1000])
    if not ok:
        return None, {}, "Error: AI service failed.", ""

    raw_text = (body or "").strip()
    candidate = _extract_sql_from_markdown(raw_text)
    candidate = _strip_after_stop_tokens(candidate)
    candidate = _ensure_select_prefix(candidate)
    candidate = _quote_text_literals(candidate)
    generated_sql = candidate.strip()
    generated_sql = _prefer_ilike_for_strings(generated_sql)
    if not generated_sql.endswith(";"):
        generated_sql = generated_sql + ";"
    logger.info("Generated SQL (trimmed): %.500s", generated_sql)

    # Persist generated SQL early
    normalized_q = " ".join(prompt.lower().split())
    try:
        GenAIChatHistory.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": "Pending"})
    except Exception:
        logger.exception("Failed to persist generated_sql early.")

    if FORBIDDEN_SQL.search(generated_sql):
        err = "Error: Generated forbidden SQL statement."
        try:
            GenAIChatHistory.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
        except Exception:
            logger.exception("Failed to persist forbidden SQL error.")
        return None, {}, err, generated_sql

    # Validate columns
    try:
        with connection.cursor() as c:
            c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", [TARGET_TABLE])
            valid_cols = [r[0] for r in c.fetchall()]
    except Exception:
        valid_cols = []
        logger.exception("Failed to fetch valid columns for validation.")

    selected_cols = _extract_selected_columns(generated_sql)
    logger.info("Selected columns: %s", selected_cols)
    if selected_cols and "*" not in selected_cols:
        invalid = [col for col in selected_cols if col and col not in valid_cols]
        if invalid:
            err = f"Error: Query uses unknown columns: {', '.join(invalid)}"
            try:
                GenAIChatHistory.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
            except Exception:
                logger.exception("Failed to persist invalid-columns error.")
            return None, {}, err, generated_sql

    # EXPLAIN
    try:
        with connection.cursor() as c:
            c.execute("EXPLAIN " + generated_sql)
    except Exception as e:
        logger.exception("EXPLAIN failed: %s", e)
        err = "Error: Invalid SQL generated; please rephrase."
        try:
            GenAIChatHistory.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
        except Exception:
            logger.exception("Failed to persist EXPLAIN error.")
        return None, {}, err, generated_sql

    # Execute (safe limit)
    try:
        safe_sql = generated_sql if re.search(r"\blimit\b", generated_sql, flags=re.IGNORECASE) else generated_sql.rstrip(";") + " LIMIT 1000;"
        with connection.cursor() as c:
            c.execute(safe_sql)
            cols = [col[0] for col in c.description] if c.description else []
            rows = c.fetchall()
            results = {"columns": cols, "rows": rows}
    except Exception as e:
        logger.exception("DB execution failed: %s", e)
        err = "Error: DB execution failed."
        try:
            GenAIChatHistory.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": err})
        except Exception:
            logger.exception("Failed to persist DB exec error.")
        return None, {}, err, generated_sql

    # Suggest visualization
    vis = suggest_visualization(results["columns"], results["rows"])

    # Persist final answer blob
    answer_blob = {
        "rows_count": len(results["rows"]),
        "preview": [ {c: _safe_preview_value(v,80) for c, v in zip(results["columns"], row)} for row in results["rows"][:5] ],
        "visualization": vis
    }
    try:
        GenAIChatHistory.objects.update_or_create(question=normalized_q, defaults={"generated_sql": generated_sql, "answer": json.dumps(answer_blob)})
    except Exception:
        logger.exception("Failed to persist successful SQL run.")

    results_json_safe = {"columns": results["columns"], "rows": _rows_to_json_safe_lists(results["rows"])}
    return results_json_safe, vis, "", generated_sql

# ---------------- RAG proxy (delegation) ----------------
def proxy_to_rag(request: HttpRequest) -> JsonResponse:
    try:
        # local import to avoid circular import at module import time
        from doc_search import views as doc_views
        return doc_views.search_documents(request)
    except Exception as e:
        logger.exception("Error proxying to search_documents: %s", e)
        return JsonResponse({"error": "rag_proxy_failed", "detail": str(e)}, status=500)

# ---------------- main endpoint ----------------
@csrf_exempt
def genai_chat(request: HttpRequest):
    """
    Unified endpoint: accepts POST JSON with keys:
      - question (string)
      - use_documents (optional boolean override)
      - strict_docs (optional boolean)
      - top_k (optional int)
    Routing: classify into sql/docs/general, with client overrides respected.
    """
    if request.method != "POST":
        return JsonResponse({"error":"Invalid request method"}, status=405)
    try:
        body = json.loads(request.body or "{}")
    except Exception as e:
        logger.exception("genai_chat: invalid JSON: %s", e)
        return JsonResponse({"error":"invalid_json", "detail": str(e)}, status=400)

    logger.info(f"genai_chat: Received initial request body: {body}")

    if body.get('action') == 'create_password_ticket':
        return JsonResponse({
            "answer": "Ticketing integration is disabled in this AIOps build."
        }, status=400)

    elif body.get('action') == 'request_email_for_ticket':
        return JsonResponse({
            "answer": "Ticketing integration is disabled in this AIOps build."
        }, status=400)

    elif body.get('action') == 'create_ticket_from_docs':
        return JsonResponse({
            "answer": "Ticketing integration is disabled in this AIOps build."
        }, status=400)


    chat_session = _get_or_create_chat_session(request, body.get("session_id"))
    question = (body.get("question") or body.get("query") or "").strip()
    if not question:
        return JsonResponse({"error":"Question cannot be empty."}, status=400)

    conversation_history = _chat_history_for_prompt(chat_session)
    _append_chat_message(chat_session, "user", question, {"request_body": body})

    # --- Simple Caching Logic ---
    cached_result = simple_cache.search(question)
    if cached_result:
        cached_result['cached'] = True
        return _chat_json_response(chat_session, cached_result)
    # --- End Caching Logic ---

    # Profanity check
    if profanity.contains_profanity(question):
        return _chat_json_response(chat_session, {"answer": "Your message contains language or content that violates our community guidelines. Please keep the conversation respectful and appropriate so we can assist you better. Thank you for understanding."}, status=400)

    normalized_q = " ".join(question.lower().split())


    # client flags
    client_use_docs = body.get("use_documents", None)
    client_strict_docs = _to_bool(body.get("strict_docs"), default=False)
    client_top_k = int(body.get("top_k", 4)) if body.get("top_k") is not None else 4

    if isinstance(client_use_docs, str):
        client_use_docs = client_use_docs.strip().lower() in ("1","true","yes","y")
    # classify intent using simple heuristic
    route = classify_query(question)
    
    # Respect client override ONLY if the intent is not a specific, non-document action.
    # This prevents the frontend from forcing a 'docs' route when the user clearly intends a direct action or prometheus query.
    if route not in ["direct_action", "prometheus_query", "initiate_password_reset", "sql", "investigation"]:
        if client_use_docs is not None:
            route = "docs" if client_use_docs else "general"

    logger.info("genai_chat: question=%s route=%s (client_use_docs=%s)", question[:200], route, client_use_docs)

    # --- Password Reset Intent ---
    if route == "initiate_password_reset":
        return _chat_json_response(chat_session, {
            "question": question,
            "answer": "Password reset automation is not enabled in this AIOps build."
        })

    if route == "investigation":
        try:
            investigation_context = build_investigation_context(question, body)

            # Extract server-computed business impact so it's always in the response
            incident_data = investigation_context.get("incident") or {}
            business_impact = incident_data.get("business_impact") or {}
            if not business_impact and investigation_context.get("scope"):
                # Try computing from the incident directly
                scope = investigation_context["scope"]
                inc = _find_investigation_incident(scope)
                if inc:
                    business_impact = _compute_incident_revenue_impact(inc) or {}

            prompt = (
                "You are an AIOps incident investigation assistant. "
                "Use the incident context, metrics, logs, traces, and dependency graph to answer the user's question. "
                "Provide a concise RCA-oriented answer as JSON with two keys: 'answer' and 'follow_up_questions'.\n"
                "- 'answer' must explain the likely root cause, blast radius, strongest evidence, and the next best diagnostic step.\n"
                "- ALWAYS include the estimated revenue/business impact if available in the context (failed transactions, revenue lost, impact level).\n"
                "- If a linked recommendation or diagnostic command exists, mention it directly.\n"
                "- Do not answer with raw PromQL unless the user explicitly asked for a Prometheus query.\n\n"
                f"RECENT CONVERSATION:\n{conversation_history or 'No prior conversation.'}\n\n"
                f"QUESTION: {question}\n\n"
                f"INVESTIGATION CONTEXT:\n{json.dumps(investigation_context, indent=2)[:14000]}\n\n"
                "Return JSON only."
            )
            ok, status, body_text = query_aide_api(prompt)
            if not ok:
                return _chat_json_response(
                    chat_session,
                    {"error": "investigation_failed", "detail": body_text, "answer": "Investigation analysis failed."},
                    status=502,
                )

            try:
                start_index = body_text.find("{")
                end_index = body_text.rfind("}")
                parsed = json.loads(body_text[start_index:end_index + 1]) if start_index != -1 and end_index != -1 else {}
            except json.JSONDecodeError:
                parsed = {"answer": body_text, "follow_up_questions": []}

            response_data = {
                "question": question,
                "answer": parsed.get("answer") or body_text,
                "follow_up_questions": parsed.get("follow_up_questions") or [],
                "suggested_command": ((investigation_context.get("linked_recommendation") or {}).get("diagnostic_command")),
                "target_host": investigation_context.get("target_host"),
                "business_impact": business_impact,
                "cached": False,
            }
            return _chat_json_response(chat_session, response_data)
        except Exception as e:
            logger.exception("Investigation route error: %s", e)
            return _chat_json_response(
                chat_session,
                {"error": "investigation_failed", "detail": str(e), "answer": "Investigation routing failed."},
                status=500,
            )

    # Direct Action route
    if route == "direct_action":
        try:
            results, err = handle_direct_action(question)
            if err:
                return _chat_json_response(chat_session, {"question": question, "answer": err, "cached": False}, status=400)
            
            # This response structure is similar to the prometheus one,
            # providing the command and target to the frontend.
            response_data = {
                "question": question,
                "answer": f"I can execute that command for you. Please review and confirm.",
                "suggested_command": results.get("command"),
                "target_host": results.get("target_host"),
                "is_destructive": results.get("is_destructive", False),
                "cached": False
            }
            return _chat_json_response(chat_session, response_data)
        except Exception as e:
            logger.exception("Direct action route error: %s", e)
            return _chat_json_response(chat_session, {"error":"direct_action_failed", "detail": str(e), "answer": "Direct action routing failed."}, status=500)

    # Prometheus route
    if route == "prometheus_query":
        try:
            results, vis, err, generated_query = handle_prometheus_query(question)
            if err:
                return _chat_json_response(chat_session, {"question": question, "answer": err, "debug_info": generated_query, "cached": False}, status=400)
            
            # The 'results' dictionary now contains 'target_host'
            response_data = {
                "question": question,
                "answer": results.get("answer"),
                "follow_up_questions": results.get("follow_up_questions", []),
                "suggested_command": results.get("suggested_command"),
                "target_host": results.get("target_host"),
                "cached": False
            }
            return _chat_json_response(chat_session, response_data)
        except Exception as e:
            logger.exception("Prometheus route error: %s", e)
            return _chat_json_response(chat_session, {"error":"prometheus_query_failed", "detail": str(e), "answer": "Prometheus query routing failed."}, status=500)

    # SQL route
    if route == "sql":
        try:
            results, vis, err, generated_sql = handle_sql(question)
            if err:
                return _chat_json_response(chat_session, {"question": question, "answer": err, "debug_info": generated_sql, "cached": False}, status=400)
            # create preview text
            preview_text = ""
            try:
                if results and results.get("rows"):
                    header = " | ".join(results["columns"])
                    divider = "-" * max(len(header), 10)
                    body_lines = []
                    for row in results["rows"][:20]:
                        body_lines.append(" | ".join(map(str, row)))
                    preview_text = header + "\n" + divider + "\n" + "\n".join(body_lines)
            except Exception:
                preview_text = ""
            
            response_data = {
                "question": question,
                "data": results,
                "preview_text": preview_text,
                "visualization": vis,
                "generated_sql": generated_sql,
                "cached": False
            }
            simple_cache.add(question, response_data)
            return _chat_json_response(chat_session, response_data)
        except Exception as e:
            logger.exception("SQL route error: %s", e)
            return _chat_json_response(chat_session, {"error":"text_to_sql_failed", "detail": str(e), "answer": "SQL generation failed."}, status=500)

    # Docs (RAG) route -> delegate to doc_search
    if route == "docs":
        # DEFINITIVE FIX: Merge the original request body with the proxy fields
        # to ensure session_id and other state is preserved.
        proxy_body = body.copy() # Start with the original body
        proxy_body.update({
            "query": question,
            "top_k": client_top_k,
            "use_documents": True,
            "strict_docs": client_strict_docs
        })
        
        logger.info(f"genai_chat: Proxying to RAG with body: {proxy_body}")

        # patch request._body for delegation, restore after call
        original_body = getattr(request, "_body", request.body)
        try:
            request._body = json.dumps(proxy_body).encode("utf-8")
            response = proxy_to_rag(request)
            if isinstance(response, JsonResponse):
                try:
                    response_payload = json.loads(response.content.decode("utf-8"))
                except Exception:
                    response_payload = {"answer": response.content.decode("utf-8", errors="ignore")}
                if isinstance(response_payload, dict):
                    response_payload.setdefault("session_id", str(chat_session.session_id))
                    _record_chat_reply(chat_session, response_payload)
            return response
        finally:
            request._body = original_body

    # General LLM
    try:
        prompt = (
            "You are a helpful assistant. Your response MUST be a single JSON object with two keys: 'answer' and 'follow_up_questions'.\n"
            "- 'answer': A string containing the direct answer to the user's question.\n"
            "- 'follow_up_questions': A list of 3-4 relevant follow-up questions a user might ask next.\n\n"
            f"RECENT CONVERSATION:\n{conversation_history or 'No prior conversation.'}\n\n"
            f"QUESTION: {question}\n\nJSON Response:"
        )
        ok, status, body_text = query_aide_api(prompt)
        if not ok:
            logger.error("AIDE general completion failed: %s", body_text)
            return _chat_json_response(chat_session, {"error":"AIDE_completion_failed","detail": body_text, "answer": "AiDE failed to generate a response."}, status=502)

        try:
            # Clean the text to make sure it's valid JSON
            start_index = body_text.find('{')
            end_index = body_text.rfind('}')
            if start_index != -1 and end_index != -1:
                json_string = body_text[start_index:end_index+1]
                response_data = json.loads(json_string)
            else:
                response_data = {"answer": body_text, "follow_up_questions": []}
            
            answer = response_data.get("answer", body_text)
            follow_ups = response_data.get("follow_up_questions", [])
        except json.JSONDecodeError:
            answer = body_text
            follow_ups = []

        response_data = {"question": question, "answer": answer, "follow_up_questions": follow_ups, "cached": False}
        
        # Persist and cache
        try:
            GenAIChatHistory.objects.update_or_create(
                question=question,
                defaults={'answer': answer}
            )
            simple_cache.add(question, response_data)
        except Exception:
            logger.exception("Failed to persist or cache general chat history.")

        return _chat_json_response(chat_session, response_data)
    except Exception as e:
        logger.exception("General LLM error: %s", e)
        return _chat_json_response(chat_session, {"error":"general_llm_failed", "detail": str(e), "answer": "General LLM processing failed."}, status=500)

# ---------------- Excel download & FAQ ----------------
@csrf_exempt
def download_excel(request):
    if request.method != "POST":
        return JsonResponse({"error":"Invalid request method"}, status=405)
    try:
        data = json.loads(request.body or "{}")
        sql_query = data.get("sql", "").strip()
        if not sql_query:
            return JsonResponse({"error":"SQL query cannot be empty."}, status=400)
        if not sql_query.lower().strip().startswith("select"):
            return JsonResponse({"error":"Only SELECT queries allowed."}, status=400)
        with connection.cursor() as c:
            c.execute(sql_query)
            columns = [col[0] for col in c.description]
            rows = c.fetchall()
        df = pd.DataFrame(rows, columns=columns)
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]) and df[col].dt.tz is not None:
                df[col] = df[col].dt.tz_localize(None)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Results')
        output.seek(0)
        response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="query_results.xlsx"'
        return response
    except Exception as e:
        logger.exception("Excel export failed: %s", e)
        return JsonResponse({"error": str(e)}, status=500)

def get_faq_questions(request):
    """
    Gets a list of recent, distinct questions to show as FAQ prompts.
    This result is no longer cached via Redis, as the semantic cache handles the primary load.
    """
    try:
        # Fetch a small number of recent, unique questions directly from the DB.
        # The performance impact is minimal for this query.
        recent_questions = list(GenAIChatHistory.objects.order_by('-id').values_list('question', flat=True).distinct()[:4])
        return JsonResponse({"questions": recent_questions})
    except Exception as e:
        logger.exception("Failed to fetch FAQ questions: %s", e)
        return JsonResponse({"error": str(e)}, status=500)

# ---------------- chat sessions, auth, incident views ----------------
@csrf_exempt
def chat_session_init_view(request: HttpRequest):
    session_id = request.GET.get("session_id") if request.method == "GET" else None
    if request.method == "POST":
        try:
            body = json.loads(request.body or "{}")
        except Exception as exc:
            return JsonResponse({"error": "invalid_json", "detail": str(exc)}, status=400)
        session_id = body.get("session_id") or session_id
    session = _get_or_create_chat_session(request, session_id)
    messages = [_serialize_chat_message(message) for message in session.messages.all()[:100]]
    return JsonResponse({
        "session_id": str(session.session_id),
        "title": session.title,
        "messages": messages,
        "user": request.user.username if request.user.is_authenticated else "",
    })


@csrf_exempt
def chat_session_list_view(request: HttpRequest):
    requested_ids: List[str] = []
    if request.method == "POST":
        try:
            body = json.loads(request.body or "{}")
        except Exception as exc:
            return JsonResponse({"error": "invalid_json", "detail": str(exc)}, status=400)
        if isinstance(body.get("session_ids"), list):
            requested_ids = [str(value).strip() for value in body.get("session_ids") if str(value).strip()]
    elif request.method != "GET":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    sessions = _recent_chat_sessions_for_request(request, requested_ids=requested_ids)
    return JsonResponse({
        "count": len(sessions),
        "results": [_serialize_chat_session(session) for session in sessions],
    })


@csrf_exempt
def chat_session_reset_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    try:
        body = json.loads(request.body or "{}")
    except Exception:
        body = {}
    old_session_id = body.get("session_id") or request.session.get("genai_chat_session_id")
    if old_session_id:
        ChatSession.objects.filter(session_id=old_session_id).update(is_active=False)
    request.session.pop("genai_chat_session_id", None)
    session = _get_or_create_chat_session(request, None)
    return JsonResponse({"session_id": str(session.session_id), "messages": []})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.POST.get("next") or request.GET.get("next") or "/genai/applications/dashboard/")
    next_url = request.POST.get("next") or request.GET.get("next") or "/genai/applications/dashboard/"
    google_configured = (
        os.getenv("GOOGLE_CLIENT_ID", "").strip() not in ("", "PASTE_GOOGLE_CLIENT_ID_HERE")
        and os.getenv("GOOGLE_CLIENT_SECRET", "").strip() not in ("", "PASTE_GOOGLE_CLIENT_SECRET_HERE")
    )
    if request.method == "POST" and not getattr(settings, "SSO_ENABLED", True):
        username = str(request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect(next_url)
        return render(request, "genai/login.html", {
            "next_url": next_url,
            "sso_enabled": False,
            "google_oauth_configured": google_configured,
            "redirect_uri": f"{request.scheme}://{request.get_host()}/accounts/google/login/callback/",
            "login_error": "Invalid username or password.",
            "username": username,
        })
    return render(request, "genai/login.html", {
        "next_url": next_url,
        "sso_enabled": getattr(settings, "SSO_ENABLED", True),
        "google_oauth_configured": google_configured,
        "redirect_uri": f"{request.scheme}://{request.get_host()}/accounts/google/login/callback/",
    })


def sso_login_view(request):
    next_url = request.GET.get("next") or "/genai/applications/dashboard/"
    if not getattr(settings, "SSO_ENABLED", True):
        return redirect(f"/genai/login/?next={next_url}")
    return redirect(f"/accounts/google/login/?process=login&next={next_url}")


def logout_view(request):
    auth_logout(request)
    return redirect("/genai/login/")


# ---------------- admin console view (document upload + process) ----------------
@login_required
def genai_console(request):
    from doc_search.forms import DocumentForm
    from doc_search.models import Document
    from doc_search.views import process_document_chunks

    if request.method == 'POST':
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save()
            try:
                process_document_chunks(doc)
            except Exception as e:
                logger.error(f"Failed to process document chunks: {e}")
            return redirect('genai:genai_console')
    else:
        form = DocumentForm()
    
    documents = Document.objects.all().order_by('-uploaded_at')
    return render(request, 'genai/genai_console.html', {
        'form': form,
        'documents': documents,
        'active_nav': 'documents',
    })


@xframe_options_exempt
@csrf_exempt
def widget_view(request):
    """
    Renders the standalone chat widget.
    - @xframe_options_exempt: Allows this view to be embedded in an iframe on external sites.
    - @csrf_exempt: Exempts this view from CSRF protection, as it's a public widget without a user session.
    """
    return render(request, 'genai/widget.html')


@login_required
def assistant_app_view(request):
    return render(request, 'genai/assistant.html', {"active_nav": "assistant"})


@login_required
def applications_dashboard_view(request):
    return render(request, 'genai/applications_dashboard.html', {"active_nav": "applications"})


@login_required
def applications_overview_view(request: HttpRequest):
    return JsonResponse(_build_application_overview())


@login_required
def cache_stats_view(request: HttpRequest):
    """Return telemetry cache observability stats."""
    return JsonResponse({"status": "ok", "data": get_cache_stats()})


@login_required
def cache_purge_view(request: HttpRequest):
    """
    POST /genai/cache/purge/
    Body (optional): {"prefix": "iq"} or {"prefix": "meta"} or omit for full flush.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    prefix = body.get("prefix")  # None → flush all
    result = purge_cache(prefix)
    return JsonResponse({"status": "ok", **result})


def _graph_node_status_from_component(component: Dict[str, Any]) -> str:
    return component.get("status") or "healthy"


def _application_graph_payload(application_key: str) -> Optional[Dict[str, Any]]:
    overview = _build_application_overview(include_ai=True, include_predictions=True)
    application = next((item for item in overview.get("results", []) if item.get("application") == application_key), None)
    if not application:
        return None

    graph = _load_dependency_graph().get("applications", {}).get(application_key, {})
    component_map = {component.get("service"): component for component in application.get("components", [])}

    reverse_graph: Dict[str, List[str]] = {}
    for source, dependencies in graph.items():
        for dependency in dependencies:
            reverse_graph.setdefault(dependency, []).append(source)

    nodes = []
    for service, dependencies in graph.items():
        component = component_map.get(service, {})
        prediction = component.get("prediction") or {}
        nodes.append({
            "id": service,
            "label": component.get("title") or service,
            "service": service,
            "kind": component.get("kind") or "service",
            "status": _graph_node_status_from_component(component),
            "role": "dependency" if not reverse_graph.get(service) else "service",
            "metrics": component.get("metrics", {}),
            "prediction": prediction,
            "depends_on": dependencies,
            "dependents": reverse_graph.get(service, []),
            "ai_insight": component.get("ai_insight") or "",
        })

    edges = [
        {
            "id": f"{source}->{dependency}",
            "source": source,
            "target": dependency,
            "relationship": "depends_on",
        }
        for source, dependencies in graph.items()
        for dependency in dependencies
    ]

    root_candidate = next(
        (component.get("service") for component in application.get("components", []) if component.get("status") in ("down", "degraded")),
        application.get("components", [{}])[0].get("service") if application.get("components") else None,
    )

    return {
        "graph_type": "application",
        "key": application_key,
        "title": application.get("title") or application_key,
        "summary": application.get("ai_insight") or f"{application_key} topology graph",
        "status": application.get("status") or "healthy",
        "root_node_id": root_candidate,
        "nodes": nodes,
        "edges": edges,
        "blast_radius": application.get("blast_radius", []),
        "evidence": {
            "active_alert_count": application.get("active_alert_count", 0),
            "prediction": application.get("prediction") or {},
        },
    }


def _incident_graph_payload(incident: Incident) -> Dict[str, Any]:
    dependency_context = incident.dependency_graph or _get_dependency_context(incident.primary_service)
    application = incident.application or dependency_context.get("application")
    app_graph = _load_dependency_graph().get("applications", {}).get(application, {}) if application else {}

    service_nodes = set()
    root_service = incident.primary_service or incident.target_host or ""
    if root_service:
        service_nodes.add(root_service)
    service_nodes.update(dependency_context.get("depends_on", []) or [])
    service_nodes.update(dependency_context.get("direct_dependents", []) or [])
    service_nodes.update(dependency_context.get("blast_radius", []) or [])

    if root_service and app_graph:
        service_nodes.update(app_graph.get(root_service, []))
        for service, dependencies in app_graph.items():
            if root_service in dependencies:
                service_nodes.add(service)

    application_payload = _application_graph_payload(application) if application else None
    application_node_map = {
        node.get("service"): node
        for node in (application_payload or {}).get("nodes", [])
        if isinstance(node, dict)
    }

    nodes = []
    for service in sorted(service_nodes):
        base_node = application_node_map.get(service, {})
        role = "service"
        if service == root_service:
            role = "root_cause"
        elif service in (dependency_context.get("depends_on") or []):
            role = "dependency"
        elif service in (dependency_context.get("blast_radius") or []):
            role = "impacted"
        nodes.append({
            "id": service,
            "label": base_node.get("label") or service,
            "service": service,
            "kind": base_node.get("kind") or "service",
            "status": base_node.get("status") or ("down" if service == root_service and incident.status != "resolved" else "healthy"),
            "role": role,
            "metrics": base_node.get("metrics", {}),
            "prediction": base_node.get("prediction") or {},
            "depends_on": app_graph.get(service, []) if app_graph else [],
            "dependents": [node for node, deps in app_graph.items() if service in deps] if app_graph else [],
            "ai_insight": base_node.get("ai_insight") or "",
        })

    node_ids = {node["id"] for node in nodes}
    edges = [
        {
            "id": f"{source}->{dependency}",
            "source": source,
            "target": dependency,
            "relationship": "depends_on",
        }
        for source, dependencies in app_graph.items()
        for dependency in dependencies
        if source in node_ids and dependency in node_ids
    ]

    return {
        "graph_type": "incident",
        "key": str(incident.incident_key),
        "title": incident.title,
        "summary": incident.summary or incident.reasoning or "Incident topology graph",
        "status": incident.status,
        "root_node_id": root_service or None,
        "nodes": nodes,
        "edges": edges,
        "blast_radius": incident.blast_radius or dependency_context.get("blast_radius", []),
        "evidence": {
            "reasoning": incident.reasoning,
            "alerts": [
                {
                    "alert_name": alert.alert_name,
                    "status": alert.status,
                    "service_name": alert.service_name,
                    "target_host": alert.target_host,
                }
                for alert in incident.alerts.all()[:10]
            ],
            "timeline_count": incident.timeline.count(),
        },
    }


@login_required
def application_graph_view(request: HttpRequest, application_key: str):
    payload = _application_graph_payload(application_key)
    if not payload:
        return JsonResponse({"error": "application_not_found"}, status=404)
    return JsonResponse(payload)


@login_required
def alerts_dashboard_view(request):
    return render(request, 'genai/alerts_dashboard.html', {"active_nav": "alerts"})


@login_required
def incidents_dashboard_view(request):
    return render(request, "genai/incidents_dashboard.html", {"active_nav": "incidents"})


@login_required
def incidents_recent_view(request: HttpRequest):
    incidents = list(Incident.objects.all()[:20])
    return JsonResponse({"count": len(incidents), "results": [_incident_summary_payload(incident) for incident in incidents]})


@login_required
def incident_timeline_page_view(request: HttpRequest, incident_key: str):
    return render(request, "genai/incident_timeline.html", {"incident_key": incident_key})


@login_required
def incident_timeline_view(request: HttpRequest, incident_key: str):
    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)
    return JsonResponse(_incident_timeline_payload(incident))


@login_required
def incident_graph_view(request: HttpRequest, incident_key: str):
    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)
    return JsonResponse(_incident_graph_payload(incident))

# This should be the same secret token configured on the secure agents.
AGENT_SECRET_TOKEN = os.getenv("AGENT_SECRET_TOKEN")

@csrf_exempt
def ingest_alert_view(request: HttpRequest):
    """
    Accepts an alert payload, gathers observability context, asks AiDE for a
    diagnostic command, optionally executes it through the remote agent, and
    returns the investigation result.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        body = json.loads(request.body or "{}")
    except Exception as exc:
        logger.exception("ingest_alert_view: invalid JSON: %s", exc)
        return JsonResponse({"error": "invalid_json", "detail": str(exc)}, status=400)

    envelope_execute = body.get("execute")
    alert_payload, from_alertmanager = _normalize_alertmanager_payload(body)
    if not from_alertmanager:
        alert_payload = body.get("alert") if isinstance(body.get("alert"), dict) else body
    if not isinstance(alert_payload, dict):
        return JsonResponse({"error": "alert_payload_required"}, status=400)

    context = collect_alert_context(alert_payload)
    target_host = (
        body.get("target_host")
        or context.get("target_host")
        or _extract_target_host_from_payload(alert_payload)
    )
    execute_immediately = _to_bool(envelope_execute, default=not from_alertmanager)

    planning_prompt = (
        "You are an AIOps incident responder. Given the alert payload and telemetry context, "
        "return JSON only with keys: summary, target_host, diagnostic_command, why, should_execute.\n"
        "- diagnostic_command must be a single executable command suitable for the target troubleshooting agent.\n"
        "- should_execute must be true only if there is enough information to run the command now.\n"
        "- target_host must be the hostname or IP where the command should run.\n\n"
        "- The telemetry context already contains Prometheus metrics, Elasticsearch logs, and Jaeger traces gathered by the app.\n"
        "- If those logs are sufficient, summarize the root cause directly.\n"
        "- If more evidence is needed, recommend one concrete diagnostic command appropriate for the execution target.\n"
        "- Do not tell the operator to inspect logs manually. The command output will be sent back to the AI for analysis.\n\n"
        "- Use the dependency graph context to estimate blast radius, upstream dependents, and the likely impacted services.\n"
        "- The agent does not support shell operators, command substitution, pipes, or semicolons.\n"
        "- For app containers, prefer file-log commands like `tail -n 200 /var/log/demo/app-orders.log`.\n"
        f"- For the database target (`db` -> `{DB_AGENT_HOST}`), prefer `pg_isready -h db` or a `psql -h db -U {DB_USER} -d {DB_NAME} -c ...` query.\n"
        "- If the evidence points to a shared dependency path, pivot the target to that dependency instead of staying on the symptom service.\n"
        "- Return a literal executable command only.\n\n"
        f"ALERT PAYLOAD:\n{json.dumps(alert_payload, indent=2)}\n\n"
        f"OBSERVABILITY CONTEXT:\n{json.dumps(context, indent=2)[:12000]}\n"
    )
    ok, status, planning_body = query_aide_api(planning_prompt)
    if not ok:
        return JsonResponse(
            {"error": "AIDE_planning_failed", "detail": planning_body, "context": context},
            status=502,
        )

    try:
        start_index = planning_body.find("{")
        end_index = planning_body.rfind("}")
        if start_index != -1 and end_index != -1:
            plan = json.loads(planning_body[start_index:end_index + 1])
        else:
            plan = {}
    except json.JSONDecodeError:
        plan = {}

    normalized_plan = _coerce_diagnostic_plan(alert_payload, context, plan, target_host)
    diagnostic_command = normalized_plan["diagnostic_command"]
    target_host = normalized_plan["target_host"]
    summary = normalized_plan["summary"]
    why = normalized_plan["why"]
    should_execute = normalized_plan["should_execute"]
    target_type = normalized_plan["target_type"]

    response_payload = {
        "summary": summary,
        "why": why,
        "target_host": target_host,
        "target_type": target_type,
        "diagnostic_command": diagnostic_command,
        "should_execute": should_execute,
        "context": context,
    }

    incident = _correlate_alert_to_incident(alert_payload, context, summary, why)
    response_payload["incident"] = _incident_summary_payload(incident)

    cache_entry = {
        "alert_id": f"alert-{uuid.uuid4().hex}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "alert_name": alert_payload.get("alert_name") or ((alert_payload.get("labels") or {}).get("alertname")),
        "status": alert_payload.get("status", "firing"),
        "target_host": target_host,
        "target_type": target_type,
        "summary": summary,
        "initial_ai_diagnosis": summary,
        "why": why,
        "initial_ai_reasoning": why,
        "diagnostic_command": diagnostic_command,
        "should_execute": should_execute,
        "execute_immediately": execute_immediately,
        "from_alertmanager": from_alertmanager,
        "labels": alert_payload.get("labels") or {},
        "annotations": alert_payload.get("annotations") or {},
        "dependency_graph": context.get("dependency_graph") or {},
        "blast_radius": (context.get("dependency_graph") or {}).get("blast_radius", []),
        "depends_on": (context.get("dependency_graph") or {}).get("depends_on", []),
        "incident_key": str(incident.incident_key),
        "incident_status": incident.status,
        "incident_title": incident.title,
    }

    # If this alert is resolved, remove matching cached entries so the frontend
    # will no longer show stale firing alerts. For non-executing (deferred)
    # recommendations, store them as before.
    if alert_payload.get("status") == "resolved":
        removed = _remove_recent_alert_recommendation_by_identity(
            cache_entry.get("alert_name"), cache_entry.get("target_host"), cache_entry.get("from_alertmanager")
        )
        logger.info("Removed %d cached alert(s) for resolved alert %s", removed, cache_entry.get("alert_name"))
        return JsonResponse(response_payload)

    if not execute_immediately:
        _store_recent_alert_recommendation(cache_entry)
        return JsonResponse(response_payload)

    if not AGENT_SECRET_TOKEN:
        response_payload["error"] = "AGENT_SECRET_TOKEN is not configured."
        return JsonResponse(response_payload, status=500)

    if not diagnostic_command or not target_host or not should_execute:
        response_payload["error"] = "AiDE did not return an executable command and target."
        return JsonResponse(response_payload, status=400)

    success, command_output, agent_response = delegate_command_to_agent(diagnostic_command, target_host)
    analysis_ok, final_answer, analysis_sections = analyze_command_output(
        summary,
        target_host,
        diagnostic_command,
        command_output,
        context=context,
    )

    response_payload.update({
        "agent_success": success,
        "agent_response": agent_response,
        "command_output": command_output,
        "final_answer": final_answer,
        "analysis_sections": analysis_sections,
        "analysis_ok": analysis_ok,
    })
    IncidentTimelineEvent.objects.create(
        incident=incident,
        event_type="diagnostic_command_executed",
        title=f"Executed diagnostic command on {target_host}",
        detail=diagnostic_command,
        payload={
            "command": diagnostic_command,
            "target_host": target_host,
            "agent_success": success,
            "command_output": command_output[:4000],
            "final_answer": final_answer,
            "analysis_sections": analysis_sections,
        },
    )
    cache_entry.update({
        "agent_success": success,
        "analysis_ok": analysis_ok,
        "final_answer": final_answer,
        "analysis_sections": analysis_sections,
        "remediation_command": analysis_sections.get("remediation_command") or "",
        "remediation_target_host": analysis_sections.get("remediation_target_host") or "",
        "remediation_why": analysis_sections.get("remediation_why") or "",
        "remediation_requires_approval": _to_bool(analysis_sections.get("remediation_requires_approval"), default=bool(analysis_sections.get("remediation_command"))),
        "post_command_ai_analysis": final_answer,
        "command_output": command_output,
        "agent_response": agent_response,
        "execution_status": "completed" if success else "failed",
        "last_execution_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    _store_recent_alert_recommendation(cache_entry)
    return JsonResponse(response_payload, status=200 if success else 502)


@login_required
def recent_alert_recommendations_view(request: HttpRequest):
    entries = cache.get(RECENT_ALERT_CACHE_KEY) or []
    if not isinstance(entries, list):
        entries = []
    
    normalized_entries = []
    changed = False
    firing_entries = []  # Track only firing alerts
    
    for entry in entries:
        if not isinstance(entry, dict):
            normalized_entries.append(entry)
            continue
        
        # Add alert_id if missing
        if not entry.get("alert_id"):
            changed = True
            entry = {**entry, "alert_id": f"alert-{uuid.uuid4().hex}"}
        
        normalized_entries.append(entry)
        
        # Only include firing alerts (filter out resolved alerts)
        if entry.get("status") != "resolved":
            firing_entries.append(entry)
    
    if changed:
        cache.set(RECENT_ALERT_CACHE_KEY, normalized_entries[:MAX_RECENT_ALERTS], RECENT_ALERT_CACHE_TTL)
    
    return JsonResponse({"count": len(firing_entries), "results": firing_entries})

@csrf_exempt
@login_required
def execute_command_view(request: HttpRequest):
    """
    Delegates a command suggested by the AI to the secure agent on the target server.
    This is the central part of the 'Secure Action Loop'.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    
    if not AGENT_SECRET_TOKEN:
        logger.error("CRITICAL: AGENT_SECRET_TOKEN is not set on the bot server. Cannot delegate commands.")
        return JsonResponse({"error": "Bot server is not configured for command execution."}, status=500)

    try:
        body = json.loads(request.body or "{}")
        alert_id = body.get("alert_id")
        command_to_run = body.get("command")
        original_question = body.get("original_question")
        target_host = body.get("target_host") # The IP or hostname of the server to run the command on.
        execution_type = _summarize_execution_type(str(body.get("execution_type") or "diagnostic").strip().lower())

        if not all([command_to_run, original_question, target_host]):
            return JsonResponse({"error": "Missing required fields: command, original_question, and target_host are required."}, status=400)

        linked_recommendation = _lookup_recent_alert_recommendation(alert_id)
        execution_context = {
            "linked_recommendation": linked_recommendation or {},
            "dependency_graph": (linked_recommendation or {}).get("dependency_graph") or {},
            "incident_key": (linked_recommendation or {}).get("incident_key"),
            "target_type": (linked_recommendation or {}).get("target_type"),
        }
        success, command_output, agent_response = delegate_command_to_agent(command_to_run, target_host)
        ok, final_answer, analysis_sections = analyze_command_output(
            original_question,
            target_host,
            command_to_run,
            command_output,
            context=execution_context,
        )
        if not ok:
            return JsonResponse({"error": final_answer}, status=502)

        execution_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        execution_status = "completed" if success else "failed"
        command_output_key = "remediation_output" if execution_type == "remediation" else "command_output"
        answer_key = "post_remediation_ai_analysis" if execution_type == "remediation" else "post_command_ai_analysis"
        execution_status_key = "remediation_execution_status" if execution_type == "remediation" else "execution_status"
        execution_time_key = "remediation_last_execution_at" if execution_type == "remediation" else "last_execution_at"
        timeline_event_type = "remediation_command_executed" if execution_type == "remediation" else "manual_command_executed"
        timeline_title = f"Manual {execution_type} command executed against {target_host}"

        if alert_id:
            incident_key = None
            recent_entries = cache.get(RECENT_ALERT_CACHE_KEY) or []
            if isinstance(recent_entries, list):
                for candidate in recent_entries:
                    if isinstance(candidate, dict) and candidate.get("alert_id") == alert_id:
                        incident_key = candidate.get("incident_key")
                        break
            _update_recent_alert_recommendation(
                alert_id,
                {
                    execution_time_key: execution_time,
                    execution_status_key: execution_status,
                    "agent_success": success,
                    "final_answer": final_answer,
                    "analysis_sections": analysis_sections,
                    answer_key: final_answer,
                    command_output_key: command_output,
                    "remediation_command": analysis_sections.get("remediation_command") or ((linked_recommendation or {}).get("remediation_command")) or "",
                    "remediation_target_host": analysis_sections.get("remediation_target_host") or ((linked_recommendation or {}).get("remediation_target_host")) or "",
                    "remediation_why": analysis_sections.get("remediation_why") or ((linked_recommendation or {}).get("remediation_why")) or "",
                    "remediation_requires_approval": _to_bool(
                        analysis_sections.get("remediation_requires_approval"),
                        default=_to_bool((linked_recommendation or {}).get("remediation_requires_approval"), default=False),
                    ),
                    "agent_response": agent_response,
                },
            )
            if incident_key:
                incident = Incident.objects.filter(incident_key=incident_key).first()
                if incident:
                    incident.status = "investigating"
                    incident.summary = incident.summary or original_question
                    incident.save(update_fields=["status", "summary", "updated_at"])
                    IncidentTimelineEvent.objects.create(
                        incident=incident,
                        event_type=timeline_event_type,
                        title=timeline_title,
                        detail=command_to_run,
                        payload={
                            "execution_type": execution_type,
                            "command": command_to_run,
                            "target_host": target_host,
                            "agent_success": success,
                            "command_output": command_output[:4000],
                            "final_answer": final_answer,
                            "analysis_sections": analysis_sections,
                        },
                    )

        return JsonResponse({
            "execution_type": execution_type,
            "final_answer": final_answer,
            "analysis_sections": analysis_sections,
            "command_output": command_output,
            "agent_success": success,
            "agent_response": agent_response,
            "last_execution_at": execution_time,
            "execution_status": execution_status,
        })

    except Exception as e:
        logger.exception("execute_command_view error: %s", e)
        return JsonResponse({"error": "An unexpected error occurred.", "detail": str(e)}, status=500)

FLEET_PROFILE_SEED = [
    {
        "slug": "infra-observability",
        "name": "Infra + Logs + Traces",
        "summary": "Recommended Linux profile with collector, node exporter, log shipping, and discovery enabled.",
        "default_for_target": "linux",
        "components": [
            "AIOps Supervisor",
            "OpenTelemetry Collector",
            "node_exporter",
            "log shipper",
            "discovery helper",
        ],
        "capabilities": ["metrics", "logs", "traces", "discovery", "heartbeat"],
        "config_json": {"logs_enabled": True, "traces_enabled": True, "discovery_enabled": True},
    },
    {
        "slug": "infra-logs",
        "name": "Infra + Logs",
        "summary": "Host metrics, service discovery, and centralized logs without application trace forwarding.",
        "default_for_target": "linux",
        "components": [
            "AIOps Supervisor",
            "OpenTelemetry Collector",
            "node_exporter",
            "log shipper",
        ],
        "capabilities": ["metrics", "logs", "discovery", "heartbeat"],
        "config_json": {"logs_enabled": True, "traces_enabled": False, "discovery_enabled": True},
    },
    {
        "slug": "infra-only",
        "name": "Infra Only",
        "summary": "Smallest Linux bundle for host metrics, heartbeat, and base control-plane enrollment.",
        "default_for_target": "linux",
        "components": [
            "AIOps Supervisor",
            "OpenTelemetry Collector",
            "node_exporter",
        ],
        "capabilities": ["metrics", "heartbeat"],
        "config_json": {"logs_enabled": False, "traces_enabled": False, "discovery_enabled": False},
    },
]


def _ensure_fleet_profiles() -> List[TelemetryProfile]:
    profiles: List[TelemetryProfile] = []
    for seed in FLEET_PROFILE_SEED:
        profile, _ = TelemetryProfile.objects.get_or_create(
            slug=seed["slug"],
            defaults={
                "name": seed["name"],
                "summary": seed["summary"],
                "default_for_target": seed["default_for_target"],
                "components": seed["components"],
                "capabilities": seed["capabilities"],
                "config_json": seed.get("config_json", {}),
                "is_active": True,
            },
        )
        changed = False
        for field in ("name", "summary", "default_for_target", "components", "capabilities", "config_json"):
            new_value = seed.get(field)
            if getattr(profile, field) != new_value:
                setattr(profile, field, new_value)
                changed = True
        if not profile.is_active:
            profile.is_active = True
            changed = True
        if changed:
            profile.save()
        profiles.append(profile)
    return profiles


def _serialize_profile(profile: TelemetryProfile) -> Dict[str, Any]:
    return {
        "slug": profile.slug,
        "name": profile.name,
        "summary": profile.summary,
        "default_for_target": profile.default_for_target,
        "components": profile.components or [],
        "capabilities": profile.capabilities or [],
    }


def _serialize_target(target: Target) -> Dict[str, Any]:
    components = list(target.components.all().order_by("name"))
    discovered_count = target.discovered_services.count()
    if not discovered_count:
        discovered_count = int(target.metadata_json.get("discovered_service_count") or 0)
    return {
        "target_id": target.target_id,
        "name": target.name,
        "target_type": target.target_type,
        "environment": target.environment,
        "hostname": target.hostname,
        "status": target.status,
        "last_heartbeat": target.last_heartbeat_at.isoformat() if target.last_heartbeat_at else "not connected yet",
        "profile_name": target.profile.name if target.profile else "Unassigned",
        "collector_status": target.collector_status,
        "discovered_service_count": discovered_count,
        "components": [
            {"name": component.name, "status": component.status}
            for component in components
        ],
    }


def _get_profile_by_slug(slug: str) -> TelemetryProfile:
    _ensure_fleet_profiles()
    return TelemetryProfile.objects.filter(slug=slug).first() or TelemetryProfile.objects.order_by("name").first()


@login_required
def fleet_targets_view(request: HttpRequest):
    _ensure_fleet_profiles()
    targets = Target.objects.select_related("profile").prefetch_related("components", "discovered_services").all()
    return JsonResponse({"count": targets.count(), "results": [_serialize_target(target) for target in targets]})


@login_required
def fleet_profiles_view(request: HttpRequest):
    profiles = _ensure_fleet_profiles()
    return JsonResponse({"count": len(profiles), "results": [_serialize_profile(profile) for profile in profiles]})


@login_required
def fleet_enroll_blueprint_view(request: HttpRequest):
    target_type = (request.GET.get("target_type") or "linux").strip().lower()
    profile_slug = (request.GET.get("profile") or "infra-observability").strip()
    profile = _get_profile_by_slug(profile_slug)
    token_value = f"lnx_{uuid.uuid4().hex[:24]}"
    expires_at = timezone.now() + timezone.timedelta(hours=24)
    token = EnrollmentToken.objects.create(
        token=token_value,
        target_type=target_type,
        profile=profile,
        created_by=request.user,
        expires_at=expires_at,
    )
    control_plane = _public_control_plane_base_url(request)
    install_command = (
        f"curl -fsSL {control_plane}/genai/fleet/install/linux/ | "
        f"sudo bash -s -- --control-plane {control_plane} --token {token.token} --profile {profile.slug}"
    )
    next_steps = [
        "Create an aiops-agent user and install the supervisor service.",
        "Install OpenTelemetry Collector and the selected host exporters locally.",
        "Enroll back into the control plane and start heartbeat reporting.",
        "Begin discovery so services can populate Fleet, Applications, and Graphs.",
    ]
    return JsonResponse(
        {
            "target_type": target_type,
            "install_mode": "generated_shell_bootstrap" if target_type == "linux" else "planned",
            "token_preview": token.token[:16] + "...",
            "install_command": install_command,
            "components": profile.components or [],
            "next_steps": next_steps,
        }
    )


@csrf_exempt
def fleet_enroll_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    try:
        body = json.loads(request.body or "{}")
        token_value = str(body.get("token") or "").strip()
        if not token_value:
            return JsonResponse({"error": "Missing enrollment token"}, status=400)
        token = EnrollmentToken.objects.select_related("profile").filter(token=token_value, revoked=False).first()
        if not token or not token.is_valid:
            return JsonResponse({"error": "Invalid or expired enrollment token"}, status=403)
        target_name = str(body.get("name") or token.target_name or body.get("hostname") or "linux-target").strip()
        target_id = str(body.get("target_id") or uuid.uuid4()).strip()
        hostname = str(body.get("hostname") or "").strip()
        target, _ = Target.objects.update_or_create(
            target_id=target_id,
            defaults={
                "name": target_name,
                "target_type": token.target_type,
                "environment": str(body.get("environment") or "production").strip(),
                "hostname": hostname,
                "ip_address": str(body.get("ip_address") or "").strip(),
                "os_name": str(body.get("os_name") or "Linux").strip(),
                "os_version": str(body.get("os_version") or "").strip(),
                "status": "connected",
                "profile": token.profile,
                "collector_status": str(body.get("collector_status") or "healthy").strip(),
                "metadata_json": body.get("metadata_json") or {},
                "last_heartbeat_at": timezone.now(),
            },
        )
        token.used_at = token.used_at or timezone.now()
        token.target_name = token.target_name or target.name
        token.save(update_fields=["used_at", "target_name"])
        for component_name in (body.get("components") or (token.profile.components if token.profile else [])):
            if not component_name:
                continue
            TargetComponent.objects.update_or_create(
                target=target,
                name=str(component_name),
                defaults={"status": "healthy"},
            )
        return JsonResponse({"target": _serialize_target(target), "profile": _serialize_profile(target.profile) if target.profile else None})
    except Exception as exc:
        logger.exception("fleet_enroll_view error: %s", exc)
        return JsonResponse({"error": "Unable to enroll target", "detail": str(exc)}, status=500)


@csrf_exempt
def fleet_heartbeat_view(request: HttpRequest, target_id: str):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    try:
        body = json.loads(request.body or "{}")
        target = Target.objects.select_related("profile").filter(target_id=target_id).first()
        if not target:
            return JsonResponse({"error": "Unknown target"}, status=404)
        target.last_heartbeat_at = timezone.now()
        target.collector_status = str(body.get("collector_status") or target.collector_status or "healthy").strip()
        target.status = str(body.get("status") or target.status or "connected").strip()
        metadata = target.metadata_json or {}
        metadata.update(body.get("metadata_json") or {})
        target.metadata_json = metadata
        target.save(update_fields=["last_heartbeat_at", "collector_status", "status", "metadata_json", "updated_at"])
        TargetHeartbeat.objects.create(target=target, payload=body)
        for component in body.get("components") or []:
            name = str(component.get("name") or "").strip()
            if not name:
                continue
            TargetComponent.objects.update_or_create(
                target=target,
                name=name,
                defaults={
                    "status": str(component.get("status") or "healthy").strip(),
                    "version": str(component.get("version") or "").strip(),
                    "metadata_json": component.get("metadata_json") or {},
                },
            )
        for service in body.get("discovered_services") or []:
            service_name = str(service.get("service_name") or "").strip()
            if not service_name:
                continue
            port = service.get("port")
            DiscoveredService.objects.update_or_create(
                target=target,
                service_name=service_name,
                port=port,
                defaults={
                    "process_name": str(service.get("process_name") or "").strip(),
                    "status": str(service.get("status") or "observed").strip(),
                    "metadata_json": service.get("metadata_json") or {},
                },
            )
        return JsonResponse({"status": "ok", "target": _serialize_target(target)})
    except Exception as exc:
        logger.exception("fleet_heartbeat_view error: %s", exc)
        return JsonResponse({"error": "Unable to record heartbeat", "detail": str(exc)}, status=500)



def _public_control_plane_base_url(request: HttpRequest) -> str:
    if AIOPS_PUBLIC_BASE_URL:
        return AIOPS_PUBLIC_BASE_URL.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def _public_otlp_grpc_endpoint(request: HttpRequest) -> str:
    if AIOPS_PUBLIC_OTLP_GRPC_ENDPOINT:
        return AIOPS_PUBLIC_OTLP_GRPC_ENDPOINT
    base_url = _public_control_plane_base_url(request)
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 4317
    return f"{host}:{4317 if port in (80, 443, 8000, 8089, 5173) else port}"


def _serialize_onboarding_request(onboarding: TargetOnboardingRequest) -> Dict[str, Any]:
    return {
        "onboarding_id": onboarding.onboarding_id,
        "name": onboarding.name,
        "hostname": onboarding.hostname,
        "ssh_user": onboarding.ssh_user,
        "ssh_port": onboarding.ssh_port,
        "target_type": onboarding.target_type,
        "profile_slug": onboarding.profile.slug if onboarding.profile else "",
        "status": onboarding.status,
        "connectivity_status": onboarding.connectivity_status,
        "connectivity_message": onboarding.connectivity_message,
        "last_connectivity_check_at": onboarding.last_connectivity_check_at.isoformat() if onboarding.last_connectivity_check_at else None,
        "last_install_at": onboarding.last_install_at.isoformat() if onboarding.last_install_at else None,
        "install_message": onboarding.install_message,
        "target_id": onboarding.target.target_id if onboarding.target else None,
        "pem_file_name": os.path.basename(onboarding.pem_file.name) if onboarding.pem_file else "",
    }


@login_required
def fleet_onboarding_requests_view(request: HttpRequest):
    if request.method == "GET":
        requests_qs = TargetOnboardingRequest.objects.select_related("profile", "target").all()
        return JsonResponse({"count": requests_qs.count(), "results": [_serialize_onboarding_request(item) for item in requests_qs]})

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        name = str(request.POST.get("name") or "").strip()
        hostname = str(request.POST.get("hostname") or "").strip()
        ssh_user = str(request.POST.get("ssh_user") or "ubuntu").strip()
        ssh_port = int(request.POST.get("ssh_port") or 22)
        target_type = str(request.POST.get("target_type") or "linux").strip().lower()
        profile_slug = str(request.POST.get("profile") or "infra-observability").strip()
        pem_file = request.FILES.get("pem_file")

        if not all([name, hostname, pem_file]):
            return JsonResponse({"error": "name, hostname, and pem_file are required"}, status=400)

        profile = _get_profile_by_slug(profile_slug)
        onboarding = TargetOnboardingRequest.objects.create(
            name=name,
            hostname=hostname,
            ssh_user=ssh_user,
            ssh_port=ssh_port,
            target_type=target_type,
            profile=profile,
            pem_file=pem_file,
            created_by=request.user,
        )
        return JsonResponse(_serialize_onboarding_request(onboarding), status=201)
    except Exception as exc:
        logger.exception("fleet_onboarding_requests_view error: %s", exc)
        return JsonResponse({"error": "Unable to create onboarding request", "detail": str(exc)}, status=500)


@login_required
def fleet_onboarding_request_detail_view(request: HttpRequest, onboarding_id: str):
    onboarding = TargetOnboardingRequest.objects.select_related("profile", "target").filter(onboarding_id=onboarding_id).first()
    if not onboarding:
        return JsonResponse({"error": "Unknown onboarding request"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_onboarding_request(onboarding))

    if request.method == "DELETE":
        if onboarding.pem_file:
            onboarding.pem_file.delete(save=False)
        onboarding.delete()
        return JsonResponse({"status": "deleted", "onboarding_id": onboarding_id})

    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)

    try:
        name = str(request.POST.get("name") or onboarding.name).strip()
        hostname = str(request.POST.get("hostname") or onboarding.hostname).strip()
        ssh_user = str(request.POST.get("ssh_user") or onboarding.ssh_user or "ubuntu").strip()
        ssh_port = int(request.POST.get("ssh_port") or onboarding.ssh_port or 22)
        target_type = str(request.POST.get("target_type") or onboarding.target_type or "linux").strip().lower()
        profile_slug = str(request.POST.get("profile") or (onboarding.profile.slug if onboarding.profile else "infra-observability")).strip()
        pem_file = request.FILES.get("pem_file")

        profile = _get_profile_by_slug(profile_slug)
        onboarding.name = name
        onboarding.hostname = hostname
        onboarding.ssh_user = ssh_user
        onboarding.ssh_port = ssh_port
        onboarding.target_type = target_type
        onboarding.profile = profile
        if pem_file:
            if onboarding.pem_file:
                onboarding.pem_file.delete(save=False)
            onboarding.pem_file = pem_file
        onboarding.connectivity_status = "untested"
        onboarding.connectivity_message = ""
        onboarding.status = "draft"
        onboarding.save()
        return JsonResponse(_serialize_onboarding_request(onboarding))
    except Exception as exc:
        logger.exception("fleet_onboarding_request_detail_view error: %s", exc)
        return JsonResponse({"error": "Unable to update onboarding request", "detail": str(exc)}, status=500)



def _ssh_base_command(onboarding: TargetOnboardingRequest) -> List[str]:
    if onboarding.pem_file and os.path.exists(onboarding.pem_file.path):
        try:
            os.chmod(onboarding.pem_file.path, 0o600)
        except OSError:
            logger.warning("Unable to chmod PEM file %s", onboarding.pem_file.path)
    return [
        "ssh",
        "-i", onboarding.pem_file.path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "PreferredAuthentications=publickey",
        "-o", "ConnectTimeout=30",
        "-p", str(onboarding.ssh_port),
        f"{onboarding.ssh_user}@{onboarding.hostname}",
    ]


@csrf_exempt
@login_required
def fleet_onboarding_test_view(request: HttpRequest, onboarding_id: str):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    onboarding = TargetOnboardingRequest.objects.select_related("profile", "target").filter(onboarding_id=onboarding_id).first()
    if not onboarding:
        return JsonResponse({"error": "Unknown onboarding request"}, status=404)
    try:
        tcp_check = subprocess.run(
            ["nc", "-vz", "-w", "5", onboarding.hostname, str(onboarding.ssh_port)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        onboarding.last_connectivity_check_at = timezone.now()
        if tcp_check.returncode != 0:
            onboarding.connectivity_status = "failed"
            onboarding.connectivity_message = (
                "TCP reachability to the SSH port failed. "
                + (tcp_check.stderr or tcp_check.stdout or "Unable to open the port.")
            )[:2000]
            onboarding.status = "failed"
            onboarding.save(update_fields=["last_connectivity_check_at", "connectivity_status", "connectivity_message", "status", "updated_at"])
            return JsonResponse(_serialize_onboarding_request(onboarding), status=502)

        command = _ssh_base_command(onboarding) + ["printf aiops-connectivity-ok"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        if result.returncode == 0 and "aiops-connectivity-ok" in (result.stdout or ""):
            onboarding.connectivity_status = "reachable"
            onboarding.connectivity_message = "TCP port 22 is reachable and SSH authentication succeeded from the control plane."
            onboarding.status = "validated"
        else:
            onboarding.connectivity_status = "failed"
            onboarding.connectivity_message = (
                "TCP port 22 is reachable, but the full SSH session from the control plane failed. "
                + (result.stderr or result.stdout or "SSH authentication or banner exchange failed.")
            )[:2000]
            onboarding.status = "failed"
        onboarding.save(update_fields=["last_connectivity_check_at", "connectivity_status", "connectivity_message", "status", "updated_at"])
        return JsonResponse(_serialize_onboarding_request(onboarding))
    except Exception as exc:
        onboarding.last_connectivity_check_at = timezone.now()
        onboarding.connectivity_status = "failed"
        onboarding.connectivity_message = str(exc)
        onboarding.status = "failed"
        onboarding.save(update_fields=["last_connectivity_check_at", "connectivity_status", "connectivity_message", "status", "updated_at"])
        return JsonResponse(_serialize_onboarding_request(onboarding), status=502)



def _build_linux_install_command(control_plane: str, token_value: str, profile_slug: str, target_name: str, hostname: str) -> str:
    safe_name = json.dumps(target_name)
    safe_host = json.dumps(hostname)
    return (
        f"curl -fsSL {control_plane}/genai/fleet/install/linux/ | "
        f"sudo bash -s -- --control-plane {control_plane} --token {token_value} --profile {profile_slug} "
        f"--target-name {safe_name} --hostname {safe_host}"
    )


@csrf_exempt
@login_required
def fleet_onboarding_install_view(request: HttpRequest, onboarding_id: str):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    onboarding = TargetOnboardingRequest.objects.select_related("profile", "target").filter(onboarding_id=onboarding_id).first()
    if not onboarding:
        return JsonResponse({"error": "Unknown onboarding request"}, status=404)
    if onboarding.connectivity_status != "reachable":
        return JsonResponse({"error": "Connectivity must be validated before install"}, status=400)
    try:
        token_value = f"lnx_{uuid.uuid4().hex[:24]}"
        token = EnrollmentToken.objects.create(
            token=token_value,
            target_type=onboarding.target_type,
            target_name=onboarding.name,
            profile=onboarding.profile,
            created_by=request.user,
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
        control_plane = _public_control_plane_base_url(request)
        install_command = _build_linux_install_command(
            control_plane,
            token.token,
            onboarding.profile.slug if onboarding.profile else "infra-observability",
            onboarding.name,
            onboarding.hostname,
        )
        remote_command = _ssh_base_command(onboarding) + [install_command]
        onboarding.status = "installing"
        onboarding.install_message = "Running remote bootstrap command..."
        onboarding.save(update_fields=["status", "install_message", "updated_at"])
        result = subprocess.run(remote_command, capture_output=True, text=True, timeout=600)
        onboarding.last_install_at = timezone.now()
        if result.returncode == 0:
            onboarding.status = "installed"
            onboarding.install_message = (result.stdout or "Remote bootstrap command completed.")[:4000]
        else:
            onboarding.status = "failed"
            onboarding.install_message = (result.stderr or result.stdout or "Remote bootstrap command failed.")[:4000]
        onboarding.save(update_fields=["status", "last_install_at", "install_message", "updated_at"])
        payload = _serialize_onboarding_request(onboarding)
        payload["install_command"] = install_command
        return JsonResponse(payload)
    except Exception as exc:
        onboarding.status = "failed"
        onboarding.last_install_at = timezone.now()
        onboarding.install_message = str(exc)
        onboarding.save(update_fields=["status", "last_install_at", "install_message", "updated_at"])
        payload = _serialize_onboarding_request(onboarding)
        return JsonResponse(payload, status=502)


@csrf_exempt
@xframe_options_exempt
def fleet_linux_install_script_view(request: HttpRequest):
    otlp_endpoint = _public_otlp_grpc_endpoint(request)
    script = f"""#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE=""
TOKEN=""
PROFILE="infra-observability"
TARGET_NAME=""
TARGET_HOSTNAME=""
OTLP_ENDPOINT="{otlp_endpoint}"
OTELCOL_VERSION="{AIOPS_OTELCOL_VERSION}"
NODE_EXPORTER_VERSION="{AIOPS_NODE_EXPORTER_VERSION}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --control-plane)
      CONTROL_PLANE="$2"
      shift 2
      ;;
    --token)
      TOKEN="$2"
      shift 2
      ;;
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --target-name)
      TARGET_NAME="$2"
      shift 2
      ;;
    --hostname)
      TARGET_HOSTNAME="$2"
      shift 2
      ;;
    --otlp-endpoint)
      OTLP_ENDPOINT="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

if [[ -z "$CONTROL_PLANE" || -z "$TOKEN" || -z "$OTLP_ENDPOINT" ]]; then
  echo "Missing --control-plane, --token, or --otlp-endpoint" >&2
  exit 1
fi

install_prereqs() {{
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y curl tar ca-certificates python3
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y curl tar ca-certificates python3 shadow-utils
  elif command -v yum >/dev/null 2>&1; then
    yum install -y curl tar ca-certificates python3 shadow-utils
  else
    echo "Unsupported package manager. Install curl, tar, ca-certificates, and python3 manually." >&2
    exit 1
  fi
}}

detect_arch() {{
  case "$(uname -m)" in
    x86_64|amd64)
      ARCH_NODE=amd64
      ARCH_OTEL=amd64
      ;;
    aarch64|arm64)
      ARCH_NODE=arm64
      ARCH_OTEL=arm64
      ;;
    *)
      echo "Unsupported architecture: $(uname -m)" >&2
      exit 1
      ;;
  esac
}}

install_node_exporter() {{
  local url="https://github.com/prometheus/node_exporter/releases/download/v${{NODE_EXPORTER_VERSION}}/node_exporter-${{NODE_EXPORTER_VERSION}}.linux-${{ARCH_NODE}}.tar.gz"
  rm -rf /tmp/node_exporter-install
  mkdir -p /tmp/node_exporter-install
  curl -fsSL "$url" -o /tmp/node_exporter.tgz
  tar -xzf /tmp/node_exporter.tgz -C /tmp/node_exporter-install
  install -m 0755 /tmp/node_exporter-install/node_exporter-${{NODE_EXPORTER_VERSION}}.linux-${{ARCH_NODE}}/node_exporter /usr/local/bin/node_exporter
}}

install_otelcol() {{
  local url="https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${{OTELCOL_VERSION}}/otelcol-contrib_${{OTELCOL_VERSION}}_linux_${{ARCH_OTEL}}.tar.gz"
  rm -rf /tmp/otelcol-install
  mkdir -p /tmp/otelcol-install
  curl -fsSL "$url" -o /tmp/otelcol.tgz
  tar -xzf /tmp/otelcol.tgz -C /tmp/otelcol-install
  install -m 0755 /tmp/otelcol-install/otelcol-contrib /usr/local/bin/otelcol-contrib
}}

write_configs() {{
  id -u aiops-agent >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash aiops-agent
  mkdir -p /opt/aiops-agent /etc/aiops-agent /var/log/aiops-agent /etc/otelcol-contrib
  cat > /etc/aiops-agent/enrollment.env <<ENV
CONTROL_PLANE=$CONTROL_PLANE
TOKEN=$TOKEN
PROFILE=$PROFILE
OTLP_ENDPOINT=$OTLP_ENDPOINT
ENV
  chmod 600 /etc/aiops-agent/enrollment.env

  cat > /etc/otelcol-contrib/config.yaml <<COLLECTOR
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu: {{}}
      memory: {{}}
      disk: {{}}
      filesystem: {{}}
      load: {{}}
      network: {{}}
      paging: {{}}
      process: {{}}
  prometheus:
    config:
      scrape_configs:
        - job_name: linux-node-exporter
          scrape_interval: 30s
          static_configs:
            - targets: ["127.0.0.1:9100"]
processors:
  batch: {{}}
exporters:
  otlp:
    endpoint: $OTLP_ENDPOINT
    tls:
      insecure: true
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp]
    metrics:
      receivers: [hostmetrics, prometheus]
      processors: [batch]
      exporters: [otlp]
COLLECTOR

  cat > /etc/systemd/system/node_exporter.service <<NODE
[Unit]
Description=Prometheus Node Exporter
After=network-online.target
Wants=network-online.target

[Service]
User=aiops-agent
Group=aiops-agent
ExecStart=/usr/local/bin/node_exporter --web.listen-address=:9100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
NODE

  cat > /etc/systemd/system/otelcol-contrib.service <<OTEL
[Unit]
Description=OpenTelemetry Collector Contrib
After=network-online.target node_exporter.service
Wants=network-online.target

[Service]
User=root
Group=root
EnvironmentFile=/etc/aiops-agent/enrollment.env
ExecStart=/usr/local/bin/otelcol-contrib --config=/etc/otelcol-contrib/config.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
OTEL
}}

enroll_target() {{
  HOSTNAME_VALUE="${{TARGET_HOSTNAME:-$(hostname)}}"
  TARGET_LABEL="${{TARGET_NAME:-$HOSTNAME_VALUE}}"
  PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{{print $1}}')"
  OS_NAME=linux
  OS_VERSION=unknown
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_NAME="${{NAME:-linux}}"
    OS_VERSION="${{VERSION_ID:-unknown}}"
  fi

  ENROLL_PAYLOAD=$(cat <<JSON
{{
  "token": "$TOKEN",
  "name": "$TARGET_LABEL",
  "target_id": "$HOSTNAME_VALUE",
  "hostname": "$HOSTNAME_VALUE",
  "environment": "production",
  "ip_address": "$PRIMARY_IP",
  "os_name": "$OS_NAME",
  "os_version": "$OS_VERSION",
  "collector_status": "installing",
  "components": [
    "AIOps Supervisor",
    "OpenTelemetry Collector",
    "node_exporter"
  ],
  "metadata_json": {{
    "profile": "$PROFILE",
    "bootstrap_mode": "phase3"
  }}
}}
JSON
)

  curl -fsS -X POST "$CONTROL_PLANE/genai/fleet/enroll/" \
    -H "Content-Type: application/json" \
    -d "$ENROLL_PAYLOAD" >/tmp/aiops-enroll.json

  TARGET_ID=$(python3 - <<'PYTHON'
import json
with open('/tmp/aiops-enroll.json') as handle:
    payload = json.load(handle)
print((payload.get('target') or {{}}).get('target_id', ''))
PYTHON
)

  cat > /usr/local/bin/aiops-heartbeat.sh <<HEARTBEAT
#!/usr/bin/env bash
set -euo pipefail
source /etc/aiops-agent/enrollment.env
TARGET_ID="$TARGET_ID"
HOSTNAME_VALUE="${{TARGET_HOSTNAME:-$(hostname)}}"
PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{{print $1}}')"
NODE_STATUS=$(systemctl is-active node_exporter 2>/dev/null || echo unknown)
OTEL_STATUS=$(systemctl is-active otelcol-contrib 2>/dev/null || echo unknown)
PAYLOAD=$(cat <<JSON
{{
  "status": "connected",
  "collector_status": "$OTEL_STATUS",
  "components": [
    {{"name": "AIOps Supervisor", "status": "healthy", "version": "phase3"}},
    {{"name": "OpenTelemetry Collector", "status": "$OTEL_STATUS", "version": "$OTELCOL_VERSION"}},
    {{"name": "node_exporter", "status": "$NODE_STATUS", "version": "$NODE_EXPORTER_VERSION"}}
  ],
  "discovered_services": [
    {{"service_name": "node_exporter", "process_name": "node_exporter", "port": 9100, "status": "observed"}},
    {{"service_name": "otelcol-contrib", "process_name": "otelcol-contrib", "port": 4317, "status": "observed"}}
  ],
  "metadata_json": {{
    "profile": "$PROFILE",
    "host": "$HOSTNAME_VALUE",
    "ip": "$PRIMARY_IP"
  }}
}}
JSON
)

curl -fsS -X POST "$CONTROL_PLANE/genai/fleet/targets/$TARGET_ID/heartbeat/" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" >/tmp/aiops-heartbeat.json
HEARTBEAT
  chmod +x /usr/local/bin/aiops-heartbeat.sh

  cat > /etc/systemd/system/aiops-heartbeat.service <<HB
[Unit]
Description=AIOps Target Heartbeat
After=network-online.target otelcol-contrib.service node_exporter.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/aiops-heartbeat.sh
HB

  cat > /etc/systemd/system/aiops-heartbeat.timer <<TIMER
[Unit]
Description=Run AIOps heartbeat every minute

[Timer]
OnBootSec=30s
OnUnitActiveSec=60s
Unit=aiops-heartbeat.service

[Install]
WantedBy=timers.target
TIMER
}}

start_services() {{
  systemctl daemon-reload
  systemctl enable --now node_exporter.service
  systemctl enable --now otelcol-contrib.service
  systemctl enable --now aiops-heartbeat.timer
  /usr/local/bin/aiops-heartbeat.sh || true
}}

install_prereqs
detect_arch
install_node_exporter
install_otelcol
write_configs
enroll_target
start_services

echo "Installed node_exporter and otelcol-contrib, wrote systemd services, enrolled the host, and enabled heartbeat."
"""
    return HttpResponse(script, content_type="text/plain")
