"""精华检测调度器 - 每天定时执行"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database import get_session, Highlight
from diary.generator import run_diary_for_date
from .detector import MotionDetector
from .ai_selector import AISelector
from .clipper import HighlightClipper
from .job import job

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
        hour, minute = settings.highlight_schedule_time.split(":")
        if settings.highlight_enabled:
            self._scheduler.add_job(
                self.run_daily_highlight,
                "cron", hour=int(hour), minute=int(minute),
                id="daily_highlight", replace_existing=True,
            )
            logger.info(f"精华检测定时任务已启动: 每天 {settings.highlight_schedule_time}")
        if settings.diary_enabled:
            self._scheduler.add_job(
                self.run_daily_diary,
                "cron", hour=int(hour), minute=int(minute),
                id="daily_diary", replace_existing=True,
            )
            logger.info(f"日记生成定时任务已启动: 每天 {settings.highlight_schedule_time}")
        self._scheduler.start()
        if not settings.highlight_enabled and not settings.diary_enabled:
            logger.info("精华检测与日记功能均未启用")

    async def run_daily_diary(self, target_date: str | None = None):
        """每日日记生成入口（重活放后台线程执行）"""
        today = datetime.now(self._tz)
        if target_date:
            date_str = target_date
        else:
            date_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        day_dir = settings.recordings_dir / date_str
        if not day_dir.exists() or not list(day_dir.glob("*.mp4")):
            logger.info(f"{date_str} 无录像，跳过日记生成")
            return
        await asyncio.to_thread(run_diary_for_date, date_str)

    async def run_daily_highlight(self, target_date: str | None = None):
        """精华检测入口（重活放后台线程执行，避免阻塞 Web 服务）"""
        logger.info("===== 开始每日精华检测 =====")
        if self._recorder:
            self._recorder.scan_new_recordings()
        today = datetime.now(self._tz)
        if target_date:
            date_str = target_date
        else:
            date_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        day_dir = settings.recordings_dir / date_str
        if not day_dir.exists():
            logger.info(f"前一天无录像文件 ({date_str})")
            return
        video_files = sorted(day_dir.glob("*.mp4"))
        if not video_files:
            logger.info(f"前一天无录像片段 ({date_str})")
            return
        await asyncio.to_thread(self._run_highlight, date_str, video_files)

    def _run_highlight(self, date_str: str, video_files: list):
        """在后台线程执行检测、打分、拼接，并更新任务进度与日志"""
        logger.info(f"找到 {len(video_files)} 个录像片段待分析 ({date_str})")
        job.start(date_str, total=len(video_files))
        job.log_line(f"开始生成 {date_str} 的精华视频，共 {len(video_files)} 个录像片段")
        try:
            all_segments = []  # list of (MotionSegment, source_file_path)
            for i, vf in enumerate(video_files, 1):
                job.set_stage("分析录像", done=i - 1, total=len(video_files), current=vf.name)
                job.log_line(f"[{i}/{len(video_files)}] 运动检测: {vf.name}")
                segments = self._detector.analyze(vf)
                for seg in segments:
                    all_segments.append((seg, vf))
            if not all_segments:
                job.finish(False, "未检测到运动，跳过精华生成")
                logger.info("未检测到运动，跳过精华生成")
                return
            logger.info(f"共检测到 {len(all_segments)} 个运动片段")
            job.log_line(f"共检测到 {len(all_segments)} 个运动片段")
            ai_success = False
            if settings.ai_enabled:
                logger.info("启用大模型识别精华片段")
                job.set_stage("大模型打分", done=0, total=0)
                ai_selector = AISelector()
                all_segments, ai_success = ai_selector.score_segments(
                    all_segments, progress_cb=job.ai_score
                )
                if not ai_success:
                    logger.warning("大模型调用全部失败，自动降级为系统自动（运动检测）")
                    job.log_line("大模型调用全部失败，自动降级为系统自动（运动检测）")
            job.set_stage("拼接片段", current="正在拼接片段，视频越长耗时越久...")
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
                        strategy="ai" if (settings.ai_enabled and ai_success) else "motion",
                    )
                    session.add(hl)
                    session.commit()
                    logger.info("精华视频记录已保存到数据库")
                except Exception as e:
                    session.rollback()
                    logger.error(f"保存精华视频记录失败: {e}")
                finally:
                    session.close()
                job.finish(True, f"生成成功: {output.name}（{output.stat().st_size / 1024 / 1024:.1f} MB）")
            else:
                job.finish(False, "精华视频生成失败，请查看日志")
        except Exception as e:
            logger.exception("精华生成异常")
            job.finish(False, f"生成异常: {e}")
        logger.info("===== 每日精华检测完成 =====")

    def stop(self):
        self._scheduler.shutdown(wait=False)
        logger.info("精华检测调度器已停止")
