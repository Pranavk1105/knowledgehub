"""Authentication and authorization: password hashing, JWT, access control."""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Document, Permission, PermissionLevel, Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# --------------------------------------------------------------------------- #
# Passwords & tokens
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    # bcrypt operates on at most 72 bytes; truncate defensively.
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    pw = plain.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


# --------------------------------------------------------------------------- #
# Current user dependency
# --------------------------------------------------------------------------- #
def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exc
    return user


# --------------------------------------------------------------------------- #
# Authorization helpers
# --------------------------------------------------------------------------- #
_LEVELS = {
    PermissionLevel.viewer: 1,
    PermissionLevel.editor: 2,
    PermissionLevel.owner: 3,
}


def effective_level(db: Session, user: User, document: Document) -> Optional[PermissionLevel]:
    """Resolve a user's effective access level on a document."""
    if user.role == Role.admin or document.owner_id == user.id:
        return PermissionLevel.owner
    perm = (
        db.query(Permission)
        .filter(Permission.document_id == document.id, Permission.user_id == user.id)
        .first()
    )
    return perm.level if perm else None


def require_access(
    db: Session, user: User, document: Document, minimum: PermissionLevel
) -> None:
    """Raise 403 unless `user` has at least `minimum` access on `document`."""
    level = effective_level(db, user, document)
    if level is None or _LEVELS[level] < _LEVELS[minimum]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires '{minimum.value}' access to this document",
        )
