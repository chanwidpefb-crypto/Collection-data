from __future__ import annotations

import datetime
import enum

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer,
                         String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConnectorType(str, enum.Enum):
    MODBUS_TCP_CLIENT = "modbus_tcp_client"
    MODBUS_TCP_SERVER = "modbus_tcp_server"
    OPCUA_CLIENT = "opcua_client"
    OPCUA_SERVER = "opcua_server"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class ModbusArea(str, enum.Enum):
    COIL = "coil"
    DISCRETE_INPUT = "discrete_input"
    HOLDING_REGISTER = "holding_register"
    INPUT_REGISTER = "input_register"


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


class Connector(Base):
    """A single data-source or data-sink integration (a "driver")."""

    __tablename__ = "connectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    type: Mapped[ConnectorType] = mapped_column(Enum(ConnectorType))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    modbus_client_config: Mapped["ModbusClientConfig"] = relationship(
        back_populates="connector", uselist=False, cascade="all, delete-orphan")
    modbus_server_config: Mapped["ModbusServerConfig"] = relationship(
        back_populates="connector", uselist=False, cascade="all, delete-orphan")
    opcua_client_config: Mapped["OpcUaClientConfig"] = relationship(
        back_populates="connector", uselist=False, cascade="all, delete-orphan")
    opcua_server_config: Mapped["OpcUaServerConfig"] = relationship(
        back_populates="connector", uselist=False, cascade="all, delete-orphan")

    modbus_client_registers: Mapped[list["ModbusClientRegister"]] = relationship(
        back_populates="connector", cascade="all, delete-orphan", order_by="ModbusClientRegister.address")
    modbus_server_registers: Mapped[list["ModbusServerRegister"]] = relationship(
        back_populates="connector", cascade="all, delete-orphan", order_by="ModbusServerRegister.address")
    opcua_client_nodes: Mapped[list["OpcUaClientNode"]] = relationship(
        back_populates="connector", cascade="all, delete-orphan", order_by="OpcUaClientNode.id")
    opcua_server_nodes: Mapped[list["OpcUaServerNode"]] = relationship(
        back_populates="connector", cascade="all, delete-orphan", order_by="OpcUaServerNode.id")


class ModbusClientConfig(Base):
    __tablename__ = "modbus_client_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), unique=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=502)
    unit_id: Mapped[int] = mapped_column(Integer, default=1)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=3000)
    poll_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)

    connector: Mapped[Connector] = relationship(back_populates="modbus_client_config")


class ModbusServerConfig(Base):
    __tablename__ = "modbus_server_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), unique=True)
    host: Mapped[str] = mapped_column(String(255), default="0.0.0.0")
    port: Mapped[int] = mapped_column(Integer, default=502)
    unit_id: Mapped[int] = mapped_column(Integer, default=1)

    connector: Mapped[Connector] = relationship(back_populates="modbus_server_config")


class OpcUaClientConfig(Base):
    __tablename__ = "opcua_client_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), unique=True)
    endpoint_url: Mapped[str] = mapped_column(String(500))
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    poll_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)

    connector: Mapped[Connector] = relationship(back_populates="opcua_client_config")


class OpcUaServerConfig(Base):
    __tablename__ = "opcua_server_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"), unique=True)
    endpoint_url: Mapped[str] = mapped_column(String(500), default="opc.tcp://0.0.0.0:4840/collection-data/")
    server_name: Mapped[str] = mapped_column(String(255), default="Collection Data OPC UA Server")
    namespace_uri: Mapped[str] = mapped_column(String(255), default="http://collection-data/opcua")
    publish_interval_ms: Mapped[int] = mapped_column(Integer, default=1000)

    connector: Mapped[Connector] = relationship(back_populates="opcua_server_config")


class ModbusClientRegister(Base):
    """A single register to poll from a remote Modbus TCP device (client mode)."""

    __tablename__ = "modbus_client_registers"
    __table_args__ = (UniqueConstraint("connector_id", "area", "address", name="uq_modbus_client_addr"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"))
    tag_name: Mapped[str] = mapped_column(String(128), unique=True)
    area: Mapped[ModbusArea] = mapped_column(Enum(ModbusArea))
    address: Mapped[int] = mapped_column(Integer)
    data_type: Mapped[str] = mapped_column(String(16), default="uint16")
    word_order: Mapped[str] = mapped_column(String(8), default="ABCD")
    factor: Mapped[float] = mapped_column(Float, default=1.0)
    offset: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    connector: Mapped[Connector] = relationship(back_populates="modbus_client_registers")


class ModbusServerRegister(Base):
    """A register exposed to external Modbus masters (server mode), sourced from the tag store."""

    __tablename__ = "modbus_server_registers"
    __table_args__ = (UniqueConstraint("connector_id", "area", "address", name="uq_modbus_server_addr"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"))
    name: Mapped[str] = mapped_column(String(128))
    area: Mapped[ModbusArea] = mapped_column(Enum(ModbusArea))
    address: Mapped[int] = mapped_column(Integer)
    data_type: Mapped[str] = mapped_column(String(16), default="uint16")
    word_order: Mapped[str] = mapped_column(String(8), default="ABCD")
    expression: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    connector: Mapped[Connector] = relationship(back_populates="modbus_server_registers")


class OpcUaClientNode(Base):
    """A single node to poll from a remote OPC UA server (client mode)."""

    __tablename__ = "opcua_client_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"))
    tag_name: Mapped[str] = mapped_column(String(128), unique=True)
    node_id: Mapped[str] = mapped_column(String(500))
    factor: Mapped[float] = mapped_column(Float, default=1.0)
    offset: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    connector: Mapped[Connector] = relationship(back_populates="opcua_client_nodes")


class OpcUaServerNode(Base):
    """A single node exposed to external OPC UA clients (server mode), sourced from the tag store."""

    __tablename__ = "opcua_server_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connector_id: Mapped[int] = mapped_column(ForeignKey("connectors.id"))
    node_name: Mapped[str] = mapped_column(String(128))
    expression: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    connector: Mapped[Connector] = relationship(back_populates="opcua_server_nodes")


class TagHistory(Base):
    """A single historian sample: one tag's value at one point in time."""

    __tablename__ = "tag_history"
    __table_args__ = (Index("ix_tag_history_tag_ts", "tag_name", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tag_name: Mapped[str] = mapped_column(String(128))
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime)
    value: Mapped[float] = mapped_column(Float)
    quality: Mapped[str] = mapped_column(String(16), default="good")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)


class UserSession(Base):
    __tablename__ = "user_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime)
