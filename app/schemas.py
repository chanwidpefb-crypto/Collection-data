from __future__ import annotations

import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.drivers.codec import DataType, WordOrder
from app.models import ConnectorType, HistorianBackendType, ModbusArea, UserRole

# ---------------------------------------------------------------------------
# Connector (top level)
# ---------------------------------------------------------------------------


class ConnectorCreate(BaseModel):
    name: str
    type: ConnectorType
    enabled: bool = True


class ConnectorUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None


class ConnectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: ConnectorType
    enabled: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime


# ---------------------------------------------------------------------------
# Modbus TCP Client
# ---------------------------------------------------------------------------


class ModbusClientConfigIn(BaseModel):
    host: str
    port: int = Field(502, ge=1, le=65535)
    unit_id: int = Field(1, ge=0, le=255)
    timeout_ms: int = Field(3000, ge=100)
    poll_interval_ms: int = Field(1000, ge=50)


class ModbusClientConfigOut(ModbusClientConfigIn):
    model_config = ConfigDict(from_attributes=True)


class ModbusClientRegisterIn(BaseModel):
    tag_name: str
    area: ModbusArea
    address: int = Field(ge=0, le=65535)
    data_type: DataType = DataType.UINT16
    word_order: WordOrder = WordOrder.ABCD
    factor: float = 1.0
    offset: float = 0.0
    enabled: bool = True
    description: Optional[str] = None


class ModbusClientRegisterOut(ModbusClientRegisterIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connector_id: int


# ---------------------------------------------------------------------------
# Modbus TCP Server
# ---------------------------------------------------------------------------


class ModbusServerConfigIn(BaseModel):
    host: str = "0.0.0.0"
    port: int = Field(502, ge=1, le=65535)
    unit_id: int = Field(1, ge=0, le=255)


class ModbusServerConfigOut(ModbusServerConfigIn):
    model_config = ConfigDict(from_attributes=True)


class ModbusServerRegisterIn(BaseModel):
    name: str
    area: ModbusArea
    address: int = Field(ge=0, le=65535)
    data_type: DataType = DataType.UINT16
    word_order: WordOrder = WordOrder.ABCD
    expression: str
    enabled: bool = True


class ModbusServerRegisterOut(ModbusServerRegisterIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connector_id: int


# ---------------------------------------------------------------------------
# OPC UA Client
# ---------------------------------------------------------------------------


class OpcUaClientConfigIn(BaseModel):
    endpoint_url: str
    username: Optional[str] = None
    password: Optional[str] = None
    poll_interval_ms: int = Field(1000, ge=50)


class OpcUaClientConfigOut(OpcUaClientConfigIn):
    model_config = ConfigDict(from_attributes=True)


class OpcUaClientNodeIn(BaseModel):
    tag_name: str
    node_id: str
    factor: float = 1.0
    offset: float = 0.0
    enabled: bool = True
    description: Optional[str] = None


class OpcUaClientNodeOut(OpcUaClientNodeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connector_id: int


# ---------------------------------------------------------------------------
# OPC UA Server
# ---------------------------------------------------------------------------


class OpcUaServerConfigIn(BaseModel):
    endpoint_url: str = "opc.tcp://0.0.0.0:4840/collection-data/"
    server_name: str = "Collection Data OPC UA Server"
    namespace_uri: str = "http://collection-data/opcua"
    publish_interval_ms: int = Field(1000, ge=50)


class OpcUaServerConfigOut(OpcUaServerConfigIn):
    model_config = ConfigDict(from_attributes=True)


class OpcUaServerNodeIn(BaseModel):
    node_name: str
    expression: str
    enabled: bool = True


class OpcUaServerNodeOut(OpcUaServerNodeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    connector_id: int


# ---------------------------------------------------------------------------
# Composite connector detail
# ---------------------------------------------------------------------------


class ConnectorDetail(ConnectorOut):
    modbus_client_config: Optional[ModbusClientConfigOut] = None
    modbus_server_config: Optional[ModbusServerConfigOut] = None
    opcua_client_config: Optional[OpcUaClientConfigOut] = None
    opcua_server_config: Optional[OpcUaServerConfigOut] = None

    modbus_client_registers: list[ModbusClientRegisterOut] = []
    modbus_server_registers: list[ModbusServerRegisterOut] = []
    opcua_client_nodes: list[OpcUaClientNodeOut] = []
    opcua_server_nodes: list[OpcUaServerNodeOut] = []


class ConnectorStatus(BaseModel):
    id: int
    name: str
    type: ConnectorType
    enabled: bool
    running: bool
    last_error: Optional[str] = None


class TagValue(BaseModel):
    tag_name: str
    value: float | int | bool | None
    quality: str
    timestamp: Optional[datetime.datetime] = None
    source_connector: Optional[str] = None


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    errors: list[str] = []


class HistoryPoint(BaseModel):
    t: datetime.datetime
    v: float


class HistorianStatus(BaseModel):
    interval_ms: int
    retention_days: int
    total_points: int


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    created_at: datetime.datetime


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: UserRole = UserRole.VIEWER


class UserRoleUpdate(BaseModel):
    role: UserRole


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


# ---------------------------------------------------------------------------
# Historian storage settings
# ---------------------------------------------------------------------------


class HistorianSettingsOut(BaseModel):
    backend: HistorianBackendType
    interval_ms: int
    retention_days: int
    ts_host: str
    ts_port: int
    ts_database: str
    ts_user: str
    ts_table: str
    ts_sslmode: str
    ts_password_set: bool
    active_backend: HistorianBackendType
    last_error: Optional[str] = None


class HistorianSettingsIn(BaseModel):
    backend: HistorianBackendType
    interval_ms: int = Field(5000, ge=1000, le=3_600_000)
    retention_days: int = Field(30, ge=1, le=3650)
    ts_host: str = ""
    ts_port: int = Field(5432, ge=1, le=65535)
    ts_database: str = ""
    ts_user: str = ""
    ts_password: Optional[str] = None  # blank/omitted keeps the currently stored password
    ts_table: str = Field("tag_history", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    ts_sslmode: str = "prefer"


class TimescaleConnectionTest(BaseModel):
    ts_host: str
    ts_port: int = Field(5432, ge=1, le=65535)
    ts_database: str
    ts_user: str
    ts_password: str
    ts_table: str = Field("tag_history", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
    ts_sslmode: str = "prefer"


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
