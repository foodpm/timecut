"""系统设置 API"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from config import settings

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/settings", tags=["settings"])

_restart_callback = None


def register_restart_callback(cb):
    global _restart_callback
    _restart_callback = cb


class SettingsUpdate(BaseModel):
    camera_name: str | None = None
    camera_rtsp_url: str | None = None
    recording_retention_days: int | None = None
    recording_segment_minutes: int | None = None
    highlight_duration_minutes: int | None = None
    highlight_enabled: bool | None = None
    highlight_schedule_time: str | None = None
    detection_sensitivity: int | None = None


@router.get("")
def get_settings():
    return {
        "camera_name": settings.camera_name,
        "camera_rtsp_url": settings.camera_rtsp_url,
        "recording_retention_days": settings.recording_retention_days,
        "recording_segment_minutes": settings.recording_segment_minutes,
        "highlight_duration_minutes": settings.highlight_duration_minutes,
        "highlight_enabled": settings.highlight_enabled,
        "highlight_schedule_time": settings.highlight_schedule_time,
        "detection_sensitivity": settings.detection_sensitivity,
    }


@router.put("")
def update_settings(data: SettingsUpdate):
    if data.camera_name is not None:
        settings.camera_name = data.camera_name
    if data.camera_rtsp_url is not None:
        settings.camera_rtsp_url = data.camera_rtsp_url
    if data.recording_retention_days is not None:
        settings.recording_retention_days = data.recording_retention_days
    if data.recording_segment_minutes is not None:
        settings.recording_segment_minutes = data.recording_segment_minutes
    if data.highlight_duration_minutes is not None:
        settings.highlight_duration_minutes = data.highlight_duration_minutes
    if data.highlight_enabled is not None:
        settings.highlight_enabled = data.highlight_enabled
    if data.highlight_schedule_time is not None:
        settings.highlight_schedule_time = data.highlight_schedule_time
    if data.detection_sensitivity is not None:
        settings.detection_sensitivity = data.detection_sensitivity
    return {"status": "ok"}


@router.post("/restart-recording")
def restart_recording():
    if _restart_callback:
        return _restart_callback()
    logger.warning("录制重启回调未注册")
    return {"status": "error", "message": "录制重启回调未注册"}
