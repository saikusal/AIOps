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
import csv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Tuple, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from io import BytesIO, StringIO
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
    AgentBehaviorVersion,
    ChatMessage,
    ChatSession,
    DiscoveredService,
    EnrollmentToken,
    ExecutionIntent,
    GenAIChatHistory,
    Incident,
    IncidentAlert,
    IncidentTimelineEvent,
    OperatorFeedback,
    RemediationOutcome,
    ReplayEvaluation,
    ReplayScenario,
    Runbook,
    SLAPolicy,
    ServicePrediction,
    Target,
    TargetComponent,
    TargetHeartbeat,
    TargetOnboardingRequest,
    TelemetryProfile,
)
from .predictions import score_components
from .sso import ensure_sso_user, get_sso_identity
from .tools.direct_action import handle_direct_action as direct_action_tool
from .tools.docs import build_docs_proxy_body
from .tools.general import handle_general_chat as general_chat_tool
from .tools.ai_generation import (
    analyze_change_risk_payload,
    explain_anomaly_payload,
    generate_runbook_payload,
    generate_timeline_narrative_payload,
)
from .tools.investigation import (
    build_investigation_context as build_investigation_context_tool,
    extract_investigation_scope as extract_investigation_scope_tool,
    find_investigation_incident as find_investigation_incident_tool,
    run_investigation_route as investigation_route_tool,
)
from .tools.prometheus import handle_prometheus_query as prometheus_query_tool
from .tools.router import classify_query as hybrid_classify_query
from .tools.sql import handle_sql as sql_tool
from .mcp_services import (
    applications_get_component_snapshot as applications_get_component_snapshot_service,
    applications_get_graph as applications_get_graph_service,
    applications_get_overview as applications_get_overview_service,
    incidents_get_summary as incidents_get_summary_service,
    incidents_get_timeline as incidents_get_timeline_service,
    logs_search as logs_search_service,
    metrics_query_raw as metrics_query_raw_service,
    metrics_query_service_overview as metrics_query_service_overview_service,
    runbooks_search as runbooks_search_service,
    traces_search as traces_search_service,
    source_read_traceback as source_read_traceback_service,
)
from .policy_engine import evaluate_execution_policy, record_execution_attempt
from .behavior_versions import current_behavior_version_payload
from .execution_safety import (
    action_signature as execution_action_signature,
    context_fingerprint as execution_context_fingerprint,
    frequency_limit_config,
    issue_approval_token,
    resolve_idempotency_key,
    sign_intent_payload,
    verify_approval_token,
)
from .remediation_ranking import rank_typed_action
from .replay_evaluation import build_replay_scores
from .multi_step_workflow import build_execution_workflow
from .typed_actions import (
    action_summary,
    command_from_typed_action,
    infer_typed_action,
    serialize_action_signature,
)
from better_profanity import profanity
import os

# ---------------- logging ----------------
logger = logging.getLogger("genai")


def _avg_boolean(field_name: str) -> models.Case:
    return models.Case(
        models.When(**{field_name: True}, then=models.Value(1.0)),
        default=models.Value(0.0),
        output_field=models.FloatField(),
    )


def _json_safe(obj: Any) -> Any:
    """Recursively convert any non-JSON-serializable values (UUID, datetime, etc.) to strings
    so dicts can be safely stored in JSONField or returned via JsonResponse."""
    import uuid as _uuid
    from datetime import date, datetime as _datetime
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    if isinstance(obj, (_datetime, date)):
        return obj.isoformat()
    return obj


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
METRICS_API_URL = os.getenv("METRICS_API_URL") or os.getenv("PROMETHEUS_URL")
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

# Source-reader MCP tool configuration
# MCP_SOURCE_PATH_FROM=/app  ->  MCP_SOURCE_PATH_TO=/source/demo/app
_MCP_SOURCE_PATH_FROM = os.getenv("MCP_SOURCE_PATH_FROM", "/app")
_MCP_SOURCE_PATH_TO = os.getenv("MCP_SOURCE_PATH_TO", "/source/demo/app")
MCP_SOURCE_PATH_MAP: Dict[str, str] = (
    {_MCP_SOURCE_PATH_FROM: _MCP_SOURCE_PATH_TO}
    if _MCP_SOURCE_PATH_FROM and _MCP_SOURCE_PATH_TO
    else {}
)
MCP_SOURCE_ROOT = os.getenv("MCP_SOURCE_ROOT", "/source/demo")
AIOPS_PUBLIC_BASE_URL = os.getenv("AIOPS_PUBLIC_BASE_URL", "").strip()
AIOPS_PUBLIC_OTLP_GRPC_ENDPOINT = os.getenv("AIOPS_PUBLIC_OTLP_GRPC_ENDPOINT", "").strip()
AIOPS_OTELCOL_VERSION = os.getenv("AIOPS_OTELCOL_VERSION", "0.87.0")
AIOPS_NODE_EXPORTER_VERSION = os.getenv("AIOPS_NODE_EXPORTER_VERSION", "1.8.1")
CHAT_HISTORY_WINDOW = int(os.getenv("CHAT_HISTORY_WINDOW", "12"))
MCP_INTERNAL_TOKEN = (os.getenv("MCP_INTERNAL_TOKEN", "") or "").strip()
RECENT_ALERT_CACHE_KEY = "aiops_recent_alert_recommendations"
RECENT_ALERT_CACHE_TTL = 60 * 60 * 24
RECENT_ALERT_FRESHNESS_SECONDS = 10 * 60
MAX_RECENT_ALERTS = 20
INCIDENT_STATE_CACHE_PREFIX = "aiops_incident_state"
INCIDENT_STATE_CACHE_TTL = int(os.getenv("AIOPS_INCIDENT_STATE_CACHE_TTL", str(60 * 60 * 6)))
REMEDIATION_VARIANCE_HISTORY_LIMIT = int(os.getenv("AIOPS_REMEDIATION_VARIANCE_HISTORY_LIMIT", "20"))

# ---------------------------------------------------------------------------
# Prompt budget helpers
# Model hard limit: 8192 tokens. We reserve 2048 for output.
# At ~4 chars/token that leaves ~6144 * 4 = 24576 chars, but the full
# system message + JSON framing adds ~500 chars, so a safe per-prompt
# budget is ~5000 chars for all variable sections combined.
# Individual section caps below are set so the total stays inside that.
# ---------------------------------------------------------------------------
def _tail_for_prompt(text: str, max_chars: int, label: str = "") -> str:
    """Return the *tail* of `text` within `max_chars` (most recent lines)."""
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    snippet = text[-max_chars:]
    newline = snippet.find("\n")
    if newline > 0:
        snippet = snippet[newline + 1:]
    prefix = f"[{label} — truncated, showing last {max_chars} chars]\n" if label else ""
    return prefix + snippet


def _head_for_prompt(text: str, max_chars: int) -> str:
    """Return the *head* of `text` within `max_chars`."""
    if not text or len(text) <= max_chars:
        return text
    snippet = text[:max_chars]
    newline = snippet.rfind("\n")
    return snippet[:newline] if newline > 0 else snippet


def _errors_first_for_prompt(text: str, max_chars: int, tail_lines: int = 40) -> str:
    """Return ERROR/exception lines first, then the recent tail, within max_chars.

    When a command returns mixed log output (HTTP 200s interleaved with ERRORs),
    a naive tail() will drown out the error lines. This helper surfaces them first
    so the LLM cannot miss them.
    """
    if not text:
        return ""
    lines = text.splitlines()
    error_kw = (" error ", "error:", "exception", "traceback", "runtimeerror", "critical", "fatal", "db_write_failed", "db_query_failed", "status=503")
    error_lines = [ln for ln in lines if any(kw in ln.lower() for kw in error_kw)]
    tail = lines[-tail_lines:]
    seen: set = set()
    combined: list = []
    for ln in error_lines:
        if ln not in seen:
            combined.append(ln)
            seen.add(ln)
    if error_lines:
        combined.append("--- recent tail ---")
    for ln in tail:
        if ln not in seen:
            combined.append(ln)
            seen.add(ln)
    result = "\n".join(combined)
    if len(result) > max_chars:
        return result[:max_chars]
    return result


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
        _assign_sla_to_incident(incident)
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


def _recent_incident_memory(service_name: Optional[str], target_host: Optional[str], alert_name: Optional[str], limit: int = 8) -> Dict[str, Any]:
    service_key = str(service_name or "").strip()
    host_key = str(target_host or "").strip()
    alert_key = str(alert_name or "").strip()
    if not any([service_key, host_key, alert_key]):
        return {}

    incident = (
        Incident.objects.filter(
            models.Q(primary_service=service_key)
            | models.Q(target_host=host_key)
            | models.Q(title__icontains=alert_key)
        )
        .order_by("-updated_at")
        .first()
    )
    if not incident:
        return {}

    timeline = IncidentTimelineEvent.objects.filter(incident=incident).order_by("-created_at")[:limit]
    events: List[Dict[str, Any]] = []
    last_remediation_command = ""
    last_remediation_at = ""
    for event in reversed(list(timeline)):
        detail = str(event.detail or "")
        if event.event_type == "remediation_command_executed" and detail:
            last_remediation_command = detail
            last_remediation_at = event.created_at.isoformat() if event.created_at else ""
        events.append(
            {
                "event_type": event.event_type,
                "title": event.title,
                "detail": detail[:500],
                "created_at": event.created_at.isoformat() if event.created_at else "",
            }
        )

    return {
        "incident_key": str(incident.incident_key),
        "incident_status": incident.status,
        "incident_title": incident.title,
        "incident_summary": incident.summary,
        "last_remediation_command": last_remediation_command,
        "last_remediation_at": last_remediation_at,
        "recent_events": events,
    }


def _inventory_runtime_context(service_name: Optional[str]) -> Dict[str, Any]:
    if str(service_name or "").strip().lower() not in {"app-inventory", "inventory"}:
        return {}

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT sku, available_quantity, reserved_quantity, updated_at
                FROM demo_inventory
                ORDER BY sku
                """
            )
            inventory_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT sku, COUNT(*) AS orders_last_5m, COALESCE(SUM(quantity), 0) AS units_last_5m
                FROM demo_orders
                WHERE created_at >= NOW() - INTERVAL '5 minutes'
                GROUP BY sku
                ORDER BY sku
                """
            )
            recent_order_rows = cursor.fetchall()

        return {
            "inventory_rows": _rows_to_json_safe_lists(inventory_rows),
            "orders_last_5m_by_sku": _rows_to_json_safe_lists(recent_order_rows),
        }
    except Exception:
        logger.exception("Failed to load inventory runtime context")
        return {}


# ---------------------------------------------------------------------------
# SLA helpers
# ---------------------------------------------------------------------------

def _severity_to_priority(severity: str) -> str:
    sev = (severity or "warning").lower()
    if sev in ("critical",):
        return "P1"
    if sev in ("high", "error"):
        return "P2"
    if sev in ("warning", "warn"):
        return "P3"
    return "P4"


def _assign_sla_to_incident(incident: Incident) -> None:
    """Set priority + SLA due timestamps from the SLAPolicy table."""
    priority = _severity_to_priority(incident.severity)
    policy = SLAPolicy.objects.filter(priority=priority).first()
    if not policy:
        return
    base = incident.opened_at or timezone.now()
    incident.priority = priority
    incident.sla_response_due_at = base + timedelta(minutes=policy.response_minutes)
    incident.sla_resolution_due_at = base + timedelta(minutes=policy.resolution_minutes)
    incident.save(update_fields=["priority", "sla_response_due_at", "sla_resolution_due_at", "updated_at"])


def _compute_sla_status(incident: Incident) -> Dict[str, Any]:
    """Return a rich SLA status dict for the incident payload."""
    now = timezone.now()
    response_due = incident.sla_response_due_at
    resolution_due = incident.sla_resolution_due_at
    acked = incident.sla_response_acknowledged_at

    def _remaining_minutes(due):
        if not due:
            return None
        return round((due - now).total_seconds() / 60, 1)

    response_breached = bool(response_due and now > response_due and not acked)
    resolution_breached = bool(
        resolution_due and now > resolution_due and incident.status != "resolved"
    )
    return {
        "priority": incident.priority,
        "response_due_at": response_due.isoformat() if response_due else None,
        "resolution_due_at": resolution_due.isoformat() if resolution_due else None,
        "response_acknowledged_at": acked.isoformat() if acked else None,
        "response_remaining_minutes": _remaining_minutes(response_due),
        "resolution_remaining_minutes": _remaining_minutes(resolution_due),
        "response_breached": response_breached,
        "resolution_breached": resolution_breached,
        "breached": response_breached or resolution_breached,
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
        "priority": incident.priority,
        "sla": _compute_sla_status(incident),
    }


def _incident_timeline_payload(incident: Incident) -> Dict[str, Any]:
    linked_recommendation = None
    recent_entries = cache.get(RECENT_ALERT_CACHE_KEY) or []
    if isinstance(recent_entries, list):
        for entry in recent_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("incident_key") or "") == str(incident.incident_key) and _recent_alert_recommendation_is_fresh(entry):
                linked_recommendation = entry
                break
    latest_runbook = incident.runbooks.order_by("-created_at").first()
    latest_narrative_event = incident.timeline.filter(event_type="pir_generated").order_by("-created_at").first()
    latest_narrative = ""
    latest_narrative_created_at = None
    if latest_narrative_event:
        latest_narrative = (
            str((latest_narrative_event.payload or {}).get("narrative") or latest_narrative_event.detail or "").strip()
        )
        latest_narrative_created_at = latest_narrative_event.created_at.isoformat()

    return {
        **_incident_summary_payload(incident),
        "linked_recommendation": linked_recommendation,
        "latest_runbook": (
            {
                "runbook_id": latest_runbook.id,
                "title": latest_runbook.title,
                "content": latest_runbook.content,
                "created_at": latest_runbook.created_at.isoformat(),
            }
            if latest_runbook
            else None
        ),
        "latest_narrative": (
            {
                "narrative": latest_narrative,
                "created_at": latest_narrative_created_at,
            }
            if latest_narrative
            else None
        ),
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


def _download_filename(prefix: str, incident_key: str, extension: str) -> str:
    safe_key = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(incident_key or "incident")).strip("-") or "incident"
    return f"{prefix}-{safe_key}.{extension}"


def _csv_download_response(filename: str, rows: List[Dict[str, Any]]) -> HttpResponse:
    output = StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _extract_investigation_scope(question: str, body: Dict[str, Any]) -> Dict[str, str]:
    return extract_investigation_scope_tool(question, body)


def _find_investigation_incident(scope: Dict[str, str]) -> Optional[Incident]:
    return find_investigation_incident_tool(scope, incident_model=Incident)


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
    return build_investigation_context_tool(
        question,
        body,
        incident_model=Incident,
        build_application_overview=_build_application_overview,
        incident_timeline_payload=_incident_timeline_payload,
        get_dependency_context=_get_dependency_context,
        application_graph_payload=_application_graph_payload,
        fetch_elasticsearch_logs=_fetch_elasticsearch_logs,
        fetch_jaeger_traces=_fetch_jaeger_traces,
        fetch_metrics_query=_fetch_metrics_query,
    )


def _chat_json_response(session: Optional[ChatSession], payload: Dict[str, Any], status: int = 200) -> JsonResponse:
    if session:
        enriched_payload = {**payload, "session_id": str(session.session_id)}
        _record_chat_reply(session, enriched_payload)
        return JsonResponse(enriched_payload, status=status)
    return JsonResponse(payload, status=status)


def _is_authorized_mcp_request(request: HttpRequest) -> bool:
    if getattr(request, "user", None) and request.user.is_authenticated:
        return True
    supplied = (request.headers.get("X-MCP-Token") or "").strip()
    return bool(MCP_INTERNAL_TOKEN and supplied and supplied == MCP_INTERNAL_TOKEN)

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
        if isinstance(entry, dict) and entry.get("alert_id") == alert_id and _recent_alert_recommendation_is_fresh(entry):
            return entry
    return None


def _parse_recent_alert_timestamp(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone=ZoneInfo("UTC"))
    return parsed


def _recent_alert_recommendation_is_fresh(entry: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(entry, dict):
        return False
    observed_at = _parse_recent_alert_timestamp(entry.get("created_at") or entry.get("last_execution_at"))
    if not observed_at:
        return False
    return (timezone.now() - observed_at).total_seconds() <= RECENT_ALERT_FRESHNESS_SECONDS


def _extract_log_messages(log_payload: Dict[str, Any]) -> List[str]:
    hits = ((log_payload or {}).get("hits") or {}).get("hits") or []
    messages: List[str] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        source = hit.get("_source") if isinstance(hit.get("_source"), dict) else {}
        message = source.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(message.strip())
    return messages


def _component_aliases(component: str) -> List[str]:
    if not component:
        return []
    normalized = str(component).strip().lower()
    aliases = {normalized, normalized.replace("_", "-"), normalized.replace("-", "_")}
    if normalized.startswith("app-"):
        aliases.add(normalized.replace("app-", ""))
    if normalized == "db":
        aliases.update({"postgres", "postgresql", "database", "psycopg2", "sql", "pg_"})
    elif normalized == "gateway":
        aliases.update({"nginx", "proxy"})
    elif normalized == "frontend":
        aliases.update({"ui", "browser", "nginx"})
    elif normalized == "toxiproxy":
        aliases.update({"proxy", "toxiproxy"})
    return sorted(alias for alias in aliases if alias)


def _message_mentions_component(message: str, component: str) -> bool:
    haystack = (message or "").lower()
    return any(alias in haystack for alias in _component_aliases(component))


def _trace_contains_error(trace_payload: Dict[str, Any], *, db_related: bool = False) -> bool:
    error_tokens = (" error", " exception", " failed", " timeout", "connection refused", "operationalerror")
    db_tokens = ("postgres", "psycopg2", "database", "pg_", "sql", "db")
    for trace in (trace_payload or {}).get("data") or []:
        if not isinstance(trace, dict):
            continue
        processes = trace.get("processes") if isinstance(trace.get("processes"), dict) else {}
        for span in trace.get("spans") or []:
            if not isinstance(span, dict):
                continue
            process = processes.get(span.get("processID") or "", {}) if isinstance(processes, dict) else {}
            haystack = " ".join(
                part for part in [
                    str(span.get("operationName") or ""),
                    json.dumps(span.get("tags") or [], default=str),
                    json.dumps(span.get("logs") or [], default=str),
                    json.dumps(process.get("tags") or [], default=str) if isinstance(process, dict) else "",
                ]
                if part
            ).lower()
            if not any(token in haystack for token in error_tokens):
                continue
            if not db_related or any(token in haystack for token in db_tokens):
                return True
    return False


def _trace_contains_component_error(trace_payload: Dict[str, Any], component: str) -> bool:
    aliases = _component_aliases(component)
    if not aliases:
        return False
    error_tokens = (" error", " exception", " failed", " timeout", "connection refused", "operationalerror")
    for trace in (trace_payload or {}).get("data") or []:
        if not isinstance(trace, dict):
            continue
        processes = trace.get("processes") if isinstance(trace.get("processes"), dict) else {}
        for span in trace.get("spans") or []:
            if not isinstance(span, dict):
                continue
            process = processes.get(span.get("processID") or "", {}) if isinstance(processes, dict) else {}
            haystack = " ".join(
                part for part in [
                    str(span.get("operationName") or ""),
                    json.dumps(span.get("tags") or [], default=str),
                    json.dumps(span.get("logs") or [], default=str),
                    json.dumps(process.get("tags") or [], default=str) if isinstance(process, dict) else "",
                ]
                if part
            ).lower()
            if any(token in haystack for token in error_tokens) and any(alias in haystack for alias in aliases):
                return True
    return False


def _error_tokens() -> Tuple[str, ...]:
    return (
        " error",
        " exception",
        " failed",
        " timeout",
        "connection refused",
        "operationalerror",
        "runtimeerror",
        "insufficient",
        "available=0",
        "status=503",
        "db_write_failed",
        "db_query_failed",
        "fatal",
        "critical",
    )


def _extract_metric_result_count(query_result: Dict[str, Any]) -> int:
    if not isinstance(query_result, dict):
        return 0
    result = query_result.get("result")
    return len(result) if isinstance(result, list) else 0


def _extract_alert_states(alert_state_payload: Dict[str, Any]) -> List[str]:
    states: List[str] = []
    for item in (alert_state_payload or {}).get("result") or []:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric") if isinstance(item.get("metric"), dict) else {}
        state = str(metric.get("alertstate") or metric.get("state") or "").strip().lower()
        if state:
            states.append(state)
    return states


def _normalize_signature_text(value: str, *, limit: int = 180) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<ip>", text)
    text = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b", "<uuid>", text)
    text = re.sub(r"\b\d+\b", "<num>", text)
    text = re.sub(r"\s+", " ", text)
    return text[:limit]


def _collect_log_error_messages(log_payload: Dict[str, Any], *, limit: int = 3) -> List[str]:
    messages = _extract_log_messages(log_payload)
    tokens = _error_tokens()
    filtered = [msg for msg in messages if any(token in msg.lower() for token in tokens)]
    return [_normalize_signature_text(msg) for msg in filtered[:limit] if msg]


def _structured_evidence_from_context(
    context: Optional[Dict[str, Any]],
    *,
    alert_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = context or {}
    alert_payload = alert_payload or {}
    logger.info(f"[EVIDENCE] Starting evidence extraction for alert: {alert_payload.get('alert_name', 'unknown')}")
    metrics = context.get("metrics") if isinstance(context, dict) else {}
    alert_state = (metrics or {}).get("alert_state") if isinstance(metrics, dict) else {}
    custom_query = (metrics or {}).get("custom_query") if isinstance(metrics, dict) else {}
    custom_query_value = _extract_first_sample_value(custom_query or {})
    custom_query_result_count = _extract_metric_result_count(custom_query or {})
    alert_states = _extract_alert_states(alert_state or {})
    if alert_states:
        alert_firing: Optional[bool] = any(state == "firing" for state in alert_states)
    else:
        # ALERTS metric returned no samples — fall back to the inbound payload's status field
        payload_status = str(alert_payload.get("status") or "").strip().lower()
        if payload_status == "firing":
            alert_firing = True
        elif payload_status in ("resolved", "ok"):
            alert_firing = False
        else:
            alert_firing = None
    logger.debug(f"[EVIDENCE] Alert state from metric: {alert_states} | Resolved alert_firing: {alert_firing} (payload status: {alert_payload.get('status')})")

    dependency_graph = context.get("dependency_graph") if isinstance(context, dict) else {}
    blast_radius = (dependency_graph or {}).get("blast_radius") or []
    depends_on = (dependency_graph or {}).get("depends_on") or []
    target_component = str(
        context.get("target_host")
        or context.get("service_name")
        or alert_payload.get("target_host")
        or ""
    )
    primary_symptom = str(
        alert_payload.get("alert_name")
        or ((alert_payload.get("annotations") or {}).get("summary"))
        or ((alert_payload.get("annotations") or {}).get("description"))
        or context.get("alert_name")
        or "unknown_alert"
    )

    confirming_signals: List[str] = []
    contradicting_signals: List[str] = []
    missing_signals: List[str] = []
    dependency_hard_evidence: Dict[str, List[str]] = {}
    log_messages = _extract_log_messages(context.get("elasticsearch") or {})
    normalized_error_messages = _collect_log_error_messages(context.get("elasticsearch") or {})
    trace_service_error = _trace_contains_error(context.get("jaeger") or {}, db_related=False)
    trace_dependency_errors: Dict[str, bool] = {}

    logger.debug(f"[EVIDENCE] Alert firing state: {alert_firing}, Custom query value: {custom_query_value}")
    
    if alert_firing is True:
        confirming_signals.append("Alert state is still firing.")
    elif alert_firing is False:
        contradicting_signals.append("Alert state is no longer firing.")
    else:
        missing_signals.append("Alert state was not available from the metrics backend.")

    if custom_query_value is not None:
        if custom_query_value > 0.1:
            confirming_signals.append(f"Alert metric remains elevated at {custom_query_value:.2f}.")
        else:
            contradicting_signals.append(f"Alert metric is low at {custom_query_value:.2f}.")
    elif custom_query_result_count:
        confirming_signals.append("Custom metric query returned active samples.")
    elif alert_firing is True:
        # Alert state already confirmed firing — no separate custom query is required
        logger.debug("[EVIDENCE] Skipping custom metric missing signal — alert_firing already confirmed")
    else:
        missing_signals.append("No custom metric sample was available.")
    
    logger.debug(f"[EVIDENCE] Log error count: {len(normalized_error_messages)}, Trace service error: {trace_service_error}")

    if normalized_error_messages:
        confirming_signals.append("Recent logs contain active error messages.")
    else:
        contradicting_signals.append("Recent logs do not contain clear active error messages.")

    if trace_service_error:
        confirming_signals.append("Recent traces contain service failures.")
    else:
        contradicting_signals.append("Recent traces do not show service failures.")

    tokens = _error_tokens()
    for dependency in depends_on:
        if not dependency:
            continue
        dependency_evidence: List[str] = []
        # Hard evidence: log message explicitly names the dependency AND contains an error token
        if any(_message_mentions_component(msg, dependency) and any(token in msg.lower() for token in tokens) for msg in log_messages):
            dependency_evidence.append(f"Logs reference failures on dependency {dependency}.")
        dep_trace_error = _trace_contains_component_error(context.get("jaeger") or {}, dependency)
        if dep_trace_error:
            dependency_evidence.append(f"Traces show failing spans for dependency {dependency}.")
        # Soft evidence: service has active errors AND trace shows any span touching this dependency
        # This catches data-layer issues (e.g. insufficient quantity) where the DB is causal but logs
        # reference the business-level symptom rather than the dependency name directly
        if not dependency_evidence and normalized_error_messages:
            dep_aliases = _component_aliases(dependency)
            trace_calls_dep = any(
                any(alias in span_text for alias in dep_aliases)
                for trace in (context.get("jaeger") or {}).get("data") or []
                if isinstance(trace, dict)
                for span in (trace.get("spans") or [])
                if isinstance(span, dict)
                for span_text in [
                    " ".join(filter(None, [
                        str(span.get("operationName") or ""),
                        json.dumps(span.get("tags") or [], default=str),
                        json.dumps((trace.get("processes") or {}).get(span.get("processID") or "", {}).get("tags") or [], default=str),
                    ])).lower()
                ]
            )
            if trace_calls_dep:
                dependency_evidence.append(f"Service has active errors and traces show calls to dependency {dependency} — likely causal.")
            elif _message_mentions_component(" ".join(log_messages), dependency):
                # Dependency is mentioned in logs even without a combined error token — soft signal
                dependency_evidence.append(f"Logs reference dependency {dependency} in context of active errors.")
        trace_dependency_errors[str(dependency)] = dep_trace_error
        if dependency_evidence:
            dependency_hard_evidence[str(dependency)] = dependency_evidence
            confirming_signals.extend(dependency_evidence)
            logger.debug(f"[EVIDENCE] Dependency {dependency} evidence: {dependency_evidence}")
        elif blast_radius:
            missing_signals.append(f"Dependency {dependency} is in the topology path, but no direct or indirect evidence found.")

    best_dependency_target = next(iter(dependency_hard_evidence), "")
    signal_score = 0.0
    # alert_firing=True from ALERTS metric OR from payload status both earn full weight
    signal_score += 0.25 if alert_firing is True else 0.0
    # custom query is a bonus — only subtract if alert is NOT confirmed
    if custom_query_value is not None and custom_query_value > 0.1:
        signal_score += 0.20
    elif custom_query_value is not None and custom_query_value <= 0.1:
        # metric present but low — mild negative
        if alert_firing is not True:
            signal_score -= 0.05
    # No penalty for missing custom query when alert_firing is already confirmed
    signal_score += 0.20 if normalized_error_messages else 0.0
    signal_score += 0.20 if trace_service_error else 0.0
    signal_score += min(0.15, 0.05 * len(dependency_hard_evidence))
    signal_score -= 0.10 if alert_firing is False else 0.0
    signal_score -= 0.05 if not normalized_error_messages and alert_firing is not True else 0.0
    confidence_score = max(0.0, min(1.0, round(signal_score, 2)))
    
    logger.info(f"[EVIDENCE] Confidence score: {confidence_score:.2f} | Best dependency target: {best_dependency_target} | Signals: {len(confirming_signals)} confirming, {len(contradicting_signals)} contradicting, {len(missing_signals)} missing")

    recommended_action_mode = "observe"
    confidence_reason = "No strong failure evidence is present yet."
    if confidence_score >= 0.35:
        recommended_action_mode = "diagnose"
        confidence_reason = "There is enough live evidence to continue diagnostic investigation."
    if best_dependency_target:
        confidence_reason = f"Direct evidence points to downstream component {best_dependency_target}."

    return {
        "schema_version": "structured-evidence-v1",
        "primary_symptom": primary_symptom,
        "target_component": target_component,
        "service_name": context.get("service_name") or alert_payload.get("service_name") or "",
        "target_host": context.get("target_host") or alert_payload.get("target_host") or "",
        "candidate_dependencies": [str(item) for item in depends_on if item],
        "blast_radius": [str(item) for item in blast_radius if item],
        "signals": {
            "confirming": confirming_signals,
            "contradicting": contradicting_signals,
            "missing": missing_signals,
        },
        "observations": {
            "alert_states": alert_states,
            "alert_firing": alert_firing,
            "custom_query_value": custom_query_value,
            "custom_query_result_count": custom_query_result_count,
            "log_error_count": len(normalized_error_messages),
            "log_error_examples": normalized_error_messages,
            "trace_service_error": trace_service_error,
            "trace_dependency_errors": trace_dependency_errors,
        },
        "dependency_hard_evidence": dependency_hard_evidence,
        "best_dependency_target": best_dependency_target,
        "confidence_score": confidence_score,
        "confidence_reason": confidence_reason,
        "recommended_action_mode": recommended_action_mode,
        "error_signature": hashlib.sha256(
            json.dumps(
                {
                    "logs": normalized_error_messages,
                    "trace_service_error": trace_service_error,
                    "trace_dependency_errors": trace_dependency_errors,
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:16],
    }


def _format_structured_evidence_for_prompt(evidence: Dict[str, Any], max_chars: int = 1200) -> str:
    if not isinstance(evidence, dict) or not evidence:
        return "{}"
    prompt_safe = {
        "primary_symptom": evidence.get("primary_symptom"),
        "target_component": evidence.get("target_component"),
        "candidate_dependencies": evidence.get("candidate_dependencies") or [],
        "signals": evidence.get("signals") or {},
        "observations": evidence.get("observations") or {},
        "confidence_score": evidence.get("confidence_score"),
        "confidence_reason": evidence.get("confidence_reason"),
        "recommended_action_mode": evidence.get("recommended_action_mode"),
    }
    return _head_for_prompt(json.dumps(prompt_safe, indent=2, default=str), max_chars)


def _assess_recommendation_evidence(context: Dict[str, Any]) -> Dict[str, Any]:
    evidence = _structured_evidence_from_context(context)
    service_hard_evidence = list((evidence.get("signals") or {}).get("confirming") or [])
    dependency_hard_evidence = evidence.get("dependency_hard_evidence") or {}
    missing_evidence = list((evidence.get("signals") or {}).get("missing") or [])
    best_dependency_target = evidence.get("best_dependency_target") or ""
    safe_action = evidence.get("recommended_action_mode") or "observe"
    hard_evidence = service_hard_evidence[:]
    for dependency_evidence in dependency_hard_evidence.values():
        hard_evidence.extend(dependency_evidence)

    return {
        "safe_action": safe_action,
        "confidence_reason": evidence.get("confidence_reason") or "",
        "confidence_score": evidence.get("confidence_score") or 0.0,
        "target_component": evidence.get("target_component") or "",
        "service_hard_evidence": service_hard_evidence,
        "dependency_hard_evidence": dependency_hard_evidence,
        "best_dependency_target": best_dependency_target,
        "hard_evidence": hard_evidence,
        "missing_evidence": missing_evidence,
        "allow_dependency_pivot": bool(best_dependency_target),
        "structured_evidence": evidence,
    }


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
    evidence_assessment = _assess_recommendation_evidence(context)
    fallback_target = fallback_target_host or service_name or target_host
    best_dependency_target = evidence_assessment.get("best_dependency_target") or ""

    if suspected_dependency and best_dependency_target and best_dependency_target != fallback_target and evidence_assessment.get("allow_dependency_pivot"):
        target_host = str(best_dependency_target)
        why = why or f"Direct evidence points to downstream component {best_dependency_target}, so the next diagnostic should pivot there."
        if not diagnostic_command or diagnostic_command.startswith("tail ") or "/var/log/demo/" in diagnostic_command:
            diagnostic_command = _default_diagnostic_for_target(target_host)
    elif suspected_dependency and (dependency_graph.get("depends_on") or []):
        target_host = fallback_target
        target_type = "application_container" if str(target_host).startswith("app-") else "service"
        why = why or "A downstream dependency may be involved, but there is no direct evidence yet. Verify the impacted component first before pivoting."
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
        default=bool(diagnostic_command and target_host and evidence_assessment.get("safe_action") != "observe"),
    )

    return {
        "summary": summary,
        "why": why,
        "target_host": target_host,
        "target_type": target_type,
        "diagnostic_command": diagnostic_command,
        "should_execute": should_execute,
        "decision_policy": evidence_assessment.get("safe_action") or "diagnose",
        "confidence_reason": evidence_assessment.get("confidence_reason") or "",
        "evidence_assessment": evidence_assessment,
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


def _policy_status_code(policy_decision: Dict[str, Any]) -> int:
    blocked_reasons = policy_decision.get("blocked_reasons") or []
    transient_block = any("cooldown" in str(reason).lower() or "retry limit" in str(reason).lower() for reason in blocked_reasons)
    return 429 if transient_block else 403


def _get_or_create_behavior_version() -> Optional[AgentBehaviorVersion]:
    payload = current_behavior_version_payload()
    defaults = {
        "prompt_version": payload.get("prompt_version", ""),
        "policy_version": payload.get("policy_version", ""),
        "model_version": payload.get("model_version", ""),
        "evidence_rules_version": payload.get("evidence_rules_version", ""),
        "ranking_version": payload.get("ranking_version", ""),
        "metadata_json": payload.get("metadata_json") or {},
        "is_active": True,
    }
    behavior, _ = AgentBehaviorVersion.objects.get_or_create(
        name=payload.get("name", "default"),
        defaults=defaults,
    )
    changed = False
    for field, value in defaults.items():
        if getattr(behavior, field) != value:
            setattr(behavior, field, value)
            changed = True
    if changed:
        behavior.save()
    return behavior


def _check_service_execution_frequency(service: str) -> Dict[str, Any]:
    service_name = (service or "").strip()
    if not service_name:
        return {"allowed": True, "count": 0, "max_frequency": None, "window_seconds": None}
    config = frequency_limit_config()
    cutoff = timezone.now() - timedelta(seconds=config["window_seconds"])
    count = ExecutionIntent.objects.filter(
        service=service_name,
        created_at__gte=cutoff,
    ).exclude(status__in=["blocked", "expired"]).count()
    allowed = count < config["max_frequency"]
    reason = "" if allowed else f"Execution frequency limit reached for service '{service_name}'."
    return {
        "allowed": allowed,
        "count": count,
        "max_frequency": config["max_frequency"],
        "window_seconds": config["window_seconds"],
        "reason": reason,
    }


def _prepare_execution_intent(
    *,
    session: Optional[ChatSession],
    user: Any,
    incident: Optional[Incident],
    execution_type: str,
    command: str,
    typed_action: Dict[str, Any],
    target_host: str,
    service: str,
    environment: str,
    policy_decision: Dict[str, Any],
    ranking: Dict[str, Any],
    context_fingerprint: str,
    dry_run: bool,
    rollback_metadata: Dict[str, Any],
    idempotency_key: str,
) -> Tuple[ExecutionIntent, bool]:
    behavior_version = _get_or_create_behavior_version()
    defaults = {
        "session": session,
        "user": user if getattr(user, "is_authenticated", False) else None,
        "incident": incident,
        "behavior_version": behavior_version,
        "execution_type": execution_type,
        "action_type": str((typed_action or {}).get("action") or ""),
        "service": service,
        "environment": environment,
        "target_host": target_host,
        "command": command,
        "action_json": typed_action or {},
        "action_signature": execution_action_signature(typed_action),
        "request_signature": sign_intent_payload(
            {
                "execution_type": execution_type,
                "typed_action": typed_action or {},
                "target_host": target_host,
                "context_fingerprint": context_fingerprint,
            }
        ),
        "requires_approval": bool(policy_decision.get("requires_approval")),
        "dry_run": dry_run,
        "rollback_json": rollback_metadata or {},
        "policy_decision_json": policy_decision or {},
        "ranking_json": ranking or {},
        "context_fingerprint": context_fingerprint,
        "status": "dry_run" if dry_run else "planned",
    }
    intent, created = ExecutionIntent.objects.get_or_create(idempotency_key=idempotency_key, defaults=defaults)
    if not created:
        return intent, True
    return intent, False


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
    evidence_assessment = _assess_recommendation_evidence(context or {})
    current_target = str((context or {}).get("target_host") or service_name or "")

    candidate_service = service_name
    if "toxiproxy" in context_blob or "connection to server at \"toxiproxy\"" in context_blob:
        candidate_service = "toxiproxy"
    elif service_name in ("app-orders", "app-inventory", "app-billing", "gateway", "frontend"):
        candidate_service = service_name
    elif "db" in depends_on or "postgres" in context_blob or "database" in context_blob:
        candidate_service = "db"

    analysis_blob = json.dumps(analysis_sections or {}, default=str).lower()

    # If the LLM generated a SQL command (derived from live source context), route it
    # to db-agent which has psql on its allowlist. Detect both bare SQL DML and
    # fully-formed psql CLI commands.
    existing_cmd = (analysis_sections.get("remediation_command") or "").strip()
    # If the LLM explicitly returned no command (e.g. "can't fix safely"), honour
    # that decision — don't fall through and invent a docker restart.
    if not existing_cmd:
        analysis_sections["remediation_typed_action"] = {}
        return analysis_sections
    _sql_dml_prefixes = ("psql ", "update ", "insert ", "delete ", "select ")
    if any(existing_cmd.lower().startswith(p) for p in _sql_dml_prefixes):
        # Bare SQL DML (UPDATE/INSERT...) needs wrapping in a psql call.
        if not existing_cmd.lower().startswith("psql "):
            safe_sql = existing_cmd.replace('"', '\"')
            existing_cmd = f'psql -h db -U {DB_USER} -d {DB_NAME} -c "{safe_sql}"'
            analysis_sections["remediation_command"] = existing_cmd
        analysis_sections["remediation_target_host"] = "db"
        analysis_sections["remediation_requires_approval"] = True
        analysis_sections["remediation_typed_action"] = infer_typed_action(
            command=analysis_sections["remediation_command"],
            target_host="db",
            why=str(analysis_sections.get("remediation_why") or "").strip(),
            requires_approval=True,
            service="db",
        )
        return analysis_sections

    if candidate_service and candidate_service not in {service_name, current_target}:
        component_text_evidence = any(
            token in analysis_blob
            for token in _component_aliases(candidate_service)
        )
        dependency_hard_evidence = evidence_assessment.get("dependency_hard_evidence") or {}
        if candidate_service not in dependency_hard_evidence and not component_text_evidence:
            analysis_sections["remediation_command"] = ""
            analysis_sections["remediation_target_host"] = ""
            analysis_sections["remediation_why"] = (
                analysis_sections.get("remediation_why")
                or f"Remediation for {candidate_service} was withheld because the current evidence does not directly confirm failure on that component."
            )
            analysis_sections["remediation_requires_approval"] = False
            analysis_sections["remediation_typed_action"] = {}
            return analysis_sections

    container_name = RESTARTABLE_CONTAINER_NAMES.get(candidate_service)
    if not container_name:
        analysis_sections["remediation_command"] = ""
        analysis_sections["remediation_target_host"] = ""
        analysis_sections["remediation_why"] = analysis_sections.get("remediation_why") or ""
        analysis_sections["remediation_requires_approval"] = False
        analysis_sections["remediation_typed_action"] = {}
        return analysis_sections

    analysis_sections["remediation_command"] = f"docker restart {container_name}"
    analysis_sections["remediation_target_host"] = "control-agent"
    analysis_sections["remediation_why"] = (
        analysis_sections.get("remediation_why")
        or f"Restart the {candidate_service} container through the control agent to attempt recovery of the affected service path."
    )
    analysis_sections["remediation_service"] = candidate_service
    analysis_sections["remediation_requires_approval"] = True
    analysis_sections["remediation_typed_action"] = infer_typed_action(
        command=analysis_sections["remediation_command"],
        target_host="control-agent",
        why=str(analysis_sections.get("remediation_why") or "").strip(),
        requires_approval=True,
        service=candidate_service,
    )
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

def _fetch_metrics_alert_state(alert_name: str, target_host: Optional[str]) -> Dict[str, Any]:
    if not METRICS_API_URL or not alert_name:
        return {}
    selectors = [f'alertname="{alert_name}"']
    if target_host:
        selectors.append(f'instance=~"{target_host}(:.*)?"')
    query = f'ALERTS{{{",".join(selectors)}}}'
    cache_id = f"alert:{query}"

    def _do_fetch():
        session = get_http_session("victoriametrics")
        response = session.get(
            f"{METRICS_API_URL}/api/v1/query",
            params={"query": query},
            timeout=(3, 10),
        )
        response.raise_for_status()
        return response.json().get("data", {})

    return metadata_cache_get_or_fetch("prom_alert", cache_id, _do_fetch, ttl=30, backend="victoriametrics")

def _fetch_metrics_query(query: str) -> Dict[str, Any]:
    if not METRICS_API_URL or not query:
        return {}

    def _do_fetch(q: str) -> Dict[str, Any]:
        session = get_http_session("victoriametrics")
        response = session.get(
            f"{METRICS_API_URL}/api/v1/query",
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
    metrics_query = alert_payload.get("prometheus_query") or alert_payload.get("metrics_query")
    dependency_context = _get_dependency_context(service_name or target_host)
    recent_incident_memory = _recent_incident_memory(service_name, target_host, alert_name)
    inventory_runtime = _inventory_runtime_context(service_name)

    return {
        "alert_name": alert_name,
        "target_host": target_host,
        "service_name": service_name,
        "dependency_graph": dependency_context,
        "recent_incident_memory": recent_incident_memory,
        "inventory_runtime": inventory_runtime,
        "metrics": {
            "alert_state": _fetch_metrics_alert_state(alert_name, target_host),
            "custom_query": _fetch_metrics_query(metrics_query) if metrics_query else {},
        },
        "elasticsearch": _fetch_elasticsearch_logs(target_host, query_text),
        "jaeger": _fetch_jaeger_traces(service_name),
    }


def _incident_state_cache_key(fingerprint: str) -> str:
    return f"{INCIDENT_STATE_CACHE_PREFIX}:{fingerprint}"


def _build_incident_state_fingerprint(
    alert_payload: Optional[Dict[str, Any]],
    context: Optional[Dict[str, Any]],
    structured_evidence: Optional[Dict[str, Any]],
) -> str:
    alert_payload = alert_payload or {}
    context = context or {}
    structured_evidence = structured_evidence or {}
    observations = structured_evidence.get("observations") if isinstance(structured_evidence, dict) else {}
    dependency_graph = context.get("dependency_graph") if isinstance(context, dict) else {}
    linked_recommendation = context.get("linked_recommendation") if isinstance(context, dict) else {}
    signature_payload = {
        "alert_name": alert_payload.get("alert_name") or context.get("alert_name") or "",
        "status": alert_payload.get("status") or "firing",
        "target_host": context.get("target_host") or alert_payload.get("target_host") or "",
        "service_name": context.get("service_name") or alert_payload.get("service_name") or "",
        "candidate_dependencies": sorted(structured_evidence.get("candidate_dependencies") or []),
        "best_dependency_target": structured_evidence.get("best_dependency_target") or "",
        "blast_radius": sorted((dependency_graph or {}).get("blast_radius") or []),
        "alert_firing": observations.get("alert_firing"),
        "custom_query_value": round(float(observations.get("custom_query_value") or 0.0), 2) if observations.get("custom_query_value") is not None else None,
        "log_error_examples": observations.get("log_error_examples") or [],
        "trace_service_error": observations.get("trace_service_error"),
        "trace_dependency_errors": observations.get("trace_dependency_errors") or {},
        "prior_remediation_command": (linked_recommendation or {}).get("remediation_command") or "",
        "error_signature": structured_evidence.get("error_signature") or "",
    }
    fingerprint_source = json.dumps(signature_payload, sort_keys=True, default=str)
    fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
    logger.info(f"[FINGERPRINT] Generated: {fingerprint[:16]}... for alert {alert_payload.get('alert_name')} on {context.get('target_host')}")
    return fingerprint


def _get_cached_state_decision(fingerprint: str) -> Dict[str, Any]:
    cached = cache.get(_incident_state_cache_key(fingerprint))
    if isinstance(cached, dict):
        logger.info(f"[CACHE] HIT for fingerprint {fingerprint[:16]}... | Stored decision: {cached.get('remediation_command', 'N/A')}")
        return cached
    else:
        logger.info(f"[CACHE] MISS for fingerprint {fingerprint[:16]}...")
        return {}


def _store_cached_state_decision(fingerprint: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    existing = _get_cached_state_decision(fingerprint)
    merged = {
        **existing,
        **(updates or {}),
        "fingerprint": fingerprint,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    cache.set(_incident_state_cache_key(fingerprint), merged, INCIDENT_STATE_CACHE_TTL)
    logger.info(f"[CACHE] STORED for fingerprint {fingerprint[:16]}... | TTL: {INCIDENT_STATE_CACHE_TTL}s | Command: {merged.get('remediation_command', 'N/A')}")
    return merged


def _remediation_decision_payload(analysis_sections: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(analysis_sections, dict):
        return {}
    typed_action = analysis_sections.get("remediation_typed_action")
    if not isinstance(typed_action, dict):
        typed_action = infer_typed_action(
            command=str(analysis_sections.get("remediation_command") or "").strip(),
            target_host=str(analysis_sections.get("remediation_target_host") or "").strip(),
            why=str(analysis_sections.get("remediation_why") or "").strip(),
            requires_approval=_to_bool(analysis_sections.get("remediation_requires_approval"), default=False),
            service=str(analysis_sections.get("remediation_service") or "").strip(),
        )
    return {
        "command": str(analysis_sections.get("remediation_command") or "").strip(),
        "target_host": str(analysis_sections.get("remediation_target_host") or "").strip(),
        "why": str(analysis_sections.get("remediation_why") or "").strip(),
        "requires_approval": _to_bool(analysis_sections.get("remediation_requires_approval"), default=False),
        "typed_action": typed_action,
    }


def _detect_remediation_variance(previous: Dict[str, Any], current: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return None
    previous_command = str(previous.get("command") or "").strip()
    current_command = str(current.get("command") or "").strip()
    if not previous_command or not current_command:
        return None
    previous_target = str(previous.get("target_host") or "").strip()
    current_target = str(current.get("target_host") or "").strip()
    previous_signature = serialize_action_signature(previous.get("typed_action")) or json.dumps({"command": previous_command, "target_host": previous_target}, sort_keys=True)
    current_signature = serialize_action_signature(current.get("typed_action")) or json.dumps({"command": current_command, "target_host": current_target}, sort_keys=True)
    if previous_signature == current_signature:
        logger.debug(f"[VARIANCE] No variance detected: same command for same state")
        return None
    logger.warning(f"[VARIANCE] DETECTED! Previous: {previous_command} → Current: {current_command}")
    return {
        "detected": True,
        "previous": previous,
        "current": current,
    }


def _evidence_delta(previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    previous_signals = previous.get("signals") if isinstance(previous, dict) else {}
    current_signals = current.get("signals") if isinstance(current, dict) else {}
    previous_confirming = set(previous_signals.get("confirming") or [])
    current_confirming = set(current_signals.get("confirming") or [])
    previous_contradicting = set(previous_signals.get("contradicting") or [])
    current_contradicting = set(current_signals.get("contradicting") or [])
    return {
        "new_confirming": sorted(current_confirming - previous_confirming),
        "cleared_confirming": sorted(previous_confirming - current_confirming),
        "new_contradicting": sorted(current_contradicting - previous_contradicting),
        "cleared_contradicting": sorted(previous_contradicting - current_contradicting),
    }


def _record_remediation_variance(
    *,
    incident: Optional[Incident],
    fingerprint: str,
    variance: Dict[str, Any],
    structured_evidence: Optional[Dict[str, Any]] = None,
) -> None:
    if not variance:
        return
    payload = {
        "fingerprint": fingerprint,
        "variance": variance,
        "evidence_delta": _evidence_delta(
            ((variance.get("previous") or {}).get("structured_evidence") or {}),
            structured_evidence or {},
        ),
        "structured_evidence": structured_evidence or {},
    }
    logger.warning(
        "Remediation variance detected fingerprint=%s previous=%s current=%s",
        fingerprint[:12],
        (variance.get("previous") or {}).get("command"),
        (variance.get("current") or {}).get("command"),
    )
    if incident:
        IncidentTimelineEvent.objects.create(
            incident=incident,
            event_type="remediation_variance_detected",
            title="Remediation recommendation changed for matching incident state",
            detail=(variance.get("current") or {}).get("command") or "",
            payload=payload,
        )


def _build_contradiction_assessment(structured_evidence: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    structured_evidence = structured_evidence or {}
    signals = structured_evidence.get("signals") if isinstance(structured_evidence, dict) else {}
    confirming = [str(item) for item in (signals.get("confirming") or []) if item]
    contradicting = [str(item) for item in (signals.get("contradicting") or []) if item]
    confidence = float(structured_evidence.get("confidence_score") or 0.0)
    total = len(confirming) + len(contradicting)
    contradiction_ratio = round(len(contradicting) / total, 4) if total else 0.0
    severity = "low"
    if contradicting and (len(contradicting) >= len(confirming) or confidence < 0.35):
        severity = "high"
    elif contradicting:
        severity = "medium"
    reasons: List[str] = []
    if contradicting:
        reasons.append(f"Found {len(contradicting)} contradictory signal(s).")
    if confidence < 0.35:
        reasons.append("Overall evidence confidence is low.")
    if len(contradicting) >= len(confirming) and contradicting:
        reasons.append("Contradictory evidence is equal to or stronger than confirming evidence.")
    return {
        "severity": severity,
        "contradiction_ratio": contradiction_ratio,
        "confirming_count": len(confirming),
        "contradicting_count": len(contradicting),
        "confidence_score": confidence,
        "should_prefer_observe": severity == "high",
        "reasons": reasons,
        "contradicting_signals": contradicting[:6],
    }


def _command_looks_like_restart(command: str) -> bool:
    normalized = str(command or "").strip().lower()
    if not normalized:
        return False
    restart_markers = (
        "restart",
        "reboot",
        "rollout restart",
        "docker restart",
        "systemctl restart",
        "kubectl rollout restart",
    )
    return any(marker in normalized for marker in restart_markers)


def _historical_outcome_learning_snapshot(
    *,
    service: str = "",
    environment: str = "",
    action_type: str = "",
    context_fingerprint: str = "",
) -> Dict[str, Any]:
    queryset = RemediationOutcome.objects.all()
    if service:
        queryset = queryset.filter(service=service)
    if environment:
        queryset = queryset.filter(environment=environment)
    if action_type:
        queryset = queryset.filter(action_type=action_type)
    if context_fingerprint:
        queryset = queryset.filter(context_fingerprint=context_fingerprint)

    summary = queryset.aggregate(
        total=models.Count("id"),
        success_rate=models.Avg(_avg_boolean("success")),
        avg_ttr=models.Avg("time_to_recovery_seconds"),
        override_rate=models.Avg(_avg_boolean("operator_override")),
    )
    by_action = list(
        queryset.values("action_type")
        .annotate(
            total=models.Count("id"),
            success_rate=models.Avg(_avg_boolean("success")),
            avg_ttr=models.Avg("time_to_recovery_seconds"),
            override_rate=models.Avg(_avg_boolean("operator_override")),
        )
        .order_by("-total", "-success_rate")[:6]
    )
    recent = list(
        queryset.values(
            "service",
            "environment",
            "action_type",
            "success",
            "verification_status",
            "created_at",
            "metadata_json",
        ).order_by("-created_at")[:5]
    )
    return {
        "filters": {
            "service": service,
            "environment": environment,
            "action_type": action_type,
            "context_fingerprint": context_fingerprint,
        },
        "summary": {
            "total": int(summary.get("total") or 0),
            "success_rate": round(float(summary.get("success_rate") or 0.0), 4),
            "avg_time_to_recovery_seconds": summary.get("avg_ttr"),
            "operator_override_rate": round(float(summary.get("override_rate") or 0.0), 4),
        },
        "by_action": [
            {
                **row,
                "success_rate": round(float(row.get("success_rate") or 0.0), 4),
                "override_rate": round(float(row.get("override_rate") or 0.0), 4),
            }
            for row in by_action
        ],
        "recent_examples": recent,
    }


def _feedback_learning_summary(*, service: str = "", environment: str = "") -> Dict[str, Any]:
    queryset = OperatorFeedback.objects.all()
    if service:
        queryset = queryset.filter(service=service)
    if environment:
        queryset = queryset.filter(environment=environment)
    summary = queryset.aggregate(total=models.Count("id"))
    breakdown = list(
        queryset.values("feedback_type")
        .annotate(total=models.Count("id"))
        .order_by("feedback_type")
    )
    recent = list(
        queryset.values(
            "feedback_type",
            "outcome_quality",
            "service",
            "environment",
            "action_type",
            "notes",
            "created_at",
        ).order_by("-created_at")[:8]
    )
    return {
        "total": int(summary.get("total") or 0),
        "breakdown": breakdown,
        "recent": recent,
    }


def _preventive_action_candidates(component: Dict[str, Any]) -> List[Dict[str, Any]]:
    prediction = component.get("prediction") or {}
    features = prediction.get("features") or {}
    service = str(component.get("service") or "")
    suggestions: List[Dict[str, Any]] = []
    error_rate = float(features.get("error_rate") or 0.0)
    latency = float(features.get("latency_p95_seconds") or 0.0)
    active_alerts = int(features.get("active_alert_count") or 0)
    blast_radius = int(features.get("blast_radius_size") or 0)

    suggestions.append(
        {
            "action": "pre_incident_investigation",
            "summary": f"Open a pre-incident investigation for {service or 'the service'}.",
            "requires_approval": False,
            "reason": "Risk score is elevated before a confirmed incident.",
        }
    )
    if error_rate >= 0.05:
        suggestions.append(
            {
                "action": "check_error_budget",
                "summary": "Review error spikes and dependency failures before the service degrades further.",
                "requires_approval": False,
                "reason": f"Current error rate is elevated at {error_rate:.3f}/s.",
            }
        )
    if latency >= 1.0:
        suggestions.append(
            {
                "action": "scale_or_throttle_review",
                "summary": "Review scaling, saturation, or traffic throttling options.",
                "requires_approval": True,
                "reason": f"p95 latency is elevated at {latency:.2f}s.",
            }
        )
    if active_alerts == 0 and blast_radius >= 2:
        suggestions.append(
            {
                "action": "watch_incident",
                "summary": "Create a watch incident because blast radius is high even before alerts escalate.",
                "requires_approval": False,
                "reason": "High blast radius risk with no active alert yet can indicate an emerging issue.",
            }
        )
    return suggestions[:4]


def _apply_contradiction_guardrail(response_data: Dict[str, Any], structured_evidence: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(response_data, dict):
        return response_data
    assessment = _build_contradiction_assessment(structured_evidence)
    response_data["contradiction_assessment"] = assessment
    remediation_command = str(response_data.get("remediation_command") or "").strip()
    if remediation_command and assessment.get("should_prefer_observe") and _command_looks_like_restart(remediation_command):
        validation_steps = response_data.get("validation_steps") if isinstance(response_data.get("validation_steps"), list) else []
        validation_steps.insert(0, "Contradictory evidence is high; verify service health and dependency state before any restart.")
        response_data["validation_steps"] = validation_steps[:8]
        response_data["remediation_command"] = ""
        response_data["remediation_requires_approval"] = False
        response_data["remediation_typed_action"] = {}
        answer = str(response_data.get("answer") or "").strip()
        guardrail_note = "Restart recommendation was suppressed because contradictory evidence is high and confidence is low."
        response_data["answer"] = f"{answer}\n\n{guardrail_note}".strip()
    return response_data


def _issue_score_from_evidence(evidence: Dict[str, Any]) -> int:
    observations = evidence.get("observations") if isinstance(evidence, dict) else {}
    score = 0
    if observations.get("alert_firing") is True:
        score += 2
    if observations.get("custom_query_value") is not None and float(observations.get("custom_query_value") or 0.0) > 0.1:
        score += 1
    score += min(int(observations.get("log_error_count") or 0), 2)
    if observations.get("trace_service_error"):
        score += 1
    dependency_errors = observations.get("trace_dependency_errors") if isinstance(observations.get("trace_dependency_errors"), dict) else {}
    score += min(sum(1 for value in dependency_errors.values() if value), 2)
    return max(score, 0)


def _build_verification_alert_payload(source: Dict[str, Any], *, fallback_target_host: str = "", fallback_summary: str = "") -> Dict[str, Any]:
    labels = source.get("labels") if isinstance(source.get("labels"), dict) else {}
    annotations = source.get("annotations") if isinstance(source.get("annotations"), dict) else {}
    return {
        "alert_name": source.get("alert_name") or labels.get("alertname") or fallback_summary or "verification_follow_up",
        "status": source.get("status") or "firing",
        "target_host": source.get("target_host") or fallback_target_host,
        "service_name": source.get("service_name") or labels.get("service_name") or labels.get("service") or labels.get("job") or "",
        "labels": labels,
        "annotations": annotations,
        "prometheus_query": source.get("prometheus_query") or source.get("metrics_query") or "",
    }


def _run_post_action_verification(
    *,
    alert_payload: Dict[str, Any],
    baseline_context: Dict[str, Any],
    baseline_evidence: Dict[str, Any],
    execution_type: str,
    command: str,
    agent_success: bool,
) -> Dict[str, Any]:
    logger.info(f"[VERIFICATION] Starting post-action verification for command: {command[:60]}...")
    if not any((METRICS_API_URL, ELASTICSEARCH_URL, JAEGER_URL)):
        logger.warning(f"[VERIFICATION] Backends not configured, marking inconclusive")
        return {
            "status": "inconclusive",
            "reason": "Telemetry backends are not configured for post-action verification.",
        }

    verification_alert = _build_verification_alert_payload(
        alert_payload,
        fallback_target_host=str((baseline_context or {}).get("target_host") or ""),
        fallback_summary=str((baseline_evidence or {}).get("primary_symptom") or ""),
    )
    fresh_context = collect_alert_context(verification_alert)
    fresh_evidence = _structured_evidence_from_context(fresh_context, alert_payload=verification_alert)
    baseline_score = _issue_score_from_evidence(baseline_evidence or {})
    fresh_score = _issue_score_from_evidence(fresh_evidence or {})
    
    logger.debug(f"[VERIFICATION] Baseline issue score: {baseline_score}, Fresh score: {fresh_score}")

    if not agent_success:
        status = "execution_failed"
        reason = "The action did not complete successfully, so no improvement can be confirmed."
    elif fresh_score == 0 and (fresh_evidence.get("observations") or {}).get("alert_firing") is False:
        status = "resolved"
        reason = "Telemetry no longer shows an active alert or active failure indicators."
    elif fresh_score < baseline_score:
        status = "partially_improved"
        reason = "Failure indicators decreased after the action, but some signals remain."
    elif fresh_score > baseline_score:
        status = "worsened"
        reason = "Failure indicators increased after the action."
    elif fresh_score == baseline_score:
        status = "unchanged"
        reason = "Verification telemetry did not materially change after the action."
    else:
        status = "inconclusive"
        reason = "Verification telemetry was not sufficient to determine the outcome."
    
    logger.info(f"[VERIFICATION] Result: {status} | Baseline score: {baseline_score} → Fresh score: {fresh_score} | Reason: {reason}")

    return {
        "status": status,
        "reason": reason,
        "execution_type": execution_type,
        "command": command,
        "baseline_issue_score": baseline_score,
        "post_issue_score": fresh_score,
        "baseline_evidence": baseline_evidence or {},
        "post_evidence": fresh_evidence,
        "post_context_summary": {
            "alert_name": fresh_context.get("alert_name") or "",
            "target_host": fresh_context.get("target_host") or "",
            "service_name": fresh_context.get("service_name") or "",
        },
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

def _format_source_context_for_prompt(context: Optional[Dict[str, Any]], max_chars: int) -> str:
    """Format source_context from the investigation context for LLM prompt injection."""
    source_context = (context or {}).get("source_context") if isinstance(context, dict) else {}
    if not source_context or not isinstance(source_context, dict):
        return ""
    parts: List[str] = []
    for file_entry in (source_context.get("files") or [])[:3]:
        if not file_entry.get("readable"):
            continue
        parts.append(
            f"# {file_entry['container_path']} (function: {file_entry['function_name']}, line {file_entry['line_number']})\n"
            f"{file_entry['snippet']}"
        )
    for schema in (source_context.get("schema_files") or [])[:2]:
        parts.append(f"# Schema: {schema['path']}\n{schema['content']}")
    if not parts:
        return ""
    combined = "\n\n".join(parts)
    if len(combined) > max_chars:
        combined = combined[:max_chars]
    return f"\nSOURCE CODE CONTEXT (read from actual application code — use to generate precise remediation):\n---\n{combined}\n---\n"


def analyze_command_output(
    original_question: str,
    target_host: str,
    command_to_run: str,
    command_output: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    # If the command output contains a Python traceback, read the referenced
    # source files and SQL schema from the filesystem via the MCP source-reader.
    # This lets the LLM see the actual application code and generate a precise
    # remediation command (e.g. the correct psql UPDATE) instead of guessing.
    source_context_prompt = ""
    _traceback_markers = ('File "/', 'Traceback (most recent')
    if any(marker in command_output for marker in _traceback_markers):
        try:
            source_result = source_read_traceback_service(
                log_messages=[command_output],
                path_prefix_map=MCP_SOURCE_PATH_MAP,
                source_root=MCP_SOURCE_ROOT,
            )
            source_context_prompt = _format_source_context_for_prompt(
                {"source_context": source_result}, max_chars=1600
            )
            files_count = len((source_result or {}).get("files") or [])
            schema_count = len((source_result or {}).get("schema_files") or [])
            logger.info(
                "source_context via traceback: files=%s schema_files=%s readable_files=%s",
                files_count,
                schema_count,
                (source_result or {}).get("readable_files"),
            )
        except Exception:
            logger.exception("source_context traceback read failed")

    # Fallback: scan schema files (*.sql, *.prisma, *.dbml) from the mounted
    # source root whenever the traceback path didn't produce context.  This
    # ensures the LLM always sees exact table/column names (e.g. available_quantity)
    # even when command output contains no Python traceback.
    if not source_context_prompt and MCP_SOURCE_ROOT:
        try:
            from genai.mcp_services import _scan_schema_files as _scan_schemas
            schema_files = _scan_schemas(MCP_SOURCE_ROOT)
            if schema_files:
                source_context_prompt = _format_source_context_for_prompt(
                    {"source_context": {"files": [], "schema_files": schema_files}},
                    max_chars=1600,
                )
                logger.info(
                    "source_context via schema fallback: schema_files=%s sample=%s",
                    len(schema_files),
                    [item.get("path") for item in schema_files[:2]],
                )
        except Exception:
            logger.exception("source_context schema fallback failed")

    # Trim the context dict to essential fields only before serialising — the
    # full context (with elasticsearch hits, jaeger spans, etc.) easily exceeds
    # the prompt budget and buries the source code snippet we just fetched.
    _CONTEXT_KEEP_KEYS = (
        "target_host",
        "service_name",
        "linked_recommendation",
        "dependency_graph",
        "evidence_assessment",
        "recent_incident_memory",
        "inventory_runtime",
    )
    slim_context: Dict[str, Any] = {
        k: (context or {}).get(k)
        for k in _CONTEXT_KEEP_KEYS
        if (context or {}).get(k) is not None
    }
    evidence_source_alert = {}
    if isinstance((context or {}).get("linked_recommendation"), dict):
        linked = (context or {}).get("linked_recommendation") or {}
        evidence_source_alert = {
            "alert_name": linked.get("alert_name") or "",
            "status": linked.get("status") or "firing",
            "target_host": linked.get("target_host") or target_host,
            "service_name": (linked.get("labels") or {}).get("service") or (context or {}).get("service_name") or "",
            "labels": linked.get("labels") or {},
            "annotations": linked.get("annotations") or {},
        }
    structured_evidence = _structured_evidence_from_context(context or {}, alert_payload=evidence_source_alert)
    contradiction_assessment = _build_contradiction_assessment(structured_evidence)
    learning_environment = (
        str((((context or {}).get("linked_recommendation") or {}).get("labels") or {}).get("environment") or "")
        or str((((context or {}).get("linked_recommendation") or {}).get("labels") or {}).get("env") or "")
        or str((((context or {}).get("inventory_runtime") or {}).get("environment") or ""))
    )
    learning_snapshot = _historical_outcome_learning_snapshot(
        service=str((context or {}).get("service_name") or ""),
        environment=learning_environment.lower(),
    )

    analysis_prompt = (
        "You are an IT infrastructure expert. A diagnostic command was run on a remote server. "
        "Analyze the output and provide JSON only with keys: answer, root_cause, evidence, impact, resolution, remediation_steps, validation_steps, remediation_command, remediation_target_host, remediation_why, remediation_requires_approval, remediation_typed_action. "
        "remediation_steps and validation_steps must be arrays of concise action items. "
        "If a concrete remediation command is justified, remediation_command must be a single executable command suitable for the target troubleshooting agent. "
        "If no safe remediation command should be proposed yet, return an empty remediation_command string. "
        "remediation_requires_approval should be true whenever a remediation_command is returned. "
        "If you can infer a structured remediation, populate remediation_typed_action with keys: action, target, reason, requires_approval, validation_plan. "
        "You must explicitly consider contradictory evidence before recommending a restart or disruptive action. "
        "If contradictory evidence is high, prefer validation or observation over restart. "
        "CRITICAL: If the command output contains ERROR log lines, Python exceptions, Tracebacks, or lines containing 'db_write_failed', 'db_query_failed', 'status=503', or 'RuntimeError', those are PRIMARY evidence of the failure. "
        "You MUST analyze them — do NOT conclude the service is healthy if ERROR entries are present. "
        "If RECENT INCIDENT MEMORY is provided, compare the current evidence with prior diagnostics and prior remediation results. "
        "If the same failure pattern has recurred after a previous remediation temporarily resolved it, propose the next safe remediation based on the current runtime state rather than repeating stale reasoning. "
        "If SOURCE CODE CONTEXT is provided below, read it carefully: use the exact table names, column names, and logic from the source to write the precise remediation command. "
        "If the error reveals a data-constraint issue (e.g. depleted inventory, zero quantity), propose a targeted SQL fix using the exact table/column names visible in the source — NOT a container restart. "
        "Do not ask the operator to inspect logs manually. If the command output contains logs, extract the likely error, impact, and concrete next action directly.\n\n"
        f"Original Question: '{original_question[:300]}'\n"
        f"Target Server: {target_host}\n"
        f"Command Run: `{command_to_run[:300]}`\n"
        f"Structured Evidence: {_format_structured_evidence_for_prompt(structured_evidence, 900)}\n"
        f"Contradiction Assessment: {_head_for_prompt(json.dumps(contradiction_assessment, indent=2, default=str), 500)}\n"
        f"Historical Outcome Learning: {_head_for_prompt(json.dumps(learning_snapshot, indent=2, default=str), 700)}\n"
        f"Context: {_head_for_prompt(json.dumps(slim_context, indent=2, default=str), 600)}\n"
        f"{source_context_prompt}"
        f"Command Output:\n---\n{_errors_first_for_prompt(command_output, 1600)}\n---\n"
    )
    logger.info(f"[LLM] Sending analysis prompt to AIDE | Evidence confidence: {structured_evidence.get('confidence_score', 'N/A')} | Target: {target_host}")
    logger.debug(f"[LLM] Prompt (first 800 chars): {analysis_prompt[:800]}...")
    ok, status, body_text = query_aide_api(analysis_prompt)
    logger.info(f"[LLM] Response received | Status: {str(status)[:50] if status else 'None'}")
    logger.debug(f"[LLM] Response body (first 500 chars): {body_text[:500] if body_text else 'Empty'}")
    if not ok:
        logger.error(f"[LLM] API call failed: {status}")
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
            if not isinstance(response_data.get("remediation_typed_action"), dict) or not response_data.get("remediation_typed_action"):
                response_data["remediation_typed_action"] = infer_typed_action(
                    command=str(response_data.get("remediation_command") or "").strip(),
                    target_host=str(response_data.get("remediation_target_host") or "").strip(),
                    why=str(response_data.get("remediation_why") or "").strip(),
                    requires_approval=_to_bool(response_data.get("remediation_requires_approval"), default=False),
                    service=str(response_data.get("remediation_service") or "").strip(),
                )
            remediation_action = response_data.get("remediation_typed_action") or {}
            if remediation_action:
                ranking_environment = (
                    str((((context or {}).get("linked_recommendation") or {}).get("labels") or {}).get("environment") or "")
                    or str((((context or {}).get("linked_recommendation") or {}).get("labels") or {}).get("env") or "")
                    or str((((context or {}).get("inventory_runtime") or {}).get("environment") or ""))
                )
                response_data["remediation_ranking"] = rank_typed_action(
                    remediation_action,
                    service=str(response_data.get("remediation_service") or (context or {}).get("service_name") or ""),
                    environment=ranking_environment.lower(),
                    blast_radius_size=len((((context or {}).get("dependency_graph") or {}).get("blast_radius") or [])),
                )
            response_data["behavior_version"] = current_behavior_version_payload()
            response_data.setdefault("structured_evidence", structured_evidence)
            response_data.setdefault("historical_outcome_learning", learning_snapshot)
            response_data = _apply_contradiction_guardrail(response_data, structured_evidence)
            logger.info(f"[LLM] Parsed response | Recommended command: {remediation_command[:60] if remediation_command else 'NO REMEDIATION'} | Requires approval: {response_data.get('remediation_requires_approval')}")
        answer = response_data.get("answer") or _format_analysis_sections(response_data) or body_text
        return True, answer, response_data if isinstance(response_data, dict) else {}
    except json.JSONDecodeError as e:
        logger.error(f"[LLM] JSON decode error: {e}")
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
        f"APPLICATION SNAPSHOT:\n{_head_for_prompt(json.dumps(components, indent=2, default=str), 4000)}"
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
            misses[q] = _fetch_metrics_query(q)

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


@login_required
def remediation_learning_view(request: HttpRequest):
    service = str(request.GET.get("service") or "").strip()
    environment = str(request.GET.get("environment") or "").strip()
    action_type = str(request.GET.get("action_type") or "").strip()
    context_fingerprint = str(request.GET.get("context_fingerprint") or "").strip()
    payload = {
        "generated_at": timezone.now().isoformat(),
        "outcomes": _historical_outcome_learning_snapshot(
            service=service,
            environment=environment,
            action_type=action_type,
            context_fingerprint=context_fingerprint,
        ),
        "feedback": _feedback_learning_summary(service=service, environment=environment),
    }
    return JsonResponse(payload)


@login_required
def preventive_recommendations_view(request: HttpRequest):
    overview = _build_application_overview(include_ai=True, include_predictions=True)
    recommendations: List[Dict[str, Any]] = []
    for application in overview.get("results", []):
        for component in application.get("components", []):
            prediction = component.get("prediction") or {}
            risk_score = float(prediction.get("risk_score") or 0.0)
            if risk_score < 0.45:
                continue
            service = str(component.get("service") or "")
            recommendations.append(
                {
                    "application": application.get("application") or "",
                    "service": service,
                    "status": component.get("status") or "healthy",
                    "risk_score": round(risk_score, 4),
                    "prediction_status": prediction.get("prediction_status") or "low",
                    "explanation": prediction.get("explanation") or "",
                    "preventive_actions": _preventive_action_candidates(component),
                    "historical_learning": _historical_outcome_learning_snapshot(service=service),
                }
            )
    recommendations.sort(key=lambda item: item.get("risk_score") or 0.0, reverse=True)
    return JsonResponse(
        {
            "generated_at": timezone.now().isoformat(),
            "count": len(recommendations),
            "results": recommendations[:20],
        }
    )


@login_required
@csrf_exempt
def operator_feedback_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request method"}, status=405)
    try:
        body = json.loads(request.body or "{}")
    except Exception as exc:
        return JsonResponse({"error": "invalid_json", "detail": str(exc)}, status=400)

    feedback_type = str(body.get("feedback_type") or "").strip().lower()
    if feedback_type not in {"accepted", "rejected", "edited", "manual_fix"}:
        return JsonResponse({"error": "feedback_type must be accepted, rejected, edited, or manual_fix"}, status=400)
    outcome_quality = str(body.get("outcome_quality") or "unknown").strip().lower()
    if outcome_quality not in {"excellent", "good", "partial", "poor", "unknown"}:
        outcome_quality = "unknown"

    intent_id = str(body.get("execution_intent_id") or "").strip()
    incident_key = str(body.get("incident_key") or "").strip()
    execution_intent = ExecutionIntent.objects.filter(intent_id=intent_id).first() if intent_id else None
    incident = Incident.objects.filter(incident_key=incident_key).first() if incident_key else None
    if not execution_intent and not incident:
        return JsonResponse({"error": "execution_intent_id or incident_key is required"}, status=400)

    original_action = body.get("original_action") if isinstance(body.get("original_action"), dict) else ((execution_intent.action_json if execution_intent else {}) or {})
    submitted_action = body.get("submitted_action") if isinstance(body.get("submitted_action"), dict) else original_action
    service = str(body.get("service") or (execution_intent.service if execution_intent else "") or (incident.primary_service if incident else "")).strip()
    environment = str(body.get("environment") or (execution_intent.environment if execution_intent else "")).strip()
    action_type = str(body.get("action_type") or (submitted_action.get("action") if isinstance(submitted_action, dict) else "") or (execution_intent.action_type if execution_intent else "")).strip()
    context_fingerprint = str(body.get("context_fingerprint") or (execution_intent.context_fingerprint if execution_intent else "")).strip()
    notes = str(body.get("notes") or "").strip()

    feedback = OperatorFeedback.objects.create(
        execution_intent=execution_intent,
        incident=incident or (execution_intent.incident if execution_intent else None),
        user=request.user if getattr(request.user, "is_authenticated", False) else None,
        feedback_type=feedback_type,
        outcome_quality=outcome_quality,
        service=service,
        environment=environment,
        action_type=action_type,
        context_fingerprint=context_fingerprint,
        original_action_json=original_action,
        submitted_action_json=submitted_action,
        notes=notes,
        metadata_json={"behavior_version": current_behavior_version_payload()},
    )

    if execution_intent:
        latest_outcome = RemediationOutcome.objects.filter(execution_intent=execution_intent).order_by("-created_at").first()
        if latest_outcome:
            latest_outcome.operator_override = feedback_type in {"rejected", "edited", "manual_fix"}
            latest_meta = latest_outcome.metadata_json or {}
            latest_meta["operator_feedback"] = {
                "feedback_id": feedback.feedback_id,
                "feedback_type": feedback_type,
                "outcome_quality": outcome_quality,
                "submitted_action": submitted_action,
                "notes": notes,
                "created_by": getattr(request.user, "username", "") or getattr(request.user, "email", ""),
            }
            latest_outcome.metadata_json = latest_meta
            latest_outcome.save(update_fields=["operator_override", "metadata_json"])

    linked_incident = incident or (execution_intent.incident if execution_intent else None)
    if linked_incident:
        IncidentTimelineEvent.objects.create(
            incident=linked_incident,
            event_type="operator_feedback_recorded",
            title="Operator feedback recorded",
            detail=feedback_type,
            payload={
                "feedback_id": feedback.feedback_id,
                "feedback_type": feedback_type,
                "outcome_quality": outcome_quality,
                "original_action": original_action,
                "submitted_action": submitted_action,
                "notes": notes,
            },
        )

    return JsonResponse(
        {
            "status": "recorded",
            "feedback": {
                "feedback_id": feedback.feedback_id,
                "feedback_type": feedback.feedback_type,
                "outcome_quality": feedback.outcome_quality,
                "service": feedback.service,
                "environment": feedback.environment,
                "action_type": feedback.action_type,
                "created_at": feedback.created_at.isoformat(),
            },
            "learning": _historical_outcome_learning_snapshot(service=service, environment=environment),
        }
    )

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

def classify_query(query: str) -> str:
    return hybrid_classify_query(query, llm_query=query_aide_api, logger=logger)

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
    return direct_action_tool(prompt, llm_query=query_aide_api, logger=logger)


def handle_prometheus_query(prompt: str) -> Tuple[Optional[dict], dict, str, str]:
    return prometheus_query_tool(
        prompt,
        llm_query=query_aide_api,
        prometheus_url=METRICS_API_URL,
        logger=logger,
    )

def handle_sql(prompt: str) -> Tuple[Optional[dict], dict, str, str]:
    return sql_tool(
        prompt,
        llm_query=query_aide_api,
        get_full_schema_for_prompt=get_full_schema_for_prompt,
        target_table=TARGET_TABLE,
        extract_sql_from_markdown=_extract_sql_from_markdown,
        strip_after_stop_tokens=_strip_after_stop_tokens,
        ensure_select_prefix=_ensure_select_prefix,
        quote_text_literals=_quote_text_literals,
        prefer_ilike_for_strings=_prefer_ilike_for_strings,
        extract_selected_columns=_extract_selected_columns,
        suggest_visualization=suggest_visualization,
        rows_to_json_safe_lists=_rows_to_json_safe_lists,
        safe_preview_value=_safe_preview_value,
        history_model=GenAIChatHistory,
        db_connection=connection,
        forbidden_sql=FORBIDDEN_SQL,
        logger=logger,
    )

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
            response_data = investigation_route_tool(
                question,
                body,
                conversation_history,
                llm_query=query_aide_api,
                incident_model=Incident,
                build_application_overview=_build_application_overview,
                incident_timeline_payload=_incident_timeline_payload,
                get_dependency_context=_get_dependency_context,
                application_graph_payload=_application_graph_payload,
                fetch_elasticsearch_logs=_fetch_elasticsearch_logs,
                fetch_jaeger_traces=_fetch_jaeger_traces,
                fetch_metrics_query=_fetch_metrics_query,
                compute_incident_revenue_impact=_compute_incident_revenue_impact,
                logger=logger,
                chat_session=chat_session,
                user=request.user,
                source_path_map=MCP_SOURCE_PATH_MAP,
                source_root=MCP_SOURCE_ROOT,
            )
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
        proxy_body = build_docs_proxy_body(body, question, client_top_k, client_strict_docs)
        
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
        response_data = general_chat_tool(
            question,
            conversation_history,
            llm_query=query_aide_api,
            history_model=GenAIChatHistory,
            cache_store=simple_cache,
            logger=logger,
        )
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


def mcp_incident_summary_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    incident_key = (request.GET.get("incident_key") or "").strip()
    if not incident_key:
        return JsonResponse({"error": "incident_key is required"}, status=400)
    payload = incidents_get_summary_service(
        incident_key=incident_key,
        incident_model=Incident,
        incident_summary_payload=_incident_summary_payload,
    )
    if not payload:
        return JsonResponse({"error": "incident_not_found"}, status=404)
    return JsonResponse(payload)


def mcp_incident_timeline_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    incident_key = (request.GET.get("incident_key") or "").strip()
    if not incident_key:
        return JsonResponse({"error": "incident_key is required"}, status=400)
    payload = incidents_get_timeline_service(
        incident_key=incident_key,
        incident_model=Incident,
        incident_timeline_payload=_incident_timeline_payload,
    )
    if not payload:
        return JsonResponse({"error": "incident_not_found"}, status=404)
    return JsonResponse(payload)


def mcp_applications_overview_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    application = (request.GET.get("application") or "").strip()
    payload = applications_get_overview_service(
        build_application_overview=_build_application_overview,
        application=application,
    )
    return JsonResponse(payload)


def mcp_application_graph_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    application = (request.GET.get("application") or "").strip()
    if not application:
        return JsonResponse({"error": "application is required"}, status=400)
    payload = applications_get_graph_service(
        application=application,
        application_graph_payload=_application_graph_payload,
    )
    if not payload:
        return JsonResponse({"error": "application_not_found"}, status=404)
    return JsonResponse(payload)


def mcp_application_component_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    application = (request.GET.get("application") or "").strip()
    service = (request.GET.get("service") or "").strip()
    if not application or not service:
        return JsonResponse({"error": "application and service are required"}, status=400)
    payload = applications_get_component_snapshot_service(
        application=application,
        service=service,
        build_application_overview=_build_application_overview,
    )
    if not payload:
        return JsonResponse({"error": "component_not_found"}, status=404)
    return JsonResponse(payload)


def mcp_metrics_service_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    service_name = (request.GET.get("service_name") or "").strip()
    if not service_name:
        return JsonResponse({"error": "service_name is required"}, status=400)
    payload = metrics_query_service_overview_service(
        service_name=service_name,
        fetch_metrics_query=_fetch_metrics_query,
    )
    return JsonResponse(payload)


def mcp_metrics_query_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    query = (request.GET.get("query") or "").strip()
    if not query:
        return JsonResponse({"error": "query is required"}, status=400)
    payload = metrics_query_raw_service(
        query=query,
        fetch_metrics_query=_fetch_metrics_query,
    )
    return JsonResponse(payload)


def mcp_logs_search_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    target_host = (request.GET.get("target_host") or "").strip() or None
    query = (request.GET.get("query") or "").strip()
    if not target_host and not query:
        return JsonResponse({"error": "target_host or query is required"}, status=400)
    payload = logs_search_service(
        target_host=target_host,
        query=query,
        fetch_elasticsearch_logs=_fetch_elasticsearch_logs,
    )
    return JsonResponse(payload)


def mcp_traces_search_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    service_name = (request.GET.get("service_name") or "").strip() or None
    if not service_name:
        return JsonResponse({"error": "service_name is required"}, status=400)
    payload = traces_search_service(
        service_name=service_name,
        fetch_jaeger_traces=_fetch_jaeger_traces,
    )
    return JsonResponse(payload)


def mcp_runbooks_search_view(request: HttpRequest):
    if not _is_authorized_mcp_request(request):
        return JsonResponse({"error": "unauthorized"}, status=401)
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)
    incident_key = (request.GET.get("incident_key") or "").strip()
    query = (request.GET.get("query") or "").strip()
    if not incident_key and not query:
        return JsonResponse({"error": "incident_key or query is required"}, status=400)
    payload = runbooks_search_service(
        incident_key=incident_key,
        query=query,
        incident_model=Incident,
        runbook_model=Runbook,
    )
    return JsonResponse(payload)


@login_required
def investigations_dashboard_view(request: HttpRequest):
    return render(request, "genai/investigations_dashboard.html", {"active_nav": "investigations"})


@login_required
def investigations_recent_view(request: HttpRequest):
    runs = InvestigationRun.objects.select_related("incident", "session").prefetch_related("tool_invocations").all()[:25]
    results = []
    for run in runs:
        invocations = list(run.tool_invocations.all()[:10])
        results.append(
            {
                "run_id": str(run.run_id),
                "status": run.status,
                "question": run.question,
                "application": run.application,
                "service": run.service,
                "target_host": run.target_host,
                "incident_key": str(run.incident.incident_key) if run.incident else "",
                "session_id": str(run.session.session_id) if run.session else "",
                "tool_call_count": run.tool_invocations.count(),
                "updated_at": run.updated_at.isoformat(),
                "tool_calls": [
                    {
                        "server_name": item.server_name,
                        "tool_name": item.tool_name,
                        "status": item.status,
                        "latency_ms": item.latency_ms,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in invocations
                ],
            }
        )
    return JsonResponse({"count": len(results), "results": results})


@login_required
def operations_dashboard_view(request: HttpRequest):
    return render(request, "genai/operations_dashboard.html", {"active_nav": "operations"})


@login_required
def operations_summary_view(request: HttpRequest):
    recent_intents = list(
        ExecutionIntent.objects.select_related("incident", "behavior_version", "approved_by")
        .order_by("-created_at")[:20]
    )
    recent_evaluations = list(
        ReplayEvaluation.objects.select_related("scenario", "execution_intent")
        .order_by("-created_at")[:12]
    )
    behavior_versions = list(
        AgentBehaviorVersion.objects.order_by("-updated_at")[:10]
    )

    intent_status_counts = ExecutionIntent.objects.values("status").annotate(total=models.Count("id")).order_by("status")
    dry_run_count = ExecutionIntent.objects.filter(dry_run=True).count()
    approval_required_count = ExecutionIntent.objects.filter(requires_approval=True).count()
    outcomes_summary = RemediationOutcome.objects.aggregate(
        total=models.Count("id"),
        success_rate=models.Avg(_avg_boolean("success")),
        avg_ttr=models.Avg("time_to_recovery_seconds"),
    )
    evaluation_summary = ReplayEvaluation.objects.aggregate(
        avg_overall=models.Avg(models.F("scores_json__overall")),
        total=models.Count("id"),
    )
    feedback_summary = OperatorFeedback.objects.aggregate(total=models.Count("id"))
    feedback_breakdown = list(
        OperatorFeedback.objects.values("feedback_type")
        .annotate(total=models.Count("id"))
        .order_by("feedback_type")
    )
    top_ranked_services = (
        RemediationOutcome.objects.values("service")
        .annotate(
            total=models.Count("id"),
            success_rate=models.Avg(_avg_boolean("success")),
            avg_blast_radius=models.Avg("blast_radius_risk"),
        )
        .order_by("-success_rate", "-total")[:8]
    )

    results = {
        "generated_at": timezone.now().isoformat(),
        "totals": {
            "execution_intents": ExecutionIntent.objects.count(),
            "dry_runs": dry_run_count,
            "approval_required": approval_required_count,
            "replay_evaluations": ReplayEvaluation.objects.count(),
            "behavior_versions": AgentBehaviorVersion.objects.count(),
        },
        "status_breakdown": list(intent_status_counts),
        "outcomes": {
            "total": int(outcomes_summary.get("total") or 0),
            "success_rate": round(float(outcomes_summary.get("success_rate") or 0.0), 4),
            "avg_time_to_recovery_seconds": outcomes_summary.get("avg_ttr"),
        },
        "feedback": {
            "total": int(feedback_summary.get("total") or 0),
            "breakdown": feedback_breakdown,
        },
        "replay": {
            "total": int(evaluation_summary.get("total") or 0),
            "avg_overall_score": round(float(evaluation_summary.get("avg_overall") or 0.0), 4),
        },
        "recent_intents": [
            {
                "intent_id": item.intent_id,
                "status": item.status,
                "execution_type": item.execution_type,
                "action_type": item.action_type,
                "service": item.service,
                "environment": item.environment,
                "target_host": item.target_host,
                "dry_run": item.dry_run,
                "requires_approval": item.requires_approval,
                "ranking_score": (item.ranking_json or {}).get("score"),
                "verification_status": (item.verification_json or {}).get("status"),
                "incident_key": str(item.incident.incident_key) if item.incident else "",
                "behavior_name": item.behavior_version.name if item.behavior_version else "",
                "behavior_versions": {
                    "prompt_version": item.behavior_version.prompt_version if item.behavior_version else "",
                    "policy_version": item.behavior_version.policy_version if item.behavior_version else "",
                    "model_version": item.behavior_version.model_version if item.behavior_version else "",
                    "ranking_version": item.behavior_version.ranking_version if item.behavior_version else "",
                },
                "approved_by": getattr(item.approved_by, "username", "") if item.approved_by else "",
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in recent_intents
        ],
        "top_ranked_services": [
            {
                "service": item.get("service") or "unknown",
                "sample_size": int(item.get("total") or 0),
                "success_rate": round(float(item.get("success_rate") or 0.0), 4),
                "avg_blast_radius": round(float(item.get("avg_blast_radius") or 0.0), 4),
            }
            for item in top_ranked_services
        ],
        "recent_replay_results": [
            {
                "evaluation_id": item.evaluation_id,
                "scenario_id": item.scenario.scenario_id if item.scenario else "",
                "scenario_title": item.scenario.title if item.scenario else "",
                "status": item.status,
                "overall_score": (item.scores_json or {}).get("overall"),
                "correctness": (item.scores_json or {}).get("correctness"),
                "safety": (item.scores_json or {}).get("safety"),
                "resolution_rate": (item.scores_json or {}).get("resolution_rate"),
                "created_at": item.created_at.isoformat(),
            }
            for item in recent_evaluations
        ],
        "behavior_history": [
            {
                "behavior_id": item.behavior_id,
                "name": item.name,
                "prompt_version": item.prompt_version,
                "policy_version": item.policy_version,
                "model_version": item.model_version,
                "evidence_rules_version": item.evidence_rules_version,
                "ranking_version": item.ranking_version,
                "is_active": item.is_active,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in behavior_versions
        ],
        "recent_feedback": _feedback_learning_summary().get("recent") or [],
    }
    return JsonResponse(results)


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

    alert_name = alert_payload.get("alert_name") or ((alert_payload.get("labels") or {}).get("alertname") or "unknown")
    logger.info(f"[INGEST] Alert received: {alert_name} | From AlertManager: {from_alertmanager}")
    
    context = collect_alert_context(alert_payload)
    target_host = (
        body.get("target_host")
        or context.get("target_host")
        or _extract_target_host_from_payload(alert_payload)
    )
    execute_immediately = _to_bool(envelope_execute, default=not from_alertmanager)
    structured_evidence = _structured_evidence_from_context(context, alert_payload=alert_payload)
    contradiction_assessment = _build_contradiction_assessment(structured_evidence)
    learning_snapshot = _historical_outcome_learning_snapshot(
        service=str(context.get("service_name") or ((alert_payload.get("labels") or {}).get("service")) or ""),
        environment=str(((alert_payload.get("labels") or {}).get("environment") or (alert_payload.get("labels") or {}).get("env") or (context.get("inventory_runtime") or {}).get("environment") or "")).lower(),
    )
    state_fingerprint = _build_incident_state_fingerprint(alert_payload, context, structured_evidence)
    cached_state = _get_cached_state_decision(state_fingerprint)
    cached_planning = cached_state.get("planning") if isinstance(cached_state.get("planning"), dict) else {}

    if cached_planning:
        logger.info(f"[INGEST] Using cached planning decision for fingerprint {state_fingerprint[:16]}...")
        normalized_plan = _coerce_diagnostic_plan(alert_payload, context, cached_planning, target_host)
    else:
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
            "- If recent incident memory is present, use it to determine whether this is a recurrence of the same failure after a previous remediation.\n"
            "- If runtime state shows the previous remediation was exhausted or insufficient, choose the next diagnostic command or remediation based on the current evidence, not just the prior command.\n"
            "- Explicitly weigh contradictory evidence before recommending aggressive action. If contradictions are high, prefer observation or safe validation.\n"
            "- The agent does not support shell operators, command substitution, pipes, or semicolons.\n"
            f"- Prefer evidence-guided targeting using this structured evidence summary: {_format_structured_evidence_for_prompt(structured_evidence, 900)}\n"
            f"- Contradiction assessment: {_head_for_prompt(json.dumps(contradiction_assessment, indent=2, default=str), 500)}\n"
            f"- Historical outcome learning: {_head_for_prompt(json.dumps(learning_snapshot, indent=2, default=str), 700)}\n"
            "- Prefer target-native diagnostics (service health, logs, metrics, database readiness) instead of platform-specific shell tricks.\n"
            "- If the evidence points to a shared dependency path, pivot the target to that dependency instead of staying on the symptom service.\n"
            "- Return a literal executable command only.\n\n"
            f"ALERT PAYLOAD:\n{_head_for_prompt(json.dumps(alert_payload, indent=2, default=str), 2000)}\n\n"
            f"OBSERVABILITY CONTEXT:\n{_head_for_prompt(json.dumps(context, indent=2, default=str), 2500)}\n"
        )
        logger.info(f"[INGEST] Sending planning prompt to AIDE for {alert_name} on {target_host}")
        ok, status, planning_body = query_aide_api(planning_prompt)
        if not ok:
            # CRITICAL: Never return a non-2xx to alertmanager — it will retry indefinitely and
            # mark the webhook as dead after 9 attempts. Accept the alert, log the LLM failure,
            # return 200 with a degraded response so alertmanager considers it delivered.
            logger.error(f"[INGEST] AIDE planning failed (LLM unavailable): {status} | Alert will be stored without AI analysis")
            _correlate_alert_to_incident(alert_payload, context, f"AI analysis unavailable: {alert_name}", "LLM backend unreachable during ingestion.")
            return JsonResponse(
                {
                    "status": "accepted_degraded",
                    "warning": "AI analysis skipped — LLM backend unavailable. Alert recorded.",
                    "alert_name": alert_name,
                    "target_host": target_host,
                    "structured_evidence": structured_evidence,
                    "incident_state_fingerprint": state_fingerprint,
                    "llm_error": str(status)[:200],
                },
                status=200,
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
        logger.info(f"[INGEST] Planning result: {normalized_plan.get('diagnostic_command', 'NO CMD')[:60]} | Should execute: {normalized_plan.get('should_execute')}")
    diagnostic_command = normalized_plan["diagnostic_command"]
    target_host = normalized_plan["target_host"]
    summary = normalized_plan["summary"]
    why = normalized_plan["why"]
    should_execute = normalized_plan["should_execute"]
    target_type = normalized_plan["target_type"]
    decision_policy = normalized_plan.get("decision_policy") or "diagnose"
    confidence_reason = normalized_plan.get("confidence_reason") or ""
    evidence_assessment = normalized_plan.get("evidence_assessment") or {}

    response_payload = {
        "summary": summary,
        "why": why,
        "target_host": target_host,
        "target_type": target_type,
        "diagnostic_command": diagnostic_command,
        "should_execute": should_execute,
        "decision_policy": decision_policy,
        "confidence_reason": confidence_reason,
        "evidence_assessment": evidence_assessment,
        "structured_evidence": structured_evidence,
        "contradiction_assessment": contradiction_assessment,
        "historical_outcome_learning": learning_snapshot,
        "incident_state_fingerprint": state_fingerprint,
        "state_cache_hit": bool(cached_planning),
        "context": context,
    }
    response_payload["diagnostic_typed_action"] = infer_typed_action(
        command=diagnostic_command,
        target_host=target_host,
        why=why,
        requires_approval=False,
        service=str(context.get("service_name") or "") if isinstance(context, dict) else "",
    )

    incident = _correlate_alert_to_incident(alert_payload, context, summary, why)
    response_payload["incident"] = _incident_summary_payload(incident)
    policy_context = {
        "labels": alert_payload.get("labels") or {},
        "target_type": target_type,
        "target_host": target_host,
        "service_name": context.get("service_name") or ((alert_payload.get("labels") or {}).get("service")) or "",
        "dependency_graph": context.get("dependency_graph") or {},
        "inventory_runtime": context.get("inventory_runtime") or {},
    }
    policy_decision = evaluate_execution_policy(
        command=diagnostic_command,
        target_host=target_host,
        execution_type="diagnostic",
        context=policy_context,
        approval_present=False,
        actor="alert-ingest",
    )
    response_payload["policy_decision"] = policy_decision
    response_payload["behavior_version"] = current_behavior_version_payload()
    _store_cached_state_decision(
        state_fingerprint,
        {
            "planning": {
                "summary": summary,
                "why": why,
                "target_host": target_host,
                "target_type": target_type,
                "diagnostic_command": diagnostic_command,
                "should_execute": should_execute,
                "decision_policy": decision_policy,
                "confidence_reason": confidence_reason,
                "evidence_assessment": evidence_assessment,
                "policy_decision": policy_decision,
                "diagnostic_typed_action": response_payload["diagnostic_typed_action"],
                "behavior_version": response_payload["behavior_version"],
            },
            "structured_evidence": structured_evidence,
            "incident_key": str(incident.incident_key),
        },
    )

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
        "decision_policy": decision_policy,
        "confidence_reason": confidence_reason,
        "evidence_assessment": evidence_assessment,
        "policy_decision": policy_decision,
        "diagnostic_typed_action": response_payload["diagnostic_typed_action"],
        "behavior_version": response_payload["behavior_version"],
        "structured_evidence": structured_evidence,
        "contradiction_assessment": contradiction_assessment,
        "historical_outcome_learning": learning_snapshot,
        "incident_state_fingerprint": state_fingerprint,
        "state_cache_hit": bool(cached_planning),
        "execute_immediately": execute_immediately,
        "from_alertmanager": from_alertmanager,
        "labels": alert_payload.get("labels") or {},
        "annotations": alert_payload.get("annotations") or {},
        "dependency_graph": context.get("dependency_graph") or {},
        "recent_incident_memory": context.get("recent_incident_memory") or {},
        "inventory_runtime": context.get("inventory_runtime") or {},
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

    if policy_decision["decision"] != "allowed":
        cache_entry.update({
            "should_execute": False,
            "execution_status": policy_decision["decision"],
            "policy_decision": policy_decision,
        })
        _store_recent_alert_recommendation(cache_entry)
        IncidentTimelineEvent.objects.create(
            incident=incident,
            event_type="execution_blocked_by_policy",
            title=f"Automatic diagnostic command {policy_decision['decision'].replace('_', ' ')}",
            detail=policy_decision.get("reason") or "",
            payload={
                "command": diagnostic_command,
                "target_host": target_host,
                "execution_type": "diagnostic",
                "typed_action": response_payload["diagnostic_typed_action"],
                "policy_decision": policy_decision,
                "incident_state_fingerprint": state_fingerprint,
            },
        )
        response_payload["should_execute"] = False
        return JsonResponse(response_payload, status=200)

    success, command_output, agent_response = delegate_command_to_agent(diagnostic_command, target_host)
    record_execution_attempt(
        policy_decision=policy_decision,
        command=diagnostic_command,
        target_host=target_host,
        success=success,
    )
    analysis_ok, final_answer, analysis_sections = analyze_command_output(
        summary,
        target_host,
        diagnostic_command,
        command_output,
        context=context,
    )
    remediation_decision = _remediation_decision_payload(analysis_sections)
    previous_remediation = cached_state.get("remediation") if isinstance(cached_state.get("remediation"), dict) else {}
    remediation_variance = _detect_remediation_variance(previous_remediation, remediation_decision)
    if remediation_variance:
        previous_variance = remediation_variance.get("previous") or {}
        remediation_variance["previous"] = {**previous_variance, "structured_evidence": cached_state.get("structured_evidence") or {}}
        remediation_variance["current"] = {**(remediation_variance.get("current") or {}), "structured_evidence": structured_evidence}
        _record_remediation_variance(
            incident=incident,
            fingerprint=state_fingerprint,
            variance=remediation_variance,
            structured_evidence=structured_evidence,
        )
    verification = _run_post_action_verification(
        alert_payload=alert_payload,
        baseline_context=context,
        baseline_evidence=structured_evidence,
        execution_type="diagnostic",
        command=diagnostic_command,
        agent_success=success,
    )
    _store_cached_state_decision(
        state_fingerprint,
        {
            "remediation": {**remediation_decision, "structured_evidence": structured_evidence},
            "last_verification": verification,
            "incident_key": str(incident.incident_key),
            "remediation_typed_action": analysis_sections.get("remediation_typed_action") or {},
        },
    )

    response_payload.update({
        "agent_success": success,
        "agent_response": agent_response,
        "command_output": command_output,
        "final_answer": final_answer,
        "analysis_sections": analysis_sections,
        "analysis_ok": analysis_ok,
        "verification": verification,
        "remediation_variance": remediation_variance or None,
        "policy_decision": policy_decision,
        "diagnostic_typed_action": response_payload["diagnostic_typed_action"],
        "remediation_typed_action": analysis_sections.get("remediation_typed_action") or {},
        "behavior_version": response_payload["behavior_version"],
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
            "typed_action": response_payload["diagnostic_typed_action"],
            "verification": verification,
            "incident_state_fingerprint": state_fingerprint,
            "policy_decision": policy_decision,
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
        "verification": verification,
        "remediation_variance": remediation_variance or None,
        "execution_status": "completed" if success else "failed",
        "last_execution_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "policy_decision": policy_decision,
        "diagnostic_typed_action": response_payload["diagnostic_typed_action"],
        "remediation_typed_action": analysis_sections.get("remediation_typed_action") or {},
        "behavior_version": response_payload["behavior_version"],
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
        session_id = str(body.get("session_id") or "").strip()
        typed_action_payload = body.get("typed_action") if isinstance(body.get("typed_action"), dict) else None
        rollback_metadata = body.get("rollback_metadata") if isinstance(body.get("rollback_metadata"), dict) else {}
        approval_token = str(body.get("approval_token") or "").strip()
        idempotency_key_input = str(body.get("idempotency_key") or "").strip()
        dry_run = _to_bool(body.get("dry_run"), default=False)
        command_to_run = body.get("command") or command_from_typed_action(typed_action_payload)
        original_question = body.get("original_question")
        target_host = body.get("target_host") or (typed_action_payload or {}).get("target_host") or (typed_action_payload or {}).get("target") # The IP or hostname of the server to run the command on.
        execution_type = _summarize_execution_type(str(body.get("execution_type") or "diagnostic").strip().lower())

        logger.info(f"[EXECUTE] Request to execute {execution_type} command: {command_to_run[:60]}... on {target_host}")

        if not all([command_to_run, original_question, target_host]):
            return JsonResponse({"error": "Missing required fields: command, original_question, and target_host are required."}, status=400)

        linked_recommendation = _lookup_recent_alert_recommendation(alert_id)
        alert_source_payload = _build_verification_alert_payload(
            linked_recommendation or {},
            fallback_target_host=target_host,
            fallback_summary=original_question,
        )
        baseline_context = collect_alert_context(alert_source_payload)
        baseline_evidence = _structured_evidence_from_context(baseline_context, alert_payload=alert_source_payload)
        state_fingerprint = _build_incident_state_fingerprint(alert_source_payload, baseline_context, baseline_evidence)
        cached_state = _get_cached_state_decision(state_fingerprint)
        execution_context = {
            "linked_recommendation": linked_recommendation or {},
            "dependency_graph": (linked_recommendation or {}).get("dependency_graph") or {},
            "incident_key": (linked_recommendation or {}).get("incident_key"),
            "target_type": (linked_recommendation or {}).get("target_type"),
            "target_host": baseline_context.get("target_host") or target_host,
            "service_name": baseline_context.get("service_name") or ((linked_recommendation or {}).get("labels") or {}).get("service") or "",
            "labels": (linked_recommendation or {}).get("labels") or {},
            "evidence_assessment": {"structured_evidence": baseline_evidence},
            "recent_incident_memory": baseline_context.get("recent_incident_memory") or {},
            "inventory_runtime": baseline_context.get("inventory_runtime") or {},
            "typed_action": typed_action_payload or {},
        }
        resolved_typed_action = typed_action_payload or infer_typed_action(
            command=command_to_run,
            target_host=target_host,
            why=original_question,
            requires_approval=execution_type == "remediation",
            service=str(execution_context.get("service_name") or ""),
        )
        incident = None
        incident_key = str((linked_recommendation or {}).get("incident_key") or "").strip()
        if incident_key:
            incident = Incident.objects.filter(incident_key=incident_key).first()
        session = ChatSession.objects.filter(session_id=session_id).first() if session_id else None
        policy_decision = evaluate_execution_policy(
            command=command_to_run,
            target_host=target_host,
            execution_type=execution_type,
            context=execution_context,
            approval_present=False,
            actor=getattr(request.user, "username", "") or getattr(request.user, "email", "") or "operator",
        )
        environment = str(policy_decision.get("environment") or "")
        service_name = str(execution_context.get("service_name") or "")
        ranking = rank_typed_action(
            resolved_typed_action,
            service=service_name,
            environment=environment,
            blast_radius_size=len((((linked_recommendation or {}).get("dependency_graph") or {}).get("blast_radius") or [])),
        )
        intent_context_fingerprint = execution_context_fingerprint(
            {
                "incident_key": incident_key,
                "execution_type": execution_type,
                "typed_action": resolved_typed_action,
                "structured_evidence": baseline_evidence,
                "target_host": target_host,
            }
        )
        idempotency_key = resolve_idempotency_key(
            provided_key=idempotency_key_input,
            execution_type=execution_type,
            incident_key=incident_key,
            action_payload=resolved_typed_action,
            original_question=str(original_question or ""),
        )
        intent, reused_existing = _prepare_execution_intent(
            session=session,
            user=request.user,
            incident=incident,
            execution_type=execution_type,
            command=command_to_run,
            typed_action=resolved_typed_action,
            target_host=target_host,
            service=service_name,
            environment=environment,
            policy_decision=policy_decision,
            ranking=ranking,
            context_fingerprint=intent_context_fingerprint,
            dry_run=dry_run,
            rollback_metadata=rollback_metadata,
            idempotency_key=idempotency_key,
        )
        if reused_existing and intent.response_json:
            return JsonResponse(intent.response_json)

        frequency_check = _check_service_execution_frequency(service_name)
        if not frequency_check["allowed"]:
            policy_decision = {
                **policy_decision,
                "decision": "blocked",
                "allowed": False,
                "blocked": True,
                "reason": frequency_check["reason"],
                "frequency_limit": frequency_check,
            }
        intent.policy_decision_json = policy_decision
        intent.ranking_json = ranking
        intent.status = "blocked" if policy_decision["decision"] == "blocked" else intent.status
        intent.save(update_fields=["policy_decision_json", "ranking_json", "status", "updated_at"])

        if policy_decision["decision"] == "requires_approval":
            if not verify_approval_token(approval_token, intent.approval_token_hash, intent.approval_expires_at):
                approval_workflow = build_execution_workflow(
                    execution_type=execution_type,
                    question=str(original_question or ""),
                    typed_action=resolved_typed_action,
                    target_host=target_host,
                    policy_decision=policy_decision,
                    ranking=ranking,
                    baseline_evidence=baseline_evidence,
                    execution_status="approval_required",
                    dry_run=dry_run,
                )
                raw_token, token_hash, expires_at = issue_approval_token(intent.intent_id)
                intent.approval_token_hash = token_hash
                intent.approval_expires_at = expires_at
                intent.status = "approval_required"
                intent.requires_approval = True
                intent.save(update_fields=["approval_token_hash", "approval_expires_at", "status", "requires_approval", "updated_at"])
                approval_response = {
                    "error": policy_decision.get("reason") or "Execution requires approval.",
                    "approval_required": True,
                    "approval_token": raw_token,
                    "approval_expires_at": expires_at.isoformat(),
                    "execution_intent_id": intent.intent_id,
                    "policy_decision": policy_decision,
                    "typed_action": resolved_typed_action,
                    "ranking": ranking,
                    "behavior_version": current_behavior_version_payload(),
                    "workflow": approval_workflow,
                }
                intent.response_json = _json_safe(approval_response)
                intent.save(update_fields=["response_json", "updated_at"])
                return JsonResponse(approval_response, status=409)
            intent.approved_at = timezone.now()
            intent.approved_by = request.user
            intent.status = "approved"
            intent.save(update_fields=["approved_at", "approved_by", "status", "updated_at"])

        if policy_decision["decision"] == "blocked":
            blocked_workflow = build_execution_workflow(
                execution_type=execution_type,
                question=str(original_question or ""),
                typed_action=resolved_typed_action,
                target_host=target_host,
                policy_decision=policy_decision,
                ranking=ranking,
                baseline_evidence=baseline_evidence,
                execution_status="blocked",
                dry_run=dry_run,
            )
            if alert_id:
                _update_recent_alert_recommendation(
                    alert_id,
                    {
                        "execution_status": policy_decision["decision"],
                        "policy_decision": policy_decision,
                        "typed_action": resolved_typed_action,
                    },
                )
            blocked_response = {
                "error": policy_decision.get("reason") or "Execution blocked by policy.",
                "policy_decision": policy_decision,
                "typed_action": resolved_typed_action,
                "ranking": ranking,
                "behavior_version": current_behavior_version_payload(),
                "execution_intent_id": intent.intent_id,
                "workflow": blocked_workflow,
            }
            intent.response_json = _json_safe(blocked_response)
            intent.save(update_fields=["response_json", "updated_at"])
            return JsonResponse(
                blocked_response,
                status=_policy_status_code(policy_decision),
            )
        if dry_run:
            dry_run_workflow = build_execution_workflow(
                execution_type=execution_type,
                question=str(original_question or ""),
                typed_action=resolved_typed_action,
                target_host=target_host,
                policy_decision=policy_decision,
                ranking=ranking,
                baseline_evidence=baseline_evidence,
                execution_status="dry_run",
                dry_run=True,
            )
            dry_run_response = {
                "execution_type": execution_type,
                "execution_status": "dry_run",
                "final_answer": f"Dry run prepared for {action_summary(resolved_typed_action) or command_to_run}.",
                "command_output": "",
                "agent_success": True,
                "typed_action": resolved_typed_action,
                "typed_action_summary": action_summary(resolved_typed_action),
                "policy_decision": policy_decision,
                "ranking": ranking,
                "behavior_version": current_behavior_version_payload(),
                "execution_intent_id": intent.intent_id,
                "idempotency_key": idempotency_key,
                "rollback_metadata": rollback_metadata,
                "workflow": dry_run_workflow,
            }
            intent.status = "dry_run"
            intent.response_json = _json_safe(dry_run_response)
            intent.executed_at = timezone.now()
            intent.completed_at = timezone.now()
            intent.save(update_fields=["status", "response_json", "executed_at", "completed_at", "updated_at"])
            return JsonResponse(dry_run_response)
        logger.info(f"[EXECUTE] Delegating command to agent...")
        intent.status = "executing"
        intent.executed_at = timezone.now()
        intent.save(update_fields=["status", "executed_at", "updated_at"])
        success, command_output, agent_response = delegate_command_to_agent(command_to_run, target_host)
        record_execution_attempt(
            policy_decision=policy_decision,
            command=command_to_run,
            target_host=target_host,
            success=success,
        )
        logger.info(f"[EXECUTE] Agent execution result: {execution_status if 'execution_status' in locals() else ('SUCCESS' if success else 'FAILED')} | Output length: {len(command_output)}")
        ok, final_answer, analysis_sections = analyze_command_output(
            original_question,
            target_host,
            command_to_run,
            command_output,
            context=execution_context,
        )
        if not ok:
            logger.error(f"[EXECUTE] Analysis failed: {final_answer}")
            return JsonResponse({"error": final_answer}, status=502)

        execution_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        execution_status = "completed" if success else "failed"
        command_output_key = "remediation_output" if execution_type == "remediation" else "command_output"
        answer_key = "post_remediation_ai_analysis" if execution_type == "remediation" else "post_command_ai_analysis"
        execution_status_key = "remediation_execution_status" if execution_type == "remediation" else "execution_status"
        execution_time_key = "remediation_last_execution_at" if execution_type == "remediation" else "last_execution_at"
        timeline_event_type = "remediation_command_executed" if execution_type == "remediation" else "manual_command_executed"
        timeline_title = f"Manual {execution_type} command executed against {target_host}"
        remediation_decision = _remediation_decision_payload(analysis_sections)
        previous_remediation = cached_state.get("remediation") if isinstance(cached_state.get("remediation"), dict) else {}
        remediation_variance = _detect_remediation_variance(previous_remediation, remediation_decision)
        verification = _run_post_action_verification(
            alert_payload=alert_source_payload,
            baseline_context=baseline_context,
            baseline_evidence=baseline_evidence,
            execution_type=execution_type,
            command=command_to_run,
            agent_success=success,
        )
        logger.info(f"[EXECUTE] Verification result: {verification.get('status')} | Variance detected: {bool(remediation_variance)}")

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
                    "remediation_typed_action": analysis_sections.get("remediation_typed_action") or ((linked_recommendation or {}).get("remediation_typed_action")) or {},
                    "agent_response": agent_response,
                    "verification": verification,
                    "remediation_variance": remediation_variance or None,
                    "incident_state_fingerprint": state_fingerprint,
                    "policy_decision": policy_decision,
                    "typed_action": resolved_typed_action,
                },
            )
            if incident_key:
                incident = Incident.objects.filter(incident_key=incident_key).first()
                if incident:
                    incident.status = "investigating"
                    incident.summary = incident.summary or original_question
                    incident.save(update_fields=["status", "summary", "updated_at"])
                    if remediation_variance:
                        previous_variance = remediation_variance.get("previous") or {}
                        remediation_variance["previous"] = {**previous_variance, "structured_evidence": cached_state.get("structured_evidence") or {}}
                        remediation_variance["current"] = {**(remediation_variance.get("current") or {}), "structured_evidence": baseline_evidence}
                        _record_remediation_variance(
                            incident=incident,
                            fingerprint=state_fingerprint,
                            variance=remediation_variance,
                            structured_evidence=baseline_evidence,
                        )
                    IncidentTimelineEvent.objects.create(
                        incident=incident,
                        event_type=timeline_event_type,
                        title=timeline_title,
                        detail=command_to_run,
                        payload=_json_safe({
                            "execution_type": execution_type,
                            "command": command_to_run,
                            "target_host": target_host,
                            "agent_success": success,
                            "command_output": command_output[:4000],
                            "final_answer": final_answer,
                            "analysis_sections": analysis_sections,
                            "verification": verification,
                            "remediation_variance": remediation_variance or None,
                            "incident_state_fingerprint": state_fingerprint,
                            "policy_decision": policy_decision,
                            "typed_action": resolved_typed_action,
                        }),
                    )

        _store_cached_state_decision(
            state_fingerprint,
            {
                "remediation": {**remediation_decision, "structured_evidence": baseline_evidence},
                "last_verification": verification,
                "structured_evidence": baseline_evidence,
                "incident_key": str(incident.incident_key) if incident else (linked_recommendation or {}).get("incident_key") or "",
                "policy_decision": policy_decision,
                "typed_action": resolved_typed_action,
            },
        )
        RemediationOutcome.objects.create(
            execution_intent=intent,
            incident=incident,
            action_type=str(resolved_typed_action.get("action") or ""),
            service=service_name,
            environment=environment,
            context_fingerprint=intent_context_fingerprint,
            action_signature=execution_action_signature(resolved_typed_action),
            success=bool(success and verification.get("status") in {"resolved", "partially_improved"}),
            verification_status=str(verification.get("status") or ""),
            time_to_recovery_seconds=0 if verification.get("status") == "resolved" else None,
            recurrence_within_minutes=None,
            blast_radius_risk=float(len((((linked_recommendation or {}).get("dependency_graph") or {}).get("blast_radius") or []))),
            operator_override=False,
            metadata_json={
                "policy_decision": policy_decision,
                "ranking": ranking,
                "behavior_version": current_behavior_version_payload(),
            },
        )
        replay_scenario = ReplayScenario.objects.create(
            incident=incident,
            session=session,
            source="execution",
            title=f"{execution_type}:{service_name or target_host}",
            alert_payload_json=alert_source_payload,
            metrics_snapshot_json=(baseline_context.get("metrics") or baseline_context.get("telemetry_metrics") or {}),
            logs_snapshot_json=(baseline_context.get("logs") or {}),
            traces_snapshot_json=(baseline_context.get("traces") or {}),
            dependency_context_json={
                "dependency_graph": execution_context.get("dependency_graph") or {},
                "structured_evidence": baseline_evidence,
            },
            prior_incident_memory_json=baseline_context.get("recent_incident_memory") or {},
            chosen_action_json=resolved_typed_action,
            outcome_json={"verification": verification, "success": success},
            behavior_version_json=current_behavior_version_payload(),
        )
        replay_scores = build_replay_scores(
            verification=verification,
            policy_decision=policy_decision,
            execution_success=success,
        )
        ReplayEvaluation.objects.create(
            scenario=replay_scenario,
            execution_intent=intent,
            status="completed",
            scores_json=replay_scores,
            summary_json={
                "verification_status": verification.get("status"),
                "execution_type": execution_type,
                "service": service_name,
            },
        )
        workflow = build_execution_workflow(
            execution_type=execution_type,
            question=str(original_question or ""),
            typed_action=resolved_typed_action,
            target_host=target_host,
            policy_decision=policy_decision,
            ranking=ranking,
            baseline_evidence=baseline_evidence,
            verification=verification,
            analysis_sections=analysis_sections,
            execution_status=execution_status,
            dry_run=dry_run,
        )

        response_payload = {
            "execution_type": execution_type,
            "final_answer": final_answer,
            "analysis_sections": analysis_sections,
            "command_output": command_output,
            "agent_success": success,
            "agent_response": agent_response,
            "last_execution_at": execution_time,
            "execution_status": execution_status,
            "verification": verification,
            "remediation_variance": remediation_variance or None,
            "incident_state_fingerprint": state_fingerprint,
            "policy_decision": policy_decision,
            "typed_action": resolved_typed_action,
            "typed_action_summary": action_summary(resolved_typed_action),
            "ranking": ranking,
            "behavior_version": current_behavior_version_payload(),
            "execution_intent_id": intent.intent_id,
            "idempotency_key": idempotency_key,
            "rollback_metadata": rollback_metadata,
            "replay_scores": replay_scores,
            "workflow": workflow,
        }
        intent.status = execution_status
        intent.verification_json = verification
        intent.response_json = _json_safe(response_payload)
        intent.completed_at = timezone.now()
        intent.save(update_fields=["status", "verification_json", "response_json", "completed_at", "updated_at"])

        return JsonResponse(response_payload)

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


# ---------------------------------------------------------------------------
# M6 — Runbook Generator
# ---------------------------------------------------------------------------

@login_required
def generate_runbook_view(request: HttpRequest, incident_key: str):
    """Generate an AI runbook from incident RCA + timeline and save to Knowledge Base."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)

    try:
        payload = generate_runbook_payload(
            incident,
            llm_query=query_aide_api,
            runbook_model=Runbook,
            timeline_event_model=IncidentTimelineEvent,
            request_user=request.user,
            logger=logger,
        )
    except RuntimeError as exc:
        return JsonResponse({"error": "llm_failed", "detail": str(exc)}, status=502)

    # Save to Knowledge Base (doc_search) so RAG can retrieve it
    try:
        from doc_search.models import Document, DocumentChunk
        from django.core.files.base import ContentFile
        doc = Document(title=payload["title"], uploaded_by=request.user if request.user.is_authenticated else None)
        doc.file.save(
            f"runbook_{str(incident_key)[:8]}.md",
            ContentFile(payload["content"].encode("utf-8")),
            save=False,
        )
        doc.processing_status = "SUCCESS"
        doc.save()
        chunk_size = 3000
        overlap = 300
        step = max(1, chunk_size - overlap)
        for index, start in enumerate(range(0, len(payload["content"]), step)):
            chunk = payload["content"][start:start + chunk_size]
            if not chunk:
                continue
            DocumentChunk.objects.create(document=doc, chunk_text=chunk, chunk_index=index)
    except Exception as kb_err:
        logger.warning("Runbook KB save failed (non-fatal): %s", kb_err)
    return JsonResponse(payload)


@login_required
def download_runbook_view(request: HttpRequest, incident_key: str):
    """Download the latest saved runbook for an incident as CSV."""
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)

    runbook = incident.runbooks.order_by("-created_at").first()
    if not runbook:
        return JsonResponse({"error": "runbook_not_found", "detail": "Generate a runbook first."}, status=404)

    return _csv_download_response(
        _download_filename("runbook", incident_key, "csv"),
        [
            {
                "incident_key": incident.incident_key,
                "title": runbook.title,
                "created_at": runbook.created_at.isoformat(),
                "content": runbook.content,
            }
        ],
    )


# ---------------------------------------------------------------------------
# M6 — Anomaly Explainer
# ---------------------------------------------------------------------------

@login_required
def explain_anomaly_view(request: HttpRequest):
    """Return a plain-English explanation of why an alert fired."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        body = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"error": "invalid_json"}, status=400)

    alert_name = body.get("alert_name") or "unknown"
    target_host = body.get("target_host") or ""
    labels = body.get("labels") or {}
    summary = body.get("summary") or body.get("initial_ai_diagnosis") or ""
    incident_key = body.get("incident_key") or ""

    incident = Incident.objects.filter(incident_key=incident_key).first() if incident_key else None
    try:
        payload = explain_anomaly_payload(
            alert_name=alert_name,
            target_host=target_host,
            labels=labels,
            summary=summary,
            incident=incident,
            llm_query=query_aide_api,
            timeline_event_model=IncidentTimelineEvent,
        )
    except RuntimeError as exc:
        return JsonResponse({"error": "llm_failed", "detail": str(exc)}, status=502)
    return JsonResponse(payload)


# ---------------------------------------------------------------------------
# M6 — Change Risk Explainer
# ---------------------------------------------------------------------------

@login_required
def change_risk_view(request: HttpRequest):
    """Analyse a planned change and return a risk score, affected services, and maintenance window."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        body = json.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"error": "invalid_json"}, status=400)

    service = (body.get("service") or "").strip()
    change_description = (body.get("change_description") or "").strip()
    planned_at = body.get("planned_at") or ""
    change_type = body.get("change_type") or "deployment"

    if not change_description:
        return JsonResponse({"error": "change_description is required"}, status=400)

    # Topology context for the service
    application_info = _get_application_info(service)
    application_key = application_info.get("application") or service
    dependency = _get_dependency_context(service)
    blast_radius = dependency.get("blast_radius") or []
    depends_on = dependency.get("depends_on") or []

    # Recent incidents for context
    recent_incidents = []
    for inc in Incident.objects.filter(
        models.Q(primary_service=service) | models.Q(application=application_key)
    ).order_by("-created_at")[:5].values("title", "severity", "status", "opened_at"):
        recent_incidents.append({
            "title": inc["title"],
            "severity": inc["severity"],
            "status": inc["status"],
            "opened_at": inc["opened_at"].isoformat(),
        })

    try:
        payload = analyze_change_risk_payload(
            service=service,
            change_description=change_description,
            planned_at=planned_at,
            change_type=change_type,
            blast_radius=blast_radius,
            depends_on=depends_on,
            recent_incidents=recent_incidents,
            llm_query=query_aide_api,
        )
    except RuntimeError as exc:
        return JsonResponse({"error": "llm_failed", "detail": str(exc)}, status=502)
    return JsonResponse(payload)


# ---------------------------------------------------------------------------
# M4 — SLA acknowledge endpoint
# ---------------------------------------------------------------------------

@login_required
def acknowledge_sla_view(request: HttpRequest, incident_key: str):
    """Mark the SLA response as acknowledged for an incident."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)

    incident.sla_response_acknowledged_at = timezone.now()
    incident.save(update_fields=["sla_response_acknowledged_at", "updated_at"])

    IncidentTimelineEvent.objects.create(
        incident=incident,
        event_type="sla_acknowledged",
        title="SLA response acknowledged",
        detail=f"Acknowledged by {request.user}",
        payload={},
    )

    return JsonResponse({"status": "ok", "sla": _compute_sla_status(incident)})


# ---------------------------------------------------------------------------
# M4 — Post-Incident Timeline Narrative
# ---------------------------------------------------------------------------

@login_required
def incident_timeline_narrative_view(request: HttpRequest, incident_key: str):
    """Generate a plain-English post-incident narrative from existing timeline events."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)

    try:
        payload = generate_timeline_narrative_payload(
            incident,
            llm_query=query_aide_api,
            timeline_event_model=IncidentTimelineEvent,
        )
    except RuntimeError as exc:
        return JsonResponse({"error": "llm_failed", "detail": str(exc)}, status=502)
    return JsonResponse(payload)


@login_required
def download_timeline_narrative_view(request: HttpRequest, incident_key: str):
    """Download the latest saved PIR narrative for an incident as CSV."""
    if request.method != "GET":
        return JsonResponse({"error": "GET required"}, status=405)

    incident = Incident.objects.filter(incident_key=incident_key).first()
    if not incident:
        return JsonResponse({"error": "incident_not_found"}, status=404)

    narrative_event = incident.timeline.filter(event_type="pir_generated").order_by("-created_at").first()
    if not narrative_event:
        return JsonResponse({"error": "narrative_not_found", "detail": "Generate a post-incident narrative first."}, status=404)

    narrative = str((narrative_event.payload or {}).get("narrative") or narrative_event.detail or "").strip()
    if not narrative:
        return JsonResponse({"error": "narrative_not_found", "detail": "No saved narrative content was found."}, status=404)

    return _csv_download_response(
        _download_filename("post-incident-narrative", incident_key, "csv"),
        [
            {
                "incident_key": incident.incident_key,
                "title": narrative_event.title,
                "created_at": narrative_event.created_at.isoformat(),
                "narrative": narrative,
            }
        ],
    )
