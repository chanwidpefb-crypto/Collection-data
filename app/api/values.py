from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_historian
from app.auth import get_current_user
from app.database import get_db
from app.historian import HistorianService
from app.tag_store import tag_store

router = APIRouter(prefix="/api", tags=["values"], dependencies=[Depends(get_current_user)])


@router.get("/values", response_model=list[schemas.TagValue])
async def live_values():
    entries = await tag_store.get_all()
    return [
        schemas.TagValue(tag_name=e.tag_name, value=e.value, quality=e.quality,
                          timestamp=e.timestamp, source_connector=e.source_connector)
        for e in sorted(entries.values(), key=lambda e: e.tag_name)
    ]


@router.get("/tags/known", response_model=list[str])
def known_tags(db: Session = Depends(get_db)):
    """Tag names defined by client-mode connectors -- usable in server "factor
    expression" fields and the register/node pickers in the UI."""
    modbus_tags = [r.tag_name for r in db.query(models.ModbusClientRegister.tag_name).all()]
    opcua_tags = [r.tag_name for r in db.query(models.OpcUaClientNode.tag_name).all()]
    return sorted(set(modbus_tags) | set(opcua_tags))


def _downsample(points: list[schemas.HistoryPoint], max_points: int) -> list[schemas.HistoryPoint]:
    if len(points) <= max_points:
        return points
    stride = -(-len(points) // max_points)  # ceil division
    return points[::stride]


@router.get("/history", response_model=dict[str, list[schemas.HistoryPoint]])
async def history(
    tags: str = Query(..., description="comma-separated tag names"),
    start: datetime.datetime = Query(...),
    end: datetime.datetime = Query(...),
    max_points: int = Query(1500, ge=10, le=20000),
    historian: HistorianService = Depends(get_historian),
):
    tag_names = [t.strip() for t in tags.split(",") if t.strip()]
    result: dict[str, list[schemas.HistoryPoint]] = {}
    for tag_name in tag_names:
        rows = await historian.query(tag_name, start, end)
        points = [schemas.HistoryPoint(t=ts, v=v) for ts, v in rows]
        result[tag_name] = _downsample(points, max_points)
    return result


@router.get("/history/status", response_model=schemas.HistorianStatus)
async def history_status(historian: HistorianService = Depends(get_historian)):
    return schemas.HistorianStatus(
        interval_ms=historian.config.interval_ms,
        retention_days=historian.config.retention_days,
        total_points=await historian.count(),
    )
