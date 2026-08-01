from .cameras import router as cameras_router
from .recordings import router as recordings_router
from .highlights import router as highlights_router
from .settings import router as settings_router
from .diary import router as diary_router

__all__ = ["cameras_router", "recordings_router", "highlights_router", "settings_router", "diary_router"]
