from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_historian
from app.auth import get_current_user
from app.database import get_db
from app.historian import Historian
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
def history(
    tags: str = Query(..., description="comma-separated tag names"),
    start: datetime.datetime = Query(...),
    end: datetime.datetime = Query(...),
    max_points: int = Query(1500, ge=10, le=20000),
    db: Session = Depends(get_db),
):
    tag_names = [t.strip() for t in tags.split(",") if t.strip()]
    result: dict[str, list[schemas.HistoryPoint]] = {}
    for tag_name in tag_names:
        rows = (
            db.query(models.TagHistory)
            .filter(models.TagHistory.tag_name == tag_name,
                    models.TagHistory.timestamp >= start,
                    models.TagHistory.timestamp <= end)
            .order_by(models.TagHistory.timestamp)
            .all()
        )
        points = [schemas.HistoryPoint(t=r.timestamp, v=r.value) for r in rows]
        result[tag_name] = _downsample(points, max_points)
    return result


@router.get("/history/status", response_model=schemas.HistorianStatus)
def history_status(db: Session = Depends(get_db), historian: Historian = Depends(get_historian)):
    total = db.query(models.TagHistory).count()
    return schemas.HistorianStatus(
        interval_ms=int(historian.interval_s * 1000),
        retention_days=historian.retention_days,
        total_points=total,
    )
