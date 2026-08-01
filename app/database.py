"""TimeCut SQLite 数据库模型"""

from datetime import datetime
from pathlib import Path
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Session

from config import settings


class Base(DeclarativeBase):
    pass


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, default="摄像头")
    rtsp_url = Column(String(512), nullable=False, default="")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Recording(Base):
    __tablename__ = "recordings"
    id = Column(Integer, primary_key=True)
    camera_id = Column(Integer, nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    has_motion = Column(Boolean, default=False)
    motion_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)


class Highlight(Base):
    __tablename__ = "highlights"
    id = Column(Integer, primary_key=True)
    camera_id = Column(Integer, nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, default=0)
    duration = Column(Float, default=0.0)
    date = Column(String(16), nullable=False)
    clip_count = Column(Integer, default=0)
    strategy = Column(String(32), default="motion")
    params = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.now)


class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


def get_engine():
    db_path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session():
    engine = get_engine()
    return Session(engine)
