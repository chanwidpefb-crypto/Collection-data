from __future__ import annotations

from fastapi import Request

from app.drivers.manager import DriverManager


def get_driver_manager(request: Request) -> DriverManager:
    return request.app.state.driver_manager
