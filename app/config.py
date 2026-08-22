"""TimeCut 配置管理"""

import json
import logging
from pathlib import Path
from pydantic_settings import BaseSettings

logger = logging.getLogger("timecut.config")


class Settings(BaseSettings):
    camera_rtsp_url: str = ""
    camera_name: str = "摄像头"
    recording_retention_days: int = 7
    recording_segment_minutes: int = 60
    recording_interval_minutes: int = 0
    recording_start_time: str = "00:00"
    recording_end_time: str = "23:59"
    highlight_duration_minutes: int = 5
    highlight_max_segment_seconds: int = 20
    highlight_max_segments_per_hour: int = 2
    highlight_schedule_time: str = "03:00"
    highlight_enabled: bool = True
    detection_sensitivity: int = 30
    web_port: int = 8090
    data_dir: str = "/data"
    tz: str = "Asia/Shanghai"
    go2rtc_url: str = "http://localhost:1984"
    go2rtc_config_path: str = "go2rtc.yaml"
    # ── go2rtc 自愈：RTSP 持续 404 时自动重启该容器（需挂载 docker.sock，留空禁用）──
    go2rtc_container_name: str = "timecut-go2rtc"
    docker_socket_path: str = "/var/run/docker.sock"
    recording_enabled: bool = True
    # ── 大模型识别精华片段 ──
    ai_enabled: bool = False
    ai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ai_model: str = "qwen-vl-plus"
    ai_api_key: str = ""
    ai_max_segments: int = 20
    # ── 大模型日记 ──
    diary_enabled: bool = False
    diary_max_segments: int = 50
    # ── YOLO 人物过滤（精华视频只保留有人片段，无人在内时自动回退运动模式）──
    yolo_enabled: bool = True
    yolo_model_path: str = "/app/models/yolo11n.onnx"
    yolo_confidence: float = 0.4

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def recordings_dir(self) -> Path:
        return Path(self.data_dir) / "recordings"

    @property
    def highlights_dir(self) -> Path:
        return Path(self.data_dir) / "highlights"

    @property
    def db_path(self) -> Path:
        return Path(self.data_dir) / "db" / "timecut.db"

    @property
    def log_dir(self) -> Path:
        return Path(self.data_dir) / "logs"

    @property
    def diaries_dir(self) -> Path:
        """日记文件目录（每天一个 Markdown，可直接阅读）"""
        return Path(self.data_dir) / "diaries"

    @property
    def settings_file(self) -> Path:
        """面板配置持久化文件（位于数据卷内，容器重启后保留）"""
        return Path(self.data_dir) / "settings.json"

    def load_persisted(self) -> None:
        """启动时加载面板持久化的配置，覆盖 .env / 环境变量"""
        if not self.settings_file.exists():
            return
        try:
            data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            for key, value in data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            logger.info(f"已加载面板持久化配置: {sorted(data.keys())}")
        except Exception as e:
            logger.warning(f"加载持久化配置失败: {e}")

    def update_persisted(self, changes: dict) -> None:
        """更新配置并写入持久化文件"""
        data = {}
        if self.settings_file.exists():
            try:
                data = json.loads(self.settings_file.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        for key, value in changes.items():
            if hasattr(self, key):
                setattr(self, key, value)
                data[key] = value
        try:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"持久化配置写入失败: {e}")


settings = Settings()
settings.load_persisted()
