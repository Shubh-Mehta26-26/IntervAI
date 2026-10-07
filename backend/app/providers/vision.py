"""Local inference only. No identity, demographic, emotion, or intent estimation."""

import io
import threading
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.schemas.vision import Detection


class VisionError(RuntimeError):
    pass


class VisionBusy(VisionError):
    pass


def validate_frame(data: bytes, content_type: str):
    if len(data) > 131072:
        raise VisionError("Frame exceeds 128 KB.")
    if content_type not in {"image/jpeg", "image/png"}:
        raise VisionError("Use JPEG or PNG.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"JPEG", "PNG"} or image.format != (
                "JPEG" if content_type == "image/jpeg" else "PNG"
            ):
                raise VisionError("Image type does not match its content.")
            width, height = image.size
            if not (32 <= width <= 640 and 32 <= height <= 640):
                raise VisionError("Frame dimensions must be between 32 and 640 pixels.")
            if getattr(image, "n_frames", 1) != 1:
                raise VisionError("Animated images are not supported.")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise VisionError("Invalid image.") from exc


class LocalVision:
    def __init__(self, directory):
        cv2.setNumThreads(1)
        self.net = cv2.dnn.readNetFromTensorflow(
            str(directory / "ssd.pb"), str(directory / "ssd.pbtxt")
        )
        self.lock = threading.Lock()

    def detect(self, data: bytes) -> Detection:
        if not self.lock.acquire(blocking=False):
            raise VisionBusy("Local vision processing is busy; drop this frame.")
        try:
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise VisionError("Invalid decoded image.")
            self.net.setInput(cv2.dnn.blobFromImage(image, size=(300, 300), swapRB=True))
            output = self.net.forward().reshape(-1, 7)
            threshold = get_settings().vision_detection_threshold
            persons, phones = [], []
            for _, label, score, *_ in output:
                if not np.isfinite(score) or not threshold <= score <= 1:
                    continue
                if int(label) == 1:
                    persons.append(float(score))
                elif int(label) == 77:
                    phones.append(float(score))
            return Detection(
                persons=len(persons),
                person_confidence=max(persons, default=None),
                phone=bool(phones),
                phone_confidence=max(phones, default=None),
            )
        except cv2.error as exc:
            raise VisionError("Local vision inference failed.") from exc
        finally:
            self.lock.release()


@lru_cache(maxsize=1)
def get_vision():
    try:
        return LocalVision(get_settings().vision_model_dir)
    except (cv2.error, OSError) as exc:
        raise VisionError("Install the local vision model before enabling monitoring.") from exc


def vision_status():
    if not get_settings().vision_enabled:
        return {"available": False, "message": "Visual monitoring is disabled by configuration."}
    try:
        get_vision()
        return {"available": True, "message": "Optional local visual monitoring is available."}
    except VisionError:
        return {
            "available": False,
            "message": "Local vision model is unavailable. The interview remains usable.",
        }
