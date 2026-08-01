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
        self._tz = ZoneInfo(settings.tz)

    @property
    def is_recording(self) -> bool:
        return self._running

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
            if not self._stopping and not self._running:
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
