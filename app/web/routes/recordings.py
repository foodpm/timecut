"""录像文件浏览 API"""

import logging
import subprocess

from fastapi import APIRouter, Query, HTTPException, Response
from fastapi.responses import FileResponse

from database import get_session, Recording
from config import settings

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

# 录制控制回调（由 main.py 注册，避免循环导入）
_control_callbacks = {}


def register_control_callback(action: str, cb):
    _control_callbacks[action] = cb


@router.post("/control/{action}")
async def control_recording(action: str):
    """控制录制开始/停止"""
    cb = _control_callbacks.get(action)
    if not cb:
        raise HTTPException(400, f"未知操作: {action}")
    return await cb()


@router.get("")
def list_recordings(
    date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    session = get_session()
    try:
        # 清理孤儿记录：文件已被删除（如用户手动删除录像文件）的记录直接从数据库移除
        _purge_missing_recordings(session)
        query = session.query(Recording).order_by(Recording.start_time.desc())
        if date:
            query = query.filter(Recording.start_time >= date)
            query = query.filter(Recording.start_time < f"{date}T23:59:59")
        total = query.count()
        records = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "total": total, "page": page, "page_size": page_size,
            "items": [{
                "id": r.id, "camera_id": r.camera_id,
                "file_path": r.file_path,
                "file_size": r.file_size,
                "file_size_mb": round(r.file_size / 1024 / 1024, 1) if r.file_size else 0,
                "duration": r.duration,
                "start_time": r.start_time.isoformat() if r.start_time else None,
                "end_time": r.end_time.isoformat() if r.end_time else None,
                "has_motion": r.has_motion, "motion_score": r.motion_score,
            } for r in records],
        }
    finally:
        session.close()


def _purge_missing_recordings(session):
    """删除数据库中文件已不存在的记录（用户在文件系统删除录像后保持列表干净）"""
    try:
        rows = session.query(Recording).all()
        missing = [
            r.id for r in rows
            if not (settings.recordings_dir / r.file_path).exists()
        ]
        if missing:
            session.query(Recording).filter(
                Recording.id.in_(missing)
            ).delete(synchronize_session=False)
            session.commit()
            logger.info(f"清理 {len(missing)} 条录像记录（对应文件已被删除）")
    except Exception as e:
        session.rollback()
        logger.warning(f"清理孤儿录像记录失败: {e}")


@router.get("/play/{recording_id}")
def play_recording(recording_id: int):
    """播放录像文件"""
    session = get_session()
    try:
        rec = session.query(Recording).filter(Recording.id == recording_id).first()
        if not rec:
            raise HTTPException(404, "录像文件不存在")
        file_path = settings.recordings_dir / rec.file_path
        if not file_path.exists():
            raise HTTPException(404, "录像文件已丢失")
        return FileResponse(
            str(file_path),
            media_type="video/mp4",
            filename=file_path.name,
            headers={"Accept-Ranges": "bytes"},
        )
    finally:
        session.close()


@router.get("/{recording_id}/thumbnail")
def recording_thumbnail(recording_id: int):
    """返回录像缩略图（首次请求时用 FFmpeg 提取一帧并缓存）"""
    session = get_session()
    try:
        rec = session.query(Recording).filter(Recording.id == recording_id).first()
        if not rec:
            raise HTTPException(404, "录像文件不存在")
    finally:
        session.close()
    video_path = settings.recordings_dir / rec.file_path
    if not video_path.exists():
        raise HTTPException(404, "录像文件已丢失")
    thumb_path = settings.recordings_dir / "thumbs" / f"{video_path.stem}.jpg"
    if not thumb_path.exists():
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "2", "-i", str(video_path),
                 "-frames:v", "1", "-vf", "scale=320:-1", "-q:v", "5", str(thumb_path)],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            logger.warning(f"生成缩略图失败: {e}")
        if not thumb_path.exists() or thumb_path.stat().st_size == 0:
            return Response(status_code=204)
    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.get("/dates")
def get_available_dates():
    recordings_dir = settings.recordings_dir
    if not recordings_dir.exists():
        return {"dates": []}
    dates = sorted((d.name for d in recordings_dir.iterdir() if d.is_dir()), reverse=True)
    return {"dates": dates}


@router.get("/stats")
def get_recording_stats():
    """统计录像总数与占用空间（按文件系统实时统计，数据库中的 file_size 可能过期）"""
    rec_dir = settings.recordings_dir
    total_bytes = 0
    total_count = 0
    if rec_dir.exists():
        for f in rec_dir.rglob("*.mp4"):
            total_count += 1
            try:
                total_bytes += f.stat().st_size
            except OSError:
                pass
    return {
        "total_recordings": total_count,
        "total_size_gb": round(total_bytes / 1024 / 1024 / 1024, 2),
        "retention_days": settings.recording_retention_days,
    }
