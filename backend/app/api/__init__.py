from fastapi import APIRouter

from . import imports, notifications, push, reminders, settings, setup

api_router = APIRouter()
api_router.include_router(setup.router)
api_router.include_router(reminders.router)
api_router.include_router(notifications.router)
api_router.include_router(push.router)
api_router.include_router(imports.router)
api_router.include_router(settings.router)

__all__ = ["api_router"]
