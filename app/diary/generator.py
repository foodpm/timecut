"""大模型日记生成器 - 分析某天录像的运动片段，用大模型总结当天发生的事"""

import base64
import json
import logging
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from config import settings
from database import get_session, Diary
from highlighter.detector import MotionDetector
from highlighter.ai_selector import extract_frame
from highlighter.job import diary_job

logger = logging.getLogger("timecut.diary")


def get_status() -> dict:
    return diary_job.to_dict()


def run_diary_for_date(date: str) -> str | None:
    """在后台线程执行的日记生成入口（更新任务状态/日志，分析、保存）"""
    if diary_job.running:
        return None
    diary_job.start(date)
    try:
        content = DiaryGenerator().generate_for_date(date)
        if content:
            diary_job.finish(True, "日记生成成功")
            return content
        diary_job.finish(False, "没有可生成的内容（未配置 AI 或当天无事件）")
        return None
    except Exception as e:
        logger.exception("日记生成异常")
        diary_job.finish(False, f"生成失败: {e}")
        return None


class DiaryGenerator:
    """逐运动片段描述 + 汇总成日记"""

    def __init__(self):
        self.base_url = settings.ai_base_url.rstrip("/")
        self.model = settings.ai_model
        self.api_key = settings.ai_api_key
        self.max_events = max(1, settings.diary_max_segments)

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
        diary_job.set_stage("分析录像", total=len(video_files))
        diary_job.log_line(f"开始分析 {date} 的录像，共 {len(video_files)} 个片段")
        candidates = []  # (event_dt, score, seg, video_path)
        for i, vf in enumerate(video_files, 1):
            start_dt = self._parse_file_start(vf)
            diary_job.set_stage("分析录像", done=i - 1, total=len(video_files), current=vf.name)
            diary_job.log_line(f"[{i}/{len(video_files)}] 运动检测: {vf.name}")
            for seg in detector.analyze(vf):
                candidates.append((start_dt, seg.score, seg, vf))
        if not candidates:
            diary_job.finish(False, "未检测到运动，跳过日记")
            logger.info(f"{date} 未检测到运动，跳过日记")
            return None
        diary_job.log_line(f"共检测到 {len(candidates)} 个运动片段，选取分数最高的 {min(len(candidates), self.max_events)} 个分析")

        # 按运动分数取前 N 个片段（控制成本，与精华识别一致）
        candidates.sort(key=lambda c: c[1], reverse=True)
        candidates = candidates[: self.max_events]
        candidates.sort(key=lambda c: c[0] + timedelta(seconds=c[2].start))

        events = []  # (datetime, description)
        diary_job.set_stage("大模型分析", total=len(candidates))
        for i, (start_dt, score, seg, vf) in enumerate(candidates, 1):
            frame_ts = seg.start + max(1.0, seg.duration / 2)
            event_dt = start_dt + timedelta(seconds=frame_ts)
            diary_job.set_stage("大模型分析", done=i - 1, total=len(candidates),
                                current=f"{event_dt.strftime('%H:%M')} {vf.name}")
            diary_job.log_line(f"[{i}/{len(candidates)}] {event_dt.strftime('%H:%M')} 分析画面: {vf.name}")
            frame = extract_frame(vf, frame_ts)
            if not frame:
                continue
            desc = self._describe_frame(frame, event_dt)
            if desc:
                events.append((event_dt, desc))
                diary_job.log_line(f"    ↳ {desc}")
        if not events:
            diary_job.finish(False, "所有片段均无值得记录的内容")
            logger.info(f"{date} 所有片段均无值得记录的内容")
            return None

        diary_job.set_stage("汇总日记")
        diary_job.log_line(f"汇总 {len(events)} 个事件，生成日记...")
        content = self._compose_diary(date, events)
        if not content:
            return None
        self._save(date, content)
        return content

    # ── 大模型调用 ──
    def _describe_frame(self, frame: bytes, event_dt: datetime) -> str:
        prompt = (
            "你是家庭监控录像日志助手。这是某天某个时刻的监控画面。"
            f"当前时刻：{event_dt.strftime('%Y-%m-%d %H:%M')}。"
            "请仔细观察画面：如果画面里有人，用 1-2 句话描述画面里的人正在做什么——"
            "有几个人、正在做什么动作、进出方向、手里有没有拿东西、有没有停顿或停留等行为细节；"
            "如果画面里没有人，也没有值得记录的事（空镜头、光线变化、树叶晃动等），"
            "只回答「无」。不要输出其他内容。"
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
            "max_tokens": 150,
        }
        text = self._chat(payload)
        if not text:
            return ""
        text = text.strip().strip("。").strip()
        if text in ("无", "没有", "无内容", "无事件", "无明显事件"):
            return ""
        return text[:150]

    def _compose_diary(self, date: str, events: list) -> str:
        """组装行为描述式日志：按时间线列出画面里的人在做什么（无需二次模型调用）"""
        lines = [f"# {date} 见闻记录", ""]
        for dt, desc in events:
            lines.append(f"## {dt.strftime('%H:%M')}")
            lines.append(desc)
            lines.append("")
        return "\n".join(lines).strip()

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
        """日记写入文件（每天一个 Markdown，可直接阅读），并在数据库保留记录"""
        diaries = settings.diaries_dir
        diaries.mkdir(parents=True, exist_ok=True)
        fpath = diaries / f"{date}.md"
        try:
            fpath.write_text(content, encoding="utf-8")
            logger.info(f"日记文件已保存: {fpath}")
        except Exception as e:
            logger.error(f"写入日记文件失败: {e}")
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
