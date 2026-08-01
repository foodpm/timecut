"""TimeCut 配置管理"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    camera_rtsp_url: str = ""
    camera_name: str = "摄像头"
    recording_retention_days: int = 7
    recording_segment_minutes: int = 60
    highlight_duration_minutes: int = 5
    highlight_schedule_time: str = "03:00"
    highlight_enabled: bool = True
    detection_sensitivity: int = 30
    web_port: int = 8090
    data_dir: str = "/data"
    tz: str = "Asia/Shanghai"
    go2rtc_url: str = "http://localhost:1984"

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


settings = Settings()
