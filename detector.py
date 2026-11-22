"""Person detection with a pretrained YOLO model (Ultralytics) via OpenCV frames.

If Ultralytics is not installed, falls back to OpenCV's built-in HOG people
detector so the app still runs (less accurate).
"""
from dataclasses import dataclass
from typing import List

import cv2


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class PersonDetector:
    def __init__(self, model_name: str = "yolov8n.pt", confidence: float = 0.4):
        self.confidence = confidence
        self.backend = "none"
        self._model = None
        self._hog = None
        try:
            from ultralytics import YOLO           # downloads yolov8n.pt on first use
            self._model = YOLO(model_name)
            self.backend = "YOLO"
        except Exception:                          # ImportError, download failure, ...
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self.backend = "OpenCV HOG (fallback)"

    def detect(self, frame) -> List[Detection]:
        return self._detect_yolo(frame) if self._model else self._detect_hog(frame)

    def _detect_yolo(self, frame) -> List[Detection]:
        result = self._model(frame, classes=[0], conf=self.confidence, verbose=False)[0]
        out = []
        for box, conf in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist()):
            x1, y1, x2, y2 = map(int, box)
            out.append(Detection(x1, y1, x2, y2, float(conf)))
        return out

    def _detect_hog(self, frame) -> List[Detection]:
        h, w = frame.shape[:2]
        scale = 640 / w if w > 640 else 1.0
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
        rects, weights = self._hog.detectMultiScale(small, winStride=(8, 8), scale=1.05)
        out = []
        for (x, y, rw, rh), wt in zip(rects, weights):
            out.append(Detection(int(x / scale), int(y / scale),
                                 int((x + rw) / scale), int((y + rh) / scale), float(wt)))
        return out

    @staticmethod
    def draw(frame, detections: List[Detection]):
        """Draw bounding boxes on a copy of the frame."""
        img = frame.copy()
        for d in detections:
            cv2.rectangle(img, (d.x1, d.y1), (d.x2, d.y2), (0, 200, 0), 2)
            cv2.putText(img, f"person {d.confidence:.2f}", (d.x1, max(15, d.y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 2)
        cv2.putText(img, f"People: {len(detections)}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return img
