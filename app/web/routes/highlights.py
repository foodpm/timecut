"""精华视频管理 API"""

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, Query, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse

from database import get_session, Highlight
from config import settings
from highlighter.job import job

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/highlights", tags=["highlights"])

_trigger_highlight_callback = None


def register_highlight_callback(callback):
    global _trigger_highlight_callback
    _trigger_highlight_callback = callback


@router.get("/job")
def get_highlight_job():
    """返回当前精华视频生成任务的进度与日志"""
    return job.to_dict()


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
    """返回精华视频缩略图（视频更新后自动重新生成）"""
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
    # 视频比缓存新（内容被重新生成过）时强制重新抽帧，避免旧封面残留
    if not thumb_path.exists() or video_path.stat().st_mtime > thumb_path.stat().st_mtime:
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        if not _generate_thumbnail(video_path, thumb_path):
            if not thumb_path.exists():
                return Response(status_code=204)
    return FileResponse(str(thumb_path), media_type="image/jpeg")


def _generate_thumbnail(video_path: Path, thumb_path: Path) -> bool:
    """多时间点采样抽帧，选曝光最均衡的一帧作为封面（避免黑场/过曝/糊帧）"""
    duration = _probe_duration(video_path)
    offsets = [2.0]
    if duration and duration > 5:
        offsets += [duration * 0.2, duration * 0.5]
    with tempfile.TemporaryDirectory(prefix="timecut_thumb_") as td:
        best = None  # (score, tmp_path)
        for i, ts in enumerate(offsets):
            tmp = Path(td) / f"f{i}.jpg"
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path),
                     "-frames:v", "1", "-vf", "scale=320:-1", "-q:v", "5", str(tmp)],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception:
                continue
            if not tmp.exists() or tmp.stat().st_size == 0:
                continue
            yavg = _frame_luma(tmp)
            if yavg is None:
                continue
            # 亮度越接近 128 越均衡；太暗/过曝直接记低分
            score = -abs(yavg - 128) if 25 <= yavg <= 235 else -100 - abs(yavg - 128)
            if best is None or score > best[0]:
                best = (score, tmp)
        if best:
            try:
                shutil.copy(best[1], thumb_path)
                return True
            except Exception:
                return False
    return False


def _probe_duration(video_path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.stdout:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def _frame_luma(image_path: Path) -> float | None:
    """用 ffmpeg signalstats 计算图片平均亮度（YAVG 0-255），失败返回 None"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-i", str(image_path),
             "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stderr.splitlines():
            m = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", line)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return None


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
        # 仅当没有其他记录引用同一文件时才删除文件（避免多记录共用文件被误删）
        refs = session.query(Highlight).filter(
            Highlight.file_path == hl.file_path,
            Highlight.id != highlight_id,
        ).count()
        if file_path.exists() and refs == 0:
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
    """手动触发精华检测：分析最近一个有录像的日期（后台执行，立即返回）"""
    if not _trigger_highlight_callback:
        return {"status": "error", "message": "精华检测未注册"}
    if job.running:
        return {"status": "error", "message": "已有任务正在生成中，请稍后再试"}
    date = _find_latest_recording_date()
    if not date:
        return {"status": "error", "message": "没有可用的录像，无法生成精华视频"}
    import asyncio
    asyncio.create_task(_trigger_highlight_callback(date))
    return {"status": "ok", "message": f"已开始生成 {date} 的精华视频，可查看实时进度"}


def _find_latest_recording_date() -> str | None:
    """找到最近一个有录像文件的日期目录"""
    rec_dir = Path(settings.data_dir) / "recordings"
    if not rec_dir.exists():
        return None
    for d in sorted((x.name for x in rec_dir.iterdir() if x.is_dir()), reverse=True):
        if list((rec_dir / d).glob("*.mp4")):
            return d
    return None
