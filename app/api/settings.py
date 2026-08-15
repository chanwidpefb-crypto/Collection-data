from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_historian
from app.auth import require_admin
from app.database import get_db
from app.historian import HistorianService
from app.historian_backends import HistorianConfig, check_timescaledb_connection

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])


def _get_or_create_row(db: Session) -> models.HistorianSettings:
    row = db.query(models.HistorianSettings).first()
    if row is None:
        row = models.HistorianSettings()
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _to_out(row: models.HistorianSettings, historian: HistorianService) -> schemas.HistorianSettingsOut:
    return schemas.HistorianSettingsOut(
        backend=row.backend, interval_ms=row.interval_ms, retention_days=row.retention_days,
        ts_host=row.ts_host, ts_port=row.ts_port, ts_database=row.ts_database, ts_user=row.ts_user,
        ts_table=row.ts_table, ts_sslmode=row.ts_sslmode, ts_password_set=bool(row.ts_password),
        active_backend=historian.config.backend, last_error=historian.last_error,
    )


@router.get("/historian", response_model=schemas.HistorianSettingsOut)
def get_historian_settings(db: Session = Depends(get_db), historian: HistorianService = Depends(get_historian)):
    return _to_out(_get_or_create_row(db), historian)


@router.put("/historian", response_model=schemas.HistorianSettingsOut)
async def update_historian_settings(payload: schemas.HistorianSettingsIn, db: Session = Depends(get_db),
                                     historian: HistorianService = Depends(get_historian)):
    row = _get_or_create_row(db)
    password = payload.ts_password if payload.ts_password else row.ts_password

    config = HistorianConfig(
        backend=payload.backend.value, interval_ms=payload.interval_ms, retention_days=payload.retention_days,
        ts_host=payload.ts_host, ts_port=payload.ts_port, ts_database=payload.ts_database,
        ts_user=payload.ts_user, ts_password=password, ts_table=payload.ts_table, ts_sslmode=payload.ts_sslmode,
    )
    try:
        await historian.apply_config(config)
    except Exception as exc:  # noqa: BLE001 - surfaced to the admin, old backend keeps running
        raise HTTPException(400, f"could not connect with these settings: {exc}") from exc

    row.backend = payload.backend
    row.interval_ms = payload.interval_ms
    row.retention_days = payload.retention_days
    row.ts_host = payload.ts_host
    row.ts_port = payload.ts_port
    row.ts_database = payload.ts_database
    row.ts_user = payload.ts_user
    row.ts_password = password
    row.ts_table = payload.ts_table
    row.ts_sslmode = payload.ts_sslmode
    db.commit()
    db.refresh(row)
    return _to_out(row, historian)


@router.post("/historian/test-connection", response_model=schemas.ConnectionTestResult)
async def test_historian_connection(payload: schemas.TimescaleConnectionTest):
    config = HistorianConfig(
        backend="timescaledb", ts_host=payload.ts_host, ts_port=payload.ts_port,
        ts_database=payload.ts_database, ts_user=payload.ts_user, ts_password=payload.ts_password,
        ts_table=payload.ts_table, ts_sslmode=payload.ts_sslmode,
    )
    ok, message = await check_timescaledb_connection(config)
    return schemas.ConnectionTestResult(ok=ok, message=message)
