"""
Redis-backed cache with an automatic in-memory fallback.

If Redis is unreachable (e.g. running the demo without docker-compose) the
module transparently degrades to a process-local dictionary so the rest of the
application keeps working. Search results and hot document reads are cached
here to absorb read traffic before it reaches Postgres / Elasticsearch.
"""

import json
import logging
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("knowledgehub.cache")


class _MemoryCache:
    """Minimal dict-based fallback (no TTL eviction — fine for demos/tests)."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = None) -> None:  # noqa: ARG002
        self._store[key] = value

    def delete(self, *keys: str) -> None:
        for k in keys:
            self._store.pop(k, None)

    def scan_iter(self, match: str):
        prefix = match.rstrip("*")
        return [k for k in list(self._store) if k.startswith(prefix)]


def _build_client():
    try:
        import redis  # imported lazily so the package is optional

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        logger.info("Connected to Redis at %s", settings.redis_url)
        return client
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("Redis unavailable (%s); using in-memory cache fallback", exc)
        return _MemoryCache()


_client = _build_client()


def cache_get(key: str) -> Optional[Any]:
    raw = _client.get(key)
    return json.loads(raw) if raw else None


def cache_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    _client.set(key, json.dumps(value), ex=ttl or settings.cache_ttl_seconds)


def cache_delete(*keys: str) -> None:
    if keys:
        _client.delete(*keys)


def invalidate_prefix(prefix: str) -> None:
    """Drop every key under a namespace, e.g. all cached search results."""
    keys = list(_client.scan_iter(match=f"{prefix}*"))
    if keys:
        _client.delete(*keys)
