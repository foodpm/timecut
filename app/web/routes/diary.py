"""日记管理 API"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import settings
from database import get_session, Diary
from diary.generator import get_status, run_diary_for_date

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/diary", tags=["diary"])


@router.get("")
def list_diary():
    """返回所有日记日期（用于网格展示）"""
    session = get_session()
    try:
        rows = session.query(Diary).order_by(Diary.date.desc()).all()
        return {"items": [
            {
                "date": r.date,
                "preview": (r.content or "").strip()[:60],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]}
    finally:
        session.close()


@router.get("/status")
def diary_status():
    """返回日记生成任务状态（兼容旧版简单状态）"""
    return get_status()


@router.get("/job")
def diary_job_status():
    """返回日记生成任务进度与日志（含阶段、百分比、滚动日志）"""
    return get_status()


@router.get("/{date}")
def get_diary(date: str):
    """返回某天的日记详情（优先读日记文件，文件不存在时回退数据库内容）"""
    session = get_session()
    try:
        rec = session.query(Diary).filter(Diary.date == date).first()
        if not rec:
            raise HTTPException(404, "该日期暂无日记")
        content = rec.content
        fpath = settings.diaries_dir / f"{date}.md"
        if fpath.exists():
            try:
                content = fpath.read_text(encoding="utf-8")
            except Exception:
                pass
        return {
            "date": rec.date,
            "content": content,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        }
    finally:
        session.close()


@router.post("/trigger")
async def trigger_diary():
    """手动生成最近一天有录像的日记（后台执行，立即返回）"""
    if get_status()["running"]:
        return {"status": "error", "message": "已有日记任务正在生成中，请稍后再试"}
    date = _find_latest_recording_date()
    if not date:
        return {"status": "error", "message": "没有可用的录像，无法生成日记"}
    asyncio.create_task(_run_async(date))
    return {"status": "ok", "message": f"已开始生成 {date} 的日记，可查看生成状态"}


async def _run_async(date: str):
    await asyncio.to_thread(run_diary_for_date, date)


def _find_latest_recording_date() -> str | None:
    """找到最近一个有录像文件的日期目录"""
    rec_dir = Path(settings.data_dir) / "recordings"
    if not rec_dir.exists():
        return None
    for d in sorted((x.name for x in rec_dir.iterdir() if x.is_dir()), reverse=True):
        if list((rec_dir / d).glob("*.mp4")):
            return d
    return None
