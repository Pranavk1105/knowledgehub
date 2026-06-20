"""Pydantic request/response models (the API contract)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

from app.models import PermissionLevel, Role


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=6)
    role: Role = Role.editor


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Role
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
class DocumentCreate(BaseModel):
    title: str
    content: str = ""
    space_id: Optional[str] = None
    tags: List[str] = []


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class DocumentOut(BaseModel):
    id: str
    title: str
    content: str
    space_id: Optional[str]
    owner_id: str
    current_version: int
    tags: List[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VersionOut(BaseModel):
    version: int
    title: str
    content: str
    edited_by: str
    created_at: datetime

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------- #
# Collaboration
# --------------------------------------------------------------------------- #
class PermissionGrant(BaseModel):
    user_id: str
    level: PermissionLevel


class CommentCreate(BaseModel):
    body: str


class CommentOut(BaseModel):
    id: str
    author_id: str
    body: str
    created_at: datetime

    class Config:
        from_attributes = True


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
class SearchHit(BaseModel):
    document_id: str
    title: str
    score: float
    highlight: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    total: int
    took_ms: int
    cached: bool
    hits: List[SearchHit]
