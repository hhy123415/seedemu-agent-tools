"""Top-level API router."""

from fastapi import APIRouter

from seedemu_tool_service.api.routes import health, runtime, tools

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(runtime.router, prefix="/runtime")
api_router.include_router(tools.router, prefix="/tools")
