"""精华视频管理 API"""

import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from database import get_session, Highlight
from config import settings

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/highlights", tags=["highlights"])

_trigger_highlight_callback = None


def register_highlight_callback(callback):
    global _trigger_highlight_callback
    _trigger_highlight_callback = callback


@router.get("")
def list_highlights(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), sort: str = Query("asc", pattern="^(asc|desc)$")):
    session = get_session()
    try:
        query = session.query(Highlight)
        # 按录制日期排序（asc = 录制时间在前的在前；desc = 最近的在前）
        if sort == "desc":
            query = query.order_by(Highlight.date.desc(), Highlight.id.desc())
        else:
            query = query.order_by(Highlight.date.asc(), Highlight.id.asc())
        total = query.count()
        records = query.offset((page - 1) * page_size).limit(page_size).all()
        return {
            "total": total, "page": page, "page_size": page_size,
            "items": [{
                "id": h.id, "camera_id": h.camera_id, "file_path": h.file_path,
                "file_size": h.file_size,
                "file_size_mb": round(h.file_size / 1024 / 1024, 1) if h.file_size else 0,
                "duration": h.duration,
                "duration_min": round(h.duration / 60, 1) if h.duration else 0,
                "date": h.date, "clip_count": h.clip_count,
                "strategy": h.strategy,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            } for h in records],
        }
    finally:
        session.close()


@router.get("/{highlight_id}/thumbnail")
def highlight_thumbnail(highlight_id: int):
    """返回精华视频缩略图（首次请求时用 FFmpeg 提取一帧并缓存）"""
    session = get_session()
    try:
        hl = session.query(Highlight).filter(Highlight.id == highlight_id).first()
        if not hl:
            raise HTTPException(404, "精华视频不存在")
    finally:
        session.close()
    video_path = Path(settings.data_dir) / hl.file_path
    if not video_path.exists():
        raise HTTPException(404, "视频文件不存在")
    thumb_path = Path(settings.data_dir) / "highlights" / "thumbs" / f"{video_path.stem}.jpg"
    if not thumb_path.exists():
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "2", "-i", str(video_path),
                 "-frames:v", "1", "-vf", "scale=320:-1", "-q:v", "5", str(thumb_path)],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            logger.warning(f"生成精华缩略图失败: {e}")
        if not thumb_path.exists() or thumb_path.stat().st_size == 0:
            return Response(status_code=204)
    return FileResponse(str(thumb_path), media_type="image/jpeg")


@router.get("/play/{highlight_id}")
def play_highlight(highlight_id: int):
    """在线播放精华视频（支持拖拽进度，无 attachment 下载头）"""
    session = get_session()
    try:
        hl = session.query(Highlight).filter(Highlight.id == highlight_id).first()
        if not hl:
            raise HTTPException(404, "精华视频不存在")
        file_path = Path(settings.data_dir) / hl.file_path
        if not file_path.exists():
            raise HTTPException(404, "视频文件不存在")
        return FileResponse(
            path=str(file_path), media_type="video/mp4",
            headers={"Accept-Ranges": "bytes"},
        )
    finally:
        session.close()


@router.get("/download/{highlight_id}")
def download_highlight(highlight_id: int):
    session = get_session()
    try:
        hl = session.query(Highlight).filter(Highlight.id == highlight_id).first()
        if not hl:
            raise HTTPException(404, "精华视频不存在")
        file_path = Path(settings.data_dir) / hl.file_path
        if not file_path.exists():
            raise HTTPException(404, "视频文件不存在")
        return FileResponse(
            path=str(file_path), media_type="video/mp4",
            filename=f"精华_{hl.date}.mp4",
        )
    finally:
        session.close()


@router.delete("/{highlight_id}")
def delete_highlight(highlight_id: int):
    session = get_session()
    try:
        hl = session.query(Highlight).filter(Highlight.id == highlight_id).first()
        if not hl:
            raise HTTPException(404, "精华视频不存在")
        file_path = Path(settings.data_dir) / hl.file_path
        if file_path.exists():
            file_path.unlink()
        session.delete(hl)
        session.commit()
        return {"status": "ok", "deleted": highlight_id}
    except Exception as e:
        session.rollback()
        raise HTTPException(500, str(e))
    finally:
        session.close()


@router.post("/trigger")
async def trigger_highlight():
    """手动触发精华检测"""
    if _trigger_highlight_callback:
        await _trigger_highlight_callback()
        return {"status": "ok", "message": "精华检测已触发"}
    return {"status": "error", "message": "精华检测未注册"}
