"""摄像头管理 API"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import get_session, Camera
from config import settings

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


class CameraUpdate(BaseModel):
    name: str | None = None
    rtsp_url: str | None = None
    enabled: bool | None = None


@router.get("")
def list_cameras():
    session = get_session()
    try:
        cameras = session.query(Camera).all()
        return [{
            "id": c.id, "name": c.name, "rtsp_url": c.rtsp_url,
            "enabled": c.enabled,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        } for c in cameras]
    finally:
        session.close()


@router.get("/{camera_id}")
def get_camera(camera_id: int):
    session = get_session()
    try:
        cam = session.query(Camera).filter(Camera.id == camera_id).first()
        if not cam:
            raise HTTPException(404, "摄像头不存在")
        return {
            "id": cam.id, "name": cam.name, "rtsp_url": cam.rtsp_url,
            "enabled": cam.enabled,
            "created_at": cam.created_at.isoformat() if cam.created_at else None,
        }
    finally:
        session.close()


@router.put("/{camera_id}")
def update_camera(camera_id: int, data: CameraUpdate):
    session = get_session()
    try:
        cam = session.query(Camera).filter(Camera.id == camera_id).first()
        if not cam:
            raise HTTPException(404, "摄像头不存在")
        if data.name is not None:
            cam.name = data.name
            settings.camera_name = data.name
        if data.rtsp_url is not None:
            cam.rtsp_url = data.rtsp_url
            settings.camera_rtsp_url = data.rtsp_url
        if data.enabled is not None:
            cam.enabled = data.enabled
        session.commit()
        return {"status": "ok", "id": camera_id}
    finally:
        session.close()


@router.get("/{camera_id}/stream-url")
def get_stream_url(camera_id: int):
    return {
        "hls": "http://go2rtc:8888/api/hls/camera1.m3u8",
        "webrtc": "http://go2rtc:8888/api/webrtc/camera1",
    }
