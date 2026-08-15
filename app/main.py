from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import connectors, values
from app.database import SessionLocal, init_db
from app.drivers.manager import DriverManager
from app.tag_store import tag_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    manager = DriverManager(SessionLocal, tag_store)
    app.state.driver_manager = manager
    await manager.start_all_enabled()
    yield
    await manager.stop_all()


app = FastAPI(title="Collection Data", lifespan=lifespan)
app.include_router(connectors.router)
app.include_router(values.router)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
