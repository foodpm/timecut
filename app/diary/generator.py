"""大模型日记生成器 - 分析某天录像的运动片段，用大模型总结当天发生的事"""

import base64
import json
import logging
import threading
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from config import settings
from database import get_session, Diary
from highlighter.detector import MotionDetector
from highlighter.ai_selector import extract_frame

logger = logging.getLogger("timecut.diary")

# ── 生成任务状态（供前端轮询）──
_lock = threading.Lock()
_status = {"running": False, "date": "", "message": "", "error": "", "done": 0, "total": 0, "current": ""}


def get_status() -> dict:
    with _lock:
        return dict(_status)


def _set_status(**kw):
    with _lock:
        _status.update(kw)


def run_diary_for_date(date: str) -> str | None:
    """在后台线程执行的日记生成入口（更新状态、分析、保存）"""
    with _lock:
        if _status["running"]:
            return None
        _status.update({"running": True, "date": date, "message": "", "error": "",
                        "done": 0, "total": 0, "current": ""})
    try:
        content = DiaryGenerator().generate_for_date(date)
        if content:
            _set_status(message="生成成功")
            return content
        _set_status(message="没有可生成的内容（未配置 AI 或当天无事件）")
        return None
    except Exception as e:
        logger.exception("日记生成异常")
        _set_status(message=f"生成失败: {e}", error=str(e))
        return None
    finally:
        _set_status(running=False)


class DiaryGenerator:
    """逐运动片段描述 + 汇总成日记"""

    def __init__(self):
        self.base_url = settings.ai_base_url.rstrip("/")
        self.model = settings.ai_model
        self.api_key = settings.ai_api_key
        self.max_events = max(1, settings.ai_max_segments)

    def generate_for_date(self, date: str) -> str | None:
        if not self.api_key:
            logger.error("未配置大模型 API Key，跳过日记生成")
            return None
        day_dir = settings.recordings_dir / date
        video_files = sorted(day_dir.glob("*.mp4")) if day_dir.exists() else []
        if not video_files:
            logger.info(f"{date} 无录像，跳过日记")
            return None

        detector = MotionDetector()
        _set_status(current="正在分析录像中的运动片段...")
        candidates = []  # (event_dt, score, seg, video_path)
        for vf in video_files:
            start_dt = self._parse_file_start(vf)
            for seg in detector.analyze(vf):
                candidates.append((start_dt, seg.score, seg, vf))
        if not candidates:
            logger.info(f"{date} 未检测到运动，跳过日记")
            return None

        # 按运动分数取前 N 个片段（控制成本，与精华识别一致）
        candidates.sort(key=lambda c: c[1], reverse=True)
        candidates = candidates[: self.max_events]
        candidates.sort(key=lambda c: c[0] + timedelta(seconds=c[2].start))
        _set_status(total=len(candidates), current="")

        events = []  # (datetime, description)
        for i, (start_dt, score, seg, vf) in enumerate(candidates, 1):
            frame_ts = seg.start + max(1.0, seg.duration / 2)
            event_dt = start_dt + timedelta(seconds=frame_ts)
            _set_status(done=i - 1, current=f"{event_dt.strftime('%H:%M')} {vf.name}")
            frame = extract_frame(vf, frame_ts)
            if not frame:
                continue
            desc = self._describe_frame(frame, event_dt)
            if desc:
                events.append((event_dt, desc))
        if not events:
            logger.info(f"{date} 所有片段均无值得记录的内容")
            return None

        content = self._compose_diary(date, events)
        if not content:
            return None
        self._save(date, content)
        return content

    # ── 大模型调用 ──
    def _describe_frame(self, frame: bytes, event_dt: datetime) -> str:
        prompt = (
            "你是家庭监控日记助手。这是某天某个时刻的监控画面。"
            f"当前时刻：{event_dt.strftime('%Y-%m-%d %H:%M')}。"
            "请用一句话描述画面中发生的事（例如：有人经过门口、车辆停靠、快递放门口、"
            "动物路过、画面异常等）。如果画面没有值得记录的内容（如空镜头、光线变化、"
            "树叶晃动），只回答「无」。不要输出其他内容。"
        )
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": "data:image/jpeg;base64," + base64.b64encode(frame).decode()}},
                ],
            }],
            "max_tokens": 80,
        }
        text = self._chat(payload)
        if not text:
            return ""
        text = text.strip().strip("。").strip()
        if text in ("无", "没有", "无内容", "无事件", "无明显事件"):
            return ""
        return text[:80]

    def _compose_diary(self, date: str, events: list) -> str:
        lines = "\n".join(f"{dt.strftime('%H:%M')} - {desc}" for dt, desc in events)
        prompt = (
            f"以下是某天家庭监控捕捉到的事件列表（时间 - 事件）：\n{lines}\n\n"
            "请以日记的口吻写一篇当天的简短日记（200 字以内），按时间顺序自然叙述"
            "当天家里门口发生了什么。语气自然真实，像一个普通人的日记。只返回日记正文，"
            "不要标题、不要解释。"
        )
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }
        text = self._chat(payload)
        return text.strip() if text else None

    def _chat(self, payload: dict) -> str | None:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"日记大模型调用失败: {e}")
            return None

    # ── 工具 ──
    @staticmethod
    def _parse_file_start(vf: Path) -> datetime:
        """从文件名解析录像开始时间：20260801_184213.mp4"""
        try:
            return datetime.strptime(vf.stem, "%Y%m%d_%H%M%S")
        except ValueError:
            return datetime(1970, 1, 1)

    @staticmethod
    def _save(date: str, content: str):
        session = get_session()
        try:
            rec = session.query(Diary).filter(Diary.date == date).first()
            if rec:
                rec.content = content
            else:
                session.add(Diary(date=date, content=content))
            session.commit()
            logger.info(f"日记已保存: {date}")
        except Exception as e:
            session.rollback()
            logger.error(f"保存日记失败: {e}")
        finally:
            session.close()
