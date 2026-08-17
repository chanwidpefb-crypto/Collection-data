from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.deps import get_driver_manager
from app.auth import require_admin
from app.csv_io import parse_bool, parse_float, read_csv, write_csv
from app.database import get_db
from app.drivers.manager import DriverManager
from app.expression import ExpressionError, evaluate, referenced_names

router = APIRouter(prefix="/api/connectors", tags=["connectors"], dependencies=[Depends(require_admin)])

_DEFAULT_CONFIG_FACTORY = {
    models.ConnectorType.MODBUS_TCP_CLIENT: lambda cid: models.ModbusClientConfig(
        connector_id=cid, host="192.168.1.10", port=502, unit_id=1),
    models.ConnectorType.MODBUS_TCP_SERVER: lambda cid: models.ModbusServerConfig(
        connector_id=cid, host="0.0.0.0", port=502, unit_id=1),
    models.ConnectorType.OPCUA_CLIENT: lambda cid: models.OpcUaClientConfig(
        connector_id=cid, endpoint_url="opc.tcp://192.168.1.10:4840"),
    models.ConnectorType.OPCUA_SERVER: lambda cid: models.OpcUaServerConfig(connector_id=cid),
}


def _get_connector_or_404(db: Session, connector_id: int) -> models.Connector:
    connector = db.get(models.Connector, connector_id)
    if connector is None:
        raise HTTPException(404, "connector not found")
    return connector


async def _restart_if_running(manager: DriverManager, connector_id: int) -> None:
    if manager.is_running(connector_id):
        await manager.restart(connector_id)


def _expression_error(expression: str) -> str | None:
    try:
        evaluate(expression, {name: 0.0 for name in referenced_names(expression)})
        return None
    except ExpressionError as exc:
        return str(exc)


def _validate_expression(expression: str) -> None:
    err = _expression_error(expression)
    if err:
        raise HTTPException(422, f"invalid expression: {err}")


@router.get("", response_model=list[schemas.ConnectorStatus])
def list_connectors(db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connectors = db.query(models.Connector).order_by(models.Connector.id).all()
    return [
        schemas.ConnectorStatus(
            id=c.id, name=c.name, type=c.type, enabled=c.enabled,
            running=manager.is_running(c.id), last_error=manager.last_error(c.id),
        )
        for c in connectors
    ]


@router.post("", response_model=schemas.ConnectorDetail, status_code=201)
def create_connector(payload: schemas.ConnectorCreate, db: Session = Depends(get_db)):
    if db.query(models.Connector).filter(models.Connector.name == payload.name).first():
        raise HTTPException(409, "a connector with this name already exists")
    connector = models.Connector(name=payload.name, type=payload.type, enabled=payload.enabled)
    db.add(connector)
    db.flush()
    db.add(_DEFAULT_CONFIG_FACTORY[payload.type](connector.id))
    db.commit()
    db.refresh(connector)
    return connector


@router.get("/{connector_id}", response_model=schemas.ConnectorDetail)
def get_connector(connector_id: int, db: Session = Depends(get_db)):
    return _get_connector_or_404(db, connector_id)


@router.patch("/{connector_id}", response_model=schemas.ConnectorDetail)
async def update_connector(connector_id: int, payload: schemas.ConnectorUpdate, db: Session = Depends(get_db),
                            manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    if payload.name is not None:
        connector.name = payload.name
    was_enabled = connector.enabled
    if payload.enabled is not None:
        connector.enabled = payload.enabled
    db.commit()
    db.refresh(connector)

    if payload.enabled is not None and payload.enabled != was_enabled:
        if payload.enabled:
            await manager.start(connector_id)
        else:
            await manager.stop(connector_id)
    return connector


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(connector_id: int, db: Session = Depends(get_db),
                            manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    await manager.stop(connector_id)
    db.delete(connector)
    db.commit()
    return None


@router.post("/{connector_id}/start", response_model=schemas.ConnectorStatus)
async def start_connector(connector_id: int, db: Session = Depends(get_db),
                           manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    await manager.start(connector_id)
    return schemas.ConnectorStatus(id=connector.id, name=connector.name, type=connector.type,
                                    enabled=connector.enabled, running=manager.is_running(connector_id),
                                    last_error=manager.last_error(connector_id))


@router.post("/{connector_id}/stop", response_model=schemas.ConnectorStatus)
async def stop_connector(connector_id: int, db: Session = Depends(get_db),
                          manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    await manager.stop(connector_id)
    return schemas.ConnectorStatus(id=connector.id, name=connector.name, type=connector.type,
                                    enabled=connector.enabled, running=manager.is_running(connector_id),
                                    last_error=manager.last_error(connector_id))


@router.post("/{connector_id}/restart", response_model=schemas.ConnectorStatus)
async def restart_connector(connector_id: int, db: Session = Depends(get_db),
                             manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    await manager.restart(connector_id)
    return schemas.ConnectorStatus(id=connector.id, name=connector.name, type=connector.type,
                                    enabled=connector.enabled, running=manager.is_running(connector_id),
                                    last_error=manager.last_error(connector_id))


# ---------------------------------------------------------------------------
# Type-specific config
# ---------------------------------------------------------------------------


def _require_type(connector: models.Connector, expected: models.ConnectorType) -> None:
    if connector.type != expected:
        raise HTTPException(400, f"connector is of type {connector.type.value}, not {expected.value}")


@router.put("/{connector_id}/modbus-client-config", response_model=schemas.ModbusClientConfigOut)
async def set_modbus_client_config(connector_id: int, payload: schemas.ModbusClientConfigIn,
                                    db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_CLIENT)
    cfg = connector.modbus_client_config
    for field, value in payload.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    await _restart_if_running(manager, connector_id)
    return cfg


@router.put("/{connector_id}/modbus-server-config", response_model=schemas.ModbusServerConfigOut)
async def set_modbus_server_config(connector_id: int, payload: schemas.ModbusServerConfigIn,
                                    db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_SERVER)
    cfg = connector.modbus_server_config
    for field, value in payload.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    await _restart_if_running(manager, connector_id)
    return cfg


@router.put("/{connector_id}/opcua-client-config", response_model=schemas.OpcUaClientConfigOut)
async def set_opcua_client_config(connector_id: int, payload: schemas.OpcUaClientConfigIn,
                                   db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_CLIENT)
    cfg = connector.opcua_client_config
    for field, value in payload.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    await _restart_if_running(manager, connector_id)
    return cfg


@router.put("/{connector_id}/opcua-server-config", response_model=schemas.OpcUaServerConfigOut)
async def set_opcua_server_config(connector_id: int, payload: schemas.OpcUaServerConfigIn,
                                   db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_SERVER)
    cfg = connector.opcua_server_config
    for field, value in payload.model_dump().items():
        setattr(cfg, field, value)
    db.commit()
    db.refresh(cfg)
    await _restart_if_running(manager, connector_id)
    return cfg


# ---------------------------------------------------------------------------
# Modbus client registers
# ---------------------------------------------------------------------------


@router.get("/{connector_id}/modbus-client-registers", response_model=list[schemas.ModbusClientRegisterOut])
def list_modbus_client_registers(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_CLIENT)
    return connector.modbus_client_registers


@router.post("/{connector_id}/modbus-client-registers", response_model=schemas.ModbusClientRegisterOut, status_code=201)
async def create_modbus_client_register(connector_id: int, payload: schemas.ModbusClientRegisterIn,
                                         restart: bool = Query(True),
                                         db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_CLIENT)
    if db.query(models.ModbusClientRegister).filter(models.ModbusClientRegister.tag_name == payload.tag_name).first() \
            or db.query(models.OpcUaClientNode).filter(models.OpcUaClientNode.tag_name == payload.tag_name).first():
        raise HTTPException(409, f"tag name '{payload.tag_name}' is already used")
    reg = models.ModbusClientRegister(connector_id=connector_id, **payload.model_dump())
    db.add(reg)
    db.commit()
    db.refresh(reg)
    if restart:
        await _restart_if_running(manager, connector_id)
    return reg


@router.put("/{connector_id}/modbus-client-registers/{register_id}", response_model=schemas.ModbusClientRegisterOut)
async def update_modbus_client_register(connector_id: int, register_id: int, payload: schemas.ModbusClientRegisterIn,
                                         restart: bool = Query(True),
                                         db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    reg = db.get(models.ModbusClientRegister, register_id)
    if reg is None or reg.connector_id != connector_id:
        raise HTTPException(404, "register not found")
    other = db.query(models.ModbusClientRegister).filter(
        models.ModbusClientRegister.tag_name == payload.tag_name,
        models.ModbusClientRegister.id != register_id).first()
    if other:
        raise HTTPException(409, f"tag name '{payload.tag_name}' is already used")
    for field, value in payload.model_dump().items():
        setattr(reg, field, value)
    db.commit()
    db.refresh(reg)
    if restart:
        await _restart_if_running(manager, connector_id)
    return reg


@router.delete("/{connector_id}/modbus-client-registers/{register_id}", status_code=204)
async def delete_modbus_client_register(connector_id: int, register_id: int, restart: bool = Query(True),
                                         db: Session = Depends(get_db),
                                         manager: DriverManager = Depends(get_driver_manager)):
    reg = db.get(models.ModbusClientRegister, register_id)
    if reg is None or reg.connector_id != connector_id:
        raise HTTPException(404, "register not found")
    db.delete(reg)
    db.commit()
    if restart:
        await _restart_if_running(manager, connector_id)
    return None


@router.get("/{connector_id}/modbus-client-registers/export")
def export_modbus_client_registers(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_CLIENT)
    fields = ["tag_name", "area", "address", "data_type", "word_order", "factor", "offset", "enabled", "description"]
    rows = [{
        "tag_name": r.tag_name, "area": r.area.value if hasattr(r.area, "value") else r.area,
        "address": r.address, "data_type": r.data_type, "word_order": r.word_order,
        "factor": r.factor, "offset": r.offset, "enabled": r.enabled, "description": r.description or "",
    } for r in connector.modbus_client_registers]
    csv_text = write_csv(fields, rows)
    return Response(content=csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{connector.name}_registers.csv"'})


@router.post("/{connector_id}/modbus-client-registers/import", response_model=schemas.ImportResult)
async def import_modbus_client_registers(connector_id: int, file: UploadFile = File(...),
                                          db: Session = Depends(get_db),
                                          manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_CLIENT)
    rows = read_csv((await file.read()).decode("utf-8-sig"))
    existing_by_tag = {r.tag_name: r for r in connector.modbus_client_registers}
    created = updated = 0
    errors: list[str] = []

    for i, row in enumerate(rows, start=2):
        tag_name = (row.get("tag_name") or "").strip()
        try:
            if not tag_name:
                raise ValueError("tag_name is required")
            payload = schemas.ModbusClientRegisterIn(
                tag_name=tag_name, area=(row.get("area") or "").strip(), address=int(row["address"]),
                data_type=(row.get("data_type") or "uint16").strip(),
                word_order=(row.get("word_order") or "ABCD").strip(),
                factor=parse_float(row.get("factor"), 1.0), offset=parse_float(row.get("offset"), 0.0),
                enabled=parse_bool(row.get("enabled"), True), description=(row.get("description") or None),
            )
        except Exception as exc:  # noqa: BLE001 - collected as a per-row import error
            errors.append(f"row {i}: {exc}")
            continue

        existing = existing_by_tag.get(tag_name)
        if existing is not None:
            for field, value in payload.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            if db.query(models.OpcUaClientNode).filter(models.OpcUaClientNode.tag_name == tag_name).first():
                errors.append(f"row {i}: tag name '{tag_name}' is already used by an OPC UA node")
                continue
            db.add(models.ModbusClientRegister(connector_id=connector_id, **payload.model_dump()))
            created += 1

    db.commit()
    await _restart_if_running(manager, connector_id)
    return schemas.ImportResult(created=created, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# Modbus server registers
# ---------------------------------------------------------------------------


@router.get("/{connector_id}/modbus-server-registers", response_model=list[schemas.ModbusServerRegisterOut])
def list_modbus_server_registers(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_SERVER)
    return connector.modbus_server_registers


@router.post("/{connector_id}/modbus-server-registers", response_model=schemas.ModbusServerRegisterOut, status_code=201)
async def create_modbus_server_register(connector_id: int, payload: schemas.ModbusServerRegisterIn,
                                         restart: bool = Query(True),
                                         db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_SERVER)
    _validate_expression(payload.expression)
    reg = models.ModbusServerRegister(connector_id=connector_id, **payload.model_dump())
    db.add(reg)
    db.commit()
    db.refresh(reg)
    if restart:
        await _restart_if_running(manager, connector_id)
    return reg


@router.put("/{connector_id}/modbus-server-registers/{register_id}", response_model=schemas.ModbusServerRegisterOut)
async def update_modbus_server_register(connector_id: int, register_id: int, payload: schemas.ModbusServerRegisterIn,
                                         restart: bool = Query(True),
                                         db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    reg = db.get(models.ModbusServerRegister, register_id)
    if reg is None or reg.connector_id != connector_id:
        raise HTTPException(404, "register not found")
    _validate_expression(payload.expression)
    for field, value in payload.model_dump().items():
        setattr(reg, field, value)
    db.commit()
    db.refresh(reg)
    if restart:
        await _restart_if_running(manager, connector_id)
    return reg


@router.delete("/{connector_id}/modbus-server-registers/{register_id}", status_code=204)
async def delete_modbus_server_register(connector_id: int, register_id: int, restart: bool = Query(True),
                                         db: Session = Depends(get_db),
                                         manager: DriverManager = Depends(get_driver_manager)):
    reg = db.get(models.ModbusServerRegister, register_id)
    if reg is None or reg.connector_id != connector_id:
        raise HTTPException(404, "register not found")
    db.delete(reg)
    db.commit()
    if restart:
        await _restart_if_running(manager, connector_id)
    return None


@router.get("/{connector_id}/modbus-server-registers/export")
def export_modbus_server_registers(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_SERVER)
    fields = ["name", "area", "address", "data_type", "word_order", "expression", "enabled"]
    rows = [{
        "name": r.name, "area": r.area.value if hasattr(r.area, "value") else r.area, "address": r.address,
        "data_type": r.data_type, "word_order": r.word_order, "expression": r.expression, "enabled": r.enabled,
    } for r in connector.modbus_server_registers]
    csv_text = write_csv(fields, rows)
    return Response(content=csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{connector.name}_registers.csv"'})


@router.post("/{connector_id}/modbus-server-registers/import", response_model=schemas.ImportResult)
async def import_modbus_server_registers(connector_id: int, file: UploadFile = File(...),
                                          db: Session = Depends(get_db),
                                          manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.MODBUS_TCP_SERVER)
    rows = read_csv((await file.read()).decode("utf-8-sig"))
    existing_by_key = {(r.area, r.address): r for r in connector.modbus_server_registers}
    created = updated = 0
    errors: list[str] = []

    for i, row in enumerate(rows, start=2):
        try:
            name = (row.get("name") or "").strip()
            if not name:
                raise ValueError("name is required")
            area_str = (row.get("area") or "").strip()
            address = int(row["address"])
            payload = schemas.ModbusServerRegisterIn(
                name=name, area=area_str, address=address,
                data_type=(row.get("data_type") or "uint16").strip(),
                word_order=(row.get("word_order") or "ABCD").strip(),
                expression=(row.get("expression") or "").strip(),
                enabled=parse_bool(row.get("enabled"), True),
            )
            expr_err = _expression_error(payload.expression)
            if expr_err:
                raise ValueError(f"invalid expression: {expr_err}")
        except Exception as exc:  # noqa: BLE001 - collected as a per-row import error
            errors.append(f"row {i}: {exc}")
            continue

        key = (models.ModbusArea(area_str), address)
        existing = existing_by_key.get(key)
        if existing is not None:
            for field, value in payload.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(models.ModbusServerRegister(connector_id=connector_id, **payload.model_dump()))
            created += 1

    db.commit()
    await _restart_if_running(manager, connector_id)
    return schemas.ImportResult(created=created, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# OPC UA client nodes
# ---------------------------------------------------------------------------


@router.get("/{connector_id}/opcua-client-nodes", response_model=list[schemas.OpcUaClientNodeOut])
def list_opcua_client_nodes(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_CLIENT)
    return connector.opcua_client_nodes


@router.post("/{connector_id}/opcua-client-nodes", response_model=schemas.OpcUaClientNodeOut, status_code=201)
async def create_opcua_client_node(connector_id: int, payload: schemas.OpcUaClientNodeIn, restart: bool = Query(True),
                                    db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_CLIENT)
    if db.query(models.OpcUaClientNode).filter(models.OpcUaClientNode.tag_name == payload.tag_name).first() \
            or db.query(models.ModbusClientRegister).filter(models.ModbusClientRegister.tag_name == payload.tag_name).first():
        raise HTTPException(409, f"tag name '{payload.tag_name}' is already used")
    node = models.OpcUaClientNode(connector_id=connector_id, **payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    if restart:
        await _restart_if_running(manager, connector_id)
    return node


@router.put("/{connector_id}/opcua-client-nodes/{node_id}", response_model=schemas.OpcUaClientNodeOut)
async def update_opcua_client_node(connector_id: int, node_id: int, payload: schemas.OpcUaClientNodeIn,
                                    restart: bool = Query(True),
                                    db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    node = db.get(models.OpcUaClientNode, node_id)
    if node is None or node.connector_id != connector_id:
        raise HTTPException(404, "node not found")
    other = db.query(models.OpcUaClientNode).filter(
        models.OpcUaClientNode.tag_name == payload.tag_name, models.OpcUaClientNode.id != node_id).first()
    if other:
        raise HTTPException(409, f"tag name '{payload.tag_name}' is already used")
    for field, value in payload.model_dump().items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    if restart:
        await _restart_if_running(manager, connector_id)
    return node


@router.delete("/{connector_id}/opcua-client-nodes/{node_id}", status_code=204)
async def delete_opcua_client_node(connector_id: int, node_id: int, restart: bool = Query(True),
                                    db: Session = Depends(get_db),
                                    manager: DriverManager = Depends(get_driver_manager)):
    node = db.get(models.OpcUaClientNode, node_id)
    if node is None or node.connector_id != connector_id:
        raise HTTPException(404, "node not found")
    db.delete(node)
    db.commit()
    if restart:
        await _restart_if_running(manager, connector_id)
    return None


@router.get("/{connector_id}/opcua-client-nodes/export")
def export_opcua_client_nodes(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_CLIENT)
    fields = ["tag_name", "node_id", "factor", "offset", "enabled", "description"]
    rows = [{
        "tag_name": n.tag_name, "node_id": n.node_id, "factor": n.factor, "offset": n.offset,
        "enabled": n.enabled, "description": n.description or "",
    } for n in connector.opcua_client_nodes]
    csv_text = write_csv(fields, rows)
    return Response(content=csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{connector.name}_nodes.csv"'})


@router.post("/{connector_id}/opcua-client-nodes/import", response_model=schemas.ImportResult)
async def import_opcua_client_nodes(connector_id: int, file: UploadFile = File(...),
                                     db: Session = Depends(get_db),
                                     manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_CLIENT)
    rows = read_csv((await file.read()).decode("utf-8-sig"))
    existing_by_tag = {n.tag_name: n for n in connector.opcua_client_nodes}
    created = updated = 0
    errors: list[str] = []

    for i, row in enumerate(rows, start=2):
        tag_name = (row.get("tag_name") or "").strip()
        try:
            if not tag_name:
                raise ValueError("tag_name is required")
            node_id = (row.get("node_id") or "").strip()
            if not node_id:
                raise ValueError("node_id is required")
            payload = schemas.OpcUaClientNodeIn(
                tag_name=tag_name, node_id=node_id,
                factor=parse_float(row.get("factor"), 1.0), offset=parse_float(row.get("offset"), 0.0),
                enabled=parse_bool(row.get("enabled"), True), description=(row.get("description") or None),
            )
        except Exception as exc:  # noqa: BLE001 - collected as a per-row import error
            errors.append(f"row {i}: {exc}")
            continue

        existing = existing_by_tag.get(tag_name)
        if existing is not None:
            for field, value in payload.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            if db.query(models.ModbusClientRegister).filter(models.ModbusClientRegister.tag_name == tag_name).first():
                errors.append(f"row {i}: tag name '{tag_name}' is already used by a Modbus register")
                continue
            db.add(models.OpcUaClientNode(connector_id=connector_id, **payload.model_dump()))
            created += 1

    db.commit()
    await _restart_if_running(manager, connector_id)
    return schemas.ImportResult(created=created, updated=updated, errors=errors)


# ---------------------------------------------------------------------------
# OPC UA server nodes
# ---------------------------------------------------------------------------


@router.get("/{connector_id}/opcua-server-nodes", response_model=list[schemas.OpcUaServerNodeOut])
def list_opcua_server_nodes(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_SERVER)
    return connector.opcua_server_nodes


@router.post("/{connector_id}/opcua-server-nodes", response_model=schemas.OpcUaServerNodeOut, status_code=201)
async def create_opcua_server_node(connector_id: int, payload: schemas.OpcUaServerNodeIn, restart: bool = Query(True),
                                    db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_SERVER)
    _validate_expression(payload.expression)
    node = models.OpcUaServerNode(connector_id=connector_id, **payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    if restart:
        await _restart_if_running(manager, connector_id)
    return node


@router.put("/{connector_id}/opcua-server-nodes/{node_id}", response_model=schemas.OpcUaServerNodeOut)
async def update_opcua_server_node(connector_id: int, node_id: int, payload: schemas.OpcUaServerNodeIn,
                                    restart: bool = Query(True),
                                    db: Session = Depends(get_db), manager: DriverManager = Depends(get_driver_manager)):
    node = db.get(models.OpcUaServerNode, node_id)
    if node is None or node.connector_id != connector_id:
        raise HTTPException(404, "node not found")
    _validate_expression(payload.expression)
    for field, value in payload.model_dump().items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    if restart:
        await _restart_if_running(manager, connector_id)
    return node


@router.delete("/{connector_id}/opcua-server-nodes/{node_id}", status_code=204)
async def delete_opcua_server_node(connector_id: int, node_id: int, restart: bool = Query(True),
                                    db: Session = Depends(get_db),
                                    manager: DriverManager = Depends(get_driver_manager)):
    node = db.get(models.OpcUaServerNode, node_id)
    if node is None or node.connector_id != connector_id:
        raise HTTPException(404, "node not found")
    db.delete(node)
    db.commit()
    if restart:
        await _restart_if_running(manager, connector_id)
    return None


@router.get("/{connector_id}/opcua-server-nodes/export")
def export_opcua_server_nodes(connector_id: int, db: Session = Depends(get_db)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_SERVER)
    fields = ["node_name", "expression", "enabled"]
    rows = [{"node_name": n.node_name, "expression": n.expression, "enabled": n.enabled}
            for n in connector.opcua_server_nodes]
    csv_text = write_csv(fields, rows)
    return Response(content=csv_text, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{connector.name}_nodes.csv"'})


@router.post("/{connector_id}/opcua-server-nodes/import", response_model=schemas.ImportResult)
async def import_opcua_server_nodes(connector_id: int, file: UploadFile = File(...),
                                     db: Session = Depends(get_db),
                                     manager: DriverManager = Depends(get_driver_manager)):
    connector = _get_connector_or_404(db, connector_id)
    _require_type(connector, models.ConnectorType.OPCUA_SERVER)
    rows = read_csv((await file.read()).decode("utf-8-sig"))
    existing_by_name = {n.node_name: n for n in connector.opcua_server_nodes}
    created = updated = 0
    errors: list[str] = []

    for i, row in enumerate(rows, start=2):
        try:
            node_name = (row.get("node_name") or "").strip()
            if not node_name:
                raise ValueError("node_name is required")
            payload = schemas.OpcUaServerNodeIn(
                node_name=node_name, expression=(row.get("expression") or "").strip(),
                enabled=parse_bool(row.get("enabled"), True),
            )
            expr_err = _expression_error(payload.expression)
            if expr_err:
                raise ValueError(f"invalid expression: {expr_err}")
        except Exception as exc:  # noqa: BLE001 - collected as a per-row import error
            errors.append(f"row {i}: {exc}")
            continue

        existing = existing_by_name.get(node_name)
        if existing is not None:
            for field, value in payload.model_dump().items():
                setattr(existing, field, value)
            updated += 1
        else:
            db.add(models.OpcUaServerNode(connector_id=connector_id, **payload.model_dump()))
            created += 1

    db.commit()
    await _restart_if_running(manager, connector_id)
    return schemas.ImportResult(created=created, updated=updated, errors=errors)
