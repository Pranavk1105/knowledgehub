"""Document CRUD, version history, and sharing endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app.cache import cache_get, cache_set, invalidate_prefix
from app.database import get_db
from app.models import (
    Document,
    DocumentVersion,
    Permission,
    PermissionLevel,
    User,
)
from app.schemas import (
    DocumentCreate,
    DocumentOut,
    DocumentUpdate,
    PermissionGrant,
    VersionOut,
)
from app.services import document_service as svc

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_doc_or_404(db: Session, doc_id: str) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("", response_model=DocumentOut, status_code=201)
def create(
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    doc = svc.create_document(
        db, user, payload.title, payload.content, payload.space_id, payload.tags
    )
    return svc.to_dict(doc)


@router.get("/{doc_id}", response_model=DocumentOut)
def read(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    cache_key = f"doc:{doc_id}"
    cached = cache_get(cache_key)
    if cached is None:
        doc = _get_doc_or_404(db, doc_id)
        auth.require_access(db, user, doc, PermissionLevel.viewer)
        data = svc.to_dict(doc)
        cache_set(cache_key, data)
        return data

    # Even on a cache hit we still enforce authorization against the DB ACL.
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.viewer)
    return cached


@router.put("/{doc_id}", response_model=DocumentOut)
def update(
    doc_id: str,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.editor)
    doc = svc.update_document(
        db, user, doc, payload.title, payload.content, payload.tags
    )
    return svc.to_dict(doc)


@router.delete("/{doc_id}", status_code=204)
def delete(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.owner)
    svc.delete_document(db, user, doc)


@router.get("/{doc_id}/versions", response_model=List[VersionOut])
def versions(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.viewer)
    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.version.desc())
        .all()
    )


@router.post("/{doc_id}/share", status_code=204)
def share(
    doc_id: str,
    grant: PermissionGrant,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    """Grant or update another user's access level on a document."""
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.owner)

    if not db.query(User).filter(User.id == grant.user_id).first():
        raise HTTPException(status_code=404, detail="Target user not found")

    perm = (
        db.query(Permission)
        .filter(Permission.document_id == doc_id, Permission.user_id == grant.user_id)
        .first()
    )
    if perm:
        perm.level = grant.level
    else:
        db.add(
            Permission(document_id=doc_id, user_id=grant.user_id, level=grant.level)
        )
    svc.log_action(db, user.id, doc_id, "shared", f"{grant.user_id}:{grant.level.value}")
    db.commit()
    # Visibility changed, so previously cached (now stale) search results for
    # the affected user must be dropped. Keys are per-user hashed, so we clear
    # the search namespace — consistent with create/update invalidation.
    invalidate_prefix("search:")
