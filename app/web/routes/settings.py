"""系统设置 API"""

import json
import logging
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import APIRouter
from pydantic import BaseModel

from config import settings

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 配置字段与 .env 环境变量名映射
_ENV_MAP = {
    "camera_name": "CAMERA_NAME",
    "camera_rtsp_url": "CAMERA_RTSP_URL",
    "recording_retention_days": "RECORDING_RETENTION_DAYS",
    "recording_segment_minutes": "RECORDING_SEGMENT_MINUTES",
    "recording_interval_minutes": "RECORDING_INTERVAL_MINUTES",
    "recording_start_time": "RECORDING_START_TIME",
    "recording_end_time": "RECORDING_END_TIME",
    "highlight_duration_minutes": "HIGHLIGHT_DURATION_MINUTES",
    "highlight_enabled": "HIGHLIGHT_ENABLED",
    "highlight_schedule_time": "HIGHLIGHT_SCHEDULE_TIME",
    "detection_sensitivity": "DETECTION_SENSITIVITY",
    "recording_enabled": "RECORDING_ENABLED",
}


def persist_recording_state(enabled: bool):
    """持久化录制开关状态"""
    settings.recording_enabled = enabled
    _persist_settings({"recording_enabled": enabled})


def _persist_settings(changes: dict):
    """将配置写入 .env 文件（本地开发生效；Docker 内 .env 不存在则忽略）"""
    try:
        from dotenv import set_key
        env_path = Path(".env")
        if not env_path.exists():
            return
        for key, value in changes.items():
            env_var = _ENV_MAP.get(key)
            if env_var:
                set_key(str(env_path), env_var, str(value))
    except Exception as e:
        logger.warning(f"持久化配置到 .env 失败: {e}")

_restart_callback = None
_delete_camera_callback = None


def register_restart_callback(cb):
    global _restart_callback
    _restart_callback = cb


def register_delete_camera_callback(cb):
    global _delete_camera_callback
    _delete_camera_callback = cb


class SettingsUpdate(BaseModel):
    camera_name: str | None = None
    camera_rtsp_url: str | None = None
    recording_retention_days: int | None = None
    recording_segment_minutes: int | None = None
    recording_interval_minutes: int | None = None
    recording_start_time: str | None = None
    recording_end_time: str | None = None
    highlight_duration_minutes: int | None = None
    highlight_enabled: bool | None = None
    highlight_schedule_time: str | None = None
    detection_sensitivity: int | None = None


@router.get("")
def get_settings():
    return {
        "camera_name": settings.camera_name,
        "camera_rtsp_url": settings.camera_rtsp_url,
        "recording_retention_days": settings.recording_retention_days,
        "recording_segment_minutes": settings.recording_segment_minutes,
        "recording_interval_minutes": settings.recording_interval_minutes,
        "recording_start_time": settings.recording_start_time,
        "recording_end_time": settings.recording_end_time,
        "highlight_duration_minutes": settings.highlight_duration_minutes,
        "highlight_enabled": settings.highlight_enabled,
        "highlight_schedule_time": settings.highlight_schedule_time,
        "detection_sensitivity": settings.detection_sensitivity,
    }


@router.get("/go2rtc/streams")
def get_go2rtc_streams():
    """读取 go2rtc 视频流列表，自动生成每个流的 RTSP 地址"""
    try:
        req = urllib.request.Request(
            f"{settings.go2rtc_url}/api/streams",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        logger.warning(f"读取 go2rtc 流失败: {e}")
        return {"streams": [], "error": f"无法连接 go2rtc: {e}"}

    # 从 go2rtc API 地址推断 RTSP 主机（Docker 内为 go2rtc，本地为 localhost）
    parsed = urlparse(settings.go2rtc_url)
    rtsp_host = parsed.hostname or "localhost"

    streams = []
    for name, info in (data or {}).items():
        producers = info.get("producers") or []
        streams.append({
            "name": name,
            "rtsp_url": f"rtsp://{rtsp_host}:8554/{name}",
            "online": len(producers) > 0,
            "source": producers[0].get("url") if producers else None,
        })
    streams.sort(key=lambda s: s["name"])
    return {"streams": streams}


def _restart_go2rtc() -> bool:
    """重启本地 go2rtc 进程（尽力而为，Docker 环境会失败并提示手动重启）"""
    import os
    import signal
    import subprocess
    import time
    try:
        out = subprocess.run(["lsof", "-ti", ":1984"], capture_output=True, text=True, timeout=5)
        pids = out.stdout.strip().split()
        for pid in pids:
            if pid:
                os.kill(int(pid), signal.SIGTERM)
        time.sleep(1.5)
        binary = os.environ.get("GO2RTC_BIN", "/tmp/go2rtc")
        if os.path.exists(binary):
            logf = open("/tmp/go2rtc.log", "a")
            subprocess.Popen(
                [binary], cwd=os.getcwd(),
                stdout=logf, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            time.sleep(2)
            return True
    except Exception as e:
        logger.warning(f"重启 go2rtc 失败: {e}")
    return False


@router.delete("/go2rtc/streams/{name}")
def delete_go2rtc_stream(name: str):
    """删除指定的 go2rtc 视频流：直接修改配置文件 + 重启 go2rtc"""
    config_updated = False

    # 1. 直接修改 go2rtc 配置文件（最可靠，本地可直接写文件）
    cfg_path = Path(settings.go2rtc_config_path)
    if cfg_path.exists():
        try:
            import yaml
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            if name in (data.get("streams") or {}):
                del data["streams"][name]
                cfg_path.write_text(
                    yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
                    encoding="utf-8",
                )
                config_updated = True
        except Exception as e:
            logger.warning(f"修改 go2rtc 配置文件失败: {e}")

    # 2. 配置文件不可写时（如 Docker 只读挂载），回退到 go2rtc API
    if not config_updated:
        try:
            cfg_text = urllib.request.urlopen(
                f"{settings.go2rtc_url}/api/config", timeout=5
            ).read().decode()
            import yaml
            data = yaml.safe_load(cfg_text) or {}
            if name in (data.get("streams") or {}):
                del data["streams"][name]
                new_cfg = yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
                req = urllib.request.Request(
                    f"{settings.go2rtc_url}/api/config",
                    data=new_cfg.encode("utf-8"),
                    method="PUT",
                    headers={"Content-Type": "text/yaml"},
                )
                urllib.request.urlopen(req, timeout=5)
                config_updated = True
        except Exception as e:
            logger.warning(f"通过 API 更新 go2rtc 配置失败: {e}")
            return {"status": "error", "message": f"删除视频流失败: {e}"}

    if not config_updated:
        return {"status": "error", "message": f"视频流 {name} 不存在或无法删除"}

    # 3. 尝试停止运行时流
    try:
        req = urllib.request.Request(
            f"{settings.go2rtc_url}/api/streams?name={quote(name)}",
            method="DELETE",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    # 4. 若流仍在运行，重启 go2rtc 使配置生效
    message = f"已删除视频流 {name}"
    try:
        remaining = json.loads(urllib.request.urlopen(
            f"{settings.go2rtc_url}/api/streams", timeout=5
        ).read())
        if name in remaining:
            if _restart_go2rtc():
                message = f"已删除视频流 {name}（go2rtc 已自动重启）"
            else:
                message = f"已从配置删除 {name}，请重启 go2rtc 后完全生效"
    except Exception:
        pass

    # 5. 若删除的是当前录制使用的流，停止录制并清空摄像头配置
    if settings.camera_rtsp_url.rstrip("/").endswith(f"/{name}"):
        if _delete_camera_callback:
            _delete_camera_callback()
        settings.camera_rtsp_url = ""
        settings.camera_name = ""
        _persist_settings({"camera_rtsp_url": "", "camera_name": ""})
        from database import get_session, Camera
        session = get_session()
        try:
            session.query(Camera).delete()
            session.commit()
        finally:
            session.close()
    return {"status": "ok", "message": message}


@router.put("")
def update_settings(data: SettingsUpdate):
    changes = {}
    if data.camera_name is not None:
        settings.camera_name = data.camera_name
        changes["camera_name"] = data.camera_name
    if data.camera_rtsp_url is not None:
        settings.camera_rtsp_url = data.camera_rtsp_url
        changes["camera_rtsp_url"] = data.camera_rtsp_url
    if data.recording_retention_days is not None:
        settings.recording_retention_days = data.recording_retention_days
        changes["recording_retention_days"] = data.recording_retention_days
    if data.recording_segment_minutes is not None:
        settings.recording_segment_minutes = data.recording_segment_minutes
        changes["recording_segment_minutes"] = data.recording_segment_minutes
    if data.recording_interval_minutes is not None:
        settings.recording_interval_minutes = data.recording_interval_minutes
        changes["recording_interval_minutes"] = data.recording_interval_minutes
    if data.recording_start_time is not None:
        settings.recording_start_time = data.recording_start_time
        changes["recording_start_time"] = data.recording_start_time
    if data.recording_end_time is not None:
        settings.recording_end_time = data.recording_end_time
        changes["recording_end_time"] = data.recording_end_time
    if data.highlight_duration_minutes is not None:
        settings.highlight_duration_minutes = data.highlight_duration_minutes
        changes["highlight_duration_minutes"] = data.highlight_duration_minutes
    if data.highlight_enabled is not None:
        settings.highlight_enabled = data.highlight_enabled
        changes["highlight_enabled"] = data.highlight_enabled
    if data.highlight_schedule_time is not None:
        settings.highlight_schedule_time = data.highlight_schedule_time
        changes["highlight_schedule_time"] = data.highlight_schedule_time
    if data.detection_sensitivity is not None:
        settings.detection_sensitivity = data.detection_sensitivity
        changes["detection_sensitivity"] = data.detection_sensitivity
    _persist_settings(changes)
    return {"status": "ok"}


@router.post("/restart-recording")
def restart_recording():
    if _restart_callback:
        return _restart_callback()
    logger.warning("录制重启回调未注册")
    return {"status": "error", "message": "录制重启回调未注册"}


@router.post("/delete-camera")
def delete_camera():
    """删除摄像头：停止录制、清空配置、删除数据库记录"""
    if _delete_camera_callback:
        _delete_camera_callback()
    # 清空摄像头配置并持久化
    settings.camera_name = ""
    settings.camera_rtsp_url = ""
    _persist_settings({"camera_name": "", "camera_rtsp_url": ""})
    # 删除数据库中的摄像头记录
    try:
        from database import get_session, Camera
        session = get_session()
        try:
            session.query(Camera).delete()
            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"删除摄像头记录失败: {e}")
    return {"status": "ok", "message": "摄像头已删除"}
