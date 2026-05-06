"""
Track 3.6 — Trace Backend Abstraction
=======================================
Decouples the control plane from a hardcoded trace backend.

Design:
  - Abstract TraceBackend interface with three operations:
      search_traces(service, from_ts, to_ts, limit)
      get_trace(trace_id)
      health_check()
  - JaegerBackend   — current production backend (all-in-one API v3/v2)
  - TempoBackend    — target long-term backend (Tempo HTTP API)
  - FallbackBackend — tries primary, falls back to secondary on failure (Jaeger→Tempo transition)
  - factory()       — returns the configured backend via TRACE_BACKEND env var

Environment variables:
  TRACE_BACKEND            jaeger | tempo | fallback   (default: jaeger)
  JAEGER_API_URL           http://jaeger:16686         (default)
  TEMPO_API_URL            http://tempo:3200           (default)
  TRACE_BACKEND_TIMEOUT    seconds                     (default: 10)

The control plane should import get_trace_backend() and call the interface;
it never references JaegerBackend or TempoBackend directly.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone as dt_tz
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("trace_backend")

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------
TRACE_BACKEND: str = os.environ.get("TRACE_BACKEND", "jaeger")
JAEGER_API_URL: str = os.environ.get("JAEGER_API_URL", "http://jaeger:16686")
TEMPO_API_URL: str = os.environ.get("TEMPO_API_URL", "http://tempo:3200")
TRACE_BACKEND_TIMEOUT: int = int(os.environ.get("TRACE_BACKEND_TIMEOUT", "10"))


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class TraceBackend(ABC):
    """
    Abstract interface for all trace storage backends.
    All methods return plain dicts/lists so callers are not coupled to
    backend-specific response shapes.
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend identifier."""

    @abstractmethod
    def search_traces(
        self,
        service: str,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 20,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for traces matching the given criteria.

        Returns a list of normalised trace summary dicts:
          {trace_id, root_service, root_operation, duration_ms, start_time, spans}
        """

    @abstractmethod
    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single trace by ID.

        Returns a normalised trace dict or None if not found.
        """

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        Check backend connectivity.

        Returns {"healthy": bool, "backend": str, "detail": str}
        """


# ---------------------------------------------------------------------------
# Jaeger backend (current production — Jaeger v2 HTTP API)
# ---------------------------------------------------------------------------

class JaegerBackend(TraceBackend):
    """
    Wraps the Jaeger HTTP API (all-in-one: /api/services, /api/traces).
    Compatible with Jaeger 1.x all-in-one image used in docker-compose.
    """

    def __init__(self, base_url: str = JAEGER_API_URL, timeout: int = TRACE_BACKEND_TIMEOUT):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

    @property
    def backend_name(self) -> str:
        return "jaeger"

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._base}{path}"
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _normalise_span(span: Dict) -> Dict[str, Any]:
        tags = {t["key"]: t["value"] for t in span.get("tags", [])}
        return {
            "span_id": span.get("spanID", ""),
            "operation": span.get("operationName", ""),
            "start_time": span.get("startTime", 0),
            "duration_us": span.get("duration", 0),
            "tags": tags,
            "references": span.get("references", []),
        }

    @staticmethod
    def _normalise_trace(trace: Dict) -> Dict[str, Any]:
        spans = trace.get("spans", [])
        processes = trace.get("processes", {})
        root_span = spans[0] if spans else {}
        root_pid = root_span.get("processID", "")
        root_service = processes.get(root_pid, {}).get("serviceName", "")
        total_duration = sum(s.get("duration", 0) for s in spans)
        start_time = root_span.get("startTime", 0)
        return {
            "trace_id": trace.get("traceID", ""),
            "root_service": root_service,
            "root_operation": root_span.get("operationName", ""),
            "duration_ms": round(total_duration / 1000, 2),
            "start_time": start_time,
            "span_count": len(spans),
            "spans": [JaegerBackend._normalise_span(s) for s in spans],
        }

    def search_traces(
        self,
        service: str,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 20,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"service": service, "limit": limit}
        if from_ts:
            params["start"] = int(from_ts.timestamp() * 1_000_000)  # microseconds
        if to_ts:
            params["end"] = int(to_ts.timestamp() * 1_000_000)
        if tags:
            params["tags"] = " ".join(f"{k}={v}" for k, v in tags.items())
        try:
            data = self._get("/api/traces", params=params)
            traces = data.get("data") or []
            return [self._normalise_trace(t) for t in traces]
        except Exception as exc:
            logger.warning("jaeger search_traces failed: %s", exc)
            return []

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = self._get(f"/api/traces/{trace_id}")
            traces = data.get("data") or []
            if traces:
                return self._normalise_trace(traces[0])
            return None
        except Exception as exc:
            logger.warning("jaeger get_trace(%s) failed: %s", trace_id, exc)
            return None

    def health_check(self) -> Dict[str, Any]:
        try:
            self._get("/api/services")
            return {"healthy": True, "backend": self.backend_name, "detail": "ok"}
        except Exception as exc:
            return {"healthy": False, "backend": self.backend_name, "detail": str(exc)}


# ---------------------------------------------------------------------------
# Tempo backend (target long-term backend — Tempo HTTP API)
# ---------------------------------------------------------------------------

class TempoBackend(TraceBackend):
    """
    Wraps the Grafana Tempo HTTP API.
    Uses Tempo's TraceQL search endpoint for searches and /api/traces/:id for lookup.

    Tempo API reference: https://grafana.com/docs/tempo/latest/api_docs/
    """

    def __init__(self, base_url: str = TEMPO_API_URL, timeout: int = TRACE_BACKEND_TIMEOUT):
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

    @property
    def backend_name(self) -> str:
        return "tempo"

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        url = f"{self._base}{path}"
        resp = self._session.get(url, params=params, timeout=self._timeout)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _normalise_span_from_tempo(span: Dict) -> Dict[str, Any]:
        attrs = {a.get("key", ""): a.get("value", {}).get("stringValue", "") for a in span.get("attributes", [])}
        start_ns = int(span.get("startTimeUnixNano", 0))
        duration_ns = int(span.get("endTimeUnixNano", 0)) - start_ns
        return {
            "span_id": span.get("spanId", ""),
            "operation": span.get("name", ""),
            "start_time": start_ns // 1_000,      # → microseconds for consistency
            "duration_us": duration_ns // 1_000,
            "tags": attrs,
            "references": [],
        }

    @staticmethod
    def _normalise_trace_from_tempo(trace: Dict) -> Dict[str, Any]:
        resource_spans = trace.get("resourceSpans") or trace.get("batches") or []
        all_spans = []
        root_service = ""
        for rs in resource_spans:
            resource_attrs = {
                a.get("key", ""): a.get("value", {}).get("stringValue", "")
                for a in rs.get("resource", {}).get("attributes", [])
            }
            if not root_service:
                root_service = resource_attrs.get("service.name", "")
            for scope_spans in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans", []):
                for span in scope_spans.get("spans", []):
                    all_spans.append(TempoBackend._normalise_span_from_tempo(span))

        root_span = all_spans[0] if all_spans else {}
        total_duration_us = sum(s.get("duration_us", 0) for s in all_spans)
        return {
            "trace_id": trace.get("traceID", ""),
            "root_service": root_service,
            "root_operation": root_span.get("operation", ""),
            "duration_ms": round(total_duration_us / 1000, 2),
            "start_time": root_span.get("start_time", 0),
            "span_count": len(all_spans),
            "spans": all_spans,
        }

    def search_traces(
        self,
        service: str,
        from_ts: Optional[datetime] = None,
        to_ts: Optional[datetime] = None,
        limit: int = 20,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        # TraceQL query: {resource.service.name="<service>"}
        traceql = f'{{resource.service.name="{service}"}}'
        if tags:
            extra = " && ".join(f'span.{k}="{v}"' for k, v in tags.items())
            traceql = f'{{{extra} && resource.service.name="{service}"}}'

        params: Dict[str, Any] = {"q": traceql, "limit": limit}
        if from_ts:
            params["start"] = int(from_ts.timestamp())
        if to_ts:
            params["end"] = int(to_ts.timestamp())

        try:
            data = self._get("/api/search", params=params)
            traces = data.get("traces") or []
            results = []
            for t in traces:
                results.append({
                    "trace_id": t.get("traceID", ""),
                    "root_service": t.get("rootServiceName", service),
                    "root_operation": t.get("rootTraceName", ""),
                    "duration_ms": round(int(t.get("durationMs", 0))),
                    "start_time": t.get("startTimeUnixNano", 0),
                    "span_count": t.get("spanCount", 0),
                    "spans": [],  # summary only — call get_trace() for full spans
                })
            return results
        except Exception as exc:
            logger.warning("tempo search_traces failed: %s", exc)
            return []

    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = self._get(f"/api/traces/{trace_id}")
            return self._normalise_trace_from_tempo(data)
        except Exception as exc:
            logger.warning("tempo get_trace(%s) failed: %s", trace_id, exc)
            return None

    def health_check(self) -> Dict[str, Any]:
        try:
            self._get("/api/echo")
            return {"healthy": True, "backend": self.backend_name, "detail": "ok"}
        except Exception as exc:
            return {"healthy": False, "backend": self.backend_name, "detail": str(exc)}


# ---------------------------------------------------------------------------
# Fallback backend (Jaeger → Tempo transition helper)
# ---------------------------------------------------------------------------

class FallbackTraceBackend(TraceBackend):
    """
    Tries the primary backend first; on failure transparently falls back to secondary.
    Designed for the Jaeger → Tempo migration window so neither the control
    plane nor the investigation code needs to change.
    """

    def __init__(self, primary: TraceBackend, secondary: TraceBackend):
        self._primary = primary
        self._secondary = secondary

    @property
    def backend_name(self) -> str:
        return f"fallback({self._primary.backend_name}→{self._secondary.backend_name})"

    def search_traces(self, service, from_ts=None, to_ts=None, limit=20, tags=None):
        result = self._primary.search_traces(service, from_ts, to_ts, limit, tags)
        if not result:
            logger.info("trace search: primary empty/failed, trying secondary")
            result = self._secondary.search_traces(service, from_ts, to_ts, limit, tags)
        return result

    def get_trace(self, trace_id: str):
        result = self._primary.get_trace(trace_id)
        if result is None:
            logger.info("get_trace: primary returned None, trying secondary")
            result = self._secondary.get_trace(trace_id)
        return result

    def health_check(self) -> Dict[str, Any]:
        primary_health = self._primary.health_check()
        secondary_health = self._secondary.health_check()
        return {
            "healthy": primary_health["healthy"] or secondary_health["healthy"],
            "backend": self.backend_name,
            "primary": primary_health,
            "secondary": secondary_health,
        }


# ---------------------------------------------------------------------------
# Factory — single entry point for the control plane
# ---------------------------------------------------------------------------

_backend_instance: Optional[TraceBackend] = None


def get_trace_backend(force_backend: Optional[str] = None) -> TraceBackend:
    """
    Return the configured TraceBackend singleton.

    The control plane should call this instead of constructing backends directly.
    Set force_backend to override TRACE_BACKEND for testing.
    """
    global _backend_instance
    if _backend_instance is not None and force_backend is None:
        return _backend_instance

    chosen = force_backend or TRACE_BACKEND

    if chosen == "jaeger":
        _backend_instance = JaegerBackend()
    elif chosen == "tempo":
        _backend_instance = TempoBackend()
    elif chosen == "fallback":
        _backend_instance = FallbackTraceBackend(
            primary=JaegerBackend(),
            secondary=TempoBackend(),
        )
    else:
        logger.warning("Unknown TRACE_BACKEND '%s', defaulting to jaeger", chosen)
        _backend_instance = JaegerBackend()

    logger.info("trace backend initialised: %s", _backend_instance.backend_name)
    return _backend_instance


def reset_trace_backend() -> None:
    """Force re-initialisation of the backend singleton (used in tests)."""
    global _backend_instance
    _backend_instance = None
