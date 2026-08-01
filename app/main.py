"""TimeCut - FastAPI 应用入口"""

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, get_session, Camera
from recorder import RecorderManager, RecordingCleaner
from highlighter import HighlightScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("timecut")

recorder = RecorderManager()
cleaner = RecordingCleaner()
scheduler = HighlightScheduler(recorder)

# 主事件循环引用：同步路由在线程池中运行，需借此把协程调度回主循环
_main_loop: asyncio.AbstractEventLoop | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _main_loop
    _main_loop = asyncio.get_running_loop()
    logger.info("=" * 40)
    logger.info("TimeCut 启动中...")
    logger.info(f"数据目录: {settings.data_dir}")
    logger.info(f"时区: {settings.tz}")
    logger.info("=" * 40)

    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
    settings.highlights_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    init_db()
    logger.info("数据库初始化完成")

    _init_default_camera()

    if settings.camera_rtsp_url:
        # 启动录制规则调度（时间段 + 间隔）
        recorder.start_scheduler()
        if settings.recording_enabled:
            await recorder.start()
        recorder.scan_new_recordings()
        # 定时扫描新录像文件（每30秒）
        async def periodic_scan():
            while True:
                await asyncio.sleep(30)
                try:
                    recorder.scan_new_recordings()
                except Exception as e:
                    logger.error(f"扫描录像文件失败: {e}")
        scan_task = asyncio.create_task(periodic_scan())
    else:
        logger.warning("未配置摄像头 RTSP 地址，请在 Web UI 中设置")
        scan_task = None

    scheduler.start()

    yield

    scheduler.stop()
    if scan_task:
        scan_task.cancel()
    recorder.stop_scheduler()
    await recorder.stop()
    logger.info("TimeCut 已关闭")


def _init_default_camera():
    session = get_session()
    try:
        cam = session.query(Camera).first()
        if not cam:
            cam = Camera(
                name=settings.camera_name,
                rtsp_url=settings.camera_rtsp_url,
                enabled=True,
            )
            session.add(cam)
            session.commit()
            logger.info(f"已创建默认摄像头: {cam.name}")
    except Exception as e:
        session.rollback()
        logger.error(f"初始化摄像头失败: {e}")
    finally:
        session.close()


app = FastAPI(
    title="TimeCut",
    description="NAS 监控摄像头录像与精华视频管理系统",
    version="0.5.2",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def trigger_restart_recording():
    """重新启动录制（配置变更后）"""
    if _main_loop is None or _main_loop.is_closed():
        return {"status": "error", "message": "主事件循环不可用"}
    asyncio.run_coroutine_threadsafe(recorder.restart(), _main_loop)
    return {"status": "ok", "message": "录制重启已触发"}


async def trigger_start_recording():
    """开始录制"""
    from web.routes.settings import persist_recording_state
    persist_recording_state(True)
    await recorder.start()
    return {"status": "ok", "recording": recorder.is_recording}


async def trigger_stop_recording():
    """停止录制"""
    from web.routes.settings import persist_recording_state
    persist_recording_state(False)
    await recorder.stop()
    return {"status": "ok", "recording": recorder.is_recording}


def trigger_delete_camera():
    """删除摄像头：停止录制"""
    if _main_loop is None or _main_loop.is_closed():
        return {"status": "error", "message": "主事件循环不可用"}
    asyncio.run_coroutine_threadsafe(recorder.stop(), _main_loop)
    return {"status": "ok"}


from web.routes import cameras_router, recordings_router, highlights_router, settings_router, diary_router
from web.routes.settings import register_restart_callback, register_delete_camera_callback
from web.routes.highlights import register_highlight_callback
from web.routes.recordings import register_control_callback
register_restart_callback(trigger_restart_recording)


async def trigger_manual_highlight(date: str):
    """手动生成指定日期的精华视频"""
    await scheduler.run_daily_highlight(date)


register_highlight_callback(trigger_manual_highlight)
register_control_callback("start", trigger_start_recording)
register_control_callback("stop", trigger_stop_recording)
register_delete_camera_callback(trigger_delete_camera)

app.include_router(cameras_router)
app.include_router(recordings_router)
app.include_router(highlights_router)
app.include_router(settings_router)
app.include_router(diary_router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "recording": recorder.is_recording,
        "version": "0.5.2",
    }


static_dir = Path(__file__).parent / "web" / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.web_port, reload=False)
