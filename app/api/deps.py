from __future__ import annotations

from fastapi import Request

from app.drivers.manager import DriverManager
from app.historian import HistorianService


def get_driver_manager(request: Request) -> DriverManager:
    return request.app.state.driver_manager


def get_historian(request: Request) -> HistorianService:
    return request.app.state.historian
