"""精华检测调度器 - 每天定时执行"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database import get_session, Highlight, Recording
from .detector import MotionDetector
from .ai_selector import AISelector
from .clipper import HighlightClipper

logger = logging.getLogger("timecut.scheduler")


class HighlightScheduler:
    """调度每日精华视频的检测与合成任务"""

    def __init__(self, recorder_manager=None):
        self._scheduler = AsyncIOScheduler(timezone=settings.tz)
        self._detector = MotionDetector()
        self._clipper = HighlightClipper()
        self._recorder = recorder_manager
        self._tz = ZoneInfo(settings.tz)

    def start(self):
        if not settings.highlight_enabled:
            logger.info("精华视频功能已禁用")
            return
        hour, minute = settings.highlight_schedule_time.split(":")
        self._scheduler.add_job(
            self.run_daily_highlight,
            "cron", hour=int(hour), minute=int(minute),
            id="daily_highlight", replace_existing=True,
        )
        self._scheduler.start()
        logger.info(f"精华检测定时任务已启动: 每天 {settings.highlight_schedule_time}")

    async def run_daily_highlight(self, target_date: str | None = None):
        logger.info("===== 开始每日精华检测 =====")
        if self._recorder:
            self._recorder.scan_new_recordings()
        today = datetime.now(self._tz)
        if target_date:
            date_str = target_date
            date_dir = target_date
        else:
            yesterday = today - timedelta(days=1)
            date_str = yesterday.strftime("%Y-%m-%d")
            date_dir = yesterday.strftime("%Y-%m-%d")
        day_dir = settings.recordings_dir / date_dir
        if not day_dir.exists():
            logger.info(f"前一天无录像文件 ({date_dir})")
            return
        video_files = sorted(day_dir.glob("*.mp4"))
        if not video_files:
            logger.info(f"前一天无录像片段 ({date_dir})")
            return
        logger.info(f"找到 {len(video_files)} 个录像片段待分析")
        all_segments = []  # list of (MotionSegment, source_file_path)
        for vf in video_files:
            segments = self._detector.analyze(vf)
            for seg in segments:
                all_segments.append((seg, vf))
        if not all_segments:
            logger.info("未检测到运动，跳过精华生成")
            return
        logger.info(f"共检测到 {len(all_segments)} 个运动片段")
        if settings.ai_enabled:
            logger.info("启用大模型识别精华片段")
            all_segments = AISelector().score_segments(all_segments)
        output = self._clipper.create_highlight(
            video_files=video_files, segments=all_segments,
        )
        if output and output.exists():
            session = get_session()
            try:
                hl = Highlight(
                    camera_id=1,
                    file_path=str(output.relative_to(settings.highlights_dir.parent)),
                    file_size=output.stat().st_size,
                    duration=self._clipper.target_duration,
                    date=date_str, clip_count=len(all_segments),
                    strategy="motion",
                )
                session.add(hl)
                session.commit()
                logger.info("精华视频记录已保存到数据库")
            except Exception as e:
                session.rollback()
                logger.error(f"保存精华视频记录失败: {e}")
            finally:
                session.close()
        logger.info("===== 每日精华检测完成 =====")

    def stop(self):
        self._scheduler.shutdown(wait=False)
        logger.info("精华检测调度器已停止")
