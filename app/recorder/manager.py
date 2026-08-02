"""录像管理器 - 使用 FFmpeg segment 实现循环录像"""

import asyncio
import subprocess
import logging
import threading
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
        self._failures = 0
        self._scheduler_task: asyncio.Task | None = None
        self._tz = ZoneInfo(settings.tz)
        # 串行化 start/stop，避免并发调用在 create_subprocess_exec 前
        # 同时通过存活检查，导致启动两个 ffmpeg 写同一文件
        self._start_lock = asyncio.Lock()
        self._remuxing = False  # TS→MP4 转封装并发保护

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
        # 每段录制 seg 分钟，录完后间隔 interval 分钟再录下一段
        interval = settings.recording_interval_minutes
        if interval <= 0:
            return True
        seg = settings.recording_segment_minutes
        if seg <= 0:
            seg = 1
        cycle = interval + seg
        total_min = now.hour * 60 + now.minute
        return (total_min % cycle) < seg

    def _ensure_dirs(self):
        settings.recordings_dir.mkdir(parents=True, exist_ok=True)
        settings.log_dir.mkdir(parents=True, exist_ok=True)

    def _build_segment_pattern(self) -> str:
        today = datetime.now(self._tz).strftime("%Y-%m-%d")
        seg_dir = settings.recordings_dir / today
        seg_dir.mkdir(parents=True, exist_ok=True)
        # MPEG-TS 中间段：写入稳定，关闭后由 _remux_closed_segments 转封装回 MP4
        return str(seg_dir / "%Y%m%d_%H%M%S.ts")

    def _get_stream_url(self) -> str:
        rtsp = settings.camera_rtsp_url
        if not rtsp:
            rtsp = "rtsp://go2rtc:8554/camera1"
        return rtsp

    def _get_stream_url(self) -> str:
        rtsp = settings.camera_rtsp_url
        if not rtsp:
            rtsp = "rtsp://go2rtc:8554/camera1"
        return rtsp

    async def start(self):
        async with self._start_lock:
            # 防重复启动：已有录制进程存活时直接跳过（进程状态比文件大小检测可靠）
            proc = self._process
            if proc is not None and proc.returncode is None:
                self._running = True
                logger.warning("录制进程仍在运行，跳过重复启动")
                return
            if self._running:
                # 状态标志与进程不一致（监控异常残留），复位后重新启动
                logger.warning("录制状态标志残留，复位后重启")
                self._running = False
            self._stopping = False
            self._ensure_dirs()
            stream_url = self._get_stream_url()
            seg_pattern = self._build_segment_pattern()
            seg_sec = settings.recording_segment_minutes * 60
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-timeout", "15000000",  # RTSP socket I/O 超时 15 秒（微秒）
                "-rw_timeout", "15000000",  # 读写超时 15 秒：上游断流但连接不断时让 ffmpeg 主动报错退出，
                                            # 避免"进程挂起不写数据、segment 永不轮转"的静默故障
                "-use_wallclock_as_timestamps", "1",
                "-i", stream_url,
                # 复用 go2rtc 转码后的 H264/AAC，直接封装不转码，降低 NAS CPU 负担、减少断流
                "-c:v", "copy",
                "-c:a", "copy",
                # MPEG-TS 分段录制：TS 无 moov/封段概念，分段轮转时不会报
                # "Error writing trailer of output file"，从根上消除分段边界崩溃；
                # 关闭的分段由 _remux_closed_segments 转封装回 MP4 供网页播放
                "-f", "segment",
                "-segment_time", str(seg_sec),
                "-segment_time_delta", "1",  # 允许稍等关键帧再切分，段边界更干净
                "-segment_format", "mpegts",
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
        # 绑定本次启动的进程对象，避免 self._process 被后续启动覆盖后监控错乱
        proc = self._process
        if proc is None:
            return
        stderr_data = b""
        # 并行监控：进程退出检测 + 写卡死检测，任一触发即结束监控
        # （上游断流但 TCP 连接不断时 ffmpeg 会静默挂起，仅靠进程退出检测无法感知）
        stderr_task = asyncio.create_task(self._drain_stderr(proc))
        stall_task = asyncio.create_task(self._watch_write_stall(proc))
        await asyncio.wait({stderr_task, stall_task}, return_when=asyncio.FIRST_COMPLETED)
        for t in (stderr_task, stall_task):
            if not t.done():
                t.cancel()
        if stderr_task.done():
            try:
                stderr_data = stderr_task.result()
            except Exception:
                stderr_data = b""
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            try:
                await proc.wait()
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass
        finally:
            # 仅当监控的仍是当前进程时才复位标志
            if self._process is proc:
                self._running = False
        if proc.returncode == 0:
            self._failures = 0
            logger.info("录制进程正常退出")
            return
        self._failures += 1
        logger.error(
            f"录制进程异常退出 (code={proc.returncode}): "
            f"{stderr_data.decode(errors='replace')[-500:]}"
        )
        # 连续失败过多（如 RTSP 地址配置错误）时暂停，避免死循环快速重启
        if self._failures >= 6:
            logger.error("录制连续失败 6 次，暂停 60 秒后重试")
            await asyncio.sleep(60)
            self._failures = 0
            if self._stopping or not self._should_record():
                return
            logger.info("正在重启录制...")
            await self.start()
            return
        # 录制进程异常退出后自动恢复（短暂等待避免 RTSP 瞬时故障时死循环）
        await asyncio.sleep(2)
        if self._stopping or not self._should_record():
            return
        logger.info("录制进程异常退出，正在自动重启...")
        await self.start()

    async def _drain_stderr(self, proc):
        """持续读取 stderr 直到进程退出，返回完整输出

        按块读取而非 readline：ffmpeg 某次错误可能单行超过 64KB，
        asyncio readline 会抛 "Separator is not found, and chunk exceed the limit"
        ValueError，导致监控任务崩溃后无人再检测进程（录制就永远停着）。
        """
        data = b""
        while True:
            chunk = await proc.stderr.read(65536)
            if not chunk:
                break
            data += chunk
        return data

    def _latest_segment_file(self):
        """当前正在录制的 segment 文件（目录中最近修改的 ts/mp4）"""
        rec_dir = settings.recordings_dir
        if not rec_dir.exists():
            return None
        files = []
        for f in rec_dir.rglob("*"):
            if f.suffix.lower() not in (".mp4", ".ts"):
                continue
            try:
                files.append((f.stat().st_mtime, f))
            except OSError:
                continue
        if not files:
            return None
        files.sort(key=lambda x: x[0], reverse=True)
        return files[0][1]

    async def _watch_write_stall(self, proc):
        """写卡死检测：segment 文件长时间无增长说明 ffmpeg 挂起（如上游断流但连接不断），
        达到阈值后强制终止进程，让主监控走自动重启分支"""
        last_size = None
        stall_count = 0
        while True:
            await asyncio.sleep(60)
            if self._process is not proc:
                return  # 已被新进程替换，退出检测
            try:
                current = self._latest_segment_file()
                size = current.stat().st_size if current else None
            except OSError:
                size = None
            if size is not None and last_size is not None and size == last_size:
                stall_count += 1
                logger.warning(
                    f"录制文件 {current.name if current else ''} 大小无增长"
                    f"（{stall_count} 次，约 {stall_count * 60} 秒）"
                )
            else:
                if size is not None:
                    last_size = size
                stall_count = 0
            if stall_count >= 3:
                logger.error("录制文件超 3 分钟无增长，判定 ffmpeg 挂起，强制终止进程")
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return

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

    def _remux_closed_segments(self):
        """把已关闭的 TS 分段转封装为 MP4（-c copy 不重编码），完成后删除 TS。

        在后台线程执行避免阻塞事件循环；录制中跳过最新的 TS（可能是正在写的段，
        误删会让 ffmpeg 写进已删除的 inode，导致该段数据丢失）。
        """
        if self._remuxing:
            return
        self._remuxing = True
        try:
            rec_dir = settings.recordings_dir
            if not rec_dir.exists():
                return
            now = datetime.now().timestamp()
            ts_files = [p for p in rec_dir.rglob("*.ts")]
            if not ts_files:
                return
            ts_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            skip_newest = self._running  # 录制中保护正在写的段
            for i, fpath in enumerate(ts_files):
                if skip_newest and i == 0:
                    continue
                try:
                    stat = fpath.stat()
                except OSError:
                    continue
                age = now - stat.st_mtime
                if age < 90:
                    continue  # 刚轮转仍在收尾，等下一轮
                mp4 = fpath.with_suffix(".mp4")
                if mp4.exists():
                    # 已转封装过，清掉残留 TS
                    try:
                        fpath.unlink()
                        logger.info(f"清理已转换的 TS: {fpath.name}")
                    except OSError as e:
                        logger.warning(f"删除 TS 失败 {fpath}: {e}")
                    continue
                if age > 24 * 3600:
                    # 超过一天仍未转成（如 ffmpeg 持续失败），兜底删除防磁盘泄漏
                    logger.warning(f"TS 转封装持续失败，删除残留: {fpath.name}")
                    try:
                        fpath.unlink()
                    except OSError:
                        pass
                    continue
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(fpath),
                     "-c", "copy", "-movflags", "+faststart", str(mp4)],
                    capture_output=True, text=True, timeout=600,
                )
                if mp4.exists() and mp4.stat().st_size > 0:
                    try:
                        fpath.unlink()
                    except OSError:
                        pass
                    logger.info(
                        f"TS 转封装完成: {mp4.name} "
                        f"({mp4.stat().st_size / 1024 / 1024:.1f}MB)"
                    )
                else:
                    logger.warning(
                        f"TS 转封装失败: {fpath.name} {result.stderr[-200:]}"
                    )
        except Exception as e:
            logger.error(f"TS 转封装异常: {e}")
        finally:
            self._remuxing = False

    def scan_new_recordings(self):
        from database import get_session, Recording
        rec_dir = settings.recordings_dir
        if rec_dir.exists() and any(rec_dir.rglob("*.ts")):
            threading.Thread(target=self._remux_closed_segments, daemon=True).start()
        session = get_session()
        try:
            rec_dir = settings.recordings_dir
            if not rec_dir.exists():
                return
            for fpath in sorted(rec_dir.rglob("*.mp4")):
                rel = fpath.relative_to(rec_dir)
                try:
                    stat = fpath.stat()
                except OSError:
                    continue
                exists = (
                    session.query(Recording)
                    .filter(Recording.file_path == str(rel))
                    .first()
                )
                if exists:
                    # ffmpeg 写入期间记录的旧大小已过期，刷新为最新文件大小
                    if exists.file_size != stat.st_size:
                        exists.file_size = stat.st_size
                    continue
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
