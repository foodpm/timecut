"""系统设置 API"""

import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from config import settings

logger = logging.getLogger("timecut.api")

router = APIRouter(prefix="/api/settings", tags=["settings"])


def persist_recording_state(enabled: bool):
    """持久化录制开关状态"""
    settings.update_persisted({"recording_enabled": enabled})


def _persist_settings(changes: dict):
    """将配置持久化到数据卷中的 settings.json（容器重启后仍生效）"""
    settings.update_persisted(changes)

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
    highlight_max_segment_seconds: int | None = None
    highlight_max_segments_per_hour: int | None = None
    highlight_enabled: bool | None = None
    highlight_schedule_time: str | None = None
    detection_sensitivity: int | None = None
    # ── 大模型识别 ──
    ai_enabled: bool | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None
    ai_max_segments: int | None = None
    # ── 日记 ──
    diary_enabled: bool | None = None
    diary_max_segments: int | None = None
    # ── YOLO 人物过滤 ──
    yolo_enabled: bool | None = None
    yolo_confidence: float | None = None


class AITestRequest(BaseModel):
    """AI 连接测试请求（未保存的表单值，缺省回退到已保存配置）"""
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_api_key: str | None = None


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
        "highlight_max_segment_seconds": settings.highlight_max_segment_seconds,
        "highlight_max_segments_per_hour": settings.highlight_max_segments_per_hour,
        "highlight_enabled": settings.highlight_enabled,
        "highlight_schedule_time": settings.highlight_schedule_time,
        "detection_sensitivity": settings.detection_sensitivity,
        "ai_enabled": settings.ai_enabled,
        "ai_base_url": settings.ai_base_url,
        "ai_model": settings.ai_model,
        "ai_api_key": settings.ai_api_key,
        "ai_max_segments": settings.ai_max_segments,
        "diary_enabled": settings.diary_enabled,
        "diary_max_segments": settings.diary_max_segments,
        "yolo_enabled": settings.yolo_enabled,
        "yolo_confidence": settings.yolo_confidence,
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


# ── go2rtc API 同源代理 ──
# 前端不再直连 :1984（HTTPS 混合内容 / 端口不可达 / CORS 都会导致浏览器
# fetch 抛 "Failed to fetch"），统一走后端转发，Web UI 与后端同源
def _go2rtc_proxy(method: str, path: str, params: dict | None = None,
                  body: bytes | None = None, content_type: str | None = None,
                  timeout: float = 90) -> Response:
    """转发请求到 go2rtc API 并原样返回（含状态码，便于前端处理 401 验证码/二次验证）"""
    url = f"{settings.go2rtc_url}{path}"
    if params:
        url += "?" + urlencode(params)
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Response(content=resp.read(), status_code=resp.status,
                            media_type=resp.headers.get_content_type() or "application/octet-stream")
    except urllib.error.HTTPError as e:
        # go2rtc 401（需要验证码/二次验证）等错误需把状态码+JSON 原样回传
        return Response(content=e.read(), status_code=e.code,
                        media_type=e.headers.get_content_type() or "application/json")
    except Exception as e:
        logger.warning(f"go2rtc 代理失败 {method} {path}: {e}")
        return JSONResponse(status_code=502, content={"detail": f"无法连接 go2rtc: {e}"})


@router.get("/go2rtc/xiaomi")
def proxy_xiaomi_get(id: str | None = None, region: str | None = None):
    """代理 go2rtc 小米账号列表 / 设备列表"""
    params = {}
    if id:
        params["id"] = id
    if region:
        params["region"] = region
    return _go2rtc_proxy("GET", "/api/xiaomi", params=params, timeout=120)


@router.post("/go2rtc/xiaomi")
async def proxy_xiaomi_post(request: Request):
    """代理 go2rtc 小米账号登录（原样转发 form 请求体）"""
    body = await request.body()
    return _go2rtc_proxy("POST", "/api/xiaomi", body=body,
                         content_type=request.headers.get("content-type", "application/x-www-form-urlencoded"))


@router.put("/go2rtc/streams")
def proxy_streams_put(name: str, src: str):
    """代理 go2rtc 添加视频流"""
    return _go2rtc_proxy("PUT", "/api/streams", params={"name": name, "src": src}, timeout=30)


@router.get("/go2rtc/onvif")
def proxy_onvif_scan(src: str | None = None):
    """代理 go2rtc ONVIF 扫描"""
    params = {}
    if src:
        params["src"] = src
    return _go2rtc_proxy("GET", "/api/onvif", params=params, timeout=120)


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
        changes["highlight_duration_minutes"] = settings.highlight_duration_minutes
    if data.highlight_max_segment_seconds is not None:
        settings.highlight_max_segment_seconds = max(1, data.highlight_max_segment_seconds)
        changes["highlight_max_segment_seconds"] = settings.highlight_max_segment_seconds
    if data.highlight_max_segments_per_hour is not None:
        settings.highlight_max_segments_per_hour = max(1, data.highlight_max_segments_per_hour)
        changes["highlight_max_segments_per_hour"] = settings.highlight_max_segments_per_hour
    if data.highlight_enabled is not None:
        settings.highlight_enabled = data.highlight_enabled
        changes["highlight_enabled"] = data.highlight_enabled
    if data.highlight_schedule_time is not None:
        settings.highlight_schedule_time = data.highlight_schedule_time
        changes["highlight_schedule_time"] = data.highlight_schedule_time
    if data.detection_sensitivity is not None:
        settings.detection_sensitivity = data.detection_sensitivity
        changes["detection_sensitivity"] = data.detection_sensitivity
    if data.ai_enabled is not None:
        settings.ai_enabled = data.ai_enabled
        changes["ai_enabled"] = data.ai_enabled
    if data.ai_base_url is not None:
        settings.ai_base_url = data.ai_base_url.strip()
        changes["ai_base_url"] = settings.ai_base_url
    if data.ai_model is not None:
        settings.ai_model = data.ai_model.strip()
        changes["ai_model"] = settings.ai_model
    if data.ai_api_key is not None:
        settings.ai_api_key = data.ai_api_key.strip()
        changes["ai_api_key"] = settings.ai_api_key
    if data.ai_max_segments is not None:
        settings.ai_max_segments = max(1, data.ai_max_segments)
        changes["ai_max_segments"] = settings.ai_max_segments
    if data.diary_enabled is not None:
        settings.diary_enabled = data.diary_enabled
        changes["diary_enabled"] = data.diary_enabled
    if data.diary_max_segments is not None:
        settings.diary_max_segments = max(1, data.diary_max_segments)
        changes["diary_max_segments"] = settings.diary_max_segments
    if data.yolo_enabled is not None:
        settings.yolo_enabled = data.yolo_enabled
        changes["yolo_enabled"] = settings.yolo_enabled
    if data.yolo_confidence is not None:
        settings.yolo_confidence = max(0.05, min(0.95, data.yolo_confidence))
        changes["yolo_confidence"] = settings.yolo_confidence
    _persist_settings(changes)
    return {"status": "ok"}


@router.post("/ai/test")
def test_ai_connection(data: AITestRequest):
    """测试大模型连接：优先请求 /models 验证地址与 Key，不支持时回退最小 chat 请求"""
    import urllib.error

    base_url = (data.ai_base_url if data.ai_base_url is not None else settings.ai_base_url).strip().rstrip("/")
    api_key = (data.ai_api_key if data.ai_api_key is not None else settings.ai_api_key).strip()
    model = (data.ai_model if data.ai_model is not None else settings.ai_model).strip()

    if not base_url:
        return {"status": "error", "message": "请先填写 API 地址"}
    if not api_key:
        return {"status": "error", "message": "请先填写 API Key"}

    # 1. 轻量校验：GET /models 验证地址可达 + Key 有效
    models = []
    try:
        req = urllib.request.Request(
            base_url + "/models",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        models = [m.get("id") for m in (payload.get("data") or []) if m.get("id")]
        note = ""
        if model and models and model not in models:
            note = f"，但模型「{model}」不在返回列表（{len(models)} 个）中，请检查模型 ID"
        return {"status": "ok", "message": "连接成功，API Key 有效" + note, "models": models[:50]}
    except urllib.error.HTTPError as e:
        if e.code == 404:
            pass  # 服务端不支持 /models，走下面的最小 chat 请求验证
        else:
            detail = e.read().decode("utf-8", errors="replace")[:200]
            return {"status": "error", "message": f"HTTP {e.code}: {detail}"}
    except Exception as e:
        return {"status": "error", "message": f"无法连接 {base_url}: {e}"}

    # 2. 兜底：最小 chat/completions 请求验证模型可用
    try:
        body = json.dumps({
            "model": model or "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }).encode("utf-8")
        req = urllib.request.Request(
            base_url + "/chat/completions",
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        if payload.get("choices"):
            return {"status": "ok", "message": "连接成功，模型可正常调用"}
        return {"status": "error", "message": f"返回数据异常: {str(payload)[:200]}"}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        return {"status": "error", "message": f"HTTP {e.code}: {detail}"}
    except Exception as e:
        return {"status": "error", "message": f"调用模型失败: {e}"}


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
