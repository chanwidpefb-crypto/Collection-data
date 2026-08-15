"""Shared fixtures for tests that exercise the full FastAPI app (auth, history
API, etc). Patches app.database onto a temp SQLite file *before* app.main is
imported for the first time, so app.main's `from app.database import
SessionLocal` binds to the temp DB regardless of test collection order."""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database_module

_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_fd)
database_module.engine = create_engine(f"sqlite:///{_db_path}", connect_args={"check_same_thread": False})
database_module.SessionLocal = sessionmaker(bind=database_module.engine, autoflush=False, autocommit=False)

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402
from app import models  # noqa: E402
from app.auth import hash_password  # noqa: E402


@pytest.fixture()
def client():
    database_module.Base.metadata.drop_all(bind=database_module.engine)
    database_module.Base.metadata.create_all(bind=database_module.engine)
    with TestClient(main_module.app) as c:
        yield c


def set_admin_password(password: str) -> int:
    db = database_module.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == "admin").first()
        user.password_hash = hash_password(password)
        db.commit()
        return user.id
    finally:
        db.close()
