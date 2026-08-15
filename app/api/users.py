from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import hash_password, require_admin
from app.database import get_db

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _admin_count(db: Session) -> int:
    return db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).count()


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.id).all()


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(409, "username already exists")
    user = models.User(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/role", response_model=schemas.UserOut)
def update_role(user_id: int, payload: schemas.UserRoleUpdate, db: Session = Depends(get_db),
                 current: models.User = Depends(require_admin)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if user.role == models.UserRole.ADMIN and payload.role != models.UserRole.ADMIN and _admin_count(db) <= 1:
        raise HTTPException(400, "cannot demote the last remaining admin")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/reset-password", response_model=schemas.UserOut)
def reset_password(user_id: int, payload: schemas.PasswordResetRequest, db: Session = Depends(get_db)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), current: models.User = Depends(require_admin)):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if user.id == current.id:
        raise HTTPException(400, "cannot delete your own account")
    if user.role == models.UserRole.ADMIN and _admin_count(db) <= 1:
        raise HTTPException(400, "cannot delete the last remaining admin")
    db.delete(user)
    db.commit()
    return None
