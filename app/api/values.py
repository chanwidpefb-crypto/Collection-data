from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.tag_store import tag_store

router = APIRouter(prefix="/api", tags=["values"])


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
