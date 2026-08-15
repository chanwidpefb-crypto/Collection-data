from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import (SESSION_COOKIE_NAME, clear_session_cookie, create_session,
                       get_current_user, hash_password, set_session_cookie, verify_password)
from app.database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.UserOut)
def login(payload: schemas.LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "invalid username or password")
    token = create_session(db, user)
    set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(response: Response, cd_session: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if cd_session:
        session = db.get(models.UserSession, cd_session)
        if session is not None:
            db.delete(session)
            db.commit()
    clear_session_cookie(response)
    return None


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=schemas.UserOut)
def change_own_password(payload: schemas.ChangePasswordRequest, user: models.User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, "current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user
