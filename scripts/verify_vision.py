"""Actual local model checks on attributed images; no webcam or external API."""

import io
import json
import time
from pathlib import Path

from app.providers.vision import get_vision, validate_frame
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
detector = get_vision()
empty = io.BytesIO()
Image.new("RGB", (320, 240), "gray").save(empty, format="JPEG")
for name, data, persons, phone in [
    ("one person", (ROOT / "tests/fixtures/vision/one.jpg").read_bytes(), 1, False),
    ("no person", empty.getvalue(), 0, False),
    (
        "two person composition",
        (ROOT / "tests/fixtures/vision/two.jpg").read_bytes(),
        2,
        False,
    ),
    ("phone", (ROOT / "tests/fixtures/vision/phone.jpg").read_bytes(), None, True),
]:
    validate_frame(data, "image/jpeg")
    started = time.monotonic()
    result = detector.detect(data)
    assert persons is None or result.persons == persons, name
    assert result.phone == phone, name
    print(
        json.dumps(
            {
                "fixture": name,
                **result.model_dump(),
                "measured_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )
print(json.dumps({"checks_passed": 4, "physical_camera": "pending"}))
