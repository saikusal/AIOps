"""
Track 3.7 — Vector Backend Abstraction
========================================
Provides a clean interface for vector similarity search so the control plane
is not coupled to a specific vector engine.

Design:
  - Abstract VectorBackend interface:
      upsert(collection, id, vector, metadata)
      search(collection, vector, limit, filters)
      delete(collection, id)
      health_check()
  - PgvectorBackend  — early implementation using pgvector extension on Postgres.
      No external service required. Safe for Docker single-node deployments.
  - WeaviateBackend  — migration target for production-scale semantic retrieval.
  - get_vector_backend() factory — controlled by VECTOR_BACKEND env var.

Collections (logical namespaces):
  code_embeddings        source: CodeChangeRecord, RepositoryIndex symbols
  runbook_embeddings     source: Runbook content
  incident_memory        source: resolved InvestigationRun summaries

Separation rule:
  - Postgres remains the canonical metadata store.
  - Vectors reference Postgres IDs but are stored in the vector backend.
  - Deleting from Postgres does NOT cascade to vectors automatically;
    lifecycle jobs own that cleanup.

Environment variables:
  VECTOR_BACKEND          pgvector | weaviate | none   (default: pgvector)
  PGVECTOR_DIMENSIONS     embedding dimensions          (default: 1536)
  WEAVIATE_URL            http://weaviate:8080          (default)
  WEAVIATE_API_KEY        optional API key for WCS
  VECTOR_EMBED_MODEL      model name hint               (default: text-embedding-3-small)
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vector_backend")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
VECTOR_BACKEND: str = os.environ.get("VECTOR_BACKEND", "pgvector")
PGVECTOR_DIMENSIONS: int = int(os.environ.get("PGVECTOR_DIMENSIONS", "1536"))
WEAVIATE_URL: str = os.environ.get("WEAVIATE_URL", "http://weaviate:8080")
WEAVIATE_API_KEY: Optional[str] = os.environ.get("WEAVIATE_API_KEY")
VECTOR_EMBED_MODEL: str = os.environ.get("VECTOR_EMBED_MODEL", "text-embedding-3-small")

# Supported logical collections — add new ones here as capabilities expand
VECTOR_COLLECTIONS = [
    "code_embeddings",
    "runbook_embeddings",
    "incident_memory",
]


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class VectorBackend(ABC):
    """
    Abstract interface for vector storage and retrieval.
    All implementations must be interchangeable behind this contract.
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend identifier."""

    @abstractmethod
    def upsert(
        self,
        collection: str,
        object_id: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Insert or update a vector entry.

        Args:
            collection: Logical collection name (e.g. 'code_embeddings').
            object_id:  Stable external ID (e.g. Postgres UUID).
            vector:     Embedding vector as list of floats.
            metadata:   Arbitrary JSON-serialisable metadata stored alongside.

        Returns True on success.
        """

    @abstractmethod
    def search(
        self,
        collection: str,
        vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform approximate nearest-neighbour search.

        Returns a list of dicts:
          {object_id, score, metadata}
        ordered by descending similarity score.
        """

    @abstractmethod
    def delete(self, collection: str, object_id: str) -> bool:
        """Delete an entry by object_id. Returns True if deleted."""

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """Returns {"healthy": bool, "backend": str, "detail": str}."""


# ---------------------------------------------------------------------------
# Pgvector backend (early implementation)
# ---------------------------------------------------------------------------

class PgvectorBackend(VectorBackend):
    """
    Stores vectors in a Postgres table using the pgvector extension.

    Schema (created on first use if the extension is available):
      CREATE TABLE IF NOT EXISTS vector_store (
          id          BIGSERIAL PRIMARY KEY,
          collection  VARCHAR(120) NOT NULL,
          object_id   VARCHAR(64)  NOT NULL,
          vector      vector(<dimensions>),
          metadata    JSONB DEFAULT '{}',
          created_at  TIMESTAMPTZ DEFAULT now(),
          updated_at  TIMESTAMPTZ DEFAULT now(),
          UNIQUE (collection, object_id)
      );

    This does NOT use a Django model to keep the vector schema decoupled
    from the relational control-plane schema. It manages its own table
    via raw SQL so it can be migrated to a separate engine later without
    touching Django migrations.
    """

    TABLE = "vector_store"

    def __init__(self, dimensions: int = PGVECTOR_DIMENSIONS):
        self._dims = dimensions
        self._initialised = False

    @property
    def backend_name(self) -> str:
        return "pgvector"

    def _conn(self):
        """Return a Django DB connection. Uses the default database."""
        from django.db import connection
        return connection

    def _ensure_schema(self) -> None:
        if self._initialised:
            return
        conn = self._conn()
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE} (
                        id          BIGSERIAL PRIMARY KEY,
                        collection  VARCHAR(120) NOT NULL,
                        object_id   VARCHAR(64)  NOT NULL,
                        vector      vector({self._dims}),
                        metadata    JSONB DEFAULT '{{}}',
                        created_at  TIMESTAMPTZ DEFAULT now(),
                        updated_at  TIMESTAMPTZ DEFAULT now(),
                        UNIQUE (collection, object_id)
                    );
                """)
                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS vector_store_hnsw_idx
                    ON {self.TABLE} USING hnsw (vector vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
                """)
                conn.connection.commit()
                self._initialised = True
                logger.info("pgvector schema initialised (dims=%d)", self._dims)
            except Exception as exc:
                logger.warning("pgvector schema setup failed (extension may not be installed): %s", exc)
                conn.connection.rollback()
                self._initialised = True  # don't retry repeatedly

    def upsert(
        self,
        collection: str,
        object_id: str,
        vector: List[float],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        import json as _json
        self._ensure_schema()
        meta_str = _json.dumps(metadata or {})
        vector_str = f"[{','.join(str(v) for v in vector)}]"
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {self.TABLE} (collection, object_id, vector, metadata, updated_at)
                    VALUES (%s, %s, %s::vector, %s::jsonb, now())
                    ON CONFLICT (collection, object_id)
                    DO UPDATE SET vector = EXCLUDED.vector,
                                  metadata = EXCLUDED.metadata,
                                  updated_at = now();
                """, [collection, object_id, vector_str, meta_str])
                conn.connection.commit()
            return True
        except Exception as exc:
            conn.connection.rollback()
            logger.error("pgvector upsert failed: %s", exc)
            return False

    def search(
        self,
        collection: str,
        vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        import json as _json
        self._ensure_schema()
        vector_str = f"[{','.join(str(v) for v in vector)}]"
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT object_id,
                           1 - (vector <=> %s::vector) AS score,
                           metadata
                    FROM {self.TABLE}
                    WHERE collection = %s
                    ORDER BY vector <=> %s::vector
                    LIMIT %s;
                """, [vector_str, collection, vector_str, limit])
                rows = cur.fetchall()
            results = []
            for row in rows:
                obj_id, score, meta = row
                results.append({
                    "object_id": obj_id,
                    "score": float(score),
                    "metadata": meta if isinstance(meta, dict) else _json.loads(meta or "{}"),
                })
            return results
        except Exception as exc:
            logger.error("pgvector search failed: %s", exc)
            return []

    def delete(self, collection: str, object_id: str) -> bool:
        self._ensure_schema()
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {self.TABLE} WHERE collection = %s AND object_id = %s;",
                    [collection, object_id],
                )
                deleted = cur.rowcount
                conn.connection.commit()
            return deleted > 0
        except Exception as exc:
            conn.connection.rollback()
            logger.error("pgvector delete failed: %s", exc)
            return False

    def health_check(self) -> Dict[str, Any]:
        try:
            conn = self._conn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            return {"healthy": True, "backend": self.backend_name, "detail": "postgres reachable"}
        except Exception as exc:
            return {"healthy": False, "backend": self.backend_name, "detail": str(exc)}


# ---------------------------------------------------------------------------
# Weaviate backend (migration target)
# ---------------------------------------------------------------------------

class WeaviateBackend(VectorBackend):
    """
    Stores vectors in Weaviate via its v4 Python client.

    Collections map to Weaviate classes. Metadata is stored as Weaviate properties.
    object_id is stored in the Weaviate object UUID slot.

    Install requirement: pip install weaviate-client>=4.0
    """

    def __init__(self, url: str = WEAVIATE_URL, api_key: Optional[str] = WEAVIATE_API_KEY):
        self._url = url
        self._api_key = api_key
        self._client = None

    @property
    def backend_name(self) -> str:
        return "weaviate"

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import weaviate
            auth = weaviate.auth.AuthApiKey(self._api_key) if self._api_key else None
            self._client = weaviate.connect_to_custom(
                http_host=self._url.replace("http://", "").replace("https://", "").split(":")[0],
                http_port=int(self._url.split(":")[-1]) if ":" in self._url.split("//")[-1] else 8080,
                http_secure=self._url.startswith("https"),
                grpc_host=self._url.replace("http://", "").replace("https://", "").split(":")[0],
                grpc_port=50051,
                grpc_secure=False,
                auth_credentials=auth,
            )
            return self._client
        except Exception as exc:
            raise RuntimeError(f"Cannot connect to Weaviate at {self._url}: {exc}") from exc

    def _class_name(self, collection: str) -> str:
        """Weaviate class names must be PascalCase."""
        return "".join(word.capitalize() for word in collection.split("_"))

    def _ensure_collection(self, collection: str) -> None:
        client = self._get_client()
        class_name = self._class_name(collection)
        try:
            if not client.collections.exists(class_name):
                from weaviate.classes.config import Configure, Property, DataType
                client.collections.create(
                    name=class_name,
                    vectorizer_config=Configure.Vectorizer.none(),
                    properties=[
                        Property(name="object_id", data_type=DataType.TEXT),
                        Property(name="collection", data_type=DataType.TEXT),
                        Property(name="metadata_json", data_type=DataType.TEXT),
                    ],
                )
                logger.info("weaviate collection created: %s", class_name)
        except Exception as exc:
            logger.warning("weaviate ensure_collection failed: %s", exc)

    def upsert(self, collection, object_id, vector, metadata=None) -> bool:
        import json as _json
        try:
            self._ensure_collection(collection)
            client = self._get_client()
            col = client.collections.get(self._class_name(collection))
            col.data.insert(
                properties={
                    "object_id": object_id,
                    "collection": collection,
                    "metadata_json": _json.dumps(metadata or {}),
                },
                vector=vector,
                uuid=object_id,  # use object_id as deterministic UUID (must be UUID4 format)
            )
            return True
        except Exception as exc:
            logger.error("weaviate upsert failed: %s", exc)
            return False

    def search(self, collection, vector, limit=10, filters=None) -> List[Dict[str, Any]]:
        import json as _json
        try:
            self._ensure_collection(collection)
            client = self._get_client()
            col = client.collections.get(self._class_name(collection))
            results = col.query.near_vector(
                near_vector=vector,
                limit=limit,
                return_metadata=["certainty"],
            )
            out = []
            for obj in results.objects:
                props = obj.properties
                out.append({
                    "object_id": props.get("object_id", str(obj.uuid)),
                    "score": obj.metadata.certainty if obj.metadata else 0.0,
                    "metadata": _json.loads(props.get("metadata_json", "{}")),
                })
            return out
        except Exception as exc:
            logger.error("weaviate search failed: %s", exc)
            return []

    def delete(self, collection, object_id) -> bool:
        try:
            client = self._get_client()
            col = client.collections.get(self._class_name(collection))
            col.data.delete_by_id(object_id)
            return True
        except Exception as exc:
            logger.error("weaviate delete failed: %s", exc)
            return False

    def health_check(self) -> Dict[str, Any]:
        try:
            client = self._get_client()
            ready = client.is_ready()
            return {
                "healthy": ready,
                "backend": self.backend_name,
                "detail": "ready" if ready else "not ready",
            }
        except Exception as exc:
            return {"healthy": False, "backend": self.backend_name, "detail": str(exc)}


# ---------------------------------------------------------------------------
# No-op backend (graceful degradation when no vector engine is configured)
# ---------------------------------------------------------------------------

class NullVectorBackend(VectorBackend):
    """
    Silently discards all operations. Used when VECTOR_BACKEND=none.
    Allows the control plane to run without a vector engine configured.
    """

    @property
    def backend_name(self) -> str:
        return "none"

    def upsert(self, collection, object_id, vector, metadata=None) -> bool:
        return True

    def search(self, collection, vector, limit=10, filters=None) -> List[Dict[str, Any]]:
        return []

    def delete(self, collection, object_id) -> bool:
        return True

    def health_check(self) -> Dict[str, Any]:
        return {"healthy": True, "backend": self.backend_name, "detail": "no-op backend"}


# ---------------------------------------------------------------------------
# Factory — single entry point
# ---------------------------------------------------------------------------

_backend_instance: Optional[VectorBackend] = None


def get_vector_backend(force_backend: Optional[str] = None) -> VectorBackend:
    """
    Return the configured VectorBackend singleton.

    The control plane calls this instead of constructing backends directly.
    """
    global _backend_instance
    if _backend_instance is not None and force_backend is None:
        return _backend_instance

    chosen = force_backend or VECTOR_BACKEND

    if chosen == "pgvector":
        _backend_instance = PgvectorBackend()
    elif chosen == "weaviate":
        _backend_instance = WeaviateBackend()
    elif chosen == "none":
        _backend_instance = NullVectorBackend()
    else:
        logger.warning("Unknown VECTOR_BACKEND '%s', defaulting to none", chosen)
        _backend_instance = NullVectorBackend()

    logger.info("vector backend initialised: %s", _backend_instance.backend_name)
    return _backend_instance


def reset_vector_backend() -> None:
    """Force re-initialisation of the backend singleton (used in tests)."""
    global _backend_instance
    _backend_instance = None


# ---------------------------------------------------------------------------
# High-level helpers — used by the investigation loop and code-context engine
# ---------------------------------------------------------------------------

def embed_and_store(
    collection: str,
    object_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Generate an embedding for *text* and store it in the vector backend.
    Embedding is generated via the local vLLM embeddings endpoint if available,
    otherwise falls back to a zero-vector (no-op) so callers never crash.

    Args:
        collection: one of VECTOR_COLLECTIONS
        object_id:  stable ID referencing the source Postgres row
        text:       text to embed
        metadata:   any additional metadata to store alongside the vector
    """
    import os
    backend = get_vector_backend()
    if backend.backend_name == "none":
        return True

    vector = _generate_embedding(text)
    if vector is None:
        return False
    return backend.upsert(collection, object_id, vector, metadata)


def semantic_search(
    collection: str,
    query_text: str,
    limit: int = 10,
    filters: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Embed *query_text* and search the specified collection.
    Returns [] if embedding fails or backend is none.
    """
    backend = get_vector_backend()
    if backend.backend_name == "none":
        return []

    vector = _generate_embedding(query_text)
    if vector is None:
        return []
    return backend.search(collection, vector, limit=limit, filters=filters)


def _generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate an embedding vector for text.
    Tries the local vLLM embeddings endpoint first.
    Returns None on failure (callers should handle gracefully).
    """
    import os, json
    vllm_url = os.environ.get("VLLM_API_URL", "")
    embed_model = VECTOR_EMBED_MODEL

    if vllm_url:
        try:
            import requests as _req
            resp = _req.post(
                f"{vllm_url.rstrip('/')}/v1/embeddings",
                json={"model": embed_model, "input": text[:8192]},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
        except Exception as exc:
            logger.warning("vllm embedding failed: %s — returning None", exc)
            return None

    logger.debug("VLLM_API_URL not configured, skipping embedding")
    return None
