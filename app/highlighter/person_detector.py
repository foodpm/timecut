"""YOLO 人物检测器 - OpenCV DNN 运行 YOLO11n ONNX 模型，判断运动片段里是否有人

官方导出的 YOLOv8/YOLO11 ONNX 模型输入固定 640x640，输出形状 (1, 4+80, N)，
其中类别 0 = person。检测结果用于精华片段的人物过滤 + 长片段内
"人物最密集"的 20 秒窗口选取。

模型加载失败 / OpenCV 不可用时不中断流程（available=False，所有片段放行）。
"""

import logging
from pathlib import Path

try:
    import cv2
    import numpy as np
    _CV_READY = True
except ImportError:
    _CV_READY = False

from config import settings
from highlighter.ai_selector import extract_frame

logger = logging.getLogger("timecut.person_detector")

COCO_PERSON_CLASS = 0
MODEL_INPUT_SIZE = 640  # 官方导出模型的固定输入尺寸


class PersonDetector:
    """加载一次模型；available=False 时不做任何过滤"""

    def __init__(self):
        self.conf = float(getattr(settings, "yolo_confidence", 0.4))
        self.available = False
        self._net = None
        if not _CV_READY:
            logger.warning("OpenCV 未安装，YOLO 人物过滤禁用")
            return
        model_path = Path(getattr(settings, "yolo_model_path", "") or "")
        if not model_path.exists():
            logger.warning(f"YOLO 模型不存在: {model_path}，人物过滤禁用")
            return
        try:
            self._net = cv2.dnn.readNetFromONNX(str(model_path))
            self._net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
            self._net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
            self.available = True
            logger.info(f"YOLO 人物检测已启用: {model_path}")
        except Exception as e:
            logger.error(f"YOLO 模型加载失败: {e}，人物过滤禁用")

    def person_timestamps(self, video_path: Path, start: float, end: float,
                          frames: int) -> list[float]:
        """在 [start, end] 区间内均匀采样 frames 帧，返回检测到人的时间戳（绝对秒）"""
        if not self.available or frames <= 0:
            return []
        hits = []
        for i in range(frames):
            ts = start + (end - start) * (i + 0.5) / frames
            jpeg = extract_frame(video_path, ts)
            if jpeg and self._frame_has_person(jpeg):
                hits.append(ts)
        return hits

    def _frame_has_person(self, jpeg: bytes) -> bool:
        """判断一帧 JPEG 是否检测到人（存在任一 > 置信度阈值的 person 框）"""
        arr = np.frombuffer(jpeg, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return False
        letterboxed = self._letterbox(frame)
        blob = cv2.dnn.blobFromImage(
            letterboxed, 1 / 255.0,
            (MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), (0, 0, 0), swapRB=True,
        )
        self._net.setInput(blob)
        pred = self._net.forward()        # (1, 4+80, N)
        pred = pred[0].transpose(1, 0)    # (N, 4+80)
        scores = pred[:, 4:]              # (N, 80)
        ids = scores.argmax(axis=1)
        confs = scores.max(axis=1)
        for cls_id, conf in zip(ids, confs):
            if int(cls_id) == COCO_PERSON_CLASS and float(conf) >= self.conf:
                return True
        return False

    @staticmethod
    def _letterbox(img):
        """等比缩放并居中填充到模型输入尺寸（无畸变）"""
        h, w = img.shape[:2]
        r = min(MODEL_INPUT_SIZE / w, MODEL_INPUT_SIZE / h)
        nw, nh = max(1, int(round(w * r))), max(1, int(round(h * r)))
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE, 3), 114, dtype=np.uint8)
        top, left = (MODEL_INPUT_SIZE - nh) // 2, (MODEL_INPUT_SIZE - nw) // 2
        canvas[top:top + nh, left:left + nw] = resized
        return canvas
