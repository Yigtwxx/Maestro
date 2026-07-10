"""Aggregate API router (REST v1 + WebSocket)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import websocket
from app.api.v1 import (
    agents,
    api_keys,
    auth,
    billing,
    dashboard,
    documents,
    marketplace,
    tasks,
    users,
)
from app.core.constants import API_V1_PREFIX

api_router = APIRouter()

# REST v1
api_router.include_router(auth.router, prefix=API_V1_PREFIX)
api_router.include_router(users.router, prefix=API_V1_PREFIX)
api_router.include_router(api_keys.router, prefix=API_V1_PREFIX)
api_router.include_router(tasks.router, prefix=API_V1_PREFIX)
api_router.include_router(billing.router, prefix=API_V1_PREFIX)
api_router.include_router(dashboard.router, prefix=API_V1_PREFIX)
api_router.include_router(marketplace.router, prefix=API_V1_PREFIX)
api_router.include_router(agents.router, prefix=API_V1_PREFIX)
api_router.include_router(documents.router, prefix=API_V1_PREFIX)

# WebSocket (paths already fully qualified in the module)
api_router.include_router(websocket.router)
