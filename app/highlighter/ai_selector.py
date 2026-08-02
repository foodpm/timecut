"""大模型精华识别器 - 运动片段抽帧后交由多模态大模型识别事件，再按规则表打分"""

import base64
import json
import logging
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from config import settings
from .detector import MotionSegment

logger = logging.getLogger("timecut.ai_selector")


def extract_frame(video_path: Path, ts: float) -> bytes | None:
    """提取视频某一时刻的一帧 JPEG 字节（640px 宽），失败返回 None"""
    with tempfile.TemporaryDirectory(prefix="timecut_ai_") as td:
        out = Path(td) / "frame.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path),
            "-frames:v", "1", "-vf", "scale=640:-1", "-q:v", "5", str(out),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception as e:
            logger.warning(f"抽帧失败: {e}")
            return None
        if out.exists() and out.stat().st_size > 0:
            return out.read_bytes()
    return None


class AISelector:
    """调用多模态大模型（OpenAI 兼容 API）判断运动片段的保留价值"""

    def __init__(self):
        self.base_url = settings.ai_base_url.rstrip("/")
        self.model = settings.ai_model
        self.api_key = settings.ai_api_key
        self.max_segments = max(1, settings.ai_max_segments)

    def score_segments(
        self, segments: list[tuple[MotionSegment, Path]], progress_cb=None
    ) -> tuple[list[tuple[MotionSegment, Path]], bool]:
        """对运动片段用大模型打分，score 更新为 AI 分数

        只分析运动分数最高的 max_segments 个候选片段，控制 API 成本；
        AI 识别失败的片段保留原运动分数。

        返回 (segments, ai_success)：ai_success 表示是否至少有一个片段成功完成 AI 打分。
        全部失败（如 API 不可用 / Key 无效）时调用方可自动降级为系统自动模式。
        progress_cb(seg, score, reason) 每个成功打分的片段回调一次，用于展示打分过程。
        """
        if not self.api_key:
            logger.error("未配置大模型 API Key，跳过 AI 识别，使用运动检测分数")
            return segments, False
        sorted_segs = sorted(segments, key=lambda s: s[0].score, reverse=True)
        candidates = sorted_segs[: self.max_segments]
        logger.info(f"AI 识别 {len(candidates)} 个候选片段 (model={self.model})")
        scored = []
        success = 0
        for seg, src in candidates:
            frame = self._extract_frame(seg, src)
            if not frame:
                scored.append((seg, src))
                continue
            ai_score, reason = self._score_frame(frame, seg)
            if ai_score is not None:
                seg.score = ai_score
                success += 1
                if progress_cb:
                    progress_cb(seg, ai_score, reason or "")
            scored.append((seg, src))
        return scored, success > 0

    def _extract_frame(self, seg: MotionSegment, src: Path) -> bytes | None:
        """提取片段中间一帧的 JPEG 字节"""
        ts = seg.start + max(1.0, seg.duration / 2)
        return extract_frame(src, ts)

    def _score_frame(self, frame: bytes, seg: MotionSegment) -> tuple[int | None, str]:
        """调用大模型识别事件类型，套用规则表计算最终分数，返回 (0-100 分数, 原因文本)"""
        b64 = base64.b64encode(frame).decode()
        prompt = (
            "你是家庭监控录像回顾助手。这是家庭监控录像中一个运动片段的某一帧画面，"
            "片段将用于生成\"一天回顾\"精华视频。"
            "请判断这一瞬间是否值得回顾，例如：家人出现、多人聚会互动、宠物出没、"
            "收到快递、外出回家等温馨或特别的时刻。"
            "请只返回 JSON：{\"category\": \"family|animal|package|vehicle|stranger|empty\", "
            "\"people_count\": 画面中的人数, \"score\": 0-100, \"reason\": \"简短原因\"}。"
            "category 含义：family=家人出现；animal=宠物或动物；package=快递包裹等特别时刻；"
            "vehicle=车辆经过；stranger=陌生人或路人；empty=空场景或光线变化。"
            "people_count 为画面中的人数，0 表示没有人。"
            "score 表示回顾价值：0=无意义画面，100=非常值得回顾。"
        )
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }],
        }
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
            content = data["choices"][0]["message"]["content"]
            score, reason = self._apply_rules(content)
            if score is not None:
                logger.info(
                    f"片段 {seg.start:.0f}s~{seg.end:.0f}s 评分={score} reason={reason}"
                )
            return score, reason
        except Exception as e:
            logger.error(f"AI 识别片段失败: {e}")
            return None, ""

    # 事件类型 → 基础分（"一天回顾"语义：家人最值得回顾，陌生人/空场景基本淘汰）
    CATEGORY_BASE = {
        "family": 70,
        "animal": 60,
        "package": 55,
        "vehicle": 35,
        "stranger": 25,
        "empty": 10,
    }

    # 兼容模型返回中文类别
    CATEGORY_ALIASES = {
        "family": "family", "家人": "family", "家庭": "family", "家庭成员": "family",
        "animal": "animal", "动物": "animal", "宠物": "animal",
        "package": "package", "包裹": "package", "快递": "package",
        "vehicle": "vehicle", "车辆": "vehicle", "车": "vehicle",
        "stranger": "stranger", "陌生人": "stranger", "路人": "stranger", "外人": "stranger",
        "empty": "empty", "空场景": "empty", "空": "empty", "无": "empty",
    }

    def _apply_rules(self, content) -> tuple[int | None, str]:
        """解析模型返回，套用规则表计算最终分数"""
        data = self._parse_json_content(content)
        if data is None:
            return self._parse_score(content), self._parse_reason(content)
        raw = self._parse_score(data.get("score"))
        category = str(data.get("category", "")).strip().lower()
        people_count = self._parse_people_count(data.get("people_count"))
        reason = str(data.get("reason") or "").strip() or self._parse_reason(content)
        rule = self._rule_score(category, people_count) if category else None
        if rule is None:
            return raw, reason
        # 模型原始分明显更高时，说明识别到规则未覆盖的内容，取较高值兜底
        if raw is not None and raw - rule >= 20:
            return raw, reason
        return rule, reason

    def _rule_score(self, category: str, people_count: int) -> int | None:
        """按事件类型基础分 + 人数加成计算最终分数，无法识别类型返回 None"""
        base = self.CATEGORY_BASE.get(self.CATEGORY_ALIASES.get(category, category))
        if base is None:
            return None
        # 画面里有人就加"热闹分"，最多加 30
        bonus = min(max(people_count, 0), 6) * 5
        return min(100, base + bonus)

    @staticmethod
    def _parse_people_count(value) -> int:
        if isinstance(value, bool):
            return 0
        if isinstance(value, (int, float)):
            return max(0, int(value))
        if isinstance(value, str):
            m = re.search(r"\d+", value)
            if m:
                return int(m.group())
        return 0

    @staticmethod
    def _parse_json_content(content) -> dict | None:
        """从模型返回文本提取 JSON 对象，失败返回 None"""
        if not isinstance(content, str):
            return None
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(content[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    @staticmethod
    def _parse_reason(content) -> str:
        """从模型返回内容解析 reason（JSON 里的 reason 字段，否则截取原文）"""
        if not isinstance(content, str):
            return ""
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(content[start : end + 1])
                r = data.get("reason")
                if r:
                    return str(r).strip()
            except Exception:
                pass
        return content.strip()[:60]

    @staticmethod
    def _parse_score(content) -> int | None:
        """从模型返回内容解析 score（兼容 JSON / 纯数字 / 文本中数字）"""
        if isinstance(content, (int, float)):
            return max(0, min(100, int(content)))
        if not isinstance(content, str):
            return None
        s = content.strip()
        try:
            if s.isdigit():
                return max(0, min(100, int(s)))
            start, end = s.find("{"), s.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(s[start : end + 1])
                return max(0, min(100, int(data.get("score", 50))))
        except Exception:
            pass
        m = re.search(r"\d{1,3}", s)
        if m:
            return max(0, min(100, int(m.group())))
        return None
