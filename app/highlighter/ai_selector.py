"""大模型精华识别器 - 运动片段抽帧后交由多模态大模型打分"""

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
        """调用大模型打分，返回 (0-100 分数, 原因文本)"""
        b64 = base64.b64encode(frame).decode()
        prompt = (
            "你是监控视频精华筛选助手。这是家庭监控录像中一个运动片段的某一帧画面。"
            "请判断该时刻画面是否包含值得保留的事件，例如：人员经过、车辆、包裹、动物、"
            "陌生人、异常情况等。请只返回 JSON：{\"score\": 0-100, \"reason\": \"简短原因\"}。"
            "score 表示该片段的保留价值：0=无意义画面（如光线变化、树叶晃动），"
            "100=非常重要事件。"
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
            score = self._parse_score(content)
            reason = self._parse_reason(content)
            if score is not None:
                logger.info(
                    f"片段 {seg.start:.0f}s~{seg.end:.0f}s AI 评分={score} "
                    f"reason={reason}"
                )
            return score, reason
        except Exception as e:
            logger.error(f"AI 识别片段失败: {e}")
            return None, ""

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
