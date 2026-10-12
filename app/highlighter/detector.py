"""运动检测器 - 使用 FFmpeg 分析录像中的运动密集时段"""

import logging
import subprocess
from pathlib import Path

from config import settings

logger = logging.getLogger("timecut.detector")


def sort_by_score_round_robin(segments: list, hour_of) -> list:
    """按分数降序排序；分数相同（±1 秒内视为同级）的片段按时段轮转交错。

    避免稳定排序下同分片段总是早晨排前面，把截断名额（如 AI 候选池 Top-N）
    全部占满。hour_of(item) 返回片段所属时段编号（0-23），轮转按时段升序进行：
    例如 0 点段 5 个、19 点段 3 个同分片段 → 0点, 19点, 0点, 19点, ... 交错排列。
    """
    keyed = sorted(segments, key=lambda s: s[0].score, reverse=True)
    result = []
    i = 0
    while i < len(keyed):
        j = i + 1
        while j < len(keyed) and keyed[i][0].score - keyed[j][0].score < 1.0:
            j += 1
        group = keyed[i:j]
        if len(group) == 1:
            result.extend(group)
        else:
            by_hour: dict[int, list] = {}
            for item in group:
                by_hour.setdefault(hour_of(item), []).append(item)
            hours = sorted(by_hour)
            idx = 0
            while True:
                emitted = False
                for h in hours:
                    if idx < len(by_hour[h]):
                        result.append(by_hour[h][idx])
                        emitted = True
                if not emitted:
                    break
                idx += 1
        i = j
    return result


def file_hour_of(src) -> int:
    """从录像文件名解析所属小时（20261011_190019.mp4 → 19），解析失败返回 0"""
    stem = src.stem
    if len(stem) == 15 and stem[8] == "_":
        try:
            return int(stem[9:11])
        except ValueError:
            pass
    return 0


class MotionSegment:
    """一个运动密集片段"""

    def __init__(self, start: float, end: float, score: float,
                 person_ts: list | None = None):
        self.start = start
        self.end = end
        self.score = score
        # YOLO 检测到人的时间戳（绝对秒，可选；用于长片段取"人物最密集"窗口）
        self.person_ts = person_ts

    @property
    def duration(self) -> float:
        return self.end - self.start


class MotionDetector:
    """基于 FFmpeg scene/motion 检测筛选精华片段"""

    def __init__(self, sensitivity: int | None = None):
        self.sensitivity = sensitivity or settings.detection_sensitivity
        # 场景变化阈值：灵敏度越高阈值越低。
        # 实测家庭监控画面 scene 分数普遍集中在 0.02-0.05 区间，
        # 旧映射在灵敏度 50 时阈值高达 0.15，导致几乎检不出运动。
        self._scene_threshold = max(0.01, 0.05 - (self.sensitivity / 100) * 0.04)

    def analyze(self, video_path: Path) -> list[MotionSegment]:
        if not video_path.exists():
            logger.warning(f"文件不存在: {video_path}")
            return []
        logger.info(f"分析运动: {video_path}")
        scene_changes = self._detect_scenes(video_path)
        if not scene_changes:
            return []
        segments = self._cluster_timestamps(scene_changes)
        logger.info(f"检测到 {len(segments)} 个运动片段")
        return segments

    def _detect_scenes(self, video_path: Path) -> list[float]:
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-filter:v", f"select='gt(scene,{self._scene_threshold})',showinfo",
            "-f", "null", "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            stderr = result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []
        timestamps = []
        for line in stderr.splitlines():
            if "pts_time:" in line:
                try:
                    parts = line.split()
                    for p in parts:
                        if p.startswith("pts_time:"):
                            ts = float(p.split(":")[1])
                            timestamps.append(ts)
                            break
                except (ValueError, IndexError):
                    continue
        duration = self._get_duration(video_path)
        if duration and timestamps:
            deduped = [timestamps[0]]
            for ts in timestamps[1:]:
                if ts - deduped[-1] > 2.0:
                    deduped.append(ts)
            return deduped
        return timestamps

    def _cluster_timestamps(self, timestamps: list[float], gap_sec: float = 30) -> list[MotionSegment]:
        if not timestamps:
            return []
        segments = []
        cluster_start = timestamps[0]
        cluster_end = timestamps[0]
        for ts in timestamps[1:]:
            if ts - cluster_end <= gap_sec:
                cluster_end = ts
            else:
                if cluster_end - cluster_start >= 5:
                    # 不封顶：用真实活动跨度（秒）作分数，避免大量同分满分导致选段偏向早晨
                    score = cluster_end - cluster_start
                    segments.append(MotionSegment(
                        start=max(0, cluster_start - 5),
                        end=cluster_end + 5,
                        score=score,
                    ))
                cluster_start = ts
                cluster_end = ts
        if cluster_end - cluster_start >= 5:
            score = cluster_end - cluster_start
            segments.append(MotionSegment(
                start=max(0, cluster_start - 5),
                end=cluster_end + 5,
                score=score,
            ))
        return segments

    @staticmethod
    def _get_duration(video_path: Path) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.stdout:
                return float(result.stdout.strip())
        except Exception:
            pass
        return 0.0
