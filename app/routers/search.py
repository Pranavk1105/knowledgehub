"""Full-text search endpoint with result caching and permission filtering."""

import hashlib
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import auth
from app.cache import cache_get, cache_set
from app.database import get_db
from app.models import Document, Permission, Role, User
from app.schemas import SearchResponse
from app.search import search_engine

router = APIRouter(prefix="/search", tags=["search"])


def _visible_document_ids(db: Session, user: User) -> set:
    """Documents the user owns, was granted access to, or (if admin) all of them."""
    if user.role == Role.admin:
        return {row[0] for row in db.query(Document.id).all()}
    owned = {row[0] for row in db.query(Document.id).filter(Document.owner_id == user.id)}
    shared = {
        row[0]
        for row in db.query(Permission.document_id).filter(Permission.user_id == user.id)
    }
    return owned | shared


@router.get("", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    started = time.perf_counter()

    # Cache key is namespaced per user so permission-filtered results never leak.
    raw_key = f"{user.id}:{limit}:{q.lower().strip()}"
    cache_key = "search:" + hashlib.sha256(raw_key.encode()).hexdigest()

    cached = cache_get(cache_key)
    if cached is not None:
        cached["cached"] = True
        cached["took_ms"] = int((time.perf_counter() - started) * 1000)
        return cached

    allowed = _visible_document_ids(db, user)
    hits = search_engine.search(q, limit=limit, allowed_ids=allowed)

    response = {
        "query": q,
        "total": len(hits),
        "took_ms": int((time.perf_counter() - started) * 1000),
        "cached": False,
        "hits": hits,
    }
    cache_set(cache_key, response)
    return response
