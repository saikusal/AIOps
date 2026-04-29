import json
import re
from typing import Callable, Optional, Set, Tuple


ROUTE_CHOICES: Set[str] = {
    "general",
    "investigation",
    "prometheus_query",
    "docs",
    "direct_action",
    "initiate_password_reset",
}


def deterministic_route(query: str) -> Optional[str]:
    """Fast path for explicit or safety-sensitive intents."""
    if not query:
        return "general"

    t = query.lower()

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
        r'unable to login',
    ]
    if any(re.search(pattern, t, re.IGNORECASE) for pattern in password_reset_patterns):
        return "initiate_password_reset"

    direct_action_keywords = [
        "list files", "delete file", "remove file", "ls", "rm", "show directory",
    ]
    if any(keyword in t for keyword in direct_action_keywords) and "server" in t:
        return "direct_action"

    contextual_handoff_markers = ["application=", "service=", "incident="]
    if any(marker in t for marker in contextual_handoff_markers):
        return "investigation"

    explicit_metric_keywords = [
        "prometheus",
        "promql",
        "node exporter",
        "snmp",
        "rate(",
        "sum by",
        "avg by",
        "histogram_quantile(",
        "up{",
    ]
    if any(keyword in t for keyword in explicit_metric_keywords):
        return "prometheus_query"

    doc_tokens = [
        "confluence", "wiki", "runbook", "kb article", "knowledge base",
        "policy", "manual", "procedure", "document", "docs", "pdf",
    ]
    if any(tok in t for tok in doc_tokens):
        return "docs"

    if len(t.split()) <= 6 and any(t.startswith(g) for g in ("hi", "hello", "hey", "what's up", "how are you", "good")):
        return "general"

    return None


def llm_route_decision(
    query: str,
    llm_query: Callable[[str], Tuple[bool, int, str]],
    logger,
) -> Tuple[str, str]:
    """
    Semantic fallback router backed by the configured LLM.
    Returns (route, rationale).
    """
    router_prompt = (
        "You are a request router for an AIOps assistant. "
        "Classify the user's message into exactly one route from this set:\n"
        "- investigation: RCA, incident analysis, blast radius, predictions, risk, next steps, service health summaries.\n"
        "- prometheus_query: explicit metric retrieval, PromQL, bandwidth/CPU/memory/disk/process metric questions.\n"
        "- docs: questions that should be answered primarily from runbooks, Confluence, manuals, or uploaded documents.\n"
        "- general: normal chat, explanations, summaries, or anything not requiring a specialized tool path.\n\n"
        "Do NOT choose docs just because the message contains the word 'document' unless the user is actually asking to search or use documentation.\n"
        "Do NOT choose prometheus_query for prediction or risk-scoring questions.\n"
        "Prefer investigation for incident, RCA, alert analysis, anomaly explanation, prediction, or \"highest risk in next 15 minutes\" style prompts.\n\n"
        "Return JSON only with keys: route, confidence, rationale.\n"
        f"USER_MESSAGE: {query}"
    )

    ok, status, body = llm_query(router_prompt)
    if not ok:
        logger.warning("LLM router failed status=%s body=%s", status, body[:500])
        return "general", "llm_router_failed"

    try:
        start = body.find("{")
        end = body.rfind("}")
        parsed = json.loads(body[start:end + 1]) if start != -1 and end != -1 else {}
    except Exception:
        logger.warning("LLM router returned non-JSON body=%s", body[:500])
        return "general", "llm_router_invalid_json"

    route = str(parsed.get("route") or "").strip().lower()
    rationale = str(parsed.get("rationale") or "").strip() or "llm_router"
    if route not in ROUTE_CHOICES:
        logger.warning("LLM router returned unknown route=%s body=%s", route, body[:500])
        return "general", "llm_router_unknown_route"
    return route, rationale


def classify_query(
    query: str,
    llm_query: Callable[[str], Tuple[bool, int, str]],
    logger,
) -> str:
    """
    Hybrid router:
    1. deterministic rules for explicit/sensitive intents
    2. semantic LLM routing for ambiguous prompts
    """
    deterministic = deterministic_route(query)
    if deterministic:
        logger.info("classify_query: deterministic route=%s question=%s", deterministic, (query or "")[:200])
        return deterministic

    route, rationale = llm_route_decision(query, llm_query=llm_query, logger=logger)
    logger.info("classify_query: llm route=%s rationale=%s question=%s", route, rationale, (query or "")[:200])
    return route
