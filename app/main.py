from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import auth_routes, connectors, users, values
from app.auth import ensure_default_admin
from app.database import SessionLocal, init_db
from app.drivers.manager import DriverManager
from app.historian import Historian
from app.tag_store import tag_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
HISTORIAN_INTERVAL_MS = int(os.environ.get("HISTORIAN_INTERVAL_MS", "5000"))
HISTORIAN_RETENTION_DAYS = int(os.environ.get("HISTORIAN_RETENTION_DAYS", "30"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    db = SessionLocal()
    try:
        ensure_default_admin(db)
    finally:
        db.close()

    manager = DriverManager(SessionLocal, tag_store)
    app.state.driver_manager = manager
    await manager.start_all_enabled()

    historian = Historian(SessionLocal, tag_store, HISTORIAN_INTERVAL_MS, HISTORIAN_RETENTION_DAYS)
    app.state.historian = historian
    historian_task = asyncio.ensure_future(historian.run_forever())

    yield

    historian.stop()
    historian_task.cancel()
    try:
        await historian_task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
    await manager.stop_all()


app = FastAPI(title="Collection Data", lifespan=lifespan)
app.include_router(auth_routes.router)
app.include_router(users.router)
app.include_router(connectors.router)
app.include_router(values.router)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
