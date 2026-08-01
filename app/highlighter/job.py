"""生成任务状态（按类型各一个单例），供前端轮询展示进度与日志"""

import threading
from datetime import datetime

LOG_MAX = 300


class Job:
    """记录一次生成任务（精华视频 / 日记）的进度与日志，跨线程读写需加锁"""

    def __init__(self, kind: str, title: str):
        self.kind = kind
        self.title = title
        self._lock = threading.Lock()
        self._reset()

    def _reset(self):
        self.running = False
        self.date = ""
        self.stage = ""      # 阶段文案：分析录像 / 大模型打分 / 拼接片段 等
        self.done = 0
        self.total = 0
        self.current = ""    # 当前处理对象（文件名等）
        self.percent = 0
        self.message = ""
        self.error = ""
        self.log = []        # [{t: "HH:MM:SS", text: str}]

    def start(self, date: str, total: int = 0):
        with self._lock:
            self._reset()
            self.running = True
            self.date = date
            self.total = total

    def set_stage(self, stage: str, done: int | None = None,
                  total: int | None = None, current: str = ""):
        with self._lock:
            self.stage = stage
            if done is not None:
                self.done = done
            if total is not None:
                self.total = total
            self.current = current or ""
            self._calc_percent()

    def tick(self, text: str):
        """推进一步并写日志（当前对象 + 数量）"""
        with self._lock:
            self.done += 1
            self._calc_percent()
            self._append(text)

    def ai_score(self, seg, score: int, reason: str):
        """大模型打分回调：记录每片段评分到日志"""
        text = f"片段 {seg.start:.0f}s~{seg.end:.0f}s 评分 {score}"
        if reason:
            text += f" · {reason[:60]}"
        with self._lock:
            self.done += 1
            self._calc_percent()
            self._append(text)

    def log_line(self, text: str):
        with self._lock:
            self._append(text)

    def finish(self, ok: bool, message: str):
        with self._lock:
            self.running = False
            self.percent = 100 if ok else self.percent
            self.message = message
            if not ok:
                self.error = message
            self._append(("✓ " if ok else "✗ ") + message)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "kind": self.kind,
                "title": self.title,
                "running": self.running,
                "date": self.date,
                "stage": self.stage,
                "done": self.done,
                "total": self.total,
                "current": self.current,
                "percent": self.percent,
                "message": self.message,
                "error": self.error,
                "log": list(self.log),
            }

    # ── 内部 ──
    def _append(self, text: str):
        self.log.append({"t": datetime.now().strftime("%H:%M:%S"), "text": text})
        if len(self.log) > LOG_MAX:
            self.log = self.log[-LOG_MAX:]

    def _calc_percent(self):
        # 阶段权重：分析录像 0-70，大模型阶段 70-90，汇总/拼接 90，完成 100
        if self.stage == "分析录像":
            self.percent = int(self.done / self.total * 70) if self.total else 0
        elif self.stage in ("大模型打分", "大模型分析"):
            self.percent = 70 + int(self.done / self.total * 20) if self.total else 70
        elif self.stage in ("拼接片段", "汇总日记"):
            self.percent = 90
        else:
            self.percent = min(99, self.percent)


job = Job("highlight", "精华视频")
diary_job = Job("diary", "日记")
