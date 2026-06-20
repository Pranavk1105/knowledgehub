"""
SQLAlchemy ORM models — the relational schema for KnowledgeHub.

Entities
--------
User              : platform accounts and their global role.
Space             : a workspace / team container for documents.
Document          : the current state of a knowledge article.
DocumentVersion   : immutable snapshot created on every save (revision history).
Permission        : per-document ACL granting a user a role on a document.
Comment           : threaded collaboration on a document.
CollaborationLog  : append-only audit trail of every action in the system.

Full-text content is indexed separately in Elasticsearch (see search.py); the
relational store remains the source of truth for content, metadata and history.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    """Global role assigned to a user account."""

    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class PermissionLevel(str, enum.Enum):
    """Access level granted on a specific document."""

    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(Role), default=Role.editor, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="owner")
    permissions = relationship("Permission", back_populates="user")


class Space(Base):
    """A team workspace that groups related documents."""

    __tablename__ = "spaces"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("Document", back_populates="space")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, default="")
    space_id = Column(String, ForeignKey("spaces.id"), nullable=True, index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    current_version = Column(Integer, default=1, nullable=False)
    tags = Column(String, default="")  # comma-separated, denormalised for fast filtering
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="documents")
    space = relationship("Space", back_populates="documents")
    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
    permissions = relationship(
        "Permission", back_populates="document", cascade="all, delete-orphan"
    )
    comments = relationship(
        "Comment", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    """Immutable snapshot of a document at a point in time."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="uq_document_version"),
    )

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    content = Column(Text, default="")
    edited_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="versions")


class Permission(Base):
    """Per-document access control entry (ACL)."""

    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("document_id", "user_id", name="uq_doc_user_perm"),
    )

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    level = Column(Enum(PermissionLevel), nullable=False)
    granted_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="permissions")
    user = relationship("User", back_populates="permissions")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="comments")


class CollaborationLog(Base):
    """Append-only audit trail used for activity feeds and synchronisation."""

    __tablename__ = "collaboration_logs"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # created | updated | commented | shared ...
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
