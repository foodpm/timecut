"""录像管理器 - 使用 FFmpeg segment 实现循环录像"""

import asyncio
import subprocess
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from config import settings
from database import get_session, Recording, Camera

logger = logging.getLogger("timecut.recorder")


class RecorderManager:
    """管理单个摄像头的 FFmpeg 循环录制进程"""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._running = False
        self._stopping = False
        self._scheduler_task: asyncio.Task | None = None
        self._tz = ZoneInfo(settings.tz)

    @property
    def is_recording(self) -> bool:
        return self._running

    # ── 录制规则调度（时间段 + 间隔）──
    def start_scheduler(self):
        """启动录制规则调度循环"""
        if self._scheduler_task and not self._scheduler_task.done():
            return
        self._scheduler_task = asyncio.create_task(self._schedule_loop())
        logger.info("录制规则调度已启动")

    def stop_scheduler(self):
        if self._scheduler_task:
            self._scheduler_task.cancel()
            self._scheduler_task = None
        logger.info("录制规则调度已停止")

    async def _schedule_loop(self):
        while True:
            await asyncio.sleep(10)
            try:
                await self._apply_schedule()
            except Exception as e:
                logger.error(f"录制规则调度异常: {e}")

    async def _apply_schedule(self):
        """根据录制时间段和间隔决定录制启停"""
        if not settings.recording_enabled:
            return
        should = self._should_record()
        if should and not self._running:
            await self.start()
        elif not should and self._running:
            await self.stop()

    def _should_record(self) -> bool:
        """是否应当录制（时间段 + 间隔规则）"""
        now = datetime.now(self._tz)
        # 1. 录制时间段判断（支持跨午夜）
        try:
            start = datetime.strptime(settings.recording_start_time, "%H:%M").time()
            end = datetime.strptime(settings.recording_end_time, "%H:%M").time()
        except ValueError:
            return True
        t = now.time()
        in_window = (start <= t <= end) if start <= end else (t >= start or t <= end)
        if not in_window:
            return False
        # 2. 录制间隔判断（0 = 连续录制）
        interval = settings.recording_interval_minutes
        if interval <= 0:
            return True
        seg = settings.recording_segment_minutes
        if seg >= interval:
            return True
        total_min = now.hour * 60 + now.minute
        return (total_min % interval) < seg

    def _ensure_dirs(self):
        settings.recordings_dir.mkdir(parents=True, exist_ok=True)
        settings.log_dir.mkdir(parents=True, exist_ok=True)

    def _build_segment_pattern(self) -> str:
        today = datetime.now(self._tz).strftime("%Y-%m-%d")
        seg_dir = settings.recordings_dir / today
        seg_dir.mkdir(parents=True, exist_ok=True)
        return str(seg_dir / "%Y%m%d_%H%M%S.mp4")

    def _get_stream_url(self) -> str:
        rtsp = settings.camera_rtsp_url
        if not rtsp:
            rtsp = "rtsp://go2rtc:8554/camera1"
        return rtsp

    async def start(self):
        if self._running:
            logger.warning("录制已在运行中")
            return
        self._stopping = False
        self._ensure_dirs()
        stream_url = self._get_stream_url()
        seg_pattern = self._build_segment_pattern()
        seg_sec = settings.recording_segment_minutes * 60
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-use_wallclock_as_timestamps", "1",
            "-i", stream_url,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "64k",
            "-movflags", "+faststart",
            "-f", "segment",
            "-segment_time", str(seg_sec),
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            "-strftime", "1",
            seg_pattern,
        ]
        logger.info(f"启动录制: {' '.join(cmd)}")
        self._running = True
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        asyncio.create_task(self._monitor_process())

    async def _monitor_process(self):
        if not self._process:
            return
        stderr_data = b""
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                stderr_data += line
            await self._process.wait()
        except Exception as e:
            logger.error(f"监控录制进程异常: {e}")
        finally:
            self._running = False
        if self._process.returncode != 0:
            logger.error(
                f"录制进程异常退出 (code={self._process.returncode}): "
                f"{stderr_data.decode(errors='replace')[-500:]}"
            )
            # 录制进程异常退出后自动恢复（等待几秒避免 RTSP 瞬时故障时死循环）
            await asyncio.sleep(5)
            if not self._stopping and not self._running and self._should_record():
                logger.info("录制进程异常退出，正在自动重启...")
                await self.start()
        else:
            logger.info("录制进程正常退出")

    async def stop(self):
        self._stopping = True
        if self._process and self._running:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except ProcessLookupError:
                logger.warning("录制进程已退出")
        self._running = False
        self._process = None
        logger.info("录制已停止")

    async def restart(self):
        await self.stop()
        await asyncio.sleep(1)
        await self.start()

    def scan_new_recordings(self):
        from database import get_session, Recording
        session = get_session()
        try:
            rec_dir = settings.recordings_dir
            if not rec_dir.exists():
                return
            for fpath in sorted(rec_dir.rglob("*.mp4")):
                rel = fpath.relative_to(rec_dir)
                exists = (
                    session.query(Recording)
                    .filter(Recording.file_path == str(rel))
                    .first()
                )
                if exists:
                    continue
                stat = fpath.stat()
                stem = fpath.stem
                try:
                    start_time = datetime.strptime(stem, "%Y%m%d_%H%M%S")
                    start_time = start_time.replace(tzinfo=self._tz)
                except ValueError:
                    start_time = datetime.fromtimestamp(stat.st_mtime)
                end_time = datetime.fromtimestamp(stat.st_mtime, tz=self._tz)
                duration = 0.0
                try:
                    result = subprocess.run(
                        [
                            "ffprobe", "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1",
                            str(fpath),
                        ],
                        capture_output=True, text=True, timeout=30,
                    )
                    if result.stdout:
                        duration = float(result.stdout.strip())
                except Exception:
                    pass
                # 过滤过短片段（RTSP 启动/断流时会产生几秒的碎片文件）
                if duration > 0 and duration < 10:
                    logger.warning(f"跳过过短录像片段: {rel} ({duration:.1f}s)")
                    continue
                rec = Recording(
                    camera_id=1,
                    file_path=str(rel),
                    file_size=stat.st_size,
                    duration=duration,
                    start_time=start_time,
                    end_time=end_time,
                )
                session.add(rec)
            session.commit()
            logger.info("录像文件数据库扫描完成")
        except Exception as e:
            session.rollback()
            logger.error(f"扫描录像文件失败: {e}")
        finally:
            session.close()
