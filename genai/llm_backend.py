"""
LLM Backend Abstraction Layer
==============================
Provides a unified interface for calling different LLM backends.

Toggle via environment variable:
    LLM_BACKEND=aide     → AIDE enterprise API (default)
    LLM_BACKEND=vllm     → Self-hosted vLLM (OpenAI-compatible, e.g. Qwen2.5-32B)

Both backends return the same signature:
    (ok: bool, status_code: int, text: str)

This module is imported by views.py which continues to call `query_aide_api(prompt)`.
The function delegates to whichever backend is active.
"""

import json
import logging
import os
import time
import uuid
from typing import Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("llm_backend")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
LLM_BACKEND = os.getenv("LLM_BACKEND", "aide").lower()  # "aide" | "vllm"

# ---- AIDE settings ----
AIDE_API_URL = os.getenv("AIDE_API_URL")
AIDE_API_KEY = os.getenv("AIDE_API_KEY")
AIDE_API_URL_SECONDARY = os.getenv("AIDE_API_URL_SECONDARY")
AIDE_API_KEY_SECONDARY = os.getenv("AIDE_API_KEY_SECONDARY")
AIDE_TIMEOUT = int(os.getenv("AIDE_TIMEOUT", "30"))
AIDE_RETRIES = int(os.getenv("AIDE_RETRIES", "3"))
AIDE_VERIFY_SSL = os.getenv("AIDE_VERIFY_SSL", "true").lower() not in ("false", "0", "no")
AIDE_DEBUG = os.getenv("AIDE_DEBUG", "false").lower() in ("true", "1", "yes")
VERIFY_PARAM = os.getenv("AIDE_CA_BUNDLE") or AIDE_VERIFY_SSL

# ---- vLLM settings ----
VLLM_API_URL = os.getenv("VLLM_API_URL", "http://localhost:8001/v1/chat/completions")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "")  # vLLM accepts any key or none
VLLM_MODEL_NAME = os.getenv("VLLM_MODEL_NAME", "qwen32b")
VLLM_TIMEOUT = int(os.getenv("VLLM_TIMEOUT", "120"))
VLLM_MAX_TOKENS = int(os.getenv("VLLM_MAX_TOKENS", "2048"))
VLLM_MAX_MODEL_LEN = int(os.getenv("VLLM_MAX_MODEL_LEN", "8192"))
VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))  # 0.0 = deterministic (consistent remediation commands)

logger.info("LLM backend: %s", LLM_BACKEND)
if LLM_BACKEND == "vllm":
    logger.info("vLLM endpoint: %s  model: %s", VLLM_API_URL, VLLM_MODEL_NAME)


# ---------------------------------------------------------------------------
# AIDE Backend (existing logic, extracted from views.py)
# ---------------------------------------------------------------------------

def _make_aide_call(session, url, headers, payload, call_id):
    """Helper to make a single AIDE API call."""
    try:
        prompt_preview = ""
        try:
            prompt_preview = json.dumps(payload, ensure_ascii=True)[:1200]
        except Exception:
            prompt_preview = "<payload_preview_unavailable>"
        logger.info("AIDE request call_id=%s url=%s payload_preview=%s", call_id, url, prompt_preview)
        resp = session.post(url, headers=headers, json=payload, timeout=AIDE_TIMEOUT, verify=VERIFY_PARAM)
        logger.info("AIDE response call_id=%s status=%s body_preview=%.800s", call_id, resp.status_code, resp.text)
        return resp
    except requests.exceptions.RequestException as e:
        logger.exception("AIDE request exception call_id=%s for URL %s: %s", call_id, url, e)
        return None


def _query_aide(prompt: str) -> Tuple[bool, int, str]:
    """Call AIDE primary API with fallback to secondary."""
    if not AIDE_API_KEY or not AIDE_API_URL:
        return (False, 0, "Primary AIDE API not configured")

    primary_session = requests.Session()
    retry_strategy = Retry(
        total=AIDE_RETRIES,
        status_forcelist=[429, 500, 502, 503],
        allowed_methods=["POST"],
        backoff_factor=0.6,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    primary_session.mount("https://", adapter)
    primary_session.mount("http://", adapter)

    headers = {
        "Authorization": f"Bearer {AIDE_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "aiops-platform-genai/1.0",
    }
    payload = {"messages": [{"role": "user", "content": prompt}]}
    call_id = f"aide-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    logger.info("Attempting Primary AIDE API call_id=%s", call_id)
    primary_resp = _make_aide_call(primary_session, AIDE_API_URL, headers, payload, call_id)

    primary_status = primary_resp.status_code if primary_resp is not None else -1
    should_fallback = primary_status not in [200, 504]

    if should_fallback:
        logger.warning("Primary AIDE failed status=%s, trying secondary. call_id=%s", primary_status, call_id)

        if not AIDE_API_URL_SECONDARY or not AIDE_API_KEY_SECONDARY:
            logger.error("Secondary AIDE API not configured. Cannot fallback.")
            if primary_resp is not None:
                return (False, primary_resp.status_code,
                        primary_resp.text if AIDE_DEBUG else f"AIDE HTTP {primary_resp.status_code}")
            return (False, 0, "Primary AIDE connection failed and secondary is not configured.")

        secondary_session = requests.Session()
        secondary_headers = headers.copy()
        secondary_headers["Authorization"] = f"Bearer {AIDE_API_KEY_SECONDARY}"

        secondary_resp = _make_aide_call(secondary_session, AIDE_API_URL_SECONDARY, secondary_headers, payload, call_id)
        secondary_status = secondary_resp.status_code if secondary_resp is not None else -1

        if secondary_status == 200:
            logger.info("Fallback to secondary AIDE successful.")
            resp = secondary_resp
        else:
            logger.error("Secondary AIDE also failed status=%s", secondary_status)
            if primary_resp is not None:
                return (False, primary_resp.status_code,
                        primary_resp.text if AIDE_DEBUG else f"AIDE HTTP {primary_resp.status_code}")
            return (False, 0, "Primary AIDE connection failed and secondary also failed.")
    else:
        resp = primary_resp

    if resp is None:
        return (False, 0, "Unexpected: response object is None")

    if resp.status_code != 200:
        return (False, resp.status_code,
                resp.text if AIDE_DEBUG else f"AIDE HTTP {resp.status_code}")

    return _parse_aide_response(resp)


def _parse_aide_response(resp) -> Tuple[bool, int, str]:
    """Parse AIDE response — handles multiple response shapes."""
    try:
        data = resp.json()
    except Exception:
        return (True, resp.status_code, resp.text.strip())

    if isinstance(data, dict):
        # OpenAI-style: choices[0].message.content
        if "choices" in data and data["choices"]:
            ch = data["choices"][0]
            if isinstance(ch, dict) and "message" in ch and isinstance(ch["message"], dict) and "content" in ch["message"]:
                return (True, resp.status_code, ch["message"]["content"].strip())
            if isinstance(ch, dict) and "text" in ch and isinstance(ch["text"], str):
                return (True, resp.status_code, ch["text"].strip())
        if "message" in data and isinstance(data["message"], dict) and "content" in data["message"]:
            return (True, resp.status_code, data["message"]["content"].strip())
        for k in ("sql", "output", "result", "response", "text"):
            if k in data and isinstance(data[k], str):
                return (True, resp.status_code, data[k].strip())

    return (True, resp.status_code, json.dumps(data)[:3000])


# ---------------------------------------------------------------------------
# vLLM Backend (OpenAI-compatible API — works with Qwen, Llama, Mistral, etc.)
# ---------------------------------------------------------------------------

# Reusable session with connection pooling
_vllm_session = None


def _get_vllm_session() -> requests.Session:
    global _vllm_session
    if _vllm_session is None:
        _vllm_session = requests.Session()
        adapter = HTTPAdapter(pool_connections=3, pool_maxsize=5)
        _vllm_session.mount("http://", adapter)
        _vllm_session.mount("https://", adapter)
    return _vllm_session


def _query_vllm(prompt: str) -> Tuple[bool, int, str]:
    """
    Call self-hosted vLLM via OpenAI-compatible /v1/chat/completions.
    Qwen2.5-32B-Instruct-AWQ served by vLLM.
    """
    call_id = f"vllm-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    # Build a system message that enforces structured output
    system_msg = (
        "You are an expert AIOps assistant. "
        "When asked to return JSON, return ONLY the raw JSON object — "
        "no markdown fences, no explanation, no preamble. "
        "When asked to return a query (PromQL, SQL), return ONLY the query string."
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt},
    ]

    # Dynamically cap OUTPUT tokens so the full prompt always fits.
    # Never truncate the prompt — reduce output budget instead.
    # Token estimate: ~4 chars/token for mixed English+JSON (conservative)
    estimated_prompt_tokens = (len(system_msg) + len(prompt)) // 4 + 50  # +50 for chat template overhead
    max_context = VLLM_MAX_MODEL_LEN
    safe_max_tokens = min(VLLM_MAX_TOKENS, max(256, max_context - estimated_prompt_tokens))
    if safe_max_tokens < VLLM_MAX_TOKENS:
        logger.info("vLLM auto-reduced max_tokens from %d to %d (est_prompt_tokens=%d, max_context=%d)",
                     VLLM_MAX_TOKENS, safe_max_tokens, estimated_prompt_tokens, max_context)

    payload = {
        "model": VLLM_MODEL_NAME,
        "messages": messages,
        "temperature": VLLM_TEMPERATURE,
        "max_tokens": safe_max_tokens,
        "stream": False,
    }

    headers = {"Content-Type": "application/json"}
    if VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLLM_API_KEY}"

    # ---- Log full request details ----
    logger.info("vLLM request call_id=%s model=%s prompt_len=%d url=%s",
                call_id, VLLM_MODEL_NAME, len(prompt), VLLM_API_URL)
    logger.info("vLLM request call_id=%s payload=%s",
                call_id, json.dumps(payload, ensure_ascii=False)[:3000])

    try:
        t0 = time.time()
        session = _get_vllm_session()
        resp = session.post(VLLM_API_URL, headers=headers, json=payload, timeout=VLLM_TIMEOUT)
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info("vLLM response call_id=%s status=%s elapsed=%dms", call_id, resp.status_code, elapsed_ms)

        if resp.status_code != 200:
            logger.error("vLLM error call_id=%s status=%s elapsed=%dms body=%s",
                         call_id, resp.status_code, elapsed_ms, resp.text[:2000])
            return (False, resp.status_code, f"vLLM HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json()

        # Standard OpenAI response: choices[0].message.content
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not content:
            logger.warning("vLLM returned empty content call_id=%s raw_response=%s",
                           call_id, json.dumps(data, ensure_ascii=False)[:2000])
            return (False, 200, "vLLM returned empty response")

        # ---- Log full response content ----
        usage = data.get("usage", {})
        logger.info("vLLM usage call_id=%s prompt_tokens=%s completion_tokens=%s total=%s elapsed=%dms",
                     call_id,
                     usage.get("prompt_tokens", "?"),
                     usage.get("completion_tokens", "?"),
                     usage.get("total_tokens", "?"),
                     elapsed_ms)
        logger.info("vLLM response_content call_id=%s content=%s",
                     call_id, content[:3000])

        return (True, 200, content)

    except requests.exceptions.Timeout:
        logger.error("vLLM timeout call_id=%s after %ds", call_id, VLLM_TIMEOUT)
        return (False, 0, f"vLLM request timed out after {VLLM_TIMEOUT}s")
    except requests.exceptions.ConnectionError as e:
        logger.error("vLLM connection error call_id=%s: %s", call_id, e)
        return (False, 0, f"vLLM connection failed: {e}")
    except Exception as e:
        logger.exception("vLLM unexpected error call_id=%s: %s", call_id, e)
        return (False, 0, f"vLLM error: {e}")


# ---------------------------------------------------------------------------
# Unified entry point — drop-in replacement for query_aide_api()
# ---------------------------------------------------------------------------

def query_llm(prompt: str) -> Tuple[bool, int, str]:
    """
    Route LLM calls to the configured backend.
    Returns (ok, status_code, text_or_raw) — same signature as the
    original query_aide_api() in views.py.
    """
    if LLM_BACKEND == "vllm":
        return _query_vllm(prompt)
    else:
        return _query_aide(prompt)


# Backward-compatible alias so existing `from genai.llm_backend import query_aide_api` works
query_aide_api = query_llm
