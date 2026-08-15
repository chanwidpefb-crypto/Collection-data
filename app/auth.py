"""Cookie-session authentication.

Passwords are hashed with bcrypt. A logged-in session is a random opaque
token stored in the `user_sessions` table and handed to the browser as an
httponly cookie -- no JWT, nothing to forge client-side. Two roles: `admin`
(full read/write, including connector configuration and user management) and
`viewer` (read-only: Live Monitor + Trend only, enforced by which routers
require `get_current_user` vs `require_admin`).
"""
from __future__ import annotations

import datetime
import logging
import secrets

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

logger = logging.getLogger("auth")

SESSION_COOKIE_NAME = "cd_session"
SESSION_TTL = datetime.timedelta(days=7)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_session(db: Session, user: models.User) -> str:
    token = secrets.token_hex(32)
    now = datetime.datetime.utcnow()
    db.add(models.UserSession(token=token, user_id=user.id, created_at=now, expires_at=now + SESSION_TTL))
    db.commit()
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME, token, httponly=True, samesite="lax",
        max_age=int(SESSION_TTL.total_seconds()), path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def get_current_user(
    cd_session: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> models.User:
    if not cd_session:
        raise HTTPException(401, "not authenticated")
    session = db.get(models.UserSession, cd_session)
    if session is None or session.expires_at < datetime.datetime.utcnow():
        raise HTTPException(401, "session expired")
    user = db.get(models.User, session.user_id)
    if user is None:
        raise HTTPException(401, "not authenticated")
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != models.UserRole.ADMIN:
        raise HTTPException(403, "admin access required")
    return user


def ensure_default_admin(db: Session) -> str | None:
    """Create a default admin user with a random password if no users exist
    yet. Returns the generated password (to be logged once) or None if users
    already exist."""
    if db.query(models.User).count() > 0:
        return None
    password = secrets.token_urlsafe(9)
    admin = models.User(username="admin", password_hash=hash_password(password), role=models.UserRole.ADMIN)
    db.add(admin)
    db.commit()
    logger.warning("=" * 70)
    logger.warning("Created default admin user -- username: admin  password: %s", password)
    logger.warning("Log in and change this password immediately.")
    logger.warning("=" * 70)
    return password
