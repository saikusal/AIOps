"""
LLM Backend
============
Calls the self-hosted vLLM endpoint (OpenAI-compatible API).
Returns the same signature used throughout the codebase:
    (ok: bool, status_code: int, text: str)

"""

import json
import logging
import os
import time
import uuid
from typing import Tuple

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger("llm_backend")

# ---------------------------------------------------------------------------
# vLLM configuration
# ---------------------------------------------------------------------------
VLLM_API_URL     = os.getenv("VLLM_API_URL", "http://localhost:8001/v1/chat/completions")
VLLM_API_KEY     = os.getenv("VLLM_API_KEY", "")
VLLM_MODEL_NAME  = os.getenv("VLLM_MODEL_NAME", "qwen32b")
VLLM_TIMEOUT     = int(os.getenv("VLLM_TIMEOUT", "120"))
VLLM_MAX_TOKENS  = int(os.getenv("VLLM_MAX_TOKENS", "2048"))
VLLM_MAX_MODEL_LEN = int(os.getenv("VLLM_MAX_MODEL_LEN", "8192"))
VLLM_TEMPERATURE = float(os.getenv("VLLM_TEMPERATURE", "0.0"))

logger.info("LLM backend: vLLM  endpoint: %s  model: %s", VLLM_API_URL, VLLM_MODEL_NAME)

# ---------------------------------------------------------------------------
# vLLM Backend
# ---------------------------------------------------------------------------

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
    """Call self-hosted vLLM via OpenAI-compatible /v1/chat/completions."""
    call_id = f"vllm-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

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

    estimated_prompt_tokens = (len(system_msg) + len(prompt)) // 4 + 50
    safe_max_tokens = min(VLLM_MAX_TOKENS, max(256, VLLM_MAX_MODEL_LEN - estimated_prompt_tokens))
    if safe_max_tokens < VLLM_MAX_TOKENS:
        logger.info("vLLM auto-reduced max_tokens from %d to %d (est_prompt_tokens=%d, max_context=%d)",
                    VLLM_MAX_TOKENS, safe_max_tokens, estimated_prompt_tokens, VLLM_MAX_MODEL_LEN)

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
            logger.error("vLLM error call_id=%s status=%s body=%s",
                         call_id, resp.status_code, resp.text[:2000])
            return (False, resp.status_code, f"vLLM HTTP {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not content:
            logger.warning("vLLM returned empty content call_id=%s raw=%s",
                           call_id, json.dumps(data, ensure_ascii=False)[:2000])
            return (False, 200, "vLLM returned empty response")

        usage = data.get("usage", {})
        logger.info("vLLM usage call_id=%s prompt_tokens=%s completion_tokens=%s total=%s elapsed=%dms",
                    call_id, usage.get("prompt_tokens", "?"), usage.get("completion_tokens", "?"),
                    usage.get("total_tokens", "?"), elapsed_ms)
        logger.info("vLLM response_content call_id=%s content=%s", call_id, content[:3000])

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
# Unified entry point
# ---------------------------------------------------------------------------

def query_llm(prompt: str) -> Tuple[bool, int, str]:
    """Call vLLM. Returns (ok, status_code, text)."""
    return _query_vllm(prompt)
