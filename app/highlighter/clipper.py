"""精华剪辑器 - 将多个运动片段拼接成一个精华视频"""

import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from config import settings
from .detector import MotionDetector, MotionSegment

logger = logging.getLogger("timecut.clipper")


class HighlightClipper:
    """将运动片段列表合并为一段精华视频"""

    def __init__(self):
        self.target_duration = settings.highlight_duration_minutes * 60
        # 单个运动片段在精华视频中最多占用的秒数：超长片段只取其中运动最密集的一段，
        # 让 5 分钟精华能覆盖更多不同的事件
        self.max_segment_seconds = max(1, settings.highlight_max_segment_seconds)
        # 同一小时内最多保留的片段数，避免精华连续堆叠同一时段的画面
        self.max_per_hour = max(1, settings.highlight_max_segments_per_hour)

    def create_highlight(
        self,
        video_files: list[Path],
        segments: list[tuple[MotionSegment, Path]],
        output_path: Path | None = None,
        date: str | None = None,
    ) -> Path | None:
        if not segments:
            logger.warning("没有运动片段可剪辑")
            return None
        selected = self._select_segments(segments, video_files)
        if not selected:
            logger.warning("筛选后无可用片段")
            return None
        if output_path is None:
            settings.highlights_dir.mkdir(parents=True, exist_ok=True)
            # 录像日期 + 生成时刻命名，保证每次生成都是新文件：
            # 同一天重新生成不会覆盖旧文件，历史精华视频完整保留
            tag = date.replace("-", "") if date else datetime.now().strftime("%Y%m%d")
            stamp = datetime.now().strftime("%H%M%S")
            output_path = settings.highlights_dir / f"精华_{tag}_{stamp}.mp4"
        return self._clip_and_concat(selected, output_path)

    def _select_segments(
        self, segments: list[tuple[MotionSegment, Path]], video_files: list[Path]
    ) -> list[tuple[MotionSegment, Path]]:
        if not segments:
            return []
        # 计算每个源文件在当天录像序列中的全局时间偏移（文件按时间顺序排列）
        offset_map: dict[Path, float] = {}
        total_offset = 0.0
        for vf in video_files:
            offset_map[vf] = total_offset
            total_offset += self._get_duration(vf)

        def global_start(item: tuple[MotionSegment, Path]) -> float:
            """片段在当天录像中的真实发生时间"""
            seg, src = item
            return offset_map.get(src, 0.0) + seg.start

        # 按运动分数从高到低挑选，每个片段最多截取 max_segment_seconds 秒，
        # 同一小时内最多 max_per_hour 段，凑满目标时长，让精华视频覆盖全天更多事件
        detector = MotionDetector()
        scene_cache: dict[Path, list[float]] = {}

        def scene_ts(src: Path) -> list[float]:
            """该源文件内的 scene 变化时间戳（长片段截取用，每个文件只检测一次）"""
            if src not in scene_cache:
                scene_cache[src] = detector._detect_scenes(src)
            return scene_cache[src]

        sorted_segs = sorted(segments, key=lambda s: s[0].score, reverse=True)
        selected = []
        sel_total = 0.0

        # 按小时分组（组内已是分数从高到低）
        hour_segs: dict[int, list[tuple[MotionSegment, Path]]] = {}
        for seg, src in sorted_segs:
            hour = int(global_start((seg, src)) // 3600)
            hour_segs.setdefault(hour, []).append((seg, src))

        def take(item):
            """取一段（≤ max_segment_seconds 秒），放不下时按剩余容量截断；已满则跳过"""
            nonlocal sel_total
            if sel_total >= self.target_duration:
                return
            seg, src = item
            piece = self._cap_segment(seg, scene_ts(src))
            remaining = self.target_duration - sel_total
            if piece.duration > remaining:
                if remaining < 10:
                    return
                piece = MotionSegment(piece.start, piece.start + remaining, piece.score)
            selected.append((piece, src))
            sel_total += piece.duration

        # ① 每时段保底：每个有人的小时先取分数最高的一段，保证全天都有内容
        for segs in hour_segs.values():
            take(segs[0])
        # ② 每时段加一：每小时内最多补到 max_per_hour 段（保持分散）
        for k in range(1, self.max_per_hour):
            for segs in hour_segs.values():
                if len(segs) > k:
                    take(segs[k])
        # ③ 分数补齐：仍凑不满目标时长时，按全局分数高低任意补选，直到装满
        used = {id(seg) for seg, _ in selected}
        for seg, src in sorted_segs:
            if id(seg) in used:
                continue
            take((seg, src))

        # 按当天真实发生时间排序，保证精华视频按时间顺序播放
        selected.sort(key=global_start)
        return selected

    def _cap_segment(self, seg: MotionSegment, scene_ts: list[float]) -> MotionSegment:
        """把片段截断到最多 max_segment_seconds 秒。

        窗口优先级：人物最密集 > 运动（scene 变化）最密集 > 片段中部兜底。
        """
        max_sec = self.max_segment_seconds
        if seg.duration <= max_sec:
            return seg
        person_ts = getattr(seg, "person_ts", None)
        if person_ts:
            in_seg = [t for t in person_ts if seg.start <= t <= seg.end]
            if in_seg:
                return self._densest_window(seg, in_seg, max_sec)
        if scene_ts:
            in_seg = [t for t in scene_ts if seg.start <= t <= seg.end]
            if in_seg:
                return self._densest_window(seg, in_seg, max_sec)
        mid = seg.start + seg.duration / 2
        s = min(max(mid - max_sec / 2, seg.start), seg.end - max_sec)
        return MotionSegment(s, s + max_sec, seg.score)

    @staticmethod
    def _densest_window(seg: MotionSegment, ts_list: list[float],
                        max_sec: float) -> MotionSegment:
        """在 ts_list 中滑动 max_sec 窗口，取覆盖时间点最多的窗口"""
        best_s, best_cnt = ts_list[0], -1
        for t in ts_list:
            s = min(max(t - max_sec / 2, seg.start), seg.end - max_sec)
            cnt = sum(1 for x in ts_list if s <= x <= s + max_sec)
            if cnt > best_cnt:
                best_cnt, best_s = cnt, s
        return MotionSegment(best_s, best_s + max_sec, seg.score)

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

    def _get_file_for_segment(
        self, seg: MotionSegment, video_files: list[Path]
    ) -> Path | None:
        """根据片段时间戳找到对应的源文件"""
        for vf in video_files:
            try:
                result = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(vf)],
                    capture_output=True, text=True, timeout=30,
                )
                if result.stdout:
                    duration = float(result.stdout.strip())
                    if seg.start <= duration:
                        return vf
                    seg.start -= duration
                    seg.end -= duration
                else:
                    seg.start -= 10
                    seg.end -= 10
            except Exception:
                seg.start -= 10
                seg.end -= 10
        return video_files[-1] if video_files else None

    def _clip_and_concat(
        self, segments: list[tuple[MotionSegment, Path]], output: Path
    ) -> Path | None:
        temp_dir = tempfile.mkdtemp(prefix="timecut_")
        concat_file = Path(temp_dir) / "files.txt"
        try:
            clip_paths = []
            for i, (seg, src) in enumerate(segments):
                if not src.exists():
                    logger.warning(f"源文件不存在: {src}，跳过片段 {i}")
                    continue
                clip_path = Path(temp_dir) / f"clip_{i:04d}.ts"
                cmd = [
                    "ffmpeg", "-y", "-accurate_seek",
                    "-i", str(src),
                    "-ss", str(seg.start), "-t", str(seg.duration),
                    "-c", "copy", "-avoid_negative_ts", "make_zero",
                    str(clip_path),
                ]
                subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if clip_path.exists() and clip_path.stat().st_size > 0:
                    clip_paths.append(clip_path)
            if not clip_paths:
                logger.error("所有片段提取失败")
                return None
            with open(concat_file, "w") as f:
                for cp in clip_paths:
                    f.write(f"file '{cp}'\n")
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(concat_file),
                 "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                 "-c:a", "aac", "-b:a", "64k",
                 "-movflags", "+faststart", str(output)],
                capture_output=True, text=True, timeout=600,
            )
            if output.exists() and output.stat().st_size > 0:
                logger.info(f"精华视频已生成: {output} ({output.stat().st_size / 1024 / 1024:.1f}MB)")
                return output
            else:
                logger.error(f"精华视频生成失败: {result.stderr[-300:]}")
                return None
        except subprocess.TimeoutExpired:
            logger.error("精华视频生成超时")
            return None
        except Exception as e:
            logger.error(f"精华视频生成异常: {e}")
            return None
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)