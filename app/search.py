"""
Full-text search layer backed by Elasticsearch.

The module owns the document index lifecycle (mapping, upsert, delete) and the
query path. As with the cache, it degrades gracefully: if Elasticsearch is not
reachable it falls back to the pure-Python inverted index in
`app.services.inverted_index`, so search keeps functioning for the demo.
"""

import logging
from typing import List, Optional

from app.config import settings
from app.services.inverted_index import InvertedIndex

logger = logging.getLogger("knowledgehub.search")

# Mapping tuned for technical knowledge articles: an English analyzer for the
# body, a keyword sub-field on the title for exact filtering, and tags as
# keywords for faceting.
_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "title": {
                "type": "text",
                "analyzer": "english",
                "fields": {"raw": {"type": "keyword"}},
            },
            "content": {"type": "text", "analyzer": "english"},
            "tags": {"type": "keyword"},
            "space_id": {"type": "keyword"},
            "owner_id": {"type": "keyword"},
            "updated_at": {"type": "date"},
        }
    }
}


class SearchEngine:
    def __init__(self) -> None:
        self.index_name = settings.elasticsearch_index
        self.es = self._connect()
        # Always keep a local inverted index as the fallback / offline engine.
        self._fallback = InvertedIndex()
        if self.es is not None:
            self._ensure_index()

    # --------------------------------------------------------------------- #
    # Connection / index management
    # --------------------------------------------------------------------- #
    def _connect(self):
        try:
            from elasticsearch import Elasticsearch

            es = Elasticsearch(settings.elasticsearch_url, request_timeout=3)
            if es.ping():
                logger.info("Connected to Elasticsearch at %s", settings.elasticsearch_url)
                return es
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("Elasticsearch unavailable (%s); using local index", exc)
        return None

    def _ensure_index(self) -> None:
        try:
            if not self.es.indices.exists(index=self.index_name):
                self.es.indices.create(
                    index=self.index_name, mappings=_INDEX_MAPPING["mappings"]
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not ensure ES index: %s", exc)

    @property
    def backend(self) -> str:
        return "elasticsearch" if self.es is not None else "inverted-index"

    # --------------------------------------------------------------------- #
    # Indexing
    # --------------------------------------------------------------------- #
    def index_document(self, doc: dict) -> None:
        """Upsert a document into the search index. `doc` carries id/title/content/tags."""
        self._fallback.add(
            doc["id"], f"{doc['title']} {doc['content']}", title=doc["title"]
        )
        if self.es is None:
            return
        try:
            self.es.index(
                index=self.index_name,
                id=doc["id"],
                document={
                    "title": doc["title"],
                    "content": doc["content"],
                    "tags": doc.get("tags", []),
                    "space_id": doc.get("space_id"),
                    "owner_id": doc.get("owner_id"),
                    "updated_at": doc.get("updated_at"),
                },
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("ES index failed for %s: %s", doc["id"], exc)

    def delete_document(self, doc_id: str) -> None:
        self._fallback.remove(doc_id)
        if self.es is None:
            return
        try:
            self.es.delete(index=self.index_name, id=doc_id, ignore=[404])
        except Exception as exc:  # pragma: no cover
            logger.warning("ES delete failed for %s: %s", doc_id, exc)

    # --------------------------------------------------------------------- #
    # Querying
    # --------------------------------------------------------------------- #
    def search(self, query: str, limit: int = 10, allowed_ids: Optional[set] = None) -> List[dict]:
        """
        Return ranked hits. If `allowed_ids` is provided the result set is
        restricted to documents the caller is permitted to see (authorization
        is enforced at the data layer, not only in the UI).
        """
        if self.es is not None:
            hits = self._search_es(query, limit, allowed_ids)
            if hits is not None:
                return hits
        return self._search_fallback(query, limit, allowed_ids)

    def _search_es(self, query: str, limit: int, allowed_ids: Optional[set]):
        try:
            must = [
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "content"],
                        "fuzziness": "AUTO",
                    }
                }
            ]
            bool_query = {"bool": {"must": must}}
            if allowed_ids is not None:
                bool_query["bool"]["filter"] = [
                    {"ids": {"values": list(allowed_ids)}}
                ]
            # elasticsearch-py 8.x: pass query/highlight/size as explicit kwargs.
            # (The legacy `body=` kwarg silently conflicts with these and drops
            # the query, so we avoid it entirely.)
            resp = self.es.search(
                index=self.index_name,
                query=bool_query,
                size=limit,
                highlight={"fields": {"content": {}}},
            )
            results = []
            for hit in resp["hits"]["hits"]:
                highlight = None
                if "highlight" in hit and hit["highlight"].get("content"):
                    highlight = " … ".join(hit["highlight"]["content"])
                results.append(
                    {
                        "document_id": hit["_id"],
                        "title": hit["_source"]["title"],
                        "score": hit["_score"],
                        "highlight": highlight,
                    }
                )
            return results
        except Exception as exc:  # pragma: no cover
            logger.warning("ES search failed (%s); falling back", exc)
            return None

    def _search_fallback(self, query: str, limit: int, allowed_ids: Optional[set]):
        ranked = self._fallback.search(query)
        results = []
        for doc_id, score, snippet in ranked:
            if allowed_ids is not None and doc_id not in allowed_ids:
                continue
            results.append(
                {
                    "document_id": doc_id,
                    "title": self._fallback.title_of(doc_id),
                    "score": round(score, 4),
                    "highlight": snippet,
                }
            )
            if len(results) >= limit:
                break
        return results


# Singleton used across the app.
search_engine = SearchEngine()
