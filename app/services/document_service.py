"""
Document lifecycle orchestration.

Centralises the rules that span multiple stores so the API routers stay thin:
  * every content change writes an immutable DocumentVersion (revision history),
  * the search index is kept in sync on create / update / delete,
  * the cache is invalidated, and
  * a CollaborationLog entry is appended for the activity feed / audit trail.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.cache import cache_delete, invalidate_prefix
from app.models import CollaborationLog, Document, DocumentVersion, User
from app.search import search_engine


def _tags_to_str(tags: Optional[List[str]]) -> str:
    return ",".join(t.strip() for t in tags if t.strip()) if tags else ""


def _tags_to_list(tags: str) -> List[str]:
    return [t for t in tags.split(",") if t] if tags else []


def log_action(db: Session, user_id: Optional[str], doc_id: Optional[str], action: str, detail: str = "") -> None:
    db.add(
        CollaborationLog(user_id=user_id, document_id=doc_id, action=action, detail=detail)
    )


def _sync_index(doc: Document) -> None:
    search_engine.index_document(
        {
            "id": doc.id,
            "title": doc.title,
            "content": doc.content,
            "tags": _tags_to_list(doc.tags),
            "space_id": doc.space_id,
            "owner_id": doc.owner_id,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        }
    )


def create_document(
    db: Session, owner: User, title: str, content: str, space_id: Optional[str], tags: Optional[List[str]]
) -> Document:
    doc = Document(
        title=title,
        content=content,
        space_id=space_id,
        owner_id=owner.id,
        current_version=1,
        tags=_tags_to_str(tags),
    )
    db.add(doc)
    db.flush()  # assign doc.id before writing the version row

    db.add(
        DocumentVersion(
            document_id=doc.id,
            version=1,
            title=title,
            content=content,
            edited_by=owner.id,
        )
    )
    log_action(db, owner.id, doc.id, "created", f"Created '{title}'")
    db.commit()
    db.refresh(doc)

    _sync_index(doc)
    invalidate_prefix("search:")
    return doc


def update_document(
    db: Session, editor: User, doc: Document, title: Optional[str], content: Optional[str], tags: Optional[List[str]]
) -> Document:
    changed = False
    if title is not None and title != doc.title:
        doc.title = title
        changed = True
    if content is not None and content != doc.content:
        doc.content = content
        changed = True
    if tags is not None:
        doc.tags = _tags_to_str(tags)
        changed = True

    if changed:
        doc.current_version += 1
        db.add(
            DocumentVersion(
                document_id=doc.id,
                version=doc.current_version,
                title=doc.title,
                content=doc.content,
                edited_by=editor.id,
            )
        )
        log_action(db, editor.id, doc.id, "updated", f"v{doc.current_version}")

    db.commit()
    db.refresh(doc)

    _sync_index(doc)
    cache_delete(f"doc:{doc.id}")
    invalidate_prefix("search:")
    return doc


def delete_document(db: Session, actor: User, doc: Document) -> None:
    doc_id = doc.id
    log_action(db, actor.id, doc_id, "deleted", f"Deleted '{doc.title}'")
    db.delete(doc)
    db.commit()

    search_engine.delete_document(doc_id)
    cache_delete(f"doc:{doc_id}")
    invalidate_prefix("search:")


def to_dict(doc: Document) -> dict:
    """Serialise a Document for API output / caching (tags as a list)."""
    return {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "space_id": doc.space_id,
        "owner_id": doc.owner_id,
        "current_version": doc.current_version,
        "tags": _tags_to_list(doc.tags),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
