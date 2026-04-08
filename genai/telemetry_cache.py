"""
Telemetry caching layer — Strategy 4: Time-Quantised Instant Cache
Inspired by https://mirastacklabs.ai/blog/chunk-split-caching/

Instant PromQL queries are quantised to N-second buckets so that
multiple callers evaluating the same query within the same time window
share a single cache entry.  Uses gzip compression for payloads > 1 KB.

Phase 2b additions:
  - Circuit breaker per backend (closed → open → half-open)
  - Exponential-backoff retries with jitter
  - Stale-on-failure: shadow key with 5× TTL, served when backend is down
  - Pooled HTTP sessions with enforced connect/read timeouts

Phase 2c additions:
  - Stale-while-revalidate: serves cached data while background thread refreshes
  - Cache purge helpers (by prefix or full flush)
"""

import gzip
import hashlib
import json
import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests as _requests
from django.core.cache import cache

logger = logging.getLogger("telemetry_cache")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INSTANT_QUANTISE_SECONDS = 60           # snap evaluation time to 60-second buckets
INSTANT_CACHE_TTL = 60                  # seconds — one scrape cycle
METADATA_CACHE_TTL = 120                # seconds — labels, service lists
STALE_TTL_MULTIPLIER = 5                # shadow (stale) key lives 5× the normal TTL
GZIP_THRESHOLD_BYTES = 1024             # compress if serialised result > 1 KB
GZIP_MAX_BYTES = 15 * 1024 * 1024       # skip caching if > 15 MB
CACHE_KEY_PREFIX = "tc:"                # telemetry cache prefix

# Retry defaults
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.3                  # seconds
RETRY_MAX_DELAY = 4.0                   # seconds

# Circuit-breaker defaults
CB_FAILURE_THRESHOLD = 5                # consecutive failures to trip
CB_RECOVERY_TIMEOUT = 30                # seconds in open state before half-open probe
CB_HALF_OPEN_MAX = 1                    # max concurrent probes when half-open

# Background revalidation thread pool (bounded to avoid runaway threads)
_revalidation_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tc-revalidate")

# ---------------------------------------------------------------------------
# Shared counters stored in Valkey (cross-worker, atomic INCR)
# ---------------------------------------------------------------------------
_COUNTER_KEY_PREFIX = "tc:stats:"
_COUNTER_NAMES = [
    "instant_hits",
    "instant_misses",
    "instant_sets",
    "batch_hits",
    "batch_misses",
    "batch_sets",
    "meta_hits",
    "meta_misses",
    "meta_sets",
    "compressed_writes",
    "bytes_saved",           # raw - compressed
    "stale_hits",            # served stale data on failure
    "circuit_trips",         # circuit breaker trips to open
    "retries",               # total retry attempts
    "revalidations",         # stale-while-revalidate background fetches
    "purges",                # manual cache purges
]


def _get_valkey_client():
    """Return the raw Valkey/Redis client for atomic counter ops."""
    try:
        return cache.client.get_client()
    except Exception:
        return None


def _inc(key: str, amount: int = 1) -> None:
    """Atomically increment a counter in Valkey (shared across workers)."""
    try:
        client = _get_valkey_client()
        if client:
            client.incrby(f"{_COUNTER_KEY_PREFIX}{key}", amount)
    except Exception:
        pass  # best-effort — don't break cache operations for stats


def _get_counters() -> Dict[str, int]:
    """Fetch all counters from Valkey in a single pipeline round-trip."""
    result = {name: 0 for name in _COUNTER_NAMES}
    try:
        client = _get_valkey_client()
        if client:
            pipe = client.pipeline(transaction=False)
            for name in _COUNTER_NAMES:
                pipe.get(f"{_COUNTER_KEY_PREFIX}{name}")
            values = pipe.execute()
            for name, val in zip(_COUNTER_NAMES, values):
                result[name] = int(val) if val else 0
    except Exception:
        pass  # return zeros on failure
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _quantise(ts: float, bucket_seconds: int) -> int:
    """Snap a Unix timestamp to the nearest lower bucket boundary."""
    return int(ts // bucket_seconds) * bucket_seconds


def _cache_key(prefix: str, query: str, quantised_ts: int) -> str:
    """Deterministic cache key from query text and quantised timestamp."""
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return f"{CACHE_KEY_PREFIX}{prefix}:{query_hash}:{quantised_ts}"


def _compress(data: bytes) -> bytes:
    """Gzip-compress data."""
    return gzip.compress(data, compresslevel=6)


def _decompress(data: bytes) -> bytes:
    """Decompress if gzip, otherwise return as-is."""
    if isinstance(data, (bytes, memoryview)):
        raw = bytes(data)
        if raw[:2] == b'\x1f\x8b':  # gzip magic bytes
            return gzip.decompress(raw)
        return raw
    return data if isinstance(data, bytes) else data


def _serialise(value: Any) -> Tuple[bytes, bool]:
    """JSON-serialise and optionally gzip. Returns (data, was_compressed)."""
    raw = json.dumps(value, separators=(",", ":"), default=str).encode("utf-8")
    if len(raw) > GZIP_MAX_BYTES:
        return b"", False  # too large, skip
    if len(raw) > GZIP_THRESHOLD_BYTES:
        compressed = _compress(raw)
        _inc("compressed_writes")
        _inc("bytes_saved", len(raw) - len(compressed))
        return compressed, True
    return raw, False


def _deserialise(raw: Any) -> Any:
    """Decompress and JSON-parse."""
    if raw is None:
        return None
    try:
        decompressed = _decompress(raw if isinstance(raw, bytes) else
                                   raw.encode("utf-8") if isinstance(raw, str) else raw)
        return json.loads(decompressed)
    except Exception:
        return None


def _stale_key(primary_key: str) -> str:
    """Shadow key for stale-on-failure fallback."""
    return f"{primary_key}:stale"


def _set_with_stale(key: str, serialised: bytes, ttl: int) -> None:
    """Write primary key *and* a shadow stale key with a longer TTL."""
    cache.set(key, serialised, timeout=ttl)
    cache.set(_stale_key(key), serialised, timeout=ttl * STALE_TTL_MULTIPLIER)


def _get_stale(key: str) -> Any:
    """Return stale (shadow) cached value, or None."""
    raw = cache.get(_stale_key(key))
    if raw is not None:
        result = _deserialise(raw)
        if result is not None:
            _inc("stale_hits")
            logger.info("serving STALE data for %s", key)
            return result
    return None


# ---------------------------------------------------------------------------
# Circuit Breaker (per-backend)
# ---------------------------------------------------------------------------
class CircuitBreaker:
    """
    Three-state breaker: CLOSED → OPEN → HALF_OPEN → CLOSED.
    - CLOSED:    requests pass through; consecutive failures counted.
    - OPEN:      requests blocked (raise fast); after recovery_timeout → half open.
    - HALF_OPEN: one probe request allowed; success → CLOSED, failure → OPEN.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        name: str,
        failure_threshold: int = CB_FAILURE_THRESHOLD,
        recovery_timeout: float = CB_RECOVERY_TIMEOUT,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = self.CLOSED
        self._failures = 0
        self._last_failure_time: float = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    logger.info("circuit %s → HALF_OPEN (probing)", self.name)
            return self._state

    def allow_request(self) -> bool:
        return self.state != self.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._state != self.CLOSED:
                logger.info("circuit %s → CLOSED", self.name)
            self._state = self.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self.failure_threshold and self._state == self.CLOSED:
                self._state = self.OPEN
                _inc("circuit_trips")
                logger.warning(
                    "circuit %s → OPEN after %d failures (recovery in %ds)",
                    self.name, self._failures, self.recovery_timeout,
                )
            elif self._state == self.HALF_OPEN:
                self._state = self.OPEN
                logger.warning("circuit %s half-open probe FAILED → OPEN", self.name)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "consecutive_failures": self._failures,
                "last_failure": self._last_failure_time,
            }


# One breaker per backend
_breakers: Dict[str, CircuitBreaker] = {
    "victoriametrics": CircuitBreaker("victoriametrics"),
    "elasticsearch": CircuitBreaker("elasticsearch"),
    "jaeger": CircuitBreaker("jaeger"),
}


def get_breaker(backend: str) -> CircuitBreaker:
    if backend not in _breakers:
        _breakers[backend] = CircuitBreaker(backend)
    return _breakers[backend]


# ---------------------------------------------------------------------------
# Retry with exponential back-off + jitter
# ---------------------------------------------------------------------------

def _retry_with_backoff(
    fetch_fn: Callable[[], Any],
    breaker: CircuitBreaker,
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    base_delay: float = RETRY_BASE_DELAY,
    max_delay: float = RETRY_MAX_DELAY,
) -> Any:
    """
    Call *fetch_fn* up to *max_attempts* times with exponential back-off.
    Respects the circuit breaker: if open, raises immediately.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        if not breaker.allow_request():
            logger.debug("circuit %s OPEN — skipping attempt %d", breaker.name, attempt)
            break

        try:
            result = fetch_fn()
            breaker.record_success()
            return result
        except Exception as exc:
            last_exc = exc
            breaker.record_failure()
            if attempt < max_attempts - 1:
                _inc("retries")
                delay = min(base_delay * (2 ** attempt), max_delay)
                jitter = delay * random.uniform(0.5, 1.0)
                logger.info(
                    "retry %d/%d for %s (%.2fs): %s",
                    attempt + 1, max_attempts, breaker.name, jitter, exc,
                )
                time.sleep(jitter)

    if last_exc:
        raise last_exc
    raise RuntimeError(f"circuit {breaker.name} is open")


# ---------------------------------------------------------------------------
# Pooled HTTP sessions (connection reuse + enforced timeouts)
# ---------------------------------------------------------------------------
_session_lock = threading.Lock()
_sessions: Dict[str, _requests.Session] = {}


def get_http_session(backend: str) -> _requests.Session:
    """
    Return a long-lived requests.Session per backend for connection pooling.
    The caller should still pass timeout= per call.
    """
    with _session_lock:
        if backend not in _sessions:
            s = _requests.Session()
            adapter = _requests.adapters.HTTPAdapter(
                pool_connections=5,
                pool_maxsize=10,
                max_retries=0,  # we handle retries ourselves
            )
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            _sessions[backend] = s
        return _sessions[backend]


# ---------------------------------------------------------------------------
# Cache purge helpers  (Phase 2c)
# ---------------------------------------------------------------------------

def purge_cache(prefix: Optional[str] = None) -> Dict[str, int]:
    """
    Delete cached keys.
    - prefix=None → flush all tc: keys (except counter keys)
    - prefix="iq" → flush only instant query keys
    - prefix="meta" → flush only metadata keys
    Returns {"deleted": N}.
    """
    deleted = 0
    try:
        client = cache.client.get_client()
        pattern = f"*{CACHE_KEY_PREFIX}{prefix + ':' if prefix else ''}*"
        keys = [
            k for k in client.scan_iter(match=pattern, count=500)
            if _COUNTER_KEY_PREFIX.encode() not in (k if isinstance(k, bytes) else k.encode())
        ]
        if keys:
            deleted = client.delete(*keys)
        _inc("purges")
        logger.info("cache purge (prefix=%s): deleted %d keys", prefix, deleted)
    except Exception as exc:
        logger.warning("cache purge failed: %s", exc)
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# Strategy 4: Time-Quantised Instant Cache
# ---------------------------------------------------------------------------

def instant_cache_get(query: str) -> Tuple[bool, Any]:
    """
    Check cache for a quantised instant query result.
    Returns (hit: bool, result: Any).
    """
    if not query:
        return False, None
    now = time.time()
    qt = _quantise(now, INSTANT_QUANTISE_SECONDS)
    key = _cache_key("iq", query, qt)
    raw = cache.get(key)
    if raw is not None:
        result = _deserialise(raw)
        if result is not None:
            logger.debug("instant cache HIT: %s", key)
            _inc("instant_hits")
            return True, result
    _inc("instant_misses")
    return False, None


def instant_cache_set(query: str, result: Any) -> None:
    """Store an instant query result under the current quantised bucket + stale shadow."""
    if not query:
        return
    now = time.time()
    qt = _quantise(now, INSTANT_QUANTISE_SECONDS)
    key = _cache_key("iq", query, qt)
    serialised, _ = _serialise(result)
    if not serialised:
        return  # too large or empty
    _set_with_stale(key, serialised, INSTANT_CACHE_TTL)
    _inc("instant_sets")
    logger.debug("instant cache SET: %s (ttl=%ds, size=%d)", key, INSTANT_CACHE_TTL, len(serialised))


def instant_cache_get_or_fetch(
    query: str,
    fetch_fn,
    backend: str = "victoriametrics",
) -> Any:
    """
    Check cache first; on miss, call fetch_fn(query) with:
      - circuit breaker check
      - retry with exponential back-off
      - stale-on-failure fallback
    This is the primary entry point for Strategy 4.
    """
    hit, result = instant_cache_get(query)
    if hit:
        return result

    breaker = get_breaker(backend)

    # Fast-fail if circuit is open: serve stale or empty
    if not breaker.allow_request():
        now = time.time()
        qt = _quantise(now, INSTANT_QUANTISE_SECONDS)
        key = _cache_key("iq", query, qt)
        stale = _get_stale(key)
        if stale is not None:
            return stale
        logger.warning("circuit %s OPEN and no stale data for %s", backend, query[:80])
        return {}

    try:
        result = _retry_with_backoff(
            lambda: fetch_fn(query),
            breaker,
        )
    except Exception as exc:
        logger.warning("all retries exhausted for %s: %s — trying stale", backend, exc)
        now = time.time()
        qt = _quantise(now, INSTANT_QUANTISE_SECONDS)
        key = _cache_key("iq", query, qt)
        stale = _get_stale(key)
        if stale is not None:
            return stale
        return {"error": str(exc)}

    if result and not (isinstance(result, dict) and "error" in result):
        instant_cache_set(query, result)
    return result


# ---------------------------------------------------------------------------
# Batch MGET — Pipeline lookup for multiple queries at once
# ---------------------------------------------------------------------------

def instant_cache_batch_get(queries: List[str]) -> Dict[str, Any]:
    """
    Batch-check cache for multiple queries.  Uses pipeline MGET when the
    cache backend supports get_many.
    Returns {query: result} for cache hits only.
    """
    if not queries:
        return {}
    now = time.time()
    qt = _quantise(now, INSTANT_QUANTISE_SECONDS)
    key_map = {}  # cache_key -> query
    for q in queries:
        if q:
            key = _cache_key("iq", q, qt)
            key_map[key] = q

    if not key_map:
        return {}

    # get_many does pipeline MGET in django_redis / django-valkey
    raw_results = cache.get_many(list(key_map.keys()))
    hits = {}
    for key, raw in raw_results.items():
        if raw is not None:
            result = _deserialise(raw)
            if result is not None:
                query = key_map[key]
                hits[query] = result
    _inc("batch_hits", len(hits))
    _inc("batch_misses", len(key_map) - len(hits))
    if hits:
        logger.info("instant cache batch: %d/%d hits", len(hits), len(key_map))
    return hits


def instant_cache_batch_set(results: Dict[str, Any]) -> None:
    """Batch-store multiple query results (primary + stale shadow)."""
    if not results:
        return
    now = time.time()
    qt = _quantise(now, INSTANT_QUANTISE_SECONDS)
    to_set = {}
    stale_set = {}
    for query, result in results.items():
        if query and result and not (isinstance(result, dict) and "error" in result):
            key = _cache_key("iq", query, qt)
            serialised, _ = _serialise(result)
            if serialised:
                to_set[key] = serialised
                stale_set[_stale_key(key)] = serialised
    if to_set:
        cache.set_many(to_set, timeout=INSTANT_CACHE_TTL)
        cache.set_many(stale_set, timeout=INSTANT_CACHE_TTL * STALE_TTL_MULTIPLIER)
        _inc("batch_sets", len(to_set))
        logger.info("instant cache batch SET: %d entries", len(to_set))


# ---------------------------------------------------------------------------
# Strategy 5: Simple TTL Cache (metadata/non-time-series)
# ---------------------------------------------------------------------------

def metadata_cache_get_or_fetch(
    cache_prefix: str,
    cache_id: str,
    fetch_fn,
    ttl: int = METADATA_CACHE_TTL,
    backend: str = "elasticsearch",
    stale_while_revalidate: bool = True,
) -> Any:
    """
    TTL cache for metadata queries (ES logs, Jaeger traces, etc.).

    Phase 2b: circuit breaker + retry + stale-on-failure.
    Phase 2c: stale-while-revalidate — if primary key expired but stale key
    exists, return stale immediately and schedule a background refresh.
    """
    key = f"{CACHE_KEY_PREFIX}meta:{cache_prefix}:{hashlib.sha256(cache_id.encode()).hexdigest()[:16]}"

    # ── primary cache hit ──
    raw = cache.get(key)
    if raw is not None:
        result = _deserialise(raw)
        if result is not None:
            _inc("meta_hits")
            return result

    _inc("meta_misses")

    # ── stale-while-revalidate (Phase 2c) ──
    stale_result = _get_stale(key) if stale_while_revalidate else None
    if stale_result is not None:
        # Serve stale now; kick off background refresh
        def _bg_revalidate():
            try:
                breaker = get_breaker(backend)
                fresh = _retry_with_backoff(fetch_fn, breaker)
                if fresh and not (isinstance(fresh, dict) and "error" in fresh):
                    ser, _ = _serialise(fresh)
                    if ser:
                        _set_with_stale(key, ser, ttl)
                        _inc("meta_sets")
                _inc("revalidations")
                logger.debug("background revalidation done for %s", key)
            except Exception as exc:
                logger.info("background revalidation failed for %s: %s", key, exc)

        _revalidation_pool.submit(_bg_revalidate)
        return stale_result

    # ── no cache at all — fetch with protection ──
    breaker = get_breaker(backend)
    if not breaker.allow_request():
        logger.warning("circuit %s OPEN, no stale data for %s", backend, key)
        return {}

    try:
        result = _retry_with_backoff(fetch_fn, breaker)
    except Exception as exc:
        logger.warning("metadata fetch failed for %s: %s", backend, exc)
        return {"error": str(exc)}

    if result and not (isinstance(result, dict) and "error" in result):
        serialised, _ = _serialise(result)
        if serialised:
            _set_with_stale(key, serialised, ttl)
            _inc("meta_sets")
    return result


# ---------------------------------------------------------------------------
# Stats / observability
# ---------------------------------------------------------------------------

def get_cache_stats() -> Dict[str, Any]:
    """
    Return comprehensive cache stats: hit/miss counters, Valkey memory,
    active key counts by prefix.
    """
    counters = _get_counters()
    total_hits = counters["instant_hits"] + counters["batch_hits"] + counters["meta_hits"]
    total_misses = counters["instant_misses"] + counters["batch_misses"] + counters["meta_misses"]
    total = total_hits + total_misses
    hit_rate = round(total_hits / total * 100, 1) if total else 0.0

    stats: Dict[str, Any] = {
        "counters": counters,
        "summary": {
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_requests": total,
            "hit_rate_pct": hit_rate,
        },
        "config": {
            "instant_quantise_seconds": INSTANT_QUANTISE_SECONDS,
            "instant_cache_ttl": INSTANT_CACHE_TTL,
            "metadata_cache_ttl": METADATA_CACHE_TTL,
            "stale_ttl_multiplier": STALE_TTL_MULTIPLIER,
            "gzip_threshold_bytes": GZIP_THRESHOLD_BYTES,
            "retry_max_attempts": RETRY_MAX_ATTEMPTS,
            "cb_failure_threshold": CB_FAILURE_THRESHOLD,
            "cb_recovery_timeout": CB_RECOVERY_TIMEOUT,
        },
        "circuit_breakers": {
            name: cb.snapshot() for name, cb in _breakers.items()
        },
    }

    # Valkey memory + key scan
    try:
        client = cache.client.get_client()
        info = client.info("memory")
        stats["valkey"] = {
            "connected": True,
            "used_memory_human": info.get("used_memory_human", "unknown"),
            "used_memory_peak_human": info.get("used_memory_peak_human", "unknown"),
            "used_memory_bytes": info.get("used_memory", 0),
        }
        # Count keys by prefix using SCAN (non-blocking)
        prefix_counts: Dict[str, int] = {"iq": 0, "meta": 0, "stale": 0, "other": 0}
        # django_redis prefixes keys with ":1:" by default
        for key in client.scan_iter(match="*tc:*", count=500):
            key_str = key.decode() if isinstance(key, bytes) else key
            # skip counter keys — they're not cache entries
            if "tc:stats:" in key_str:
                continue
            if ":stale" in key_str:
                prefix_counts["stale"] += 1
            elif ":tc:iq:" in key_str:
                prefix_counts["iq"] += 1
            elif ":tc:meta:" in key_str:
                prefix_counts["meta"] += 1
            else:
                prefix_counts["other"] += 1
        stats["valkey"]["key_counts"] = prefix_counts
        stats["valkey"]["total_tc_keys"] = sum(prefix_counts.values())

        # DB-wide key count
        db_size = client.dbsize()
        stats["valkey"]["total_db_keys"] = db_size
    except Exception as exc:
        stats["valkey"] = {"connected": False, "error": str(exc)}

    return stats
