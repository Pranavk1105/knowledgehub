"""Collaboration endpoints: comments and the per-document activity feed."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth
from app.database import get_db
from app.models import CollaborationLog, Comment, Document, PermissionLevel, User
from app.schemas import CommentCreate, CommentOut
from app.services import document_service as svc

router = APIRouter(prefix="/documents", tags=["collaboration"])


def _get_doc_or_404(db: Session, doc_id: str) -> Document:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/{doc_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    doc_id: str,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.viewer)
    comment = Comment(document_id=doc_id, author_id=user.id, body=payload.body)
    db.add(comment)
    svc.log_action(db, user.id, doc_id, "commented", payload.body[:80])
    db.commit()
    db.refresh(comment)
    return comment


@router.get("/{doc_id}/comments", response_model=List[CommentOut])
def list_comments(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.viewer)
    return (
        db.query(Comment)
        .filter(Comment.document_id == doc_id)
        .order_by(Comment.created_at.asc())
        .all()
    )


@router.get("/{doc_id}/activity")
def activity_feed(
    doc_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(auth.get_current_user),
):
    """Recent actions on a document (audit / activity trail)."""
    doc = _get_doc_or_404(db, doc_id)
    auth.require_access(db, user, doc, PermissionLevel.viewer)
    logs = (
        db.query(CollaborationLog)
        .filter(CollaborationLog.document_id == doc_id)
        .order_by(CollaborationLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "action": log.action,
            "detail": log.detail,
            "user_id": log.user_id,
            "at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
