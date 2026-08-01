"""精华剪辑器 - 将多个运动片段拼接成一个精华视频"""

import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from config import settings
from .detector import MotionSegment

logger = logging.getLogger("timecut.clipper")


class HighlightClipper:
    """将运动片段列表合并为一段精华视频"""

    def __init__(self):
        self.target_duration = settings.highlight_duration_minutes * 60

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
            # 用录像日期命名，避免同一天多次生成覆盖同名文件
            tag = date.replace("-", "") if date else datetime.now().strftime("%Y%m%d")
            output_path = settings.highlights_dir / f"精华_{tag}.mp4"
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

        # 按运动分数从高到低挑选，凑满目标时长
        sorted_segs = sorted(segments, key=lambda s: s[0].score, reverse=True)
        selected = []
        sel_total = 0.0
        for seg, src in sorted_segs:
            if sel_total + seg.duration > self.target_duration:
                remaining = self.target_duration - sel_total
                if remaining >= 10:
                    selected.append((MotionSegment(seg.start, seg.start + remaining, seg.score), src))
                    sel_total = self.target_duration
                break
            selected.append((seg, src))
            sel_total += seg.duration
        # 按当天真实发生时间排序，保证精华视频按时间顺序播放
        selected.sort(key=global_start)
        return selected

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